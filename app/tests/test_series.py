"""Fase 2 — séries de estudos (item 8)."""
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
