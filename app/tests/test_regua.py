"""Testes das regras puras da régua de renovação. Standalone."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ANUAL = {"slug": "anual", "cycle": "YEARLY"}
MENSAL = {"slug": "mensal", "cycle": "MONTHLY"}


def _sub(**kw):
    base = {"id": "s1", "asaas_subscription_id": None, "cancelado_em": None,
            "proximo_vencimento": "2026-08-01"}
    base.update(kw)
    return base


class TestOffsetVencimento(unittest.TestCase):
    def setUp(self):
        import regua
        self.r = regua

    def test_faltando_sete_dias_da_menos_sete(self):
        self.assertEqual(self.r.offset_vencimento("2026-08-01", date(2026, 7, 25)), -7)

    def test_no_dia_do_vencimento_da_zero(self):
        self.assertEqual(self.r.offset_vencimento("2026-08-01", date(2026, 8, 1)), 0)

    def test_vencido_ha_quinze_dias_da_mais_quinze(self):
        self.assertEqual(self.r.offset_vencimento("2026-08-01", date(2026, 8, 16)), 15)

    def test_aceita_iso_com_hora(self):
        self.assertEqual(self.r.offset_vencimento("2026-08-01T10:30:00", date(2026, 8, 1)), 0)

    def test_data_ausente_ou_malformada_da_none(self):
        # None mantém o assinante fora da régua em vez de mandar mensagem errada
        self.assertIsNone(self.r.offset_vencimento(None, date(2026, 8, 1)))
        self.assertIsNone(self.r.offset_vencimento("", date(2026, 8, 1)))
        self.assertIsNone(self.r.offset_vencimento("amanhã", date(2026, 8, 1)))


class TestNaRegua(unittest.TestCase):
    def setUp(self):
        import regua
        self.r = regua

    def test_anual_sem_assinatura_recorrente_entra(self):
        # Pix e cartão parcelado não criam subscription no Asaas -> não renovam sozinhos
        self.assertTrue(self.r.na_regua(_sub(), ANUAL))

    def test_anual_com_assinatura_recorrente_fica_fora(self):
        # cartão à vista renova sozinho, não precisa ser avisado
        self.assertFalse(self.r.na_regua(_sub(asaas_subscription_id="sub_1"), ANUAL))

    def test_mensal_fica_fora(self):
        # mensal só existe no cartão, e cartão mensal renova sozinho
        self.assertFalse(self.r.na_regua(_sub(), MENSAL))

    def test_quem_cancelou_a_renovacao_fica_fora(self):
        # ele já comunicou que quer sair; insistir no WhatsApp gera bloqueio
        self.assertFalse(self.r.na_regua(_sub(cancelado_em="2026-07-20T10:00:00"), ANUAL))

    def test_plano_ausente_fica_fora(self):
        self.assertFalse(self.r.na_regua(_sub(), {}))
        self.assertFalse(self.r.na_regua(_sub(), None))


class TestAutomacoesDoDia(unittest.TestCase):
    def setUp(self):
        import regua
        self.r = regua
        self.autos = [
            {"id": "a1", "dias": -7, "ativo": 1, "canal": "whatsapp", "texto": "x"},
            {"id": "a2", "dias": -3, "ativo": 1, "canal": "whatsapp", "texto": "x"},
            {"id": "a3", "dias": -3, "ativo": 0, "canal": "whatsapp", "texto": "x"},
        ]

    def test_casa_apenas_o_offset_exato(self):
        r = self.r.automacoes_do_dia(self.autos, -7)
        self.assertEqual([a["id"] for a in r], ["a1"])

    def test_automacao_inativa_nao_dispara(self):
        r = self.r.automacoes_do_dia(self.autos, -3)
        self.assertEqual([a["id"] for a in r], ["a2"])

    def test_offset_sem_automacao_devolve_vazio(self):
        self.assertEqual(self.r.automacoes_do_dia(self.autos, -99), [])

    def test_offset_none_devolve_vazio(self):
        self.assertEqual(self.r.automacoes_do_dia(self.autos, None), [])


if __name__ == "__main__":
    unittest.main()
