"""Testes do webhook Asaas (decidir puro + processar). Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDecidir(unittest.TestCase):
    def setUp(self):
        import webhook_asaas
        self.w = webhook_asaas

    def test_matriz(self):
        self.assertEqual(self.w.decidir("PAYMENT_CONFIRMED", False), "ATIVAR")
        self.assertEqual(self.w.decidir("PAYMENT_RECEIVED", True), "RENOVAR")
        self.assertEqual(self.w.decidir("PAYMENT_OVERDUE", True), "INADIMPLENTE")
        self.assertEqual(self.w.decidir("PAYMENT_REFUNDED", True), "SUSPENDER")
        self.assertEqual(self.w.decidir("PAYMENT_DELETED", True), "SUSPENDER")
        self.assertEqual(self.w.decidir("PAYMENT_CREATED", False), "IGNORAR")


class TestProcessar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["ASAAS_WEBHOOK_TOKEN"] = "segredo"
        for m in ("config", "db", "subscribers", "webhook_asaas"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, subscribers, webhook_asaas
        for mod in (config, db, subscribers, webhook_asaas):
            importlib.reload(mod)
        self.cfg, self.db, self.s, self.w = config, db, subscribers, webhook_asaas
        self.s._migrado = False
        db.init()
        self.enviados = []
        self.envfn = lambda wpp, msg: self.enviados.append((wpp, msg))

    def _body(self, event="PAYMENT_CONFIRMED", ext="tok", pid="pay_1", sub=None):
        return {"event": event, "payment": {"id": pid, "externalReference": ext,
                "customer": "cus_1", "subscription": sub, "dueDate": "2026-07-19"}}

    def test_token_invalido(self):
        st, _ = self.w.processar(self._body(), "errado", enviar_fn=self.envfn)
        self.assertEqual(st, 401)

    def test_ativar_cria_assinante(self):
        tok = self.db.criar_pending({"nome": "Dr. A", "whatsapp": "5543999990000",
                                     "email": "a@x.com", "plano": "anual", "metodo": "CARTAO"})
        st, msg = self.w.processar(self._body(ext=tok), "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "ativado"))
        self.assertEqual(len(self.s.ativos()), 1)
        self.assertEqual(len(self.enviados), 1)      # boas-vindas

    def test_idempotente(self):
        tok = self.db.criar_pending({"nome": "Dr. A", "whatsapp": "5543", "plano": "mensal"})
        self.w.processar(self._body(ext=tok), "segredo", enviar_fn=self.envfn)
        st, msg = self.w.processar(self._body(ext=tok), "segredo", enviar_fn=self.envfn)
        self.assertEqual(msg, "duplicado")
        self.assertEqual(len(self.s.listar()), 1)    # não duplicou

    def test_inadimplente_e_renova(self):
        reg = self.s.criar_de_pagamento({"nome": "B", "whatsapp": "5543", "plano": "mensal"},
                                         {"subscription": "sub_9"})
        self.w.processar(self._body(event="PAYMENT_OVERDUE", pid="p2", sub="sub_9"), "segredo", enviar_fn=self.envfn)
        self.assertEqual(self.s.por_subscription("sub_9")["status"], "INADIMPLENTE")
        self.w.processar(self._body(event="PAYMENT_RECEIVED", pid="p3", sub="sub_9"), "segredo", enviar_fn=self.envfn)
        self.assertEqual(self.s.por_subscription("sub_9")["status"], "ATIVO")

    def _body_valor(self, event="PAYMENT_CONFIRMED", ext="tok", pid="pay_af", value=897.30, sub=None):
        return {"event": event, "payment": {"id": pid, "externalReference": ext, "value": value,
                "customer": "cus_af", "subscription": sub, "dueDate": "2026-07-19"}}

    def test_ativar_com_afiliado_registra_comissao(self):
        self.db.criar_afiliado("Dra. Maria", "", "dramaria", 10, 3)
        tok = self.db.criar_pending({"nome": "Dr. Novo", "whatsapp": "5543999991111",
                                     "email": "n@x.com", "plano": "anual", "metodo": "PIX",
                                     "afiliado_codigo": "DRAMARIA", "valor": 897.30})
        st, msg = self.w.processar(self._body_valor(ext=tok), "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "ativado"))
        comis = self.db.listar_comissoes()
        self.assertEqual(len(comis), 1)
        self.assertAlmostEqual(comis[0]["valor_venda"], 897.30, places=2)
        self.assertAlmostEqual(comis[0]["valor_comissao"], 26.92, places=2)  # 3% de 897.30

    def test_renovar_nao_registra_comissao(self):
        reg = self.s.criar_de_pagamento({"nome": "B", "whatsapp": "5543", "plano": "mensal"},
                                         {"subscription": "sub_af"})
        self.w.processar(self._body_valor(event="PAYMENT_RECEIVED", pid="pr1", sub="sub_af"),
                         "segredo", enviar_fn=self.envfn)
        self.assertEqual(self.db.listar_comissoes(), [])

    def test_ativar_afiliado_comissao_falha_alerta_admin(self):
        # se registrar_comissao falhar: ativação segue, comissão não entra, admin é avisado.
        self.db.criar_afiliado("Dra. Maria", "", "dramaria", 10, 3)
        tok = self.db.criar_pending({"nome": "Dr. N", "whatsapp": "5543999992222",
                                     "email": "n@x.com", "plano": "anual", "metodo": "PIX",
                                     "afiliado_codigo": "DRAMARIA", "valor": 897.30})
        alertas = []
        orig_reg, orig_alert = self.db.registrar_comissao, self.w._alertar_admin
        self.db.registrar_comissao = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down"))
        self.w._alertar_admin = lambda pid, sid, motivo: alertas.append(motivo)
        try:
            st, msg = self.w.processar(self._body_valor(ext=tok), "segredo", enviar_fn=self.envfn)
        finally:
            self.db.registrar_comissao, self.w._alertar_admin = orig_reg, orig_alert
        self.assertEqual((st, msg), (200, "ativado"))       # ativação não quebra
        self.assertEqual(self.db.listar_comissoes(), [])    # comissão não entrou
        self.assertTrue(any("comissão" in m for m in alertas))  # admin avisado


class TestAvisarVenda(unittest.TestCase):
    def test_avisar_venda_monta_email(self):
        import webhook_asaas, email_send
        chamado = {}
        orig = email_send.enviar
        email_send.enviar = lambda to, assunto, html: chamado.update(to=to, assunto=assunto, html=html)
        try:
            webhook_asaas._avisar_venda("Fulano", "Anual", "960", "f@x.com", 37)
        finally:
            email_send.enviar = orig
        self.assertIn("Anual", chamado["assunto"])
        self.assertIn("Fulano", chamado["html"])
        self.assertIn("37", chamado["html"])

    def test_avisar_venda_com_afiliado_mostra_comissao(self):
        import webhook_asaas, email_send
        chamado = {}
        orig = email_send.enviar
        email_send.enviar = lambda to, assunto, html: chamado.update(to=to, assunto=assunto, html=html)
        try:
            webhook_asaas._avisar_venda("Fulano", "Anual", "960", "f@x.com", 37,
                                        afiliado="Dra. Maria", comissao=26.92)
        finally:
            email_send.enviar = orig
        self.assertIn("Dra. Maria", chamado["html"])
        self.assertIn("26.92", chamado["html"])

    def test_avisar_venda_afiliado_sem_comissao_nao_mostra_valor(self):
        import webhook_asaas, email_send
        chamado = {}
        orig = email_send.enviar
        email_send.enviar = lambda to, assunto, html: chamado.update(html=html)
        try:
            webhook_asaas._avisar_venda("Fulano", "Anual", "897.30", "x", 1,
                                        afiliado="Dra. Maria", comissao=None)
        finally:
            email_send.enviar = orig
        self.assertIn("Dra. Maria", chamado["html"])       # afiliado ainda aparece
        self.assertNotIn("R$ None", chamado["html"])       # mas sem valor de comissão fantasma

    def test_avisar_venda_nao_propaga_erro(self):
        import webhook_asaas, email_send
        orig = email_send.enviar
        email_send.enviar = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("smtp down"))
        try:
            webhook_asaas._avisar_venda("F", "Mensal", "99", "x", 1)  # não pode levantar
        finally:
            email_send.enviar = orig


if __name__ == "__main__":
    unittest.main()
