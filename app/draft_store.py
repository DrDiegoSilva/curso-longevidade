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


def aplicar(data_iso, acao, texto=None):
    r = carregar(data_iso)
    if not r:
        raise ValueError("rascunho não encontrado")
    if acao == "aprovar":
        r["status"] = "APPROVED"
    elif acao == "editar":
        r["status"] = "EDITED"
        r["resumo"] = texto or r["resumo"]
    elif acao == "nao_enviar":
        r["status"] = "SKIPPED"
    else:
        raise ValueError(f"ação inválida: {acao}")
    r["decidido_em"] = datetime.now().isoformat()
    salvar(r)
    return r
