"""Parser e render do kit de redes (rodape do PDF). Standalone."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestParseGancho(unittest.TestCase):
    def setUp(self):
        import content
        self.c = content

    def test_json_formato_antigo_com_angulo_vira_gancho(self):
        """O estoque de reserva/classicos esta cheio deste formato: `angulo` sem
        roteiro. Se parar de funcionar, todo estudo ja na fila sai com o kit vazio."""
        bruto = ('{"frase": "Perdeu 20,9% do peso.",'
                 ' "reels": [{"angulo": "Nao e forca de vontade.", "apoio": "O comparador perdeu 3,1%."}]}')
        r = self.c.parse_gancho(bruto)
        self.assertEqual(r["frase"], "Perdeu 20,9% do peso.")
        self.assertEqual(len(r["reels"]), 1)
        self.assertEqual(r["reels"][0]["gancho"], "Nao e forca de vontade.")
        self.assertEqual(r["reels"][0]["apoio"], "O comparador perdeu 3,1%.")
        self.assertEqual(r["reels"][0]["roteiro"], [])

    def test_texto_puro_antigo_vira_um_reel(self):
        """Formato legado: o banco de reserva/classicos esta cheio deles."""
        r = self.c.parse_gancho("Fale sobre obesidade como doenca cronica.")
        self.assertEqual(r["frase"], "")
        self.assertEqual(len(r["reels"]), 1)
        self.assertEqual(r["reels"][0]["gancho"], "Fale sobre obesidade como doenca cronica.")
        self.assertEqual(r["reels"][0]["apoio"], "")

    def test_vazio_nao_quebra(self):
        for entrada in ("", None, "   "):
            r = self.c.parse_gancho(entrada)
            self.assertEqual(r["frase"], "")
            self.assertEqual(r["reels"], [])

    def test_json_so_com_frase(self):
        r = self.c.parse_gancho('{"frase": "So a frase."}')
        self.assertEqual(r["frase"], "So a frase.")
        self.assertEqual(r["reels"], [])

    def test_item_sem_apoio(self):
        r = self.c.parse_gancho('{"reels": [{"gancho": "So o gancho."}]}')
        self.assertEqual(r["reels"][0]["apoio"], "")

    def test_corta_em_tres(self):
        """A IA vai extrapolar alguma hora; nao pode virar bloco gigante no PDF."""
        itens = ",".join('{"gancho": "a%d"}' % i for i in range(5))
        r = self.c.parse_gancho('{"reels": [%s]}' % itens)
        self.assertEqual(len(r["reels"]), 3)

    def test_item_sem_angulo_e_descartado(self):
        r = self.c.parse_gancho('{"reels": [{"apoio": "orfao"}, {"angulo": "bom"}]}')
        self.assertEqual(len(r["reels"]), 1)
        self.assertEqual(r["reels"][0]["gancho"], "bom")

    def test_nunca_imprime_none(self):
        r = self.c.parse_gancho('{"frase": null, "reels": [{"angulo": "x", "apoio": null}]}')
        self.assertEqual(r["frase"], "")
        self.assertEqual(r["reels"][0]["apoio"], "")

    def test_json_novo_completo(self):
        bruto = ('{"frase": "A frase do post.",'
                 ' "paciente": "Como eu explico na consulta.",'
                 ' "limites": ["Nao prometa resultado.", "Nao cite marca."],'
                 ' "reels": [{"titulo": "Quando dizem que e psicologico",'
                 '            "gancho": "Se te disseram que era da sua cabeca, escuta isso.",'
                 '            "roteiro": ["Comece contando a situacao.", "Explique o que muda."],'
                 '            "apoio": "47 mulheres na pos-menopausa."}]}')
        r = self.c.parse_gancho(bruto)
        self.assertEqual(r["frase"], "A frase do post.")
        self.assertEqual(r["paciente"], "Como eu explico na consulta.")
        self.assertEqual(r["limites"], ["Nao prometa resultado.", "Nao cite marca."])
        self.assertEqual(len(r["reels"]), 1)
        p = r["reels"][0]
        self.assertEqual(p["titulo"], "Quando dizem que e psicologico")
        self.assertEqual(p["gancho"], "Se te disseram que era da sua cabeca, escuta isso.")
        self.assertEqual(p["roteiro"], ["Comece contando a situacao.", "Explique o que muda."])
        self.assertEqual(p["apoio"], "47 mulheres na pos-menopausa.")

    def test_campos_novos_ausentes_viram_vazio(self):
        """Formato antigo nao tem paciente/limites/titulo/roteiro -- nao pode virar None."""
        r = self.c.parse_gancho('{"reels": [{"angulo": "so o angulo"}]}')
        self.assertEqual(r["paciente"], "")
        self.assertEqual(r["limites"], [])
        self.assertEqual(r["reels"][0]["titulo"], "")
        self.assertEqual(r["reels"][0]["roteiro"], [])

    def test_roteiro_com_lixo_dentro_e_limpo(self):
        r = self.c.parse_gancho(
            '{"reels": [{"gancho": "g", "roteiro": ["passo bom", "", null, "outro"]}]}')
        self.assertEqual(r["reels"][0]["roteiro"], ["passo bom", "outro"])

    def test_roteiro_que_nao_e_lista_nao_quebra(self):
        r = self.c.parse_gancho('{"reels": [{"gancho": "g", "roteiro": "virou string"}]}')
        self.assertEqual(r["reels"][0]["roteiro"], [])

    def test_limites_corta_no_teto(self):
        itens = ",".join('"limite %d"' % i for i in range(9))
        r = self.c.parse_gancho('{"limites": [%s]}' % itens)
        self.assertEqual(len(r["limites"]), self.c.MAX_LIMITES)

    def test_roteiro_corta_no_teto(self):
        passos = ",".join('"passo %d"' % i for i in range(9))
        r = self.c.parse_gancho('{"reels": [{"gancho": "g", "roteiro": [%s]}]}' % passos)
        self.assertEqual(len(r["reels"][0]["roteiro"]), self.c.MAX_PASSOS)

    def test_json_cortado_nao_vira_pauta(self):
        """O defeito que mais dói: com a IA estourando o limite de tokens, o JSON
        chega pela metade, o json.loads falha e o texto bruto virava UMA pauta --
        o PDF imprimia {"frase":... na cara do assinante pagante."""
        cortado = '{"frase": "A frase do post.", "reels": [{"gancho": "Se te disser'
        r = self.c.parse_gancho(cortado)
        self.assertEqual(r["reels"], [], "JSON cortado nao pode virar pauta")
        self.assertEqual(r["frase"], "")

    def test_lista_json_tambem_nao_vira_pauta(self):
        r = self.c.parse_gancho('[{"gancho": "veio lista em vez de objeto"}')
        self.assertEqual(r["reels"], [])

    def test_texto_que_so_comeca_com_chave_no_meio_ainda_vira_pauta(self):
        """Texto legado de verdade nao comeca com { -- so o JSON cortado comeca."""
        r = self.c.parse_gancho("Fale que {isto} nao e JSON.")
        self.assertEqual(len(r["reels"]), 1)

    def test_reels_com_tipo_errado_nao_levanta(self):
        """Se `reels` vier como numero, booleano, string ou dict em vez de lista,
        deve devolver reels: [] sem levantar TypeError. Esta protecao e critica
        porque a funcao roda no caminho do PDF diario, sem try/except em volta."""
        for reels_invalido in (5, True, False, 3.14, "uma string", {"dict": "orfao"}):
            r = self.c.parse_gancho('{"reels": %s}' % json.dumps(reels_invalido))
            self.assertEqual(r["reels"], [],
                           "reels: %s nao pode levantar, deve devolver []" % type(reels_invalido).__name__)


class TestKitHtml(unittest.TestCase):
    def setUp(self):
        import pdf
        self.pdf = pdf
        self.artigo = {"titulo_original": "Tirzepatide Once Weekly for Obesity",
                       "titulo": "Tirzepatida semanal para obesidade",
                       "fonte": "N Engl J Med", "data": "2022", "doi": "10.1056/NEJMoa2206038"}
        self.gancho = ('{"frase": "Perdeu 20,9% do peso em 72 semanas.",'
                       ' "reels": [{"angulo": "Nao e forca de vontade.", "apoio": "O comparador perdeu 3,1%."},'
                       '           {"angulo": "Nao acontece em um mes.", "apoio": "Foram 72 semanas."}]}')

    def test_mostra_titulo_original_em_ingles(self):
        html = self.pdf._kit_html(self.gancho, self.artigo)
        self.assertIn("Tirzepatide Once Weekly for Obesity", html)
        self.assertNotIn("Tirzepatida semanal", html)     # o pt fica no topo do PDF, nao aqui

    def test_cai_para_titulo_quando_nao_ha_original(self):
        art = dict(self.artigo)
        del art["titulo_original"]
        html = self.pdf._kit_html(self.gancho, art)
        self.assertIn("Tirzepatida semanal para obesidade", html)

    def test_mostra_frase_e_os_reels(self):
        html = self.pdf._kit_html(self.gancho, self.artigo)
        self.assertIn("Perdeu 20,9% do peso em 72 semanas.", html)
        self.assertIn("Nao e forca de vontade.", html)
        self.assertIn("Nao acontece em um mes.", html)
        self.assertIn("O comparador perdeu 3,1%.", html)

    def test_um_reel_so_renderiza_igual_bem(self):
        """Caso ESPERADO agora (o prompt prefere menos): nao pode sobrar item vazio."""
        html = self.pdf._kit_html('{"reels": [{"angulo": "Unico."}]}', self.artigo)
        self.assertEqual(html.count('class="reel"'), 1)
        self.assertNotIn("None", html)

    def test_texto_legado_nao_quebra(self):
        html = self.pdf._kit_html("Fale sobre obesidade como doenca cronica.", self.artigo)
        self.assertIn("Fale sobre obesidade como doenca cronica.", html)
        self.assertNotIn("None", html)

    def test_gancho_vazio_ainda_mostra_o_cartao_do_estudo(self):
        """O recorte do paper vale por si so, mesmo sem texto de IA."""
        html = self.pdf._kit_html("", self.artigo)
        self.assertIn("Tirzepatide Once Weekly for Obesity", html)

    def test_sem_gancho_e_sem_estudo_devolve_vazio(self):
        self.assertEqual(self.pdf._kit_html("", {}), "")

    def test_escapa_html_do_conteudo(self):
        art = dict(self.artigo, titulo_original="A <script>alert(1)</script> B")
        html = self.pdf._kit_html("", art)
        self.assertNotIn("<script>", html)


class TestMontarHtmlKit(unittest.TestCase):
    def setUp(self):
        import pdf
        self.pdf = pdf
        self.artigo = {"titulo": "Tirzepatide Once Weekly", "fonte": "NEJM", "data": "2022",
                       "doi": "10.1056/x", "url": "https://doi.org/10.1056/x", "tema": "Obesidade"}
        self.conteudo = {"titulo_pt": "Tirzepatida semanal", "resumo": "Resumo.",
                         "gancho": '{"frase": "A frase.", "reels": [{"angulo": "Angulo."}]}',
                         "grafico": None}
        self.tema = {"cor": "#14332a", "rotulo": "Obesidade"}

    def test_kit_entra_no_pdf(self):
        html = self.pdf.montar_html(self.artigo, self.conteudo, self.tema)
        self.assertIn("A frase.", html)
        self.assertIn("Angulo.", html)
        self.assertIn("Tirzepatide Once Weekly", html)

    def test_referencia_vira_link_clicavel(self):
        """Chromium --print-to-pdf preserva hyperlink; texto puro nao clica."""
        html = self.pdf.montar_html(self.artigo, self.conteudo, self.tema)
        self.assertIn('<a href="https://doi.org/10.1056/x"', html)

    def test_sem_url_nao_gera_link_vazio(self):
        art = dict(self.artigo, url="")
        html = self.pdf.montar_html(art, self.conteudo, self.tema)
        self.assertNotIn('<a href=""', html)


class TestPromptGancho(unittest.TestCase):
    def setUp(self):
        import content
        self.c = content

    def test_prompt_pede_json_com_frase_e_reels(self):
        s = self.c.SYS_GANCHO
        self.assertIn("frase", s)
        self.assertIn("reels", s)
        self.assertIn("gancho", s)

    def test_prompt_proibe_completar_cota(self):
        """Modelo de IA preenche ate o numero pedido; o 3o sai inventado."""
        s = self.c.SYS_GANCHO.lower()
        self.assertIn("1 a 3", s)
        self.assertTrue("nunca invente" in s or "nao invente" in s)

    def test_prompt_descreve_o_schema_novo(self):
        for chave in ('"paciente"', '"limites"', '"gancho"', '"roteiro"', '"titulo"'):
            self.assertIn(chave, self.c.SYS_GANCHO, f"schema sem {chave}")

    def test_prompt_manda_falar_com_o_paciente_e_proibe_metodologia(self):
        s = self.c.SYS_GANCHO.lower()
        self.assertIn("paciente", s)
        self.assertIn("metodologia", s)
        self.assertIn("comparador", s)

    def test_prompt_proibe_jargao_de_marketing(self):
        """O texto gerado ia com 'nomeia a cena'/'vira a chave' -- quem le e medico
        ou social media, nao publicitario."""
        s = self.c.SYS_GANCHO.lower()
        for termo in ("nomeia a cena", "vira a chave", "prova por baixo"):
            self.assertIn(termo, s, f"o prompt precisa PROIBIR '{termo}' pelo nome")

    def test_prompt_mantem_as_travas_do_cfm(self):
        s = self.c.SYS_GANCHO.lower()
        for termo in ("cfm", "receita", "resultado"):
            self.assertIn(termo, s)

    def test_teto_de_tokens_cabe_na_saida_real(self):
        """Saida real medida: 934 tokens. Com 900 o JSON chega cortado."""
        import inspect
        fonte = inspect.getsource(self.c.gerar_conteudo)
        self.assertIn("SYS_GANCHO", fonte)
        self.assertNotIn("max_tokens=900", fonte)
        self.assertIn("max_tokens=2500", fonte)

    def test_gerar_conteudo_devolve_gancho_parseavel(self):
        falso = '{"frase": "F", "reels": [{"angulo": "A", "apoio": "B"}]}'
        r = self.c.gerar_conteudo({"titulo": "t", "resumo": "r", "fonte": "f"},
                                  gerar_resumo=lambda a: "resumo",
                                  gerar_gancho=lambda a: falso,
                                  gerar_grafico_json=lambda a: "{}",
                                  gerar_titulo=lambda a: "titulo")
        self.assertEqual(self.c.parse_gancho(r["gancho"])["frase"], "F")


class TestKitNoSite(unittest.TestCase):
    def test_pagina_digest_mostra_o_kit(self):
        import site_web
        d = {"titulo_pt": "Tirzepatida semanal", "titulo_original": "Tirzepatide Once Weekly",
             "fonte": "NEJM", "data": "2026-08-04", "doi": "10.1056/x", "url": "https://x",
             "resumo": "Resumo.", "grafico": None,
             "gancho": '{"frase": "A frase.", "reels": [{"angulo": "Angulo."}]}'}
        html = site_web.pagina_digest({"rotulo": "Obesidade", "emoji": "", "slug": "obesidade", "cor": "#14332a"}, d)
        self.assertIn("A frase.", html)
        self.assertIn("Angulo.", html)
        self.assertIn("Tirzepatide Once Weekly", html)

    def test_site_tem_o_css_do_kit(self):
        """O site tem copia PROPRIA do CSS do PDF: sem estas classes o kit sai sem estilo."""
        import site_web
        d = {"titulo_pt": "T", "titulo_original": "T EN", "fonte": "NEJM", "data": "2026-08-04",
             "doi": "x", "url": "https://x", "resumo": "r", "grafico": None,
             "gancho": '{"frase": "F", "reels": [{"angulo": "A"}]}'}
        html = site_web.pagina_digest({"rotulo": "Obesidade", "emoji": "", "slug": "obesidade", "cor": "#14332a"}, d)
        for classe in (".paper-box{", ".frase-box{", ".reels{", ".reel-n{"):
            self.assertIn(classe, html, classe)


class TestTituloOriginal(unittest.TestCase):
    """O cartao do estudo mostra o titulo em INGLES, e ele se perdia: `art["titulo"]`
    vira titulo_pt nos caminhos de reserva/classico/regeracao (daily.py:274/:319/:392)."""

    def setUp(self):
        import tempfile, importlib
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import config, db
        importlib.reload(config)
        importlib.reload(db)
        self.db = db
        db.init()

    def test_digest_guarda_o_titulo_original(self):
        art = {"tema": "Obesidade", "titulo": "Tirzepatide Once Weekly",
               "titulo_original": "Tirzepatide Once Weekly",
               "fonte": "NEJM", "doi": "10.1056/x", "url": "https://x"}
        self.db.registrar_digest(art, {"titulo_pt": "Tirzepatida semanal", "resumo": "r",
                                       "gancho": "", "grafico": None}, data="2026-08-04")
        d = self.db.digest_do_dia("2026-08-04")
        self.assertEqual(d["titulo_original"], "Tirzepatide Once Weekly")

    def test_digest_cai_para_titulo_quando_nao_ha_original(self):
        """Caminho do candidato: `titulo` ja e o original em ingles."""
        art = {"tema": "Obesidade", "titulo": "Original In English",
               "fonte": "NEJM", "doi": "10.1056/y", "url": "https://y"}
        self.db.registrar_digest(art, {"titulo_pt": "Titulo em portugues", "resumo": "r",
                                       "gancho": "", "grafico": None}, data="2026-08-05")
        self.assertEqual(self.db.digest_do_dia("2026-08-05")["titulo_original"],
                         "Original In English")


if __name__ == "__main__":
    unittest.main()
