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
    import auth_web, mensagens
    try:
        link = auth_web.preparar_primeiro_acesso(whatsapp)
    except Exception as e:
        print(f"[webhook] preparar 1º acesso falhou: {e}", flush=True)
        link = f"{config.ARTIGOS_URL}/primeiro-acesso"
    try:
        enviar_fn(whatsapp, mensagens.wa_boas_vindas(link, nome))   # texto editável no admin
    except Exception as e:
        print(f"[webhook] boas-vindas WhatsApp falhou: {e}", flush=True)
    if email:
        try:
            import email_send
            assunto, html = mensagens.email_boas_vindas(nome, link)   # editável no admin
            email_send.enviar(email, assunto, html)
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


def _avisar_venda(nome, plano, valor, contato, ativos, afiliado=None, comissao=None):
    """E-mail instantâneo ao admin quando uma venda ativa. Nunca pode quebrar a ativação."""
    try:
        import email_send
        esc = __import__("html").escape
        assunto = f"🎉 Nova venda — {plano} · R$ {valor}"
        val_com = (f' · comissão <b style="color:#e8efe9">R$ {esc(str(comissao))}</b>'
                   if comissao is not None else '')   # só mostra o valor se a comissão foi registrada
        linha_af = (f'<p style="margin:6px 0;color:#a9bcb2">Afiliado: '
                    f'<b style="color:#e8efe9">{esc(afiliado)}</b>{val_com}</p>') if afiliado else ""
        corpo = (
            f'<div style="font-family:Georgia,serif;background:#0e211a;color:#e8efe9;'
            f'padding:28px;border-radius:14px;max-width:520px;margin:0 auto">'
            f'<h1 style="color:#e7c766;font-size:23px;margin:0 0 14px">🎉 Nova venda</h1>'
            f'<p style="margin:6px 0"><b>{esc(nome or "—")}</b></p>'
            f'<p style="margin:6px 0;color:#a9bcb2">Plano: <b style="color:#e8efe9">{esc(plano or "—")}</b> · '
            f'Valor: <b style="color:#e8efe9">R$ {esc(str(valor))}</b></p>'
            f'<p style="margin:6px 0;color:#a9bcb2">Contato: {esc(contato or "—")}</p>'
            f'{linha_af}'
            f'<p style="margin:16px 0 0;color:#e7c766">Agora você tem <b>{ativos}</b> assinantes ativos.</p>'
            f'</div>')
        email_send.enviar(config.ADMIN_EMAIL, assunto, corpo)
    except Exception as e:
        print(f"[webhook] aviso de venda falhou: {e}", flush=True)


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
        # O Asaas não propaga o externalReference do checkout p/ o pagamento -> além de
        # buscar pelo token, casa o pending pelo CPF do cliente Asaas (recupera o afiliado).
        pending = (db.obter_pending(pay.get("externalReference"))
                   or db.obter_pending_por_cpf(cust.get("cpfCnpj")))
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
        reg = subscribers.criar_de_pagamento(
            {"nome": nome, "whatsapp": whatsapp, "email": email, "plano": plano.get("slug", ""),
             "termos_versao": (pending or {}).get("termos_versao", ""),
             "termos_ip": (pending or {}).get("termos_ip", "")},
            {"customer": pay.get("customer"), "subscription": sid, "payment": pid, "proximo_vencimento": prox})
        if not sid:
            # Pix é pagamento DETACHED (avulso), sem assinatura recorrente por trás — não
            # existe cobrança futura agendada, logo nunca chega um PAYMENT_OVERDUE pra
            # expirar ninguém. Sem acesso_ate, ATIVO sem acesso_ate = acesso PRA SEMPRE
            # (subscribers.tem_acesso), então quem pagou uma vez ficaria recebendo os
            # estudos indefinidamente. Grava o mesmo vencimento já calculado (prox) —
            # decisão do Diego. No cartão (com subscription/sid) NÃO gravamos: o cartão
            # renova sozinho e uma data de fim cortaria o acesso na virada do ciclo,
            # antes da próxima cobrança confirmar.
            subscribers.marcar_status(reg["id"], "ATIVO", acesso_ate=prox)
        _boas_vindas(whatsapp, nome, email, enviar_fn)
        # Afiliado (D3): comissão sobre o valor pago (só na 1ª venda). No cartão o desconto
        # é RECORRENTE (o Asaas não deixa alterar o `value` da assinatura por API) — decisão do
        # Diego: renovação com desconto "da nada". A busca do afiliado é protegida: uma falha
        # transitória aqui NÃO pode derrubar a ativação (senão o Asaas re-tenta e duplica o assinante).
        try:
            af = db.afiliado_por_codigo((pending or {}).get("afiliado_codigo") or "")
        except Exception as e:
            print(f"[webhook] afiliado_por_codigo falhou: {e}", flush=True)
            af = None
        valor_comissao = None
        if af:
            import pricing
            valor_venda = float(pay.get("value") or 0)
            try:
                comissao_calc = pricing.comissao(valor_venda, af["pct_comissao"])
                db.registrar_comissao(af["id"], reg["id"], plano.get("slug", ""), valor_venda, comissao_calc)
                valor_comissao = comissao_calc      # só exibe/e-maila a comissão se ela foi de fato registrada
            except Exception as e:
                print(f"[webhook] registrar_comissao falhou: {e}", flush=True)
                _alertar_admin(pid, sid, f"venda de afiliado ({af.get('nome') or af.get('codigo')}) paga "
                                         f"R$ {valor_venda} mas NÃO consegui registrar a comissão — registre manualmente")
        try:
            _avisar_venda(nome, (plano.get("nome") or plano.get("slug") or "—"),
                          pay.get("value"), email or whatsapp, len(subscribers.ativos()),
                          afiliado=(af["nome"] if af else None), comissao=valor_comissao)
        except Exception as e:
            print(f"[webhook] _avisar_venda: {e}", flush=True)
        return (200, "ativado")

    if acao == "RENOVAR" and sub:
        if sub.get("cancelado_em"):
            # Decisão do Diego: cancelar = cancelar a RENOVAÇÃO, não o período já
            # contratado. No anual em 12x as parcelas restantes continuam sendo
            # cobradas normalmente depois do cancelamento — é o cliente quitando os 12
            # meses que ele contratou, não uma nova assinatura. Esta parcela, portanto,
            # NÃO reativa: não mexe em status/cancelado_em/cancel_motivo nem empurra
            # proximo_vencimento/acesso_ate — o cancelamento (db.claim_cancelamento) já
            # gravou tudo isso de forma completa e é essa gravação que continua valendo.
            # (Se em vez disso checássemos status=="CANCELADO", um assinante suspenso
            # por SUSPENDER — estorno/chargeback, que NÃO grava cancelado_em — deixaria
            # de poder ser reativado por um pagamento seguinte; checar cancelado_em
            # preserva esse caso, tratado mais abaixo.)
            _alertar_admin(pid, sid, f"assinante {sub.get('nome') or sub.get('id')} já tinha "
                           f"cancelado a renovação em {sub.get('cancelado_em')} (motivo: "
                           f"{sub.get('cancel_motivo') or '—'}) e o Asaas confirmou mais um "
                           f"pagamento — pode ser parcela legítima do anual em 12x, ou o "
                           f"cancelamento da assinatura pode ter falhado no Asaas e ele está "
                           f"sendo cobrado indevidamente. Confira qual dos dois é")
            return (200, "parcela-pos-cancelamento")
        plano = config.plano_por_slug(sub.get("plano", "")) or {}
        prox = _proximo_venc(plano.get("cycle", "MONTHLY"), pay.get("dueDate"))
        # Reativação normal (sem cancelado_em) — ex.: estorno/chargeback que reverteu
        # (SUSPENDER marca CANCELADO sem gravar cancelado_em) e um novo pagamento
        # confirma. Limpar as marcas de cancelamento faz parte dela:
        # - cancelado_em: db.claim_cancelamento só grava quando ele está vazio. Um
        #   assinante reativado com a marca antiga ficaria PERMANENTEMENTE impedido de
        #   cancelar — todo claim perderia e a página diria "já cancelado".
        # - acesso_ate: em ATIVO, uma data no passado zera o acesso (subscribers.tem_acesso);
        #   a data herdada do cancelamento anterior deixaria o assinante pagando sem receber.
        subscribers.marcar_status(sub["id"], "ATIVO", carencia_ate=None,
                                  proximo_vencimento=prox, aviso_renov_em=None,
                                  cancelado_em=None, cancel_motivo=None, acesso_ate=None)
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
