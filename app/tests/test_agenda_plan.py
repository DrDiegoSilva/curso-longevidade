"""Testes das funções puras de planejamento da agenda. Sem I/O."""
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import agenda_plan as ap


def _cand(tema, tipo="reserva", titulo="t", ref_id="r", payload=None):
    return {"tipo": tipo, "tema": tema, "titulo": titulo, "ref_id": ref_id, "payload": payload}


class TestDiasUteis(unittest.TestCase):
    def test_pula_fim_de_semana(self):
        envio = {"segunda", "terca", "quarta", "quinta", "sexta"}
        # 2026-07-24 é sexta; próximos 3 úteis = sex, seg, ter
        got = ap.dias_uteis_desde(datetime(2026, 7, 24), 3, envio)
        self.assertEqual(got, ["2026-07-24", "2026-07-27", "2026-07-28"])

    def test_conta_certa(self):
        envio = {"segunda", "terca", "quarta", "quinta", "sexta"}
        self.assertEqual(len(ap.dias_uteis_desde(datetime(2026, 7, 20), 15, envio)), 15)

    def test_dias_envio_vazio_levanta(self):
        # sem dia útil válido -> falha rápido em vez de loop infinito
        with self.assertRaises(ValueError):
            ap.dias_uteis_desde(datetime(2026, 7, 20), 5, set())
        with self.assertRaises(ValueError):
            ap.dias_uteis_desde(datetime(2026, 7, 20), 5, {"feriado"})


class TestPlanejar(unittest.TestCase):
    def _dias(self, datas):
        return [(d, None, False) for d in datas]

    def test_variedade_nao_repete_tema(self):
        dias = self._dias(["2026-07-27", "2026-07-28", "2026-07-29"])
        cands = [_cand("A"), _cand("A"), _cand("B"), _cand("B")]
        plano = ap.planejar_agenda(dias, cands, ["A", "B"], None)
        temas = [plano[d]["tema"] for d in ["2026-07-27", "2026-07-28", "2026-07-29"]]
        self.assertNotEqual(temas[0], temas[1])
        self.assertNotEqual(temas[1], temas[2])

    def test_respeita_dia_bloqueado(self):
        # dia do meio fixado/pulado (bloqueado) não recebe plano; seu tema alimenta variedade
        dias = [("2026-07-27", None, False), ("2026-07-28", "A", True), ("2026-07-29", None, False)]
        cands = [_cand("A"), _cand("A")]
        plano = ap.planejar_agenda(dias, cands, ["A"], None)
        self.assertNotIn("2026-07-28", plano)
        self.assertIn("2026-07-27", plano)
        # 29 vem depois de bloqueado tema A -> variedade tenta != A, mas só há A -> ainda preenche
        self.assertIn("2026-07-29", plano)

    def test_reserva_antes_de_fila(self):
        dias = self._dias(["2026-07-27"])
        cands = [_cand("A", tipo="fila", ref_id=None, payload={"x": 1}), _cand("A", tipo="reserva")]
        plano = ap.planejar_agenda(dias, cands, ["A"], None)
        self.assertEqual(plano["2026-07-27"]["tipo"], "reserva")

    def test_estoque_magro_deixa_vazio(self):
        dias = self._dias(["2026-07-27", "2026-07-28"])
        cands = [_cand("A")]
        plano = ap.planejar_agenda(dias, cands, ["A"], None)
        self.assertEqual(len(plano), 1)

    def test_nao_reusa_candidato(self):
        dias = self._dias(["2026-07-27", "2026-07-28"])
        cands = [_cand("A", ref_id="r1"), _cand("B", ref_id="r2")]
        plano = ap.planejar_agenda(dias, cands, ["A", "B"], None)
        self.assertNotEqual(plano["2026-07-27"]["ref_id"], plano["2026-07-28"]["ref_id"])

    def test_variedade_vence_rotacao(self):
        # rotação pede A, mas o dia anterior foi A e há B disponível -> escolhe B
        dias = self._dias(["2026-07-27"])
        cands = [_cand("A"), _cand("B")]
        plano = ap.planejar_agenda(dias, cands, ["A"], "A")
        self.assertEqual(plano["2026-07-27"]["tema"], "B")

    def test_reserva_vence_rotacao(self):
        # rotação pede A (fila), mas há reserva B -> prefere a reserva
        dias = self._dias(["2026-07-27"])
        cands = [_cand("A", tipo="fila", ref_id=None, payload={"x": 1}), _cand("B", tipo="reserva")]
        plano = ap.planejar_agenda(dias, cands, ["A"], "X")
        self.assertEqual(plano["2026-07-27"]["tipo"], "reserva")


