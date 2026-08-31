"""Testes da trilha semanal de empreendedorismo médico. Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _recarregar(tmp):
    """Isola config/db/subscribers/trilha num banco temporário."""
    os.environ["DSCURSO_DATA"] = tmp
    os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(tmp, "t.db")
    for m in ("config", "db", "subscribers", "trilha"):
        if m in sys.modules:
            importlib.reload(sys.modules[m])
    import config, db, subscribers
    importlib.reload(config); importlib.reload(db); importlib.reload(subscribers)
    subscribers._migrado = False
    db.init()
    return config, db, subscribers


class TestBancoTrilha(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg, self.db, self.subs = _recarregar(self.tmp)

    def _peca(self, produto="empreendedorismo", numero=1):
        self.db.trilha_upsert_peca(produto, numero, "Saber onde você está", f"Peça {numero}",
                                   "corpo", "micro", "mentalidade", "", "")

    def test_upsert_peca_grava_e_le(self):
        self._peca()
        p = self.db.trilha_peca("empreendedorismo", 1)
        self.assertEqual(p["titulo"], "Peça 1")
        self.assertEqual(p["micro_resultado"], "micro")
        self.assertEqual(p["produto"], "empreendedorismo")

    def test_upsert_peca_atualiza_em_vez_de_duplicar(self):
        self._peca()
        self.db.trilha_upsert_peca("empreendedorismo", 1, "eixo novo", "Título novo",
                                   "c", "m", "t", "", "")
        self.assertEqual(self.db.trilha_peca("empreendedorismo", 1)["titulo"], "Título novo")

    def test_dois_produtos_podem_usar_o_mesmo_numero(self):
        # a razão de existir do `produto` na chave: sem ele, a peça 1 de
        # "peptideos" pisaria na peça 1 de "empreendedorismo".
        self._peca("empreendedorismo", 1)
        self.db.trilha_upsert_peca("peptideos", 1, "eixo", "Peça peptídeo 1",
                                   "corpo p", "", "", "aviso p", "")
        self.assertEqual(self.db.trilha_peca("empreendedorismo", 1)["titulo"], "Peça 1")
        self.assertEqual(self.db.trilha_peca("peptideos", 1)["titulo"], "Peça peptídeo 1")
        self.assertEqual(self.db.trilha_peca("peptideos", 1)["aviso"], "aviso p")

    def test_peca_inexistente_devolve_none(self):
        self.assertIsNone(self.db.trilha_peca("empreendedorismo", 13))

    def test_posicao_nasce_em_1(self):
        self.assertEqual(self.db.trilha_posicao("sub-a", "empreendedorismo"), 1)

    def test_posicao_leitura_nao_cria_linha_quando_nunca_comecou(self):
        self.assertIsNone(self.db.trilha_posicao_leitura("sub-a", "peptideos"))
        # confirma que NÃO criou linha (senão a próxima leitura devolveria 1, não None)
        self.assertIsNone(self.db.trilha_posicao_leitura("sub-a", "peptideos"))

    def test_posicao_leitura_reflete_avanco(self):
        self.db.trilha_avancar("sub-a", "empreendedorismo", 1)
        self.assertEqual(self.db.trilha_posicao_leitura("sub-a", "empreendedorismo"), 2)

    def test_registrar_envio_e_idempotente(self):
        self.assertTrue(self.db.trilha_registrar_envio("sub-a", "empreendedorismo", 1))
        self.assertFalse(self.db.trilha_registrar_envio("sub-a", "empreendedorismo", 1))
        self.assertTrue(self.db.trilha_registrar_envio("sub-a", "empreendedorismo", 2))
        self.assertTrue(self.db.trilha_registrar_envio("sub-b", "empreendedorismo", 1))
        # mesmo numero, produto diferente -- não é a mesma linha
        self.assertTrue(self.db.trilha_registrar_envio("sub-a", "peptideos", 1))

    def test_avancar_move_a_posicao(self):
        self.db.trilha_avancar("sub-a", "empreendedorismo", 1)
        self.assertEqual(self.db.trilha_posicao("sub-a", "empreendedorismo"), 2)

    def test_marcar_feito_e_idempotente(self):
        self.db.trilha_registrar_envio("sub-a", "empreendedorismo", 1)
        self.assertFalse(self.db.trilha_fez("sub-a", "empreendedorismo", 1))
        self.assertTrue(self.db.trilha_marcar_feito("sub-a", "empreendedorismo", 1))
        self.assertTrue(self.db.trilha_fez("sub-a", "empreendedorismo", 1))
        self.assertFalse(self.db.trilha_marcar_feito("sub-a", "empreendedorismo", 1))

    def test_marcar_feito_em_peca_nao_enviada_nao_grava(self):
        self.assertFalse(self.db.trilha_marcar_feito("sub-a", "empreendedorismo", 7))
        self.assertFalse(self.db.trilha_fez("sub-a", "empreendedorismo", 7))

    def test_historico_vem_do_mais_recente(self):
        self.db.trilha_registrar_envio("sub-a", "empreendedorismo", 1)
        self.db.trilha_registrar_envio("sub-a", "empreendedorismo", 2)
        h = self.db.trilha_historico("sub-a", "empreendedorismo")
        self.assertEqual([x["numero"] for x in h], [2, 1])

    def test_historico_nao_mistura_produtos(self):
        self.db.trilha_registrar_envio("sub-a", "empreendedorismo", 1)
        self.db.trilha_registrar_envio("sub-a", "peptideos", 1)
        self.assertEqual(len(self.db.trilha_historico("sub-a", "empreendedorismo")), 1)
        self.assertEqual(len(self.db.trilha_historico("sub-a", "peptideos")), 1)

    def test_painel_conta_enviadas_e_feitas(self):
        self.db.trilha_registrar_envio("sub-a", "empreendedorismo", 1)
        self.db.trilha_registrar_envio("sub-a", "empreendedorismo", 2)
        self.db.trilha_marcar_feito("sub-a", "empreendedorismo", 1)
        self.db.trilha_avancar("sub-a", "empreendedorismo", 2)
        linha = [l for l in self.db.trilha_painel("empreendedorismo")
                if l["subscriber_id"] == "sub-a"][0]
        self.assertEqual(linha["enviadas"], 2)
        self.assertEqual(linha["feitas"], 1)
        self.assertEqual(linha["proxima_peca"], 3)

    def test_painel_nao_mistura_produtos(self):
        self.db.trilha_registrar_envio("sub-a", "empreendedorismo", 1)
        self.db.trilha_registrar_envio("sub-a", "peptideos", 1)
        self.db.trilha_registrar_envio("sub-a", "peptideos", 2)
        linha_pep = [l for l in self.db.trilha_painel("peptideos")
                    if l["subscriber_id"] == "sub-a"][0]
        self.assertEqual(linha_pep["enviadas"], 2)

    def test_tabelas_novas_estao_na_lista_de_rls(self):
        for t in ("trilha_pecas", "trilha_progresso", "trilha_envios"):
            self.assertIn(t, self.db._TABELAS)


class TestParseESeed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg, self.db, self.subs = _recarregar(self.tmp)
        import trilha
        importlib.reload(trilha)
        self.t = trilha

    def test_parse_le_cabecalho_e_secoes(self):
        p = self.t.parse_peca(
            "titulo: O custo real da sua hora\n"
            "eixo: Saber onde você está\n"
            "ferramenta: planilha-custo-hora\n"
            "\n"
            "## corpo\n"
            "Primeiro parágrafo.\n"
            "\n"
            "Segundo parágrafo.\n"
            "\n"
            "## micro-resultado\n"
            "Calcule o custo da sua hora.\n"
            "\n"
            "## mentalidade\n"
            "Empenho é diferente de desempenho.\n")
        self.assertEqual(p["titulo"], "O custo real da sua hora")
        self.assertEqual(p["eixo"], "Saber onde você está")
        self.assertEqual(p["ferramenta"], "planilha-custo-hora")
        self.assertIn("Segundo parágrafo.", p["corpo"])
        self.assertEqual(p["micro_resultado"], "Calcule o custo da sua hora.")
        self.assertEqual(p["mentalidade"], "Empenho é diferente de desempenho.")
        self.assertEqual(p["aviso"], "")

    def test_parse_le_secao_aviso(self):
        p = self.t.parse_peca(
            "titulo: GHK-Cu\neixo: Reparo de pele\n\n"
            "## corpo\ntexto\n\n"
            "## aviso\n"
            "A Anvisa nomeou o GHK-Cu injetável como ilegal para qualquer uso em saúde.\n")
        self.assertIn("ilegal", p["aviso"])

    def test_parse_sem_ferramenta_devolve_vazio(self):
        p = self.t.parse_peca("titulo: X\neixo: Y\n\n## corpo\nz\n")
        self.assertEqual(p["ferramenta"], "")
        self.assertEqual(p["micro_resultado"], "")

    def test_semear_produto_grava_as_pecas_do_diretorio(self):
        d = os.path.join(self.tmp, "trilha")
        os.makedirs(d)
        with open(os.path.join(d, "01-um.md"), "w", encoding="utf-8") as f:
            f.write("titulo: Um\neixo: A\n\n## corpo\ncorpo um\n")
        with open(os.path.join(d, "02-dois.md"), "w", encoding="utf-8") as f:
            f.write("titulo: Dois\neixo: A\n\n## corpo\ncorpo dois\n")
        self.assertEqual(self.t.semear_produto("empreendedorismo", d), 2)
        self.assertEqual(self.db.trilha_peca("empreendedorismo", 1)["titulo"], "Um")
        self.assertEqual(self.db.trilha_peca("empreendedorismo", 2)["titulo"], "Dois")

    def test_semear_produto_e_idempotente_e_atualiza_texto_editado(self):
        d = os.path.join(self.tmp, "trilha")
        os.makedirs(d)
        caminho = os.path.join(d, "01-um.md")
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("titulo: Um\neixo: A\n\n## corpo\nversao 1\n")
        self.t.semear_produto("empreendedorismo", d)
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("titulo: Um\neixo: A\n\n## corpo\nversao 2\n")
        self.t.semear_produto("empreendedorismo", d)
        self.assertIn("versao 2", self.db.trilha_peca("empreendedorismo", 1)["corpo"])

    def test_semear_produto_ignora_arquivo_sem_numero_no_nome(self):
        d = os.path.join(self.tmp, "trilha")
        os.makedirs(d)
        with open(os.path.join(d, "leiame.md"), "w", encoding="utf-8") as f:
            f.write("titulo: X\n\n## corpo\ny\n")
        self.assertEqual(self.t.semear_produto("empreendedorismo", d), 0)

    def test_semear_produto_diretorio_inexistente_nao_quebra(self):
        self.assertEqual(self.t.semear_produto("empreendedorismo",
                                               os.path.join(self.tmp, "nao-existe")), 0)

    def test_semear_roda_todos_os_produtos_do_catalogo(self):
        contagens = self.t.semear()
        self.assertEqual(contagens["empreendedorismo"], self.cfg.TRILHAS["empreendedorismo"]["total"])
        # "peptideos" ainda não tem conteúdo escrito -- 0 é o resultado correto,
        # não um erro (mesmo comportamento de diretório vazio/ausente).
        self.assertEqual(contagens.get("peptideos", 0), 0)

    def test_as_12_pecas_do_repo_carregam(self):
        contagens = self.t.semear()
        for n in range(1, self.cfg.TRILHAS["empreendedorismo"]["total"] + 1):
            p = self.db.trilha_peca("empreendedorismo", n)
            self.assertIsNotNone(p, f"peça {n} não carregou")
            self.assertTrue(p["titulo"].strip(), f"peça {n} sem título")

    def test_semear_avisa_quando_produto_exige_aviso_e_peca_nao_tem(self):
        d = os.path.join(self.tmp, "peptideos")
        os.makedirs(d)
        with open(os.path.join(d, "01-um.md"), "w", encoding="utf-8") as f:
            f.write("titulo: Sem aviso\neixo: A\n\n## corpo\ntexto\n")
        os.environ["DSCURSO_PEPTIDEOS_DIR"] = d
        import config
        importlib.reload(config)
        importlib.reload(self.t)
        try:
            with _CapturaPrint() as saida:
                self.t.semear()
            self.assertIn("sem `aviso`", saida.texto)
            self.assertIn("1", saida.texto)
        finally:
            os.environ.pop("DSCURSO_PEPTIDEOS_DIR", None)


class _CapturaPrint:
    """Captura stdout pra checar o aviso de log de `semear()` sem depender de
    `logging` (o repo usa `print(..., flush=True)` em toda parte)."""
    def __enter__(self):
        import io, contextlib
        self._redirect = contextlib.redirect_stdout(io.StringIO())
        self._buf = self._redirect.__enter__()
        self.texto = ""
        return self

    def __exit__(self, *exc):
        self.texto = self._buf.getvalue()
        self._redirect.__exit__(*exc)


class TestDrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg, self.db, self.subs = _recarregar(self.tmp)
        import trilha
        importlib.reload(trilha)
        self.t = trilha
        self.t.semear()
        self.t.definir_produto_ativo("empreendedorismo")

    def test_dia_da_trilha_e_sabado(self):
        from datetime import date
        self.assertTrue(self.t.e_dia_da_trilha(date(2026, 8, 8)))     # sábado
        self.assertFalse(self.t.e_dia_da_trilha(date(2026, 8, 7)))    # sexta
        self.assertFalse(self.t.e_dia_da_trilha(date(2026, 8, 9)))    # domingo

    def test_assinante_novo_recebe_a_peca_1(self):
        peca = self.t.proxima_peca("sub-a")
        self.assertEqual(peca["numero"], 1)
        self.assertEqual(peca["produto"], "empreendedorismo")

    def test_peca_nao_avanca_sozinha(self):
        self.assertEqual(self.t.proxima_peca("sub-a")["numero"], 1)
        self.assertEqual(self.t.proxima_peca("sub-a")["numero"], 1)

    def test_avanco_leva_a_proxima(self):
        self.db.trilha_avancar("sub-a", "empreendedorismo", 1)
        self.assertEqual(self.t.proxima_peca("sub-a")["numero"], 2)

    def test_quem_concluiu_e_sem_produto_ativo_nao_tem_proxima(self):
        self.db.trilha_avancar("sub-a", "empreendedorismo", self.cfg.TRILHAS["empreendedorismo"]["total"])
        self.t.definir_produto_ativo("")
        self.assertIsNone(self.t.proxima_peca("sub-a"))

    def test_quem_conclui_cai_na_proxima_trilha_ativa(self):
        self.db.trilha_avancar("sub-a", "empreendedorismo", self.cfg.TRILHAS["empreendedorismo"]["total"])
        self.t.definir_produto_ativo("peptideos")
        produto = self.t.produto_do_assinante("sub-a")
        self.assertEqual(produto, "peptideos")

    def test_abertura_da_peca_1_nao_cobra_nada(self):
        self.assertEqual(self.t.abertura("sub-a", "empreendedorismo", 1), "")

    def test_abertura_reconhece_quem_fez(self):
        self.db.trilha_registrar_envio("sub-a", "empreendedorismo", 1)
        self.db.trilha_marcar_feito("sub-a", "empreendedorismo", 1)
        self.assertIn("semana passada", self.t.abertura("sub-a", "empreendedorismo", 2).lower())

    def test_abertura_retoma_quem_nao_fez(self):
        self.db.trilha_registrar_envio("sub-a", "empreendedorismo", 1)
        texto = self.t.abertura("sub-a", "empreendedorismo", 2)
        self.assertTrue(texto)
        self.assertNotIn("parabéns", texto.lower())


class TestPdfTrilha(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg, self.db, self.subs = _recarregar(self.tmp)
        import pdf_trilha
        importlib.reload(pdf_trilha)
        self.p = pdf_trilha
        self.peca = {"produto": "empreendedorismo", "numero": 3, "titulo": "Escolha uma linha",
                     "eixo": "Saber onde você está", "corpo": "Primeiro.\n\nSegundo.",
                     "micro_resultado": "Faça a conta.", "mentalidade": "Pense grande.",
                     "ferramenta_slug": "mapa-de-linha", "aviso": ""}

    def test_html_traz_titulo_e_progresso(self):
        h = self.p.montar_html(self.peca, "Diego")
        self.assertIn("Escolha uma linha", h)
        total = self.cfg.TRILHAS["empreendedorismo"]["total"]
        self.assertIn(f"3 de {total}", h)

    def test_html_traz_as_tres_camadas(self):
        h = self.p.montar_html(self.peca, "Diego")
        self.assertIn("Faça a conta.", h)
        self.assertIn("Pense grande.", h)
        self.assertIn("Segundo.", h)

    def test_paragrafos_do_corpo_viram_p(self):
        h = self.p.montar_html(self.peca, "Diego")
        self.assertIn("<p>Primeiro.</p>", h)
        self.assertIn("<p>Segundo.</p>", h)

    def test_link_da_ferramenta_aparece_quando_existe(self):
        h = self.p.montar_html(self.peca, "Diego", link_ferramenta="https://x/ferramentas/mapa")
        self.assertIn('href="https://x/ferramentas/mapa"', h)

    def test_sem_ferramenta_nao_deixa_botao_orfao(self):
        h = self.p.montar_html(self.peca, "Diego")
        self.assertNotIn("Baixar", h)

    def test_abertura_entra_quando_existe(self):
        h = self.p.montar_html(self.peca, "Diego", abertura="Continua em aberto.")
        self.assertIn("Continua em aberto.", h)

    def test_escapa_html_do_conteudo(self):
        peca = dict(self.peca, titulo="Dose <script>alert(1)</script>")
        h = self.p.montar_html(peca, "Diego")
        self.assertNotIn("<script>", h)
        self.assertIn("&lt;script&gt;", h)

    def test_escapa_nome_do_assinante(self):
        h = self.p.montar_html(self.peca, "<img src=x onerror=1>")
        self.assertNotIn("<img src=x", h)

    def test_subtitulo_vira_h2_sem_sobrar_marcador(self):
        peca = dict(self.peca, corpo="### Um passo importante\n\nTexto normal.")
        h = self.p.montar_html(peca, "Diego")
        self.assertIn("<h2>Um passo importante</h2>", h)
        self.assertNotIn("###", h)

    def test_tabela_de_cano_vira_table_com_thead_e_tbody(self):
        corpo = "| Item | Valor |\n| --- | --- |\n| Aluguel | R$ 100 |"
        peca = dict(self.peca, corpo=corpo)
        h = self.p.montar_html(peca, "Diego")
        self.assertIn("<table>", h)
        self.assertIn("<thead>", h)
        self.assertIn("<tbody>", h)
        self.assertIn("<th>Item</th>", h)
        self.assertIn("<td>Aluguel</td>", h)
        self.assertNotIn("|", h)

    def test_negrito_vira_strong_em_paragrafo_tabela_e_lista(self):
        corpo = ("Isto é **forte**.\n\n"
                 "| Item | Valor |\n| --- | --- |\n| **Total** | R$ 100 |\n\n"
                 "- Primeiro **item**.")
        peca = dict(self.peca, corpo=corpo)
        h = self.p.montar_html(peca, "Diego")
        self.assertIn("<strong>forte</strong>", h)
        self.assertIn("<strong>Total</strong>", h)
        self.assertIn("<strong>item</strong>", h)
        self.assertNotIn("**", h)

    def test_lista_com_marcador_vira_ul(self):
        peca = dict(self.peca, corpo="- Um\n- Dois\n- Três")
        h = self.p.montar_html(peca, "Diego")
        self.assertIn("<ul><li>Um</li><li>Dois</li><li>Três</li></ul>", h)

    def test_lista_numerada_vira_ol(self):
        peca = dict(self.peca, corpo="1. Um\n2. Dois\n3. Três")
        h = self.p.montar_html(peca, "Diego")
        self.assertIn("<ol><li>Um</li><li>Dois</li><li>Três</li></ol>", h)

    def test_escapa_script_dentro_de_celula_de_tabela(self):
        corpo = "| Item | Valor |\n| --- | --- |\n| <script>alert(1)</script> | R$ 1 |"
        peca = dict(self.peca, corpo=corpo)
        h = self.p.montar_html(peca, "Diego")
        self.assertNotIn("<script>", h)
        self.assertIn("&lt;script&gt;", h)

    def test_escapa_script_dentro_de_item_de_lista(self):
        peca = dict(self.peca, corpo="- <script>alert(1)</script>")
        h = self.p.montar_html(peca, "Diego")
        self.assertNotIn("<script>", h)
        self.assertIn("&lt;script&gt;", h)

    def test_texto_sem_marcacao_continua_saindo_como_antes(self):
        peca = dict(self.peca, corpo="Primeiro.\n\nSegundo.")
        h = self.p.montar_html(peca, "Diego")
        self.assertIn("<p>Primeiro.</p>", h)
        self.assertIn("<p>Segundo.</p>", h)
        self.assertNotIn("<h2>", h)
        self.assertNotIn("<ul>", h)
        self.assertNotIn("<table>", h)

    def test_peca_real_renderiza_sem_sobrar_marcador(self):
        import trilha
        caminho = os.path.join(os.path.dirname(__file__), "..", "..", "seed", "trilha",
                               "05-precificacao.md")
        with open(caminho, encoding="utf-8") as f:
            peca = trilha.parse_peca(f.read())
        peca["numero"] = 5
        h = self.p.montar_html(peca, "Diego")
        self.assertNotIn("|", h)
        self.assertNotIn("###", h)
        self.assertNotIn("**", h)
        self.assertIn("<table>", h)
        self.assertIn("<h2>", h)

    def test_sem_aviso_nao_mostra_bloco_de_alerta(self):
        h = self.p.montar_html(self.peca, "Diego")
        self.assertNotIn("Sem registro na Anvisa", h)
        self.assertNotIn("bloco alerta", h)

    def test_com_aviso_mostra_bloco_de_alerta_depois_do_corpo(self):
        peca = dict(self.peca, produto="peptideos",
                   aviso="A Anvisa nomeou esta substância como ilegal para qualquer uso.")
        h = self.p.montar_html(peca, "Diego")
        self.assertIn("Sem registro na Anvisa", h)
        self.assertIn("ilegal para qualquer uso", h)
        # ordem: depois do corpo, antes do bloco de tarefa da semana
        pos_corpo = h.index('<div class="corpo">')
        pos_alerta = h.index('bloco alerta')
        pos_tarefa = h.index("Sua tarefa desta semana")
        self.assertTrue(pos_corpo < pos_alerta < pos_tarefa)

    def test_aviso_escapa_html(self):
        peca = dict(self.peca, aviso="<script>alert(1)</script>")
        h = self.p.montar_html(peca, "Diego")
        self.assertNotIn("<script>alert", h)

    def test_nome_e_total_vem_do_catalogo_do_produto(self):
        peca = dict(self.peca, produto="peptideos", numero=1)
        h = self.p.montar_html(peca, "Diego")
        total_pep = self.cfg.TRILHAS["peptideos"]["total"]
        self.assertIn(f"1 de {total_pep}", h)
        self.assertIn(self.cfg.TRILHAS["peptideos"]["nome"], h)


class TestEnvio(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg, self.db, self.subs = _recarregar(self.tmp)
        import trilha
        importlib.reload(trilha)
        self.t = trilha
        self.t.semear()
        self.t.definir_produto_ativo("empreendedorismo")
        self.enviados = []

    def _fake_enviar(self, whatsapp, pdf_path, caption=""):
        self.enviados.append({"whatsapp": whatsapp, "caption": caption})

    def _fake_render(self, html, out_path):
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("pdf")
        return out_path

    def _sub(self, nome="Fulano", numero="5543999990000", slot="08h"):
        reg = self.subs.adicionar(nome, numero)
        self.subs.definir_slot(reg["id"], slot)
        return self.subs.por_id(reg["id"])

    def test_envia_a_peca_1_e_avanca(self):
        sub = self._sub()
        ok = self.t.enviar_para(sub, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertTrue(ok)
        self.assertEqual(len(self.enviados), 1)
        self.assertEqual(self.db.trilha_posicao(sub["id"], "empreendedorismo"), 2)

    def test_claim_orfao_e_retomado_assinante_volta_a_receber(self):
        sub = self._sub()
        self.db.trilha_registrar_envio(sub["id"], "empreendedorismo", 1)
        self.assertEqual(self.db.trilha_posicao(sub["id"], "empreendedorismo"), 1)
        ok = self.t.enviar_para(sub, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertTrue(ok, "claim órfão tem que ser retomado, não travar o assinante pra sempre")
        self.assertEqual(len(self.enviados), 1)
        self.assertEqual(self.db.trilha_posicao(sub["id"], "empreendedorismo"), 2)

    def test_falha_no_envio_nao_avanca_a_posicao(self):
        sub = self._sub()

        def explode(*a, **k):
            raise RuntimeError("zap caiu")

        ok = self.t.enviar_para(sub, enviar_fn=explode, render_fn=self._fake_render)
        self.assertFalse(ok)
        self.assertEqual(self.db.trilha_posicao(sub["id"], "empreendedorismo"), 1)

    def test_falha_no_envio_libera_o_claim_pra_proxima_semana(self):
        sub = self._sub()

        def explode(*a, **k):
            raise RuntimeError("zap caiu")

        self.t.enviar_para(sub, enviar_fn=explode, render_fn=self._fake_render)
        ok = self.t.enviar_para(sub, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertTrue(ok, "a mesma peça tem que poder ser reenviada depois de falhar")

    def test_quem_concluiu_e_sem_ativo_nao_recebe_mais(self):
        sub = self._sub()
        self.db.trilha_avancar(sub["id"], "empreendedorismo", self.cfg.TRILHAS["empreendedorismo"]["total"])
        self.t.definir_produto_ativo("")
        ok = self.t.enviar_para(sub, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertFalse(ok)
        self.assertEqual(self.enviados, [])

    def test_slot_envia_so_pro_proprio_slot(self):
        from datetime import date
        a = self._sub("A", "5543999990001", "08h")
        b = self._sub("B", "5543999990002", "18h")
        res = self.t.enviar_slot("08h", quando=date(2026, 8, 8),
                                 enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertEqual(res["enviados"], 1)
        self.assertEqual(self.db.trilha_posicao(a["id"], "empreendedorismo"), 2)
        self.assertEqual(self.db.trilha_posicao(b["id"], "empreendedorismo"), 1)

    def test_slot_nao_envia_em_dia_util(self):
        from datetime import date
        self._sub()
        res = self.t.enviar_slot("08h", quando=date(2026, 8, 7),
                                 enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertEqual(res["enviados"], 0)
        self.assertEqual(self.enviados, [])

    def test_slot_e_idempotente_no_mesmo_sabado(self):
        from datetime import date
        self._sub()
        sab = date(2026, 8, 8)
        self.t.enviar_slot("08h", quando=sab, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        res = self.t.enviar_slot("08h", quando=sab, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertEqual(res["enviados"], 0)
        self.assertEqual(len(self.enviados), 1)

    def test_cancelado_nao_recebe(self):
        from datetime import date
        sub = self._sub()
        self.subs.marcar_status(sub["id"], "CANCELADO", acesso_ate="2020-01-01")
        res = self.t.enviar_slot("08h", quando=date(2026, 8, 8),
                                 enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertEqual(res["enviados"], 0)

    def test_falha_no_avanco_apos_envio_nao_trava_o_assinante(self):
        sub = self._sub()
        avancar_original = self.db.trilha_avancar
        chamadas = {"n": 0}

        def avancar_com_falha(sub_id, produto, numero):
            chamadas["n"] += 1
            if chamadas["n"] == 1:
                raise RuntimeError("disco cheio")
            return avancar_original(sub_id, produto, numero)

        self.db.trilha_avancar = avancar_com_falha
        try:
            ok1 = self.t.enviar_para(sub, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
            self.assertFalse(ok1, "avanço falhou -- não pode reportar sucesso")
            self.assertEqual(self.db.trilha_posicao(sub["id"], "empreendedorismo"), 1)

            ok2 = self.t.enviar_para(sub, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
            self.assertTrue(ok2, "claim liberado -- a mesma peça tem que poder sair de novo")
            self.assertEqual(self.db.trilha_posicao(sub["id"], "empreendedorismo"), 2)
        finally:
            self.db.trilha_avancar = avancar_original

        self.assertEqual(len(self.enviados), 2, "peça 1 saiu duas vezes -- duplicata, não sumiço")

    def test_falha_inesperada_num_assinante_nao_impede_os_demais_do_slot(self):
        from datetime import date
        from unittest.mock import patch
        a = self._sub("A", "5543999990005", "08h")
        b = self._sub("B", "5543999990006", "08h")

        produto_original = self.t.produto_do_assinante

        def produto_com_explosao(sub_id):
            if sub_id == a["id"]:
                raise RuntimeError("banco caiu bem na hora do Fulano A")
            return produto_original(sub_id)

        self.t.produto_do_assinante = produto_com_explosao
        try:
            with patch("time.sleep"):
                res = self.t.enviar_slot("08h", quando=date(2026, 8, 8),
                                         enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        finally:
            self.t.produto_do_assinante = produto_original

        self.assertEqual(res["enviados"], 1, "B tinha que receber mesmo com A explodindo")
        self.assertEqual(res["falhas"], 1)
        self.assertEqual(self.db.trilha_posicao(b["id"], "empreendedorismo"), 2)

    def test_slot_respeita_o_delay_entre_assinantes(self):
        from datetime import date
        from unittest.mock import patch
        a = self._sub("A", "5543999990010", "08h")
        b = self._sub("B", "5543999990011", "08h")
        c = self._sub("C", "5543999990012", "08h")
        with patch("time.sleep") as mock_sleep:
            res = self.t.enviar_slot("08h", quando=date(2026, 8, 8),
                                     enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertEqual(res["enviados"], 3)
        self.assertEqual(mock_sleep.call_count, 2, "3 envios -> 2 pausas entre eles, nunca no fim")
        for chamada in mock_sleep.call_args_list:
            self.assertEqual(chamada.args[0], self.cfg.SEND_DELAY_SEC)

    def test_troca_de_slot_no_mesmo_sabado_nao_duplica(self):
        from datetime import date
        sub = self._sub(slot="08h")
        sab = date(2026, 8, 8)

        res1 = self.t.enviar_slot("08h", quando=sab, enviar_fn=self._fake_enviar,
                                  render_fn=self._fake_render)
        self.assertEqual(res1["enviados"], 1)
        self.assertEqual(self.db.trilha_posicao(sub["id"], "empreendedorismo"), 2)

        self.subs.definir_slot(sub["id"], "18h")

        res2 = self.t.enviar_slot("18h", quando=sab, enviar_fn=self._fake_enviar,
                                  render_fn=self._fake_render)
        self.assertEqual(res2["enviados"], 0, "já recebeu a peça da semana -- não pode duplicar")
        self.assertEqual(len(self.enviados), 1, "só UMA peça no sábado, apesar da troca de slot")
        self.assertEqual(self.db.trilha_posicao(sub["id"], "empreendedorismo"), 2)

    def test_link_da_ferramenta_aponta_pro_portal_do_assinante(self):
        capturado = {}

        def espiao(whatsapp, pdf_path, caption=""):
            with open(pdf_path, encoding="utf-8") as f:
                capturado["html"] = f.read()

        def render_html(html, out_path):
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html)
            return out_path

        sub = self._sub()
        self.assertTrue(self.t.enviar_para(sub, enviar_fn=espiao, render_fn=render_html))
        html = capturado["html"]
        self.assertIn(f"{self.cfg.ARTIGOS_URL}/ferramentas/", html)
        self.assertNotIn(f"{self.cfg.PUBLIC_URL}/ferramentas/", html)


class TestLoteDePecas(unittest.TestCase):
    """Peptídeos manda 2 peças por sábado (vs. 1 da trilha de empreendedorismo) --
    `config.TRILHAS["peptideos"]["pecas_por_envio"]`."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        d = os.path.join(self.tmp, "peptideos")
        os.makedirs(d)
        for n, titulo in ((1, "Um"), (2, "Dois"), (3, "Três")):
            with open(os.path.join(d, f"{n:02d}-p.md"), "w", encoding="utf-8") as f:
                f.write(f"titulo: {titulo}\neixo: A\n\n## corpo\ncorpo {n}\n")
        os.environ["DSCURSO_PEPTIDEOS_DIR"] = d
        self.cfg, self.db, self.subs = _recarregar(self.tmp)
        import trilha
        importlib.reload(trilha)
        self.t = trilha
        self.t.semear()
        self.t.definir_produto_ativo("peptideos")
        self.enviados = []

    def tearDown(self):
        os.environ.pop("DSCURSO_PEPTIDEOS_DIR", None)

    def _fake_enviar(self, whatsapp, pdf_path, caption=""):
        self.enviados.append(caption)

    def _fake_render(self, html, out_path):
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("pdf")
        return out_path

    def _sub(self):
        reg = self.subs.adicionar("Fulano", "5543999990000")
        self.subs.definir_slot(reg["id"], "08h")
        return self.subs.por_id(reg["id"])

    def test_manda_2_pecas_numa_visita_so(self):
        sub = self._sub()
        ok = self.t.enviar_para(sub, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertTrue(ok)
        self.assertEqual(len(self.enviados), 2)
        self.assertIn("Semana 1", self.enviados[0])
        self.assertIn("Semana 2", self.enviados[1])
        self.assertEqual(self.db.trilha_posicao(sub["id"], "peptideos"), 3)

    def test_pausa_entre_as_2_pecas_da_mesma_pessoa(self):
        from unittest.mock import patch
        sub = self._sub()
        with patch("time.sleep") as mock_sleep:
            self.t.enviar_para(sub, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        mock_sleep.assert_called_once_with(self.cfg.SEND_DELAY_SEC)

    def test_trilha_acaba_no_meio_do_lote_manda_a_ultima_e_para(self):
        sub = self._sub()
        self.db.trilha_avancar(sub["id"], "peptideos", 2)   # só falta a peça 3
        ok = self.t.enviar_para(sub, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertTrue(ok)
        self.assertEqual(len(self.enviados), 1)
        self.assertIn("Semana 3", self.enviados[0])
        self.assertEqual(self.db.trilha_posicao(sub["id"], "peptideos"), 4)

    def test_2a_peca_falha_nao_desfaz_a_1a(self):
        sub = self._sub()
        chamadas = {"n": 0}

        def enviar_falha_na_2a(whatsapp, pdf_path, caption=""):
            chamadas["n"] += 1
            if chamadas["n"] == 2:
                raise RuntimeError("zap caiu na 2ª")
            self.enviados.append(caption)

        ok = self.t.enviar_para(sub, enviar_fn=enviar_falha_na_2a, render_fn=self._fake_render)
        self.assertTrue(ok, "a 1ª peça saiu de verdade -- não é falha total")
        self.assertEqual(len(self.enviados), 1)
        self.assertEqual(self.db.trilha_posicao(sub["id"], "peptideos"), 2,
                         "avançou só da 1ª -- a 2ª fica pro próximo sábado")


class TestLinkFerramentaNoEnvio(unittest.TestCase):
    """Important 4 da revisão: o PDF só pode oferecer o link de download da
    ferramenta quando o arquivo existe de verdade em seed/trilha/ferramentas/ --
    caso contrário o assinante loga e recebe 404. Usa `DSCURSO_TRILHA_DIR` isolado
    (mesmo padrão de TestFerramentaSegura em test_trilha_web.py) pra não escrever
    arquivo nenhum no diretório real do repo."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_TRILHA_DIR"] = os.path.join(self.tmp, "trilha")
        os.makedirs(os.path.join(self.tmp, "trilha", "ferramentas"))
        self.cfg, self.db, self.subs = _recarregar(self.tmp)
        import trilha
        importlib.reload(trilha)
        self.t = trilha
        self.db.trilha_upsert_peca(1, "eixo", "Peça 1", "corpo", "micro", "mentalidade",
                                   "planilha-custo-hora")
        self.enviados = []

    def tearDown(self):
        # DSCURSO_TRILHA_DIR é global -- sem limpar, vaza pras classes seguintes
        # da suíte (mesmo achado documentado em TestFerramentaSegura).
        os.environ.pop("DSCURSO_TRILHA_DIR", None)

    def _fake_enviar(self, whatsapp, pdf_path, caption=""):
        self.enviados.append({"whatsapp": whatsapp, "caption": caption})

    def _render_capturando(self, htmls):
        def render(html, out_path):
            htmls.append(html)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("pdf")
            return out_path
        return render

    def _sub(self, nome="Fulano", numero="5543999990000", slot="08h"):
        reg = self.subs.adicionar(nome, numero)
        self.subs.definir_slot(reg["id"], slot)
        return self.subs.por_id(reg["id"])

    def test_link_some_quando_arquivo_da_ferramenta_nao_existe(self):
        sub = self._sub()
        htmls = []
        ok = self.t.enviar_para(sub, enviar_fn=self._fake_enviar,
                                render_fn=self._render_capturando(htmls))
        self.assertTrue(ok)
        self.assertNotIn("Baixar", htmls[0])
        self.assertNotIn("planilha-custo-hora", htmls[0])

    def test_link_aparece_quando_arquivo_da_ferramenta_existe(self):
        caminho = os.path.join(self.cfg.TRILHA_DIR, "ferramentas", "planilha-custo-hora.csv")
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("a,b\n")
        sub = self._sub()
        htmls = []
        ok = self.t.enviar_para(sub, enviar_fn=self._fake_enviar,
                                render_fn=self._render_capturando(htmls))
        self.assertTrue(ok)
        self.assertIn("/ferramentas/planilha-custo-hora", htmls[0])
        self.assertIn("Baixar", htmls[0])


class TestProdutoDoAssinante(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg, self.db, self.subs = _recarregar(self.tmp)
        import trilha
        importlib.reload(trilha)
        self.t = trilha

    def test_ninguem_ativo_e_ninguem_comecou_devolve_none(self):
        self.assertIsNone(self.t.produto_do_assinante("sub-a"))

    def test_assinante_novo_entra_no_produto_ativo(self):
        self.t.definir_produto_ativo("peptideos")
        self.assertEqual(self.t.produto_do_assinante("sub-a"), "peptideos")

    def test_meio_de_um_produto_continua_nele_mesmo_trocando_o_ativo(self):
        self.t.definir_produto_ativo("empreendedorismo")
        self.db.trilha_avancar("sub-a", "empreendedorismo", 1)   # está na peça 2 de 12
        self.t.definir_produto_ativo("peptideos")                # Diego troca a ativa
        self.assertEqual(self.t.produto_do_assinante("sub-a"), "empreendedorismo",
                         "quem tá no meio tem que terminar antes de trocar")

    def test_quem_concluiu_cai_no_produto_ativo(self):
        self.t.definir_produto_ativo("empreendedorismo")
        self.db.trilha_avancar("sub-a", "empreendedorismo", self.cfg.TRILHAS["empreendedorismo"]["total"])
        self.t.definir_produto_ativo("peptideos")
        self.assertEqual(self.t.produto_do_assinante("sub-a"), "peptideos")

    def test_definir_produto_ativo_rejeita_produto_desconhecido(self):
        with self.assertRaises(ValueError):
            self.t.definir_produto_ativo("nao-existe")

    def test_definir_produto_ativo_vazio_desliga(self):
        self.t.definir_produto_ativo("peptideos")
        self.t.definir_produto_ativo("")
        self.assertEqual(self.t.produto_ativo(), "")
        self.assertIsNone(self.t.produto_do_assinante("sub-a"))


class TestInterruptor(unittest.TestCase):
    """O interruptor mestre virou seletor de produto. Nasce sem nenhuma trilha
    ativa porque a trilha não tem aprovação por envio (o estudo diário tem, às
    18h): o conteúdo vai do arquivo direto pro WhatsApp de assinante pagante. Um
    deploy sozinho não pode começar a enviar."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg, self.db, self.subs = _recarregar(self.tmp)
        import trilha
        importlib.reload(trilha)
        self.t = trilha
        self.t.semear()

    def test_nasce_sem_produto_ativo(self):
        self.assertEqual(self.t.produto_ativo(), "")

    def test_ligar_e_desligar(self):
        self.t.definir_produto_ativo("empreendedorismo")
        self.assertEqual(self.t.produto_ativo(), "empreendedorismo")
        self.t.definir_produto_ativo("")
        self.assertEqual(self.t.produto_ativo(), "")


class TestMigracaoMultiproduto(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg, self.db, self.subs = _recarregar(self.tmp)

    def test_catalogo_tem_os_dois_produtos(self):
        self.assertIn("empreendedorismo", self.cfg.TRILHAS)
        self.assertIn("peptideos", self.cfg.TRILHAS)
        self.assertEqual(self.cfg.TRILHAS["empreendedorismo"]["total"], 12)
        self.assertEqual(self.cfg.TRILHAS["peptideos"]["total"], 11)
        self.assertEqual(self.cfg.TRILHAS["peptideos"]["pecas_por_envio"], 2)
        self.assertEqual(self.cfg.TRILHAS["empreendedorismo"]["pecas_por_envio"], 1)

    def test_tabelas_novas_tem_coluna_produto(self):
        with self.db._conn() as c:
            self.assertTrue(self.db._tem_coluna(c, "trilha_pecas", "produto"))
            self.assertTrue(self.db._tem_coluna(c, "trilha_progresso", "produto"))
            self.assertTrue(self.db._tem_coluna(c, "trilha_envios", "produto"))
            self.assertTrue(self.db._tem_coluna(c, "trilha_pecas", "aviso"))

    def test_migracao_preserva_pecas_existentes_marcando_empreendedorismo(self):
        # simula um banco ANTIGO (schema de 1 produto só) já com 1 peça gravada,
        # roda a migração de novo e confere que a peça sobrevive marcada.
        with self.db._conn() as c:
            c.execute("DROP TABLE trilha_pecas")
            c.execute("""CREATE TABLE trilha_pecas (
                numero INTEGER PRIMARY KEY, eixo TEXT DEFAULT '', titulo TEXT DEFAULT '',
                corpo TEXT DEFAULT '', micro_resultado TEXT DEFAULT '',
                mentalidade TEXT DEFAULT '', ferramenta_slug TEXT DEFAULT '',
                ativa INTEGER DEFAULT 1, atualizado_em TEXT)""")
            c.execute("INSERT INTO trilha_pecas (numero, titulo) VALUES (1, 'Peça velha')")
        self.db._migrar_trilha_multiproduto()
        p = self.db.trilha_peca("empreendedorismo", 1)
        self.assertIsNotNone(p)
        self.assertEqual(p["titulo"], "Peça velha")

    def test_migracao_e_idempotente(self):
        self.db._migrar_trilha_multiproduto()   # 2ª chamada não pode quebrar
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
