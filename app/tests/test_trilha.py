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

    def _peca(self, numero=1):
        self.db.trilha_upsert_peca(numero, "Saber onde você está", f"Peça {numero}",
                                   "corpo", "micro", "mentalidade", "")

    def test_upsert_peca_grava_e_le(self):
        self._peca(1)
        p = self.db.trilha_peca(1)
        self.assertEqual(p["titulo"], "Peça 1")
        self.assertEqual(p["micro_resultado"], "micro")

    def test_upsert_peca_atualiza_em_vez_de_duplicar(self):
        self._peca(1)
        self.db.trilha_upsert_peca(1, "eixo novo", "Título novo", "c", "m", "t", "")
        self.assertEqual(self.db.trilha_peca(1)["titulo"], "Título novo")

    def test_peca_inexistente_devolve_none(self):
        self.assertIsNone(self.db.trilha_peca(13))

    def test_posicao_nasce_em_1(self):
        self.assertEqual(self.db.trilha_posicao("sub-a"), 1)

    def test_registrar_envio_e_idempotente(self):
        self.assertTrue(self.db.trilha_registrar_envio("sub-a", 1))    # 1ª vez
        self.assertFalse(self.db.trilha_registrar_envio("sub-a", 1))   # repetido
        self.assertTrue(self.db.trilha_registrar_envio("sub-a", 2))    # outra peça
        self.assertTrue(self.db.trilha_registrar_envio("sub-b", 1))    # outro assinante

    def test_avancar_move_a_posicao(self):
        self.db.trilha_avancar("sub-a", 1)
        self.assertEqual(self.db.trilha_posicao("sub-a"), 2)

    def test_marcar_feito_e_idempotente(self):
        self.db.trilha_registrar_envio("sub-a", 1)
        self.assertFalse(self.db.trilha_fez("sub-a", 1))
        self.assertTrue(self.db.trilha_marcar_feito("sub-a", 1))
        self.assertTrue(self.db.trilha_fez("sub-a", 1))
        self.assertFalse(self.db.trilha_marcar_feito("sub-a", 1))   # 2º clique não duplica

    def test_marcar_feito_em_peca_nao_enviada_nao_grava(self):
        self.assertFalse(self.db.trilha_marcar_feito("sub-a", 7))
        self.assertFalse(self.db.trilha_fez("sub-a", 7))

    def test_historico_vem_do_mais_recente(self):
        self.db.trilha_registrar_envio("sub-a", 1)
        self.db.trilha_registrar_envio("sub-a", 2)
        h = self.db.trilha_historico("sub-a")
        self.assertEqual([x["numero"] for x in h], [2, 1])

    def test_painel_conta_enviadas_e_feitas(self):
        self.db.trilha_registrar_envio("sub-a", 1)
        self.db.trilha_registrar_envio("sub-a", 2)
        self.db.trilha_marcar_feito("sub-a", 1)
        self.db.trilha_avancar("sub-a", 2)
        linha = [l for l in self.db.trilha_painel() if l["subscriber_id"] == "sub-a"][0]
        self.assertEqual(linha["enviadas"], 2)
        self.assertEqual(linha["feitas"], 1)
        self.assertEqual(linha["proxima_peca"], 3)

    def test_tabelas_novas_estao_na_lista_de_rls(self):
        # fora de _TABELAS, a tabela fica exposta na Data API pública do Supabase
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

    def test_parse_sem_ferramenta_devolve_vazio(self):
        p = self.t.parse_peca("titulo: X\neixo: Y\n\n## corpo\nz\n")
        self.assertEqual(p["ferramenta"], "")
        self.assertEqual(p["micro_resultado"], "")

    def test_semear_grava_as_pecas_do_diretorio(self):
        d = os.path.join(self.tmp, "trilha")
        os.makedirs(d)
        with open(os.path.join(d, "01-um.md"), "w", encoding="utf-8") as f:
            f.write("titulo: Um\neixo: A\n\n## corpo\ncorpo um\n")
        with open(os.path.join(d, "02-dois.md"), "w", encoding="utf-8") as f:
            f.write("titulo: Dois\neixo: A\n\n## corpo\ncorpo dois\n")
        self.assertEqual(self.t.semear(d), 2)
        self.assertEqual(self.db.trilha_peca(1)["titulo"], "Um")
        self.assertEqual(self.db.trilha_peca(2)["titulo"], "Dois")

    def test_semear_e_idempotente_e_atualiza_texto_editado(self):
        d = os.path.join(self.tmp, "trilha")
        os.makedirs(d)
        caminho = os.path.join(d, "01-um.md")
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("titulo: Um\neixo: A\n\n## corpo\nversao 1\n")
        self.t.semear(d)
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("titulo: Um\neixo: A\n\n## corpo\nversao 2\n")
        self.t.semear(d)
        self.assertIn("versao 2", self.db.trilha_peca(1)["corpo"])

    def test_semear_ignora_arquivo_sem_numero_no_nome(self):
        d = os.path.join(self.tmp, "trilha")
        os.makedirs(d)
        with open(os.path.join(d, "leiame.md"), "w", encoding="utf-8") as f:
            f.write("titulo: X\n\n## corpo\ny\n")
        self.assertEqual(self.t.semear(d), 0)

    def test_semear_diretorio_inexistente_nao_quebra(self):
        self.assertEqual(self.t.semear(os.path.join(self.tmp, "nao-existe")), 0)

    def test_as_12_pecas_do_repo_carregam(self):
        # o diretório real do repo tem que estar parseável e completo
        self.assertEqual(self.t.semear(), self.cfg.TRILHA_TOTAL)
        for n in range(1, self.cfg.TRILHA_TOTAL + 1):
            p = self.db.trilha_peca(n)
            self.assertIsNotNone(p, f"peça {n} não carregou")
            self.assertTrue(p["titulo"].strip(), f"peça {n} sem título")


class TestDrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg, self.db, self.subs = _recarregar(self.tmp)
        import trilha
        importlib.reload(trilha)
        self.t = trilha
        self.t.semear()

    def test_dia_da_trilha_e_sabado(self):
        from datetime import date
        self.assertTrue(self.t.e_dia_da_trilha(date(2026, 8, 8)))     # sábado
        self.assertFalse(self.t.e_dia_da_trilha(date(2026, 8, 7)))    # sexta
        self.assertFalse(self.t.e_dia_da_trilha(date(2026, 8, 9)))    # domingo

    def test_assinante_novo_recebe_a_peca_1(self):
        self.assertEqual(self.t.proxima_peca("sub-a")["numero"], 1)

    def test_peca_nao_avanca_sozinha(self):
        self.assertEqual(self.t.proxima_peca("sub-a")["numero"], 1)
        self.assertEqual(self.t.proxima_peca("sub-a")["numero"], 1)   # sem avanço, mesma peça

    def test_avanco_leva_a_proxima(self):
        self.db.trilha_avancar("sub-a", 1)
        self.assertEqual(self.t.proxima_peca("sub-a")["numero"], 2)

    def test_quem_concluiu_nao_tem_proxima(self):
        self.db.trilha_avancar("sub-a", self.cfg.TRILHA_TOTAL)
        self.assertIsNone(self.t.proxima_peca("sub-a"))

    def test_abertura_da_peca_1_nao_cobra_nada(self):
        self.assertEqual(self.t.abertura("sub-a", 1), "")

    def test_abertura_reconhece_quem_fez(self):
        self.db.trilha_registrar_envio("sub-a", 1)
        self.db.trilha_marcar_feito("sub-a", 1)
        self.assertIn("semana passada", self.t.abertura("sub-a", 2).lower())

    def test_abertura_retoma_quem_nao_fez(self):
        self.db.trilha_registrar_envio("sub-a", 1)
        texto = self.t.abertura("sub-a", 2)
        self.assertTrue(texto)
        self.assertNotIn("parabéns", texto.lower())


