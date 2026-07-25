"""Texto do WhatsApp do assinante: badge do tema no topo (função pura)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import daily


class TestTextoResumo(unittest.TestCase):
    def test_badge_tema_no_topo(self):
        tmeta = {"rotulo": "Obesidade", "emoji": "⚖️"}
        txt = daily.montar_texto_resumo("Tirzepatida em 3 anos", "linha 1\nlinha 2", tmeta)
        self.assertTrue(txt.startswith("⚖️ *Obesidade*\n"))   # tema com emoji no topo
        self.assertIn("🔬 *Tirzepatida em 3 anos*", txt)      # título logo abaixo
        self.assertIn("linha 1\nlinha 2", txt)                # resumo preservado

    def test_sem_tema_nao_quebra(self):
        txt = daily.montar_texto_resumo("Título X", "resumo", {})
        self.assertTrue(txt.startswith("🔬 *Título X*"))       # sem tema -> sem badge


class TestSeloFresco(unittest.TestCase):
    def test_fresco_tem_selo(self):
        tmeta = {"rotulo": "Obesidade", "emoji": "⚖️"}
        txt = daily.montar_texto_resumo("Título X", "corpo", tmeta, fresco=True)
        self.assertIn("🆕", txt)
        self.assertIn("Estudo recente", txt)
        self.assertTrue(txt.index("Estudo recente") < txt.index("Título X"))  # selo no topo

    def test_nao_fresco_sem_selo(self):
        txt = daily.montar_texto_resumo("Título X", "corpo", {"rotulo": "Obesidade"}, fresco=False)
        self.assertNotIn("Estudo recente", txt)

    def test_default_sem_selo(self):
        txt = daily.montar_texto_resumo("T", "c", {})
        self.assertNotIn("Estudo recente", txt)


if __name__ == "__main__":
    unittest.main()
