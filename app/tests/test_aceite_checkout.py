"""Testes do aceite no checkout: obrigatório no POST e propagado na ativação. Standalone."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAceiteNoCheckout(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "subscribers"):
            sys.modules.pop(m, None)
        import db, legal
        db._INITED = False
        db.init()
        self.db, self.legal = db, legal

    def test_pagina_assinar_tem_checkbox_obrigatorio(self):
        import site_web
        html = site_web.pagina_assinar("anual")
        self.assertIn('name="aceito"', html)
        self.assertIn('href="/termos"', html)
        self.assertIn('href="/privacidade"', html)

    def test_pending_guarda_a_versao_aceita(self):
        token = self.db.criar_pending({"nome": "T", "email": "t@e.com", "cpf": "1", "whatsapp": "43999990000",
                                       "plano": "anual", "metodo": "PIX", "parcelas": 1, "valor": 997.0,
                                       "termos_versao": self.legal.VERSAO, "termos_ip": "203.0.113.7"})
        p = self.db.obter_pending(token)
        self.assertEqual(p["termos_versao"], self.legal.VERSAO)
        self.assertEqual(p["termos_ip"], "203.0.113.7")

    def test_ativacao_copia_o_aceite_pro_assinante(self):
        import subscribers
        reg = subscribers.criar_de_pagamento(
            {"nome": "T", "whatsapp": "43999990000", "email": "t@e.com", "plano": "anual",
             "termos_versao": self.legal.VERSAO, "termos_ip": "203.0.113.7"}, {})
        atual = [s for s in subscribers.listar() if s["id"] == reg["id"]][0]
        self.assertEqual(atual["termos_versao"], self.legal.VERSAO)
        self.assertFalse(subscribers.precisa_aceitar(atual))


if __name__ == "__main__":
    unittest.main()
