"""Rascunho do dia + máquina de estado.

PERSISTIDO NO BANCO (Supabase/`daily_drafts`), não mais em /data/drafts.
Motivo: /data é efêmero — apagado a cada deploy/restart do container. O estudo
preparado às 18h precisa sobreviver até o envio das 08h. API pública inalterada
(novo_rascunho/salvar/carregar/por_token/pode_enviar/aplicar) — daily.py não muda.
"""
import secrets
from datetime import datetime
import db

VALIDOS = {"DRAFT", "APPROVED", "EDITED", "SKIPPED", "SENT"}


def novo_rascunho(data_iso, artigo, resumo, pdf_path):
    return {
        "data": data_iso,
        "status": "DRAFT",
        "review_token": secrets.token_urlsafe(24),
        "artigo": artigo,
        "resumo": resumo,
        "pdf_path": pdf_path,
        "criado_em": datetime.now().isoformat(),
        "decidido_em": None,
    }


def salvar(r):
    db.init()
    db.salvar_draft(r["data"], r.get("review_token", ""), r.get("status", "DRAFT"), r)


def carregar(data_iso):
    db.init()
    return db.obter_draft(data_iso)


def por_token(token):
    db.init()
    return db.obter_draft_por_token(token)


def pode_enviar(status):
    return status not in ("SKIPPED", "SENT")


def _guardar_texto(r, texto):
    """Grava o texto editado no rascunho. Vale pra APROVAR **e** editar.

    O `aprovar` não gravava — e a tela tem UMA caixa de texto e dois botões que parecem
    salvar. Quem editava e clicava no principal perdia a edição em silêncio, e o texto
    original ia pros assinantes (aconteceu em 2026-08-11: o nome do Diego saiu no PDF
    apesar de ele ter editado na véspera).

    Texto vazio/ausente é no-op: POST antigo ou forjado não pode zerar o estudo do dia.
    """
    novo = texto or r.get("resumo", "")
    if novo == r.get("resumo", ""):
        return
    r["resumo"] = novo
    # O preview das 18h tem o texto VELHO. Sem zerar, o "📄 Ver PDF" devolve a versão
    # antiga e a edição parece não ter pegado — e pior, de forma intermitente (o /data
    # some no deploy e aí regenera certo). O serve.py regenera quando `pdf_path` é vazio.
    r["pdf_path"] = ""


def _guardar_kit(r, kit):
    """Grava o kit de marketing editado. `None` = formulário não trouxe kit -> no-op.

    Mexer no kit invalida o preview: senão o "📄 Ver PDF" devolve a versão velha e a
    edição parece não ter pegado — o mesmo alçapão do texto e da área.
    """
    import json
    if kit is None:
        return
    novo = json.dumps(kit, ensure_ascii=False)
    if novo == (r.get("gancho") or ""):
        return
    r["gancho"] = novo
    r["pdf_path"] = ""


def aplicar(data_iso, acao, texto=None, area=None, kit=None):
    """Aplica a decisão do curador. `area` viaja junto com aprovar/editar (o <select>
    da tela de revisão fica dentro do mesmo form dos botões) — vetar o dia não é hora
    de mexer na área."""
    import area_estudo
    r = carregar(data_iso)
    if not r:
        raise ValueError("rascunho não encontrado")
    # A área ANTES do status: a guarda de "já enviado" mora em `area_estudo.pode_corrigir`
    # e lê `r["status"]` — sobrescrever o status primeiro apagaria o SENT que ela procura.
    if acao == "aprovar":
        area_estudo.aplicar_no_rascunho(r, area)
        _guardar_texto(r, texto)
        _guardar_kit(r, kit)
        r["status"] = "APPROVED"
    elif acao == "editar":
        area_estudo.aplicar_no_rascunho(r, area)
        _guardar_texto(r, texto)
        _guardar_kit(r, kit)
        r["status"] = "EDITED"
    elif acao == "nao_enviar":
        r["status"] = "SKIPPED"
    else:
        raise ValueError(f"ação inválida: {acao}")
    r["decidido_em"] = datetime.now().isoformat()
    salvar(r)
    return r
