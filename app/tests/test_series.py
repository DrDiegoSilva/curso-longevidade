"""Fase 2 — séries de estudos (item 8)."""
import io
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _reload_db(tmp):
    os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(tmp, "t.db")
    os.environ.pop("DATABASE_URL", None)
    import importlib, db as _db
    importlib.reload(_db)
    _db.init()
    return _db


def _snapshot_env():
    """Guarda o ambiente ANTERIOR (antes de _reload_db mexer nele)."""
    return {k: os.environ.get(k) for k in ("DSCURSO_ARTIGOS_DB", "DATABASE_URL")}


def _restore_db(snap):
    """Restaura o ambiente pro estado do snapshot E reseta o estado do módulo
    `db` (via reload, que zera `_INITED`). Sem o reload, `db._INITED` continua
    True apontando pro banco temp já apagado; o próximo módulo de teste que
    faz `db.init()` preguiçoso (ex.: via subscribers.py) vira no-op e quebra
    com "no such table" no banco default restaurado — vaza pra frente por
    ordem alfabética (mesma lição do test_renovar_ja_recorrente.py sobre o
    test_preparar_pdf). Reusado pelo Task 2 (TestSeriesAtivar)."""
    for k, v in snap.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    import importlib, db as _db
    importlib.reload(_db)


