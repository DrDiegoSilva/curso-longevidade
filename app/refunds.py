"""Regras do direito de arrependimento (CDC art. 49) e escolha do alvo do estorno.
Puro/testável: sem rede, sem banco. Quem chama a API do Asaas é o serve.py.

Regra de negócio (spec 2026-07-24): reembolso existe SOMENTE dentro dos 7 dias.
Depois disso o cancelamento não devolve valor — o acesso segue até o fim do período pago.
"""
from datetime import datetime


def dentro_arrependimento(criado_em, hoje, dias=7):
    """True se `hoje` está dentro do prazo de arrependimento contado de `criado_em`.

    `criado_em` é o ISO de `subscribers.criado_em`, gravado quando o webhook confirma o
    pagamento — é a data da contratação efetiva, que é o marco do art. 49.
    O prazo é INCLUSIVO: no dia `dias` o consumidor ainda tem direito.

    Data ausente ou malformada devolve False de propósito: sem data confiável, dinheiro
    não sai automaticamente. Esses casos seguem pelo caminho manual.
    """
    if not criado_em:
        return False
    try:
        d = datetime.fromisoformat(str(criado_em)).date()
    except (TypeError, ValueError):
        return False
    return (hoje - d).days <= int(dias)


def alvo_estorno(pagamento):
    """Decide o que estornar a partir do objeto de pagamento do Asaas.

    Cartão parcelado vira um `installment` com N cobranças: estornar só o `payment` da
    parcela 1 devolveria 1/12 do valor. Quando o campo `installment` existe, o alvo é o
    parcelamento inteiro.

    Retorna ("installment", id) ou ("payment", id).
    """
    inst = (pagamento or {}).get("installment")
    if inst:
        return ("installment", inst)
    return ("payment", (pagamento or {}).get("id"))
