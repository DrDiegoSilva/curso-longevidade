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

    def test_nao_open_access_na_pmc_tenta_unpaywall(self):
        """PMC diz que NÃO é OA (ou nem tem PMCID) -> ainda tenta a Unpaywall por DOI,
        que pode achar OA em lugar que a PMC não indexa."""
        orig_lookup, orig_unpaywall = be._pmcid_por_doi, be.texto_completo_unpaywall
        be._pmcid_por_doi = lambda doi: ("PMC3", "N")
        be.texto_completo_unpaywall = lambda doi: f"UNPAYWALL-{doi}"
        try:
            self.assertEqual(be.texto_completo(doi="10.1/z"), "UNPAYWALL-10.1/z")
        finally:
            be._pmcid_por_doi, be.texto_completo_unpaywall = orig_lookup, orig_unpaywall

    def test_nenhuma_fonte_acha_devolve_none(self):
        orig_lookup, orig_unpaywall = be._pmcid_por_doi, be.texto_completo_unpaywall
        be._pmcid_por_doi = lambda doi: ("PMC3", "N")
        be.texto_completo_unpaywall = lambda doi: None
        try:
            self.assertIsNone(be.texto_completo(doi="10.1/z"))
        finally:
            be._pmcid_por_doi, be.texto_completo_unpaywall = orig_lookup, orig_unpaywall

    def test_sem_doi_nem_pmcid_devolve_none(self):
        self.assertIsNone(be.texto_completo())


class TestUnpaywallMelhorPdf(unittest.TestCase):
    def test_sem_doi_nao_chama_rede(self):
        chamado = {"n": 0}
        orig = be._http_get_json
        def conta(url, timeout=40):
            chamado["n"] += 1
            return {}
        be._http_get_json = conta
        try:
            self.assertEqual(be._unpaywall_melhor_pdf(""), "")
        finally:
            be._http_get_json = orig
        self.assertEqual(chamado["n"], 0)

    def test_oa_com_pdf(self):
        orig = be._http_get_json
        be._http_get_json = lambda url, timeout=40: {
            "is_oa": True, "best_oa_location": {"url_for_pdf": "https://x.org/a.pdf"}}
        try:
            self.assertEqual(be._unpaywall_melhor_pdf("10.1/x"), "https://x.org/a.pdf")
        finally:
            be._http_get_json = orig

    def test_nao_oa_devolve_vazio(self):
        orig = be._http_get_json
        be._http_get_json = lambda url, timeout=40: {"is_oa": False}
        try:
            self.assertEqual(be._unpaywall_melhor_pdf("10.1/x"), "")
        finally:
            be._http_get_json = orig

    def test_oa_sem_link_de_pdf_devolve_vazio(self):
        orig = be._http_get_json
        be._http_get_json = lambda url, timeout=40: {
            "is_oa": True, "best_oa_location": {"url": "https://x.org/landing"}}
        try:
            self.assertEqual(be._unpaywall_melhor_pdf("10.1/x"), "")
        finally:
            be._http_get_json = orig

    def test_falha_de_rede_devolve_vazio_sem_levantar(self):
        orig = be._http_get_json
        def bomba(url, timeout=40):
            raise TimeoutError("sem resposta")
        be._http_get_json = bomba
        try:
            self.assertEqual(be._unpaywall_melhor_pdf("10.1/x"), "")
        finally:
            be._http_get_json = orig


