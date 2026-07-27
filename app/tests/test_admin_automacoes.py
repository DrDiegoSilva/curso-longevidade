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

    def test_pagina_mostra_o_bonus_de_resgate_atual(self):
        # Campo numérico do bônus de resgate, na seção "Régua de renovação", com o
        # valor atual (o que está salvo, ou o default 30) e a explicação da regra.
        import site_web
        html = site_web.pagina_admin_mensagens(
            "wa", "a", "c", "ra", "rc", automacoes=self.db.listar_automacoes(),
            token="t", bonus_resgate_dias=15)
        self.assertIn("salvar_bonus_resgate", html)
        self.assertIn('name="bonus_resgate_dias"', html)
        self.assertIn('value="15"', html)
        self.assertIn("perdido o acesso", html)     # explica a regra pro Diego
        self.assertIn("Régua de renovação", html)

    def test_escape_de_payload_xss_no_texto_da_automacao(self):
        """Verifica que payloads de script no campo texto são escapados.

        O campo texto das automações é renderizado diretamente no HTML da página
        /admin/mensagens. Se o escape for removido, XSS armazenado será possível.
        Este teste trava que _esc() está sendo usado corretamente.
        """
        import site_web

        # Automação com payload XSS no campo texto
        automacao_com_xss = {
            "id": "auto-1",
            "dias": -7,
            "canal": "email",
            "texto": "<script>alert('XSS')</script>",
            "ativo": 1
        }

        html = site_web.pagina_admin_mensagens(
            "wa", "assunto", "corpo", "renov assunto", "renov corpo",
            automacoes=[automacao_com_xss], token="t")

        # O payload XSS NÃO deve aparecer como tag crua (sem escape)
        self.assertNotIn("<script>alert('XSS')</script>", html,
                        "Payload XSS não deve aparecer desescapado no HTML")

        # O payload DEVE aparecer escapado (com &lt; e &gt;)
        self.assertIn("&lt;script&gt;alert(&#x27;XSS&#x27;)&lt;/script&gt;", html,
                     "Payload XSS deve aparecer escapado no HTML")

    def test_escape_de_payload_xss_no_id_da_automacao(self):
        """Verifica que payloads de script no campo id são escapados.

        O campo id das automações é renderizado em um input hidden do HTML
        da página /admin/mensagens. Se o escape for removido, XSS armazenado
        será possível quando o id for renderizado em outros contextos.
        Este teste trava que _esc() está sendo usado corretamente no campo id.
        """
        import site_web

        # Automação com payload XSS no campo id
        automacao_com_xss_id = {
            "id": "auto\" onload=\"alert('XSS')",
            "dias": -3,
            "canal": "whatsapp",
            "texto": "Texto normal",
            "ativo": 1
        }

        html = site_web.pagina_admin_mensagens(
            "wa", "assunto", "corpo", "renov assunto", "renov corpo",
            automacoes=[automacao_com_xss_id], token="t")

        # O payload XSS NO ID não deve aparecer desescapado
        self.assertNotIn("auto\" onload=\"alert('XSS')", html,
                        "Payload XSS no id não deve aparecer desescapado")

        # O payload DEVE aparecer escapado (aspas duplas escapadas)
        self.assertIn("auto&quot; onload=&quot;alert(&#x27;XSS&#x27;)", html,
                     "Payload XSS no id deve aparecer escapado")


if __name__ == "__main__":
    unittest.main()
