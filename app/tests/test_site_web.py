"""Smoke test do render (site_web). Standalone: python3 app/tests/test_site_web.py"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DSCURSO_DATA", tempfile.mkdtemp())


class TestRender(unittest.TestCase):
    def setUp(self):
        import site_web
        self.s = site_web

    def test_landing(self):
        h = self.s.landing()
        self.assertIn("<!doctype html>", h)
        self.assertIn("Quero assinar", h)
        self.assertIn("CRM-PR 54310", h)
        self.assertIn("Obesidade", h)

    def test_entrar(self):
        self.assertIn("Enviar código", self.s.pagina_entrar("numero"))
        self.assertIn("Digite o código", self.s.pagina_entrar("codigo", whatsapp="55x"))
        self.assertIn("noindex", self.s.pagina_entrar("numero"))

    def test_hub_vazio_e_cheio(self):
        self.assertIn("Ainda não há", self.s.hub_temas([]))
        h = self.s.hub_temas([{"slug": "obesidade", "rotulo": "Obesidade", "emoji": "⚖️", "cor": "#14332a", "total": 2}])
        self.assertIn("2 edições", h)
        self.assertIn("/artigos/obesidade", h)

    def test_lista_e_digest(self):
        meta = {"slug": "obesidade", "rotulo": "Obesidade", "emoji": "⚖️", "cor": "#14332a"}
        digs = [{"data": "2026-07-19", "titulo_pt": "Estudo X"}]
        self.assertIn("Estudo X", self.s.lista_tema(meta, digs))
        d = {"data": "2026-07-19", "titulo_pt": "Estudo X <b>", "resumo": "Linha *forte*",
             "gancho": "dica", "grafico": '{"barras":[{"rotulo":"A","valor":5}]}', "doi": "10/x", "fonte": "NEJM", "url": "http://x"}
        html = self.s.pagina_digest(meta, d)
        self.assertIn("Estudo X &lt;b&gt;", html)   # escapado
        self.assertIn("<strong>forte</strong>", html)
        self.assertIn("bar-fill", html)             # gráfico renderizado
        self.assertIn("Ver o estudo original", html)

    def test_robots(self):
        self.assertIn("Disallow: /artigos", self.s.robots_txt())


if __name__ == "__main__":
    unittest.main()
