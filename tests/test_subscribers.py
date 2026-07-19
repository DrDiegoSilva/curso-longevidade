import sys, os, tempfile, unittest, importlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


class TestSubs(unittest.TestCase):
    def setUp(self):
        os.environ["DSCURSO_DATA"] = tempfile.mkdtemp()
        import config
        importlib.reload(config)
        import subscribers
        importlib.reload(subscribers)
        self.s = subscribers

    def test_add_list_remove(self):
        a = self.s.adicionar("Dra. Ana", "55 43 99999-0000")
        self.assertEqual(a["status"], "ATIVO")
        self.assertEqual(a["whatsapp"], "5543999990000")  # só dígitos
        self.assertEqual(len(self.s.listar()), 1)
        self.assertEqual(len(self.s.ativos()), 1)
        self.assertTrue(self.s.remover(a["id"]))
        self.assertEqual(len(self.s.listar()), 0)

    def test_remover_inexistente(self):
        self.assertFalse(self.s.remover("naoexiste"))


if __name__ == "__main__":
    unittest.main()
