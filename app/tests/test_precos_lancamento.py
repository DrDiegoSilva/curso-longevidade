"""Preços de lançamento + cupom LANCAMENTO (valor fixo). Standalone."""
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


class TestCupomFixo(unittest.TestCase):
    def setUp(self):
        self.snap = (os.environ.get("DSCURSO_ARTIGOS_DB"), os.environ.get("DATABASE_URL"))
        self.tmp = tempfile.mkdtemp()
        self.db = _reload_db(self.tmp)

    def tearDown(self):
        import shutil, importlib
        a, d = self.snap
        os.environ["DSCURSO_ARTIGOS_DB"] = a if a is not None else ""
        if a is None:
            os.environ.pop("DSCURSO_ARTIGOS_DB", None)
        if d is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = d
        import db as _db
        importlib.reload(_db)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_seed_lancamento_existe(self):
        info = self.db.obter_cupom("LANCAMENTO")
        self.assertIsNotNone(info)
        self.assertEqual(float(info["desconto_valor"]), 500.0)
        self.assertEqual(info["plano_slug"], "anual")
        self.assertEqual(info["uso_unico"], 0)          # multi-uso
        self.assertEqual(info["ativo"], 1)

    def test_cupom_desconto_escopo(self):
        self.assertEqual(self.db.cupom_desconto("LANCAMENTO", "anual"), 500.0)
        self.assertEqual(self.db.cupom_desconto("LANCAMENTO", "mensal"), 0.0)   # fora do escopo
        self.assertEqual(self.db.cupom_desconto("INEXISTENTE", "anual"), 0.0)

    def test_cupom_desconto_ignora_cortesia(self):
        self.db.criar_cupom(codigo="CORTESIA30", dias_acesso=30)               # cortesia, sem desconto_valor
        self.assertEqual(self.db.cupom_desconto("CORTESIA30", "anual"), 0.0)

    def test_cupom_desconto_inativo(self):
        self.db.criar_cupom(codigo="PROMO2", desconto_valor=200, plano_slug="", uso_unico=True)
        self.assertEqual(self.db.cupom_desconto("PROMO2", "anual"), 200.0)     # escopo vazio = qualquer plano
        self.db.consumir_cupom("PROMO2")                                       # uso único -> desativa
        self.assertEqual(self.db.cupom_desconto("PROMO2", "anual"), 0.0)       # inativo -> 0


class TestBaseCobradaFixo(unittest.TestCase):
    def setUp(self):
        import pricing, config
        self.p, self.cfg = pricing, config
        self.anual = self.cfg.plano_por_slug("anual")

    def test_cupom_fixo_cartao(self):
        # 1497 - 500 = 997 (cartão não tem desconto Pix)
        self.assertEqual(self.p.base_cobrada(self.anual, "CARTAO", 1497.0, 0.0, 500.0), 997.0)

    def test_cupom_fixo_pix_empilha(self):
        # 1497 - 500 = 997, depois Pix 5% -> 947.15
        self.assertEqual(self.p.base_cobrada(self.anual, "PIX", 1497.0, 0.0, 500.0), 947.15)

    def test_retrocompat_sem_cupom_valor(self):
        # chamada antiga (4 args) inalterada
        self.assertEqual(self.p.base_cobrada(self.anual, "CARTAO", 1497.0, 0.0), 1497.0)
        self.assertEqual(self.p.base_cobrada(self.anual, "PIX", 1497.0, 0.0), round(1497.0 * 0.95, 2))

    def test_nao_fica_negativo(self):
        self.assertEqual(self.p.base_cobrada(self.anual, "CARTAO", 300.0, 0.0, 500.0), 0.0)
