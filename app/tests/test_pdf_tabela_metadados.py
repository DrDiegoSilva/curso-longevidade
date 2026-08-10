"""Os dois defeitos que o 1º PDF real com o kit novo mostrou (2026-08-10).

A) Tabela markdown CRUA no meio do resumo: o modelo escolheu tabela, o
   `_tokens_resumo` só conhecia separador/título/parágrafo, e o assinante recebeu
   `| População | Proteína/dia |` e `|---|---|---|` impressos literalmente.
   Atinge o PDF *e* o portal -- `site_web.pagina_digest` chama o mesmo
   `pdf._resumo_html`.

B) Metadado órfão no topo: `· · DOI —` embaixo do título. No caminho de UPLOAD
   fonte/data/DOI são campos opcionais do formulário e chegam vazios; a linha era
   montada incondicionalmente.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ART = {"titulo": "T EN", "titulo_original": "T EN", "fonte": "NEJM",
       "data": "2026-08-04", "doi": "10.1056/x", "url": "https://x"}
TEMA = {"cor": "#14332a", "rotulo": "Obesidade", "emoji": "⚖️"}

# Trecho fiel ao PDF de 2026-08-10 (pág. 3), que saiu com os canos crus.
RESUMO_COM_TABELA = """*Populações especiais — destaques da Tabela 1:*
| População | Proteína/dia | Observação principal |
|---|---|---|
| Idosos (≥65 anos) | 1,2–1,5 g/kg | RT + monitorar vitamina D e ferro |
| DM2 | ≥1,2 g/kg | Monitorar B12 (metformina) |"""


def _meta(html):
    m = re.search(r'<div class="meta">(.*?)</div>', html, re.S)
    return m.group(1) if m else None


def _css(html):
    """Só o <style>. Asserção de CSS feita no documento inteiro casa com os
    COMENTÁRIOS do próprio CSS e passa mesmo com a regra errada."""
    return html[html.index("<style>"):html.index("</style>")]


class TestTabelaNoResumo(unittest.TestCase):
    def setUp(self):
        import pdf
        self.pdf = pdf

    def test_tabela_de_cano_vira_table(self):
        h = self.pdf._resumo_html(RESUMO_COM_TABELA)
        self.assertIn("<table>", h)
        self.assertIn("<th>População</th>", h)
        self.assertIn("<td>DM2</td>", h)

    def test_nenhum_cano_cru_chega_no_assinante(self):
        h = self.pdf._resumo_html(RESUMO_COM_TABELA)
        self.assertNotIn("|", h)

    def test_linha_separadora_some(self):
        """`|---|---|---|` virava um parágrafo próprio no PDF."""
        h = self.pdf._resumo_html(RESUMO_COM_TABELA)
        self.assertNotIn("---", h)

    def test_titulo_da_secao_sobrevive_a_tabela_que_vem_depois(self):
        h = self.pdf._resumo_html(RESUMO_COM_TABELA)
        self.assertIn("Populações especiais", h)
        self.assertIn('class="h"', h)

    def test_negrito_do_whatsapp_funciona_dentro_da_celula(self):
        """O resumo usa `*negrito*` (WhatsApp), não `**negrito**` (trilha)."""
        h = self.pdf._resumo_html("| Item | Valor |\n|---|---|\n| *Total* | 10 |")
        self.assertIn("<strong>Total</strong>", h)
        self.assertNotIn("*", h)

    def test_escapa_html_dentro_da_celula(self):
        h = self.pdf._resumo_html("| a | b |\n|---|---|\n| <script>x</script> | 1 |")
        self.assertNotIn("<script>", h)
        self.assertIn("&lt;script&gt;", h)

    def test_frase_solta_entre_canos_continua_paragrafo(self):
        """Sem linha separadora não é tabela -- o texto não pode sumir num <table>."""
        h = self.pdf._resumo_html("| isto é só uma frase entre canos |")
        self.assertNotIn("<table>", h)
        self.assertIn("isto é só uma frase entre canos", h)

    def test_texto_depois_da_tabela_nao_se_perde(self):
        h = self.pdf._resumo_html(f"{RESUMO_COM_TABELA}\nParágrafo final.")
        self.assertIn("<p>Parágrafo final.</p>", h)

    def test_resumo_sem_tabela_continua_igual(self):
        h = self.pdf._resumo_html("📊 *Resultados*\nprimeiro\nsegundo")
        self.assertNotIn("<table>", h)
        self.assertIn("<p>primeiro</p>", h)


class TestCssDaTabela(unittest.TestCase):
    """O PDF e o site têm cópias SEPARADAS do CSS: sem a regra nos dois, um deles
    renderiza tabela default de browser."""

    def test_pdf_tem_css_de_tabela(self):
        import pdf
        h = pdf.montar_html(ART, {"titulo_pt": "T", "resumo": RESUMO_COM_TABELA,
                                  "gancho": ""}, TEMA)
        self.assertIn(".corpo table", h)
        self.assertIn(".corpo th", h)

    def test_cabecalho_repete_quando_a_tabela_quebra_de_pagina(self):
        """Olha a REGRA, não o documento: `table-header-group` também aparece no
        comentário do CSS, e assertIn no HTML inteiro passaria com a regra errada."""
        import pdf
        h = pdf.montar_html(ART, {"titulo_pt": "T", "resumo": "x", "gancho": ""}, TEMA)
        regra = re.search(r"\.corpo thead\s*\{([^}]*)\}", _css(h))
        self.assertIsNotNone(regra)
        self.assertIn("table-header-group", regra.group(1))

    def test_a_tabela_inteira_nao_leva_break_inside_avoid(self):
        """Grupo maior que a página faz o Chromium empurrar tudo e abrir página em
        branco -- o mesmo defeito que os cards do kit já tiveram. Quem não pode
        partir é a LINHA, não a tabela."""
        import pdf
        h = pdf.montar_html(ART, {"titulo_pt": "T", "resumo": "x", "gancho": ""}, TEMA)
        regra = re.search(r"\.corpo table\s*\{([^}]*)\}", _css(h))
        self.assertIsNotNone(regra)
        self.assertNotIn("break-inside:avoid", regra.group(1).replace(" ", ""))

    def test_site_tem_css_de_tabela(self):
        import site_web
        d = {"titulo_pt": "T", "titulo_original": "T EN", "fonte": "NEJM",
             "data": "2026-08-04", "doi": "10.1056/x", "url": "https://x",
             "resumo": RESUMO_COM_TABELA, "grafico": None, "gancho": ""}
        h = site_web.pagina_digest(
            {"rotulo": "Obesidade", "emoji": "", "slug": "obesidade", "cor": "#14332a"}, d)
        self.assertIn("<table>", h)
        for regra in (".doc .corpo table{", ".doc .corpo th{"):
            self.assertIn(regra, h, regra)


class TestMetadadosVazios(unittest.TestCase):
    def _pdf(self, **art):
        import pdf
        return pdf.montar_html(dict(ART, **art),
                               {"titulo_pt": "T", "resumo": "x", "gancho": ""}, TEMA)

    def test_upload_sem_metadado_nenhum_nao_imprime_pontos_orfaos(self):
        h = self._pdf(fonte="", data="", doi="")
        self.assertEqual(_meta(h), "")
        corpo = h[h.index("</style>"):]          # sem o CSS, que fala de "DOI" nos comentários
        self.assertNotIn("DOI", corpo)
        self.assertNotIn("&middot;  &middot;", corpo)

    def test_regua_dourada_continua_separando_titulo_do_corpo(self):
        """Sem a régua o título encosta no resumo. Fica só o filete."""
        h = self._pdf(fonte="", data="", doi="")
        self.assertIn(".meta:empty", h)

    def test_doi_ausente_nao_vira_travessao_orfao(self):
        h = self._pdf(doi="")
        self.assertEqual(_meta(h), "NEJM &middot; 2026-08-04")

    def test_fonte_ausente_nao_deixa_ponto_na_frente(self):
        h = self._pdf(fonte="")
        self.assertEqual(_meta(h), "2026-08-04 &middot; DOI 10.1056/x")

    def test_metadado_completo_continua_igual(self):
        self.assertEqual(_meta(self._pdf()), "NEJM &middot; 2026-08-04 &middot; DOI 10.1056/x")

    def test_kit_nao_deixa_rotulo_de_revista_vazio(self):
        """Mesma classe do `· · DOI —`, no bloco "1 · O estudo": sem fonte nem data
        sobrava um `<div class="paper-rev"></div>` só com o margin, abrindo um vão
        acima do título do paper."""
        import pdf
        h = pdf.montar_html(dict(ART, fonte="", data=""),
                            {"titulo_pt": "T", "resumo": "x", "gancho": ""}, TEMA)
        self.assertNotIn('<div class="paper-rev"></div>', h)
        self.assertIn("T EN", h)                 # o bloco em si continua saindo

    def test_kit_com_revista_continua_mostrando(self):
        import pdf
        h = pdf.montar_html(ART, {"titulo_pt": "T", "resumo": "x", "gancho": ""}, TEMA)
        self.assertIn('<div class="paper-rev">NEJM · 2026-08-04</div>', h)

    def test_site_tambem_omite_o_que_nao_existe(self):
        import site_web
        d = {"titulo_pt": "T", "titulo_original": "T EN", "fonte": "", "data": "2026-08-04",
             "doi": "", "url": "", "resumo": "x", "grafico": None, "gancho": ""}
        h = site_web.pagina_digest(
            {"rotulo": "Obesidade", "emoji": "", "slug": "obesidade", "cor": "#14332a"}, d)
        self.assertEqual(_meta(h), "4 ago 2026")
        self.assertIn(".doc .meta:empty", h)


if __name__ == "__main__":
    unittest.main()
