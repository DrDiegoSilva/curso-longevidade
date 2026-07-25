"""Testes do re-aceite dos termos pela base atual. Standalone."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPrecisaAceitar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "subscribers"):
            sys.modules.pop(m, None)
        import db, subscribers, legal
        db._INITED = False
        db.init()
        self.subs, self.legal = subscribers, legal

    def test_assinante_sem_aceite_precisa_aceitar(self):
        self.assertTrue(self.subs.precisa_aceitar({"termos_versao": None}))
        self.assertTrue(self.subs.precisa_aceitar({}))

    def test_assinante_com_versao_antiga_precisa_aceitar(self):
        self.assertTrue(self.subs.precisa_aceitar({"termos_versao": "2020-01-01"}))

    def test_assinante_com_versao_atual_nao_precisa(self):
        self.assertFalse(self.subs.precisa_aceitar({"termos_versao": self.legal.VERSAO}))

    def test_registrar_aceite_grava_versao_data_e_ip(self):
        reg = self.subs.criar_de_pagamento(
            {"nome": "T", "whatsapp": "43999990000", "email": "t@e.com", "plano": "anual"}, {})
        self.subs.registrar_aceite(reg["id"], self.legal.VERSAO, "203.0.113.7")
        atual = [s for s in self.subs.listar() if s["id"] == reg["id"]][0]
        self.assertEqual(atual["termos_versao"], self.legal.VERSAO)
        self.assertTrue(atual["termos_aceito_em"])
        self.assertEqual(atual["termos_ip"], "203.0.113.7")
        self.assertFalse(self.subs.precisa_aceitar(atual))


class TestPaginaAceite(unittest.TestCase):
    def test_pagina_tem_checkbox_e_links(self):
        import site_legal
        html = site_legal.pagina_aceite_termos("/minha")
        self.assertIn('name="aceito"', html)
        self.assertIn('action="/aceitar-termos"', html)
        self.assertIn('href="/termos"', html)
        self.assertIn('href="/privacidade"', html)
        self.assertIn('value="/minha"', html)


if __name__ == "__main__":
    unittest.main()
