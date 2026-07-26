"""O +1 mês de resgate e a extensão a partir do fim atual, no webhook. Standalone."""
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestBonusResgate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "subscribers", "webhook_asaas"):
            sys.modules.pop(m, None)
        import db, subscribers, webhook_asaas
        db._INITED = False
        db.init()
        self.db, self.subs, self.w = db, subscribers, webhook_asaas

    def _assinante(self, acesso_ate):
        reg = self.subs.criar_de_pagamento(
            {"nome": "T", "whatsapp": "43999990000", "email": "t@e.com", "plano": "anual",
             "cpf": "12345678909"},
            {"payment": "pay_1", "proximo_vencimento": acesso_ate})
        self.subs.marcar_status(reg["id"], "ATIVO", acesso_ate=acesso_ate)
        return reg

    def _pagar(self, valor=1099.0):
        """Pagamento Pix avulso (sem subscription, sem installment) do mesmo CPF."""
        return {"id": "pay_2", "value": valor, "customer": "cus_1",
                "cpfCnpj": "12345678909", "dueDate": date.today().isoformat()}

    def test_recompra_com_acesso_vigente_estende_do_fim_atual_sem_bonus(self):
        fim = (date.today() + timedelta(days=15)).isoformat()
        reg = self._assinante(fim)
        self.w._executar("PAYMENT_CONFIRMED", self._pagar(), "pay_2", lambda w, m: None)
        atual = [s for s in self.subs.listar() if s["id"] == reg["id"]][0]
        esperado = (date.today() + timedelta(days=15 + 365)).isoformat()
        self.assertTrue(atual["acesso_ate"].startswith(esperado))

    def test_recompra_apos_vencer_conta_de_hoje_com_bonus(self):
        fim = (date.today() - timedelta(days=5)).isoformat()
        reg = self._assinante(fim)
        self.w._executar("PAYMENT_CONFIRMED", self._pagar(), "pay_2", lambda w, m: None)
        atual = [s for s in self.subs.listar() if s["id"] == reg["id"]][0]
        esperado = (date.today() + timedelta(days=365 + 30)).isoformat()
        self.assertTrue(atual["acesso_ate"].startswith(esperado))

    def test_primeira_compra_nao_ganha_bonus(self):
        # ninguém existe ainda -> caminho normal de ATIVAR, sem bônus.
        # O ramo ATIVAR de webhook_asaas._executar tem um guard proposital: nunca
        # ativar assinante sem NENHUMA fonte de WhatsApp (produto exige canal de
        # contato). _pagar() sozinho não fornece nenhuma (sem cliente do Asaas
        # mockado, sem pending, sem telefone no payload) — precisa de um pending
        # com whatsapp casado pelo token (externalReference), mesmo padrão de
        # app/tests/test_webhook.py (test_ativar_cria_assinante).
        tok = self.db.criar_pending({"nome": "T", "whatsapp": "43999990000", "email": "t@e.com",
                                     "cpf": "12345678909", "plano": "anual"})
        pay = self._pagar()
        pay["externalReference"] = tok
        self.w._executar("PAYMENT_CONFIRMED", pay, "pay_2", lambda w, m: None)
        novo = self.subs.listar()[0]
        esperado = (date.today() + timedelta(days=365)).isoformat()
        self.assertTrue(novo["acesso_ate"].startswith(esperado))


if __name__ == "__main__":
    unittest.main()
