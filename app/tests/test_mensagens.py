"""Testes das mensagens de boas-vindas editáveis (+ settings do db). Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestMensagens(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import db as _db
        importlib.reload(_db)
        import mensagens as _m
        importlib.reload(_m)
        self.db, self.m = _db, _m
        self.db.init()

    def test_get_set_config(self):
        self.assertEqual(self.db.get_config("x", "padrao"), "padrao")
        self.db.set_config("x", "novo")
        self.assertEqual(self.db.get_config("x", "padrao"), "novo")

    def test_wa_default_substitui(self):
        out = self.m.wa_boas_vindas("http://senha", "Ana")
        self.assertIn("http://senha", out)
        self.assertNotIn("{link}", out)
        self.assertNotIn("{nome}", out)

    def test_wa_editado_persiste(self):
        self.db.set_config(self.m.K_WA, "Oi {nome}, senha: {link}")
        self.assertEqual(self.m.wa_boas_vindas("http://s", "Bia"), "Oi Bia, senha: http://s")

    def test_wa_sem_link_reanexado(self):
        self.db.set_config(self.m.K_WA, "Sem link aqui")   # admin removeu {link}
        self.assertIn("http://LINKSEGURO", self.m.wa_boas_vindas("http://LINKSEGURO", "X"))

    def test_email_assunto_e_html_com_botao(self):
        assunto, html = self.m.email_boas_vindas("Ana", "http://senha")
        self.assertTrue(assunto)                           # tem assunto
        self.assertIn('href="http://senha"', html)         # link vira botão
        self.assertIn("Ana", html)                         # {nome} substituído
        self.assertNotIn("{link}", html)
        self.assertNotIn("{nome}", html)


if __name__ == "__main__":
    unittest.main()
