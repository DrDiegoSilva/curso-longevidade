"""Testes das funções puras de planejamento da agenda. Sem I/O."""
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import agenda_plan as ap


def _cand(tema, tipo="reserva", titulo="t", ref_id="r", payload=None,
          fresco=False, classico=False, score=5):
    return {"tipo": tipo, "tema": tema, "titulo": titulo, "ref_id": ref_id, "payload": payload,
            "fresco": fresco, "classico": classico, "score": score}


def _c(tema, tipo="reserva", fresco=False, classico=False, score=5, ref_id="r"):
    return {"tipo": tipo, "tema": tema, "titulo": "t", "ref_id": ref_id, "payload": None,
            "fresco": fresco, "classico": classico, "score": score}


def _todo_dia(tema):
    """Mapa que prefere o mesmo tema em qualquer dia — preserva a intenção dos testes
    que só queriam dizer 'a preferência do dia é X'."""
    return {d: [tema] for d in ap.DIAS}


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


class TestSemanasDoMes(unittest.TestCase):
    def test_quatro_semanas_cheias(self):
        envio = {"segunda", "terca", "quarta", "quinta", "sexta"}
        # 2026-07-22 é quarta -> segunda da semana = 2026-07-20
        dias = ap.semanas_do_mes(datetime(2026, 7, 22), envio, 4)
        self.assertEqual(len(dias), 20)             # 4 semanas x 5 dias
        self.assertEqual(dias[0], "2026-07-20")     # segunda da semana atual (inclui passados)
        self.assertEqual(dias[-1], "2026-08-14")    # sexta da 4a semana
        for d in dias:                              # nenhum fim de semana
            self.assertLess(datetime.strptime(d, "%Y-%m-%d").weekday(), 5)

    def test_dias_envio_vazio_levanta(self):
        with self.assertRaises(ValueError):
            ap.semanas_do_mes(datetime(2026, 7, 22), set(), 4)


class TestPlanejar(unittest.TestCase):
    def _dias(self, datas):
        return [(d, None, False) for d in datas]

    def test_variedade_nao_repete_tema(self):
        dias = self._dias(["2026-07-27", "2026-07-28", "2026-07-29"])
        cands = [_cand("A"), _cand("A"), _cand("B"), _cand("B")]
        plano = ap.planejar_agenda(dias, cands, {"segunda": ["A"], "terca": ["B"], "quarta": ["A"]}, None)
        temas = [plano[d]["tema"] for d in ["2026-07-27", "2026-07-28", "2026-07-29"]]
        self.assertNotEqual(temas[0], temas[1])
        self.assertNotEqual(temas[1], temas[2])

    def test_respeita_dia_bloqueado(self):
        # dia do meio fixado/pulado (bloqueado) não recebe plano; seu tema alimenta variedade
        dias = [("2026-07-27", None, False), ("2026-07-28", "A", True), ("2026-07-29", None, False)]
        cands = [_cand("A"), _cand("A")]
        plano = ap.planejar_agenda(dias, cands, _todo_dia("A"), None)
        self.assertNotIn("2026-07-28", plano)
        self.assertIn("2026-07-27", plano)
        # 29 vem depois de bloqueado tema A -> variedade tenta != A, mas só há A -> ainda preenche
        self.assertIn("2026-07-29", plano)

    def test_tier_decide_antes_do_score(self):
        # curada (reserva) bate crua (fila) com o resto empatado, mesmo com score menor —
        # o TIER de curadoria vem antes da nota; score só desempata dentro do mesmo tier.
        dias = self._dias(["2026-07-27"])
        cands = [_cand("A", tipo="fila", ref_id=None, payload={"x": 1}, score=9),
                 _cand("A", tipo="reserva", score=3)]
        plano = ap.planejar_agenda(dias, cands, _todo_dia("A"), None)
        self.assertEqual(plano["2026-07-27"]["tipo"], "reserva")

    def test_estoque_magro_deixa_vazio(self):
        dias = self._dias(["2026-07-27", "2026-07-28"])
        cands = [_cand("A")]
        plano = ap.planejar_agenda(dias, cands, _todo_dia("A"), None)
        self.assertEqual(len(plano), 1)

    def test_nao_reusa_candidato(self):
        dias = self._dias(["2026-07-27", "2026-07-28"])
        cands = [_cand("A", ref_id="r1"), _cand("B", ref_id="r2")]
        plano = ap.planejar_agenda(dias, cands, {"segunda": ["A"], "terca": ["B"]}, None)
        self.assertNotEqual(plano["2026-07-27"]["ref_id"], plano["2026-07-28"]["ref_id"])

    def test_variedade_vence_rotacao(self):
        # rotação pede A, mas o dia anterior foi A e há B disponível -> escolhe B
        dias = self._dias(["2026-07-27"])
        cands = [_cand("A"), _cand("B")]
        plano = ap.planejar_agenda(dias, cands, _todo_dia("A"), "A")
        self.assertEqual(plano["2026-07-27"]["tema"], "B")

    def test_rotacao_vence_quando_tipo_e_score_empatam(self):
        # rotação (tema==preferido) vem antes do TIER: decide entre A e B mesmo com tipos diferentes
        dias = self._dias(["2026-07-27"])
        cands = [_cand("A", tipo="fila", ref_id=None, payload={"x": 1}), _cand("B", tipo="reserva")]
        plano = ap.planejar_agenda(dias, cands, _todo_dia("A"), "X")
        self.assertEqual(plano["2026-07-27"]["tema"], "A")


