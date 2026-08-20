"""Task 1: Renomear a trilha de "Trilha do Consultório" para "Trilha do Consultório Lucrativo".

O config.TRILHA_NOME é a fonte única que se propaga para:
1. Capa do PDF (app/pdf_trilha.py via montar_html)
2. Rodapé do PDF (app/pdf_trilha.py via montar_html)
3. Título de página (app/site_web.py via pagina_trilha)
4. Legenda do WhatsApp (app/trilha.py via enviar_para)

Testado per-função, não módulo inteiro — garante que o nome está sendo usado
no lugar certo, não apenas em algum lugar do arquivo.
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

    def test_nome_e_o_esperado(self):
        """O nome padrão deve ser 'Trilha do Consultório Lucrativo'."""
        import config
        self.assertEqual(config.TRILHA_NOME, "Trilha do Consultório Lucrativo")

    def test_env_ainda_sobrescreve(self):
        """DSCURSO_TRILHA_NOME continua tendo prioridade — é a válvula de escape sem deploy."""
        os.environ["DSCURSO_TRILHA_NOME"] = "Nome Via Env"
        try:
            import config
            importlib.reload(config)
            self.assertEqual(config.TRILHA_NOME, "Nome Via Env")
        finally:
            del os.environ["DSCURSO_TRILHA_NOME"]
            import config
            importlib.reload(config)

    def test_legenda_do_whatsapp_usa_o_nome_novo(self):
        """trilha.enviar_para monta a legenda com config.TRILHA_NOME — sem edição própria."""
        import trilha
        fonte = inspect.getsource(trilha.enviar_para)
        self.assertIn("config.TRILHA_NOME", fonte,
                      "trilha.enviar_para() deve usar config.TRILHA_NOME na legenda")

    def test_titulo_do_portal_usa_o_nome_novo(self):
        """site_web.pagina_trilha() renderiza o título com config.TRILHA_NOME (ou alias)."""
        import site_web
        fonte = inspect.getsource(site_web.pagina_trilha)
        # A função usa o alias _cfg.TRILHA_NOME (import config as _cfg)
        self.assertIn("_cfg.TRILHA_NOME", fonte,
                      "site_web.pagina_trilha() deve usar _cfg.TRILHA_NOME no título")

    def test_alias_cfg_referenciado(self):
        """site_web.py usa também o alias _cfg.TRILHA_NOME (import ... as _cfg)."""
        import site_web
        modulo_source = inspect.getsource(site_web)
        self.assertIn("_cfg.TRILHA_NOME", modulo_source,
                      "site_web.py deve ter alias _cfg.TRILHA_NOME")

    def test_pdf_trilha_usa_o_nome_novo(self):
        """pdf_trilha.montar_html() renderiza capa e rodapé com config.TRILHA_NOME."""
        import pdf_trilha
        fonte = inspect.getsource(pdf_trilha.montar_html)
        self.assertIn("config.TRILHA_NOME", fonte,
                      "pdf_trilha.montar_html() deve usar config.TRILHA_NOME em capa e rodapé")


if __name__ == "__main__":
    unittest.main()
