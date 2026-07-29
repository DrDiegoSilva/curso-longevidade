"""Fase 2 — séries de estudos (item 8)."""
import contextlib
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


class TestSeriesHardening(unittest.TestCase):
    """Task 5 — endurecimento do caminho de ATIVAÇÃO (2 Critical + 5 Important
    da revisão final em 3 fatias, todos reproduzidos com código rodando).
    Cada teste nomeia o achado que trava."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.snap = _snapshot_env()
        self.db = _reload_db(self.tmp)
        self.dias = ["segunda", "terca", "quarta", "quinta", "sexta"]
        base = date.today() + timedelta(days=14)
        self.seg = base - timedelta(days=base.weekday())     # uma segunda no futuro
        self.seg_iso = self.seg.isoformat()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        _restore_db(self.snap)

    # ── helpers ──
    def _reserva(self, titulo="R"):
        return self.db.salvar_reserva({"tema": "Obesidade", "titulo_pt": titulo,
                                       "resumo": "r", "tags": ["glp1"]})

    def _serie_com(self, n, nome="S"):
        sid = self.db.criar_serie(nome)
        ids = []
        for k in range(n):
            rid = self._reserva(f"R{k}")
            self.db.adicionar_serie_item(sid, "reserva", rid, titulo=f"R{k}", tema="Obesidade")
            ids.append(rid)
        return sid, ids

    def _segunda_mes_1_digito(self):
        """Primeira segunda-feira futura cujo MÊS tem 1 dígito — condição pro bug
        de comparação-como-texto do piso ('2026-6-29' > '2026-07-30' porque
        '6' > '0'). Calculada a partir de hoje pra não vencer com o calendário."""
        d = date.today() + timedelta(days=14)
        d = d - timedelta(days=d.weekday())
        while d.month >= 10:
            d = d + timedelta(days=7)
        return d

    # ── CRITICAL 1: falha na ativação não pode trancar a feature ──
    def test_c1_falha_total_deixa_serie_em_rascunho_e_nao_tranca(self):
        """CRITICAL 1: com TODOS os dias falhando, o `atualizar_serie(status='ativa')`
        rodava incondicional. A série virava 'ativa' com zero itens datados, e
        `reconciliar` (que filtra `if i.get("data")`) nunca fechava — 'Já existe uma
        série ativa' pra sempre, sem ação de cancelar/concluir na rota."""
        from unittest import mock
        import series
        sid, rids = self._serie_com(3)
        with mock.patch.object(self.db, "agenda_upsert",
                               side_effect=RuntimeError("UNIQUE constraint failed: agenda.data")):
            ok, msg = series.ativar_serie(sid, self.seg_iso, db_mod=self.db, dias_envio=self.dias)
        self.assertFalse(ok)
        det = self.db.obter_serie(sid)
        self.assertEqual(det["serie"]["status"], "rascunho")      # NÃO ficou ativa
        self.assertEqual([i["data"] for i in det["itens"]], ["", "", ""])
        self.assertIn("agenda.data", msg)                          # erro real chega ao admin
        # e a feature continua utilizável: a mesma série ativa de novo depois
        ok2, msg2 = series.ativar_serie(sid, self.seg_iso, db_mod=self.db, dias_envio=self.dias)
        self.assertTrue(ok2, msg2)

    def test_c1_falha_parcial_fecha_como_incompleta_e_nao_ignora_item_sem_data(self):
        """CRITICAL 1 (irmão): com ALGUNS itens datados, `reconciliar` fechava a
        série como 'concluida' ignorando calado o item órfão (nunca agendado)."""
        from unittest import mock
        import series
        sid, _ = self._serie_com(3)
        real = self.db.agenda_upsert
        n = {"i": 0}

        def falha_no_terceiro(*a, **kw):
            n["i"] += 1
            if n["i"] == 3:
                raise RuntimeError("boom no 3º dia")
            return real(*a, **kw)

        with mock.patch.object(self.db, "agenda_upsert", side_effect=falha_no_terceiro):
            ok, msg = series.ativar_serie(sid, self.seg_iso, db_mod=self.db, dias_envio=self.dias)
        self.assertFalse(ok)                     # falha parcial AVISA
        self.assertIn("boom no 3º dia", msg)
        det = self.db.obter_serie(sid)
        self.assertEqual(det["serie"]["status"], "ativa")          # 2 dias foram gravados
        self.assertEqual([i["data"] for i in det["itens"]].count(""), 1)
        fechados = series.reconciliar(db_mod=self.db, hoje="2099-01-01")
        self.assertIn(sid, fechados)
        self.assertEqual(self.db.obter_serie(sid)["serie"]["status"], "incompleta")

    # ── CRITICAL 2: "uma série ativa" era check-then-act ──
    def test_c2_ativacao_concorrente_de_series_diferentes_deixa_so_uma_ativa(self):
        """CRITICAL 2: o check (series.py:149) e a escrita (:182) tinham o loop de
        gravação inteiro no meio. ThreadingHTTPServer = 1 thread por clique:
        8 ativações concorrentes deixavam 8 séries 'ativa'."""
        import threading
        import series
        sids = [self._serie_com(1, nome=f"S{k}")[0] for k in range(8)]
        barreira = threading.Barrier(len(sids))
        res, erros = [], []

        def worker(sid):
            barreira.wait()
            try:
                res.append(series.ativar_serie(sid, self.seg_iso, db_mod=self.db,
                                               dias_envio=self.dias))
            except Exception as e:          # noqa: BLE001 — o contrato é "não crasha"
                erros.append(e)

        ths = [threading.Thread(target=worker, args=(s,)) for s in sids]
        for t in ths:
            t.start()
        for t in ths:
            t.join()
        self.assertEqual(erros, [])
        ativas = [s for s in self.db.listar_series() if s["status"] == "ativa"]
        self.assertEqual(len(ativas), 1)
        self.assertEqual(sum(1 for ok, _ in res if ok), 1)

    def test_c2_duplo_clique_na_mesma_serie_ativa_uma_vez_so(self):
        """CRITICAL 2 (caso realista): 8 cliques na MESMA série devolviam ok=True
        em 7-8 deles e a reserva era consumida/devolvida várias vezes
        (_liberar_dia do 2º clique devolve ao pool o que o 1º acabou de prender)."""
        import threading
        import series
        sid, rids = self._serie_com(1)
        barreira = threading.Barrier(8)
        res, erros = [], []

        def worker():
            barreira.wait()
            try:
                res.append(series.ativar_serie(sid, self.seg_iso, db_mod=self.db,
                                               dias_envio=self.dias))
            except Exception as e:          # noqa: BLE001
                erros.append(e)

        ths = [threading.Thread(target=worker) for _ in range(8)]
        for t in ths:
            t.start()
        for t in ths:
            t.join()
        self.assertEqual(erros, [])
        self.assertEqual(sum(1 for ok, _ in res if ok), 1)
        self.assertEqual(self.db.obter_reserva(rids[0])["status"], "agendado")
        self.assertEqual(self.db.agenda_slot(self.seg_iso)["ref_id"], rids[0])

    def test_c2_init_retroaplica_indice_de_serie_ativa_com_duplicatas(self):
        """CRITICAL 2, retrofit: `db.init()` roda em bancos que JÁ têm linhas em
        `series` — se duas já estiverem 'ativa' (estado deixado pela corrida
        antiga), o CREATE UNIQUE INDEX falha e derrubaria o init inteiro."""
        import shutil
        import sqlite3
        tmp2 = tempfile.mkdtemp()
        try:
            caminho = os.path.join(tmp2, "duas_ativas.db")
            # `with sqlite3.connect(...)` commita mas NÃO fecha — daí o closing()
            # explícito, pra este teste não somar ResourceWarning à saída da suíte.
            with contextlib.closing(sqlite3.connect(caminho)) as c, c:
                c.execute("""CREATE TABLE series (id TEXT PRIMARY KEY, nome TEXT, status TEXT,
                             data_inicio TEXT, criado_em TEXT, ativada_em TEXT)""")
                c.execute("INSERT INTO series VALUES ('a','A','ativa','','2026-01-01','2026-01-01')")
                c.execute("INSERT INTO series VALUES ('b','B','ativa','','2026-01-02','2026-01-02')")
            os.environ["DSCURSO_ARTIGOS_DB"] = caminho
            os.environ.pop("DATABASE_URL", None)
            import importlib
            import db as _db
            importlib.reload(_db)
            _db.init()                       # não pode levantar
            ativas = [s for s in _db.listar_series() if s["status"] == "ativa"]
            self.assertEqual(len(ativas), 1)
            self.assertEqual(ativas[0]["id"], "a")       # mantém a ativada primeiro
            self.assertEqual(_db.obter_serie("b")["serie"]["status"], "incompleta")
            # e a trava passa a valer de verdade
            self.assertFalse(_db.reivindicar_serie_ativa("b", "2026-08-10", "2026-08-01"))
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)

    # ── IMPORTANT 3: data sem zero-padding burlava o piso ──
    def test_i3_data_sem_zero_padding_respeita_o_piso(self):
        """IMPORTANT 3: strptime aceita '2026-6-29', mas o piso era comparado como
        TEXTO — '2026-6-29' < '2026-07-30' é False ('6' > '0'). Resultado provado:
        ok=True, slot escrito num dia anterior ao piso e reserva consumida."""
        import series
        sid, rids = self._serie_com(1)
        d = self._segunda_mes_1_digito()
        crua = f"{d.year}-{d.month}-{d.day}"          # sem zero-padding
        piso = (d + timedelta(days=7)).isoformat()    # piso uma semana DEPOIS
        ok, msg = series.ativar_serie(sid, crua, dia_min=piso, db_mod=self.db,
                                      dias_envio=self.dias)
        self.assertFalse(ok, msg)
        self.assertIsNone(self.db.agenda_slot(d.isoformat()))          # nada na agenda
        self.assertEqual(self.db.obter_reserva(rids[0])["status"], "pronto")  # não gastou
        self.assertEqual(self.db.obter_serie(sid)["serie"]["status"], "rascunho")

    def test_i3_data_sem_zero_padding_e_gravada_normalizada(self):
        """Minor: `data_inicio` era persistida crua, então '2026-6-29' ficava
        gravado assim e ordena errado em qualquer comparação textual da coluna."""
        import series
        sid, _ = self._serie_com(1)
        d = self._segunda_mes_1_digito()
        crua = f"{d.year}-{d.month}-{d.day}"
        ok, msg = series.ativar_serie(sid, crua, db_mod=self.db, dias_envio=self.dias)
        self.assertTrue(ok, msg)
        self.assertEqual(self.db.obter_serie(sid)["serie"]["data_inicio"], d.isoformat())

    # ── IMPORTANT 4: sem regra própria de "não no passado" ──
    def test_i4_recusa_data_no_passado_mesmo_sem_dia_min(self):
        """IMPORTANT 4: o piso só existia porque o ÚNICO chamador de produção passa
        `dia_min`. Sem ele, uma segunda no passado virava slot histórico na agenda."""
        import series
        sid, rids = self._serie_com(1)
        passado = date.today() - timedelta(days=7)
        passado = passado - timedelta(days=passado.weekday())    # segunda no passado
        ok, msg = series.ativar_serie(sid, passado.isoformat(), db_mod=self.db,
                                      dias_envio=self.dias)
        self.assertFalse(ok, msg)
        self.assertIsNone(self.db.agenda_slot(passado.isoformat()))
        self.assertEqual(self.db.obter_reserva(rids[0])["status"], "pronto")
        self.assertEqual(self.db.obter_serie(sid)["serie"]["status"], "rascunho")

    # ── IMPORTANT 5: sem guarda de "já agendado" / "já enviado" ──
    def test_i5_recusa_estudo_que_ja_ocupa_um_dia_da_agenda(self):
        """IMPORTANT 5: `db.buscar_por_tag` filtra só por tag — nunca por status.
        Uma reserva já presa a um slot entrava na série e era gravada num SEGUNDO
        dia: mesmo ref_id em dois slots = mesmo estudo preparado e enviado 2x.
        `daily.materializar` já guarda isso (daily.py:166)."""
        import series
        sid = self.db.criar_serie("S")
        rid = self._reserva("Já agendada")
        outro = (self.seg + timedelta(days=30)).isoformat()
        self.db.agenda_upsert(outro, tipo="reserva", ref_id=rid, tema="Obesidade",
                              titulo="Já agendada")
        self.db.marcar_reserva_agendado(rid)
        self.db.adicionar_serie_item(sid, "reserva", rid, titulo="Já agendada", tema="Obesidade")
        ok, msg = series.ativar_serie(sid, self.seg_iso, db_mod=self.db, dias_envio=self.dias)
        self.assertFalse(ok, msg)
        self.assertIn("Já agendada", msg)                   # o admin sabe QUAL estudo
        self.assertIsNone(self.db.agenda_slot(self.seg_iso))
        self.assertEqual(self.db.agenda_slot(outro)["ref_id"], rid)   # slot original intacto
        self.assertEqual(self.db.obter_serie(sid)["serie"]["status"], "rascunho")

    def test_i5_recusa_estudo_ja_enviado(self):
        """IMPORTANT 5 (irmão): uma reserva com status='enviado' era aceita e o
        `marcar_reserva_agendado` a devolvia pra 'agendado' — estudo já mandado
        seria mandado de novo. `daily.materializar` só lê status='pronto'
        (daily.py:165)."""
        import series
        sid = self.db.criar_serie("S")
        rid = self._reserva("Já enviada")
        self.db.marcar_reserva_enviado(rid)
        self.db.adicionar_serie_item(sid, "reserva", rid, titulo="Já enviada", tema="Obesidade")
        ok, msg = series.ativar_serie(sid, self.seg_iso, db_mod=self.db, dias_envio=self.dias)
        self.assertFalse(ok, msg)
        self.assertEqual(self.db.obter_reserva(rid)["status"], "enviado")   # não voltou
        self.assertIsNone(self.db.agenda_slot(self.seg_iso))
        self.assertEqual(self.db.obter_serie(sid)["serie"]["status"], "rascunho")

    # ── IMPORTANT 6: 'ordem' com TOCTOU reembaralhava a sequência curada ──
    def test_i6_ordens_concorrentes_nao_se_repetem(self):
        """IMPORTANT 6: `SELECT MAX(ordem)+1` + INSERT simples, sem
        UNIQUE(serie_id, ordem) atrás. 10 threads com 10 itens DISTINTOS produziam
        ordem = [0,0,0,0,0,1,1,2,2,2] — a sequência curada, que é o ponto da série,
        reembaralhava sem erro nenhum."""
        import threading
        sid = self.db.criar_serie("S")
        barreira = threading.Barrier(10)
        erros = []

        def worker(k):
            barreira.wait()
            try:
                self.db.adicionar_serie_item(sid, "reserva", f"r{k}", titulo=f"R{k}")
            except Exception as e:          # noqa: BLE001
                erros.append(e)

        ths = [threading.Thread(target=worker, args=(k,)) for k in range(10)]
        for t in ths:
            t.start()
        for t in ths:
            t.join()
        self.assertEqual(erros, [])
        itens = self.db.obter_serie(sid)["itens"]
        self.assertEqual(len(itens), 10)
        self.assertEqual(sorted(i["ordem"] for i in itens), list(range(10)))

    def test_i6_reordenar_continua_funcionando_com_a_constraint(self):
        """IMPORTANT 6, armadilha: `reordenar_serie_item` troca duas 'ordem'. Um
        UNIQUE(serie_id, ordem) ingênuo faz o estado INTERMEDIÁRIO do swap violar
        a constraint — a correção não pode quebrar a reordenação."""
        sid = self.db.criar_serie("S")
        a = self.db.adicionar_serie_item(sid, "reserva", "r1", titulo="A")
        b = self.db.adicionar_serie_item(sid, "reserva", "r2", titulo="B")
        c = self.db.adicionar_serie_item(sid, "reserva", "r3", titulo="C")
        self.db.reordenar_serie_item(c, "cima")
        self.assertEqual([i["id"] for i in self.db.obter_serie(sid)["itens"]], [a, c, b])
        self.db.reordenar_serie_item(a, "baixo")
        self.assertEqual([i["id"] for i in self.db.obter_serie(sid)["itens"]], [c, a, b])
        self.assertEqual([i["ordem"] for i in self.db.obter_serie(sid)["itens"]], [0, 1, 2])

    def test_i6_init_repara_ordens_duplicadas_pre_existentes(self):
        """IMPORTANT 6, retrofit: um banco escrito pela versão com TOCTOU já tem
        ordens repetidas — o CREATE UNIQUE INDEX falharia e mataria o init."""
        import shutil
        import sqlite3
        tmp2 = tempfile.mkdtemp()
        try:
            caminho = os.path.join(tmp2, "ordens_dup.db")
            with contextlib.closing(sqlite3.connect(caminho)) as c, c:
                c.execute("""CREATE TABLE serie_itens (
                             id TEXT PRIMARY KEY, serie_id TEXT, ordem INTEGER DEFAULT 0,
                             ref_tipo TEXT, ref_id TEXT, titulo TEXT DEFAULT '',
                             tema TEXT DEFAULT '', data TEXT DEFAULT '', enviado INTEGER DEFAULT 0)""")
                for k, ordem in enumerate([0, 0, 0, 1, 1]):
                    c.execute("INSERT INTO serie_itens (id,serie_id,ordem,ref_tipo,ref_id,titulo) "
                              "VALUES (?,?,?,?,?,?)",
                              (f"i{k}", "s1", ordem, "reserva", f"r{k}", f"R{k}"))
            os.environ["DSCURSO_ARTIGOS_DB"] = caminho
            os.environ.pop("DATABASE_URL", None)
            import importlib
            import db as _db
            importlib.reload(_db)
            _db.init()                       # não pode levantar
            with contextlib.closing(sqlite3.connect(caminho)) as c:
                ordens = [r[0] for r in c.execute(
                    "SELECT ordem FROM serie_itens WHERE serie_id='s1' ORDER BY ordem")]
            self.assertEqual(ordens, [0, 1, 2, 3, 4])     # renumerado, sem repetição
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)

    # ── minor: data_inicio None não pode crashar ──
    def test_minor_data_inicio_none_nao_levanta(self):
        """Minor: o guard capturava só ValueError, então `data_inicio=None` batia
        num TypeError do strptime. Não alcançável pela rota atual (serve.py:494
        sempre entrega string), mas o contrato declarado é 'não crasha'."""
        import series
        sid, _ = self._serie_com(1)
        ok, msg = series.ativar_serie(sid, None, db_mod=self.db, dias_envio=self.dias)
        self.assertFalse(ok)
        self.assertTrue(msg)
        self.assertEqual(self.db.obter_serie(sid)["serie"]["status"], "rascunho")

    # ── IMPORTANT (introduzido pela própria correção): janela entre o claim e o rollback ──
    def test_escape_entre_claim_e_gravacao_devolve_a_serie_pra_rascunho(self):
        """A correção do CRITICAL 1 tomava o claim e SÓ depois entrava no try/except
        por dia — `_dias_livres` (que chama db.agenda_slot) e o próprio rollback
        ficavam de fora. Um erro ali (banco travado, timeout) deixava a série
        'ativa' com zero itens datados: estado que o `reconciliar` se RECUSA a
        fechar de propósito (pra não correr com o claim) e que a rota não sabe
        cancelar — a trava permanente do Finding 1 por uma porta mais estreita."""
        from unittest import mock
        import series
        sid, rids = self._serie_com(2)
        with mock.patch.object(self.db, "agenda_slot",
                               side_effect=RuntimeError("database is locked")):
            ok, msg = series.ativar_serie(sid, self.seg_iso, db_mod=self.db, dias_envio=self.dias)
        self.assertFalse(ok)
        self.assertIn("database is locked", msg)          # erro real chega ao admin
        self.assertEqual(self.db.obter_serie(sid)["serie"]["status"], "rascunho")
        self.assertEqual(self.db.obter_reserva(rids[0])["status"], "pronto")   # nada consumido
        # e a feature NÃO ficou trancada: a mesma série ativa normalmente depois
        ok2, msg2 = series.ativar_serie(sid, self.seg_iso, db_mod=self.db, dias_envio=self.dias)
        self.assertTrue(ok2, msg2)
        self.assertEqual(self.db.obter_serie(sid)["serie"]["status"], "ativa")

    def test_demover_series_ativas_extras_nao_estoura_em_variavel_solta(self):
        """MINOR: `extras` era ligada DENTRO do `with` e lida depois dele.

        Com o `_Wrap.__exit__` real (devolve None, não suprime) o erro de dentro
        do bloco propaga e a linha `if extras:` nunca roda — o NameError relatado
        NÃO acontece hoje (medido, ver relatório). O que existe é a fragilidade:
        a ligação só é segura por causa desse detalhe do context manager. Este
        teste trava as DUAS pontas — o erro real continua propagando, e nem num
        `__exit__` que suprima a função quebra por variável solta."""
        from unittest import mock

        class ConexaoQueLevanta:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return None          # igual ao _Wrap: NÃO suprime

            def execute(self, *a):
                raise RuntimeError("boom no banco")

        class ConexaoQueSuprime(ConexaoQueLevanta):
            def __exit__(self, *a):
                return True          # suprime — única via pra variável solta

        with mock.patch.object(self.db, "_conn", return_value=ConexaoQueLevanta()):
            with self.assertRaises(RuntimeError) as ctx:
                self.db._demover_series_ativas_extras()
        self.assertIn("boom no banco", str(ctx.exception))   # erro real, não mascarado

        with mock.patch.object(self.db, "_conn", return_value=ConexaoQueSuprime()):
            self.db._demover_series_ativas_extras()          # não pode levantar


