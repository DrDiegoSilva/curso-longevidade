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

    def test_botao_regerar_audio_so_com_audio_on(self):
        r = {"data": "2026-07-18", "review_token": "tok", "resumo": "x",
             "artigo": {"titulo": "T", "fonte": "NEJM"}}
        sem = review_web.pagina_revisao(r, audio_on=False)
        self.assertNotIn("regerar_audio", sem)
        com = review_web.pagina_revisao(r, audio_on=True)
        self.assertIn('name="acao" value="regerar_audio"', com)
        self.assertIn("Regerar áudio", com)

    def test_aviso_aparece_quando_passado(self):
        r = {"data": "2026-07-18", "review_token": "tok", "resumo": "x",
             "artigo": {"titulo": "T", "fonte": "NEJM"}}
        html = review_web.pagina_revisao(r, aviso="Novo áudio enviado")
        self.assertIn("Novo áudio enviado", html)

    def test_pagina_admin_lista_form_e_token(self):
        html = review_web.pagina_admin([{"id": "a1", "nome": "Dra. Ana", "whatsapp": "5543"}], token="segredoADM")
        self.assertIn("Dra. Ana", html)
        self.assertIn("Assinantes (1)", html)
        self.assertIn('name="acao" value="adicionar"', html)
        self.assertIn('name="token" value="segredoADM"', html)  # token viaja no POST


if __name__ == "__main__":
    unittest.main()
