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
    """Valor a cobrar na renovação: a BASE contratada, ou a base de tabela quando não houver.

    `valor_contratado` guarda a BASE do plano no momento da contratação (pré-desconto de
    método, pré-cupom de afiliado) — nunca o valor pago. Duas razões, as duas de dinheiro:
    no cartão parcelado o valor pago de cada evento é UMA parcela (gravar isso fazia o anual
    em 12x renovar por R$ 91,58); e no Pix o valor pago já tem os 5% de desconto, que
    `pricing.base_cobrada` aplica DE NOVO a cada renovação (o preço derretia por ciclo).

    O fallback existe porque `valor_contratado` só passou a ser gravado agora — os assinantes
    anteriores entraram no preço de lançamento, que é justamente o `base` do plano.

    SÓ VALE PARA O MESMO PLANO. As mensagens de resgate mandam quem perdeu o acesso para o
    `/assinar` público, onde o cliente ESCOLHE o plano: sem esta checagem, um ex-mensal (99)
    levava o anual por R$ 94,05, e o plano `teste` (R$ 5, oculto mas alcançável por
    /assinar?plano=teste) virava trava de preço vitalícia em qualquer plano.

    Só valor FINITO e POSITIVO é aceito: `float()` converte "inf"/"nan" sem reclamar, e um
    infinito passaria por uma checagem ingênua de `> 0` e viraria preço cobrado. Qualquer coisa
    fora disso (ausente, zero, negativo, texto, infinito) cai no base — errar aqui é dinheiro.
    """
    import math
    sub = sub or {}
    if (sub.get("plano") or "") != (plano or {}).get("slug"):
        return float(plano["base"])
    try:
        v = float(sub.get("valor_contratado") or 0)
    except (TypeError, ValueError):
        v = 0.0
    return v if (math.isfinite(v) and v > 0) else float(plano["base"])


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
