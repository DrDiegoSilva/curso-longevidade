"""Testes da tela de renovação. Standalone."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PLANO = {"slug": "anual", "nome": "Anual", "cycle": "YEARLY", "base": 1099.0,
         "pix_desconto_pct": 5}


class TestPaginaRenovar(unittest.TestCase):
    def setUp(self):
        import site_web
        self.sw = site_web

    def test_mostra_plano_preco_e_vencimento(self):
        html = self.sw.pagina_renovar({"nome": "Teste"}, PLANO, 1044.05, 1099.0,
                                      "2026-08-01", bonus=False)
        self.assertIn("Anual", html)
        self.assertIn("1.044,05", html)
        self.assertIn("1.099,00", html)
        # site_web._data_br formata por extenso ("1 ago 2026"), não DD/MM/AAAA —
        # usamos o helper existente em vez de reimplementar formatação de data.
        self.assertIn("1 ago 2026", html)

    def test_nao_tem_campo_de_cupom(self):
        # cupom de afiliado é só na 1ª venda — a tela de renovação não pode oferecer
        html = self.sw.pagina_renovar({"nome": "T"}, PLANO, 1044.05, 1099.0,
                                      "2026-08-01", bonus=False)
        self.assertNotIn('name="cupom"', html)

    def test_bonus_aparece_so_quando_expirado(self):
        com = self.sw.pagina_renovar({"nome": "T"}, PLANO, 1044.05, 1099.0,
                                     "2026-08-01", bonus=True)
        sem = self.sw.pagina_renovar({"nome": "T"}, PLANO, 1044.05, 1099.0,
                                     "2026-08-01", bonus=False)
        self.assertIn("1 mês extra", com)
        self.assertNotIn("1 mês extra", sem)

    def test_form_posta_o_metodo_escolhido(self):
        html = self.sw.pagina_renovar({"nome": "T"}, PLANO, 1044.05, 1099.0,
                                      "2026-08-01", bonus=False)
        self.assertIn('action="/renovar"', html)
        self.assertIn('name="metodo"', html)


if __name__ == "__main__":
    unittest.main()
