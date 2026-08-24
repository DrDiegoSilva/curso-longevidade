"""Item 23 — trocar o estudo de amanhã na tela de aprovação."""
import importlib
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DSCURSO_DATA", tempfile.mkdtemp())


class TestMarcarJaEnviados(unittest.TestCase):
    def setUp(self):
        import daily
        importlib.reload(daily)
        self.daily = daily

    def test_casa_por_doi(self):
        import db
        digests = [{"data": "2026-07-14", "doi": "10.1/X", "titulo_original": "", "titulo_pt": ""}]
        with mock.patch.object(db, "listar_digests", return_value=digests):
            alts = self.daily.marcar_ja_enviados([{"titulo": "Y", "doi": "10.1/x"}])
        self.assertEqual(alts[0]["ja_enviado_em"], "2026-07-14")

    def test_casa_por_titulo_original_quando_falta_doi(self):
        import db
        digests = [{"data": "2026-07-14", "doi": "", "titulo_original": "Effects of X", "titulo_pt": ""}]
        with mock.patch.object(db, "listar_digests", return_value=digests):
            alts = self.daily.marcar_ja_enviados([{"titulo": "effects of x", "doi": ""}])
        self.assertEqual(alts[0]["ja_enviado_em"], "2026-07-14")

    def test_casa_por_titulo_pt_quando_falta_doi(self):
        import db
        digests = [{"data": "2026-07-14", "doi": "", "titulo_original": "", "titulo_pt": "Efeitos de X"}]
        with mock.patch.object(db, "listar_digests", return_value=digests):
            alts = self.daily.marcar_ja_enviados([{"titulo": "Efeitos de X", "doi": ""}])
        self.assertEqual(alts[0]["ja_enviado_em"], "2026-07-14")

    def test_guarda_a_data_mais_antiga(self):
        import db
        digests = [{"data": "2026-08-01", "doi": "10.1/x", "titulo_original": "", "titulo_pt": ""},
                   {"data": "2026-06-01", "doi": "10.1/x", "titulo_original": "", "titulo_pt": ""}]
        with mock.patch.object(db, "listar_digests", return_value=digests):
            alts = self.daily.marcar_ja_enviados([{"titulo": "Y", "doi": "10.1/X"}])
        self.assertEqual(alts[0]["ja_enviado_em"], "2026-06-01")

    def test_sem_casamento_fica_none(self):
        import db
        with mock.patch.object(db, "listar_digests", return_value=[]):
            alts = self.daily.marcar_ja_enviados([{"titulo": "Nunca saiu", "doi": ""}])
        self.assertIsNone(alts[0]["ja_enviado_em"])

    def test_doi_e_titulo_vazios_nao_casam_a_toa(self):
        import db
        digests = [{"data": "2026-07-14", "doi": "", "titulo_original": "", "titulo_pt": ""}]
        with mock.patch.object(db, "listar_digests", return_value=digests):
            alts = self.daily.marcar_ja_enviados([{"titulo": "", "doi": ""}])
        self.assertIsNone(alts[0]["ja_enviado_em"])


class TestMontarAlternativas(unittest.TestCase):
    def setUp(self):
        import daily
        importlib.reload(daily)
        self.daily = daily

    def _db(self, reserva, candidatos):
        import db
        return (mock.patch.object(db, "listar_reserva", return_value=reserva),
                mock.patch.object(db, "listar_candidatos", return_value=candidatos),
                mock.patch.object(db, "listar_digests", return_value=[]))

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
        p1, p2, p3 = self._db(reserva, candidatos)
        with p1, p2, p3:
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
        p1, p2, p3 = self._db([], candidatos)
        with p1, p2, p3:
            alts = daily.montar_alternativas(r)
        self.assertEqual([a["id"] for a in alts], ["c_ok"])
        self.assertEqual(alts[0], {"tipo": "candidato", "id": "c_ok",
                                   "titulo": "Outro", "fonte": "Sports Med",
                                   "tema": "Performance", "score": 7,
                                   "doi": "", "ja_enviado_em": None})

    def test_alternativa_valida(self):
        daily = self.daily
        r = {"reserva_id": None, "candidato_id": None, "artigo": {"tema": "Obesidade"}}
        p1, p2, p3 = self._db([{"id": "res1", "titulo_pt": "R", "fonte": "", "tema": "Obesidade", "prioridade": 0, "score": 1}], [])
        with p1, p2, p3:
            self.assertTrue(daily.alternativa_valida(r, "reserva", "res1"))
            self.assertFalse(daily.alternativa_valida(r, "candidato", "res1"))
            self.assertFalse(daily.alternativa_valida(r, "reserva", "nope"))

    def test_doi_passa_para_a_alternativa(self):
        daily = self.daily
        r = {"reserva_id": None, "candidato_id": None, "artigo": {"tema": "Obesidade"}}
        reserva = [{"id": "res1", "titulo_pt": "R", "fonte": "X", "tema": "Obesidade",
                    "prioridade": 0, "score": 1, "doi": "10.1/res"}]
        candidatos = [{"id": "c1", "titulo": "C", "fonte": "Y", "tema": "Obesidade",
                       "score": 2, "doi": "10.1/cand"}]
        p1, p2, p3 = self._db(reserva, candidatos)
        with p1, p2, p3:
            alts = daily.montar_alternativas(r)
        dois = {a["id"]: a["doi"] for a in alts}
        self.assertEqual(dois, {"res1": "10.1/res", "c1": "10.1/cand"})


