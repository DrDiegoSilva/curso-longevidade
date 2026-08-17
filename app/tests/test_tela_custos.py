"""Item 40 — a tela que finalmente lê o ledger de custos.

O ledger grava desde 2026-08-14 e até aqui gravava no vazio. Esta entrega só LÊ.
Standalone: python3 app/tests/test_tela_custos.py"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _snapshot_env():
    return (os.environ.get("DSCURSO_ARTIGOS_DB"), os.environ.get("DATABASE_URL"))


def _reload_db(tmp):
    os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(tmp, "t.db")
    os.environ.pop("DATABASE_URL", None)
    import importlib, db as _db
    importlib.reload(_db)
    _db.init()
    return _db


def _restore_db(snap):
    import importlib
    a, d = snap
    if a is None:
        os.environ.pop("DSCURSO_ARTIGOS_DB", None)
    else:
        os.environ["DSCURSO_ARTIGOS_DB"] = a
    if d is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = d
    import db as _db
    importlib.reload(_db)


class _Base(unittest.TestCase):
    def setUp(self):
        self.snap = _snapshot_env()
        self.tmp = tempfile.mkdtemp()
        self.db = _reload_db(self.tmp)

    def tearDown(self):
        _restore_db(self.snap)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _uso(self, quando, acao="dossie", modelo="claude-sonnet-4-6",
             tin=1000, tout=100, chamadas=1):
        """Grava direto com o carimbo que eu quero — `registrar_ia_uso` usa `now()`."""
        import secrets
        with self.db._conn() as c:
            c.execute("""INSERT INTO ia_uso (id,quando,acao,modelo,tokens_in,tokens_out,chamadas)
                         VALUES (?,?,?,?,?,?,?)""",
                      (secrets.token_hex(8), quando, acao, modelo, tin, tout, chamadas))


class TestResumoIaUso(_Base):
    def test_agrupa_por_dia_acao_e_modelo(self):
        self._uso("2026-08-14T10:00:00", "dossie", tin=1000, tout=100)
        self._uso("2026-08-14T18:00:00", "dossie", tin=500, tout=50)
        self._uso("2026-08-14T19:00:00", "kit", tin=200, tout=20)
        r = self.db.resumo_ia_uso("2026-08-01")
        dossie = [x for x in r if x["acao"] == "dossie"]
        self.assertEqual(len(dossie), 1)                 # as duas viraram uma linha
        self.assertEqual(dossie[0]["tokens_in"], 1500)
        self.assertEqual(dossie[0]["tokens_out"], 150)
        self.assertEqual(dossie[0]["chamadas"], 2)
        self.assertEqual(dossie[0]["dia"], "2026-08-14")

    def test_dias_diferentes_nao_se_misturam(self):
        self._uso("2026-08-14T10:00:00", "dossie")
        self._uso("2026-08-15T10:00:00", "dossie")
        self.assertEqual(len(self.db.resumo_ia_uso("2026-08-01")), 2)

    def test_modelos_diferentes_nao_se_misturam(self):
        """O custo depende do modelo — somar Haiku com Opus perderia a informação."""
        self._uso("2026-08-14T10:00:00", "titulo", modelo="claude-haiku-4-5-20251001")
        self._uso("2026-08-14T11:00:00", "titulo", modelo="claude-opus-4-8")
        self.assertEqual(len(self.db.resumo_ia_uso("2026-08-01")), 2)

    def test_desde_e_inclusivo_com_carimbo_completo(self):
        """Prova inclusividade real: carimbo idêntico ao da linha deve ser incluído."""
        self._uso("2026-08-14T10:00:00", "dossie")
        # Chamar com carimbo COMPLETO e idêntico: deve incluir a linha
        self.assertEqual(len(self.db.resumo_ia_uso("2026-08-14T10:00:00")), 1)

    def test_desde_com_data_curta_como_uso_real(self):
        """Uso real: a tela chama com "2026-08-14" (data curta), esperando tudo aquele dia."""
        self._uso("2026-08-14T00:00:00", "dossie")
        self._uso("2026-08-14T23:59:59", "kit")
        # Chamar com data curta: deve incluir tudo que começar com "2026-08-14"
        r = self.db.resumo_ia_uso("2026-08-14")
        self.assertEqual(len(r), 2)

    def test_antes_do_desde_fica_de_fora(self):
        self._uso("2026-08-13T23:59:59", "dossie")
        self.assertEqual(self.db.resumo_ia_uso("2026-08-14"), [])

    def test_ate_e_exclusivo(self):
        self._uso("2026-08-14T10:00:00", "dossie")
        self._uso("2026-08-20T10:00:00", "dossie")
        r = self.db.resumo_ia_uso("2026-08-01", "2026-08-15")
        self.assertEqual([x["dia"] for x in r], ["2026-08-14"])

    def test_ordena_do_dia_mais_novo_para_o_mais_velho(self):
        self._uso("2026-08-14T10:00:00", "dossie")
        self._uso("2026-08-16T10:00:00", "kit")
        self.assertEqual([x["dia"] for x in self.db.resumo_ia_uso("2026-08-01")],
                         ["2026-08-16", "2026-08-14"])

    def test_janela_sem_nada_devolve_lista_vazia(self):
        self.assertEqual(self.db.resumo_ia_uso("2026-08-01"), [])

    def test_filtrar_por_prefixo_do_mes_bate_com_consultar_direto_pelo_mes(self):
        """Item 5 (Minor): a rota deixa de consultar o mês E os 30 dias -- consulta só os
        30 dias e deriva o mês filtrando em Python pelo prefixo do dia. Prova que essa
        derivação devolve exatamente o mesmo conjunto que consultar direto pelo mês (a
        janela do mês é sempre subconjunto da de 30 dias)."""
        self._uso("2026-07-20T10:00:00", "dossie", tin=500, tout=0)   # mês anterior
        self._uso("2026-08-01T10:00:00", "dossie", tin=1000, tout=0)
        self._uso("2026-08-14T10:00:00", "kit", tin=2000, tout=0)
        l30 = self.db.resumo_ia_uso("2026-07-17")
        direto = self.db.resumo_ia_uso("2026-08-01")
        filtrado = [l for l in l30 if (l.get("dia") or "").startswith("2026-08")]

        def _chave(x):
            return (x["dia"], x["acao"], x["modelo"])

        self.assertEqual(sorted(filtrado, key=_chave), sorted(direto, key=_chave))


class TestDinheiro(unittest.TestCase):
    """As linhas agregadas viram R$. O preço vem de config.PRECOS_IA e o cálculo é na
    leitura — preço errado é recálculo, não perda."""

    def setUp(self):
        import importlib, config, ia_custo
        importlib.reload(config)
        importlib.reload(ia_custo)
        self.cfg, self.ia = config, ia_custo

    def _linha(self, dia="2026-08-14", acao="dossie", modelo="claude-sonnet-4-6",
               tin=1_000_000, tout=0):
        return {"dia": dia, "acao": acao, "modelo": modelo,
                "tokens_in": tin, "tokens_out": tout, "chamadas": 1}

    def test_total_soma_as_linhas(self):
        p_in, _ = self.cfg.PRECOS_IA["claude-sonnet-4-6"]
        t = self.ia.total_usd([self._linha(), self._linha()])
        self.assertAlmostEqual(t, p_in * 2)

    def test_por_acao_soma_dentro_da_acao(self):
        r = self.ia.por_acao([self._linha(acao="dossie"), self._linha(acao="dossie")])
        self.assertEqual(len(r), 1)
        p_in, _ = self.cfg.PRECOS_IA["claude-sonnet-4-6"]
        self.assertAlmostEqual(r[0]["usd"], p_in * 2)

    def test_por_acao_ordena_do_maior_gasto_para_o_menor(self):
        """É o que diz ao Diego o que cortar se achar caro — ordem errada esconde isso."""
        linhas = [self._linha(acao="barato", tin=1000),
                  self._linha(acao="caro", tin=5_000_000),
                  self._linha(acao="medio", tin=100_000)]
        self.assertEqual([x["acao"] for x in self.ia.por_acao(linhas)],
                         ["caro", "medio", "barato"])

    def test_por_acao_traz_o_valor_em_reais(self):
        r = self.ia.por_acao([self._linha()])
        self.assertAlmostEqual(r[0]["brl"], r[0]["usd"] * self.cfg.USD_BRL)

    def test_modelos_diferentes_na_mesma_acao_somam_com_o_preco_de_cada_um(self):
        linhas = [self._linha(acao="titulo", modelo="claude-haiku-4-5-20251001"),
                  self._linha(acao="titulo", modelo="claude-sonnet-4-6")]
        h_in, _ = self.cfg.PRECOS_IA["claude-haiku-4-5-20251001"]
        s_in, _ = self.cfg.PRECOS_IA["claude-sonnet-4-6"]
        r = self.ia.por_acao(linhas)
        self.assertEqual(len(r), 1)
        self.assertAlmostEqual(r[0]["usd"], h_in + s_in)

    def test_por_dia_agrupa_por_data(self):
        linhas = [self._linha(dia="2026-08-14"), self._linha(dia="2026-08-14"),
                  self._linha(dia="2026-08-15")]
        d = self.ia.por_dia(linhas)
        p_in, _ = self.cfg.PRECOS_IA["claude-sonnet-4-6"]
        self.assertAlmostEqual(d["2026-08-14"], p_in * 2)
        self.assertAlmostEqual(d["2026-08-15"], p_in)

    def test_lista_vazia_nao_explode(self):
        self.assertEqual(self.ia.por_acao([]), [])
        self.assertEqual(self.ia.por_dia([]), {})
        self.assertEqual(self.ia.total_usd([]), 0.0)

    def test_modelo_sem_preco_entra_como_zero_e_nao_derruba(self):
        r = self.ia.por_acao([self._linha(modelo="modelo-que-nao-existe")])
        self.assertEqual(r[0]["usd"], 0.0)

    def test_por_dia_com_dia_ausente_nao_levanta(self):
        """Dia ausente/None cai num balde vazio; resto soma correto. Defensável, precisa
        estar verificado."""
        linhas = [self._linha(dia=None), self._linha(dia="2026-08-15")]
        d = self.ia.por_dia(linhas)
        p_in, _ = self.cfg.PRECOS_IA["claude-sonnet-4-6"]
        # A linha com dia=None vai pro balde ""
        self.assertAlmostEqual(d.get(""), p_in)
        # A linha real soma corretamente
        self.assertAlmostEqual(d["2026-08-15"], p_in)
        # Total está correto
        self.assertEqual(len(d), 2)


class TestTela(unittest.TestCase):
    def setUp(self):
        import importlib, site_web
        importlib.reload(site_web)
        self.sw = site_web

    def _dados(self, **kw):
        d = {"mes": "2026-08", "ate": "2026-08-16", "usd": 12.34, "brl": 67.87,
             "cotacao": 5.5, "assinantes": 42,
             "por_acao": [{"acao": "dossie", "usd": 8.0, "brl": 44.0},
                          {"acao": "kit", "usd": 4.34, "brl": 23.87}],
             "dias": [{"dia": "2026-08-16", "ledger": 1.2}],
             "fatura": "sem_chave", "total_ledger": 20.0, "total_fatura": 22.5}
        d.update(kw)
        return d

    def test_devolve_pagina_completa(self):
        html = self.sw.pagina_custos(self._dados(), "tok")
        self.assertTrue(html.lstrip().lower().startswith("<!doctype html>"))

    def test_mostra_o_gasto_do_mes_em_reais(self):
        html = self.sw.pagina_custos(self._dados(), "tok")
        self.assertIn("67,87", html.replace(".", ","))

    def test_mostra_a_cotacao_usada(self):
        """Número em R$ sem dizer a cotação é número sem procedência.

        Âncora tem que ser a frase inteira: "5,5" sozinho casa com qualquer resto de
        CSS global (ex.: "font-size:15,5px" da folha de estilo de `_pagina`), e o teste
        passaria mesmo sem a cotação aparecer na tela — já aconteceu."""
        html = self.sw.pagina_custos(self._dados(), "tok")
        self.assertIn("cotação R$ 5,50", html.replace(".", ","))

    def test_titulo_deixa_explicito_que_e_ate_hoje_nao_o_mes_fechado(self):
        """Item 2 (IMPORTANT): "no mês" sozinho, no dia 2, é ~1/15 do gasto real numa
        tela de decidir preço. O rótulo precisa dizer até quando."""
        d = self._dados(mes="2026-08", ate="2026-08-02")
        html = self.sw.pagina_custos(d, "tok")
        self.assertIn("até 02/08", html)

    def test_por_assinante_tambem_deixa_explicito_o_ate(self):
        d = self._dados(mes="2026-08", ate="2026-08-02", assinantes=1, brl=10.0)
        html = self.sw.pagina_custos(d, "tok")
        self.assertIn("no mês até 02/08", html)

    def test_o_rotulo_usa_o_dado_recebido_e_nao_chama_datetime_por_conta_propria(self):
        """Prova que o render não inventa `datetime.now()` internamente: se chamasse,
        essa data "impossível" (ano 2099) seria ignorada silenciosamente."""
        html = self.sw.pagina_custos(self._dados(ate="2099-12-31"), "tok")
        self.assertIn("até 31/12", html)

    def test_mostra_quantos_assinantes_dividem_a_conta(self):
        """Âncora na FRASE inteira, não em "42" sozinho: o CSS global de `_pagina` tem
        `clamp(42px,...)` e `rgba(20,51,42,...)` -- provado por mutação (armadilha nº 5
        desta entrega): com `assinantes=41` o teste antigo (`assertIn("42", html)`)
        continuava passando, porque o "42" da folha de estilo global casava sozinho."""
        html = self.sw.pagina_custos(self._dados(assinantes=42), "tok")
        self.assertIn("Com <strong>42</strong> assinantes ativos", html)

    def test_diz_que_o_custo_e_fixo(self):
        """Sem essa frase ele olha um número que cai sozinho e tira a conclusão errada
        sobre o próprio produto."""
        html = self.sw.pagina_custos(self._dados(), "tok").lower()
        self.assertIn("fixo", html)

    def test_lista_as_acoes_do_maior_pro_menor_na_ordem_que_recebeu(self):
        """Busca a partir da seção "Onde o dinheiro vai": o CSS global de `_pagina` tem
        `-webkit-` (vendor prefix), e "kit" é substring disso — procurar do início do
        documento faria o teste comparar a posição errada."""
        html = self.sw.pagina_custos(self._dados(), "tok")
        inicio = html.index("Onde o dinheiro vai")
        self.assertLess(html.index("dossie", inicio), html.index("kit", inicio))

    def test_sem_chave_explica_o_que_falta(self):
        html = self.sw.pagina_custos(self._dados(fatura="sem_chave"), "tok")
        self.assertIn("DSCURSO_ANTHROPIC_ADMIN_KEY", html)

    def test_chave_recusada_diz_isso(self):
        html = self.sw.pagina_custos(self._dados(fatura="recusada"), "tok").lower()
        self.assertIn("recusada", html)

    def test_erro_na_api_diz_isso_sem_derrubar_a_pagina(self):
        html = self.sw.pagina_custos(self._dados(fatura="erro"), "tok")
        self.assertTrue(html.lstrip().lower().startswith("<!doctype html>"))
        self.assertIn("67,87", html.replace(".", ","))      # o lado nosso continua lá

    def test_dia_a_dia_so_tem_a_nossa_coluna(self):
        """Item 1 (CRITICAL): comparar dia a dia mistura fusos diferentes -- nós
        carimbamos em horário de São Paulo, a Anthropic bate em UTC. A tabela "Dia a dia"
        não pode fingir ter coluna de fatura/diferença nem com a fatura lida ("ok").

        Âncora original (`test_com_fatura_mostra_as_tres_colunas`) casava em "fatura" e
        "diferen", que também aparecem no PARÁGRAFO de aviso emitido sempre que
        `estado == "ok"` -- provado por mutação: com `dias=[]` (sem nenhum `<th>` de
        tabela) o teste antigo continuava passando."""
        d = self._dados(fatura="ok", dias=[{"dia": "2026-08-16", "ledger": 1.0}])
        html = self.sw.pagina_custos(d, "tok")
        inicio = html.index("Dia a dia")
        fim = html.index("Conferência com a fatura")
        trecho_tabela = html[inicio:fim]
        self.assertNotIn("Fatura", trecho_tabela)
        self.assertNotIn("Diferença", trecho_tabela)
        self.assertIn("Nosso medidor", trecho_tabela)

    def test_conferencia_mostra_os_dois_totais_e_a_diferenca(self):
        """Item 1: o bloco novo "Conferência com a fatura" traz os TRÊS números do mesmo
        período de 30 dias -- nosso total, o da fatura, e a diferença entre eles."""
        d = self._dados(fatura="ok", total_ledger=20.0, total_fatura=22.5)
        html = self.sw.pagina_custos(d, "tok")
        inicio = html.index("Conferência com a fatura")
        trecho = html[inicio:].replace(".", ",")
        self.assertIn("20,00", trecho)     # nosso ledger
        self.assertIn("22,50", trecho)     # fatura
        self.assertIn("2,50", trecho)      # diferença

    def test_conferencia_explica_a_diferenca_de_fuso(self):
        """Item 1: sem essa explicação, o Diego veria uma discrepância grande e
        concluiria que a NOSSA tabela de preços está errada, quando é só o corte do dia
        em fusos diferentes."""
        html = self.sw.pagina_custos(self._dados(fatura="ok"), "tok")
        inicio = html.index("Conferência com a fatura")
        trecho = html[inicio:].lower()
        self.assertIn("utc", trecho)
        self.assertIn("são paulo", trecho)
        self.assertIn("período", trecho)

    def test_conferencia_sem_fatura_lida_nao_finge_numero(self):
        """Item 1: nos estados sem_chave/recusada/erro não houve leitura nenhuma pra
        comparar -- mesmo que a rota (por engano) mande total_ledger/total_fatura, o
        bloco de conferência não pode fingir ter um número."""
        for estado in ("sem_chave", "recusada", "erro"):
            d = self._dados(fatura=estado, total_ledger=999.0, total_fatura=999.0)
            html = self.sw.pagina_custos(d, "tok")
            inicio = html.index("Conferência com a fatura")
            trecho = html[inicio:].replace(".", ",")
            self.assertNotIn("999,00", trecho, f"estado={estado} não devia ter número")

    def test_avisa_que_a_fatura_e_da_organizacao_inteira(self):
        """Sem isso a tela mente por omissão: a diferença pode ser uso de outra origem,
        não preço errado na nossa tabela."""
        html = self.sw.pagina_custos(self._dados(fatura="ok"), "tok").lower()
        self.assertIn("organiza", html)

    def test_escapa_o_nome_da_acao(self):
        d = self._dados(por_acao=[{"acao": "<script>alert(1)</script>", "usd": 1.0,
                                   "brl": 5.5}])
        self.assertNotIn("<script>alert(1)</script>", self.sw.pagina_custos(d, "tok"))

    def test_mes_sem_gasto_nenhum_nao_quebra(self):
        d = self._dados(usd=0.0, brl=0.0, por_acao=[], dias=[])
        html = self.sw.pagina_custos(d, "tok")
        self.assertTrue(html.lstrip().lower().startswith("<!doctype html>"))

    def test_zero_assinantes_nao_divide_por_zero(self):
        html = self.sw.pagina_custos(self._dados(assinantes=0), "tok")
        self.assertTrue(html.lstrip().lower().startswith("<!doctype html>"))

    def test_o_nav_de_admin_ganhou_o_link_de_custos(self):
        self.assertIn("/admin/custos", self.sw._admin_nav("tok"))

    def test_fatura_parcial_avisa_que_a_leitura_ficou_incompleta(self):
        """`anthropic_admin.custo_por_dia` devolve `parcial=True` quando descartou algum
        valor ilegível ou bateu no teto de páginas. Sem esse aviso na tela, uma fatura
        curta em silêncio faz o Diego concluir que a nossa tabela de preços superestima o
        gasto — o oposto do que aconteceu."""
        html = self.sw.pagina_custos(self._dados(fatura="ok", parcial=True), "tok").lower()
        self.assertIn("parcial", html)

    def test_fatura_completa_nao_mostra_aviso_de_parcial(self):
        """Âncora em "subestimada" (palavra inteira, sem tag no meio) — "leitura parcial"
        nunca aparece como substring contígua no HTML real: o texto emitido é
        'Leitura <strong>parcial</strong> da fatura', com a tag `<strong>` partindo a
        frase. Uma asserção ancorada nela passaria sempre, independente do gate."""
        html = self.sw.pagina_custos(self._dados(fatura="ok", parcial=False), "tok").lower()
        self.assertNotIn("subestimada", html)

    def test_parcial_ausente_no_dict_nao_quebra_a_pagina(self):
        """`dados` sem a chave "parcial" (ex.: fatura sem_chave) não pode levantar."""
        d = self._dados(fatura="sem_chave")
        d.pop("parcial", None)
        html = self.sw.pagina_custos(d, "tok")
        self.assertTrue(html.lstrip().lower().startswith("<!doctype html>"))


import io


class _RouteStub:
    def __init__(self, path):
        self.path = path
        self.rfile = io.BytesIO(b"")
        self.headers = {"Content-Length": "0"}
        self.client_address = ("127.0.0.1", 0)

    def _html(self, s, code=200):
        return {"code": code, "body": s}

    def _redirect(self, location, token=None, clear=False):
        return {"redirect": location}

    def _sessao(self):
        return None


class TestRotaCustos(_Base):
    def setUp(self):
        super().setUp()
        self.snap_token = os.environ.get("DSCURSO_ADMIN_TOKEN")
        os.environ["DSCURSO_ADMIN_TOKEN"] = "tok123"
        import importlib, config, serve
        importlib.reload(config)
        importlib.reload(serve)
        self.serve = serve

    def tearDown(self):
        if self.snap_token is None:
            os.environ.pop("DSCURSO_ADMIN_TOKEN", None)
        else:
            os.environ["DSCURSO_ADMIN_TOKEN"] = self.snap_token
        import importlib, config
        importlib.reload(config)
        super().tearDown()

    def _get(self, path):
        return self.serve.Handler.do_GET(_RouteStub(path))

    def test_sem_token_403(self):
        self.assertEqual(self._get("/admin/custos")["code"], 403)

    def test_com_token_abre(self):
        r = self._get("/admin/custos?token=tok123")
        self.assertEqual(r["code"], 200)
        self.assertIn("Custo de IA", r["body"])

    def test_abre_mesmo_sem_nenhum_uso_gravado(self):
        r = self._get("/admin/custos?token=tok123")
        self.assertEqual(r["code"], 200)

    def test_mostra_o_que_foi_gravado_no_mes(self):
        from datetime import datetime
        hoje = datetime.now().strftime("%Y-%m-%d")
        self._uso(f"{hoje}T10:00:00", "dossie", tin=1_000_000, tout=0)
        r = self._get("/admin/custos?token=tok123")
        self.assertIn("dossie", r["body"])

    def _stub_fatura(self, valor):
        """Substitui `anthropic_admin.custo_por_dia` e restaura com `addCleanup` --
        mesmo se o teste falhar no meio. Sem isso o stub vaza pros testes seguintes da
        classe (a ordem do unittest é alfabética, então o vazamento é silencioso: os
        testes continuam passando, mas deixam de exercitar o caminho que dizem testar)."""
        import anthropic_admin
        original = anthropic_admin.custo_por_dia
        self.addCleanup(setattr, anthropic_admin, "custo_por_dia", original)
        anthropic_admin.custo_por_dia = valor

    def test_a_fatura_fora_do_ar_nao_derruba_a_tela(self):
        self._stub_fatura(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("explodiu")))
        r = self._get("/admin/custos?token=tok123")
        self.assertEqual(r["code"], 200)

    def test_fatura_parcial_mostra_o_aviso_na_pagina_de_verdade(self):
        """Prova a fiação: a Task 4 provou o RENDER chamando `pagina_custos` direto com um
        `dados` montado à mão -- nunca passou pela rota. Aqui `anthropic_admin.custo_por_dia`
        devolve `parcial=True` de verdade, e é `serve.py` quem precisa repassar a chave."""
        self._stub_fatura(lambda *a, **k: {
            "estado": "ok", "dias": {"2026-08-14": 1.23}, "parcial": True})
        r = self._get("/admin/custos?token=tok123")
        self.assertEqual(r["code"], 200)
        self.assertIn("parcial", r["body"].lower())

    def test_fatura_completa_nao_mostra_o_aviso_na_pagina_de_verdade(self):
        """Espelho do teste acima com `parcial=False`. Âncora em "subestimada" (palavra
        inteira, sem tag HTML no meio) -- "leitura parcial" nunca aparece como substring
        contígua no HTML real: o texto emitido é 'Leitura <strong>parcial</strong> da
        fatura', com a tag partindo a frase. Ver `site_web._FATURA_PARCIAL_AVISO`."""
        self._stub_fatura(lambda *a, **k: {
            "estado": "ok", "dias": {"2026-08-14": 1.23}, "parcial": False})
        r = self._get("/admin/custos?token=tok123")
        self.assertEqual(r["code"], 200)
        self.assertNotIn("subestimada", r["body"].lower())

    def test_a_rota_consulta_o_ledger_uma_unica_vez(self):
        """Item 5 (Minor): a janela do mês corrente é sempre subconjunto da janela de 30
        dias (um mês tem no máximo 31 dias) -- bater duas vezes no banco pela mesma
        tabela é trabalho repetido. Prova por contagem de chamadas a `db.resumo_ia_uso`."""
        import db
        chamadas = []
        original = db.resumo_ia_uso

        def _contando(*a, **k):
            chamadas.append((a, k))
            return original(*a, **k)

        self.addCleanup(setattr, db, "resumo_ia_uso", original)
        db.resumo_ia_uso = _contando
        self._get("/admin/custos?token=tok123")
        self.assertEqual(len(chamadas), 1)

    def test_o_gasto_do_mes_bate_com_o_calculo_direto_apos_juntar_as_consultas(self):
        """Item 5: confere que juntar as duas consultas numa só (mês derivado por
        filtro em Python) não mudou o número exibido -- é o teste que o item pede."""
        from datetime import datetime
        import config, ia_custo, site_web
        hoje = datetime.now().strftime("%Y-%m-%dT10:00:00")
        self._uso(hoje, "dossie", tin=1_000_000, tout=0)
        r = self._get("/admin/custos?token=tok123")
        usd = ia_custo.custo_usd("claude-sonnet-4-6", 1_000_000, 0)
        brl = ia_custo.em_brl(usd)
        self.assertIn(f"R$ {site_web._rs(brl)}", r["body"])

    def test_a_rota_manda_o_dia_de_hoje_pro_rotulo_do_mes(self):
        """Item 2 (IMPORTANT): a rota precisa mandar até quando o mês foi somado --
        `site_web.pagina_custos` não pode inventar `datetime.now()` no render."""
        from datetime import datetime
        hoje = datetime.now()
        r = self._get("/admin/custos?token=tok123")
        self.assertIn(f"até {hoje.strftime('%d/%m')}", r["body"])

    def test_a_rota_monta_o_bloco_de_conferencia_com_fatura_ok(self):
        """Item 1 (CRITICAL): confere a fiação de ponta a ponta -- com a fatura
        respondendo "ok" de verdade (via stub), a rota calcula total_ledger/total_fatura
        e o bloco "Conferência com a fatura" chega à página com os dois números."""
        from datetime import datetime
        hoje = datetime.now().strftime("%Y-%m-%d")
        self._uso(f"{hoje}T10:00:00", "dossie", tin=1_000_000, tout=0)
        self._stub_fatura(lambda *a, **k: {
            "estado": "ok", "dias": {hoje: 2.5}, "parcial": False})
        r = self._get("/admin/custos?token=tok123")
        self.assertIn("Conferência com a fatura", r["body"])
        self.assertIn("2,50", r["body"].replace(".", ","))


if __name__ == "__main__":
    unittest.main()
