"""Testes dos parsers puros de sources.py (rede não é testada). Standalone."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sources


class TestReconstruirAbstract(unittest.TestCase):
    def test_ordem_pelas_posicoes(self):
        inv = {"perda": [2], "A": [0], "de": [3], "tirzepatida": [1], "peso": [4]}
        self.assertEqual(sources.reconstruir_abstract(inv), "A tirzepatida perda de peso")

    def test_palavra_repetida_em_varias_posicoes(self):
        inv = {"peso": [0, 3], "do": [1], "corpo": [2], "estável": [4]}
        self.assertEqual(sources.reconstruir_abstract(inv), "peso do corpo peso estável")

    def test_vazio_ou_none(self):
        self.assertEqual(sources.reconstruir_abstract(None), "")
        self.assertEqual(sources.reconstruir_abstract({}), "")


class TestParsers(unittest.TestCase):
    def test_pubmed_esummary_sem_abstract(self):
        data = {"result": {"uids": ["1"], "1": {"title": "T", "fulljournalname": "NEJM",
                "articleids": [{"idtype": "doi", "value": "10.1/x"}], "pubdate": "2026"}}}
        out = sources.parse_pubmed_esummary(data)
        self.assertEqual(out[0]["doi"], "10.1/x")
        self.assertEqual(out[0]["resumo"], "")          # esummary não traz abstract (por isso aposentado)

    def test_clinicaltrials_parse(self):
        data = {"studies": [{"protocolSection": {
            "identificationModule": {"nctId": "NCT01", "briefTitle": "Estudo X"},
            "descriptionModule": {"briefSummary": "resumo do ensaio"}}}]}
        out = sources.parse_clinicaltrials(data)
        self.assertEqual(out[0]["url"], "https://clinicaltrials.gov/study/NCT01")
        self.assertEqual(out[0]["resumo"], "resumo do ensaio")


class TestSemanticScholar(unittest.TestCase):
    def test_parse_so_com_abstract(self):
        data = {"data": [
            {"title": "A", "abstract": "x" * 200, "venue": "NEJM", "year": 2026,
             "publicationDate": "2026-02-01", "externalIds": {"DOI": "10.1/a"}},
            {"title": "B", "abstract": "curto", "venue": "BMJ"},          # < 120 -> fora
            {"title": "C", "abstract": None, "venue": "Lancet"}]}         # sem abstract -> fora
        out = sources.parse_semanticscholar(data)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["doi"], "10.1/a")
        self.assertEqual(out[0]["url"], "https://doi.org/10.1/a")
        self.assertEqual(out[0]["banco"], "semanticscholar")

    def test_sem_chave_nao_chama(self):
        antigo = os.environ.pop("SEMANTIC_SCHOLAR_KEY", None)
        try:
            self.assertEqual(sources._semanticscholar_normalizado("q", "2026-01-01", "2026-07-19"), [])
        finally:
            if antigo is not None:
                os.environ["SEMANTIC_SCHOLAR_KEY"] = antigo


class TestBackoff(unittest.TestCase):
    def _fake_get(self, respostas):
        """Retorna uma função que consome `respostas` (Exception ou valor) a cada chamada."""
        it = iter(respostas)
        def g(url, headers=None, timeout=40):
            r = next(it)
            if isinstance(r, Exception):
                raise r
            return r
        return g

    def _http(self, code):
        import urllib.error
        return urllib.error.HTTPError("u", code, "", {}, None)

    def test_repete_no_429_e_sucede(self):
        orig = sources._get
        sources._get = self._fake_get([self._http(429), self._http(429), {"ok": 1}])
        try:
            self.assertEqual(sources._get_backoff("u", sleep=lambda s: None), {"ok": 1})
        finally:
            sources._get = orig

    def test_desiste_apos_tentativas(self):
        orig = sources._get
        sources._get = self._fake_get([self._http(429)] * 4)
        try:
            with self.assertRaises(Exception):
                sources._get_backoff("u", tentativas=4, sleep=lambda s: None)
        finally:
            sources._get = orig

    def test_erro_fatal_nao_repete(self):
        orig = sources._get
        chamado = {"n": 0}
        def g(url, headers=None, timeout=40):
            chamado["n"] += 1
            raise self._http(404)                       # 404 não é retry
        sources._get = g
        try:
            with self.assertRaises(Exception):
                sources._get_backoff("u", sleep=lambda s: None)
            self.assertEqual(chamado["n"], 1)           # chamou só 1 vez
        finally:
            sources._get = orig


if __name__ == "__main__":
    unittest.main()