class TestReviewWebTrocar(unittest.TestCase):
    def test_pagina_revisao_tem_botao_trocar(self):
        import review_web
        html = review_web.pagina_revisao({"artigo": {"titulo": "T"}, "data": "2026-07-28",
                                          "resumo": "x", "review_token": "tok"})
        self.assertIn('value="trocar"', html)
        self.assertIn("🔁", html)

    def test_pagina_trocar_lista_e_escapa(self):
        import review_web
        alts = [{"tipo": "reserva", "id": "res1", "titulo": "T <b>x</b>",
                 "fonte": "NEJM", "tema": "Obesidade", "score": 9}]
        r = {"artigo": {"titulo": "Atual"}}
        html = review_web.pagina_trocar_estudo(alts, r, "tok")
        self.assertIn("T &lt;b&gt;x&lt;/b&gt;", html)          # título escapado
        self.assertIn('value="trocar_confirmar"', html)
        self.assertIn('name="tipo" value="reserva"', html)
        self.assertIn('name="id" value="res1"', html)
        self.assertIn("/revisar/tok", html)                    # form + voltar

    def test_pagina_trocar_vazio(self):
        import review_web
        html = review_web.pagina_trocar_estudo([], {"artigo": {"titulo": "Atual"}}, "tok")
        self.assertIn("Sem outros estudos", html)

    def test_pagina_trocando(self):
        import review_web
        self.assertIn("Trocando", review_web.pagina_trocando())


