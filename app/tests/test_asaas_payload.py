"""Testes do montador de payload do checkout Asaas (puro). Standalone."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPayload(unittest.TestCase):
    def setUp(self):
        import config, asaas, pricing
        self.cfg, self.a, self.p = config, asaas, pricing
        self.dados = {"nome": "Dr. X", "cpf": "123.456.789-00", "email": "x@y.com", "whatsapp": "(43) 99999-0000"}

    def _plano(self, slug):
        return self.cfg.plano_por_slug(slug)

    def test_mensal_pix_recorrente(self):
        p = self.a.montar_checkout(self._plano("mensal"), "PIX", 1, self.dados, "tok1", "https://x")
        self.assertEqual(p["billingTypes"], ["PIX"])
        self.assertEqual(p["chargeTypes"], ["RECURRENT"])
        self.assertEqual(p["value"], 99.0)
        self.assertEqual(p["subscription"]["cycle"], "MONTHLY")
        self.assertEqual(p["externalReference"], "tok1")
        self.assertEqual(p["customerData"]["cpfCnpj"], "12345678900")

    def test_mensal_cartao_recorrente(self):
        p = self.a.montar_checkout(self._plano("mensal"), "CARTAO", 1, self.dados, "t", "https://x")
        self.assertEqual(p["billingTypes"], ["CREDIT_CARD"])
        self.assertEqual(p["chargeTypes"], ["RECURRENT"])
        self.assertEqual(p["value"], self.p.valor_cartao(99.0, 1))
        self.assertNotIn("installmentCount", p)

    def test_anual_cartao_parcelado(self):
        p = self.a.montar_checkout(self._plano("anual"), "CARTAO", 12, self.dados, "t", "https://x")
        self.assertEqual(p["chargeTypes"], ["RECURRENT"])
        self.assertEqual(p["subscription"]["cycle"], "YEARLY")
        self.assertEqual(p["installmentCount"], 12)
        self.assertEqual(p["value"], self.p.valor_cartao(960.0, 12))

    def test_anual_pix_avulso(self):
        p = self.a.montar_checkout(self._plano("anual"), "PIX", 1, self.dados, "t", "https://x")
        self.assertEqual(p["billingTypes"], ["PIX"])
        self.assertEqual(p["chargeTypes"], ["DETACHED"])
        self.assertEqual(p["value"], 960.0)
        self.assertNotIn("subscription", p)

    def test_success_url(self):
        p = self.a.montar_checkout(self._plano("mensal"), "PIX", 1, self.dados, "t", "https://artigos.x")
        self.assertEqual(p["callback"]["successUrl"], "https://artigos.x/obrigado")


if __name__ == "__main__":
    unittest.main()
