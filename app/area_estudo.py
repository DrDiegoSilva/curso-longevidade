"""Corrigir a ÁREA de um estudo — o lugar único que sabe escrever a área onde ela vale.

Nasceu do estudo de 2026-08-10: subido à mão antes da detecção automática, saiu com
"MEUS ESTUDOS" na capa do PDF e não havia NENHUM lugar no sistema pra corrigir.

Por que corrigir o rascunho basta: `daily.enviar_slot` monta o PDF na HORA do envio
(08h) a partir de `artigo["tema"]`, então uma correção feita entre as 18h e as 08h
conserta de uma vez a capa do PDF, o badge do WhatsApp e a página do portal.

Módulo próprio (e não mais uma função no `daily.py`, que já tem 35 KB) porque as fatias
2 e 3 do item 36 pedem os irmãos deste `aplicar_no_rascunho`: escrever a área no
`digests` (estudo já enviado) e na reserva (dias futuros).
"""
import json
import os

_CFG_PATH = os.path.join(os.path.dirname(__file__), "temas_config.json")


def areas():
    """As chaves de área do `temas_config.json` — as mesmas que dão rótulo, emoji e cor
    à capa do PDF (`daily._tema_meta`)."""
    with open(_CFG_PATH, encoding="utf-8") as f:
        return list(json.load(f).get("temas", {}).keys())


def valida(area, atual):
    """A área pedida, se for uma chave de verdade; senão a atual (no-op).

    `/revisar/<token>` é rota pública, protegida só pelo token, e a área vai parar na
    capa do PDF que o assinante recebe. Só passa chave que está no `temas_config.json`
    — mesma guarda do `triage.extrair_metadados`, pelo mesmo motivo.

    NÃO faz casefold de propósito: 'obesidade' minúsculo não é chave da config, e
    `_tema_meta` devolveria o nome cru como rótulo da capa. É exatamente assim que
    "MEUS ESTUDOS" foi parar num PDF.
    """
    pedida = (area or "").strip()
    return pedida if pedida in areas() else atual


def aplicar_no_rascunho(r, area):
    """Escreve a área no rascunho de amanhã. Devolve True se mudou algo.

    Muta `r` no lugar, como o vizinho `draft_store.aplicar` — quem chama é dono do
    dicionário e o persiste logo em seguida.
    """
    art = r.get("artigo")
    if not isinstance(art, dict):
        return False
    atual = art.get("tema", "")
    nova = valida(area, atual)
    if nova == atual:
        return False
    art["tema"] = nova
    # O preview das 18h está no disco com a capa ERRADA. Sem zerar isto, o "📄 Ver PDF"
    # devolve o PDF velho e a correção parece não ter funcionado. O `serve.py` regenera
    # sob demanda quando `pdf_path` está vazio, já lendo o tema novo.
    r["pdf_path"] = ""
    _gravar_na_reserva(r.get("reserva_id"), nova)
    return True


def _gravar_na_reserva(reserva_id, area):
    """Leva a correção ao registro de ORIGEM: se o estudo for trocado (🔁) depois, ele
    volta ao estoque com a área já certa em vez de a correção evaporar.

    Acabamento, não o essencial — o que sai amanhã é o rascunho. Banco fora do ar não
    pode fazer a capa sair errada.
    """
    if not reserva_id:
        return
    try:
        import db
        db.atualizar_reserva(reserva_id, tema=area)
    except Exception as e:
        print(f"[area] gravar área na reserva {reserva_id} falhou: {e}", flush=True)
