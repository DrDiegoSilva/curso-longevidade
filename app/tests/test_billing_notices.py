"""Testes do billing_notices (seleção de quem avisar). Standalone."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAvisar(unittest.TestCase):
    def setUp(self):
        import billing_notices
        self.b = billing_notices
        self.hoje = date(2026, 7, 19)

    def _s(self, pv, status="ATIVO", aviso=None, email="a@x.com", asaas_subscription_id="sub_1"):
        return {"id": "1", "status": status, "proximo_vencimento": pv, "aviso_renov_em": aviso,
                "email": email, "asaas_subscription_id": asaas_subscription_id}

    def test_dentro_da_janela(self):
        pv = (self.hoje + timedelta(days=2)).isoformat()
        self.assertEqual(len(self.b.assinantes_a_avisar([self._s(pv)], 3, self.hoje)), 1)

    def test_fora_da_janela(self):
        pv = (self.hoje + timedelta(days=10)).isoformat()
        self.assertEqual(self.b.assinantes_a_avisar([self._s(pv)], 3, self.hoje), [])

    def test_ja_avisado_nao_reavisa(self):
        pv = (self.hoje + timedelta(days=1)).isoformat()
        self.assertEqual(self.b.assinantes_a_avisar([self._s(pv, aviso=pv)], 3, self.hoje), [])

    def test_novo_ciclo_reavisa(self):
        pv = (self.hoje + timedelta(days=1)).isoformat()
        velho = (self.hoje - timedelta(days=360)).isoformat()
        self.assertEqual(len(self.b.assinantes_a_avisar([self._s(pv, aviso=velho)], 3, self.hoje)), 1)

    def test_cancelado_nao_avisa(self):
        pv = (self.hoje + timedelta(days=1)).isoformat()
        self.assertEqual(self.b.assinantes_a_avisar([self._s(pv, status="CANCELADO")], 3, self.hoje), [])

    def test_sem_assinatura_recorrente_nao_avisa(self):
        # Pix à vista / cartão parcelado não tem asaas_subscription_id — quem avisa
        # esse público agora é a régua (regua.py), não este e-mail de pré-renovação.
        pv = (self.hoje + timedelta(days=1)).isoformat()
        self.assertEqual(
            self.b.assinantes_a_avisar([self._s(pv, asaas_subscription_id=None)], 3, self.hoje), [])


if __name__ == "__main__":
    unittest.main()