class TestRankPiramide(unittest.TestCase):
    def test_fresco_vence_estoque_mesmo_tema(self):
        dias = [("2026-07-27", None, False)]
        cands = [_c("Obesidade", fresco=False, score=9), _c("Obesidade", fresco=True, score=6, ref_id="f")]
        plano = ap.planejar_agenda(dias, cands, _todo_dia("Obesidade"), None)
        self.assertEqual(plano["2026-07-27"]["ref_id"], "f")     # fresco fura, mesmo com score menor

    def test_classico_e_piso(self):
        dias = [("2026-07-27", None, False)]
        cands = [_c("Obesidade", classico=True, score=9, ref_id="cl"),
                 _c("Obesidade", classico=False, score=3, ref_id="rs")]
        plano = ap.planejar_agenda(dias, cands, _todo_dia("Obesidade"), None)
        self.assertEqual(plano["2026-07-27"]["ref_id"], "rs")    # estoque comum > clássico

    def test_emprestimo_entre_temas(self):
        dias = [("2026-07-27", None, False)]
        cands = [_c("Obesidade", classico=True, score=8, ref_id="ob")]   # só há clássico de Obesidade
        plano = ap.planejar_agenda(dias, cands, _todo_dia("Performance"), None)   # dia pedia Performance
        self.assertEqual(plano["2026-07-27"]["ref_id"], "ob")            # empresta do gigante

    def test_classificar_slot_novos_tipos(self):
        self.assertEqual(ap.classificar_slot({"tipo": "candidato", "ref_id": "x"}), ("candidato", "x"))
        self.assertEqual(ap.classificar_slot({"tipo": "classico", "ref_id": "y"}), ("classico", "y"))

    def test_curada_vence_crua_mesmo_com_nota_menor(self):
        # regressão: reserva (curada, revisada por humano) tem que vencer candidato/fila
        # cru (varredura, sem revisão) do MESMO tema/frescor, mesmo com nota (score) menor.
        # Se _tier voltar a ser só "não-clássico", este teste falha (score decide e o cru vence).
        dias = [("2026-07-27", None, False)]
        cands = [_c("Obesidade", tipo="candidato", fresco=False, score=9, ref_id="crua"),
                 _c("Obesidade", tipo="reserva", fresco=False, score=3, ref_id="curada")]
        plano = ap.planejar_agenda(dias, cands, _todo_dia("Obesidade"), None)
        self.assertEqual(plano["2026-07-27"]["ref_id"], "curada")


