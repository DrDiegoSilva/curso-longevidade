"""Testes de app/pdf_trilha.py — a capa nova, o icone DS, e os blocos maiores."""
import base64
import os
import re
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _decodifica_png(b64):
    """Le os primeiros bytes e confirma que e' PNG de verdade, sem precisar de Pillow."""
    bruto = base64.b64decode(b64)
    assinatura_png = b"\x89PNG\r\n\x1a\n"
    return bruto[:8] == assinatura_png, bruto


class TestIconeDS(unittest.TestCase):
    def test_e_um_png_valido(self):
        import pdf_trilha
        ok, bruto = _decodifica_png(pdf_trilha._ICONE_DS_B64)
        self.assertTrue(ok, "a constante nao decodifica pra um PNG valido")
        self.assertGreater(len(bruto), 1000, "arquivo suspeito de pequeno/truncado")

    def test_tem_canal_alfa_com_transparencia_real(self):
        """O PNG precisa ser RGBA com pixel(s) realmente transparente(s) — e' o que
        permite compor o icone sobre a banda verde sem caixa branca ao redor.
        Checagem sem Pillow: o PNG usa chunk IHDR pra declarar o tipo de cor; tipo 6
        = RGBA. Basta olhar o byte de "color type" no cabecalho IHDR."""
        import pdf_trilha
        _, bruto = _decodifica_png(pdf_trilha._ICONE_DS_B64)
        # IHDR comeca no byte 8 (assinatura) + 4 (tamanho do chunk) + 4 ("IHDR") = 16
        # width(4) height(4) bitdepth(1) colortype(1) ...
        color_type = bruto[16 + 9]
        self.assertEqual(color_type, 6, "PNG nao e' RGBA (color type 6) — sem alfa")

    def test_constante_e_identica_ao_arquivo_fonte(self):
        """Valida byte a byte que a constante esta' igual ao arquivo fonte .b64"""
        caminho = os.path.join(os.path.dirname(__file__), "..", "..",
                               "docs", "superpowers", "specs", "assets",
                               "2026-08-19-ds-mark-icone.b64")
        with open(caminho) as f:
            fonte = f.read().strip()
        import pdf_trilha
        self.assertEqual(pdf_trilha._ICONE_DS_B64, fonte, "constante diverge do arquivo fonte")


def _peca(numero=1, titulo="O custo real da sua hora", eixo="Saber onde você está",
          corpo="Texto do corpo.", micro_resultado="A tarefa.", mentalidade="A mentalidade.",
          ferramenta_slug="planilha-x", produto="empreendedorismo"):
    return {"numero": numero, "titulo": titulo, "eixo": eixo, "corpo": corpo,
            "micro_resultado": micro_resultado, "mentalidade": mentalidade,
            "ferramenta_slug": ferramenta_slug, "produto": produto}


