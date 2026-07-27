"""Item 23 — trocar o estudo de amanhã na tela de aprovação."""
import importlib
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DSCURSO_DATA", tempfile.mkdtemp())


class TestMontarAlternativas(unittest.TestCase):
    def setUp(self):
        import daily
        importlib.reload(daily)
        self.daily = daily

    def _db(self, reserva, candidatos):
        import db
        return (mock.patch.object(db, "listar_reserva", return_value=reserva),
                mock.patch.object(db, "listar_candidatos", return_value=candidatos))

    def test_reserva_primeiro_e_exclui_atual_e_ordena(self):
        daily = self.daily
        r = {"reserva_id": "res_atual", "candidato_id": None,
             "artigo": {"tema": "Obesidade"}}
        reserva = [
            {"id": "res_atual", "titulo_pt": "Atual", "fonte": "X", "tema": "Obesidade", "prioridade": 0, "score": 9},
            {"id": "res_up", "titulo_pt": "Meu upload", "fonte": "NEJM", "tema": "Obesidade", "prioridade": 1, "score": 2},
            {"id": "res_b", "titulo_pt": "Reserva B", "fonte": "Lancet", "tema": "Hormonal", "prioridade": 0, "score": 5},
        ]
        candidatos = [
            {"id": "c_horm", "titulo": "Cand Hormonal", "fonte": "JCEM", "tema": "Hormonal", "score": 8},
            {"id": "c_obe", "titulo": "Cand Obesidade", "fonte": "Obesity", "tema": "Obesidade", "score": 3},
        ]
        p1, p2 = self._db(reserva, candidatos)
        with p1, p2:
            alts = daily.montar_alternativas(r)
        ids = [(a["tipo"], a["id"]) for a in alts]
        # atual excluído; uploads/reserva no topo (prioridade=1 primeiro, depois score);
        # candidatos depois com tema de amanhã (Obesidade) na frente do Hormonal
        self.assertEqual(ids, [
            ("reserva", "res_up"), ("reserva", "res_b"),
            ("candidato", "c_obe"), ("candidato", "c_horm"),
        ])
        self.assertEqual(alts[0]["titulo"], "Meu upload")

    def test_exclui_candidato_atual_e_normaliza(self):
        daily = self.daily
        r = {"reserva_id": None, "candidato_id": "c_atual", "artigo": {"tema": "Performance"}}
        candidatos = [
            {"id": "c_atual", "titulo": "Atual", "fonte": "X", "tema": "Performance", "score": 5},
            {"id": "c_ok", "titulo": "Outro", "fonte": "Sports Med", "tema": "Performance", "score": 7},
        ]
        p1, p2 = self._db([], candidatos)
        with p1, p2:
            alts = daily.montar_alternativas(r)
        self.assertEqual([a["id"] for a in alts], ["c_ok"])
        self.assertEqual(alts[0], {"tipo": "candidato", "id": "c_ok",
                                   "titulo": "Outro", "fonte": "Sports Med",
                                   "tema": "Performance", "score": 7})

    def test_alternativa_valida(self):
        daily = self.daily
        r = {"reserva_id": None, "candidato_id": None, "artigo": {"tema": "Obesidade"}}
        p1, p2 = self._db([{"id": "res1", "titulo_pt": "R", "fonte": "", "tema": "Obesidade", "prioridade": 0, "score": 1}], [])
        with p1, p2:
            self.assertTrue(daily.alternativa_valida(r, "reserva", "res1"))
            self.assertFalse(daily.alternativa_valida(r, "candidato", "res1"))
            self.assertFalse(daily.alternativa_valida(r, "reserva", "nope"))


if __name__ == "__main__":
    unittest.main()
