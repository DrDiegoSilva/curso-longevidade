"""Testes do pricing.py — cartão SEM JUROS (sem gross-up; D1 2026-07-23). Standalone."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPricing(unittest.TestCase):
    def setUp(self):
        import pricing
        self.p = pricing
        import config
        self.cfg = config

    def test_valor_cartao_sem_juros(self):
        # sem juros: cobra o valor base, independente das parcelas (até o teto de 12x)
        for n in range(1, 13):
            self.assertEqual(self.p.valor_cartao(997.0, n), 997.0)

    def test_opcoes_parcelas_sem_juros(self):
        ops = self.p.opcoes_parcelas(997.0, max_parcelas=12)
        self.assertEqual(len(ops), 12)
        self.assertEqual(ops[0]["parcelas"], 1)
        for o in ops:
            self.assertEqual(o["total"], 997.0)                       # total = base (sem juros)
            self.assertEqual(o["por_parcela"], round(997.0 / o["parcelas"], 2))

    def test_anual_1497(self):
        pl = self.cfg.plano_por_slug("anual")
        self.assertEqual(pl["base"], 1497.0)
        self.assertEqual(pl["preco"], "R$ 1.497")
        self.assertEqual(pl["pix_desconto_pct"], 5)

    def test_fmt_brl(self):
        self.assertEqual(self.p.fmt_brl(99.0), "R$ 99,00")
        self.assertEqual(self.p.fmt_brl(1008.0), "R$ 1.008,00")
        self.assertEqual(self.p.fmt_brl(1008.5), "R$ 1.008,50")

    def test_preco_vigente_founder_e_pos(self):
        anual = self.cfg.plano_por_slug("anual")
        self.assertEqual(self.p.preco_vigente(anual, 0), 1497.0)
        self.assertEqual(self.p.preco_vigente(anual, self.cfg.FOUNDER_LIMITE), 1497.0)
        mensal = self.cfg.plano_por_slug("mensal")
        self.assertEqual(self.p.preco_vigente(mensal, 0), 147.0)
        self.assertEqual(self.p.preco_vigente(mensal, 999), 147.0)
        tri = self.cfg.plano_por_slug("trimestral")      # sem base_pos -> sempre base
        self.assertEqual(self.p.preco_vigente(tri, 999), float(tri["base"]))

    def test_vagas_founder(self):
        lim = self.cfg.FOUNDER_LIMITE
        self.assertEqual(self.p.vagas_founder(0), lim)
        self.assertEqual(self.p.vagas_founder(7), lim - 7)
        self.assertEqual(self.p.vagas_founder(lim + 5), 0)

    def test_preco_str_vigente(self):
        anual = self.cfg.plano_por_slug("anual")
        self.assertEqual(self.p.preco_str_vigente(anual, 0), "R$ 1.497")
        self.assertEqual(self.p.preco_str_vigente(anual, self.cfg.FOUNDER_LIMITE), "R$ 1.497")

    def test_valor_com_desconto(self):
        self.assertEqual(self.p.valor_com_desconto(997.0, 10), 897.30)
        self.assertEqual(self.p.valor_com_desconto(99.0, 10), 89.10)
        self.assertEqual(self.p.valor_com_desconto(1497.0, 10), 1347.30)
        self.assertEqual(self.p.valor_com_desconto(100.0, 0), 100.0)   # 0% = base

    def test_base_cobrada_anual_pix_e_cupom(self):
        anual = self.cfg.plano_por_slug("anual")     # base 1099, pix_desconto_pct 5
        mensal = self.cfg.plano_por_slug("mensal")   # sem pix_desconto_pct
        # cartão: só o cupom (NÃO ganha os 5% do Pix)
        self.assertEqual(self.p.base_cobrada(anual, "CARTAO", 1099.0, 10), 989.10)
        self.assertEqual(self.p.base_cobrada(anual, "CARTAO", 1099.0, 0), 1099.0)
        # Pix sem cupom: 5% sobre a base
        self.assertEqual(self.p.base_cobrada(anual, "PIX", 1099.0, 0), 1044.05)
        # Pix + cupom: empilha (cupom primeiro, depois 5% do Pix)
        esperado = self.p.valor_com_desconto(self.p.valor_com_desconto(1099.0, 10), 5)
        self.assertEqual(self.p.base_cobrada(anual, "PIX", 1099.0, 10), esperado)
        # mensal no Pix NÃO ganha desconto (5% é só no anual)
        self.assertEqual(self.p.base_cobrada(mensal, "PIX", 99.0, 0), 99.0)

    def test_comissao(self):
        self.assertEqual(self.p.comissao(897.30, 3), 26.92)
        self.assertEqual(self.p.comissao(89.10, 3), 2.67)
        self.assertEqual(self.p.comissao(1000.0, 0), 0.0)


class TestFigurasAssinar(unittest.TestCase):
    """`figuras_assinar` = TODAS as figuras de dinheiro que a tela /assinar mostra,
    calculadas num único lugar (o mesmo que o fechamento usa, via `base_cobrada`).

    Existe por causa de um bug ao vivo (2026-07-29): a prévia do cupom só atualizava o
    resumo, então o tile do Pix e o dropdown de parcelas continuavam mostrando valores
    SEM o cupom — e o dropdown chegou a mostrar o valor do PIX parcelado, que não
    existe (Pix é à vista). Uma função só, usada pela página E pela prévia, é o que
    impede as três figuras de divergirem."""

    def setUp(self):
        import pricing, config
        self.p, self.cfg = pricing, config
        self.anual = config.plano_por_slug("anual")     # 1497, pix -5%
        self.mensal = config.plano_por_slug("mensal")   # 147, recorrente, sem Pix

    # ── as duas âncoras de dinheiro do plano anual com LANCAMENTO (−R$ 500) ──
    def test_cartao_anual_com_lancamento_e_997(self):
        f = self.p.figuras_assinar(self.anual, "CARTAO", 1497.0, cupom_valor=500.0)
        self.assertEqual(f["preco"], "R$ 997,00")

    def test_pix_anual_com_lancamento_e_947_15(self):
        f = self.p.figuras_assinar(self.anual, "PIX", 1497.0, cupom_valor=500.0)
        self.assertEqual(f["preco"], "R$ 947,15")

    def test_pix_desc_nao_depende_do_metodo_escolhido(self):
        """O tile do Pix mostra SEMPRE o à-vista do Pix — inclusive quando o visitante
        está com o Cartão selecionado. Era aqui que a tela mentia: o tile ficava com
        1.422,15 (1497 − 5%, sem o cupom)."""
        for metodo in ("CARTAO", "PIX"):
            f = self.p.figuras_assinar(self.anual, metodo, 1497.0, cupom_valor=500.0)
            self.assertEqual(f["pix_desc"], "R$ 947,15 à vista", metodo)

    def test_parcelas_saem_da_base_do_CARTAO_mesmo_no_pix(self):
        """Parcelamento só existe no cartão: a lista nunca pode empilhar o desconto do
        Pix (era o "12x de R$ 78,93 — total R$ 947,15" visto ao vivo)."""
        for metodo in ("CARTAO", "PIX"):
            f = self.p.figuras_assinar(self.anual, metodo, 1497.0, cupom_valor=500.0)
            self.assertEqual({o["total"] for o in f["parcelas"]}, {"R$ 997,00"}, metodo)
            doze = [o for o in f["parcelas"] if o["parcelas"] == 12][0]
            self.assertEqual(doze["por_parcela"], "R$ 83,08", metodo)

    def test_parcelas_tem_as_tres_chaves_que_o_js_le_ja_formatadas(self):
        f = self.p.figuras_assinar(self.anual, "CARTAO", 1497.0)
        self.assertEqual(len(f["parcelas"]), 12)
        for o in f["parcelas"]:
            self.assertEqual(sorted(o), ["parcelas", "por_parcela", "total"])
            self.assertIsInstance(o["parcelas"], int)
            self.assertTrue(o["por_parcela"].startswith("R$ "), o)
            self.assertTrue(o["total"].startswith("R$ "), o)

    def test_cartao_desc_do_plano_recorrente_traz_o_valor_com_desconto(self):
        """Mensal mostra dinheiro no tile do Cartão ("R$ X/mês · renova") — com um
        código de afiliado (10%) o tile tem que acompanhar, senão promete 147 e cobra
        132,30."""
        f = self.p.figuras_assinar(self.mensal, "CARTAO", 147.0, cupom_pct=10.0)
        self.assertEqual(f["cartao_desc"], "R$ 132,30/mês · renova")
        self.assertEqual(f["preco"], "R$ 132,30")

    def test_cartao_desc_do_anual_nao_tem_dinheiro(self):
        f = self.p.figuras_assinar(self.anual, "CARTAO", 1497.0, cupom_valor=500.0)
        self.assertEqual(f["cartao_desc"], "parcelável · renova no fim")

    def test_sem_cupom_reproduz_o_preco_de_tabela(self):
        f = self.p.figuras_assinar(self.anual, "CARTAO", 1497.0)
        self.assertEqual(f["preco"], "R$ 1.497,00")
        self.assertEqual(f["pix_desc"], "R$ 1.422,15 à vista")
        self.assertEqual({o["total"] for o in f["parcelas"]}, {"R$ 1.497,00"})

    def test_tudo_vem_de_base_cobrada_e_opcoes_parcelas(self):
        """Sem aritmética duplicada: cada figura tem que casar com as funções que o
        fechamento usa (é a propriedade que a tela existe pra garantir)."""
        f = self.p.figuras_assinar(self.anual, "PIX", 1497.0, 10.0, 500.0)
        pix = self.p.base_cobrada(self.anual, "PIX", 1497.0, 10.0, 500.0)
        cartao = self.p.base_cobrada(self.anual, "CARTAO", 1497.0, 10.0, 500.0)
        self.assertEqual(f["preco"], self.p.fmt_brl(pix))
        self.assertEqual(f["pix_desc"], f"{self.p.fmt_brl(pix)} à vista")
        self.assertEqual(
            f["parcelas"],
            [{"parcelas": o["parcelas"], "por_parcela": self.p.fmt_brl(o["por_parcela"]),
              "total": self.p.fmt_brl(o["total"])} for o in self.p.opcoes_parcelas(cartao)])

    def test_base_vigente_manda_no_lugar_de_plano_base(self):
        # pós-founder: quem chama passa a base VIGENTE, e é ela que aparece em tudo.
        f = self.p.figuras_assinar(self.anual, "CARTAO", 1997.0, cupom_valor=500.0)
        self.assertEqual(f["preco"], "R$ 1.497,00")
        self.assertEqual({o["total"] for o in f["parcelas"]}, {"R$ 1.497,00"})


if __name__ == "__main__":
    unittest.main()
