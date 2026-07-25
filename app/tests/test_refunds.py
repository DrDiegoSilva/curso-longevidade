"""Testes do refunds.py — regra dos 7 dias (CDC art. 49) e alvo do estorno. Standalone."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDentroArrependimento(unittest.TestCase):
    def setUp(self):
        import refunds
        self.r = refunds

    def test_dia_zero_esta_dentro(self):
        self.assertTrue(self.r.dentro_arrependimento("2026-07-24T10:00:00", date(2026, 7, 24)))

    def test_dia_sete_ainda_esta_dentro(self):
        # 7 dias é inclusivo: o consumidor tem o dia 7 inteiro
        self.assertTrue(self.r.dentro_arrependimento("2026-07-24T10:00:00", date(2026, 7, 31)))

    def test_dia_oito_esta_fora(self):
        self.assertFalse(self.r.dentro_arrependimento("2026-07-24T10:00:00", date(2026, 8, 1)))

    def test_data_ausente_fica_fora(self):
        # sem data confiável não estorna automaticamente — dinheiro não sai por chute
        self.assertFalse(self.r.dentro_arrependimento(None, date(2026, 7, 24)))
        self.assertFalse(self.r.dentro_arrependimento("", date(2026, 7, 24)))

    def test_data_malformada_fica_fora(self):
        self.assertFalse(self.r.dentro_arrependimento("ontem", date(2026, 7, 24)))

    def test_data_futura_fica_dentro(self):
        # relógio torto não pode virar negativa de reembolso
        self.assertTrue(self.r.dentro_arrependimento("2026-07-25T10:00:00", date(2026, 7, 24)))

    def test_prazo_configuravel(self):
        self.assertTrue(self.r.dentro_arrependimento("2026-07-24T10:00:00", date(2026, 8, 5), dias=30))


class TestAlvoEstorno(unittest.TestCase):
    def setUp(self):
        import refunds
        self.r = refunds

    def test_pagamento_avulso(self):
        pag = {"id": "pay_123", "value": 997.0}
        self.assertEqual(self.r.alvo_estorno(pag), ("payment", "pay_123"))

    def test_pagamento_parcelado_aponta_pro_parcelamento(self):
        # anual em 12x: estornar só o payment devolveria 1/12 (R$ 83 em vez de R$ 997)
        pag = {"id": "pay_123", "value": 83.08, "installment": "ins_999"}
        self.assertEqual(self.r.alvo_estorno(pag), ("installment", "ins_999"))

    def test_installment_nulo_e_tratado_como_avulso(self):
        pag = {"id": "pay_123", "value": 997.0, "installment": None}
        self.assertEqual(self.r.alvo_estorno(pag), ("payment", "pay_123"))


if __name__ == "__main__":
    unittest.main()
