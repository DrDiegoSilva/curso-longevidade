"""Testes das funções de estorno do asaas.py. Sem rede: _req é substituído. Standalone."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestEstorno(unittest.TestCase):
    def setUp(self):
        import asaas
        self.a = asaas
        self.chamadas = []
        self._req_original = asaas._req

        def fake_req(caminho, metodo="GET", payload=None):
            self.chamadas.append({"caminho": caminho, "metodo": metodo, "payload": payload})
            return {"ok": True}

        asaas._req = fake_req

    def tearDown(self):
        self.a._req = self._req_original

    def test_estorno_total_de_pagamento_nao_manda_valor(self):
        # sem `value` o Asaas estorna o total — é o que queremos no arrependimento
        self.a.estornar_pagamento("pay_123")
        self.assertEqual(self.chamadas[0]["caminho"], "payments/pay_123/refund")
        self.assertEqual(self.chamadas[0]["metodo"], "POST")
        self.assertNotIn("value", self.chamadas[0]["payload"])

    def test_estorno_de_pagamento_com_valor(self):
        self.a.estornar_pagamento("pay_123", 50.0)
        self.assertEqual(self.chamadas[0]["payload"]["value"], 50.0)

    def test_estorno_total_de_parcelamento(self):
        self.a.estornar_parcelamento("ins_999")
        self.assertEqual(self.chamadas[0]["caminho"], "installments/ins_999/refund")
        self.assertEqual(self.chamadas[0]["metodo"], "POST")
        self.assertNotIn("value", self.chamadas[0]["payload"])

    def test_estorno_leva_descricao(self):
        self.a.estornar_pagamento("pay_123")
        self.assertIn("description", self.chamadas[0]["payload"])
        self.assertIn("arrependimento", self.chamadas[0]["payload"]["description"].lower())


if __name__ == "__main__":
    unittest.main()
