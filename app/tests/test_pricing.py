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

    def test_preco_vigente_founder_e_pos(self):
        anual = self.cfg.plano_por_slug("anual")
        self.assertEqual(self.p.preco_vigente(anual, 0), 997.0)
        self.assertEqual(self.p.preco_vigente(anual, self.cfg.FOUNDER_LIMITE), 1497.0)
        mensal = self.cfg.plano_por_slug("mensal")
        self.assertEqual(self.p.preco_vigente(mensal, 0), 99.0)
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
        self.assertEqual(self.p.preco_str_vigente(anual, 0), "R$ 997")
        self.assertEqual(self.p.preco_str_vigente(anual, self.cfg.FOUNDER_LIMITE), "R$ 1.497")


if __name__ == "__main__":
    unittest.main()
