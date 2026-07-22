"""Teste da cola materializar_agenda: estoque temporário (SQLite + queue.json)."""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestMaterializar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ.pop("DATABASE_URL", None)
        import importlib
        import config as _cfg
        importlib.reload(_cfg)
        import db as _db
        importlib.reload(_db)
        import queue_store as _q
        importlib.reload(_q)
        import daily as _d
        importlib.reload(_d)
        self.db, self.q, self.daily = _db, _q, _d
        self.db.init()

    def _reserva(self, tema, titulo):
        return self.db.salvar_reserva({"tema": tema, "titulo_pt": titulo, "resumo": "r",
                                       "gancho": "", "grafico": "", "doi": "", "fonte": "NEJM",
                                       "url": "", "data": "2026-07-20"})

    def test_preenche_e_consome_estoque(self):
        for i in range(6):
            self._reserva("Obesidade", f"Estudo {i}")
        # desliga o reabastecimento de rede no teste
        self.daily.reabastecer = lambda: 0
        n = self.daily.materializar_agenda(dias=5)
        self.assertEqual(n, 5)
        # 5 viraram 'agendado', sobrou 1 pronto
        self.assertEqual(self.db.contar_reserva_pronto(), 1)
        amanha = datetime.now() + timedelta(days=1)
        import agenda_plan as ap
        datas = ap.dias_uteis_desde(amanha, 5, self.daily._dias_envio())
        for d in datas:
            self.assertEqual(self.db.agenda_slot(d)["tipo"], "reserva")

    def test_nao_mexe_em_dia_fixado(self):
        for i in range(5):
            self._reserva("Obesidade", f"E{i}")
        self.daily.reabastecer = lambda: 0
        import agenda_plan as ap
        amanha = datetime.now() + timedelta(days=1)
        d0 = ap.dias_uteis_desde(amanha, 1, self.daily._dias_envio())[0]
        self.db.agenda_upsert(d0, tipo="reserva", ref_id="fixo", tema="Longevidade", titulo="FIXO", fixado=1)
        self.daily.materializar_agenda(dias=5)
        self.assertEqual(self.db.agenda_slot(d0)["ref_id"], "fixo")

    def test_dia_fixado_preserva_e_preenche_resto(self):
        for i in range(6):
            self._reserva("Obesidade", f"E{i}")
        self.daily.reabastecer = lambda: 0
        import agenda_plan as ap
        datas = ap.dias_uteis_desde(datetime.now() + timedelta(days=1), 5, self.daily._dias_envio())
        self.db.agenda_upsert(datas[0], tipo="reserva", ref_id="fixo", tema="Longevidade", titulo="FIXO", fixado=1)
        self.daily.materializar_agenda(dias=5)
        self.assertEqual(self.db.agenda_slot(datas[0])["ref_id"], "fixo")   # preservado
        for d in datas[1:]:                                                 # demais preenchidos
            self.assertEqual(self.db.agenda_slot(d)["tipo"], "reserva")

    def test_nao_double_book_reserva_referenciada(self):
        # item 'pronto' já preso a um slot (consume meio-falho) NÃO é reagendado noutro dia
        rid = self._reserva("Obesidade", "Ref")
        import agenda_plan as ap
        datas = ap.dias_uteis_desde(datetime.now() + timedelta(days=1), 5, self.daily._dias_envio())
        self.db.agenda_upsert(datas[0], tipo="reserva", ref_id=rid, tema="Obesidade", titulo="Ref")
        self.daily.reabastecer = lambda: 0
        self.daily.materializar_agenda(dias=5)
        n_rid = sum(1 for d in datas if (self.db.agenda_slot(d) or {}).get("ref_id") == rid)
        self.assertEqual(n_rid, 1)

    def test_reclama_agendado_orfao(self):
        # item 'agendado' que nenhum slot referencia -> reconciliação devolve e reagenda
        rid = self._reserva("Obesidade", "Orfao")
        self.db.marcar_reserva_agendado(rid)
        self.assertEqual(self.db.contar_reserva_pronto(), 0)
        self.daily.reabastecer = lambda: 0
        self.daily.materializar_agenda(dias=5)
        import agenda_plan as ap
        datas = ap.dias_uteis_desde(datetime.now() + timedelta(days=1), 5, self.daily._dias_envio())
        referenciado = any((self.db.agenda_slot(d) or {}).get("ref_id") == rid for d in datas)
        self.assertTrue(referenciado)

    def test_remover_sem_chave_nao_apaga_tudo(self):
        # remover um artigo sem chave (doi/url/titulo=None) não pode varrer a fila
        self.q._save({"fila": [{"score": 1}, {"score": 2}], "vistos": [], "ultimo_tema": None})
        self.q.remover({"score": 99})   # _chave = None -> no-op
        self.assertEqual(len(self.q.listar()), 2)


if __name__ == "__main__":
    unittest.main()
