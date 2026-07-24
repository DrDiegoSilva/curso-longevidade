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

    def test_registrar_envio_slot_idempotente(self):
        self.assertTrue(self.db.registrar_envio_slot("2026-07-24", "08h"))    # 1ª vez
        self.assertFalse(self.db.registrar_envio_slot("2026-07-24", "08h"))   # repetido
        self.assertTrue(self.db.registrar_envio_slot("2026-07-24", "12h"))    # outro slot
        self.assertTrue(self.db.registrar_envio_slot("2026-07-25", "08h"))    # outro dia


class TestVaga(unittest.TestCase):
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

    def test_contar_por_slot_default(self):
        a = self.s.adicionar("A", "5543000000001")   # sem slot -> 08h
        self.s.definir_slot(self.s.adicionar("B", "5543000000002")["id"], "12h")
        cont = self.s.contar_por_slot()
        self.assertEqual(cont["08h"], 1)
        self.assertEqual(cont["12h"], 1)
        self.assertEqual(cont["20h"], 0)

    def test_slots_com_vaga_esconde_cheio_mas_mantem_atual(self):
        for i in range(3):
            self.s.definir_slot(self.s.adicionar(f"C{i}", f"554300001000{i}")["id"], "07h")
        vaga = self.s.slots_com_vaga(teto=3)          # 07h cheio (3/3)
        self.assertNotIn("07h", vaga)
        self.assertIn("08h", vaga)
        # mesmo cheio, o slot_atual do assinante é ofertado (pra ele manter)
        vaga2 = self.s.slots_com_vaga(teto=3, slot_atual="07h")
        self.assertIn("07h", vaga2)
        self.assertEqual(vaga2, [s for s in self.cfg.SLOTS if s in vaga2])  # ordem preservada


if __name__ == "__main__":
    unittest.main()
