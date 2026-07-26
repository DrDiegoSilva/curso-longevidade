"""Régua de renovação: quem avisar, quando, e com qual automação.

As funções deste bloco são puras (sem rede, sem banco) — o disparador que usa o banco e manda
mensagem fica no fim do arquivo, no mesmo formato do billing_notices.py.

Público da régua: plano ANUAL, sem assinatura recorrente no Asaas e que não cancelou.
Cartão à vista e mensal criam `subscription` no Asaas e renovam sozinhos; Pix (DETACHED) e
cartão parcelado não criam — é a ausência desse id que identifica quem precisa agir.
"""
from datetime import datetime


def offset_vencimento(vencimento, hoje):
    """`hoje - vencimento` em dias. Faltando 7 dias => -7; no dia => 0; vencido há 15 => +15.

    Mesma convenção do campo `dias` da automação, então o casamento é igualdade direta.
    Devolve None quando a data é ausente ou malformada: sem data confiável o assinante fica
    fora da régua, em vez de receber um aviso com prazo errado.
    """
    if not vencimento:
        return None
    try:
        d = datetime.fromisoformat(str(vencimento)).date()
    except (TypeError, ValueError):
        return None
    return (hoje - d).days


def na_regua(sub, plano):
    """True se este assinante deve receber a régua."""
    if not sub:
        return False                       # sub ausente ou vazio
    if (plano or {}).get("cycle") != "YEARLY":
        return False
    if (sub or {}).get("asaas_subscription_id"):
        return False                      # renova sozinho no cartão
    if (sub or {}).get("cancelado_em"):
        return False                      # já pediu para sair
    return True


def automacoes_do_dia(automacoes, offset):
    """Automações ativas cujo `dias` bate exatamente com o offset de hoje.

    Coage `dias` e `ativo` a valores numéricos: dados vindos do banco ou tela
    podem ser strings (ex.: `"0"`, `"-7"`), e em Python `"0"` é truthy enquanto
    `0` é falsy. Sem coerção, uma automação desativada (`ativo=0`) gravada como
    `ativo="0"` voltaria a disparar em produção.
    """
    if offset is None:
        return []
    return [a for a in (automacoes or [])
            if int(a.get("ativo") or 0) and int(a.get("dias") or 0) == offset]


# ── Disparador (usa banco e rede) — mesmo formato do billing_notices.py ──
def _texto(template, sub, vencimento, link):
    """Substitui os marcadores. Data em pt-BR — ninguém lê ISO num WhatsApp."""
    import site_web
    return (template or "").replace("{nome}", (sub.get("nome") or "").split(" ")[0]) \
                           .replace("{ate}", site_web._data_br(vencimento) or "") \
                           .replace("{link}", link)


def disparar(hoje=None, enviar_wa=None, enviar_email=None):
    """Percorre os assinantes da régua e manda as automações que casam com hoje.

    Cada envio é isolado: falha em um assinante não interrompe os demais e NÃO grava o ledger,
    para que a próxima execução do mesmo dia tente de novo. Passado o dia, o disparo é perdido
    de propósito — "vence em 7 dias" chegando no dia 3 confunde mais do que ajuda.

    Devolve quantas mensagens saíram.
    """
    from datetime import date as _date
    import config, db, subscribers
    hoje = hoje or _date.today()
    if enviar_wa is None:
        import deliver
        enviar_wa = deliver.enviar_texto
    if enviar_email is None:
        import email_send
        enviar_email = lambda dest, assunto, corpo: email_send.enviar(dest, assunto, corpo)

    automacoes = db.listar_automacoes(so_ativas=True)
    enviadas = 0
    for sub in subscribers.listar():
        plano = config.plano_por_slug(sub.get("plano", "")) or {}
        if not na_regua(sub, plano):
            continue
        venc = sub.get("proximo_vencimento")
        off = offset_vencimento(venc, hoje)
        for a in automacoes_do_dia(automacoes, off):
            # São dois fluxos diferentes: RENOVAÇÃO (dias <= 0) é quem ainda tem acesso
            # e paga antes de vencer — usa /renovar, que exige sessão, e funciona porque
            # quem tem acesso consegue logar. RECONTRATAÇÃO (dias > 0) é quem já perdeu
            # o acesso — /renovar bloquearia esse assinante, então usa /assinar, que é
            # público (e o webhook reconhece o CPF e reativa com o bônus de resgate).
            rota = "renovar" if int(a.get("dias") or 0) <= 0 else "assinar"
            link = f"{config.ARTIGOS_URL}/{rota}"

            # Determina o destinatário conforme o canal ANTES de marcar o ledger.
            # Se não há destinatário, não marca e não envia — registra um log.
            destinatario = None
            if a.get("canal") == "email":
                destinatario = sub.get("email")
                if not destinatario:
                    print(f"[regua] pulando assinante {sub.get('id')} automação {a.get('id')}: "
                          f"sem email cadastrado", flush=True)
                    continue
            else:  # WhatsApp ou outro canal padrão
                destinatario = sub.get("whatsapp")
                if not destinatario:
                    print(f"[regua] pulando assinante {sub.get('id')} automação {a.get('id')}: "
                          f"sem WhatsApp cadastrado", flush=True)
                    continue

            # Agora que sabemos ter destinatário, marca o ledger.
            if not db.registrar_aviso(sub["id"], a["id"], venc):
                continue                      # já saiu neste ciclo
            try:
                msg = _texto(a.get("texto"), sub, venc, link)
                if a.get("canal") == "email":
                    enviar_email(destinatario, "Sua assinatura — Atualização Científica", msg)
                else:
                    enviar_wa(destinatario, msg)
                enviadas += 1
            except Exception as e:
                print(f"[regua] envio falhou p/ {sub.get('id')} ({a.get('id')}): {e}", flush=True)
                try:
                    db.remover_aviso(sub["id"], a["id"], venc)   # destrava a retentativa de hoje
                except Exception as e2:
                    print(f"[regua] remover_aviso falhou: {e2}", flush=True)
    return enviadas
