"""Task 1: Renomear a trilha de "Trilha do Consultório" para "Trilha do Consultório Lucrativo".

O config.TRILHA_NOME é a fonte única que se propaga para:
1. Capa do PDF (app/pdf_trilha.py)
2. Rodapé do PDF (app/pdf_trilha.py)
3. Título de página (app/site_web.py)
4. Legenda do WhatsApp (app/trilha.py)
"""
import importlib
import inspect
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DSCURSO_DATA", tempfile.mkdtemp())


class TestTrilhaNomePropaga(unittest.TestCase):
    """Valida que TRILHA_NOME se propaga corretamente por todo o código."""

    def setUp(self):
        """Reload dos módulos para pegar a config atualizada."""
        import config
        import trilha
        import site_web
        import pdf_trilha

        importlib.reload(config)
        importlib.reload(trilha)
        importlib.reload(site_web)
        importlib.reload(pdf_trilha)

        self.config = config
        self.trilha = trilha
        self.site_web = site_web
        self.pdf_trilha = pdf_trilha

    def test_trilha_nome_eh_lucrativa(self):
        """O nome padrão deve ser 'Trilha do Consultório Lucrativo'."""
        self.assertEqual(self.config.TRILHA_NOME, "Trilha do Consultório Lucrativo")

    def test_trilha_nome_nao_eh_antiga(self):
        """Garante que não é o nome antigo."""
        self.assertNotEqual(self.config.TRILHA_NOME, "Trilha do Consultório")

    def test_config_nome_referenciado_em_trilha_py(self):
        """Verifica que trilha.py referencia config.TRILHA_NOME."""
        source = inspect.getsource(self.trilha)
        self.assertIn("config.TRILHA_NOME", source,
                      "trilha.py deve referenciar config.TRILHA_NOME")

    def test_config_nome_referenciado_em_site_web_py(self):
        """Verifica que site_web.py referencia config.TRILHA_NOME."""
        source = inspect.getsource(self.site_web)
        self.assertIn("config.TRILHA_NOME", source,
                      "site_web.py deve referenciar config.TRILHA_NOME")

    def test_config_nome_referenciado_em_pdf_trilha_py(self):
        """Verifica que pdf_trilha.py referencia config.TRILHA_NOME."""
        source = inspect.getsource(self.pdf_trilha)
        self.assertIn("config.TRILHA_NOME", source,
                      "pdf_trilha.py deve referenciar config.TRILHA_NOME")


if __name__ == "__main__":
    unittest.main()