class TestClassificarSlot(unittest.TestCase):
    def test_none_e_fallback(self):
        self.assertEqual(ap.classificar_slot(None), ("fallback", None))

    def test_pulado(self):
        self.assertEqual(ap.classificar_slot({"tipo": "pulado"}), ("pulado", None))

    def test_reserva(self):
        self.assertEqual(ap.classificar_slot({"tipo": "reserva", "ref_id": "abc"}), ("reserva", "abc"))

    def test_candidato(self):
        self.assertEqual(ap.classificar_slot({"tipo": "candidato", "ref_id": "xyz"}), ("candidato", "xyz"))

    def test_classico(self):
        self.assertEqual(ap.classificar_slot({"tipo": "classico", "ref_id": "cls"}), ("classico", "cls"))

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


class TestEstadoEstoque(unittest.TestCase):
    UTEIS = ["segunda", "terca", "quarta", "quinta", "sexta"]

    def test_conta_e_projeta_a_data_do_ultimo_envio(self):
        # 2026-07-27 é segunda; 5 envios cobrem até sexta 31/07
        e = ap.estado_estoque(2, 3, 0, datetime(2026, 7, 27), self.UTEIS, minimo=10)
        self.assertEqual(e["envios"], 5)
        self.assertEqual(e["ate"], "2026-07-31")

    def test_soma_as_tres_fontes(self):
        e = ap.estado_estoque(1, 2, 4, datetime(2026, 7, 27), self.UTEIS, minimo=10)
        self.assertEqual(e["envios"], 7)

    def test_estoque_zero_nao_tem_data(self):
        e = ap.estado_estoque(0, 0, 0, datetime(2026, 7, 27), self.UTEIS, minimo=10)
        self.assertIsNone(e["ate"])
        self.assertTrue(e["baixo"])

    def test_limiar_exato_nao_e_baixo(self):
        e = ap.estado_estoque(10, 0, 0, datetime(2026, 7, 27), self.UTEIS, minimo=10)
        self.assertFalse(e["baixo"])

    def test_abaixo_do_limiar_e_baixo(self):
        e = ap.estado_estoque(9, 0, 0, datetime(2026, 7, 27), self.UTEIS, minimo=10)
        self.assertTrue(e["baixo"])

    def test_dias_envio_vazio_degrada_ate_pra_none_sem_levantar(self):
        # dias_envio sem nenhum dia útil válido faria dias_uteis_desde levantar
        # ValueError; estado_estoque é função pura e não pode propagar isso pro
        # chamador — degrada pra "não sei até quando" mantendo envios/baixo corretos.
        e = ap.estado_estoque(3, 2, 1, datetime(2026, 7, 27), set(), minimo=10)
        self.assertEqual(e["envios"], 6)
        self.assertIsNone(e["ate"])
        self.assertTrue(e["baixo"])


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


class TestTemaDoDia(unittest.TestCase):
    MAPA = {
        "segunda": ["Longevidade", "Performance"],
        "terca":   ["Obesidade"],
        "quarta":  ["Hormonal"],
        "quinta":  ["Obesidade"],
        "sexta":   ["Lipedema"],
    }

    def test_dia_de_tema_unico(self):
        # 2026-07-28 é terça, 2026-07-30 é quinta
        self.assertEqual(ap.tema_do_dia("2026-07-28", self.MAPA), "Obesidade")
        self.assertEqual(ap.tema_do_dia("2026-07-30", self.MAPA), "Obesidade")
        self.assertEqual(ap.tema_do_dia("2026-07-29", self.MAPA), "Hormonal")
        self.assertEqual(ap.tema_do_dia("2026-07-31", self.MAPA), "Lipedema")

    def test_alterna_entre_semanas_consecutivas(self):
        # 2026-07-27 e 2026-08-03 são segundas consecutivas
        a = ap.tema_do_dia("2026-07-27", self.MAPA)
        b = ap.tema_do_dia("2026-08-03", self.MAPA)
        self.assertIn(a, ("Longevidade", "Performance"))
        self.assertIn(b, ("Longevidade", "Performance"))
        self.assertNotEqual(a, b)

    def test_alterna_atravessando_a_virada_de_ano(self):
        # 2026-12-28 (semana ISO 53) e 2027-01-04 (semana ISO 1) são segundas
        # consecutivas com a MESMA paridade de semana ISO — a alternância não pode
        # depender de isocalendar()[1].
        a = ap.tema_do_dia("2026-12-28", self.MAPA)
        b = ap.tema_do_dia("2027-01-04", self.MAPA)
        self.assertNotEqual(a, b)

    def test_estavel_dentro_da_mesma_data(self):
        self.assertEqual(ap.tema_do_dia("2026-07-27", self.MAPA),
                         ap.tema_do_dia("2026-07-27", self.MAPA))

    def test_dia_fora_do_mapa_nao_tem_preferencia(self):
        self.assertIsNone(ap.tema_do_dia("2026-08-01", self.MAPA))   # sábado

    def test_mapa_vazio_ou_none(self):
        self.assertIsNone(ap.tema_do_dia("2026-07-28", {}))
        self.assertIsNone(ap.tema_do_dia("2026-07-28", None))

    def test_lista_vazia_no_dia(self):
        self.assertIsNone(ap.tema_do_dia("2026-07-28", {"terca": []}))


