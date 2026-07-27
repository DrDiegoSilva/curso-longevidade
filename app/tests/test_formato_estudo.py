"""Testes do formato SYS_ESTUDO (estrutural + rewire dos geradores de um estudo). Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestFormatoEstudo(unittest.TestCase):
    def setUp(self):
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
        import resumo_diario as rd
        importlib.reload(rd)
        self.rd = rd

    def test_sys_estudo_tem_secoes_e_guardrails(self):
        s = self.rd.SYS_ESTUDO
        for m in ["RESUMO DIRETO", "RESUMO COMPLETO", "O que o estudo perguntou",
                  "Vieses e limita", "Pontos fortes", "Conflito de interesse",
                  "não declarado", "NÃO repita o título"]:
            self.assertIn(m, s)
        self.assertTrue("nunca invente" in s.lower() or "não invente" in s.lower())

    def test_sys_aprof_segue_para_o_digest(self):
        self.assertTrue(hasattr(self.rd, "SYS_APROF"))
        self.assertNotEqual(self.rd.SYS_ESTUDO, self.rd.SYS_APROF)

    def test_gerar_texto_usa_sys_estudo(self):
        cap = {}
        orig = self.rd.claude
        self.rd.claude = lambda model, prompt, system="", **k: cap.update(system=system, prompt=prompt) or ""
        try:
            self.rd.gerar_texto_do_artigo({"titulo": "T", "resumo": "ABSTRACT-XYZ",
                                           "data": "2026", "fonte": "F", "doi": "d"})
        finally:
            self.rd.claude = orig
        self.assertEqual(cap["system"], self.rd.SYS_ESTUDO)
        self.assertIn("ABSTRACT-XYZ", cap["prompt"])

    def test_curadoria_usa_sys_estudo(self):
        import curadoria
        importlib.reload(curadoria)
        cap = {}
        orig = self.rd.claude
        self.rd.claude = lambda model, prompt, system="", **k: cap.update(system=system) or ""
        try:
            curadoria.gerar_resumo(
                {"titulo": "T", "abstract": "X", "data": "", "fonte": "", "doi": ""},
                gerar_gancho=lambda a: "", gerar_grafico_json=lambda a: "", gerar_titulo=lambda a: "T")
        finally:
            self.rd.claude = orig
        self.assertEqual(cap.get("system"), self.rd.SYS_ESTUDO)


if __name__ == "__main__":
    unittest.main()
