"""Item 37 — DOI/revista/data saem DE DENTRO do PDF subido.

O item 35-B só escondeu a linha vazia; isto preenche de verdade, que é o que faz
o upload manual ficar igual ao que vem do Europe PMC. De quebra conserta o
`Referência: —` do rodapé: com DOI dá pra montar a URL do paper.

O DOI sai por REGEX, não por IA: ele tem formato fixo, e identificador é
exatamente o tipo de campo em que alucinação passa despercebida.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TEMAS = ["Obesidade", "Hormonal", "Lipedema", "Performance", "Longevidade"]

# Como um paper de verdade abre a primeira página.
PRIMEIRA_PAGINA = """Clinical Nutrition ESPEN 62 (2026) 445-453

Medical nutrition in the era of GLP-1 receptor agonists

Received 12 March 2026; accepted 2 June 2026
https://doi.org/10.1016/j.clnesp.2026.05.014

Abstract
Glucagon-like peptide-1 receptor agonists have transformed obesity care..."""


class TestDoiDoTexto(unittest.TestCase):
    def setUp(self):
        import curadoria
        self.c = curadoria

    def test_acha_o_doi_na_primeira_pagina(self):
        self.assertEqual(self.c.doi_do_texto(PRIMEIRA_PAGINA), "10.1016/j.clnesp.2026.05.014")

    def test_acha_doi_sem_o_prefixo_de_url(self):
        self.assertEqual(self.c.doi_do_texto("DOI: 10.1056/NEJMoa2032183"), "10.1056/NEJMoa2032183")

    def test_ponto_final_da_frase_nao_entra_no_doi(self):
        self.assertEqual(self.c.doi_do_texto("ver 10.1001/jama.2026.1234."), "10.1001/jama.2026.1234")

    def test_parentese_de_fechamento_nao_entra_no_doi(self):
        self.assertEqual(self.c.doi_do_texto("(doi 10.1038/s41586-024-07123-4)"),
                         "10.1038/s41586-024-07123-4")

    def test_pega_o_primeiro_que_e_o_do_proprio_paper(self):
        """O DOI do paper aparece na abertura; os das referências vêm depois."""
        txt = PRIMEIRA_PAGINA + "\n\nReferences\n1. Smith J. https://doi.org/10.9999/outro.paper"
        self.assertEqual(self.c.doi_do_texto(txt), "10.1016/j.clnesp.2026.05.014")

    def test_texto_sem_doi_devolve_vazio(self):
        self.assertEqual(self.c.doi_do_texto("um texto qualquer sem identificador"), "")
        self.assertEqual(self.c.doi_do_texto(""), "")


class TestExtrairMetadados(unittest.TestCase):
    def setUp(self):
        import triage
        self.t = triage

    def test_devolve_area_fonte_e_data(self):
        r = self.t.extrair_metadados("T", "x", TEMAS,
            llm=lambda p: '{"area":"Obesidade","fonte":"Clinical Nutrition ESPEN","data":"2026-06"}')
        self.assertEqual(r["area"], "Obesidade")
        self.assertEqual(r["fonte"], "Clinical Nutrition ESPEN")
        self.assertEqual(r["data"], "2026-06")

    def test_area_fora_da_lista_nao_e_aceita(self):
        r = self.t.extrair_metadados("T", "x", TEMAS,
                                     llm=lambda p: '{"area":"Cardiologia","fonte":"NEJM"}')
        self.assertEqual(r["area"], "")
        self.assertEqual(r["fonte"], "NEJM")      # o resto do JSON continua valendo

    def test_falha_da_ia_devolve_tudo_vazio_sem_levantar(self):
        def explode(p):
            raise RuntimeError("sem rede")
        self.assertEqual(self.t.extrair_metadados("T", "x", TEMAS, llm=explode),
                         {"area": "", "fonte": "", "data": ""})

    def test_resposta_que_nao_e_json_nao_derruba(self):
        self.assertEqual(self.t.extrair_metadados("T", "x", TEMAS, llm=lambda p: "sei lá"),
                         {"area": "", "fonte": "", "data": ""})

    def test_uma_chamada_so_para_os_tres_campos(self):
        """Antes eram 2 chamadas Haiku sobre o MESMO texto (área e metadados)."""
        chamadas = []
        self.t.extrair_metadados("T", "CORPO", TEMAS,
                                 llm=lambda p: chamadas.append(p) or '{"area":"Obesidade"}')
        self.assertEqual(len(chamadas), 1)
        self.assertIn("CORPO", chamadas[0])


class TestUploadPreenche(unittest.TestCase):
    def setUp(self):
        import importlib
        import shutil
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        for m in ("config", "db", "curadoria"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import curadoria, db
        importlib.reload(db)
        importlib.reload(curadoria)
        self.db, self.cur = db, curadoria
        db.init()

    def _subir(self, texto=PRIMEIRA_PAGINA, extrair=None, **campos):
        if extrair is None:
            def extrair(titulo, corpo, temas):
                return {"area": "Obesidade", "fonte": "Clinical Nutrition ESPEN", "data": "2026-06"}
        self.cur.adicionar_meu_estudo(
            texto, triar_fn=lambda arts, tema: [], extrair_fn=extrair,
            gerar_resumo=lambda a: "r", gerar_gancho=lambda a: "g",
            gerar_grafico_json=lambda a: "null", gerar_titulo=lambda a: "T", **campos)
        return self.db.listar_reserva(status="pronto")[0]

    def test_area_detectada_vira_o_tema_do_estudo(self):
        """Era "Meus estudos" fixo -- o chip da capa saía genérico em todo upload."""
        self.assertEqual(self._subir()["tema"], "Obesidade")

    def test_doi_do_pdf_vai_pro_estudo(self):
        self.assertEqual(self._subir()["doi"], "10.1016/j.clnesp.2026.05.014")

    def test_revista_e_data_da_ia_vao_pro_estudo(self):
        r = self._subir()
        self.assertEqual(r["fonte"], "Clinical Nutrition ESPEN")
        self.assertEqual(r["data"], "2026-06")

    def test_referencia_do_rodape_vira_link_pelo_doi(self):
        """Era `Referência: —` no upload, porque `url` nascia vazia."""
        self.assertEqual(self._subir()["url"], "https://doi.org/10.1016/j.clnesp.2026.05.014")

    def test_o_que_o_diego_digitou_ganha_do_extraido(self):
        r = self._subir(fonte="Revista que eu digitei", doi="10.0/meu")
        self.assertEqual(r["fonte"], "Revista que eu digitei")
        self.assertEqual(r["doi"], "10.0/meu")
        self.assertEqual(r["url"], "https://doi.org/10.0/meu")

    def test_url_digitada_ganha_do_doi(self):
        self.assertEqual(self._subir(url="https://meulink.com/x")["url"], "https://meulink.com/x")

    def test_pdf_sem_doi_nenhum_nao_inventa_url(self):
        r = self._subir(texto="texto de um estudo qualquer, sem identificador nenhum. " * 20)
        self.assertEqual(r["doi"], "")
        self.assertEqual(r["url"], "")

    def test_extracao_que_explode_nao_impede_o_upload(self):
        def explode(titulo, corpo, temas):
            raise RuntimeError("caiu")
        r = self._subir(extrair=explode)
        self.assertEqual(r["tema"], "Meus estudos")
        self.assertEqual(r["doi"], "10.1016/j.clnesp.2026.05.014")   # regex não depende da IA

    def test_a_revista_extraida_chega_no_gerador_do_resumo(self):
        visto = {}
        self.cur.adicionar_meu_estudo(
            PRIMEIRA_PAGINA, triar_fn=lambda arts, tema: [],
            extrair_fn=lambda t, c, temas: {"area": "", "fonte": "ESPEN", "data": ""},
            gerar_resumo=lambda a: visto.setdefault("fonte", a.get("fonte")) or "r",
            gerar_gancho=lambda a: "g", gerar_grafico_json=lambda a: "null",
            gerar_titulo=lambda a: "T")
        self.assertEqual(visto["fonte"], "ESPEN")


if __name__ == "__main__":
    unittest.main()
