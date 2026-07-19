"""Rascunho do dia: persistência em /data/drafts + máquina de estado."""
import os
import json
import secrets
import glob
from datetime import datetime
import config

VALIDOS = {"DRAFT", "APPROVED", "EDITED", "SKIPPED", "SENT"}


def _path(data_iso):
    return os.path.join(config.drafts_dir(), f"{data_iso}.json")


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
    os.makedirs(config.drafts_dir(), exist_ok=True)
    with open(_path(r["data"]), "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=1)


def carregar(data_iso):
    try:
        return json.load(open(_path(data_iso), encoding="utf-8"))
    except Exception:
        return None


def por_token(token):
    for p in glob.glob(os.path.join(config.drafts_dir(), "*.json")):
        try:
            r = json.load(open(p, encoding="utf-8"))
            if r.get("review_token") == token:
                return r
        except Exception:
            pass
    return None


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
