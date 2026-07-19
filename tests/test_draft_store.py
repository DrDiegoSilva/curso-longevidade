import sys, os, tempfile, unittest, importlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


class TestDraftStore(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.d
        import config
        importlib.reload(config)
        import draft_store
        importlib.reload(draft_store)
        self.ds = draft_store

    def test_ciclo_criar_salvar_carregar_por_token(self):
        r = self.ds.novo_rascunho("2026-07-18", {"titulo": "T"}, "resumo", "/data/x.pdf")
        self.assertEqual(r["status"], "DRAFT")
        self.assertTrue(len(r["review_token"]) >= 20)
        self.ds.salvar(r)
        self.assertEqual(self.ds.carregar("2026-07-18")["artigo"]["titulo"], "T")
        self.assertEqual(self.ds.por_token(r["review_token"])["data"], "2026-07-18")

    def test_transicoes(self):
        r = self.ds.novo_rascunho("2026-07-18", {"titulo": "T"}, "resumo", "/x.pdf")
        self.ds.salvar(r)
        self.assertEqual(self.ds.aplicar("2026-07-18", "editar", "novo texto")["status"], "EDITED")
        self.assertEqual(self.ds.carregar("2026-07-18")["resumo"], "novo texto")
        self.assertEqual(self.ds.aplicar("2026-07-18", "nao_enviar")["status"], "SKIPPED")
        self.assertFalse(self.ds.pode_enviar("SKIPPED"))
        self.assertTrue(self.ds.pode_enviar("DRAFT"))

    def test_acao_invalida(self):
        r = self.ds.novo_rascunho("2026-07-18", {"titulo": "T"}, "resumo", "/x.pdf")
        self.ds.salvar(r)
        with self.assertRaises(ValueError):
            self.ds.aplicar("2026-07-18", "explodir")


if __name__ == "__main__":
    unittest.main()
