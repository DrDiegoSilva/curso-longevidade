import os, sys, unittest, tempfile
from datetime import date
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

class TestVarreduraSemanal(unittest.TestCase):
    def setUp(self):   # padrão do repo (ver test_agenda_materializar.py)
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ.pop("DATABASE_URL", None)
        import importlib, config as _cfg; importlib.reload(_cfg)
        import db as _db; importlib.reload(_db)
        _db.init()
        self.calls = []

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_roda_domingo_uma_vez(self):
        import daily
        domingo = date(2026, 7, 26)     # 2026-07-26 é domingo
        r1 = daily.varredura_semanal(hoje=domingo, rodar_fn=lambda: self.calls.append(1) or 3)
        r2 = daily.varredura_semanal(hoje=domingo, rodar_fn=lambda: self.calls.append(1) or 3)
        self.assertTrue(r1); self.assertFalse(r2)       # idempotente na mesma semana
        self.assertEqual(len(self.calls), 1)

    def test_nao_roda_fora_de_domingo(self):
        import daily
        segunda = date(2026, 7, 27)
        r = daily.varredura_semanal(hoje=segunda, rodar_fn=lambda: self.calls.append(1))
        self.assertFalse(r); self.assertEqual(self.calls, [])
