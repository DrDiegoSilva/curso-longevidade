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


def base_cobrada(plano, metodo, base_vig, cupom_pct=0.0, cupom_valor=0.0):
    """Valor efetivamente cobrado: aplica o desconto FIXO do cupom promocional (R$), depois
    o cupom % (afiliado), e por fim, se for PIX e o plano oferecer `pix_desconto_pct`, o
    desconto Pix por cima (empilha). Puro/testável."""
    v = round(float(base_vig), 2)
    if cupom_valor:
        v = round(max(0.0, v - float(cupom_valor)), 2)
    if cupom_pct:
        v = valor_com_desconto(v, cupom_pct)
    if (metodo or "").upper() == "PIX" and plano.get("pix_desconto_pct"):
        v = valor_com_desconto(v, plano["pix_desconto_pct"])
    return v


def comissao(valor_venda, pct):
    """pct% de comissão sobre o valor pago. comissao(897.30, 3) -> 26.92"""
    return round(float(valor_venda) * float(pct) / 100.0, 2)


def figuras_assinar(plano, metodo, base_vig, cupom_pct=0.0, cupom_valor=0.0):
    """TODAS as figuras de dinheiro da tela /assinar, num só lugar. Puro/testável.

    Existe por causa de um bug ao vivo (2026-07-29): a tela mostra dinheiro em TRÊS
    lugares (resumo, tile do Pix, dropdown de parcelas) e a prévia do cupom atualizava
    só o resumo — o tile do Pix ficava com o valor SEM o cupom e o dropdown chegou a
    oferecer o valor do PIX parcelado, que não existe. Uma função só, chamada pela
    página (`site_web.pagina_assinar`) E pela prévia (`POST /assinar/cupom`), é o que
    impede as três de divergirem.

      preco          -> resumo, no MÉTODO escolhido (é o que será cobrado nesse método)
      pix_desc       -> tile do Pix: à-vista do Pix, SEMPRE (independe do método escolhido)
      cartao_desc    -> tile do Cartão (dinheiro só no plano recorrente; anual é texto fixo)
      parcelado_desc -> a opção "parcelado" do cartão, já com o TETO e a cifra da parcela
      parcelas       -> lista completa, SEMPRE sobre a base do CARTÃO: parcelamento não
                     existe no Pix (à vista), então empilhar o desconto do Pix aqui
                     ofereceria uma parcela que ninguém pode pagar.

    `parcelado_desc` sai da MESMA base que `parcelas` e pelo mesmo motivo. A tela não
    oferece mais 2x…11x (2026-07-30): o que vai pro Asaas é `maxInstallmentCount`, um
    teto, e quem escolhe o número final é o cliente na tela de pagamento — oferecer o
    número aqui seria escolher duas vezes, valendo só a segunda.

    `base_vig` é a base VIGENTE (a mesma que o fechamento usa — ver
    `pricing.preco_vigente`/`renovacao.preco_renovacao`), nunca `plano["base"]` cru.
    """
    base_pix = base_cobrada(plano, "PIX", base_vig, cupom_pct, cupom_valor)
    base_cartao = base_cobrada(plano, "CARTAO", base_vig, cupom_pct, cupom_valor)
    escolhida = base_pix if (metodo or "").upper() == "PIX" else base_cartao
    ops = opcoes_parcelas(base_cartao)
    teto = ops[-1]
    return {
        "preco": fmt_brl(escolhida),
        "pix_desc": f"{fmt_brl(base_pix)} à vista",
        # mensal (recorrente_pix): o tile diz o valor do ciclo; anual: texto sem dinheiro.
        # O anual não diz mais "renova no fim" no tile: no cartão ele agora é DUAS ofertas
        # (à vista renova, parcelado não), e a escolha aparece logo abaixo do tile.
        "cartao_desc": (f"{fmt_brl(valor_cartao(base_cartao, 1))}/mês · renova"
                        if plano.get("recorrente_pix") else "à vista ou parcelado"),
        "parcelado_desc": f"até {teto['parcelas']}x de {fmt_brl(teto['por_parcela'])} · não renova",
        "parcelas": [{"parcelas": o["parcelas"],
                      "por_parcela": fmt_brl(o["por_parcela"]),
                      "total": fmt_brl(o["total"])}
                     for o in opcoes_parcelas(base_cartao)],
    }
