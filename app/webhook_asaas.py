"""Webhook do Asaas: valida token, idempotência e aplica a ação no assinante.
`decidir` é puro/testável; `processar` orquestra (db + subscribers + WhatsApp).
"""
import hmac
from datetime import datetime, timedelta, date
import config
import db
import subscribers
import refunds

CARENCIA_DIAS = 3
# Fonte única do mapa de ciclos E da regra do bônus de resgate — ambos vêm do
# renovacao.py, que é a ÚNICA implementação dessa regra (Task 8: antes havia uma
# segunda cópia, inline aqui, de "está no futuro?" + _proximo_venc, divergente da
# de renovacao.novo_vencimento — foi removida).
from renovacao import CICLO_DIAS as _CICLO_DIAS, novo_vencimento


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


def _confirmar_renovacao(sub, vencimento, automatica=True):
    """Confirma a renovação. Canal por tipo (decisão do Diego 2026-07-25):
    - automática (cartão recorrente, ramo RENOVAR): e-mail, que serve de comprovante
      de cobrança — o assinante não fez nada, só foi cobrado de novo;
    - manual (recontratação/recompra: o assinante foi lá e pagou de novo): WhatsApp,
      canal onde ele já está e já consome o produto.
    Um único texto (mensagens.email_renovacao) serve pros dois canais — pro assinante
    os casos são só "paguei e meu acesso segue valendo"; pro WhatsApp o HTML vira texto
    plano via site_web._sem_html (WhatsApp não renderiza tags). Nunca pode derrubar a
    ativação/renovação: por isso o try/except cobre TUDO que pode levantar aqui dentro
    (imports, montagem de link/ate e o envio em si) — ACHADO 3 (revisão): antes, os
    imports e link/ate ficavam fora do try, e uma falha ali subiria até `_executar`,
    que desfaz a marca de idempotência e devolve 500 pro Asaas (que re-tenta o evento
    com o status do assinante já gravado)."""
    try:
        import mensagens, site_web
        link = f"{config.ARTIGOS_URL}/minha"
        ate = site_web._data_br(vencimento) or ""
        if automatica:
            if not sub.get("email"):
                return
            import email_send
            assunto, html = mensagens.email_renovacao(sub.get("nome", ""), ate, link)
            email_send.enviar(sub["email"], assunto, html)
        else:
            import deliver
            _, corpo = mensagens.email_renovacao(sub.get("nome", ""), ate, link)
            deliver.enviar_texto(sub.get("whatsapp"), site_web._sem_html(corpo))
    except Exception as e:
        print(f"[webhook] confirmação de renovação falhou: {e}", flush=True)


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
    import mensagens
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
        # IMPORTANT 2 (correção 1): sem ASAAS_API_KEY (ou se a consulta ao Asaas falhar),
        # `cust` fica vazio -> cpfCnpj vazio -> o pending nunca era achado por CPF, mesmo
        # existindo. Mesmo atalho usado logo abaixo pro WhatsApp: Pix avulso manda
        # `cpfCnpj` DIRETO no pagamento, sem precisar da API — tenta esse como fallback.
        pending = (db.obter_pending(pay.get("externalReference"))
                   or db.obter_pending_por_cpf(cust.get("cpfCnpj") or pay.get("cpfCnpj")))
        # Sem ASAAS_API_KEY (ou se a consulta ao Asaas falhar), `cust` fica vazio e uma
        # recompra/recontratação de quem JÁ é assinante ficaria bloqueada aqui por "falta"
        # de WhatsApp — mesmo já tendo o telefone dele gravado. Acha o assinante pelo CPF
        # do próprio pagamento (Pix avulso manda `cpfCnpj` nele, sem precisar da API) e usa
        # o WhatsApp já em arquivo como último fallback.
        _existente_por_cpf = subscribers.por_cpf(cust.get("cpfCnpj") or pay.get("cpfCnpj") or "")
        whatsapp = phone.normalizar(cust.get("mobilePhone") or cust.get("phone")
                                    or (pending or {}).get("whatsapp")
                                    or (_existente_por_cpf or {}).get("whatsapp") or "")
        if not whatsapp:
            print("[webhook] ATIVAR sem whatsapp — pulei", flush=True)
            _alertar_admin(pid, sid, "pagamento confirmado mas SEM WhatsApp p/ ativar — ative manualmente")
            return (200, "sem-whatsapp")
        # Guarda contra duplicata: no Asaas, cartão À VISTA cria assinatura recorrente
        # (subscription preenchido), mas cartão PARCELADO não — cada parcela confirmada
        # chega com "subscription" vazio, então por_subscription nunca acha o assinante
        # e cai neste ramo ATIVAR de novo. Sem checar se o CPF/WhatsApp já é assinante,
        # o anual em 12x criaria até 12 registros duplicados (boas-vindas, e-mail de
        # "nova venda" e comissão de afiliado repetidos a cada parcela confirmada).
        # Calculado ANTES do plano (abaixo) de propósito: o IMPORTANT 2 (correção 2)
        # precisa saber se já existe assinante pra preferir o plano DELE em vez de
        # adivinhar pelo valor pago.
        # `pay["cpfCnpj"]` entra aqui pelo mesmo motivo do `_existente_por_cpf` acima: sem
        # ASAAS_API_KEY o `cust` vem vazio, e o CPF do próprio pagamento é o que sobra.
        cpf_cliente = cust.get("cpfCnpj") or pay.get("cpfCnpj") or (pending or {}).get("cpf") or ""
        existente = subscribers.por_cpf(cpf_cliente) or subscribers.por_whatsapp(whatsapp)
        novo_assinante = existente is None

        if existente:
            # Duas guardas ANTES de calcular qualquer período (revisão final #2). Ficam aqui,
            # e não dentro dos ramos, porque o ATIVAR é reentrante por dois caminhos distintos
            # e os dois desembocavam em "conceder um ciclo novo".
            tipo_pagamento, _ = refunds.alvo_estorno(pay)
            if pid and existente.get("asaas_payment_id") == pid:
                # B5: o Asaas manda PAYMENT_CONFIRMED e PAYMENT_RECEIVED para o MESMO
                # pagamento, e a idempotência é por (payment_id, event) — os dois passam.
                # No Pix (sem `subscription`) o 2º achava o assinante com acesso vigente e
                # caía na RECOMPRA, estendendo um ciclo inteiro: um ano pago virava dois.
                # A guarda é por identidade do pagamento, então a recompra legítima (outro
                # pagamento, antes de vencer) continua passando.
                return (200, "replay")
            if tipo_pagamento == "installment":
                # B6/B7: parcela de cartão parcelado. Só atualiza a referência do pagamento
                # mais recente (é nela que o estorno se baseia). NUNCA concede período novo,
                # NUNCA reativa e NUNCA limpa o cancelamento: antes, a parcela que chegasse
                # depois do acesso vencer caía na recontratação e comprava um ciclo anual
                # inteiro + bônus de resgate por R$ 91,58, ressuscitando quem tinha cancelado
                # a renovação e apagando o `cancelado_em`.
                subscribers.marcar_status(existente["id"], existente["status"], asaas_payment_id=pid)
                return (200, "parcela-registrada")

        # Cascata do plano: 1) ciclo da assinatura recorrente REAL no Asaas (a fonte mais
        # confiável, quando disponível); 2) se já é assinante conhecido (recompra ou
        # recontratação), o plano JÁ está no cadastro dele — usa esse, não adivinha; 3)
        # adivinhar pelo valor pago (preço de tabela) só faz sentido pra CLIENTE NOVO,
        # sem cadastro prévio; 4) plano do pending, último recurso.
        # IMPORTANT 2 (correção 2): antes, um assinante existente que pagou com desconto
        # (Pix, founder) tinha o valor comparado contra o preço de TABELA em
        # plano_por_base — não casava com nada, e a cascata caía no default MONTHLY (30
        # dias de acesso pra quem, por exemplo, pagou um ano).
        plano = (config.plano_por_cycle(sub_obj.get("cycle"))
                 or (config.plano_por_slug(existente.get("plano", "")) if existente else None)
                 or config.plano_por_base(pay.get("value"))
                 or (config.plano_por_slug((pending or {}).get("plano", "")) if pending else None) or {})
        if not plano:
            # IMPORTANT 2 (correção 3): a cascata inteira falhou (cliente novo, sem
            # pending, valor que não bate com nenhum preço de tabela) — dinheiro entrou
            # e o sistema não sabe o que foi vendido. Segue com o default MONTHLY (linha
            # abaixo, pra não travar a ativação), mas avisa o Diego em vez de ficar calado.
            _alertar_admin(pid, sid, "pagamento confirmado mas não consegui identificar o "
                                     f"plano contratado (valor pago R$ {pay.get('value')}) — "
                                     "confira e ajuste o acesso manualmente")
        prox = _proximo_venc(plano.get("cycle", "MONTHLY"), pay.get("dueDate"))
        nome = cust.get("name") or (pending or {}).get("nome", "")
        email = cust.get("email") or (pending or {}).get("email", "")
        # B1/B2 da revisão final #2: a base contratada vem do PENDING, nunca de
        # `pay["value"]`. No cartão parcelado `value` é UMA parcela (o anual em 12x
        # renovaria por R$ 91,58 em vez de R$ 1.099) e no Pix já vem com os 5% de desconto,
        # que a renovação reaplica (o preço derretia 5% por ciclo). Quando a base é
        # desconhecida (pending antigo, ou pending não encontrado), NÃO grava nada: a
        # renovação cai no preço de tabela, que é o certo, em vez de um valor inventado.
        base_contratada = (pending or {}).get("valor_base")
        extra_valor = {"valor_contratado": base_contratada} if base_contratada else {}

        if existente and subscribers.tem_acesso(existente):
            # Parcela e reentrega do mesmo pagamento já saíram nas guardas acima — o que
            # chega aqui é necessariamente um pagamento NOVO e avulso.
            # Pix não tem parcelamento — se chegou aqui (CPF/WhatsApp já é assinante com
            # acesso vigente) é porque ele comprou OUTRO período antes do atual vencer
            # (Pix sem `subscription`, OU cartão à vista com uma assinatura recorrente
            # NOVA, distinta da que ele já tinha — por isso caiu em ATIVAR e não em
            # RENOVAR). Sem tratar isso à parte, o pagamento seria engolido em silêncio:
            # não estenderia o acesso e o dinheiro simplesmente sumiria. `novo_vencimento`
            # decide sozinho a regra (Task 8): acesso ainda vigente -> estende a partir do
            # FIM ATUAL, SEM bônus (renovar em dia não ganha o resgate — só quem já perdeu
            # o acesso). Passa sempre o valor configurado (editável em /admin/mensagens,
            # default 30) — é a função quem decide se aplica, não o chamador.
            dias_ciclo = _CICLO_DIAS.get(plano.get("cycle", "MONTHLY"), 30)
            novo_fim = novo_vencimento(existente.get("acesso_ate"), date.today(),
                                       dias_ciclo, bonus_dias=mensagens.bonus_resgate_dias()).isoformat()
            # valor_contratado atualizado pro valor deste pagamento: renovacao.preco_renovacao
            # usa esse campo pra cobrar o preço que o assinante de fato contratou (ex.:
            # founder) em vez do preço de tabela — sem regravar aqui, uma recompra em outro
            # valor deixaria o campo desatualizado e a renovação seguinte cobraria errado.
            # ACHADO CRÍTICO 2 (correção): quando o pagamento traz `subscription` (cartão à
            # vista recorrente), grava o asaas_subscription_id no assinante — sem isso,
            # dois estragos: (1) regua.na_regua só exclui quem tem esse campo preenchido;
            # vazio, o assinante recorrente continuava na régua, recebia os avisos de
            # renovar e era cobrado de novo pela régua ENQUANTO o cartão cobrava sozinho
            # (cobrança em dobro); (2) eventos futuros dessa assinatura (PAYMENT_OVERDUE,
            # cancelamento, estorno) são casados por subscribers.por_subscription — sem o
            # id gravado, nunca achavam ninguém e o acesso nunca era cortado. Pix não traz
            # `subscription` -> não passa o campo (fica como já estava gravado).
            # acesso_ate segue a mesma regra do resto do arquivo: com assinatura recorrente
            # gravada, None é o certo (o cartão renova e empurra sozinho, é o RENOVAR mais
            # abaixo quem confirma o próximo ciclo); só sem assinatura (Pix) a data de fim
            # é obrigatória, senão ATIVO sem acesso_ate vira acesso pra sempre.
            # B9: recompra é um contrato à distância NOVO -> nova janela de arrependimento.
            # `criado_em` é o marco do art. 49 (é o que refunds.dentro_arrependimento lê, e
            # seu único leitor); sem regravar, quem voltava e cancelava no 3º dia não
            # recebia estorno nenhum e ninguém era avisado.
            extra_sub = {"asaas_subscription_id": sid} if sid else {}
            subscribers.marcar_status(existente["id"], existente["status"], asaas_payment_id=pid,
                                      acesso_ate=(None if sid else novo_fim), proximo_vencimento=novo_fim,
                                      criado_em=datetime.now().isoformat(),
                                      **extra_valor, **extra_sub)
            # Recompra é manual (o assinante voltou e pagou de novo) -> WhatsApp.
            _confirmar_renovacao({"email": existente.get("email") or email,
                                  "nome": existente.get("nome") or nome,
                                  "whatsapp": existente.get("whatsapp") or whatsapp},
                                 novo_fim, automatica=False)
            return (200, "pix-recomprado-estendido")

        if existente:
            # Acesso já tinha acabado (ex.: Pix anual vencido) e o cliente comprou de
            # novo -> recontratação legítima. Reativa o registro existente em vez de
            # criar outro (mantém o histórico do assinante num id só). `novo_vencimento`
            # conta de HOJE (o acesso não está mais vigente) e aplica o bônus de resgate
            # (Task 8) — é exatamente o caso que ele existe pra cobrir. O número de dias
            # é o configurado em /admin/mensagens (default 30 quando ausente/inválido).
            # acesso_ate segue a mesma regra de sempre: só grava quando NÃO há
            # subscription (Pix avulso); no cartão o próprio ciclo recorrente controla
            # o acesso.
            dias_ciclo = _CICLO_DIAS.get(plano.get("cycle", "MONTHLY"), 30)
            prox = novo_vencimento(existente.get("acesso_ate"), date.today(),
                                  dias_ciclo, bonus_dias=mensagens.bonus_resgate_dias()).isoformat()
            # valor_contratado atualizado pro valor deste pagamento — mesma razão do
            # ramo de recompra acima: sem isso a recontratação meses depois, a um preço
            # diferente, deixaria o campo com o valor antigo (ou nulo) e a renovação
            # seguinte cobraria errado.
            # ACHADO CRÍTICO 2 (correção): mesmo bug do ramo de recompra acima, aqui do
            # lado de quem tinha PERDIDO o acesso — recontratação no cartão à vista
            # também precisa gravar o asaas_subscription_id (régua + eventos futuros da
            # assinatura, ver comentário detalhado no ramo de recompra). A regra do
            # acesso_ate já estava certa aqui (prox só quando NÃO há sid) — mantida.
            # IMPORTANT 1 (correção): quem estava CANCELADO (cancelado_em preenchido) e
            # volta a pagar depois de perder o acesso é reativado aqui — precisa limpar
            # as marcas do cancelamento anterior, mesmo critério já usado no ramo RENOVAR
            # mais abaixo (`cancelado_em=None, cancel_motivo=None`). Sem isso, dois
            # estragos silenciosos: (1) regua.na_regua exclui quem tem cancelado_em
            # preenchido — o assinante que recontratou nunca mais recebe aviso de
            # vencimento, e some da régua pra sempre; (2) db.claim_cancelamento só
            # cancela quem tem cancelado_em VAZIO — com a marca antiga, ele fica
            # PERMANENTEMENTE impedido de cancelar de novo.
            extra_sub = {"asaas_subscription_id": sid} if sid else {}
            # B9: recontratação também é contrato novo -> nova janela de arrependimento, e o
            # `asaas_payment_id` PRECISA apontar pro pagamento desta compra: sem isso o
            # estorno automático miraria a cobrança da compra anterior (a que já foi paga e
            # consumida), devolvendo o dinheiro errado ou falhando.
            subscribers.marcar_status(existente["id"], "ATIVO", proximo_vencimento=prox,
                                      acesso_ate=(prox if not sid else None),
                                      cancelado_em=None, cancel_motivo=None,
                                      asaas_payment_id=pid,
                                      criado_em=datetime.now().isoformat(),
                                      **extra_valor, **extra_sub)
            reg = existente
        else:
            reg = subscribers.criar_de_pagamento(
                {"nome": nome, "whatsapp": whatsapp, "email": email, "plano": plano.get("slug", ""),
                 "cpf": cpf_cliente,
                 "termos_versao": (pending or {}).get("termos_versao", ""),
                 "termos_ip": (pending or {}).get("termos_ip", ""),
                 "valor_contratado": base_contratada},
                {"customer": pay.get("customer"), "subscription": sid, "payment": pid,
                 "proximo_vencimento": prox})
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

        if novo_assinante:
            _boas_vindas(whatsapp, nome, email, enviar_fn)
        else:
            # Recontratação (caso 3 da guarda: acesso já tinha expirado e ele comprou de
            # novo): a conta já existe e já tem senha — mandar as boas-vindas de novo
            # (com o link de CRIAR senha) seria confuso. Confirmação de renovação em vez
            # disso — recontratação é manual (o assinante voltou e pagou de novo) -> WhatsApp.
            _confirmar_renovacao({"email": email, "nome": nome, "whatsapp": whatsapp}, prox, automatica=False)
        # Afiliado (D3): comissão sobre o valor pago (só na 1ª venda). No cartão o desconto
        # é RECORRENTE (o Asaas não deixa alterar o `value` da assinatura por API) — decisão do
        # Diego: renovação com desconto "da nada". A busca do afiliado é protegida: uma falha
        # transitória aqui NÃO pode derrubar a ativação (senão o Asaas re-tenta e duplica o assinante).
        # Recontratação (existente reativado acima) NÃO gera comissão nova — mesma regra "só na 1ª venda".
        af = None
        if novo_assinante:
            try:
                af = db.afiliado_por_codigo((pending or {}).get("afiliado_codigo") or "")
            except Exception as e:
                print(f"[webhook] afiliado_por_codigo falhou: {e}", flush=True)
                af = None
        valor_comissao = None
        # Valor da VENDA (total pago pelo cliente), não do evento: no cartão parcelado o Asaas
        # confirma parcela por parcela, e `pay["value"]` é 1/12. Como a comissão sai só na 1ª
        # venda, o erro nunca se corrigia depois — o afiliado recebia 3% de uma parcela.
        # `pending["valor"]` é o total já com cupom/desconto de método aplicado, que é
        # exatamente a base da comissão. Sem pending, resta o valor do evento.
        valor_venda_total = float((pending or {}).get("valor") or pay.get("value") or 0)
        if af:
            import pricing
            valor_venda = valor_venda_total
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
                          valor_venda_total, email or whatsapp, len(subscribers.ativos()),
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
        # Renovação automática (cartão à vista cobrando de novo sozinho): sem isso o
        # cliente é cobrado e não recebe nada — é exatamente o tipo de cobrança muda
        # que gera "não reconheço essa cobrança" e chargeback. automatica=True -> e-mail.
        _confirmar_renovacao(sub, prox, automatica=True)
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
