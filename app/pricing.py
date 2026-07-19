"""Preço de cartão com gross-up da taxa (o Asaas credita o valor cheio).
Puro/testável. Taxas em config.TAXA_CARTAO + config.TAXA_FIXA.
"""
import config


def faixa(parcelas):
    p = int(parcelas)
    if p <= 1:
        return "avista"
    if p <= 6:
        return "ate6"
    return "ate12"


def valor_cartao(base, parcelas=1):
    """Valor a cobrar no cartão para o Asaas creditar ~= base (gross-up)."""
    pct = config.TAXA_CARTAO[faixa(parcelas)]
    return round((float(base) + config.TAXA_FIXA) / (1 - pct), 2)


def opcoes_parcelas(base, max_parcelas=12):
    out = []
    for n in range(1, int(max_parcelas) + 1):
        total = valor_cartao(base, n)
        out.append({"parcelas": n, "total": total, "por_parcela": round(total / n, 2)})
    return out


def fmt_brl(v):
    s = f"{float(v):,.2f}"                      # 1,008.00 (estilo US)
    s = s.replace(",", "§").replace(".", ",").replace("§", ".")  # -> 1.008,00
    return f"R$ {s}"
