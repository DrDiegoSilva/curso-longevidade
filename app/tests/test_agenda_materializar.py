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


if __name__ == "__main__":
    unittest.main()
