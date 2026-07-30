"""Diagramação do PDF diário: cor semântica do gráfico, braços em cartões,
bloco de vieses/limitações e agrupamento título+texto (paginação).

Regra de ouro destes testes: NADA do resumo pode sumir na diagramação.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pdf as pdfmod
import content


ART = {"tema": "Obesidade", "titulo": "T", "fonte": "NEJM", "doi": "10.x",
       "url": "https://ex.com/a", "data": "2026-01-01"}
TEMA = {"cor": "#14332a", "rotulo": "Obesidade", "emoji": "🍎"}


def _texto(html):
    """Texto visível (sem tags) — para provar que nenhum trecho se perdeu."""
    return re.sub(r"<[^>]+>", " ", html)


class TestGraficoSemantico(unittest.TestCase):
    def test_comparador_cinza_intervencao_verde_melhor_ouro(self):
        g = {"titulo": "Peso", "unidade": "%", "barras": [
            {"rotulo": "Insulina", "valor": -1.7, "comparador": True},
            {"rotulo": "Empa", "valor": -5.6},
            {"rotulo": "Combinação", "valor": -10.7}]}
        h = pdfmod._grafico_html(g)
        self.assertIn(pdfmod._CINZA_FILL, h)                 # comparador
        self.assertIn(pdfmod._OURO_FILL, h)                  # melhor resultado (maior |valor|)
        self.assertIn(pdfmod._VERDES[0], h)                  # intervenção intermediária
        self.assertIn("comparador", _texto(h))               # sublabel + legenda
        # o dourado tem que estar na barra da Combinação, não na do comparador
        linha_comb = [l for l in h.split('<div class="bar-row">') if "Combina" in l][0]
        self.assertIn(pdfmod._OURO_FILL, linha_comb)
        linha_ins = [l for l in h.split('<div class="bar-row">') if "Insulina" in l][0]
        self.assertIn(pdfmod._CINZA_FILL, linha_ins)
        self.assertNotIn(pdfmod._OURO_FILL, linha_ins)

    def test_conteudo_antigo_sem_flag_mantem_visual_de_hoje(self):
        """Retrocompatibilidade: gráfico já salvo (sem `comparador`) renderiza
        igual ao de antes — 1ª barra verde-escura, resto cinza. Nunca tudo cinza."""
        g = {"titulo": "Peso", "unidade": "%", "barras": [
            {"rotulo": "Tirzepatida", "valor": 20.9}, {"rotulo": "Placebo", "valor": 3.1}]}
        h = pdfmod._grafico_html(g)
        self.assertIn(pdfmod._LEGADO_FILL, h)
        self.assertIn(pdfmod._CINZA_FILL, h)
        self.assertNotIn(pdfmod._OURO_FILL, h)
        self.assertNotIn("melhor resultado", h)              # sem legenda no modo legado

    def test_chamada_so_aparece_quando_a_ia_manda(self):
        base = {"titulo": "P", "unidade": "%", "barras": [
            {"rotulo": "A", "valor": 10, "comparador": True}, {"rotulo": "B", "valor": 60}]}
        self.assertNotIn("chamada", pdfmod._grafico_html(base))
        com = dict(base, chamada="6× mais eficaz que a *insulina*")
        h = pdfmod._grafico_html(com)
        self.assertIn("6× mais eficaz que a", _texto(h))
        self.assertIn("<strong>insulina</strong>", h)         # *negrito* funciona

    def test_grafico_vazio_continua_sem_render(self):
        self.assertEqual(pdfmod._grafico_html(None), "")
        self.assertEqual(pdfmod._grafico_html({"barras": []}), "")


class TestBracos(unittest.TestCase):
    def test_cartoes_usam_a_cor_da_barra_do_mesmo_braco(self):
        g = {"titulo": "P", "unidade": "%", "barras": [
                {"rotulo": "Insulina", "valor": -1.7, "comparador": True},
                {"rotulo": "Combinação", "valor": -10.7}],
             "bracos": [{"nome": "Insulina", "dose": "controle ativo", "n": "45"},
                        {"nome": "Combinação", "dose": "lira + empa", "n": "45"}]}
        h = pdfmod._bracos_html(g)
        card_ins = [c for c in h.split('<div class="braco">') if "Insulina" in c][0]
        card_comb = [c for c in h.split('<div class="braco">') if "Combina" in c][0]
        self.assertIn(f'background:{pdfmod._CINZA_FILL}', card_ins)
        self.assertIn(f'background:{pdfmod._OURO_STRIPE}', card_comb)
        self.assertIn("n = 45", _texto(h))
        self.assertIn("controle ativo", _texto(h))

    def test_sem_bracos_nao_renderiza_nada(self):
        self.assertEqual(pdfmod._bracos_html(None), "")
        self.assertEqual(pdfmod._bracos_html({"barras": [{"rotulo": "A", "valor": 1}]}), "")
        self.assertEqual(pdfmod._bracos_html({"bracos": []}), "")

    def test_braco_sem_barra_correspondente_nao_quebra(self):
        g = {"barras": [{"rotulo": "X", "valor": 1}], "bracos": [{"nome": "Desconhecido"}]}
        h = pdfmod._bracos_html(g)
        self.assertIn("Desconhecido", _texto(h))


class TestLimitacoes(unittest.TestCase):
    RESUMO = ("📊 *Resultados*\n"
              "A carótida caiu em todos.\n"
              "🧯 *Vieses e limitações*\n"
              "Não é randomizado — é coorte pareada.\n"
              "183 pacientes, centro único.\n"
              "🧠 *O que muda na prática*\n"
              "Somar as classes passa a ter racional.")

    def test_secao_vira_bloco_proprio_com_seus_paragrafos(self):
        h = pdfmod._resumo_html(self.RESUMO)
        self.assertIn('class="limites"', h)
        bloco = h.split('<div class="limites">')[1]
        self.assertIn("coorte pareada", bloco)
        self.assertIn("centro único", bloco)
        # a seção seguinte NÃO pode ser sugada para dentro do bloco
        limites = h.split('class="limites"')[1].split('class="h"')[0]
        self.assertNotIn("racional", limites)

    def test_nada_do_resumo_se_perde(self):
        """O pior desfecho possível: sumir texto. Cada linha tem que sobreviver."""
        h = pdfmod._resumo_html(self.RESUMO)
        visivel = _texto(h)
        for linha in self.RESUMO.split("\n"):
            self.assertIn(linha.replace("*", "").strip(), visivel)

    def test_sem_secao_de_limitacoes_cai_no_render_plano(self):
        r = "📊 *Resultados*\nA queda foi de 10%.\nOutro parágrafo."
        h = pdfmod._resumo_html(r)
        self.assertNotIn("limites", h)
        for t in ("Resultados", "A queda foi de 10%.", "Outro parágrafo."):
            self.assertIn(t, _texto(h))

    def test_texto_sem_titulos_continua_parágrafo_simples(self):
        h = pdfmod._resumo_html("linha um\nlinha dois")
        self.assertEqual(h, "<p>linha um</p><p>linha dois</p>")


class TestPaginacaoAgrupamento(unittest.TestCase):
    def test_titulo_viaja_colado_ao_primeiro_paragrafo(self):
        h = pdfmod._resumo_html("📊 *Resultados*\nprimeiro\nsegundo")
        self.assertIn('<div class="keep"><p class="h">📊 Resultados</p><p>primeiro</p></div>', h)
        self.assertIn("<p>segundo</p>", h)                    # 2º fica fora do grupo

    def test_paragrafo_gigante_nao_entra_no_keep(self):
        """Grupo maior que a página faria o Chromium abrir página em branco —
        nesse caso degrada para o render antigo (sem invólucro)."""
        gigante = "x" * (pdfmod._MAX_KEEP_CHARS + 50)
        h = pdfmod._resumo_html(f"📊 *Resultados*\n{gigante}")
        self.assertNotIn("keep", h)
        self.assertIn(gigante, h)

    def test_titulo_sem_texto_seguinte_nao_quebra(self):
        h = pdfmod._resumo_html("📊 *Resultados*\n---\noutra coisa")
        self.assertIn('<p class="h">📊 Resultados</p>', h)
        self.assertIn('<hr class="rule">', h)
        self.assertIn("outra coisa", _texto(h))

    def test_orfas_e_viuvas_em_3(self):
        html = pdfmod.montar_html(ART, {"titulo_pt": "T", "resumo": "a", "gancho": ""}, TEMA)
        self.assertIn("orphans:3", html)
        self.assertIn("widows:3", html)

    def test_bloco_de_limites_pode_quebrar_mas_o_topo_nao(self):
        h = pdfmod._resumo_html(TestLimitacoes.RESUMO)
        limites = h.split('<div class="limites">')[1]
        self.assertTrue(limites.startswith('<div class="keep">'))


class TestPreservacaoDoQueJaFunciona(unittest.TestCase):
    """Guarda-corpo: os elementos que o dono pediu para NÃO mudar."""

    def test_pecas_intocadas(self):
        conteudo = {"titulo_pt": "Título", "resumo": "💡 *Em resumo*\ntexto", "gancho": "poste isso",
                    "grafico": {"titulo": "G", "unidade": "%", "barras": [{"rotulo": "A", "valor": 1}]}}
        h = pdfmod.montar_html(ART, conteudo, TEMA)
        for pedaco in ("height:185px", "Atualiza&ccedil;&atilde;o cient&iacute;fica", "Dr. Diego Silva",
                       "CRM-PR 54310", 'class="tag"', "🍎", "Obesidade", "📣 Para suas redes",
                       "Refer&ecirc;ncia: https://ex.com/a", "@page", "size: A4; margin: 0",
                       "font-size:20px", "Georgia", "NEJM", "DOI 10.x",
                       "border-bottom:2px solid #c9a227", "<svg viewBox"):
            self.assertIn(pedaco, h, pedaco)
        self.assertIn("conteúdo exclusivo para assinantes", h)


class TestParseGrafico(unittest.TestCase):
    def test_flag_chamada_e_bracos_sao_parseados(self):
        txt = ('{"titulo":"P","unidade":"%","barras":[{"rotulo":"A","valor":1,"comparador":true},'
               '{"rotulo":"B","valor":9}],"chamada":"9x mais que A",'
               '"bracos":[{"nome":"A","dose":"10 mg","n":45}]}')
        g = content._parse_grafico(txt)
        self.assertTrue(g["barras"][0]["comparador"])
        self.assertNotIn("comparador", g["barras"][1])
        self.assertEqual(g["chamada"], "9x mais que A")
        self.assertEqual(g["bracos"], [{"nome": "A", "dose": "10 mg", "n": "45"}])

    def test_json_antigo_sem_campos_novos_continua_valido(self):
        g = content._parse_grafico('{"titulo":"P","unidade":"%","barras":[{"rotulo":"A","valor":1}]}')
        self.assertEqual(g["barras"], [{"rotulo": "A", "valor": 1}])
        self.assertNotIn("chamada", g)
        self.assertNotIn("bracos", g)

    def test_prompt_pede_comparador(self):
        p = content._prompt_grafico({"titulo": "t", "resumo": "r"})
        self.assertIn("comparador", p)
        self.assertIn("chamada", p)
        self.assertIn("bracos", p)


if __name__ == "__main__":
    unittest.main()
