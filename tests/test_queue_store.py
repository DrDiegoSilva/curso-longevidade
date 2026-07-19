import sys, os, tempfile, unittest, importlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


def art(titulo, tema, score, doi=""):
    return {"titulo": titulo, "tema": tema, "score": score, "doi": doi, "url": ""}


class TestQueue(unittest.TestCase):
    def setUp(self):
        os.environ["DSCURSO_DATA"] = tempfile.mkdtemp()
        import config
        importlib.reload(config)
        import queue_store
        importlib.reload(queue_store)
        self.q = queue_store

    def test_adicionar_dedup_e_ordena_por_score(self):
        n = self.q.adicionar([art("A", "Obesidade", 3, "10/a"), art("B", "Lipedema", 9, "10/b")])
        self.assertEqual(n, 2)
        # dedupe: reenviar A não entra de novo
        self.assertEqual(self.q.adicionar([art("A", "Obesidade", 3, "10/a")]), 0)
        self.assertEqual(self.q.tamanho(), 2)
        prox = self.q.proximo()  # maior score primeiro
        self.assertEqual(prox["titulo"], "B")

    def test_variedade_evita_tema_repetido(self):
        self.q.adicionar([art("A", "Obesidade", 9, "10/a"),
                          art("B", "Obesidade", 8, "10/b"),
                          art("C", "Lipedema", 1, "10/c")])
        self.q.confirmar_envio(art("X", "Obesidade", 0))  # último enviado = Obesidade
        prox = self.q.proximo()
        # apesar de A/B (Obesidade) terem score maior, pega C (Lipedema) por variedade
        self.assertEqual(prox["tema"], "Lipedema")

    def test_variedade_cede_quando_so_ha_um_tema(self):
        self.q.adicionar([art("A", "Obesidade", 9, "10/a"), art("B", "Obesidade", 8, "10/b")])
        self.q.confirmar_envio(art("X", "Obesidade", 0))
        prox = self.q.proximo()  # só há Obesidade -> manda mesmo assim (o melhor)
        self.assertEqual(prox["titulo"], "A")

    def test_proximo_none_quando_vazia(self):
        self.assertIsNone(self.q.proximo())


if __name__ == "__main__":
    unittest.main()
