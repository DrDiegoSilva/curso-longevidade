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
    if (plano or {}).get("cycle") != "YEARLY":
        return False
    if (sub or {}).get("asaas_subscription_id"):
        return False                      # renova sozinho no cartão
    if (sub or {}).get("cancelado_em"):
        return False                      # já pediu para sair
    return True


def automacoes_do_dia(automacoes, offset):
    """Automações ativas cujo `dias` bate exatamente com o offset de hoje."""
    if offset is None:
        return []
    return [a for a in (automacoes or [])
            if a.get("ativo") and int(a.get("dias")) == offset]
