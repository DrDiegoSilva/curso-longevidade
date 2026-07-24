"""Testes do horário de envio por assinante (slots). Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestSlotBasico(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        for m in ("config", "db", "subscribers"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, subscribers
        importlib.reload(config); importlib.reload(db); importlib.reload(subscribers)
        self.cfg, self.db, self.s = config, db, subscribers
        self.s._migrado = False
        db.init()

    def test_slot_de_default(self):
        self.assertEqual(self.s.slot_de({}), self.cfg.SLOT_DEFAULT)
        self.assertEqual(self.s.slot_de({"slot_envio": None}), self.cfg.SLOT_DEFAULT)
        self.assertEqual(self.s.slot_de({"slot_envio": "xx"}), self.cfg.SLOT_DEFAULT)  # inválido
        self.assertEqual(self.s.slot_de({"slot_envio": "12h"}), "12h")

    def test_definir_slot(self):
        reg = self.s.adicionar("Fulano", "5543999990000")
        self.s.definir_slot(reg["id"], "18h")
        self.assertEqual(self.s.por_id(reg["id"])["slot_envio"], "18h")
        self.s.definir_slot(reg["id"], "zz")   # inválido -> não muda
        self.assertEqual(self.s.por_id(reg["id"])["slot_envio"], "18h")


if __name__ == "__main__":
    unittest.main()
