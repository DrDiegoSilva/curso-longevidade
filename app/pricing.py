"""Preço de cartão SEM JUROS (D1 2026-07-23) + founder pricing (D2 2026-07-24).
Cartão: o cliente paga o valor do plano parcelado em até 12x, sem gross-up.
Founder: enquanto houver < config.FOUNDER_LIMITE assinantes ativos, valem os preços de
lançamento (base/preco); a partir do limite, os pós-founder (base_pos/preco_pos).
Puro/testável.
"""
import config


def valor_cartao(base, parcelas=1):
    """Sem juros: cobra o valor base (sem gross-up), independente das parcelas."""
    return round(float(base), 2)


def opcoes_parcelas(base, max_parcelas=12):
    out = []
    for n in range(1, int(max_parcelas) + 1):
        total = valor_cartao(base, n)
        out.append({"parcelas": n, "total": total, "por_parcela": round(total / n, 2)})
    return out


def _pos_founder(plano, n_ativos):
    """True se o plano tem preço pós-founder e já batemos o limite de assinantes ativos."""
    return bool(plano.get("base_pos")) and int(n_ativos) >= config.FOUNDER_LIMITE


def preco_vigente(plano, n_ativos):
    """Valor a cobrar hoje: base_pos se pós-founder, senão base."""
    return float(plano["base_pos"]) if _pos_founder(plano, n_ativos) else float(plano["base"])


def preco_str_vigente(plano, n_ativos):
    """String de exibição do preço vigente (mantém o estilo 'R$ 997' sem centavos)."""
    if _pos_founder(plano, n_ativos):
        return plano.get("preco_pos") or plano.get("preco")
    return plano.get("preco")


def nota_str_vigente(plano, n_ativos):
    """Nota vigente do card (nota_pos no pós-founder, se existir)."""
    if _pos_founder(plano, n_ativos):
        return plano.get("nota_pos") or plano.get("nota")
    return plano.get("nota")


def vagas_founder(n_ativos):
    """Quantas vagas restam no preço de lançamento (0 se já passou do limite)."""
    return max(0, config.FOUNDER_LIMITE - int(n_ativos))


def fmt_brl(v):
    s = f"{float(v):,.2f}"                      # 1,008.00 (estilo US)
    s = s.replace(",", "§").replace(".", ",").replace("§", ".")  # -> 1.008,00
    return f"R$ {s}"


def valor_com_desconto(base, pct):
    """Aplica pct% de desconto sobre a base. valor_com_desconto(997, 10) -> 897.30"""
    return round(float(base) * (1 - float(pct) / 100.0), 2)


def base_cobrada(plano, metodo, base_vig, cupom_pct=0.0):
    """Valor efetivamente cobrado: aplica o cupom (%) sobre a base vigente e, se for PIX e o plano
    oferecer `pix_desconto_pct`, o desconto Pix por cima (empilha com o cupom). Puro/testável."""
    v = valor_com_desconto(base_vig, cupom_pct) if cupom_pct else round(float(base_vig), 2)
    if (metodo or "").upper() == "PIX" and plano.get("pix_desconto_pct"):
        v = valor_com_desconto(v, plano["pix_desconto_pct"])
    return v


def comissao(valor_venda, pct):
    """pct% de comissão sobre o valor pago. comissao(897.30, 3) -> 26.92"""
    return round(float(valor_venda) * float(pct) / 100.0, 2)
