"""Testes do subscribers.py (SQLite + tem_acesso). Standalone."""
import os
import sys
import json
import tempfile
import importlib
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestSubs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        for m in ("config", "db", "subscribers"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, subscribers
        importlib.reload(config); importlib.reload(db); importlib.reload(subscribers)
        self.s = subscribers
        self.s._migrado = False
        db.init()

    def _fut(self, dias=1):
        return (datetime.now() + timedelta(days=dias)).isoformat()

    def _pass(self, dias=1):
        return (datetime.now() - timedelta(days=dias)).isoformat()

    def test_tem_acesso(self):
        t = self.s.tem_acesso
        self.assertTrue(t({"status": "ATIVO"}))
        self.assertTrue(t({"status": "INADIMPLENTE", "carencia_ate": self._fut()}))
        self.assertFalse(t({"status": "INADIMPLENTE", "carencia_ate": self._pass()}))
        self.assertTrue(t({"status": "CANCELADO", "acesso_ate": self._fut()}))
        self.assertFalse(t({"status": "CANCELADO", "acesso_ate": self._pass()}))
        self.assertFalse(t({"status": "CANCELADO"}))
        self.assertFalse(t({"status": "OUTRO"}))

    def test_adicionar_e_ativos(self):
        self.s.adicionar("Dr. A", "55 43 99999-0000")
        atv = self.s.ativos()
        self.assertEqual(len(atv), 1)
        self.assertEqual(atv[0]["whatsapp"], "5543999990000")

    def test_criar_de_pagamento_e_status(self):
        reg = self.s.criar_de_pagamento(
            {"nome": "Dr. B", "whatsapp": "5543", "email": "b@x.com", "plano": "anual"},
            {"customer": "cus_1", "subscription": "sub_1", "proximo_vencimento": self._fut(365)})
        self.assertEqual(self.s.por_subscription("sub_1")["email"], "b@x.com")
        self.s.marcar_status(reg["id"], "INADIMPLENTE", carencia_ate=self._fut())
        self.assertTrue(self.s.tem_acesso(self.s.listar()[0]))
        self.s.registrar_cancelamento(reg["id"], "caro demais", acesso_ate=self._pass())
        self.assertEqual(self.s.ativos(), [])

    def test_migra_json(self):
        # grava JSON e força nova migração
        with open(os.path.join(self.tmp, "subscribers.json"), "w", encoding="utf-8") as f:
            json.dump([{"id": "x", "nome": "Velho", "whatsapp": "5543111", "status": "ATIVO"}], f)
        self.s._migrado = False
        self.assertEqual(len(self.s.listar()), 1)
        self.assertEqual(self.s.listar()[0]["nome"], "Velho")


if __name__ == "__main__":
    unittest.main()
