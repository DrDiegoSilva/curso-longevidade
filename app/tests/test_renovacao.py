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

    def _sub(self, valor_contratado=None):
        """Assinante DO MESMO plano de PLANO — `valor_contratado` só vale para o plano em
        que foi contratado (B3 da revisão final #2), então sem o `plano` aqui todos os
        testes abaixo cairiam no preço de tabela por outro motivo e não provariam nada."""
        return {"plano": PLANO["slug"], "valor_contratado": valor_contratado}

    def test_usa_o_valor_contratado_quando_existe(self):
        # founder que entrou a 997 renova a 997, mesmo com a tabela já em 1099.
        # (valor != base de propósito: com 1099 os dois caminhos dariam o mesmo número
        # e o teste passaria mesmo se `valor_contratado` fosse ignorado.)
        self.assertEqual(self.r.preco_renovacao(self._sub(997.0), PLANO), 997.0)

    def test_valor_contratado_diferente_do_base_e_respeitado(self):
        self.assertEqual(self.r.preco_renovacao(self._sub(897.30), PLANO), 897.30)

    def test_sem_valor_contratado_cai_no_base_do_plano(self):
        # base atual de assinantes foi criada antes da coluna existir
        self.assertEqual(self.r.preco_renovacao({"plano": PLANO["slug"]}, PLANO), 1099.0)
        self.assertEqual(self.r.preco_renovacao(self._sub(None), PLANO), 1099.0)
        self.assertEqual(self.r.preco_renovacao(self._sub(0), PLANO), 1099.0)

    def test_valor_contratado_invalido_cai_no_base(self):
        self.assertEqual(self.r.preco_renovacao(self._sub("abc"), PLANO), 1099.0)

    def test_valor_contratado_negativo_cai_no_base(self):
        # trava o `> 0`: um refactor para `!= 0` cobraria valor negativo de verdade
        self.assertEqual(self.r.preco_renovacao(self._sub(-100.0), PLANO), 1099.0)

    def test_valor_nao_finito_cai_no_base(self):
        # float() aceita "inf"/"nan" caladamente, e infinito passaria por um teste ingênuo de > 0
        self.assertEqual(self.r.preco_renovacao(self._sub("inf"), PLANO), 1099.0)
        self.assertEqual(self.r.preco_renovacao(self._sub(float("inf")), PLANO), 1099.0)
        self.assertEqual(self.r.preco_renovacao(self._sub(float("nan")), PLANO), 1099.0)

    def test_sem_valor_contratado_usa_base_padrao_imune_ao_override_admin(self):
        # legado (sem valor_contratado) + plano com override do admin (base=1600, tabela
        # subiu) -> tem que cair no base_padrao (preço de lançamento, 1497), NUNCA no base
        # (preço atual de tabela) — senão o admin subindo o preço vaza pra renovação de
        # quem já era assinante.
        plano_com_override = {"slug": "anual", "base": 1600.0, "base_padrao": 1497.0}
        sub = {"plano": "anual"}  # sem valor_contratado = legado
        self.assertEqual(self.r.preco_renovacao(sub, plano_com_override), 1497.0)

    def test_plano_sem_base_padrao_cai_no_base_back_compat(self):
        # chamador/teste antigo que monta um plano à mão sem base_padrao continua
        # funcionando: o .get(..., base) segura a barra
        plano_sem_base_padrao = {"slug": "anual", "base": 1099.0}
        sub = {"plano": "anual"}
        self.assertEqual(self.r.preco_renovacao(sub, plano_sem_base_padrao), 1099.0)


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
