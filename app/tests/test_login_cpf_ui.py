"""Testes de render das telas de login em modo CPF. Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestLoginCPFUI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import site_web as _sw
        importlib.reload(_sw)
        self.sw = _sw

    def test_login_cpf_mode(self):
        html = self.sw.pagina_login(via="cpf")
        self.assertIn('action="/entrar-cpf"', html)
        self.assertIn('name="cpf"', html)
        self.assertIn("CPF", html)

    def test_login_whatsapp_inalterado_com_link_descoberta(self):
        html = self.sw.pagina_login()
        self.assertIn('action="/entrar"', html)
        self.assertIn('name="whatsapp"', html)
        self.assertIn('href="/entrar-cpf"', html)   # link de descoberta

    def test_entrar_codigo_cpf_numero(self):
        html = self.sw.pagina_entrar("numero", via="cpf")
        self.assertIn('action="/entrar-cpf-codigo"', html)
        self.assertIn('name="cpf"', html)

    def test_entrar_codigo_cpf_hidden_carrega_valor(self):
        html = self.sw.pagina_entrar("codigo", whatsapp="12345678901", via="cpf")
        self.assertIn('action="/entrar-cpf-codigo"', html)
        self.assertIn('name="cpf"', html)
        self.assertIn('value="12345678901"', html)


if __name__ == "__main__":
    unittest.main()
