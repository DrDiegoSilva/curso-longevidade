"""Admin de preços editáveis (resolver + página + rotas). Standalone."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _reload_db(tmp):
    os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(tmp, "t.db")
    os.environ.pop("DATABASE_URL", None)
    import importlib, db as _db
    importlib.reload(_db)
    _db.init()
    return _db


def _snapshot_env():
    return (os.environ.get("DSCURSO_ARTIGOS_DB"), os.environ.get("DATABASE_URL"))


def _restore_db(snap):
    import importlib
    a, d = snap
    if a is None:
        os.environ.pop("DSCURSO_ARTIGOS_DB", None)
    else:
        os.environ["DSCURSO_ARTIGOS_DB"] = a
    if d is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = d
    import db as _db
    importlib.reload(_db)


class TestParsePreco(unittest.TestCase):
    def test_valido(self):
        import config
        self.assertEqual(config.parse_preco("1600"), 1600.0)
        self.assertEqual(config.parse_preco("1600,50"), 1600.5)
        self.assertEqual(config.parse_preco(" 1497.00 "), 1497.0)

    def test_invalido(self):
        import config
        for bad in ("", "0", "-5", "abc", None, "1.2.3"):
            self.assertIsNone(config.parse_preco(bad))


class TestPrecoResolver(unittest.TestCase):
    def setUp(self):
        self.snap = _snapshot_env()
        self.tmp = tempfile.mkdtemp()
        self.db = _reload_db(self.tmp)
        import importlib, config
        importlib.reload(config)
        self.cfg = config

    def tearDown(self):
        import shutil
        _restore_db(self.snap)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sem_override_usa_default(self):
        pl = self.cfg.plano_por_slug("anual")
        self.assertEqual(pl["base"], 1497.0)
        self.assertEqual(pl["preco"], "R$ 1.497")

    def test_override_aplica_e_deriva(self):
        self.db.set_config("preco_base_anual", "1600")
        pl = self.cfg.plano_por_slug("anual")
        self.assertEqual(pl["base"], 1600.0)
        self.assertEqual(pl["base_pos"], 1600.0)
        self.assertEqual(pl["preco"], "R$ 1.600")
        self.assertEqual(pl["nota"], "≈ R$ 133/mês · em até 12x sem juros")   # round(1600/12)=133
        mensal = self.cfg.plano_por_slug("mensal")
        self.db.set_config("preco_base_mensal", "159")
        mensal = self.cfg.plano_por_slug("mensal")
        self.assertEqual(mensal["base"], 159.0)
        self.assertEqual(mensal["preco"], "R$ 159")
        self.assertEqual(mensal["nota"], "")

    def test_override_nao_muta_PLANOS(self):
        self.db.set_config("preco_base_anual", "1600")
        self.cfg.plano_por_slug("anual")
        cru = next(p for p in self.cfg.PLANOS if p["slug"] == "anual")
        self.assertEqual(cru["base"], 1497.0)                # PLANOS intacto

    def test_planos_venda_aplica_override(self):
        self.db.set_config("preco_base_anual", "1600")
        venda = {p["slug"]: p for p in self.cfg.planos_venda()}
        self.assertNotIn("teste", venda)                     # ocultos fora
        self.assertEqual(venda["anual"]["base"], 1600.0)

    def test_plano_por_base_enxerga_override(self):
        self.db.set_config("preco_base_anual", "1600")
        self.assertEqual(self.cfg.plano_por_base(1600.0)["slug"], "anual")