class TestDbSeries(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.snap = _snapshot_env()
        self.db = _reload_db(self.tmp)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        _restore_db(self.snap)

    def test_criar_listar_obter(self):
        sid = self.db.criar_serie("Série GLP1")
        self.assertTrue(sid)
        todas = self.db.listar_series()
        self.assertEqual(len(todas), 1)
        self.assertEqual(todas[0]["nome"], "Série GLP1")
        self.assertEqual(todas[0]["status"], "rascunho")
        det = self.db.obter_serie(sid)
        self.assertEqual(det["serie"]["id"], sid)
        self.assertEqual(det["itens"], [])
        self.assertIsNone(self.db.obter_serie("nao-existe"))

    def test_adicionar_itens_ordena(self):
        sid = self.db.criar_serie("S")
        a = self.db.adicionar_serie_item(sid, "reserva", "r1", titulo="A", tema="Obesidade")
        b = self.db.adicionar_serie_item(sid, "candidato", "c1", titulo="B", tema="Obesidade")
        itens = self.db.obter_serie(sid)["itens"]
        self.assertEqual([i["ordem"] for i in itens], [0, 1])
        self.assertEqual([i["id"] for i in itens], [a, b])
        self.assertEqual(itens[0]["ref_tipo"], "reserva")
        self.assertEqual(itens[0]["titulo"], "A")
        self.assertEqual(itens[0]["data"], "")

    def test_adicionar_item_duplicado_nao_duplica(self):
        """FINDING 3 (revisão final): adicionar_serie_item com (serie_id,
        ref_tipo, ref_id) repetido devolve o item EXISTENTE em vez de criar uma
        segunda linha — um double-click no ➕ não pode agendar o mesmo estudo
        duas vezes."""
        sid = self.db.criar_serie("S")
        a = self.db.adicionar_serie_item(sid, "reserva", "r1", titulo="A")
        b = self.db.adicionar_serie_item(sid, "reserva", "r1", titulo="A de novo")
        self.assertEqual(a, b)
        itens = self.db.obter_serie(sid)["itens"]
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0]["titulo"], "A")   # não sobrescreveu com a 2ª chamada

    def test_adicionar_item_duplicado_concorrente_nao_duplica(self):
        """FINDING 3, corrida real: serve.py roda em ThreadingHTTPServer — um
        double-click de verdade chega como DUAS THREADS concorrentes, cada uma
        com sua própria conexão sqlite. Um SELECT-antes-do-INSERT sem UNIQUE
        constraint tem uma janela TOCTOU (as duas threads podem ver "não
        existe" antes de qualquer INSERT commitar). Sem a UNIQUE(serie_id,
        ref_tipo, ref_id) + ON CONFLICT DO NOTHING, 8 threads concorrentes
        produziam 3 linhas em vez de 1 (comprovado manualmente durante a
        revisão) — este teste trava essa garantia na suíte."""
        import threading
        sid = self.db.criar_serie("S")
        resultados, erros = [], []
        barreira = threading.Barrier(8)

        def worker():
            barreira.wait()
            try:
                resultados.append(
                    self.db.adicionar_serie_item(sid, "reserva", "rXX", titulo="Dup"))
            except Exception as e:
                erros.append(e)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(erros, [])
        self.assertEqual(len(set(resultados)), 1)   # todas as threads concordam no MESMO id
        self.assertEqual(len(self.db.obter_serie(sid)["itens"]), 1)

    def test_init_retroaplica_unique_index_em_serie_itens_pre_existente(self):
        """FINDING 3c (achado na re-revisão): CREATE TABLE IF NOT EXISTS é
        no-op numa tabela que já existe — então um banco de dev deixado por
        uma sessão ANTERIOR desta Fase 2 (ex.: Tasks 1-2 em a136efb, antes da
        UNIQUE(serie_id,ref_tipo,ref_id) inline) nunca ganha a constraint só
        por rodar db.init() de novo. Sem um índice único aplicado à parte,
        o INSERT...ON CONFLICT(serie_id,ref_tipo,ref_id) de
        adicionar_serie_item quebra com sqlite3.OperationalError('ON CONFLICT
        clause does not match any PRIMARY KEY or UNIQUE constraint') já no 1º
        insert (não só no duplicado) — produção não é afetada (a tabela não
        existe lá ainda), mas qualquer banco local de sessão anterior vira
        crash na hora de adicionar o 1º estudo a uma série."""
        import shutil
        import sqlite3
        tmp2 = tempfile.mkdtemp()
        try:
            caminho = os.path.join(tmp2, "pre_fix.db")
            # simula o schema de ANTES desta rodada: serie_itens sem UNIQUE.
            with sqlite3.connect(caminho) as c:
                c.execute("""
                    CREATE TABLE serie_itens (
                        id TEXT PRIMARY KEY,
                        serie_id TEXT,
                        ordem INTEGER DEFAULT 0,
                        ref_tipo TEXT,
                        ref_id TEXT,
                        titulo TEXT DEFAULT '',
                        tema TEXT DEFAULT '',
                        data TEXT DEFAULT '',
                        enviado INTEGER DEFAULT 0
                    )
                """)
            os.environ["DSCURSO_ARTIGOS_DB"] = caminho
            os.environ.pop("DATABASE_URL", None)
            import importlib
            import db as _db
            importlib.reload(_db)
            _db.init()   # não pode levantar; precisa retroaplicar o índice único
            sid = _db.criar_serie("S")
            a = _db.adicionar_serie_item(sid, "reserva", "r1", titulo="A")  # 1º insert
            b = _db.adicionar_serie_item(sid, "reserva", "r1", titulo="A de novo")  # dedup
            self.assertEqual(a, b)
            self.assertEqual(len(_db.obter_serie(sid)["itens"]), 1)
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)

    def test_reordenar_troca_vizinho(self):
        sid = self.db.criar_serie("S")
        a = self.db.adicionar_serie_item(sid, "reserva", "r1", titulo="A")
        b = self.db.adicionar_serie_item(sid, "reserva", "r2", titulo="B")
        self.db.reordenar_serie_item(b, "cima")
        ordem = [i["id"] for i in self.db.obter_serie(sid)["itens"]]
        self.assertEqual(ordem, [b, a])
        self.db.reordenar_serie_item(b, "cima")   # já é o primeiro -> no-op
        self.assertEqual([i["id"] for i in self.db.obter_serie(sid)["itens"]], [b, a])

    def test_remover_item(self):
        sid = self.db.criar_serie("S")
        a = self.db.adicionar_serie_item(sid, "reserva", "r1")
        self.db.adicionar_serie_item(sid, "reserva", "r2")
        self.db.remover_serie_item(a)
        itens = self.db.obter_serie(sid)["itens"]
        self.assertEqual([i["ref_id"] for i in itens], ["r2"])

    def test_atualizar_serie_e_item_data(self):
        sid = self.db.criar_serie("S")
        iid = self.db.adicionar_serie_item(sid, "reserva", "r1")
        self.db.atualizar_serie(sid, status="ativa", data_inicio="2026-08-10")
        s = self.db.obter_serie(sid)["serie"]
        self.assertEqual(s["status"], "ativa")
        self.assertEqual(s["data_inicio"], "2026-08-10")
        self.db.set_serie_item_data(iid, "2026-08-10")
        self.assertEqual(self.db.obter_serie(sid)["itens"][0]["data"], "2026-08-10")


