"""Testes do estorno automático no cancelamento (7 dias). Sem rede. Standalone."""
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _sub(dias_atras, pid="pay_1", sid="sub_1"):
    return {"id": "s1", "nome": "Teste", "email": "t@e.com",
            "asaas_payment_id": pid, "asaas_subscription_id": sid,
            "criado_em": (datetime.now() - timedelta(days=dias_atras)).isoformat()}


class TestEstornoArrependimento(unittest.TestCase):
    def setUp(self):
        import serve, asaas, db
        self.serve, self.asaas, self.db = serve, asaas, db
        self.estornos = []
        self.comissoes = []
        self.alertas = []

        self._orig = (asaas.obter_pagamento, asaas.estornar_pagamento,
                      asaas.estornar_parcelamento, db.estornar_comissao)
        asaas.obter_pagamento = lambda pid: {"id": pid, "value": 997.0}
        asaas.estornar_pagamento = lambda pid, valor=None: self.estornos.append(("payment", pid))
        asaas.estornar_parcelamento = lambda iid, valor=None: self.estornos.append(("installment", iid))
        db.estornar_comissao = lambda sid: self.comissoes.append(sid) or 1

        import webhook_asaas
        self._orig_alerta = webhook_asaas._alertar_admin
        webhook_asaas._alertar_admin = lambda pid, sid, motivo: self.alertas.append(motivo)

    def tearDown(self):
        (self.asaas.obter_pagamento, self.asaas.estornar_pagamento,
         self.asaas.estornar_parcelamento, self.db.estornar_comissao) = self._orig
        import webhook_asaas
        webhook_asaas._alertar_admin = self._orig_alerta

    def test_cancelou_no_dia_3_estorna_integral(self):
        valor = self.serve.estornar_arrependimento(_sub(3))
        self.assertEqual(valor, 997.0)
        self.assertEqual(self.estornos, [("payment", "pay_1")])
        self.assertEqual(self.comissoes, ["s1"])

    def test_cancelou_no_dia_30_nao_estorna(self):
        self.assertIsNone(self.serve.estornar_arrependimento(_sub(30)))
        self.assertEqual(self.estornos, [])

    def test_parcelado_estorna_o_parcelamento_inteiro(self):
        self.asaas.obter_pagamento = lambda pid: {"id": pid, "value": 83.08, "installment": "ins_9"}
        self.serve.estornar_arrependimento(_sub(2))
        self.assertEqual(self.estornos, [("installment", "ins_9")])

    def test_cortesia_sem_pagamento_nao_estorna_nem_alerta(self):
        # cupom de cortesia entra sem asaas_payment_id — não é falha, é ausência de cobrança
        self.assertIsNone(self.serve.estornar_arrependimento(_sub(2, pid=None)))
        self.assertEqual(self.estornos, [])
        self.assertEqual(self.alertas, [])

    def test_falha_no_estorno_alerta_e_devolve_none(self):
        def explode(pid, valor=None):
            raise RuntimeError("saldo insuficiente")
        self.asaas.estornar_pagamento = explode
        self.assertIsNone(self.serve.estornar_arrependimento(_sub(2)))
        self.assertEqual(len(self.alertas), 1)
        self.assertIn("estorno", self.alertas[0].lower())


if __name__ == "__main__":
    unittest.main()