class TestPlanejarComMapa(unittest.TestCase):
    MAPA = {
        "segunda": ["Longevidade", "Performance"],
        "terca":   ["Obesidade"],
        "quarta":  ["Hormonal"],
        "quinta":  ["Obesidade"],
        "sexta":   ["Lipedema"],
    }

    def test_terca_recebe_obesidade(self):
        # 2026-07-28 é terça
        dias = [("2026-07-28", None, False)]
        cands = [_cand("Hormonal", ref_id="h"), _cand("Obesidade", ref_id="o")]
        plano = ap.planejar_agenda(dias, cands, self.MAPA, None)
        self.assertEqual(plano["2026-07-28"]["ref_id"], "o")

    def test_quinta_tambem_recebe_obesidade(self):
        # 2026-07-30 é quinta — prova que o mapa vale por dia, não por posição na fila
        dias = [("2026-07-30", None, False)]
        cands = [_cand("Lipedema", ref_id="l"), _cand("Obesidade", ref_id="o")]
        plano = ap.planejar_agenda(dias, cands, self.MAPA, None)
        self.assertEqual(plano["2026-07-30"]["ref_id"], "o")

    def test_semana_inteira_segue_o_mapa(self):
        datas = ["2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31"]
        dias = [(d, None, False) for d in datas]
        cands = ([_cand("Longevidade", ref_id="lo"), _cand("Performance", ref_id="pe")]
                 + [_cand("Obesidade", ref_id=f"ob{i}") for i in range(2)]
                 + [_cand("Hormonal", ref_id="ho"), _cand("Lipedema", ref_id="li")])
        plano = ap.planejar_agenda(dias, cands, self.MAPA, None)
        temas = [plano[d]["tema"] for d in datas]
        self.assertIn(temas[0], ("Longevidade", "Performance"))
        self.assertEqual(temas[1], "Obesidade")
        self.assertEqual(temas[2], "Hormonal")
        self.assertEqual(temas[3], "Obesidade")
        self.assertEqual(temas[4], "Lipedema")

    def test_sem_candidato_do_tema_o_dia_nao_fica_vazio(self):
        # terça pede Obesidade, mas só há Hormonal -> preenche mesmo assim
        dias = [("2026-07-28", None, False)]
        cands = [_cand("Hormonal", ref_id="h")]
        plano = ap.planejar_agenda(dias, cands, self.MAPA, None)
        self.assertEqual(plano["2026-07-28"]["ref_id"], "h")

    def test_variedade_ainda_vence_o_mapa(self):
        # terça pede Obesidade, mas o dia anterior foi Obesidade e há alternativa
        dias = [("2026-07-28", None, False)]
        cands = [_cand("Obesidade", ref_id="o"), _cand("Hormonal", ref_id="h")]
        plano = ap.planejar_agenda(dias, cands, self.MAPA, "Obesidade")
        self.assertEqual(plano["2026-07-28"]["ref_id"], "h")

    def test_mapa_vazio_ainda_preenche(self):
        dias = [("2026-07-28", None, False)]
        cands = [_cand("Hormonal", ref_id="h")]
        plano = ap.planejar_agenda(dias, cands, {}, None)
        self.assertEqual(plano["2026-07-28"]["ref_id"], "h")


if __name__ == "__main__":
    unittest.main()
