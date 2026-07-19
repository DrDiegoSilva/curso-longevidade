"""Aviso discreto por e-mail ~3 dias antes de renovar/vencer (reduz surpresa/chargeback).
`assinantes_a_avisar` é puro/testável; `avisar_pre_renovacao` roda no agendador (08h).
"""
from datetime import date, timedelta


def assinantes_a_avisar(subs, dias, hoje):
    """ATIVOs com vencimento em [hoje, hoje+dias] ainda não avisados NESTE ciclo."""
    limite = hoje + timedelta(days=dias)
    out = []
    for s in subs:
        if s.get("status") != "ATIVO":
            continue
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


def avisar_pre_renovacao(dias=3):
    import subscribers
    import email_send
    hoje = date.today()
    alvo = assinantes_a_avisar(subscribers.listar(), dias, hoje)
    for s in alvo:
        pv = s.get("proximo_vencimento")
        if s.get("email"):
            html = (f"<p>Olá {s.get('nome') or ''},</p>"
                    f"<p>Sua assinatura da <strong>Atualização Científica</strong> vence em {pv}. "
                    f"Se for recorrente (cartão ou Pix Automático), ela renova sozinha — nada a fazer. "
                    f"Se você pagou via Pix à vista, é só renovar para continuar recebendo os estudos.</p>"
                    f"<p>— Dr. Diego Silva · CRM-PR 54310</p>")
            email_send.enviar(s["email"], "Sua assinatura renova em breve", html)
        subscribers.marcar_status(s["id"], s["status"], aviso_renov_em=pv)
    return len(alvo)
