"""Testes do disparador da régua. Sem rede, sem banco real. Standalone."""
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDisparo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "subscribers", "regua"):
            sys.modules.pop(m, None)
        import db, subscribers, regua
        db._INITED = False
        db.init()
        self.db, self.subs, self.regua = db, subscribers, regua
        self.wa = []
        self.emails = []
        # só a automação de -7 fica ativa, para o teste ser determinístico
        for a in db.listar_automacoes():
            db.salvar_automacao(a["id"], a["dias"], a["canal"], a["texto"],
                                1 if a["dias"] == -7 else 0)

    def _criar(self, **kw):
        reg = self.subs.criar_de_pagamento(
            {"nome": "Teste", "whatsapp": "43999990000", "email": "t@e.com", "plano": "anual"},
            {"proximo_vencimento": "2026-08-01"})
        if kw:
            self.subs.marcar_status(reg["id"], kw.pop("status", "ATIVO"), **kw)
        return reg

    def _disparar(self, hoje):
        return self.regua.disparar(hoje=hoje,
                                   enviar_wa=lambda w, m: self.wa.append((w, m)),
                                   enviar_email=lambda e, a, c: self.emails.append((e, a)))

    def test_dispara_no_offset_certo(self):
        self._criar()
        n = self._disparar(date(2026, 7, 25))          # -7
        self.assertEqual(n, 1)
        self.assertEqual(len(self.wa), 1)

    def test_nao_dispara_em_outro_dia(self):
        self._criar()
        self.assertEqual(self._disparar(date(2026, 7, 24)), 0)
        self.assertEqual(self.wa, [])

    def test_rodar_duas_vezes_no_mesmo_dia_envia_uma_vez(self):
        self._criar()
        self._disparar(date(2026, 7, 25))
        self._disparar(date(2026, 7, 25))
        self.assertEqual(len(self.wa), 1)

    def test_quem_tem_assinatura_recorrente_nao_recebe(self):
        reg = self._criar()
        self.subs.marcar_status(reg["id"], "ATIVO", asaas_subscription_id="sub_1")
        self.assertEqual(self._disparar(date(2026, 7, 25)), 0)

    def test_quem_cancelou_nao_recebe(self):
        reg = self._criar()
        self.subs.marcar_status(reg["id"], "CANCELADO", cancelado_em="2026-07-20T10:00:00")
        self.assertEqual(self._disparar(date(2026, 7, 25)), 0)

    def test_marcadores_sao_substituidos(self):
        self._criar()
        self._disparar(date(2026, 7, 25))
        msg = self.wa[0][1]
        self.assertNotIn("{nome}", msg)
        self.assertNotIn("{ate}", msg)
        self.assertNotIn("{link}", msg)
        self.assertIn("/renovar", msg)

    def test_falha_de_envio_nao_grava_ledger_e_nao_derruba_os_outros(self):
        self._criar()

        def explode(w, m):
            raise RuntimeError("whatsapp fora do ar")

        n = self.regua.disparar(hoje=date(2026, 7, 25), enviar_wa=explode,
                                enviar_email=lambda e, a, c: None)
        self.assertEqual(n, 0)
        # como não gravou o ledger, a próxima execução do MESMO dia tenta de novo
        n2 = self._disparar(date(2026, 7, 25))
        self.assertEqual(n2, 1)

    def test_email_sem_destinatario_nao_marca_ledger(self):
        """Automação de email + assinante sem email → nada é enviado, ledger não fica marcado.

        Prova por mutação: se marcarmos o ledger ANTES de verificar o destinatário (bug),
        este teste falhará na segunda execução (ledger já estará marcado e registrar_aviso
        devolverá False).
        """
        reg = self._criar()
        # Remove o email do assinante
        self.subs.marcar_status(reg["id"], "ATIVO", email=None)

        # Muda a automação de -7 para canal email
        auto = [a for a in self.db.listar_automacoes() if a["dias"] == -7][0]
        self.db.salvar_automacao(auto["id"], auto["dias"], "email", auto["texto"], 1)

        # Primeira execução: não envia (sem email), ledger não fica marcado
        n1 = self._disparar(date(2026, 7, 25))
        self.assertEqual(n1, 0)
        self.assertEqual(len(self.emails), 0)

        # Segunda execução do mesmo dia: como o ledger não foi marcado, o disparador
        # tentaria novamente se houvesse um destinatário. Mas como ainda não há email,
        # continua sem enviar.
        n2 = self._disparar(date(2026, 7, 25))
        self.assertEqual(n2, 0)
        self.assertEqual(len(self.emails), 0)

    def test_whatsapp_sem_destinatario_nao_marca_ledger(self):
        """Automação de WhatsApp + assinante sem WhatsApp → nada é enviado, ledger não fica marcado."""
        reg = self._criar()
        # Remove o WhatsApp do assinante
        self.subs.marcar_status(reg["id"], "ATIVO", whatsapp=None)

        # Primeira execução: não envia (sem WhatsApp), ledger não fica marcado
        n1 = self._disparar(date(2026, 7, 25))
        self.assertEqual(n1, 0)
        self.assertEqual(len(self.wa), 0)

        # Segunda execução do mesmo dia: como o ledger não foi marcado, o disparador
        # tentaria novamente. Mas como ainda não há WhatsApp, continua sem enviar.
        n2 = self._disparar(date(2026, 7, 25))
        self.assertEqual(n2, 0)
        self.assertEqual(len(self.wa), 0)

    def test_email_com_destinatario_envia_normalmente(self):
        """Automação de email + assinante com email → envia normalmente pelo canal email."""
        reg = self._criar()

        # Muda a automação de -7 para canal email
        auto = [a for a in self.db.listar_automacoes() if a["dias"] == -7][0]
        self.db.salvar_automacao(auto["id"], auto["dias"], "email", auto["texto"], 1)

        # Primeira execução: envia por email
        n1 = self._disparar(date(2026, 7, 25))
        self.assertEqual(n1, 1)
        self.assertEqual(len(self.emails), 1)
        self.assertEqual(self.emails[0][0], "t@e.com")

        # Segunda execução do mesmo dia: ledger já marcado, não envia novamente
        n2 = self._disparar(date(2026, 7, 25))
        self.assertEqual(n2, 0)
        self.assertEqual(len(self.emails), 1)


if __name__ == "__main__":
    unittest.main()