class TestSeriesAtivar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.snap = _snapshot_env()
        self.db = _reload_db(self.tmp)
        self.dias = ["segunda", "terca", "quarta", "quinta", "sexta"]
        # uma segunda-feira ~2 semanas no futuro (determinístico)
        base = date.today() + timedelta(days=14)
        self.seg = base - timedelta(days=base.weekday())          # segunda
        self.seg_iso = self.seg.isoformat()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        _restore_db(self.snap)

    def _serie_com(self, n):
        sid = self.db.criar_serie("S")
        ids = []
        for k in range(n):
            rid = self.db.salvar_reserva({"tema": "Obesidade", "titulo_pt": f"R{k}",
                                          "resumo": "r", "tags": ["glp1"]})
            self.db.adicionar_serie_item(sid, "reserva", rid, titulo=f"R{k}", tema="Obesidade")
            ids.append(rid)
        return sid, ids

    def test_ativa_grava_n_dias_uteis_em_ordem_e_consome(self):
        import series
        sid, rids = self._serie_com(3)
        ok, msg = series.ativar_serie(sid, self.seg_iso, db_mod=self.db, dias_envio=self.dias)
        self.assertTrue(ok, msg)
        # seg, ter, qua recebem os 3 estudos em ordem
        esperados = [(self.seg + timedelta(days=k)).isoformat() for k in range(3)]
        for dia, rid in zip(esperados, rids):
            slot = self.db.agenda_slot(dia)
            self.assertEqual(slot["tipo"], "reserva")
            self.assertEqual(slot["ref_id"], rid)
            self.assertEqual(self.db.obter_reserva(rid)["status"], "agendado")  # consumido
        self.assertEqual(self.db.obter_serie(sid)["serie"]["status"], "ativa")
        self.assertEqual([i["data"] for i in self.db.obter_serie(sid)["itens"]], esperados)

    def test_pula_fixado_e_pulado(self):
        import series
        sid, rids = self._serie_com(2)
        ter = (self.seg + timedelta(days=1)).isoformat()
        qua = (self.seg + timedelta(days=2)).isoformat()
        self.db.agenda_fixar(ter, True)          # terça fixada -> pular
        ok, msg = series.ativar_serie(sid, self.seg_iso, db_mod=self.db, dias_envio=self.dias)
        self.assertTrue(ok, msg)
        datas = [i["data"] for i in self.db.obter_serie(sid)["itens"]]
        self.assertEqual(datas, [self.seg_iso, qua])   # seg e qua; terça pulada
        self.assertEqual(self.db.agenda_slot(ter)["fixado"], 1)  # fixado intacto

    def test_recusa_segunda_ativa(self):
        import series
        sid1, _ = self._serie_com(1)
        sid2, _ = self._serie_com(1)
        self.db.atualizar_serie(sid1, status="ativa")
        ok, msg = series.ativar_serie(sid2, self.seg_iso, db_mod=self.db, dias_envio=self.dias)
        self.assertFalse(ok)
        self.assertIn("ativa", msg.lower())

    def test_recusa_data_nao_util_e_abaixo_do_min(self):
        import series
        sid, _ = self._serie_com(1)
        sab = (self.seg + timedelta(days=5)).isoformat()   # sábado
        ok, _ = series.ativar_serie(sid, sab, db_mod=self.db, dias_envio=self.dias)
        self.assertFalse(ok)
        ok2, msg2 = series.ativar_serie(sid, self.seg_iso, dia_min="2099-01-01",
                                        db_mod=self.db, dias_envio=self.dias)
        self.assertFalse(ok2)
        self.assertIn("2099-01-01", msg2)

    def test_reconciliar_fecha_serie_vencida(self):
        import series
        sid, _ = self._serie_com(1)
        self.db.atualizar_serie(sid, status="ativa")
        self.db.set_serie_item_data(self.db.obter_serie(sid)["itens"][0]["id"], "2020-01-01")
        fechados = series.reconciliar(db_mod=self.db, hoje="2026-07-28")
        self.assertIn(sid, fechados)
        self.assertEqual(self.db.obter_serie(sid)["serie"]["status"], "concluida")

    def test_dia_minimo_pula_dia_ja_preparado(self):
        import series
        amanha = (date.today() + timedelta(days=1))
        # força amanhã a ser dia útil escolhendo dias_envio = todos
        todos = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
        preparado = {amanha.isoformat()}
        dm = series.dia_minimo_inicio(db_mod=self.db, hoje=date.today().isoformat(),
                                      dias_envio=todos, preparado_fn=lambda d: d in preparado)
        self.assertGreater(dm, amanha.isoformat())   # pulou amanhã (já preparado)

    def test_dias_envio_vazio_recusa_sem_raise(self):
        """dias_envio=[] (admin em modo 'não envia') não pode derrubar ativar_serie
        com ValueError vindo de _dias_uteis_validos — precisa devolver (False, msg)
        sem escrever nada na agenda nem mudar o status da série."""
        import series
        sid, _ = self._serie_com(1)
        ok, msg = series.ativar_serie(sid, self.seg_iso, db_mod=self.db, dias_envio=[])
        self.assertFalse(ok)
        self.assertIn("dia", msg.lower())
        self.assertIsNone(self.db.agenda_slot(self.seg_iso))       # nada escrito na agenda
        self.assertEqual(self.db.obter_serie(sid)["serie"]["status"], "rascunho")  # intocada

    def test_dia_minimo_inicio_dias_envio_vazio_nao_levanta(self):
        """FINDING 1 (CRITICAL, revisão final): dias_envio=[] é estado real e
        alcançável (admin salva /admin/envio sem nenhum dia marcado ->
        daily._dias_envio() devolve set()). dia_minimo_inicio() é avaliado como
        ARGUMENTO nas duas rotas (GET /series e POST acao=ativar), ANTES de
        qualquer guard poder ajudar — precisa devolver um sentinel falsy ("")
        em vez de levantar ValueError, senão a tela inteira cai com 500."""
        import series
        dm = series.dia_minimo_inicio(db_mod=self.db, dias_envio=[])
        self.assertEqual(dm, "")

    def test_ativar_data_inicio_malformada_recusa_sem_raise(self):
        """FINDING 2 (IMPORTANT, revisão final): data_inicio malformada/vazia
        chega via POST urlencoded direto (sem passar pelo <input type=date> do
        navegador) e não pode derrubar ativar_serie com ValueError do
        datetime.strptime — precisa devolver (False, msg) amigável."""
        import series
        sid, _ = self._serie_com(1)
        for data_ruim in ("10/08/2026", "", "2026-13-45"):
            with self.subTest(data_ruim=data_ruim):
                ok, msg = series.ativar_serie(sid, data_ruim, db_mod=self.db, dias_envio=self.dias)
                self.assertFalse(ok)
                self.assertTrue(msg)
                self.assertEqual(self.db.obter_serie(sid)["serie"]["status"], "rascunho")

    def test_serie_com_item_duplicado_ocupa_1_dia(self):
        """FINDING 3 (revisão final): dois add_item com o mesmo (serie_id,
        ref_tipo, ref_id) — ex.: double-click no ➕ — não pode virar 2 linhas na
        série nem ocupar 2 dias consecutivos da agenda com o MESMO estudo."""
        import series
        sid = self.db.criar_serie("S")
        rid = self.db.salvar_reserva({"tema": "Obesidade", "titulo_pt": "Dup",
                                      "resumo": "r", "tags": ["glp1"]})
        self.db.adicionar_serie_item(sid, "reserva", rid, titulo="Dup", tema="Obesidade")
        self.db.adicionar_serie_item(sid, "reserva", rid, titulo="Dup", tema="Obesidade")
        self.assertEqual(len(self.db.obter_serie(sid)["itens"]), 1)
        ok, msg = series.ativar_serie(sid, self.seg_iso, db_mod=self.db, dias_envio=self.dias)
        self.assertTrue(ok, msg)
        ter = (self.seg + timedelta(days=1)).isoformat()
        self.assertIsNone(self.db.agenda_slot(ter))   # não ocupou o dia seguinte

    def test_libera_dia_com_fila_devolve_payload_a_fila(self):
        """Um dia com tipo='fila' (materializar_agenda usa isso quando a reserva
        está rasa) carrega um artigo já triado (custo de IA) no payload — ativar
        uma série ali precisa devolver esse artigo à fila (queue_store.devolver),
        não descartá-lo."""
        import json
        from unittest import mock
        import series
        sid, _ = self._serie_com(1)
        payload = {"titulo": "Fila X", "tema": "Obesidade", "score": 5, "url": "https://x"}
        self.db.agenda_upsert(self.seg_iso, tipo="fila", payload=json.dumps(payload))
        with mock.patch("queue_store.devolver") as m_devolver:
            ok, msg = series.ativar_serie(sid, self.seg_iso, db_mod=self.db, dias_envio=self.dias)
        self.assertTrue(ok, msg)
        m_devolver.assert_called_once_with(payload)
        slot = self.db.agenda_slot(self.seg_iso)
        self.assertEqual(slot["tipo"], "reserva")   # sobrescrito pelo item da série

    def test_contexto_pagina(self):
        import series
        sid = self.db.criar_serie("S")
        self.db.salvar_reserva({"tema": "Obesidade", "titulo_pt": "Reta",
                                "resumo": "r", "tags": ["retatrutida"]})
        ctx = series.contexto_pagina(db_mod=self.db, serie_aberta_id=sid, termo="retatrutida")
        self.assertEqual(len(ctx["series"]), 1)
        self.assertEqual(ctx["aberta"]["serie"]["id"], sid)
        self.assertEqual(ctx["resultados"][0]["titulo"], "Reta")
        self.assertEqual(series.contexto_pagina(db_mod=self.db)["resultados"], [])