class TestAgendaDevolverCandidato(unittest.TestCase):
    """Task 1 (Cancelar série) — bug pré-existente: `agenda_devolver` trata
    'reserva' e 'fila' mas ignorava 'candidato' — o slot virava 'vazio' e o
    candidato nunca voltava pro estoque (fica preso em status 'agendado' pra
    sempre). `series._liberar_dia` trata os três; a inconsistência era do
    `db`. Efeito colateral ao vivo: o botão 'pular' (agenda_pular) num dia
    de candidato vazava o candidato."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.snap = _snapshot_env()
        self.db = _reload_db(self.tmp)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        _restore_db(self.snap)

    def _novo_candidato(self, chave, titulo):
        self.db.salvar_candidatos([{"tema": "Obesidade", "titulo": titulo, "chave": chave,
                                    "score": 6, "tipo": "varredura"}])
        return self.db.listar_candidatos(status="novo")[0]["id"]

    def test_devolver_dia_de_candidato_volta_ao_estoque(self):
        cid = self._novo_candidato("cser-cand-1", "C1")
        self.db.marcar_candidato_agendado(cid)
        self.db.agenda_upsert("2026-08-10", tipo="candidato", ref_id=cid, titulo="C1")

        self.db.agenda_devolver("2026-08-10")

        self.assertEqual(self.db.agenda_slot("2026-08-10")["tipo"], "vazio")
        cand = self.db.obter_candidato(cid)
        self.assertEqual(cand["status"], "novo",
                         "candidato tem que voltar pro estoque, senão vaza")

    def test_devolver_preserva_fixado(self):
        cid = self._novo_candidato("cser-cand-2", "C2")
        self.db.marcar_candidato_agendado(cid)
        self.db.agenda_upsert("2026-08-11", tipo="candidato", ref_id=cid, titulo="C2", fixado=1)

        self.db.agenda_devolver("2026-08-11")

        self.assertEqual(self.db.agenda_slot("2026-08-11")["fixado"], 1)


def _segunda_futura(dias=14):
    """Uma segunda-feira a pelo menos ~`dias` dias de hoje. Data COMPUTADA, não
    fixa: uma data cravada apodrece (o piso de `ativar_serie` recusa data
    passada, então um '2026-08-10' fixo passa a falhar sozinho depois daquela
    data)."""
    base = date.today() + timedelta(days=dias)
    return (base - timedelta(days=base.weekday())).isoformat()


class TestCancelarSerie(unittest.TestCase):
    """Task 2 (Cancelar série) — desfaz uma ativação: libera os dias futuros
    ainda não preparados (estudo volta pro estoque, slot vira 'vazio') e volta
    a série pra 'rascunho' com os itens intactos, pronta pra reativar com outra
    data. Não mexe em dia já enviado/de hoje, em dia com rascunho das 18h
    pronto, nem em dia que já é de outro estudo (evita duplicar no estoque)."""

    DIAS_UTEIS = ["segunda", "terca", "quarta", "quinta", "sexta"]

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.snap = _snapshot_env()
        self.db = _reload_db(self.tmp)
        self.hoje = date.today().isoformat()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        _restore_db(self.snap)

    def _serie_ativa(self, n=3, inicio=None):
        """Série ativa com n reservas em n dias úteis seguidos a partir de inicio."""
        import series
        inicio = inicio or _segunda_futura()
        sid = self.db.criar_serie("S")
        for i in range(n):
            rid = self.db.salvar_reserva({"tema": "Obesidade", "titulo_pt": f"R{i}",
                                          "resumo": "r", "tags": ["glp1"]})
            self.db.adicionar_serie_item(sid, "reserva", rid, titulo=f"R{i}", tema="Obesidade")
        ok, msg = series.ativar_serie(sid, inicio, db_mod=self.db, dias_envio=self.DIAS_UTEIS)
        self.assertTrue(ok, f"setup falhou: {msg}")
        return sid

    def test_libera_dias_futuros_e_devolve_estudos(self):
        import series
        sid = self._serie_ativa(n=3)
        dias = [it["data"] for it in self.db.obter_serie(sid)["itens"]]

        ok, msg = series.cancelar_serie(sid, db_mod=self.db, hoje=self.hoje,
                                        preparado_fn=lambda d: False)

        self.assertTrue(ok, msg)
        for d in dias:
            self.assertEqual(self.db.agenda_slot(d)["tipo"], "vazio", f"{d} devia estar livre")
        for it in self.db.obter_serie(sid)["itens"]:
            self.assertEqual(it["data"], "", "item liberado perde a data")
            self.assertEqual(self.db.obter_reserva(it["ref_id"])["status"], "pronto",
                             "estudo tem que voltar pro estoque")
        self.assertEqual(self.db.obter_serie(sid)["serie"]["status"], "rascunho")

    def test_mantem_dia_passado_e_de_hoje(self):
        import series
        sid = self._serie_ativa(n=3)
        dias = sorted(it["data"] for it in self.db.obter_serie(sid)["itens"])

        # hoje = o 2º dia: o 1º é passado, o 2º é hoje, só o 3º é futuro
        ok, msg = series.cancelar_serie(sid, db_mod=self.db, hoje=dias[1],
                                        preparado_fn=lambda d: False)

        self.assertTrue(ok, msg)
        self.assertNotEqual(self.db.agenda_slot(dias[0])["tipo"], "vazio", "passado fica")
        self.assertNotEqual(self.db.agenda_slot(dias[1])["tipo"], "vazio", "hoje fica")
        self.assertEqual(self.db.agenda_slot(dias[2])["tipo"], "vazio", "futuro sai")

    def test_nao_libera_dia_com_rascunho_pronto_e_avisa(self):
        import series
        sid = self._serie_ativa(n=2)
        dias = sorted(it["data"] for it in self.db.obter_serie(sid)["itens"])

        ok, msg = series.cancelar_serie(sid, db_mod=self.db, hoje=self.hoje,
                                        preparado_fn=lambda d: d == dias[0])

        self.assertTrue(ok, msg)
        self.assertNotEqual(self.db.agenda_slot(dias[0])["tipo"], "vazio")
        self.assertEqual(self.db.agenda_slot(dias[1])["tipo"], "vazio")
        self.assertIn("rascunho", msg.lower(), f"o admin tem que ser avisado: {msg}")

    def test_nao_mexe_em_dia_que_ja_e_de_outro_estudo(self):
        import series
        sid = self._serie_ativa(n=1)
        it = self.db.obter_serie(sid)["itens"][0]
        dia = it["data"]
        # alguém trocou o dia (Item 23 / edição manual): o slot não é mais do item
        outra = self.db.salvar_reserva({"tema": "Obesidade", "titulo_pt": "OUTRA", "resumo": "r"})
        self.db.agenda_upsert(dia, tipo="reserva", ref_id=outra, titulo="OUTRA")

        ok, msg = series.cancelar_serie(sid, db_mod=self.db, hoje=self.hoje,
                                        preparado_fn=lambda d: False)

        self.assertTrue(ok, msg)
        self.assertEqual(self.db.agenda_slot(dia)["ref_id"], outra, "não mexe no dia alheio")
        self.assertEqual(self.db.obter_reserva(it["ref_id"])["status"], "agendado",
                         "não devolve às cegas — duplicaria o estudo no estoque")

    def test_serie_presa_ativa_sem_datas_volta_a_rascunho(self):
        """O caso grave: hoje esse estado só sai editando o banco."""
        import series
        sid = self.db.criar_serie("Presa")
        self.db.atualizar_serie(sid, status="ativa")

        ok, msg = series.cancelar_serie(sid, db_mod=self.db, hoje=self.hoje,
                                        preparado_fn=lambda d: False)

        self.assertTrue(ok, msg)
        self.assertEqual(self.db.obter_serie(sid)["serie"]["status"], "rascunho")

    def test_recusa_rascunho_e_concluida(self):
        import series
        sid = self.db.criar_serie("R")
        ok, msg = series.cancelar_serie(sid, db_mod=self.db)
        self.assertFalse(ok)
        self.assertIn("rascunho", msg.lower())

        self.db.atualizar_serie(sid, status="concluida")
        ok2, msg2 = series.cancelar_serie(sid, db_mod=self.db)
        self.assertFalse(ok2)

    def test_falha_por_dia_avisa_e_nao_fica_silenciosa(self):
        import series
        sid = self._serie_ativa(n=2)
        dias = sorted(it["data"] for it in self.db.obter_serie(sid)["itens"])
        real = self.db.agenda_devolver

        def devolver_quebrado(dia):
            if dia == dias[0]:
                raise RuntimeError("boom")
            return real(dia)

        self.db.agenda_devolver = devolver_quebrado
        try:
            ok, msg = series.cancelar_serie(sid, db_mod=self.db, hoje=self.hoje,
                                            preparado_fn=lambda d: False)
        finally:
            self.db.agenda_devolver = real

        self.assertIn(dias[0], msg, f"o dia que falhou tem que aparecer: {msg}")
        self.assertEqual(self.db.agenda_slot(dias[1])["tipo"], "vazio",
                         "uma falha não impede os outros dias")

    def test_cancelar_libera_a_proxima_ativacao(self):
        """Fecha o ciclo: ativei na data errada -> cancelo -> ativo na certa."""
        import series
        sid = self._serie_ativa(n=2)
        ok, _ = series.cancelar_serie(sid, db_mod=self.db, hoje=self.hoje,
                                      preparado_fn=lambda d: False)
        self.assertTrue(ok)

        nova = _segunda_futura(dias=21)
        ok2, msg2 = series.ativar_serie(sid, nova, db_mod=self.db, dias_envio=self.DIAS_UTEIS)

        self.assertTrue(ok2, msg2)
        datas = sorted(it["data"] for it in self.db.obter_serie(sid)["itens"])
        self.assertEqual(datas[0], nova, "reativou na data nova")

    def test_aceita_status_incompleta(self):
        """'incompleta' é um status aceito na whitelist (série que 'reconciliar' fechou
        com item órfão) — alcançável de verdade, não só uma sigla no docstring."""
        import series
        sid = self.db.criar_serie("Incompleta")
        self.db.atualizar_serie(sid, status="incompleta")

        ok, msg = series.cancelar_serie(sid, db_mod=self.db, hoje=self.hoje,
                                        preparado_fn=lambda d: False)

        self.assertTrue(ok, msg)
        self.assertEqual(self.db.obter_serie(sid)["serie"]["status"], "rascunho")

    def test_preparado_fn_que_falha_nao_trava_os_outros_dias(self):
        """`preparado_fn` (por padrão, uma leitura no banco via draft_store.carregar) pode
        levantar com o banco travado — mesma falha que já tratamos pra `agenda_slot`. Uma
        falha nela não pode: (1) travar o loop e deixar os OUTROS dias presos; (2) pular o
        `atualizar_serie` final, deixando a série 'ativa' pra sempre — exatamente o estado
        preso que esta função existe pra consertar, agora alcançável a partir dela mesma."""
        import series
        sid = self._serie_ativa(n=2)
        dias = sorted(it["data"] for it in self.db.obter_serie(sid)["itens"])

        def preparado_quebrado(d):
            if d == dias[0]:
                raise RuntimeError("banco travado")
            return False

        ok, msg = series.cancelar_serie(sid, db_mod=self.db, hoje=self.hoje,
                                        preparado_fn=preparado_quebrado)

        self.assertTrue(ok, msg)
        self.assertIn(dias[0], msg, f"o dia que falhou tem que aparecer: {msg}")
        self.assertEqual(self.db.agenda_slot(dias[1])["tipo"], "vazio",
                         "uma falha no preparado_fn não pode travar os outros dias")
        self.assertEqual(self.db.obter_serie(sid)["serie"]["status"], "rascunho",
                         "a série tem que voltar pra rascunho mesmo com falha parcial")
