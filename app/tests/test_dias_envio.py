"""Testes do _dias_envio (override editável via db.settings). Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDiasEnvio(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        for m in ("config", "db", "daily"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, daily
        importlib.reload(config); importlib.reload(db); importlib.reload(daily)
        self.db, self.daily = db, daily
        db.init()

    def test_default_do_config(self):
        # sem override no banco -> usa o temas_config.json
        esperado = set(self.daily._cfg().get("dias_envio", ["segunda", "terca", "quarta", "quinta", "sexta"]))
        self.assertEqual(self.daily._dias_envio(), esperado)

    def test_override_settings(self):
        self.db.set_config("dias_envio", "segunda,domingo")
        self.assertEqual(self.daily._dias_envio(), {"segunda", "domingo"})

    def test_override_vazio_zero_dias(self):
        self.db.set_config("dias_envio", "")   # salvou sem nenhum dia -> não envia em nenhum
        self.assertEqual(self.daily._dias_envio(), set())


if __name__ == "__main__":
    unittest.main()
