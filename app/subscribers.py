"""Assinantes em SQLite (artigos.db). API pública estável (listar/ativos/adicionar/
remover) para daily/auth/admin; + funções de cobrança (status, cancelamento).
Migra o antigo subscribers.json 1× (idempotente).
"""
import secrets
from datetime import datetime
import config
import db
import phone

_migrado = False

_COLS = ["id", "nome", "whatsapp", "email", "cpf", "plano", "metodo", "status",
         "asaas_customer_id", "asaas_subscription_id", "asaas_payment_id",
         "proximo_vencimento", "acesso_ate", "carencia_ate", "aviso_renov_em",
         "criado_em", "cancelado_em", "cancel_motivo", "oferta_retencao_em", "senha_hash"]


def _norm(w):
    return phone.normalizar(w)


def _ensure():
    global _migrado
    db.init()
    if not _migrado:
        _migrar_json()
        _migrado = True


def _migrar_json():
    with db._conn() as c:
        if c.execute("SELECT COUNT(*) n FROM subscribers").fetchone()["n"]:
            return
    import json
    try:
        with open(config.subscribers_path(), encoding="utf-8") as f:
            rows = json.load(f)
    except Exception:
        rows = []
    for r in rows:
        _insert({"id": r.get("id") or secrets.token_hex(6), "nome": r.get("nome", ""),
                 "whatsapp": _norm(r.get("whatsapp", "")), "status": r.get("status", "ATIVO"),
                 "criado_em": r.get("criado_em") or datetime.now().isoformat()})


def _insert(d):
    vals = [d.get(k) for k in _COLS]
    ph = ",".join("?" * len(_COLS))
    updates = ",".join(f"{k}=excluded.{k}" for k in _COLS if k != "id")
    with db._conn() as c:
        c.execute(f"INSERT INTO subscribers ({','.join(_COLS)}) VALUES ({ph}) "
                  f"ON CONFLICT (id) DO UPDATE SET {updates}", vals)


def listar():
    _ensure()
    with db._conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM subscribers ORDER BY criado_em DESC")]


def _futuro(iso, agora):
    if not iso:
        return False
    try:
        return datetime.fromisoformat(iso) > agora
    except Exception:
        return False


def tem_acesso(s, agora=None):
    """Quem pode receber/logar: ATIVO, ou INADIMPLENTE na carência, ou CANCELADO no período pago."""
    agora = agora or datetime.now()
    st = s.get("status")
    if st == "ATIVO":
        return True
    if st == "INADIMPLENTE":
        return _futuro(s.get("carencia_ate"), agora)
    if st == "CANCELADO":
        return _futuro(s.get("acesso_ate"), agora)
    return False


def ativos():
    return [s for s in listar() if tem_acesso(s)]


def adicionar(nome, whatsapp):
    """Cadastro manual/cortesia (ATIVO, sem Asaas)."""
    _ensure()
    reg = {"id": secrets.token_hex(6), "nome": (nome or "").strip(), "whatsapp": _norm(whatsapp),
           "status": "ATIVO", "criado_em": datetime.now().isoformat()}
    _insert(reg)
    return reg


def remover(id):
    _ensure()
    with db._conn() as c:
        return c.execute("DELETE FROM subscribers WHERE id=?", (id,)).rowcount > 0


def por_subscription(sid):
    if not sid:
        return None
    _ensure()
    with db._conn() as c:
        r = c.execute("SELECT * FROM subscribers WHERE asaas_subscription_id=?", (sid,)).fetchone()
    return dict(r) if r else None


def por_whatsapp(w):
    n = _norm(w)
    return next((s for s in listar() if _norm(s.get("whatsapp", "")) == n), None)


def criar_de_pagamento(pending, dados_asaas=None, status="ATIVO"):
    """Cria/ativa assinante a partir do cadastro (pending) + ids do Asaas."""
    _ensure()
    a = dados_asaas or {}
    reg = {"id": secrets.token_hex(6), "nome": pending.get("nome", ""),
           "whatsapp": _norm(pending.get("whatsapp", "")), "email": pending.get("email", ""),
           "cpf": pending.get("cpf", ""), "plano": pending.get("plano", ""),
           "metodo": pending.get("metodo", ""), "status": status,
           "asaas_customer_id": a.get("customer"), "asaas_subscription_id": a.get("subscription"),
           "asaas_payment_id": a.get("payment"), "proximo_vencimento": a.get("proximo_vencimento"),
           "criado_em": datetime.now().isoformat()}
    _insert(reg)
    return reg


def marcar_status(id, status, **campos):
    _ensure()
    campos["status"] = status
    sets = ",".join(f"{k}=?" for k in campos)
    with db._conn() as c:
        c.execute(f"UPDATE subscribers SET {sets} WHERE id=?", list(campos.values()) + [id])


def registrar_cancelamento(id, motivo, acesso_ate=None):
    marcar_status(id, "CANCELADO", cancel_motivo=motivo,
                  cancelado_em=datetime.now().isoformat(), acesso_ate=acesso_ate)


def definir_senha(id, senha_hash):
    """Grava o hash da senha do assinante (nunca a senha crua)."""
    _ensure()
    with db._conn() as c:
        c.execute("UPDATE subscribers SET senha_hash=? WHERE id=?", (senha_hash, id))
