import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import review_web


class TestReviewWeb(unittest.TestCase):
    def test_pagina_revisao_tem_texto_e_botoes(self):
        r = {"data": "2026-07-18", "review_token": "tok", "resumo": "meu resumo",
             "artigo": {"titulo": "T", "fonte": "NEJM"}}
        html = review_web.pagina_revisao(r)
        self.assertIn("meu resumo", html)
        self.assertIn("Aprovar", html)
        self.assertIn("Não enviar", html)
        self.assertIn('action="/revisar/tok"', html)

    def test_pagina_admin_lista_e_form(self):
        html = review_web.pagina_admin([{"id": "a1", "nome": "Dra. Ana", "whatsapp": "5543"}])
        self.assertIn("Dra. Ana", html)
        self.assertIn("Assinantes (1)", html)
        self.assertIn('name="acao" value="adicionar"', html)


if __name__ == "__main__":
    unittest.main()
