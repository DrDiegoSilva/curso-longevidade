"""Testes do conteúdo legal: versão, cláusulas obrigatórias e render das páginas. Standalone."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestLegal(unittest.TestCase):
    def setUp(self):
        import legal
        self.legal = legal

    def test_versao_definida(self):
        self.assertTrue(self.legal.VERSAO)
        self.assertRegex(self.legal.VERSAO, r"^\d{4}-\d{2}-\d{2}$")

    def test_termos_tem_clausula_de_reembolso_negando_apos_o_prazo(self):
        texto = " ".join(corpo for _, corpo in self.legal.TERMOS)
        self.assertIn("NÃO gerando reembolso", texto)

    def test_termos_tem_prazo_de_arrependimento_de_7_dias(self):
        texto = " ".join(corpo for _, corpo in self.legal.TERMOS)
        self.assertIn("7 (sete) dias", texto)

    def test_termos_ressalvam_o_foro_do_consumidor(self):
        # eleição pura de foro contra consumidor é nula (CDC art. 51, IV c/c 101, I)
        texto = " ".join(corpo for _, corpo in self.legal.TERMOS)
        self.assertIn("Londrina", texto)
        self.assertIn("domicílio", texto)
        self.assertIn("101", texto)

    def test_privacidade_identifica_o_controlador(self):
        texto = " ".join(corpo for _, corpo in self.legal.PRIVACIDADE)
        self.assertIn("52.891.914/0001-93", texto)
        self.assertIn("Clínica Diego Silva LTDA", texto)
        self.assertIn("contato@drdiegosilva.com.br", texto)

    def test_privacidade_lista_os_operadores(self):
        texto = " ".join(corpo for _, corpo in self.legal.PRIVACIDADE)
        self.assertIn("Asaas", texto)


class TestPaginasLegais(unittest.TestCase):
    def test_pagina_termos_renderiza(self):
        import site_legal, legal
        html = site_legal.pagina_termos()
        self.assertIn("<!doctype html>", html)
        self.assertIn(legal.VERSAO, html)
        self.assertIn(legal.TERMOS[0][0], html)

    def test_pagina_privacidade_renderiza(self):
        import site_legal, legal
        html = site_legal.pagina_privacidade()
        self.assertIn("<!doctype html>", html)
        self.assertIn("52.891.914/0001-93", html)


if __name__ == "__main__":
    unittest.main()
