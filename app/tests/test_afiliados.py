"""Testes de afiliados/comissões (db). Standalone: python3 app/tests/test_afiliados.py"""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAfiliadosDb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import db as _db
        importlib.reload(_db)
        self.db = _db
        self.db.init()

    def test_criar_e_por_codigo(self):
        cod = self.db.criar_afiliado("Dra. Maria", "maria@x.com", "dramaria", 10, 3)
        self.assertEqual(cod, "DRAMARIA")
        af = self.db.afiliado_por_codigo("dramaria")            # case-insensitive
        self.assertIsNotNone(af)
        self.assertEqual(af["nome"], "Dra. Maria")
        self.assertEqual(af["pct_desconto"], 10)
        self.assertEqual(af["pct_comissao"], 3)
        self.assertEqual(self.db.afiliado_por_codigo("naoexiste"), None)

    def test_toggle_desativa(self):
        self.db.criar_afiliado("M", "", "codX")
        af = self.db.afiliado_por_codigo("codx")
        self.db.toggle_afiliado(af["id"], False)
        self.assertIsNone(self.db.afiliado_por_codigo("codx"))  # inativo some da consulta
        self.db.toggle_afiliado(af["id"], True)
        self.assertIsNotNone(self.db.afiliado_por_codigo("codx"))


if __name__ == "__main__":
    unittest.main()
