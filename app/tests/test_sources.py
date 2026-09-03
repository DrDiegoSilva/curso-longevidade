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


class TestParseOpenAlex(unittest.TestCase):
    def _fake(self, inv, cited):
        return {"results": [{
            "title": "Semaglutide CV outcomes",
            "abstract_inverted_index": inv,
            "primary_location": {"source": {"display_name": "NEJM"}},
            "doi": "https://doi.org/10.1/x", "id": "https://openalex.org/W1",
            "publication_date": "2023-01-01", "type": "article",
            "cited_by_count": cited,
        }]}

    def _make_long_inv(self):
        """Create inverted index for abstract with ≥120 chars."""
        # Using 61 repetitions of "a" gives 121 chars when reconstructed
        words = ("a " * 61).split()
        inv = {}
        for i, word in enumerate(words):
            if word not in inv:
                inv[word] = []
            inv[word].append(i)
        return inv

    def _make_short_inv(self):
        """Create inverted index for abstract with <120 chars."""
        # Using 5 words gives ~10 chars when reconstructed (well under 120)
        words = ["short", "test", "abstract", "for", "filtering"]
        inv = {}
        for i, word in enumerate(words):
            if word not in inv:
                inv[word] = []
            inv[word].append(i)
        return inv

    def test_extrai_citacoes(self):
        inv = self._make_long_inv()
        got = sources.parse_openalex(self._fake(inv, 3120))
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["citacoes"], 3120)
        self.assertEqual(got[0]["banco"], "openalex")

    def test_sem_citacoes_default_zero(self):
        inv = self._make_long_inv()
        d = self._fake(inv, 0); del d["results"][0]["cited_by_count"]
        self.assertEqual(sources.parse_openalex(d)[0]["citacoes"], 0)

    def test_filtra_abstract_curto(self):
        inv = self._make_short_inv()
        got = sources.parse_openalex(self._fake(inv, 100))
        self.assertEqual(len(got), 0)  # abstract < 120 chars -> filtered out


class TestParseEpmc(unittest.TestCase):
    def test_carrega_pmcid_e_open_access(self):
        results = [{"title": "T", "abstractText": "x" * 200, "journalTitle": "NEJM",
                    "doi": "10.1/x", "firstPublicationDate": "2026-01-01",
                    "pmcid": "PMC1", "isOpenAccess": "Y"}]
        out = sources.parse_epmc(results)
        self.assertEqual(out[0]["pmcid"], "PMC1")
        self.assertEqual(out[0]["isOpenAccess"], "Y")
        self.assertEqual(out[0]["banco"], "europepmc")

    def test_sem_pmcid_fica_vazio_nao_quebra(self):
        results = [{"title": "T", "abstractText": "x" * 200, "journalTitle": "NEJM"}]
        out = sources.parse_epmc(results)
        self.assertEqual(out[0]["pmcid"], "")
        self.assertEqual(out[0]["isOpenAccess"], "")

    def test_filtra_abstract_curto(self):
        results = [{"title": "T", "abstractText": "curto"}]
        self.assertEqual(sources.parse_epmc(results), [])


class TestSoComTextoCompleto(unittest.TestCase):
    """O gate obrigatório: sem texto completo (Open Access), o artigo é descartado --
    decisão de 2026-09-03, nunca cai pro abstract como substituto."""

    def test_descarta_sem_texto_completo(self):
        import buscar_estudos as be
        orig = be.texto_completo
        be.texto_completo = lambda **kw: None
        try:
            out = sources._so_com_texto_completo([{"titulo": "A", "doi": "10.1/x"}])
        finally:
            be.texto_completo = orig
        self.assertEqual(out, [])

    def test_mantem_e_anexa_texto_completo(self):
        import buscar_estudos as be
        orig = be.texto_completo
        be.texto_completo = lambda **kw: "TEXTO INTEGRAL DO ESTUDO"
        try:
            out = sources._so_com_texto_completo(
                [{"titulo": "A", "doi": "10.1/x", "pmcid": "PMC1", "url": "https://doi.org/10.1/x"}])
        finally:
            be.texto_completo = orig
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["texto_completo"], "TEXTO INTEGRAL DO ESTUDO")

    def test_troca_url_pro_link_da_europe_pmc_quando_tem_pmcid(self):
        """DOI pode cair em paywall; o link da Europe PMC do próprio full text, não."""
        import buscar_estudos as be
        orig = be.texto_completo
        be.texto_completo = lambda **kw: "TEXTO"
        try:
            out = sources._so_com_texto_completo(
                [{"titulo": "A", "doi": "10.1/x", "pmcid": "PMC42", "url": "https://doi.org/10.1/x"}])
        finally:
            be.texto_completo = orig
        self.assertEqual(out[0]["url"], "https://europepmc.org/article/PMC/PMC42")

    def test_clinicaltrials_sem_doi_nunca_passa(self):
        """ClinicalTrials.gov não tem DOI -> texto_completo() sempre None -> sempre descartado."""
        import buscar_estudos as be
        orig = be.texto_completo
        chamados = []
        be.texto_completo = lambda **kw: chamados.append(kw) or None
        try:
            out = sources._so_com_texto_completo(
                [{"titulo": "Trial", "doi": "", "url": "https://clinicaltrials.gov/study/NCT01"}])
        finally:
            be.texto_completo = orig
        self.assertEqual(out, [])
        self.assertEqual(chamados[0]["doi"], "")

    def test_nao_muta_a_lista_original(self):
        import buscar_estudos as be
        orig = be.texto_completo
        be.texto_completo = lambda **kw: "TEXTO"
        entrada = [{"titulo": "A", "doi": "10.1/x", "pmcid": "PMC1"}]
        try:
            sources._so_com_texto_completo(entrada)
        finally:
            be.texto_completo = orig
        self.assertNotIn("texto_completo", entrada[0])   # o dict original não foi alterado


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