class TestCapaNova(unittest.TestCase):
    def _html(self, **kw):
        import pdf_trilha
        return pdf_trilha.montar_html(_peca(**kw), "Dr. Diego",
                                      link_ferramenta="https://ex.com/f")

    def test_tem_a_banda_verde(self):
        h = self._html()
        self.assertIn("linear-gradient(120deg,#0e211a,#1e5045)", h)

    def test_tem_o_icone_embutido(self):
        import pdf_trilha
        h = self._html()
        self.assertIn(f'src="data:image/png;base64,{pdf_trilha._ICONE_DS_B64}"', h)

    def test_tem_o_nome_do_medico(self):
        h = self._html()
        self.assertIn('<span class="capa-nome">Dr. Diego Silva</span>', h)

    def test_tem_o_selo_da_semana(self):
        h = self._html(numero=3)
        self.assertIn('<span class="capa-selo">Semana 3 de 12</span>', h)

    def test_tem_o_nome_do_produto_embaixo(self):
        h = self._html()
        self.assertIn('<div class="capa-produto">Trilha do Consultório Lucrativo</div>', h)

    def test_sem_selo_de_tema(self):
        """Decisao explicita do Diego — nao existe campo de categoria por peca.

        A versao antiga deste teste procurava a string literal "Mentalidade</div>",
        o que nao prova nada: o markup real usa <p>/<span>, nunca uma <div> fechando
        logo apos "Mentalidade" (o rotulo do bloco fica em <p class="rot">Mentalidade
        </p>, nao em <div>Mentalidade</div>). Um selo de tema de verdade, tipo
        <span class="capa-tema">Mentalidade</span>, passava batido.

        A forma robusta e' ancorar no conjunto FECHADO de classes "capa-*" que a capa
        realmente usa hoje (capa-topo, capa-assinatura, capa-icone, capa-nome,
        capa-selo, capa-produto — nenhuma delas e' selo de categoria/tema). Qualquer
        classe nova com esse prefixo — capa-tema, capa-tag, capa-categoria ou outra —
        quebra este teste, porque o conjunto deixa de bater."""
        h = self._html()
        classes_capa = re.findall(r'class="capa-[a-z-]*"', h)
        self.assertEqual(
            set(classes_capa),
            {'class="capa-topo"', 'class="capa-assinatura"', 'class="capa-icone"',
             'class="capa-nome"', 'class="capa-selo"', 'class="capa-produto"'},
            "apareceu uma classe capa-* nova na capa — se for selo de tema, e' a "
            "regressao que este teste existe pra pegar",
        )

    def test_a_capa_esta_fora_do_wrapper_de_margem(self):
        """A tecnica de sangria exige que .capa fique FORA de .pagina (senao herda a
        margem lateral e para de bater de ponta a ponta)."""
        h = self._html()
        pos_capa = h.index('<div class="capa">')
        pos_pagina = h.index('<div class="pagina">')
        self.assertLess(pos_capa, pos_pagina)
        # o </div> que fecha .capa tem que vir ANTES da abertura de .pagina
        fim_capa = h.index("</div>", h.index('<div class="capa-produto">'))
        self.assertLess(fim_capa, pos_pagina)

    def test_titulo_e_corpo_continuam_depois_da_capa(self):
        h = self._html(titulo="Título Teste")
        self.assertIn("<h1>Título Teste</h1>", h)

    def test_numero_e_nome_vao_escapados(self):
        """Defesa em profundidade: config.TRILHAS[produto]["nome"] e' hoje um valor de config,
        nao entrada de usuario por requisicao — mas continua indo por _esc, como todo campo aqui."""
        import config
        import pdf_trilha
        with mock.patch.dict(config.TRILHAS["empreendedorismo"], {"nome": '<script>alert(1)</script>'}):
            h = pdf_trilha.montar_html(_peca(), "Dr. Diego")
        self.assertNotIn("<script>alert(1)</script>", h)
        self.assertIn("&lt;script&gt;", h)

    def test_numero_tambem_vai_escapado(self):
        """O teste acima cobria TRILHA_NOME — este cobre o escape do proprio numero da semana."""
        import pdf_trilha
        h = pdf_trilha.montar_html(_peca(numero='<script>alert(2)</script>'), "Dr. Diego")
        self.assertNotIn("<script>alert(2)</script>", h)
        self.assertIn("&lt;script&gt;", h)


