"""Testes das rotas da trilha: página do assinante, '✅ fiz' e download. Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPaginaTrilha(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        for m in ("config", "db", "subscribers", "trilha", "site_web"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, subscribers, trilha, site_web
        for m in (config, db, subscribers, trilha, site_web):
            importlib.reload(m)
        subscribers._migrado = False
        db.init()
        self.cfg, self.db, self.subs, self.t, self.w = config, db, subscribers, trilha, site_web
        self.t.semear()

    def test_pagina_mostra_a_peca_e_o_botao(self):
        itens = [{"numero": 1, "titulo": "O custo real da sua hora", "feito": False,
                  "ferramenta_slug": ""}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens)
        self.assertIn("O custo real da sua hora", h)
        self.assertIn("fiz", h.lower())

    def test_peca_feita_nao_mostra_botao_de_novo(self):
        itens = [{"numero": 1, "titulo": "X", "feito": True, "ferramenta_slug": ""}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens)
        self.assertNotIn('value="marcar_feito"', h)

    def test_ferramenta_vira_link_de_download(self):
        itens = [{"numero": 1, "titulo": "X", "feito": False, "ferramenta_slug": "planilha-x"}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens)
        self.assertIn("/ferramentas/planilha-x", h)

    def test_escapa_titulo(self):
        itens = [{"numero": 1, "titulo": "<script>x</script>", "feito": False,
                  "ferramenta_slug": ""}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens)
        self.assertNotIn("<script>x", h)

    def test_lista_vazia_mostra_mensagem_de_fallback(self):
        # Minor 4 da revisão: função pura, mesmo estilo dos demais testes desta classe.
        h = self.w.pagina_trilha({"nome": "Diego"}, [])
        self.assertIn("chega no próximo sábado", h)

    def test_peca_ainda_nao_entregue_nao_mostra_botao(self):
        # Important 3 da revisão (defeito do plano, não da execução): o item de
        # prévia que `serve._pagina_trilha` insere quando a peça atual ainda não foi
        # enviada por WhatsApp vem com `entregue=False`. Antes desta correção, esse
        # item tinha o mesmo botão "✅ Fiz" dos itens já entregues — clicar chamava
        # `trilha_marcar_feito`, que devolve False em silêncio (não existe linha em
        # trilha_envios pra essa peça ainda), e a página só recarregava sem avisar
        # nada. Um botão que não faz nada é pior que nenhum botão.
        itens = [{"numero": 1, "titulo": "X", "feito": False, "ferramenta_slug": "",
                  "entregue": False}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens)
        self.assertNotIn('value="marcar_feito"', h)
        self.assertIn("sábado", h.lower())

    def test_item_sem_a_chave_entregue_continua_mostrando_o_botao(self):
        # Compatibilidade: item sem a chave `entregue` (formato usado pelos testes
        # mais antigos desta classe, acima) é tratado como já entregue -- não
        # queremos quebrar chamador nenhum que ainda não passe essa chave.
        itens = [{"numero": 1, "titulo": "X", "feito": False, "ferramenta_slug": ""}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens)
        self.assertIn('value="marcar_feito"', h)

    def test_saudacao_usa_o_nome_do_assinante(self):
        # Minor 5 da revisão: `sub` estava no assinatura mas não era usado no corpo
        # da página. Escolhi usar pra saudação (mesmo padrão de `pagina_minha`,
        # que faz `Olá, {nome}.`) em vez de remover o parâmetro -- justificativa no
        # relatório desta rodada.
        h = self.w.pagina_trilha({"nome": "Diego"}, [])
        self.assertIn("Diego", h)

    def test_plabel_tem_regra_no_css_global(self):
        # Minor da revisão FINAL: `.plabel` era usada em pagina_trilha (rótulo
        # "Semana N de 12") e no painel do admin sem regra correspondente em
        # site_web._CSS -- renderizava como parágrafo comum, sem destaque nenhum.
        self.assertIn(".plabel", self.w._CSS)


class TestFerramentaSegura(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["DSCURSO_TRILHA_DIR"] = self.tmp
        for m in ("config", "db", "trilha"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, trilha
        for m in (config, db, trilha):
            importlib.reload(m)
        db.init()
        self.cfg, self.t = config, trilha
        os.makedirs(os.path.join(self.tmp, "ferramentas"), exist_ok=True)
        with open(os.path.join(self.tmp, "ferramentas", "planilha-x.csv"), "w") as f:
            f.write("a,b\n")

    def tearDown(self):
        # `DSCURSO_TRILHA_DIR` é global (os.environ) e só esta classe o define --
        # sem limpar, ele vaza pras classes seguintes desta suíte (ex.: quem chama
        # `trilha.semear()` sem realimentar a env var passa a ler deste tmpdir vazio
        # de peças em vez do `seed/trilha/` de verdade, e `trilha_listar_pecas()`
        # some com as 12 peças). Achado ao rodar a suíte inteira do arquivo.
        os.environ.pop("DSCURSO_TRILHA_DIR", None)

    def test_acha_a_ferramenta_existente(self):
        self.assertTrue(self.t.caminho_ferramenta("planilha-x"))

    def test_slug_inexistente_devolve_none(self):
        self.assertIsNone(self.t.caminho_ferramenta("nao-existe"))

    def test_path_traversal_e_barrado(self):
        for mau in ("../db.py", "..%2Fdb.py", "a/../../etc/passwd", "/etc/passwd",
                    "..", ".", "a\\..\\b"):
            self.assertIsNone(self.t.caminho_ferramenta(mau), f"passou: {mau}")


class TestPaginaTrilhaFerramentaFaltando(unittest.TestCase):
    """Important 4 da revisão, na página do assinante: `serve.Handler._pagina_trilha`
    alimenta `ferramenta_slug` pra `site_web.pagina_trilha`, que sempre mostrou o
    link sem checar se o arquivo existe. Usa `DSCURSO_TRILHA_DIR` isolado (mesmo
    padrão de TestFerramentaSegura) pra não escrever nada no diretório real do
    repo."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["DSCURSO_TRILHA_DIR"] = os.path.join(self.tmp, "trilha")
        os.makedirs(os.path.join(self.tmp, "trilha", "ferramentas"))
        for m in ("config", "db", "subscribers", "trilha", "site_web", "serve"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, subscribers, trilha, site_web, serve
        for m in (config, db, subscribers, trilha, site_web, serve):
            importlib.reload(m)
        subscribers._migrado = False
        db.init()
        self.cfg, self.db, self.subs, self.serve = config, db, subscribers, serve
        self.db.trilha_upsert_peca(1, "eixo", "Peça 1", "corpo", "micro", "mentalidade",
                                   "planilha-custo-hora")
        self.sub = {"id": "sub-a", "nome": "Diego"}
        self.db.trilha_registrar_envio(self.sub["id"], 1)
        self.db.trilha_avancar(self.sub["id"], 1)

    def tearDown(self):
        os.environ.pop("DSCURSO_TRILHA_DIR", None)

    def test_link_some_quando_arquivo_nao_existe(self):
        html = self.serve.Handler._pagina_trilha(None, self.sub)
        self.assertNotIn("/ferramentas/planilha-custo-hora", html)

    def test_link_aparece_quando_arquivo_existe(self):
        caminho = os.path.join(self.cfg.TRILHA_DIR, "ferramentas", "planilha-custo-hora.csv")
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("a,b\n")
        html = self.serve.Handler._pagina_trilha(None, self.sub)
        self.assertIn("/ferramentas/planilha-custo-hora", html)


class TestTrilhaNumeroValido(unittest.TestCase):
    """Achado Important 2 da revisão: um `numero` com dezenas de dígitos no form de
    POST /trilha chegava direto em `db.trilha_marcar_feito`, que estoura
    `OverflowError: Python int too large to convert to SQLite INTEGER` (o sqlite3
    não converte um Python int de precisão arbitrária pra INTEGER de 64 bits) --
    sem try/except no caminho, e qualquer assinante logado conseguia disparar.
    `serve._trilha_numero_valido` filtra a faixa (1..config.TRILHA_TOTAL) ANTES de
    qualquer valor chegar no banco. Função pura, mesmo padrão de
    test_destino_seguro.py (TestDestinoSeguro)."""

    def setUp(self):
        import serve
        self.f = serve._trilha_numero_valido

    def test_numero_valido_passa(self):
        self.assertEqual(self.f("1"), 1)
        self.assertEqual(self.f("12"), 12)

    def test_numero_fora_da_faixa_vira_zero(self):
        self.assertEqual(self.f("0"), 0)
        self.assertEqual(self.f("13"), 0)
        self.assertEqual(self.f("-1"), 0)

    def test_numero_nao_numerico_vira_zero(self):
        self.assertEqual(self.f("abc"), 0)
        self.assertEqual(self.f(""), 0)
        self.assertEqual(self.f(None), 0)

    def test_numero_gigante_nao_estoura_e_vira_zero(self):
        # ~90 dígitos: bem além de qualquer INTEGER de 64 bits do SQLite.
        self.assertEqual(self.f("9" * 90), 0)


class _TrilhaPostStub:
    """Stub mínimo pro `self` de `_trilha_post`: só o que o método usa, sem abrir
    socket real -- mesmo padrão do `_AceitarTermosStub` de test_destino_seguro.py.
    `_pagina_trilha` aqui devolve só `msg` como marcador: esta classe testa
    roteamento (gate de aceite + validação de `numero`), não a renderização da
    página, que já está coberta em TestPaginaTrilha."""

    def __init__(self, sub):
        self._sub = sub
        self.redirects = []

    def _sub_logado(self):
        return self._sub

    def _html(self, s, code=200):
        return s

    def _redirect(self, location, token=None, clear=False):
        self.redirects.append(location)
        return f"<redirect {location}>"

    def _pagina_trilha(self, sub, msg=""):
        return f"<pagina msg={msg!r}>"


class TestTrilhaPostRota(unittest.TestCase):
    """Achado Important 1 da revisão: POST /trilha mutava (`marcar_feito`) sem
    checar o gate de aceite de termos que `_meus_dados_post` já respeita (o próprio
    repo documenta a regra lá: sem a checagem, "continuava gravando normalmente
    mesmo com o aceite pendente"). `db.trilha_marcar_feito` é exatamente esse tipo
    de mutação.

    Testa o MÉTODO real `serve.Handler._trilha_post`, chamado com um stub no lugar
    de `self` -- mesmo padrão de `TestAceitarTermosSanitizaDestinoDeVerdade` em
    test_destino_seguro.py. Não é teste de rota HTTP (não abre socket nem usa
    request real); é possível porque a Rodada de correção 1 extraiu a lógica de
    POST /trilha, antes inline em `do_POST`, para o método `_trilha_post` (mesma
    forma que `/meus-dados` já usava com `_meus_dados_post`)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        for m in ("config", "db", "subscribers", "trilha", "site_web", "legal", "serve"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, subscribers, trilha, site_web, legal, serve
        for m in (config, db, subscribers, trilha, site_web, legal, serve):
            importlib.reload(m)
        subscribers._migrado = False
        db.init()
        self.subs, self.legal, self.serve = subscribers, legal, serve
        self.sub = subscribers.criar_de_pagamento(
            {"nome": "T", "whatsapp": "43999990000", "email": "t@e.com", "plano": "anual"}, {})

    def _post(self, sub, acao="marcar_feito", numero="1"):
        stub = _TrilhaPostStub(sub)
        g = lambda k: {"acao": acao, "numero": numero}.get(k, "")
        return self.serve.Handler._trilha_post(stub, g)

    def test_aceite_pendente_bloqueia_marcar_feito(self):
        # assinante recém-criado nunca aceitou (termos_versao vazio) -> o gate tem
        # que barrar ANTES de qualquer chamada a trilha_marcar_feito/_pagina_trilha.
        html = self._post(self.sub)
        self.assertIn("aceit", html.lower())    # caiu na tela de aceite dos termos
        self.assertNotIn("pagina msg=", html)   # não chegou em _pagina_trilha

    def test_aceite_em_dia_deixa_a_rota_seguir(self):
        self.subs.registrar_aceite(self.sub["id"], self.legal.VERSAO, "203.0.113.7")
        sub2 = [s for s in self.subs.listar() if s["id"] == self.sub["id"]][0]
        html = self._post(sub2)
        self.assertIn("pagina msg=", html)      # passou do gate, chegou no final da rota

    def test_numero_gigante_no_form_nao_derruba_a_rota(self):
        # prova end-to-end do achado Important 2: sem a validação de faixa, este
        # cenário levantaria OverflowError dentro de db.trilha_marcar_feito.
        self.subs.registrar_aceite(self.sub["id"], self.legal.VERSAO, "203.0.113.7")
        sub2 = [s for s in self.subs.listar() if s["id"] == self.sub["id"]][0]
        html = self._post(sub2, numero="9" * 90)
        self.assertIn("pagina msg=", html)


class TestAdminTrilha(unittest.TestCase):
    """Painel `/admin/trilha`: quem está em qual semana, quanto recebeu e quanto
    executou. Testa só a função de renderização (`pagina_admin_trilha`), mesmo
    padrão de TestPaginaTrilha -- a rota em si é fiação simples em serve.py."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        for m in ("config", "db", "site_web"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, site_web
        for m in (config, db, site_web):
            importlib.reload(m)
        db.init()
        self.w = site_web

    def test_lista_assinantes_com_posicao(self):
        linhas = [{"nome": "Diego", "proxima_peca": 4, "enviadas": 3, "feitas": 2,
                   "concluiu": False}]
        h = self.w.pagina_admin_trilha(linhas)
        self.assertIn("Diego", h)
        self.assertIn("4", h)

    def test_marca_quem_concluiu(self):
        linhas = [{"nome": "Ana", "proxima_peca": 13, "enviadas": 12, "feitas": 12,
                   "concluiu": True}]
        h = self.w.pagina_admin_trilha(linhas)
        self.assertIn("Concluiu", h)

    def test_sem_ninguem_na_trilha_nao_quebra(self):
        h = self.w.pagina_admin_trilha([])
        self.assertIn("Ninguém", h)

    def test_escapa_nome(self):
        linhas = [{"nome": "<script>x</script>", "proxima_peca": 1, "enviadas": 0,
                   "feitas": 0, "concluiu": False}]
        self.assertNotIn("<script>x", self.w.pagina_admin_trilha(linhas))


class TestPreviaPecas(unittest.TestCase):
    """Prévia das 12 peças no admin: `db.trilha_listar_pecas` alimenta a lista de
    links em `pagina_admin_trilha`, um por peça, apontando pra `/admin/trilha/peca/<n>`
    -- a mesma renderização (`pdf_trilha.montar_html`) que vira o PDF no WhatsApp."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        for m in ("config", "db", "trilha", "pdf_trilha", "site_web"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, trilha, pdf_trilha, site_web
        for m in (config, db, trilha, pdf_trilha, site_web):
            importlib.reload(m)
        db.init()
        self.cfg, self.db, self.t, self.w = config, db, trilha, site_web
        self.t.semear()

    def test_listar_pecas_vem_ordenado(self):
        nums = [p["numero"] for p in self.db.trilha_listar_pecas()]
        self.assertEqual(nums, sorted(nums))
        self.assertEqual(len(nums), self.cfg.TRILHA_TOTAL)

    def test_admin_lista_as_12_pecas_com_link_de_previa(self):
        h = self.w.pagina_admin_trilha([], pecas=self.db.trilha_listar_pecas())
        self.assertIn("/admin/trilha/peca/1", h)
        self.assertIn(f"/admin/trilha/peca/{self.cfg.TRILHA_TOTAL}", h)

    def test_admin_sem_pecas_nao_quebra(self):
        h = self.w.pagina_admin_trilha([], pecas=[])
        self.assertIn("Nenhuma peça", h)


class _RotaPecaStub:
    """Stub mínimo pro `self` de `do_GET`: só `path` e `_html` -- mesmo padrão do
    `_RouteStub` de test_admin_precos.py, sem abrir socket real. A rota de prévia
    (`/admin/trilha/peca/<n>`) não lê cookie nem corpo, então nem `headers` nem
    `rfile` são necessários aqui."""

    def __init__(self, path):
        self.path = path

    def _html(self, s, code=200):
        return {"code": code, "body": s}


class TestRotaPreviaPeca(unittest.TestCase):
    """`/admin/trilha/peca/<n>`: prévia sob demanda, renderizada com a MESMA
    `pdf_trilha.montar_html` que vira PDF no WhatsApp -- por isso a prévia não
    pode divergir do envio real. Testa a rota de verdade via `serve.Handler.do_GET`
    (sem servidor real, mesmo padrão de `TestRotaAdminPrecos`) porque a ORDEM das
    guardas importa: token errado tem que barrar ANTES de qualquer parse de
    `numero` ou leitura de banco, e a rota mais específica
    (`/admin/trilha/peca/<n>`) tem que vencer `/admin/trilha` -- nenhuma das duas
    coisas aparece num teste de função pura."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["DSCURSO_ADMIN_TOKEN"] = "tok123"
        for m in ("config", "db", "trilha", "pdf_trilha", "serve"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, trilha, pdf_trilha, serve
        for m in (config, db, trilha, pdf_trilha, serve):
            importlib.reload(m)
        db.init()
        self.cfg, self.db, self.t, self.serve = config, db, trilha, serve
        self.t.semear()

    def tearDown(self):
        os.environ.pop("DSCURSO_ADMIN_TOKEN", None)

    def _get(self, path):
        return self.serve.Handler.do_GET(_RotaPecaStub(path))

    def test_sem_token_barra_antes_de_ler_o_banco(self):
        r = self._get("/admin/trilha/peca/1")
        self.assertEqual(r["code"], 403)

    def test_token_errado_barra_mesmo_com_numero_invalido(self):
        # prova a ordem das guardas: token errado + numero não-numérico ainda
        # devolve 403 (a guarda de admin roda primeiro) e não 404 (o parse do
        # `numero`, que viria depois, nunca chega a rodar).
        r = self._get("/admin/trilha/peca/abc?token=errado")
        self.assertEqual(r["code"], 403)

    def test_numero_nao_inteiro_com_token_bom_devolve_404_sem_traceback(self):
        r = self._get("/admin/trilha/peca/abc?token=tok123")
        self.assertEqual(r["code"], 404)

    def test_numero_inexistente_devolve_404(self):
        r = self._get(f"/admin/trilha/peca/{self.cfg.TRILHA_TOTAL + 1}?token=tok123")
        self.assertEqual(r["code"], 404)

    def test_numero_gigante_devolve_404_sem_estourar(self):
        # Rodada de correção 1: achado Important do revisor. Antes da correção, o
        # `int(path.rsplit(...))` cru não estourava (Python tem inteiro de precisão
        # arbitrária), então o valor gigante chegava intacto em `db.trilha_peca`, que
        # tenta vincular esse int no sqlite3 -- e AÍ estoura (`OverflowError: Python
        # int too large to convert to SQLite INTEGER`), sem try/except no caminho do
        # banco. Mesma classe de bug já corrigida no POST /trilha (`45350e2`), agora
        # fechada aqui reaproveitando `_trilha_numero_valido` em vez de validação
        # paralela. ~90 dígitos: bem além de qualquer INTEGER de 64 bits do SQLite,
        # mesma grandeza usada em TestTrilhaNumeroValido.
        r = self._get(f"/admin/trilha/peca/{'9' * 90}?token=tok123")
        self.assertEqual(r["code"], 404)

    def test_numero_zero_devolve_404(self):
        r = self._get("/admin/trilha/peca/0?token=tok123")
        self.assertEqual(r["code"], 404)

    def test_numero_negativo_devolve_404(self):
        r = self._get("/admin/trilha/peca/-1?token=tok123")
        self.assertEqual(r["code"], 404)

    def test_token_certo_devolve_a_mesma_renderizacao_do_pdf(self):
        titulo = self.db.trilha_peca(1)["titulo"]
        r = self._get("/admin/trilha/peca/1?token=tok123")
        self.assertEqual(r["code"], 200)
        self.assertIn(titulo, r["body"])

    def test_previa_nao_mostra_link_de_ferramenta_que_nao_existe(self):
        # Important 4 da revisão: a peça 1 do seed real declara `ferramenta:
        # planilha-custo-hora` no cabeçalho, mas seed/trilha/ferramentas/ só tem
        # .gitkeep -- a prévia do admin não pode divergir do envio real e mostrar
        # um botão que dá 404.
        self.assertTrue(self.db.trilha_peca(1)["ferramenta_slug"])   # a peça DECLARA ferramenta
        r = self._get("/admin/trilha/peca/1?token=tok123")
        self.assertEqual(r["code"], 200)
        self.assertNotIn("Baixar", r["body"])


if __name__ == "__main__":
    unittest.main()