class TestPdfBytesParaTexto(unittest.TestCase):
    def test_extrai_via_pdftotext(self):
        import subprocess
        orig = subprocess.run
        class FakeOut:
            stdout = "Corpo do artigo.".encode("utf-8")
        subprocess.run = lambda *a, **k: FakeOut()
        try:
            self.assertEqual(be._pdf_bytes_para_texto(b"%PDF-fake"), "Corpo do artigo.")
        finally:
            subprocess.run = orig

    def test_saida_vazia_devolve_none(self):
        import subprocess
        orig = subprocess.run
        class FakeOut:
            stdout = b""
        subprocess.run = lambda *a, **k: FakeOut()
        try:
            self.assertIsNone(be._pdf_bytes_para_texto(b"%PDF-fake"))
        finally:
            subprocess.run = orig

    def test_falha_devolve_none_sem_levantar(self):
        import subprocess
        orig = subprocess.run
        def bomba(*a, **k):
            raise OSError("pdftotext não encontrado")
        subprocess.run = bomba
        try:
            self.assertIsNone(be._pdf_bytes_para_texto(b"%PDF-fake"))
        finally:
            subprocess.run = orig


class TestTextoCompletoUnpaywall(unittest.TestCase):
    def test_sem_pdf_devolve_none_sem_baixar(self):
        orig_melhor, orig_bytes = be._unpaywall_melhor_pdf, be._http_get_bytes
        be._unpaywall_melhor_pdf = lambda doi: ""
        chamado = {"n": 0}
        be._http_get_bytes = lambda url, timeout=60: chamado.__setitem__("n", chamado["n"] + 1) or (b"", "")
        try:
            self.assertIsNone(be.texto_completo_unpaywall("10.1/x"))
        finally:
            be._unpaywall_melhor_pdf, be._http_get_bytes = orig_melhor, orig_bytes
        self.assertEqual(chamado["n"], 0)

    def test_pdf_de_verdade_extrai_texto(self):
        orig_melhor, orig_bytes, orig_extrai = (be._unpaywall_melhor_pdf, be._http_get_bytes,
                                                  be._pdf_bytes_para_texto)
        be._unpaywall_melhor_pdf = lambda doi: "https://x.org/a.pdf"
        be._http_get_bytes = lambda url, timeout=60: (b"%PDF-fake", "application/pdf")
        be._pdf_bytes_para_texto = lambda pdf_bytes: "Corpo do artigo."
        try:
            self.assertEqual(be.texto_completo_unpaywall("10.1/x"), "Corpo do artigo.")
        finally:
            be._unpaywall_melhor_pdf, be._http_get_bytes, be._pdf_bytes_para_texto = (
                orig_melhor, orig_bytes, orig_extrai)

    def test_resposta_html_e_descartada_sem_extrair(self):
        """Link "de PDF" que na verdade devolve uma página HTML (landing/paywall) --
        não pode virar texto completo: menu/propaganda no lugar do corpo real."""
        orig_melhor, orig_bytes, orig_extrai = (be._unpaywall_melhor_pdf, be._http_get_bytes,
                                                  be._pdf_bytes_para_texto)
        be._unpaywall_melhor_pdf = lambda doi: "https://x.org/a.pdf"
        be._http_get_bytes = lambda url, timeout=60: (b"<html>...</html>", "text/html; charset=utf-8")
        chamado = {"n": 0}
        be._pdf_bytes_para_texto = lambda pdf_bytes: chamado.__setitem__("n", chamado["n"] + 1)
        try:
            self.assertIsNone(be.texto_completo_unpaywall("10.1/x"))
        finally:
            be._unpaywall_melhor_pdf, be._http_get_bytes, be._pdf_bytes_para_texto = (
                orig_melhor, orig_bytes, orig_extrai)
        self.assertEqual(chamado["n"], 0)

    def test_falha_de_download_devolve_none(self):
        orig_melhor, orig_bytes = be._unpaywall_melhor_pdf, be._http_get_bytes
        be._unpaywall_melhor_pdf = lambda doi: "https://x.org/a.pdf"
        def bomba(url, timeout=60):
            raise TimeoutError("sem resposta")
        be._http_get_bytes = bomba
        try:
            self.assertIsNone(be.texto_completo_unpaywall("10.1/x"))
        finally:
            be._unpaywall_melhor_pdf, be._http_get_bytes = orig_melhor, orig_bytes


if __name__ == "__main__":
    unittest.main()
