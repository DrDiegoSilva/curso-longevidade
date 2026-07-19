import sys, os, json, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import sources

FX = os.path.join(os.path.dirname(__file__), "fixtures")


class TestParsers(unittest.TestCase):
    def test_parse_pubmed(self):
        data = json.load(open(os.path.join(FX, "pubmed_esummary.json"), encoding="utf-8"))
        arts = sources.parse_pubmed_esummary(data)
        self.assertTrue(len(arts) >= 1)
        a = arts[0]
        self.assertEqual(a["banco"], "pubmed")
        self.assertTrue(a["titulo"])
        self.assertEqual(a["doi"], "10.1056/NEJMoa2600001")
        self.assertTrue(a["url"].startswith("http"))

    def test_parse_clinicaltrials(self):
        data = json.load(open(os.path.join(FX, "clinicaltrials_v2.json"), encoding="utf-8"))
        arts = sources.parse_clinicaltrials(data)
        self.assertTrue(len(arts) >= 1)
        self.assertEqual(arts[0]["banco"], "clinicaltrials")
        self.assertTrue(arts[0]["url"].startswith("https://clinicaltrials.gov/"))

    def test_search_all_isola_falha_de_banco(self):
        # monkeypatch: um conector explode, os outros seguem
        orig = (sources._epmc_normalizado, sources._pubmed, sources._clinicaltrials)
        sources._epmc_normalizado = lambda q, d, a: [{"banco": "europepmc", "titulo": "ok"}]
        sources._pubmed = lambda q, d, a: (_ for _ in ()).throw(RuntimeError("pubmed caiu"))
        sources._clinicaltrials = lambda q, d, a: []
        try:
            out = sources.search_all("x", "2026-01-01", "2026-02-01")
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0]["banco"], "europepmc")
        finally:
            sources._epmc_normalizado, sources._pubmed, sources._clinicaltrials = orig


if __name__ == "__main__":
    unittest.main()
