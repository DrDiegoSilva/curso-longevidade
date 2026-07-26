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
         "criado_em", "cancelado_em", "cancel_motivo", "oferta_retencao_em",
         "termos_versao", "termos_aceito_em", "termos_ip", "valor_contratado", "senha_hash"]


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
    # nome padronizado em MAIÚSCULO (cadastro consistente em todas as vias de criação)
    vals = [((d.get(k) or "").strip().upper() if k == "nome" else d.get(k)) for k in _COLS]
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
        ac = s.get("acesso_ate")          # cortesia com prazo: ATIVO + acesso_ate no futuro
        return _futuro(ac, agora) if ac else True   # pago/vitalício sem data = sempre

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


def por_payment(pid):
    """Assinante cuja última cobrança em arquivo é este pagamento. None se vazio/sem match.

    Existe para os eventos que NÃO trazem `subscription` (estorno/chargeback/overdue de Pix
    ou de cartão parcelado): sem isto, `por_subscription` devolvia None e o evento era
    descartado como "ignorado", deixando acesso ativo depois de um estorno.
    """
    if not pid:
        return None
    _ensure()
    with db._conn() as c:
        r = c.execute("SELECT * FROM subscribers WHERE asaas_payment_id=?", (pid,)).fetchone()
    return dict(r) if r else None


def por_whatsapp(w):
    n = _norm(w)
    return next((s for s in listar() if _norm(s.get("whatsapp", "")) == n), None)


def por_cpf(c):
    """Assinante com esse CPF (compara só os dígitos). None se não achar/vazio."""
    import cpf as cpfmod
    n = cpfmod.so_digitos(c)
    if not n:
        return None
    return next((s for s in listar() if cpfmod.so_digitos(s.get("cpf", "")) == n), None)


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
           # Aceite feito no checkout (Task 7): copiado do pending pro assinante, pra
           # quem já aceitou lá não cair na tela de re-aceite (subscribers.precisa_aceitar).
           "termos_versao": pending.get("termos_versao") or "",
           "termos_aceito_em": datetime.now().isoformat() if pending.get("termos_versao") else "",
           "termos_ip": pending.get("termos_ip") or "",
           "valor_contratado": pending.get("valor_contratado"),
           "criado_em": datetime.now().isoformat()}
    _insert(reg)
    return reg


def marcar_status(id, status, **campos):
    _ensure()
    campos["status"] = status
    sets = ",".join(f"{k}=?" for k in campos)
    with db._conn() as c:
        c.execute(f"UPDATE subscribers SET {sets} WHERE id=?", list(campos.values()) + [id])


# registrar_cancelamento foi removida de propósito: gravar o cancelamento agora é
# db.claim_cancelamento, um UPDATE condicional único que é ao mesmo tempo a gravação e o
# claim contra corrida. Manter um segundo caminho de escrita (incondicional) só serviria
# para alguém, um dia, cancelar por fora do claim e reabrir a janela de duplo estorno.


def definir_senha(id, senha_hash):
    """Grava o hash da senha do assinante (nunca a senha crua)."""
    _ensure()
    with db._conn() as c:
        c.execute("UPDATE subscribers SET senha_hash=? WHERE id=?", (senha_hash, id))


def por_id(id):
    _ensure()
    with db._conn() as c:
        r = c.execute("SELECT * FROM subscribers WHERE id=?", (id,)).fetchone()
    return dict(r) if r else None


def atualizar_contato(id, nome, email):
    """Atualiza nome e e-mail do assinante (edição na página de dados)."""
    _ensure()
    with db._conn() as c:
        c.execute("UPDATE subscribers SET nome=?, email=? WHERE id=?",
                  ((nome or "").strip().upper(), (email or "").strip(), id))


def atualizar_whatsapp(id, novo):
    """Troca o número (normalizado). Só chamar após confirmação por OTP no número novo."""
    _ensure()
    with db._conn() as c:
        c.execute("UPDATE subscribers SET whatsapp=? WHERE id=?", (_norm(novo), id))


def definir_curador(id, on):
    """Liga/desliga o flag 'curador' (recebe a revisão das 18h). Fora de _COLS de
    propósito: o upsert de pagamento não pode zerar essa escolha."""
    _ensure()
    with db._conn() as c:
        c.execute("UPDATE subscribers SET curador=? WHERE id=?", (1 if on else 0, id))


def slot_de(sub):
    """Slot do assinante (config.SLOTS). NULL/vazio/inválido -> config.SLOT_DEFAULT."""
    s = (sub or {}).get("slot_envio")
    return s if s in config.SLOTS else config.SLOT_DEFAULT


def definir_slot(id, slot):
    """Grava o slot de envio (só se ∈ config.SLOTS). Fora de _COLS de propósito não é —
    slot_envio ESTÁ em _COLS, mas o upsert de pagamento não manda slot, então preserva."""
    if slot not in config.SLOTS:
        return
    _ensure()
    with db._conn() as c:
        c.execute("UPDATE subscribers SET slot_envio=? WHERE id=?", (slot, id))


def curadores():
    """Assinantes ATIVOS marcados como curador (recebem o resumo do dia p/ revisar)."""
    return [s for s in ativos() if s.get("curador")]


def contar_por_slot():
    """Quantos assinantes ATIVOS em cada slot (config.SLOTS). NULL/vazio conta como default."""
    cont = {s: 0 for s in config.SLOTS}
    for s in ativos():
        cont[slot_de(s)] = cont.get(slot_de(s), 0) + 1
    return cont


def slots_com_vaga(teto, slot_atual=None):
    """Slots (na ordem de config.SLOTS) com count < teto. O slot_atual é sempre incluído
    (pra o assinante poder manter o horário mesmo se lotou depois)."""
    cont = contar_por_slot()
    return [s for s in config.SLOTS if cont.get(s, 0) < int(teto) or s == slot_atual]


def precisa_aceitar(sub):
    """True quando o assinante ainda não aceitou a versão vigente dos termos.
    Vale tanto pra base antiga (nunca aceitou) quanto pra quem aceitou versão anterior."""
    import legal
    return (sub or {}).get("termos_versao") != legal.VERSAO


def registrar_aceite(id, versao, ip=""):
    """Grava o aceite: versão, momento e IP — é a prova de que o assinante concordou."""
    _ensure()
    with db._conn() as c:
        c.execute("UPDATE subscribers SET termos_versao=?, termos_aceito_em=?, termos_ip=? WHERE id=?",
                  (versao, datetime.now().isoformat(), ip or "", id))
