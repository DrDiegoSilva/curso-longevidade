"""Preço de cartão SEM JUROS (D1 2026-07-23): o cliente paga o valor do plano
parcelado em até 12x e o Diego absorve a taxa de transação (~4%) recebendo mês a mês
(antecipação desligada no Asaas). Puro/testável. Sem gross-up.
"""


def valor_cartao(base, parcelas=1):
    """Sem juros: cobra o valor base (sem gross-up), independente das parcelas."""
    return round(float(base), 2)


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
