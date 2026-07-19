"""Testes do email_send.py. Standalone."""
import os
import sys
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestEmail(unittest.TestCase):
    def setUp(self):
        os.environ.pop("RESEND_API_KEY", None)
        os.environ.pop("DSCURSO_EMAIL_BACKEND", None)
        import config, email_send
        importlib.reload(config); importlib.reload(email_send)
        self.cfg, self.e = config, email_send

    def test_payload(self):
        p = self.e._resend_payload("dr@x.com", "Assunto", "<p>oi</p>", "De <a@b.com>")
        self.assertEqual(p["from"], "De <a@b.com>")
        self.assertEqual(p["to"], ["dr@x.com"])
        self.assertEqual(p["subject"], "Assunto")
        self.assertIn("oi", p["html"])

    def test_backend_none_nao_explode(self):
        r = self.e.enviar("dr@x.com", "S", "<p>x</p>")   # sem chave => skipped, sem rede
        self.assertTrue(r.get("skipped"))
        self.assertEqual(self.cfg.EMAIL_BACKEND, "none")


if __name__ == "__main__":
    unittest.main()
