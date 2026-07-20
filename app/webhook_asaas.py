"""Webhook do Asaas: valida token, idempotência e aplica a ação no assinante.
`decidir` é puro/testável; `processar` orquestra (db + subscribers + WhatsApp).
"""
import hmac
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


def _boas_vindas(whatsapp, nome, email, enviar_fn):
    """Confirma a assinatura e manda o link de CRIAR SENHA nos dois canais (WhatsApp + e-mail)."""
    import auth_web
    try:
        link = auth_web.preparar_primeiro_acesso(whatsapp)
    except Exception as e:
        print(f"[webhook] preparar 1º acesso falhou: {e}", flush=True)
        link = f"{config.ARTIGOS_URL}/primeiro-acesso"
    msg = (auth_web.wa_msg_senha(link, primeiro=True)
           + "\n\nA partir do próximo dia útil você começa a receber os resumos por aqui.")
    try:
        enviar_fn(whatsapp, msg)
    except Exception as e:
        print(f"[webhook] boas-vindas WhatsApp falhou: {e}", flush=True)
    if email:
        try:
            import email_send
            email_send.enviar(email, f"Crie sua senha de acesso — {config.PRODUTO}",
                              auth_web.email_html_senha(nome, link, True))
        except Exception as e:
            print(f"[webhook] boas-vindas e-mail falhou: {e}", flush=True)


def _alertar_admin(pid, sid, motivo):
    """Avisa o Dr. Diego quando um pagamento não pôde ser ativado — sem isso, seria
    dinheiro que entra e some sem ninguém perceber."""
    try:
        import deliver
        deliver.enviar_admin(f"⚠️ Pagamento no Asaas precisa de atenção: {motivo}. "
                             f"Pagamento {pid or '—'} · assinatura {sid or '—'}. Confira em Assinantes.")
    except Exception as e:
        print(f"[webhook] alerta admin falhou: {e}", flush=True)


def _executar(event, pay, pid, enviar_fn):
    """Aplica a ação do evento. Pode levantar exceção — o chamador (`processar`)
    desfaz a idempotência e alerta o admin nesse caso, p/ o Asaas re-tentar."""
    import phone
    sid = pay.get("subscription")
    sub = subscribers.por_subscription(sid)
    acao = decidir(event, sub is not None)

    if acao == "ATIVAR":
        # Asaas NÃO propaga externalReference do checkout -> montar do CLIENTE do Asaas.
        cust, sub_obj = {}, {}
        if config.ASAAS_API_KEY:
            import asaas
            try:
                cust = asaas.obter_cliente(pay.get("customer")) or {}
            except Exception as e:
                print(f"[webhook] obter_cliente falhou: {e}", flush=True)
            if sid:
                try:
                    sub_obj = asaas.obter_assinatura(sid) or {}
                except Exception as e:
                    print(f"[webhook] obter_assinatura falhou: {e}", flush=True)
        pending = db.obter_pending(pay.get("externalReference"))
        whatsapp = phone.normalizar(cust.get("mobilePhone") or cust.get("phone")
                                    or (pending or {}).get("whatsapp") or "")
        if not whatsapp:
            print("[webhook] ATIVAR sem whatsapp — pulei", flush=True)
            _alertar_admin(pid, sid, "pagamento confirmado mas SEM WhatsApp p/ ativar — ative manualmente")
            return (200, "sem-whatsapp")
        plano = (config.plano_por_cycle(sub_obj.get("cycle"))
                 or config.plano_por_base(pay.get("value"))
                 or (config.plano_por_slug((pending or {}).get("plano", "")) if pending else None) or {})
        prox = _proximo_venc(plano.get("cycle", "MONTHLY"), pay.get("dueDate"))
        nome = cust.get("name") or (pending or {}).get("nome", "")
        email = cust.get("email") or (pending or {}).get("email", "")
        subscribers.criar_de_pagamento(
            {"nome": nome, "whatsapp": whatsapp, "email": email, "plano": plano.get("slug", "")},
            {"customer": pay.get("customer"), "subscription": sid, "payment": pid, "proximo_vencimento": prox})
        _boas_vindas(whatsapp, nome, email, enviar_fn)
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


def processar(body, token_header, enviar_fn=None):
    """Retorna (status_code, msg). Idempotente. token_header valida a origem.
    A ativação roda protegida: se falhar no meio, DESFAZ a marca de idempotência e
    devolve 500 pro Asaas re-tentar (senão o cliente pagaria e nunca seria liberado)."""
    event = (body or {}).get("event")
    pay = (body or {}).get("payment") or {}
    pid = pay.get("id") or ""
    token_ok = bool(config.ASAAS_WEBHOOK_TOKEN) and hmac.compare_digest(
        str(token_header or ""), str(config.ASAAS_WEBHOOK_TOKEN))
    print(f"[webhook] event={event} pay={pid} sub={pay.get('subscription')} token_ok={token_ok}", flush=True)
    if not token_ok:
        return (401, "unauthorized")
    if enviar_fn is None:
        import deliver
        enviar_fn = deliver.enviar_texto

    if not db.registrar_webhook(pid, event):
        return (200, "duplicado")
    try:
        return _executar(event, pay, pid, enviar_fn)
    except Exception as e:
        print(f"[webhook] ERRO ao processar {event}/{pid}: {e}", flush=True)
        try:
            db.remover_webhook(pid, event)      # desfaz idempotência -> Asaas re-tenta o evento
        except Exception as e2:
            print(f"[webhook] remover_webhook falhou: {e2}", flush=True)
        _alertar_admin(pid, pay.get("subscription"), f"falha ao processar o pagamento ({e})")
        return (500, "erro-processando")
