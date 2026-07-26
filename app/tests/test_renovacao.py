"""Testes de preço e datas da renovação. Standalone."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PLANO = {"slug": "anual", "cycle": "YEARLY", "base": 1099.0}


class TestPrecoRenovacao(unittest.TestCase):
    def setUp(self):
        import renovacao
        self.r = renovacao

    def test_usa_o_valor_contratado_quando_existe(self):
        # founder que entrou a 1099 renova a 1099, mesmo se a tabela já subiu
        self.assertEqual(self.r.preco_renovacao({"valor_contratado": 1099.0}, PLANO), 1099.0)

    def test_valor_contratado_diferente_do_base_e_respeitado(self):
        self.assertEqual(self.r.preco_renovacao({"valor_contratado": 897.30}, PLANO), 897.30)

    def test_sem_valor_contratado_cai_no_base_do_plano(self):
        # base atual de assinantes foi criada antes da coluna existir
        self.assertEqual(self.r.preco_renovacao({}, PLANO), 1099.0)
        self.assertEqual(self.r.preco_renovacao({"valor_contratado": None}, PLANO), 1099.0)
        self.assertEqual(self.r.preco_renovacao({"valor_contratado": 0}, PLANO), 1099.0)

    def test_valor_contratado_invalido_cai_no_base(self):
        self.assertEqual(self.r.preco_renovacao({"valor_contratado": "abc"}, PLANO), 1099.0)

    def test_valor_contratado_negativo_cai_no_base(self):
        # trava o `> 0`: um refactor para `!= 0` cobraria valor negativo de verdade
        self.assertEqual(self.r.preco_renovacao({"valor_contratado": -100.0}, PLANO), 1099.0)

    def test_valor_nao_finito_cai_no_base(self):
        # float() aceita "inf"/"nan" caladamente, e infinito passaria por um teste ingênuo de > 0
        self.assertEqual(self.r.preco_renovacao({"valor_contratado": "inf"}, PLANO), 1099.0)
        self.assertEqual(self.r.preco_renovacao({"valor_contratado": float("inf")}, PLANO), 1099.0)
        self.assertEqual(self.r.preco_renovacao({"valor_contratado": float("nan")}, PLANO), 1099.0)


class TestNovoVencimento(unittest.TestCase):
    def setUp(self):
        import renovacao
        self.r = renovacao

    def test_com_acesso_vigente_estende_do_fim_atual(self):
        # renovou faltando 15 dias -> não pode perder esses 15 dias
        novo = self.r.novo_vencimento("2026-08-01", date(2026, 7, 17), 365)
        self.assertEqual(novo, date(2027, 8, 1))

    def test_no_dia_do_vencimento_ainda_conta_como_acesso_vigente(self):
        novo = self.r.novo_vencimento("2026-08-01", date(2026, 8, 1), 365)
        self.assertEqual(novo, date(2027, 8, 1))

    def test_no_dia_do_vencimento_nao_ganha_bonus(self):
        novo = self.r.novo_vencimento("2026-08-01", date(2026, 8, 1), 365, bonus_dias=30)
        self.assertEqual(novo, date(2027, 8, 1))

    def test_expirado_conta_de_hoje(self):
        novo = self.r.novo_vencimento("2026-08-01", date(2026, 8, 10), 365)
        self.assertEqual(novo, date(2027, 8, 10))

    def test_expirado_ganha_o_bonus(self):
        # +1 mês de resgate: só para quem já tinha perdido o acesso
        novo = self.r.novo_vencimento("2026-08-01", date(2026, 8, 10), 365, bonus_dias=30)
        self.assertEqual(novo, date(2027, 9, 9))

    def test_sem_data_de_acesso_conta_de_hoje_com_bonus(self):
        novo = self.r.novo_vencimento(None, date(2026, 8, 10), 365, bonus_dias=30)
        self.assertEqual(novo, date(2027, 9, 9))

    def test_data_malformada_conta_de_hoje(self):
        novo = self.r.novo_vencimento("ontem", date(2026, 8, 10), 365)
        self.assertEqual(novo, date(2027, 8, 10))


class TestCicloDias(unittest.TestCase):
    def test_mapa_publico_cobre_os_ciclos_dos_planos(self):
        import renovacao, config
        for p in config.PLANOS:
            self.assertIn(p["cycle"], renovacao.CICLO_DIAS)

    def test_webhook_usa_o_mesmo_mapa(self):
        # sem duplicar a constante em dois arquivos
        import renovacao, webhook_asaas
        self.assertIs(webhook_asaas._CICLO_DIAS, renovacao.CICLO_DIAS)


if __name__ == "__main__":
    unittest.main()
