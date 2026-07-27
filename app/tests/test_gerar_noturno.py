"""Geração noturna dos candidatos priorizados na curadoria (fn injetável, sem IA).
Standalone: python3 app/tests/test_gerar_noturno.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import daily


class TestGerarNoturno(unittest.TestCase):
    def test_chama_o_gerador_e_devolve_o_total(self):
        chamou = []
        n = daily.gerar_selecionados_noturno(gerar_fn=lambda: chamou.append(1) or 3)
        self.assertEqual(n, 3)
        self.assertEqual(len(chamou), 1)

    def test_falha_no_gerador_nao_propaga(self):
        def explode():
            raise RuntimeError("IA fora do ar")
        self.assertEqual(daily.gerar_selecionados_noturno(gerar_fn=explode), 0)

    def test_nada_selecionado_devolve_zero(self):
        self.assertEqual(daily.gerar_selecionados_noturno(gerar_fn=lambda: 0), 0)


if __name__ == "__main__":
    unittest.main()