class TestPdfTrilha(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg, self.db, self.subs = _recarregar(self.tmp)
        import pdf_trilha
        importlib.reload(pdf_trilha)
        self.p = pdf_trilha
        self.peca = {"numero": 3, "titulo": "Escolha uma linha", "eixo": "Saber onde você está",
                     "corpo": "Primeiro.\n\nSegundo.", "micro_resultado": "Faça a conta.",
                     "mentalidade": "Pense grande.", "ferramenta_slug": "mapa-de-linha"}

    def test_html_traz_titulo_e_progresso(self):
        h = self.p.montar_html(self.peca, "Diego")
        self.assertIn("Escolha uma linha", h)
        self.assertIn(f"3 de {self.cfg.TRILHA_TOTAL}", h)

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


class TestEnvio(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg, self.db, self.subs = _recarregar(self.tmp)
        import trilha
        importlib.reload(trilha)
        self.t = trilha
        self.t.semear()
        self.enviados = []

    def _fake_enviar(self, whatsapp, pdf_path, caption=""):
        # assinatura igual a deliver.enviar_pdf(whatsapp, pdf_path, caption="") de
        # propósito: um dublê que aceita mais parâmetros do que a função real é
        # como o bug do `nome_arquivo` passou despercebido da primeira vez.
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
        self.assertEqual(self.db.trilha_posicao(sub["id"]), 2)

    def test_claim_orfao_e_retomado_assinante_volta_a_receber(self):
        # Important 2 da revisão: um claim em trilha_envios sem a posição ter
        # avançado só pode ser órfão (execução anterior morreu entre o INSERT do
        # claim e o envio/avanço -- deploy, OOM, restart). Sem a correção, isto
        # travava o assinante NESSA peça pra sempre: `enviar_para` devolvia False
        # em TODO sábado seguinte porque o claim nunca era liberado.
        sub = self._sub()
        self.db.trilha_registrar_envio(sub["id"], 1)     # claim órfão de uma execução anterior
        self.assertEqual(self.db.trilha_posicao(sub["id"]), 1)   # não avançou -- é o sinal do órfão
        ok = self.t.enviar_para(sub, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertTrue(ok, "claim órfão tem que ser retomado, não travar o assinante pra sempre")
        self.assertEqual(len(self.enviados), 1)
        self.assertEqual(self.db.trilha_posicao(sub["id"]), 2)

    def test_falha_no_envio_nao_avanca_a_posicao(self):
        sub = self._sub()

        def explode(*a, **k):
            raise RuntimeError("zap caiu")

        ok = self.t.enviar_para(sub, enviar_fn=explode, render_fn=self._fake_render)
        self.assertFalse(ok)
        self.assertEqual(self.db.trilha_posicao(sub["id"]), 1)   # continua na peça 1

    def test_falha_no_envio_libera_o_claim_pra_proxima_semana(self):
        sub = self._sub()

        def explode(*a, **k):
            raise RuntimeError("zap caiu")

        self.t.enviar_para(sub, enviar_fn=explode, render_fn=self._fake_render)
        ok = self.t.enviar_para(sub, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertTrue(ok, "a mesma peça tem que poder ser reenviada depois de falhar")

    def test_quem_concluiu_nao_recebe_mais(self):
        sub = self._sub()
        self.db.trilha_avancar(sub["id"], self.cfg.TRILHA_TOTAL)
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
        self.assertEqual(self.db.trilha_posicao(a["id"]), 2)
        self.assertEqual(self.db.trilha_posicao(b["id"]), 1)

    def test_slot_nao_envia_em_dia_util(self):
        from datetime import date
        self._sub()
        res = self.t.enviar_slot("08h", quando=date(2026, 8, 7),   # sexta
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
        # Cenário do achado da revisão: a mensagem JÁ saiu (enviar_fn deu certo) e
        # SÓ o db.trilha_avancar falha (lock, disco cheio, banco fora do ar). Sem
        # a correção, o claim ficava órfão e o assinante nunca mais recebia nada.
        sub = self._sub()
        avancar_original = self.db.trilha_avancar
        chamadas = {"n": 0}

        def avancar_com_falha(sub_id, numero):
            chamadas["n"] += 1
            if chamadas["n"] == 1:
                raise RuntimeError("disco cheio")
            return avancar_original(sub_id, numero)

        self.db.trilha_avancar = avancar_com_falha
        try:
            ok1 = self.t.enviar_para(sub, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
            self.assertFalse(ok1, "avanço falhou -- não pode reportar sucesso")
            self.assertEqual(self.db.trilha_posicao(sub["id"]), 1, "não avançou de verdade")

            # a mensagem já tinha saído na 1ª tentativa -- é a duplicata aceitável
            ok2 = self.t.enviar_para(sub, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
            self.assertTrue(ok2, "claim liberado -- a mesma peça tem que poder sair de novo")
            self.assertEqual(self.db.trilha_posicao(sub["id"]), 2)
        finally:
            self.db.trilha_avancar = avancar_original

        self.assertEqual(len(self.enviados), 2, "peça 1 saiu duas vezes -- duplicata, não sumiço")

    def test_falha_inesperada_num_assinante_nao_impede_os_demais_do_slot(self):
        from datetime import date
        from unittest.mock import patch
        a = self._sub("A", "5543999990005", "08h")
        b = self._sub("B", "5543999990006", "08h")

        posicao_original = self.db.trilha_posicao

        def posicao_com_explosao(sub_id):
            if sub_id == a["id"]:
                raise RuntimeError("banco caiu bem na hora do Fulano A")
            return posicao_original(sub_id)

        self.db.trilha_posicao = posicao_com_explosao
        try:
            with patch("time.sleep"):    # 2 assinantes no mesmo slot -> pacing dormiria de verdade
                res = self.t.enviar_slot("08h", quando=date(2026, 8, 8),
                                         enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        finally:
            self.db.trilha_posicao = posicao_original

        self.assertEqual(res["enviados"], 1, "B tinha que receber mesmo com A explodindo")
        self.assertEqual(res["falhas"], 1)
        self.assertEqual(self.db.trilha_posicao(b["id"]), 2)   # B avançou normalmente

    def test_slot_respeita_o_delay_entre_assinantes(self):
        # Important 1 da revisão: é o MESMO número de WhatsApp que sustenta o
        # produto pago inteiro -- disparar em rajada arrisca banimento. O loop
        # tem que dormir config.SEND_DELAY_SEC entre assinantes, mas não antes
        # do 1º nem depois do último (atraso inútil).
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
        # Important 3 da revisão, provado por execução: assinante no 08h recebe a
        # peça 1, troca o horário pro 18h no MEIO do mesmo sábado, e o tick das 18h
        # dispara a peça 2 -- posição pula de 1 pra 3 num dia só. Correção: claim
        # por (sábado, assinante), não só por (peça, assinante).
        from datetime import date
        sub = self._sub(slot="08h")
        sab = date(2026, 8, 8)

        res1 = self.t.enviar_slot("08h", quando=sab, enviar_fn=self._fake_enviar,
                                  render_fn=self._fake_render)
        self.assertEqual(res1["enviados"], 1)
        self.assertEqual(self.db.trilha_posicao(sub["id"]), 2)

        self.subs.definir_slot(sub["id"], "18h")   # troca de horário no meio do sábado

        res2 = self.t.enviar_slot("18h", quando=sab, enviar_fn=self._fake_enviar,
                                  render_fn=self._fake_render)
        self.assertEqual(res2["enviados"], 0, "já recebeu a peça da semana -- não pode duplicar")
        self.assertEqual(len(self.enviados), 1, "só UMA peça no sábado, apesar da troca de slot")
        self.assertEqual(self.db.trilha_posicao(sub["id"]), 2, "posição não pode pular pra 3")


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


if __name__ == "__main__":
    unittest.main()