class TestTrocarEstudoAmanha(unittest.TestCase):
    def setUp(self):
        import daily
        importlib.reload(daily)
        self.daily = daily

    def test_rascunho_nao_encontrado_avisa(self):
        daily = self.daily
        with mock.patch.object(daily.draft_store, "por_token", return_value=None), \
             mock.patch.object(daily.deliver, "enviar_curador") as m_cur:
            out = daily.trocar_estudo_amanha("tok", "reserva", "x")
        self.assertIsNone(out)
        m_cur.assert_called_once()

    def test_candidato_atual_volta_ao_pool_grava_slot_e_prepara_escolhido(self):
        daily = self.daily
        import db
        r = {"candidato_id": "c_velho", "data": "2026-07-28", "artigo": {"tema": "Perf"}}
        novo = {"review_token": "novo", "data": "2026-07-28",
                "artigo": {"tema": "Obesidade", "titulo": "Ret"}, "titulo_pt": "Ret PT"}
        with mock.patch.object(daily.draft_store, "por_token", return_value=r), \
             mock.patch.object(db, "marcar_candidato_pronto") as m_pool, \
             mock.patch.object(db, "marcar_reserva_pronto") as m_res_pool, \
             mock.patch.object(db, "agenda_upsert") as m_up, \
             mock.patch.object(db, "marcar_reserva_agendado") as m_res_ag, \
             mock.patch.object(daily, "_preparar_da_reserva", return_value=novo) as m_res, \
             mock.patch.object(daily, "_preparar_de_candidato") as m_cand, \
             mock.patch.object(daily.deliver, "enviar_curador") as m_cur:
            out = daily.trocar_estudo_amanha("tok", "reserva", "res_escolhida")
        m_res.assert_called_once_with(reserva_id="res_escolhida")
        m_cand.assert_not_called()
        m_up.assert_called_once_with("2026-07-28", tipo="reserva", ref_id="res_escolhida",
                                     payload=None, tema="Obesidade", titulo="Ret PT", fixado=0)
        m_res_ag.assert_called_once_with("res_escolhida")
        m_pool.assert_called_once_with("c_velho")
        m_res_pool.assert_not_called()
        m_cur.assert_not_called()
        self.assertEqual(out["review_token"], "novo")

    def test_reserva_atual_volta_ao_pool_e_grava_slot_do_candidato(self):
        daily = self.daily
        import db
        r = {"reserva_id": "res_velha", "data": "2026-07-28", "artigo": {"tema": "Obesidade"}}
        novo = {"review_token": "n", "data": "2026-07-28",
                "artigo": {"tema": "Perf", "titulo": "Cand"}, "titulo_pt": ""}
        with mock.patch.object(daily.draft_store, "por_token", return_value=r), \
             mock.patch.object(db, "marcar_candidato_pronto") as m_pool, \
             mock.patch.object(db, "marcar_reserva_pronto") as m_res_pool, \
             mock.patch.object(db, "agenda_upsert") as m_up, \
             mock.patch.object(db, "marcar_candidato_agendado") as m_cand_ag, \
             mock.patch.object(daily, "_preparar_de_candidato", return_value=novo) as m_cand, \
             mock.patch.object(daily, "_preparar_da_reserva"), \
             mock.patch.object(daily.deliver, "enviar_curador"):
            daily.trocar_estudo_amanha("tok", "candidato", "c_escolhido")
        m_cand.assert_called_once_with("c_escolhido")
        m_up.assert_called_once_with("2026-07-28", tipo="candidato", ref_id="c_escolhido",
                                     payload=None, tema="Perf", titulo="Cand", fixado=0)
        m_cand_ag.assert_called_once_with("c_escolhido")
        m_res_pool.assert_called_once_with("res_velha")
        m_pool.assert_not_called()

    def test_preparo_falha_avisa_curador_sem_tocar_agenda(self):
        daily = self.daily
        import db
        r = {"candidato_id": "c_velho", "data": "2026-07-28", "artigo": {"tema": "Obesidade"}}
        with mock.patch.object(daily.draft_store, "por_token", return_value=r), \
             mock.patch.object(db, "agenda_upsert") as m_up, \
             mock.patch.object(db, "marcar_candidato_pronto") as m_pool, \
             mock.patch.object(daily, "_preparar_da_reserva", side_effect=RuntimeError("boom")), \
             mock.patch.object(daily.deliver, "enviar_curador") as m_cur:
            out = daily.trocar_estudo_amanha("tok", "reserva", "res_x")
        self.assertIsNone(out)
        m_cur.assert_called_once()
        m_up.assert_not_called()
        m_pool.assert_not_called()

    def test_agenda_falha_avisa_mas_nao_crasha(self):
        daily = self.daily
        import db
        r = {"candidato_id": "c_velho", "data": "2026-07-28", "artigo": {"tema": "Obesidade"}}
        novo = {"review_token": "n", "data": "2026-07-28",
                "artigo": {"tema": "Obesidade", "titulo": "T"}, "titulo_pt": "T"}
        with mock.patch.object(daily.draft_store, "por_token", return_value=r), \
             mock.patch.object(db, "agenda_upsert", side_effect=RuntimeError("db lock")), \
             mock.patch.object(db, "marcar_reserva_agendado"), \
             mock.patch.object(db, "marcar_candidato_pronto") as m_pool, \
             mock.patch.object(daily, "_preparar_da_reserva", return_value=novo), \
             mock.patch.object(daily.deliver, "enviar_curador") as m_cur:
            out = daily.trocar_estudo_amanha("tok", "reserva", "res_x")
        m_cur.assert_called_once()                     # avisou que a agenda não atualizou
        m_pool.assert_not_called()                     # bookkeeping abortou junto (não devolveu o antigo)
        self.assertEqual(out["review_token"], "n")     # não crashou; retornou o novo


if __name__ == "__main__":
    unittest.main()
