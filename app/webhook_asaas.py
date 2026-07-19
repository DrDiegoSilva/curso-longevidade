"""Webhook do Asaas: valida token, idempotência e aplica a ação no assinante.
`decidir` é puro/testável; `processar` orquestra (db + subscribers + WhatsApp).
"""
from datetime import datetime, timedelta
import config
import db
import subscribers

CARENCIA_DIAS = 3
_CICLO_DIAS = {"WEEKLY": 7, "BIWEEKLY": 14, "MONTHLY": 30, "BIMONTHLY": 61,
               "QUARTERLY": 91, "SEMIANNUALLY": 182, "YEARLY": 365}


def decidir(event, sub_existe):
    """event + se já existe assinante -> ação (puro)."""
    e = (event or "").upper()
    if e in ("PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"):
        return "RENOVAR" if sub_existe else "ATIVAR"
    if e == "PAYMENT_OVERDUE":
        return "INADIMPLENTE"
    if e in ("PAYMENT_REFUNDED", "PAYMENT_DELETED", "PAYMENT_CHARGEBACK_REQUESTED"):
        return "SUSPENDER"
    return "IGNORAR"


def _proximo_venc(cycle, ref=None):
    try:
        base = datetime.fromisoformat(ref) if ref else datetime.now()
    except Exception:
        base = datetime.now()
    return (base + timedelta(days=_CICLO_DIAS.get(cycle, 30))).date().isoformat()


def _boas_vindas(whatsapp, nome, enviar_fn):
    msg = (f"✅ Assinatura confirmada — bem-vindo(a) à *Atualização Científica*"
           f"{', ' + nome if nome else ''}!\n\n"
           f"Seu acesso ao portal é com ESTE número de WhatsApp. Entre em "
           f"{config.PUBLIC_URL}/entrar e peça o código.\n\n"
           f"A partir do próximo dia útil você começa a receber os resumos aqui.")
    try:
        enviar_fn(whatsapp, msg)
    except Exception as e:
        print(f"[webhook] boas-vindas falhou: {e}", flush=True)


def processar(body, token_header, enviar_fn=None):
    """Retorna (status_code, msg). Idempotente. token_header valida a origem."""
    if not config.ASAAS_WEBHOOK_TOKEN or token_header != config.ASAAS_WEBHOOK_TOKEN:
        return (401, "unauthorized")
    if enviar_fn is None:
        import deliver
        enviar_fn = deliver.enviar_texto

    event = (body or {}).get("event")
    pay = (body or {}).get("payment") or {}
    pid = pay.get("id") or ""
    if not db.registrar_webhook(pid, event):
        return (200, "duplicado")

    sid = pay.get("subscription")
    sub = subscribers.por_subscription(sid)
    acao = decidir(event, sub is not None)

    if acao == "ATIVAR":
        pending = db.obter_pending(pay.get("externalReference"))
        if not pending:
            return (200, "sem-pending")   # cortesia/já processado
        plano = config.plano_por_slug(pending.get("plano", "")) or {}
        prox = _proximo_venc(plano.get("cycle", "MONTHLY"), pay.get("dueDate"))
        subscribers.criar_de_pagamento(pending, {
            "customer": pay.get("customer"), "subscription": sid,
            "payment": pid, "proximo_vencimento": prox})
        _boas_vindas(subscribers._norm(pending.get("whatsapp", "")), pending.get("nome", ""), enviar_fn)
        return (200, "ativado")

    if acao == "RENOVAR" and sub:
        plano = config.plano_por_slug(sub.get("plano", "")) or {}
        prox = _proximo_venc(plano.get("cycle", "MONTHLY"), pay.get("dueDate"))
        subscribers.marcar_status(sub["id"], "ATIVO", carencia_ate=None,
                                  proximo_vencimento=prox, aviso_renov_em=None)
        return (200, "renovado")

    if acao == "INADIMPLENTE" and sub:
        carencia = (datetime.now() + timedelta(days=CARENCIA_DIAS)).isoformat()
        subscribers.marcar_status(sub["id"], "INADIMPLENTE", carencia_ate=carencia)
        return (200, "inadimplente")

    if acao == "SUSPENDER" and sub:
        subscribers.marcar_status(sub["id"], "CANCELADO", acesso_ate=datetime.now().isoformat())
        return (200, "suspenso")

    return (200, "ignorado")
