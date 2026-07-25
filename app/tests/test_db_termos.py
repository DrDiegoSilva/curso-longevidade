"""Testes das colunas de aceite dos termos e da reversão de comissão. Standalone."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestTermosDB(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "subscribers"):
            sys.modules.pop(m, None)
        import db
        self.db = db
        db._INITED = False
        db.init()

    def test_colunas_de_termos_existem(self):
        with self.db._conn() as c:
            cols = [r[1] for r in c.execute("PRAGMA table_info(subscribers)").fetchall()]
        for col in ("termos_versao", "termos_aceito_em", "termos_ip"):
            self.assertIn(col, cols)

    def test_coluna_estornada_em_existe(self):
        with self.db._conn() as c:
            cols = [r[1] for r in c.execute("PRAGMA table_info(comissoes)").fetchall()]
        self.assertIn("estornada_em", cols)

    def test_estornar_comissao_marca_a_comissao_do_assinante(self):
        self.db.registrar_comissao("af1", "sub1", "anual", 997.0, 29.91)
        n = self.db.estornar_comissao("sub1")
        self.assertEqual(n, 1)
        com = [c for c in self.db.listar_comissoes() if c["subscriber_id"] == "sub1"][0]
        self.assertTrue(com["estornada_em"])

    def test_estornar_comissao_de_assinante_sem_comissao_devolve_zero(self):
        self.assertEqual(self.db.estornar_comissao("nao-existe"), 0)


if __name__ == "__main__":
    unittest.main()