class TestClassificarSlot(unittest.TestCase):
    def test_none_e_fallback(self):
        self.assertEqual(ap.classificar_slot(None), ("fallback", None))

    def test_pulado(self):
        self.assertEqual(ap.classificar_slot({"tipo": "pulado"}), ("pulado", None))

    def test_reserva(self):
        self.assertEqual(ap.classificar_slot({"tipo": "reserva", "ref_id": "abc"}), ("reserva", "abc"))

    def test_fila(self):
        self.assertEqual(ap.classificar_slot({"tipo": "fila", "payload": "{}"}), ("fila", "{}"))

    def test_vazio_e_fallback(self):
        self.assertEqual(ap.classificar_slot({"tipo": "vazio"}), ("fallback", None))


class TestReabastecer(unittest.TestCase):
    def test_abaixo_do_horizonte(self):
        self.assertTrue(ap.precisa_reabastecer(2, 3, 15))

    def test_estoque_suficiente(self):
        self.assertFalse(ap.precisa_reabastecer(10, 10, 15))


class TestAgruparPorSemana(unittest.TestCase):
    def test_normal(self):
        # 27/07 (seg) e 31/07 (sex) = mesma semana; 03/08 (seg) = semana seguinte
        slots = [{"data": "2026-07-27"}, {"data": "2026-07-31"}, {"data": "2026-08-03"}]
        self.assertEqual([len(s) for s in ap.agrupar_por_semana(slots)], [2, 1])

    def test_vazio(self):
        self.assertEqual(ap.agrupar_por_semana([]), [])


class TestPreparoRoteamento(unittest.TestCase):
    """preparar_18h escolhe a fonte certa a partir do slot (com dublês nas partes de I/O)."""
    def setUp(self):
        import os, tempfile
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ.pop("DATABASE_URL", None)
        import importlib
        import config as _cfg; importlib.reload(_cfg)
        import db as _db; importlib.reload(_db)
        import queue_store as _q; importlib.reload(_q)
        import daily as _d; importlib.reload(_d)
        self.db, self.daily = _db, _d
        self.db.init()
        self.chamadas = []
        # dublês: registram a fonte usada, sem tocar rede/IA/PDF. Retornam um dict
        # "truthy" (não None) para imitar o rascunho real que essas funções devolvem
        # em caso de sucesso — preparar_18h usa `if r:` p/ decidir se cai no fallback,
        # e `list.append(...)` sempre retorna None, então sem o `or {...}` o dublê de
        # sucesso pareceria uma falha e disparava um fallback espúrio.
        self.daily.materializar_agenda = lambda dias=15: 0
        self.daily._preparar_da_reserva = lambda reserva_id=None: self.chamadas.append(("reserva", reserva_id)) or {"stub": True}
        self.daily._preparar_de_artigo = lambda art: self.chamadas.append(("artigo", art.get("titulo"))) or {"stub": True}
        self.daily._preparar_fallback = lambda: self.chamadas.append(("fallback", None)) or {"stub": True}

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _amanha_util(self):
        import agenda_plan as ap
        from datetime import datetime, timedelta
        return ap.dias_uteis_desde(datetime.now() + timedelta(days=1), 1, self.daily._dias_envio())[0]

    def test_slot_reserva(self):
        d = self._amanha_util()
        self.db.agenda_upsert(d, tipo="reserva", ref_id="rid-1", tema="Obesidade", titulo="T")
        self.daily.preparar_18h(amanha=datetime.strptime(d, "%Y-%m-%d"))
        self.assertEqual(self.chamadas, [("reserva", "rid-1")])

    def test_slot_pulado_nao_prepara(self):
        d = self._amanha_util()
        self.db.agenda_upsert(d, tipo="pulado")
        self.daily.preparar_18h(amanha=datetime.strptime(d, "%Y-%m-%d"))
        self.assertEqual(self.chamadas, [])

    def test_slot_vazio_cai_no_fallback(self):
        d = self._amanha_util()
        self.daily.preparar_18h(amanha=datetime.strptime(d, "%Y-%m-%d"))  # sem slot
        self.assertEqual(self.chamadas, [("fallback", None)])

    def test_reserva_que_explode_cai_no_fallback(self):
        from datetime import datetime
        d = self._amanha_util()
        self.db.agenda_upsert(d, tipo="reserva", ref_id="rid-x", tema="Obesidade", titulo="T")
        def _boom(reserva_id=None):
            self.chamadas.append(("reserva", reserva_id))
            raise RuntimeError("falha de rede")
        self.daily._preparar_da_reserva = _boom
        self.daily.preparar_18h(amanha=datetime.strptime(d, "%Y-%m-%d"))
        self.assertEqual(self.chamadas, [("reserva", "rid-x"), ("fallback", None)])


if __name__ == "__main__":
    unittest.main()
