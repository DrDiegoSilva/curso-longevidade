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


class TestDbSeries(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # Guarda o ambiente ANTERIOR e restaura no tearDown: dar `pop`/sobrescrever
        # cegamente vaza pra frente (ordem alfabética) e quebra o próximo módulo que
        # espera achar o banco no caminho default — mesma lição do
        # test_renovar_ja_recorrente.py (comentário sobre o test_preparar_pdf).
        self._env0 = {k: os.environ.get(k) for k in ("DSCURSO_ARTIGOS_DB", "DATABASE_URL")}
        self.db = _reload_db(self.tmp)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        for k, v in self._env0.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

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
