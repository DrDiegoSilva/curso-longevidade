"""Preço e datas da renovação. Puro/testável: sem rede, sem banco.

Duas regras de negócio moram aqui:
- a renovação cobra o valor que o assinante CONTRATOU, não o de tabela (founder renova como
  founder — é o que a cláusula 2 dos termos promete);
- o bônus de resgate só vale para quem JÁ perdeu o acesso; quem renova em dia não ganha.
"""
from datetime import datetime, timedelta

# Ciclo do Asaas -> dias. Fonte única: o webhook_asaas importa daqui.
CICLO_DIAS = {"WEEKLY": 7, "BIWEEKLY": 14, "MONTHLY": 30, "BIMONTHLY": 61,
              "QUARTERLY": 91, "SEMIANNUALLY": 182, "YEARLY": 365}


def preco_renovacao(sub, plano):
    """Valor a cobrar na renovação: o contratado, ou o base do plano quando não houver.

    O fallback existe porque `valor_contratado` só passou a ser gravado agora — os assinantes
    anteriores entraram no preço de lançamento, que é justamente o `base` do plano.
    """
    try:
        v = float((sub or {}).get("valor_contratado") or 0)
    except (TypeError, ValueError):
        v = 0.0
    return v if v > 0 else float(plano["base"])


def novo_vencimento(acesso_ate, hoje, dias_ciclo, bonus_dias=0):
    """Novo fim do acesso depois de uma renovação paga.

    Com acesso vigente, estende a partir do FIM ATUAL — senão o assinante que renova adiantado
    perde os dias que já tinha pago. Já expirado, conta de hoje e ganha o bônus de resgate.
    O dia do vencimento ainda conta como acesso vigente (ele tem o dia inteiro).
    """
    fim = None
    if acesso_ate:
        try:
            fim = datetime.fromisoformat(str(acesso_ate)).date()
        except (TypeError, ValueError):
            fim = None
    vigente = fim is not None and fim >= hoje
    base = fim if vigente else hoje
    extra = 0 if vigente else int(bonus_dias or 0)
    return base + timedelta(days=int(dias_ciclo) + extra)
