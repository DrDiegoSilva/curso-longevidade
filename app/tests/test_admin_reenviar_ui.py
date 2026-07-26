"""Testes de render do botão/confirmação/feedback de reenviar boas-vindas. Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAdminReenviarUI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import site_web as _sw
        importlib.reload(_sw)
        self.sw = _sw

    def _sub(self, **kw):
        base = {"id": 7, "nome": "Gleidson", "whatsapp": "5544999998888",
                "email": "", "plano": "mensal", "status": "ATIVO"}
        base.update(kw)
        return base

    def test_botao_reenviar_por_linha(self):
        html = self.sw.pagina_admin([self._sub()], token="tk")
        self.assertIn('name="acao" value="reenviar"', html)
        self.assertIn("Reenviar", html)

    def test_caixa_confirmacao_quando_reenviar_id(self):
        html = self.sw.pagina_admin([self._sub()], token="tk", reenviar_id="7")
        self.assertIn('name="acao" value="reenviar_confirmar"', html)
        self.assertIn("Gleidson", html)
        self.assertIn("Confirmar reenvio", html)

    def test_feedback_sucesso(self):
        html = self.sw.pagina_admin([self._sub()], token="tk", sucesso="Boas-vindas reenviadas")
        self.assertIn("Boas-vindas reenviadas", html)


if __name__ == "__main__":
    unittest.main()
