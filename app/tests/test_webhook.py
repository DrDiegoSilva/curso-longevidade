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