class TestTipografiaMaisJusta(unittest.TestCase):
    """Prova a alegacao do spec (secao 4): margem/entrelinha reduzidas, SEM tocar em
    nenhum font-size de texto de leitura. font-size do body continua ausente de proposito
    (herda o padrao do navegador) — se algum dia alguem adicionar um font-size aqui pra
    'resolver' a pagina 2, e' a troca errada que o Diego recusou; este teste segura isso."""

    def test_pagina_sem_margem_lateral_no_page_rule(self):
        import pdf_trilha
        self.assertIn("margin: 15mm 0 13mm", pdf_trilha._CSS)

    def test_entrelinha_do_corpo_e_1_5(self):
        import pdf_trilha
        self.assertIn("line-height: 1.5;", pdf_trilha._CSS)

    def test_paragrafo_do_corpo_tem_margem_reduzida(self):
        import pdf_trilha
        self.assertIn(".corpo p { margin: 0 0 9px; }", pdf_trilha._CSS)

    def test_item_de_lista_tem_margem_reduzida(self):
        import pdf_trilha
        self.assertIn("li { margin: 0 0 4px; }", pdf_trilha._CSS)

    def test_body_nao_declara_font_size_proprio(self):
        """O corpo continua no tamanho padrao do navegador — nenhuma letra encolheu."""
        import re
        import pdf_trilha
        regra_body = re.search(r"\bbody\s*\{([^}]*)\}", pdf_trilha._CSS)
        self.assertIsNotNone(regra_body)
        self.assertNotIn("font-size", regra_body.group(1))

    def test_body_sem_margem_propria(self):
        """Sem isto a banda ganha moldura branca nas laterais e no topo — visto de
        verdade num render real durante a revisao. Ancora no CONTEUDO da regra `body`
        (mesma tecnica do teste de font-size acima), nao na formatacao exata do bloco,
        pra nao quebrar por causa de quebra de linha ou espacamento."""
        import re
        import pdf_trilha
        regra_body = re.search(r"\bbody\s*\{([^}]*)\}", pdf_trilha._CSS)
        self.assertIsNotNone(regra_body)
        self.assertIn("margin: 0", regra_body.group(1))

    def test_primeira_pagina_sem_margem_no_topo(self):
        """Sem isto sobra uma faixa branca de 15mm acima da capa — visto de verdade
        num render real durante a revisao."""
        import pdf_trilha
        self.assertIn("@page :first { margin-top: 0; }", pdf_trilha._CSS)


class TestBlocosMaiores(unittest.TestCase):
    def test_bloco_tem_borda_dourada_a_esquerda(self):
        import pdf_trilha
        self.assertIn("border-left: 4px solid #c9a227", pdf_trilha._CSS)

    def test_bloco_tem_fundo_creme(self):
        import pdf_trilha
        self.assertIn("background: #fdfbf5", pdf_trilha._CSS)

    def test_bloco_tem_padding_maior(self):
        import pdf_trilha
        self.assertIn("padding: 22px 26px", pdf_trilha._CSS)

    def test_texto_do_bloco_e_maior_que_o_corpo(self):
        """O corpo continua no tamanho padrao (sem font-size explicito = herda do body);
        o texto DENTRO do bloco agora e' explicitamente maior (15px) — e' o oposto de
        'apertar a letra': aqui a letra de destaque CRESCE."""
        import pdf_trilha
        self.assertIn(".bloco p { margin: 0; font-size: 15px; line-height: 1.6; }",
                      pdf_trilha._CSS.replace("\n", " ").replace("  ", " "))

    def test_o_rotulo_do_bloco_ficou_mais_espacoso(self):
        import pdf_trilha
        self.assertIn("letter-spacing: .18em", pdf_trilha._CSS)
        self.assertIn("font-weight: 700", pdf_trilha._CSS)

    def test_bloco_nao_e_fatiado_pela_quebra_de_pagina(self):
        """Sem isto, um `.bloco` que cai perto do fim da pagina e' cortado ao meio
        pela quebra — visto de verdade num render real das 12 pecas da trilha
        (peca 7, card "Mentalidade"). Com o fundo creme + trilho dourado (Task 4),
        o corte fica muito mais visivel do que era antes."""
        import pdf_trilha
        self.assertIn("break-inside: avoid", pdf_trilha._CSS)

    def test_margem_entre_blocos_e_enxuta(self):
        """Renderizando as 12 pecas reais com Chromium: com a margem antiga (26px
        entre blocos + 24px antes do rodape), as pecas 04 e 07 tinham o bloco
        "Mentalidade" cabendo certinho na pagina 2, mas so' a LINHA do rodape
        vazava pra uma pagina 3 quase inteira em branco (~97% vazia). Encolher
        essa margem devolve as 2 pecas pra 2 paginas sem tocar em nenhum
        font-size nem no padding interno do bloco (que continuam intocados)."""
        import pdf_trilha
        self.assertIn("margin: 8px 0 0", pdf_trilha._CSS)

    def test_margem_do_rodape_e_enxuta(self):
        import pdf_trilha
        self.assertIn(".rodape { margin-top: 4px", pdf_trilha._CSS)
