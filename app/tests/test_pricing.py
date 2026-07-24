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

    def test_anual_997(self):
        pl = self.cfg.plano_por_slug("anual")
        self.assertEqual(pl["base"], 997.0)
        self.assertEqual(pl["preco"], "R$ 997")

    def test_fmt_brl(self):
        self.assertEqual(self.p.fmt_brl(99.0), "R$ 99,00")
        self.assertEqual(self.p.fmt_brl(1008.0), "R$ 1.008,00")
        self.assertEqual(self.p.fmt_brl(1008.5), "R$ 1.008,50")


if __name__ == "__main__":
    unittest.main()
