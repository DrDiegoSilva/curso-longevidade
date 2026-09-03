"""Texto completo (Open Access, Europe PMC) — buscar_estudos.py. Rede não é testada;
os pontos de HTTP (_http_get_json/_http_get_text) são substituídos, igual sources.py faz
com seu próprio _get."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import buscar_estudos as be


class TestXmlParaTexto(unittest.TestCase):
    def test_tira_tags_e_junta_espaco(self):
        xml = "<article><p>A tirzepatida <bold>reduziu</bold> o peso.</p></article>"
        self.assertEqual(be._xml_para_texto(xml), "A tirzepatida reduziu o peso.")

    def test_corta_bibliografia(self):
        xml = "<article><body><p>Resultado principal.</p></body><back><ref>Ref 1</ref></back></article>"
        texto = be._xml_para_texto(xml)
        self.assertIn("Resultado principal", texto)
        self.assertNotIn("Ref 1", texto)

    def test_unescape_entidades(self):
        xml = "<p>Risco &gt; 10% (IC95%) &amp; p&lt;0.05</p>"
        self.assertEqual(be._xml_para_texto(xml), "Risco > 10% (IC95%) & p<0.05")

    def test_corta_em_max_chars(self):
        xml = "<p>" + ("a" * 100) + "</p>"
        self.assertEqual(len(be._xml_para_texto(xml, max_chars=10)), 10)

    def test_vazio(self):
        self.assertEqual(be._xml_para_texto(""), "")
        self.assertEqual(be._xml_para_texto(None), "")


class TestTextoCompletoPmc(unittest.TestCase):
    def test_busca_e_extrai(self):
        orig = be._http_get_text
        be._http_get_text = lambda url, timeout=60: "<p>Corpo do artigo.</p>"
        try:
            self.assertEqual(be.texto_completo_pmc("PMC123"), "Corpo do artigo.")
        finally:
            be._http_get_text = orig

    def test_sem_pmcid_devolve_none(self):
        self.assertIsNone(be.texto_completo_pmc(""))

    def test_falha_de_rede_devolve_none_sem_levantar(self):
        orig = be._http_get_text
        def bomba(url, timeout=60):
            raise TimeoutError("sem resposta")
        be._http_get_text = bomba
        try:
            self.assertIsNone(be.texto_completo_pmc("PMC123"))
        finally:
            be._http_get_text = orig


class TestPmcidPorDoi(unittest.TestCase):
    def test_acha(self):
        orig = be._http_get_json
        be._http_get_json = lambda url, timeout=40: {"resultList": {"result": [
            {"pmcid": "PMC999", "isOpenAccess": "Y"}]}}
        try:
            self.assertEqual(be._pmcid_por_doi("10.1/x"), ("PMC999", "Y"))
        finally:
            be._http_get_json = orig

    def test_nao_acha(self):
        orig = be._http_get_json
        be._http_get_json = lambda url, timeout=40: {"resultList": {"result": []}}
        try:
            self.assertEqual(be._pmcid_por_doi("10.1/x"), ("", ""))
        finally:
            be._http_get_json = orig

    def test_sem_doi_nao_chama_rede(self):
        chamado = {"n": 0}
        orig = be._http_get_json
        def conta(url, timeout=40):
            chamado["n"] += 1
            return {}
        be._http_get_json = conta
        try:
            self.assertEqual(be._pmcid_por_doi(""), ("", ""))
        finally:
            be._http_get_json = orig
        self.assertEqual(chamado["n"], 0)


class TestTextoCompleto(unittest.TestCase):
    def test_usa_pmcid_ja_conhecido_sem_2a_chamada(self):
        """Artigo que já veio da própria Europe PMC (search) não precisa de lookup por DOI."""
        chamado_lookup = {"n": 0}
        orig_lookup, orig_pmc = be._pmcid_por_doi, be.texto_completo_pmc
        be._pmcid_por_doi = lambda doi: chamado_lookup.__setitem__("n", chamado_lookup["n"] + 1) or ("", "")
        be.texto_completo_pmc = lambda pmcid: f"TEXTO-{pmcid}"
        try:
            self.assertEqual(be.texto_completo(doi="10.1/x", pmcid="PMC1", is_open_access="Y"),
                              "TEXTO-PMC1")
        finally:
            be._pmcid_por_doi, be.texto_completo_pmc = orig_lookup, orig_pmc
        self.assertEqual(chamado_lookup["n"], 0)

    def test_sem_pmcid_resolve_por_doi(self):
        """Artigo de outra base (OpenAlex/Semantic Scholar) resolve pelo DOI."""
        orig_lookup, orig_pmc = be._pmcid_por_doi, be.texto_completo_pmc
        be._pmcid_por_doi = lambda doi: ("PMC2", "Y")
        be.texto_completo_pmc = lambda pmcid: f"TEXTO-{pmcid}"
        try:
            self.assertEqual(be.texto_completo(doi="10.1/y"), "TEXTO-PMC2")
        finally:
            be._pmcid_por_doi, be.texto_completo_pmc = orig_lookup, orig_pmc

    def test_nao_open_access_devolve_none(self):
        orig_lookup = be._pmcid_por_doi
        be._pmcid_por_doi = lambda doi: ("PMC3", "N")   # tem PMCID mas NÃO é OA -> sem full text
        try:
            self.assertIsNone(be.texto_completo(doi="10.1/z"))
        finally:
            be._pmcid_por_doi = orig_lookup

    def test_sem_doi_nem_pmcid_devolve_none(self):
        self.assertIsNone(be.texto_completo())


if __name__ == "__main__":
    unittest.main()
