"""Aviso discreto ~3 dias antes de renovar/vencer (reduz surpresa/chargeback).
`assinantes_a_avisar` é puro/testável; `avisar_pre_renovacao` roda no agendador (08h).

Vai por WHATSAPP desde 2026-08-01. Era e-mail, e o canal de e-mail nunca funcionou em
produção — sem `RESEND_API_KEY` o `email_send.enviar` só logava e devolvia `skipped`, e
ninguém olhava o retorno. Ou seja: este aviso nunca chegou a assinante nenhum. A conta do
Resend do Diego só tem `clinicdspro.com.br` verificado, e mandar cobrança da Atualização
Científica de um domínio de outra marca convida o cliente a marcar como spam — justo no
aviso que existe pra EVITAR chargeback. O WhatsApp é onde ele já recebe o produto todo dia.
"""
from datetime import date, timedelta


def assinantes_a_avisar(subs, dias, hoje):
    """ATIVOs com renovação automática (asaas_subscription_id) e vencimento em
    [hoje, hoje+dias] ainda não avisados NESTE ciclo.

    Quem NÃO tem assinatura recorrente (Pix à vista, cartão parcelado) é coberto pela
    régua (regua.py) — sem essa exclusão, esse assinante receberia dois avisos com
    textos diferentes, um deles dizendo "renova sozinha" para quem não renova.
    """
    limite = hoje + timedelta(days=dias)
    out = []
    for s in subs:
        if s.get("status") != "ATIVO":
            continue
        if not s.get("asaas_subscription_id"):
            continue        # sem assinatura recorrente = régua (regua.py), não este aviso
        pv = s.get("proximo_vencimento")
        if not pv:
            continue
        try:
            d = date.fromisoformat(pv)
        except Exception:
            continue
        if hoje <= d <= limite and (s.get("aviso_renov_em") or "") != pv:
            out.append(s)
    return out


def texto_pre_renovacao(nome, pv):
    """Corpo do aviso em TEXTO PURO — o WhatsApp entrega tag de HTML crua na cara do
    assinante. Puro e testável, sem rede."""
    ola = f"Olá {nome}," if nome else "Olá,"
    return (f"{ola}\n\n"
            f"Sua assinatura da *Atualização Científica* vence em {pv}.\n\n"
            f"Se for recorrente (cartão ou Pix Automático), ela renova sozinha — nada a fazer. "
            f"Se você pagou via Pix à vista, é só renovar para continuar recebendo os estudos.\n\n"
            f"— Dr. Diego Silva · CRM-PR 54310")


def avisar_pre_renovacao(dias=3, enviar_fn=None):
    """Retorna quantos foram REALMENTE avisados.

    O agendador (`daily.rotina_08h`) imprime esse número como "N aviso(s) enviado(s)";
    devolver o total de ALVOS, como antes, fazia o log mentir todo dia.
    """
    import subscribers
    import deliver
    enviar = enviar_fn or deliver.enviar_texto
    avisados = 0
    for s in assinantes_a_avisar(subscribers.listar(), dias, date.today()):
        pv = s.get("proximo_vencimento")
        wpp = (s.get("whatsapp") or "").strip()
        if not wpp:
            # NÃO marca `aviso_renov_em`. Era esse o bug: a marcação ficava FORA do `if`
            # do canal, então quem não tinha como ser avisado era gravado como avisado e
            # perdia o aviso daquele ciclo inteiro, calado. Com o e-mail morto isso valia
            # pra 100% da base.
            print(f"[pre-renovacao] assinante {s.get('id')} sem WhatsApp — pulei", flush=True)
            continue
        try:
            enviar(wpp, texto_pre_renovacao(s.get("nome") or "", pv))
        except Exception as e:
            # Falha de um não derruba o lote. E não marca: amanhã tenta de novo.
            print(f"[pre-renovacao] envio p/ {wpp} falhou: {e}", flush=True)
            continue
        subscribers.marcar_status(s["id"], s["status"], aviso_renov_em=pv)
        avisados += 1
    return avisados
