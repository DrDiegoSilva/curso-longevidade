"""Lista-semente de assinantes em /data/subscribers.json (manual na Fase 1)."""
import os
import json
import secrets
from datetime import datetime
import config


def _load():
    try:
        return json.load(open(config.subscribers_path(), encoding="utf-8"))
    except Exception:
        return []


def _save(rows):
    os.makedirs(config.DATA, exist_ok=True)
    with open(config.subscribers_path(), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)


def listar():
    return _load()


def ativos():
    return [r for r in _load() if r.get("status") == "ATIVO"]


def adicionar(nome, whatsapp):
    rows = _load()
    reg = {
        "id": secrets.token_hex(6),
        "nome": nome.strip(),
        "whatsapp": "".join(c for c in whatsapp if c.isdigit()),
        "status": "ATIVO",
        "criado_em": datetime.now().isoformat(),
    }
    rows.append(reg)
    _save(rows)
    return reg


def remover(id):
    rows = _load()
    novo = [r for r in rows if r.get("id") != id]
    _save(novo)
    return len(novo) != len(rows)
