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
        self.claims = []

        self._orig = (asaas.obter_pagamento, asaas.estornar_pagamento,
                      asaas.estornar_parcelamento, db.estornar_comissao, db.claim_cancelamento)
        asaas.obter_pagamento = lambda pid: {"id": pid, "value": 997.0}
        asaas.estornar_pagamento = lambda pid, valor=None: self.estornos.append(("payment", pid))
        asaas.estornar_parcelamento = lambda iid, valor=None: self.estornos.append(("installment", iid))
        db.estornar_comissao = lambda sid: self.comissoes.append(sid) or 1
        # Por padrão o claim é sempre vencido (não há concorrência) — os testes de
        # corrida sobrescrevem isso pontualmente.
        db.claim_cancelamento = lambda sid: self.claims.append(sid) or True

        import webhook_asaas
        self._orig_alerta = webhook_asaas._alertar_admin
        webhook_asaas._alertar_admin = lambda pid, sid, motivo: self.alertas.append(motivo)

    def tearDown(self):
        (self.asaas.obter_pagamento, self.asaas.estornar_pagamento,
         self.asaas.estornar_parcelamento, self.db.estornar_comissao,
         self.db.claim_cancelamento) = self._orig
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

    def test_estorno_ok_mas_baixa_de_comissao_falha_devolve_valor_e_alerta_diferente(self):
        # ACHADO 1: o estorno no Asaas já saiu — a falha é só na baixa da comissão do
        # afiliado. A função tem que devolver o valor (não None) e o alerta precisa
        # deixar claro que o estorno DEU CERTO, não usar a mensagem de "estorno falhou".
        def explode(sid):
            raise RuntimeError("database is locked")
        self.db.estornar_comissao = explode
        valor = self.serve.estornar_arrependimento(_sub(3))
        self.assertEqual(valor, 997.0)
        self.assertEqual(self.estornos, [("payment", "pay_1")])
        self.assertEqual(len(self.alertas), 1)
        msg = self.alertas[0].lower()
        self.assertIn("comiss", msg)
        self.assertNotIn("estorne manualmente no painel do asaas", msg)

    def test_claim_perdido_nao_estorna_nem_alerta_e_devolve_none(self):
        # ACHADO 2: outra chamada concorrente (duplo clique/retry) já reivindicou o
        # cancelamento — não é falha, então sem alerta, e sem chamar o Asaas de novo.
        self.db.claim_cancelamento = lambda sid: False
        self.assertIsNone(self.serve.estornar_arrependimento(_sub(3)))
        self.assertEqual(self.estornos, [])
        self.assertEqual(self.comissoes, [])
        self.assertEqual(self.alertas, [])

    def test_claim_vencido_segue_o_fluxo_normal_de_estorno(self):
        valor = self.serve.estornar_arrependimento(_sub(3))
        self.assertEqual(valor, 997.0)
        self.assertEqual(self.claims, ["s1"])
        self.assertEqual(self.estornos, [("payment", "pay_1")])
        self.assertEqual(self.comissoes, ["s1"])
        self.assertEqual(self.alertas, [])


if __name__ == "__main__":
    unittest.main()
