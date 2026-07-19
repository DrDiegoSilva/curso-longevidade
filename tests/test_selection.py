import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import selection


def art(**k):
    base = {"titulo": "x", "resumo": "y", "fonte": "z", "doi": "", "url": "",
            "data": "2026-07-10", "tipo": "", "banco": "europepmc"}
    base.update(k)
    return base


class TestSelection(unittest.TestCase):
    def test_dedupe_por_doi_e_url(self):
        arts = [art(doi="10.1/a"), art(doi="10.1/a"), art(url="http://u/1")]
        out = selection.dedupe(arts, {"10.1/a"})
        self.assertEqual(len(out), 1)  # os com doi visto saem; sobra o de url novo
        self.assertEqual(out[0]["url"], "http://u/1")

    def test_rank_prioriza_estudo_forte_recente(self):
        fraco = art(doi="10/f", tipo="Editorial", data="2026-07-11")
        forte = art(doi="10/s", tipo="Meta-Analysis", data="2026-07-01")
        out = selection.rank([fraco, forte])
        self.assertEqual(out[0]["doi"], "10/s")

    def test_escolher_none_quando_tudo_ja_enviado(self):
        arts = [art(doi="10/a")]
        self.assertIsNone(selection.escolher_do_dia(arts, {"10/a"}))

    def test_escolher_retorna_melhor(self):
        arts = [art(doi="10/a", tipo="Editorial"), art(doi="10/b", tipo="Randomized Controlled Trial")]
        self.assertEqual(selection.escolher_do_dia(arts, set())["doi"], "10/b")


if __name__ == "__main__":
    unittest.main()
