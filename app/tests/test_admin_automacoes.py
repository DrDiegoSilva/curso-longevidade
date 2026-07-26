"""Testes da seção de automações no /admin/mensagens. Standalone."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPaginaAutomacoes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "site_web"):
            sys.modules.pop(m, None)
        import db
        db._INITED = False
        db.init()
        self.db = db

    def test_lista_as_automacoes_na_pagina(self):
        import site_web
        html = site_web.pagina_admin_mensagens(
            "wa", "assunto", "corpo", "renov assunto", "renov corpo",
            automacoes=self.db.listar_automacoes(), token="t")
        self.assertIn("salvar_automacao", html)
        self.assertIn("remover_automacao", html)
        self.assertIn('name="dias"', html)
        self.assertIn('name="canal"', html)
        # as seis padrão aparecem
        for d in (-7, -3, 0, 1, 3, 15):
            self.assertIn(f'value="{d}"', html)

    def test_marcadores_documentados_na_tela(self):
        import site_web
        html = site_web.pagina_admin_mensagens(
            "wa", "a", "c", "ra", "rc", automacoes=self.db.listar_automacoes(), token="t")
        for marcador in ("{nome}", "{ate}", "{link}"):
            self.assertIn(marcador, html)

    def test_pagina_funciona_sem_automacoes(self):
        import site_web
        html = site_web.pagina_admin_mensagens("wa", "a", "c", "ra", "rc",
                                               automacoes=[], token="t")
        self.assertIn("salvar_automacao", html)


if __name__ == "__main__":
    unittest.main()