class TestPaginaSeries(unittest.TestCase):
    def _ctx(self, aberta=None, resultados=None):
        return {"series": [{"id": "s1", "nome": "Série GLP1", "status": "rascunho"}],
                "aberta": aberta, "resultados": resultados or []}

    def test_lista_e_form_nova(self):
        import site_web
        html = site_web.pagina_series(self._ctx(), "tok")
        self.assertIn("Série GLP1", html)
        self.assertIn("/series", html)
        self.assertIn('name="acao"', html)          # form de criar
        self.assertIn("value=\"criar\"", html)

    def test_montador_com_itens_e_ativar(self):
        import site_web
        aberta = {"serie": {"id": "s1", "nome": "Série GLP1", "status": "rascunho", "data_inicio": ""},
                  "itens": [{"id": "i1", "ordem": 0, "ref_tipo": "reserva", "ref_id": "r1",
                             "titulo": "Retatrutida 24s", "tema": "Obesidade", "data": ""}]}
        resultados = [{"tipo": "reserva", "id": "r2", "titulo": "Semaglutida", "tema": "Obesidade",
                       "tags": ["semaglutida"]}]
        html = site_web.pagina_series(self._ctx(aberta, resultados), "tok",
                                      serie_aberta_id="s1", dia_min="2026-08-10")
        self.assertIn("Retatrutida 24s", html)       # item na série
        self.assertIn("Semaglutida", html)           # resultado da busca
        self.assertIn('value="ativar"', html)        # form de ativar (rascunho)
        self.assertIn("2026-08-10", html)            # min da data de início

    def test_escapa_titulo_malicioso(self):
        import site_web
        aberta = {"serie": {"id": "s1", "nome": "S", "status": "rascunho", "data_inicio": ""},
                  "itens": [{"id": "i1", "ordem": 0, "ref_tipo": "reserva", "ref_id": "r1",
                             "titulo": "<script>x</script>", "tema": "", "data": ""}]}
        html = site_web.pagina_series(self._ctx(aberta), "tok", serie_aberta_id="s1")
        self.assertNotIn("<script>x</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_ativa_nao_mostra_form_ativar(self):
        import site_web
        aberta = {"serie": {"id": "s1", "nome": "S", "status": "ativa", "data_inicio": "2026-08-10"},
                  "itens": []}
        html = site_web.pagina_series(self._ctx(aberta), "tok", serie_aberta_id="s1")
        self.assertNotIn('value="ativar"', html)
        self.assertIn("ativa", html.lower())


class _SeriesRotaStub:
    """Stub mínimo pro `self` de `do_GET`/`do_POST` quando `path == '/series'`. Não
    abre socket real: em vez de instanciar `http.server.BaseHTTPRequestHandler`
    (que dispara `handle()` sozinho no `__init__`), criamos uma classe que HERDA de
    `serve.Handler` só pra reusar os métodos de verdade que a rota chama de fato
    (`_series_upload`, `_parse_multipart`, `do_GET`, `do_POST`) e sobrescrevemos só o
    que dependeria de uma conexão real: `path`/`headers`/`rfile` (entrada da
    requisição) e `_html`/`_redirect`/`_sessao` (saída + sessão — mesmo padrão do
    `_RotaStub` de test_reaceite.py e do `_Stub` de test_regressoes_correcoes.py, que
    sobrescrevem só o que o método sob teste toca)."""

    def __init__(self, path, body=b"", ctype="application/x-www-form-urlencoded",
                 sessao=None):
        self.path = path
        self.headers = {"Content-Length": str(len(body)), "Content-Type": ctype}
        self.rfile = io.BytesIO(body)
        self._sess = sessao

    def _sessao(self):
        return self._sess

    def _html(self, s, code=200):
        return (code, s)

    def _redirect(self, location, token=None, clear=False):
        return ("REDIRECT", location)


def _make_stub_cls():
    """`_SeriesRotaStub` precisa herdar de `serve.Handler` (não `object`) pra ter
    `_series_upload`/`_parse_multipart`/`do_GET`/`do_POST` de verdade — mas `serve` só
    existe depois do `import` dentro do `setUp` de cada teste (mesmo padrão dos outros
    testes deste arquivo, que importam `db`/`series`/`site_web` só depois de apontar
    `DSCURSO_ARTIGOS_DB` pro banco temporário). Construída sob demanda em vez de uma
    subclasse import-time fixa."""
    import serve
    # `_SeriesRotaStub` PRIMEIRO na MRO: precisa que `_html`/`_redirect`/`_sessao`
    # (que sobrescrevem os de verdade) vençam a resolução de nome; `serve.Handler`
    # depois só entra pros métodos que o stub não define (`do_GET`, `do_POST`,
    # `_series_upload`, `_parse_multipart`).
    return type("_SeriesRotaStubHandler", (_SeriesRotaStub, serve.Handler), {})


class TestRotaSeries(unittest.TestCase):
    """Fix round 1 (revisão): (1) o gate token-only barrava admin logado por sessão
    sem token na URL — `_admin_nav` só bota `?token=` no link quando RECEBE um token,
    então o admin que entra por sessão e clica em 'Séries' apanhava 403; a correção
    espelha `/curadoria`/`/agenda` (token OU sessão de admin). (2) a rota inteira
    (gate + dispatch de `acao` + a ordem multipart-antes-do-urlencoded) não tinha
    cobertura direta — só regressão da suíte. Os testes abaixo exercitam
    `serve.Handler.do_GET`/`do_POST` de verdade (via `_SeriesRotaStub`), não só
    `series.py`/`site_web.py` isolados."""

    ADMIN_WPP = "5599988877766"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.snap = _snapshot_env()
        self.db = _reload_db(self.tmp)
        # `auth_web.eh_admin` lê `config.ADMIN_WHATSAPPS` via um `import config` no
        # TOPO do módulo (referência presa em auth_web.py, não recalculada por
        # chamada). Se algum teste anterior da suíte já fez `sys.modules.pop("config")`
        # + reimport (troca o OBJETO do módulo) DEPOIS que `auth_web` foi carregado
        # pela primeira vez, `auth_web` fica preso no objeto config VELHO — meu
        # `import config` abaixo pegaria o objeto NOVO, e mutar `ADMIN_WHATSAPPS`
        # nele ficaria invisível pro `eh_admin` real (403 mesmo com sessão de admin).
        # Achado ao rodar a suíte inteira: passava isolado, falhava no discover.
        # `importlib.reload` (não pop+reimport) resincroniza sem trocar identidade.
        import importlib
        if "auth_web" in sys.modules:
            importlib.reload(sys.modules["auth_web"])
        import config, auth_web
        self._token0 = config.ADMIN_TOKEN
        self._wpps0 = config.ADMIN_WHATSAPPS
        config.ADMIN_TOKEN = "segredo-teste"
        config.ADMIN_WHATSAPPS = [self.ADMIN_WPP]
        self.config = config
        self.Stub = _make_stub_cls()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.config.ADMIN_TOKEN = self._token0
        self.config.ADMIN_WHATSAPPS = self._wpps0
        _restore_db(self.snap)

    def test_get_sem_token_sem_sessao_403(self):
        stub = self.Stub("/series")
        code, _ = stub.do_GET()
        self.assertEqual(code, 403)

    def test_get_com_token_valido_renderiza(self):
        stub = self.Stub("/series?token=segredo-teste")
        code, html = stub.do_GET()
        self.assertEqual(code, 200)
        self.assertIn("Séries de estudos", html)

    def test_get_com_sessao_admin_sem_token_renderiza(self):
        # ACHADO (revisão, Finding 1): sem a correção, isto devolvia 403 — o gate era
        # token-only. `_admin_nav` só linka com token quando RECEBE um; um admin que
        # entrou por sessão (login normal) e clicou no atalho ficava sem porta nenhuma.
        stub = self.Stub("/series", sessao={"whatsapp": self.ADMIN_WPP})
        code, html = stub.do_GET()
        self.assertEqual(code, 200)
        self.assertIn("Séries de estudos", html)

    def test_post_criar_cria_serie_e_redireciona(self):
        stub = self.Stub("/series", body=b"acao=criar&nome=Serie+X&token=segredo-teste")
        tag, location = stub.do_POST()
        self.assertEqual(tag, "REDIRECT")
        self.assertTrue(location.startswith("/series?serie="))
        self.assertIn("token=segredo-teste", location)
        criadas = self.db.listar_series()
        self.assertEqual(len(criadas), 1)
        self.assertEqual(criadas[0]["nome"], "Serie X")

    def test_post_acao_desconhecida_nao_levanta_e_redireciona(self):
        stub = self.Stub("/series", body=b"acao=chuta-o-balde&token=segredo-teste")
        tag, location = stub.do_POST()          # não pode levantar (nenhum elif bate)
        self.assertEqual(tag, "REDIRECT")
        self.assertTrue(location.startswith("/series?"))
        self.assertEqual(self.db.listar_series(), [])   # nada foi criado

    def test_post_sem_token_nem_sessao_403(self):
        stub = self.Stub("/series", body=b"acao=criar&nome=X")
        code, _ = stub.do_POST()
        self.assertEqual(code, 403)

    def test_post_multipart_nao_e_engolido_pelo_parser_urlencoded(self):
        # a ordem do branch em do_POST importa: o dispatch multipart precisa vir ANTES
        # de `form = up.parse_qs(raw.decode("utf-8"))`, senão bytes binários de um
        # upload de PDF seriam (mal) interpretados como urlencoded. Sobrescrevemos
        # `_series_upload` (instância, não classe) só pra provar QUE ele foi chamado —
        # o processamento real do PDF/texto já tem cobertura própria em
        # `_curadoria_upload`/curadoria.adicionar_meu_estudo noutros arquivos.
        chamadas = []
        stub = self.Stub("/series", body=b"--X\r\nlixo binario nao-urlencoded\r\n--X--",
                         ctype="multipart/form-data; boundary=X")
        stub._series_upload = lambda raw, ctype: chamadas.append((raw, ctype)) or ("UPLOAD", ctype)
        resultado = stub.do_POST()
        self.assertEqual(len(chamadas), 1)
        self.assertEqual(chamadas[0][1], "multipart/form-data; boundary=X")
        self.assertEqual(resultado, ("UPLOAD", "multipart/form-data; boundary=X"))

    def test_series_upload_gate_token_ou_sessao(self):
        # mesmo Finding 1, mas no branch multipart de verdade (_series_upload): o token
        # vem de `campos.get("token")` (multipart), não de `g("token")` — forma
        # diferente, mesma semântica OR-com-sessão.
        raw = (b'--X\r\nContent-Disposition: form-data; name="serie"\r\n\r\ns1\r\n'
               b'--X\r\nContent-Disposition: form-data; name="texto"\r\n\r\n'
               b'texto qualquer\r\n--X--\r\n')
        ctype = "multipart/form-data; boundary=X"
        sem_credencial = self.Stub("/series", body=raw, ctype=ctype)
        code, _ = sem_credencial._series_upload(raw, ctype)
        self.assertEqual(code, 403)
        com_sessao = self.Stub("/series", body=raw, ctype=ctype,
                               sessao={"whatsapp": self.ADMIN_WPP})
        resultado = com_sessao._series_upload(raw, ctype)
        self.assertNotEqual(resultado[0], 403)   # passou do gate (pode falhar depois
                                                  # por texto curto demais — não é o que
                                                  # este teste verifica)

    def test_get_dias_envio_vazio_nao_derruba_a_pagina(self):
        """FINDING 1 (CRITICAL, revisão final), fim-a-fim: com dias_envio=""
        salvo (admin desmarcou todos os dias em /admin/envio), o GET /series
        chamava series.dia_minimo_inicio() como ARGUMENTO — a exceção estourava
        antes de qualquer guard rodar e a rota inteira caía com 500."""
        self.db.set_config("dias_envio", "")
        stub = self.Stub("/series?token=segredo-teste")
        code, html = stub.do_GET()
        self.assertEqual(code, 200)
        self.assertIn("Séries de estudos", html)

    def test_post_ativar_dias_envio_vazio_redireciona_com_msg_amigavel(self):
        """Mesma raiz do teste acima, mas no POST acao=ativar — que também avalia
        series.dia_minimo_inicio() como argumento antes de chamar ativar_serie."""
        self.db.set_config("dias_envio", "")
        sid = self.db.criar_serie("S")
        self.db.adicionar_serie_item(sid, "reserva", "r1", titulo="R1")
        body = (f"acao=ativar&serie={sid}&data_inicio=2026-08-10"
                f"&token=segredo-teste").encode()
        stub = self.Stub("/series", body=body)
        tag, location = stub.do_POST()
        self.assertEqual(tag, "REDIRECT")   # não pode levantar/500
        import urllib.parse as _up
        self.assertIn("dia", _up.unquote(location).lower())
        self.assertEqual(self.db.obter_serie(sid)["serie"]["status"], "rascunho")

    def test_post_ativar_data_malformada_nao_levanta(self):
        """FINDING 2 (IMPORTANT, revisão final), fim-a-fim: data_inicio chega
        malformada num POST urlencoded direto (sem o <input type=date> do
        navegador no meio) — a rota não pode devolver 500."""
        sid = self.db.criar_serie("S")
        self.db.adicionar_serie_item(sid, "reserva", "r1", titulo="R1")
        body = (f"acao=ativar&serie={sid}&data_inicio=10%2F08%2F2026"
                f"&token=segredo-teste").encode()
        stub = self.Stub("/series", body=body)
        tag, location = stub.do_POST()
        self.assertEqual(tag, "REDIRECT")
        self.assertEqual(self.db.obter_serie(sid)["serie"]["status"], "rascunho")

    def test_post_add_item_duplicado_avisa_ja_esta_na_serie(self):
        """FINDING 3 (revisão final), fim-a-fim: 2º add_item do MESMO estudo
        (double-click no ➕) precisa avisar 'já está na série' em vez de
        duplicar silenciosamente a linha."""
        sid = self.db.criar_serie("S")
        body = (f"acao=add_item&serie={sid}&tipo=reserva&id=r1&titulo=A"
                f"&tema=Obesidade&token=segredo-teste").encode()
        self.Stub("/series", body=body).do_POST()
        tag, location = self.Stub("/series", body=body).do_POST()
        self.assertEqual(tag, "REDIRECT")
        import urllib.parse as _up
        self.assertIn("já está na série", _up.unquote(location).lower())
        self.assertEqual(len(self.db.obter_serie(sid)["itens"]), 1)
