"""Testes do pricing.py (gross-up da taxa de cartão). Standalone."""
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

    def test_faixa(self):
        self.assertEqual(self.p.faixa(1), "avista")
        self.assertEqual(self.p.faixa(2), "ate6")
        self.assertEqual(self.p.faixa(6), "ate6")
        self.assertEqual(self.p.faixa(7), "ate12")
        self.assertEqual(self.p.faixa(12), "ate12")

    def test_valor_cartao_gross_up(self):
        base = 960.0
        v1 = self.p.valor_cartao(base, 1)
        pct = self.cfg.TAXA_CARTAO["avista"]
        esperado = round((base + self.cfg.TAXA_FIXA) / (1 - pct), 2)
        self.assertEqual(v1, esperado)
        self.assertGreater(v1, base)  # taxa embutida

    def test_valor_cartao_monotonico_por_faixa(self):
        base = 960.0
        self.assertLess(self.p.valor_cartao(base, 1), self.p.valor_cartao(base, 6))
        self.assertLess(self.p.valor_cartao(base, 6), self.p.valor_cartao(base, 12))

    def test_opcoes_parcelas(self):
        ops = self.p.opcoes_parcelas(269.0, max_parcelas=12)
        self.assertEqual(len(ops), 12)
        self.assertEqual(ops[0]["parcelas"], 1)
        for o in ops:
            self.assertEqual(o["por_parcela"], round(o["total"] / o["parcelas"], 2))

    def test_fmt_brl(self):
        self.assertEqual(self.p.fmt_brl(99.0), "R$ 99,00")
        self.assertEqual(self.p.fmt_brl(1008.0), "R$ 1.008,00")
        self.assertEqual(self.p.fmt_brl(1008.5), "R$ 1.008,50")


if __name__ == "__main__":
    unittest.main()
