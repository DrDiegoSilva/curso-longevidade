"""Testes do CRUD da agenda + status 'agendado' na reserva (SQLite temporário)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAgendaDb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ.pop("DATABASE_URL", None)
        import importlib, db as _db
        importlib.reload(_db)
        self.db = _db
        self.db.init()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _reserva(self, tema="Obesidade", titulo="Estudo X"):
        return self.db.salvar_reserva({"tema": tema, "titulo_pt": titulo, "resumo": "r",
                                       "gancho": "g", "grafico": "", "doi": "", "fonte": "NEJM",
                                       "url": "", "data": "2026-07-20"})

    def test_upsert_e_slot(self):
        self.db.agenda_upsert("2026-07-27", tipo="reserva", ref_id="abc", tema="Obesidade", titulo="T")
        s = self.db.agenda_slot("2026-07-27")
        self.assertEqual(s["tipo"], "reserva")
        self.assertEqual(s["ref_id"], "abc")
        self.assertEqual(s["titulo"], "T")

    def test_upsert_atualiza(self):
        self.db.agenda_upsert("2026-07-27", tipo="vazio")
        self.db.agenda_upsert("2026-07-27", tipo="pulado")
        self.assertEqual(self.db.agenda_slot("2026-07-27")["tipo"], "pulado")

    def test_listar_intervalo(self):
        self.db.agenda_upsert("2026-07-27", tipo="reserva", ref_id="a")
        self.db.agenda_upsert("2026-07-28", tipo="reserva", ref_id="b")
        self.db.agenda_upsert("2026-08-10", tipo="reserva", ref_id="c")
        m = self.db.agenda_listar("2026-07-27", "2026-07-31")
        self.assertEqual(set(m.keys()), {"2026-07-27", "2026-07-28"})

    def test_agendado_some_da_reserva(self):
        rid = self._reserva()
        self.assertEqual(self.db.contar_reserva_pronto(), 1)
        self.db.marcar_reserva_agendado(rid)
        self.assertEqual(self.db.contar_reserva_pronto(), 0)
        self.assertIsNone(self.db.proximo_da_reserva())
        self.db.marcar_reserva_pronto(rid)
        self.assertEqual(self.db.contar_reserva_pronto(), 1)

    def test_devolver_volta_pronto(self):
        rid = self._reserva()
        self.db.marcar_reserva_agendado(rid)
        self.db.agenda_upsert("2026-07-27", tipo="reserva", ref_id=rid, tema="Obesidade", titulo="T")
        self.db.agenda_devolver("2026-07-27")
        self.assertEqual(self.db.agenda_slot("2026-07-27")["tipo"], "vazio")
        self.assertEqual(self.db.contar_reserva_pronto(), 1)

    def test_mover_swap(self):
        self.db.agenda_upsert("2026-07-27", tipo="reserva", ref_id="a", tema="A", titulo="Ta")
        self.db.agenda_upsert("2026-07-28", tipo="reserva", ref_id="b", tema="B", titulo="Tb")
        self.assertTrue(self.db.agenda_mover("2026-07-27", "2026-07-28"))
        self.assertEqual(self.db.agenda_slot("2026-07-27")["ref_id"], "b")
        self.assertEqual(self.db.agenda_slot("2026-07-28")["ref_id"], "a")

    def test_mover_recusa_destino_fixado(self):
        self.db.agenda_upsert("2026-07-27", tipo="reserva", ref_id="a", tema="A")
        self.db.agenda_upsert("2026-07-28", tipo="reserva", ref_id="b", tema="B", fixado=1)
        self.assertFalse(self.db.agenda_mover("2026-07-27", "2026-07-28"))
        self.assertEqual(self.db.agenda_slot("2026-07-28")["ref_id"], "b")

    def test_pular_devolve_e_marca(self):
        rid = self._reserva()
        self.db.marcar_reserva_agendado(rid)
        self.db.agenda_upsert("2026-07-27", tipo="reserva", ref_id=rid, tema="Obesidade")
        self.db.agenda_pular("2026-07-27", True)
        self.assertEqual(self.db.agenda_slot("2026-07-27")["tipo"], "pulado")
        self.assertEqual(self.db.contar_reserva_pronto(), 1)

    def test_pular_preserva_fixado(self):
        rid = self._reserva()
        self.db.marcar_reserva_agendado(rid)
        self.db.agenda_upsert("2026-07-27", tipo="reserva", ref_id=rid, tema="Obesidade", fixado=1)
        self.db.agenda_pular("2026-07-27", True)
        s = self.db.agenda_slot("2026-07-27")
        self.assertEqual(s["tipo"], "pulado")
        self.assertEqual(s["fixado"], 1)
        self.assertEqual(self.db.contar_reserva_pronto(), 1)

    def test_fixar_cria_linha_se_nao_existe(self):
        # fixar um dia ainda sem linha na agenda deve criar a linha e persistir o pino
        self.assertIsNone(self.db.agenda_slot("2026-07-27"))
        self.db.agenda_fixar("2026-07-27", True)
        s = self.db.agenda_slot("2026-07-27")
        self.assertIsNotNone(s)
        self.assertEqual(s["fixado"], 1)
        self.assertEqual(s["tipo"], "vazio")

    def test_digest_do_dia(self):
        self.assertIsNone(self.db.digest_do_dia("2026-07-20"))
        self.db.registrar_digest({"tema": "Obesidade", "titulo": "orig"},
                                 {"titulo_pt": "Retatrutida X", "resumo": "r"}, None, data="2026-07-20")
        dg = self.db.digest_do_dia("2026-07-20")
        self.assertIsNotNone(dg)
        self.assertEqual(dg["tema"], "Obesidade")
        self.assertEqual(dg["titulo_pt"], "Retatrutida X")

    def test_ref_ids_reserva_e_payloads_fila(self):
        self.db.agenda_upsert("2026-07-27", tipo="reserva", ref_id="r1", tema="A")
        self.db.agenda_upsert("2026-07-28", tipo="fila", payload='{"doi":"10.1/x"}', tema="B")
        self.db.agenda_upsert("2026-07-29", tipo="vazio")
        self.assertEqual(self.db.agenda_ref_ids_reserva(), {"r1"})
        self.assertEqual(self.db.agenda_payloads_fila(), ['{"doi":"10.1/x"}'])


if __name__ == "__main__":
    unittest.main()
