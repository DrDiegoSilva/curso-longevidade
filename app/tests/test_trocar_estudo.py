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
        self.assertIn("Trocando", review_web.pagina_trocando("tok-velho", "2026-08-27"))

    def test_item_com_aviso_de_ja_enviado(self):
        import review_web
        alts = [{"tipo": "reserva", "id": "res1", "titulo": "T",
                 "fonte": "NEJM", "tema": "Obesidade", "score": 9,
                 "ja_enviado_em": "2026-07-14"}]
        r = {"artigo": {"titulo": "Atual"}}
        html = review_web.pagina_trocar_estudo(alts, r, "tok")
        self.assertIn("já enviado em 2026-07-14", html)

    def test_item_sem_aviso_quando_nunca_enviado(self):
        import review_web
        alts = [{"tipo": "reserva", "id": "res1", "titulo": "T",
                 "fonte": "NEJM", "tema": "Obesidade", "score": 9,
                 "ja_enviado_em": None}]
        r = {"artigo": {"titulo": "Atual"}}
        html = review_web.pagina_trocar_estudo(alts, r, "tok")
        self.assertNotIn("já enviado", html)

    def test_tema_so_com_disponiveis_nao_mostra_cabecalho_ja_enviados(self):
        import review_web
        alts = [{"tipo": "reserva", "id": "res1", "titulo": "T",
                 "fonte": "NEJM", "tema": "Obesidade", "score": 9,
                 "ja_enviado_em": None}]
        html = review_web.pagina_trocar_estudo(alts, {"artigo": {"titulo": "Atual"}}, "tok")
        self.assertNotIn("Já enviados", html)

    def test_tema_so_com_ja_enviados_mostra_nada_disponivel_e_o_bloco(self):
        import review_web
        alts = [{"tipo": "reserva", "id": "res1", "titulo": "T",
                 "fonte": "NEJM", "tema": "Obesidade", "score": 9,
                 "ja_enviado_em": "2026-07-14"}]
        html = review_web.pagina_trocar_estudo(alts, {"artigo": {"titulo": "Atual"}}, "tok")
        self.assertIn("Nada disponível neste tema.", html)
        self.assertIn("Já enviados", html)
        self.assertIn('value="trocar_confirmar"', html)   # continua escolhível

    def test_tema_misto_mostra_disponiveis_antes_dos_ja_enviados(self):
        import review_web
        alts = [
            {"tipo": "reserva", "id": "disp", "titulo": "Disponível",
             "fonte": "NEJM", "tema": "Obesidade", "score": 9, "ja_enviado_em": None},
            {"tipo": "reserva", "id": "env", "titulo": "Enviado",
             "fonte": "NEJM", "tema": "Obesidade", "score": 5, "ja_enviado_em": "2026-07-14"},
        ]
        html = review_web.pagina_trocar_estudo(alts, {"artigo": {"titulo": "Atual"}}, "tok")
        self.assertLess(html.index("Disponível"), html.index("Já enviados"))
        self.assertLess(html.index("Já enviados"), html.index("Enviado"))


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
             mock.patch.object(daily.draft_store, "salvar") as m_salvar, \
             mock.patch.object(db, "marcar_candidato_pronto") as m_pool, \
             mock.patch.object(db, "marcar_reserva_pronto") as m_res_pool, \
             mock.patch.object(db, "agenda_upsert") as m_up, \
             mock.patch.object(db, "marcar_reserva_agendado") as m_res_ag, \
             mock.patch.object(daily, "_preparar_da_reserva", return_value=novo) as m_res, \
             mock.patch.object(daily, "_preparar_de_candidato") as m_cand, \
             mock.patch.object(daily.deliver, "enviar_curador") as m_cur:
            out = daily.trocar_estudo_amanha("tok", "reserva", "res_escolhida")
        m_res.assert_called_once_with(reserva_id="res_escolhida", data_alvo="2026-07-28")
        m_cand.assert_not_called()
        m_up.assert_called_once_with("2026-07-28", tipo="reserva", ref_id="res_escolhida",
                                     payload=None, tema="Obesidade", titulo="Ret PT", fixado=0)
        m_res_ag.assert_called_once_with("res_escolhida")
        m_pool.assert_called_once_with("c_velho")
        m_res_pool.assert_not_called()
        m_cur.assert_not_called()
        self.assertEqual(out["review_token"], "novo")
        self.assertEqual(novo["token_anterior"], "tok")    # amarra o novo rascunho ao token antigo
        m_salvar.assert_called_once_with(novo)

    def test_reserva_atual_volta_ao_pool_e_grava_slot_do_candidato(self):
        daily = self.daily
        import db
        r = {"reserva_id": "res_velha", "data": "2026-07-28", "artigo": {"tema": "Obesidade"}}
        novo = {"review_token": "n", "data": "2026-07-28",
                "artigo": {"tema": "Perf", "titulo": "Cand"}, "titulo_pt": ""}
        with mock.patch.object(daily.draft_store, "por_token", return_value=r), \
             mock.patch.object(daily.draft_store, "salvar") as m_salvar, \
             mock.patch.object(db, "marcar_candidato_pronto") as m_pool, \
             mock.patch.object(db, "marcar_reserva_pronto") as m_res_pool, \
             mock.patch.object(db, "agenda_upsert") as m_up, \
             mock.patch.object(db, "marcar_candidato_agendado") as m_cand_ag, \
             mock.patch.object(daily, "_preparar_de_candidato", return_value=novo) as m_cand, \
             mock.patch.object(daily, "_preparar_da_reserva"), \
             mock.patch.object(daily.deliver, "enviar_curador"):
            daily.trocar_estudo_amanha("tok", "candidato", "c_escolhido")
        m_cand.assert_called_once_with("c_escolhido", data_alvo="2026-07-28")
        m_up.assert_called_once_with("2026-07-28", tipo="candidato", ref_id="c_escolhido",
                                     payload=None, tema="Perf", titulo="Cand", fixado=0)
        m_cand_ag.assert_called_once_with("c_escolhido")
        m_res_pool.assert_called_once_with("res_velha")
        m_pool.assert_not_called()
        self.assertEqual(novo["token_anterior"], "tok")    # amarra o novo rascunho ao token antigo
        m_salvar.assert_called_once_with(novo)

    def test_preparo_falha_avisa_curador_e_grava_erro_no_rascunho(self):
        daily = self.daily
        import db
        r = {"candidato_id": "c_velho", "data": "2026-07-28", "artigo": {"tema": "Obesidade"}}
        with mock.patch.object(daily.draft_store, "por_token", return_value=r), \
             mock.patch.object(db, "agenda_upsert") as m_up, \
             mock.patch.object(db, "marcar_candidato_pronto") as m_pool, \
             mock.patch.object(daily, "_preparar_da_reserva", side_effect=RuntimeError("boom")), \
             mock.patch.object(daily.draft_store, "falhar_troca") as m_falhar, \
             mock.patch.object(daily.deliver, "enviar_curador") as m_cur:
            out = daily.trocar_estudo_amanha("tok", "reserva", "res_x")
        self.assertIsNone(out)
        m_falhar.assert_called_once_with(
            r, "Não consegui trocar o estudo; o anterior segue valendo.")
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
             mock.patch.object(daily.draft_store, "salvar"), \
             mock.patch.object(db, "agenda_upsert", side_effect=RuntimeError("db lock")), \
             mock.patch.object(db, "marcar_reserva_agendado"), \
             mock.patch.object(db, "marcar_candidato_pronto") as m_pool, \
             mock.patch.object(daily, "_preparar_da_reserva", return_value=novo), \
             mock.patch.object(daily.deliver, "enviar_curador") as m_cur:
            out = daily.trocar_estudo_amanha("tok", "reserva", "res_x")
        m_cur.assert_called_once()                     # avisou que a agenda não atualizou
        m_pool.assert_not_called()                     # bookkeeping abortou junto (não devolveu o antigo)
        self.assertEqual(out["review_token"], "n")     # não crashou; retornou o novo


class TestTrocaPinaADataMesmoDepoisDaMeiaNoite(unittest.TestCase):
    """Achado do Diego (2026-09-28): "troquei o estudo e foi enviado o estudo antigo".

    Causa raiz: `_preparar_de_candidato`/`_preparar_da_reserva` recomputavam "amanhã" na
    hora da troca (`datetime.now() + 1 dia`). Uma troca feita depois da meia-noite
    recomputa um dia inteiro à frente do rascunho que estava sendo substituído -- o novo
    rascunho nasce numa data que `enviar_slot` só vai ler NO DIA SEGUINTE, e o antigo (na
    data certa) é o que sai às 08h. Fim-a-fim com `trocar_estudo_amanha` de verdade
    (sem mockar os `_preparar_*`), só a IA/rede é fake."""

    def setUp(self):
        self._env_antes = {k: os.environ.get(k) for k in ("DSCURSO_ARTIGOS_DB", "DSCURSO_DATA", "DATABASE_URL")}
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ.pop("DATABASE_URL", None)
        import importlib, config as _cfg
        importlib.reload(_cfg)
        import db as _db
        importlib.reload(_db)
        _db.init()
        import daily
        importlib.reload(daily)
        self.daily = daily
        self.db = _db

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        for k, v in self._env_antes.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_candidato_escolhido_fica_na_mesma_data_do_rascunho_trocado(self):
        daily = self.daily
        db = self.db
        # rascunho original preparado ontem às 18h, pra sair HOJE (a "amanhã" de ontem)
        hoje = "2026-09-29"
        r_antigo = daily.draft_store.novo_rascunho(hoje, {"tema": "Obesidade", "titulo": "Velho"},
                                                   "resumo velho", None)
        r_antigo["candidato_id"] = "c_velho"
        daily.draft_store.salvar(r_antigo)
        db.salvar_candidatos([{"tema": "Obesidade", "titulo": "Novo escolhido", "chave": "k_novo",
                               "fonte": "NEJM", "doi": "10.1/novo", "url": "http://novo",
                               "data": "2026-09-01", "score": 9, "abstract": "abstract do novo"}])
        cand_novo = db.listar_candidatos(tipo="varredura")[0]
        with mock.patch.object(daily.content, "gerar_conteudo",
                               return_value={"resumo": "resumo novo", "gancho": "g", "grafico": None,
                                            "titulo_pt": "Novo PT"}), \
             mock.patch.object(daily.pdfmod, "gerar_pdf"), \
             mock.patch.object(daily.deliver, "enviar_curador"), \
             mock.patch.object(daily, "enviar_audio_preview"), \
             mock.patch.object(db, "agenda_upsert"), \
             mock.patch.object(db, "marcar_candidato_agendado"), \
             mock.patch.object(db, "marcar_candidato_pronto"), \
             mock.patch("daily.datetime") as m_dt:
            # a TROCA em si acontece depois da meia-noite: "agora" já é HOJE (0h05),
            # então "amanhã" recomputado do zero seria AMANHÃ -- um dia à frente do
            # rascunho de "hoje" que está sendo substituído.
            from datetime import datetime as _real_dt, timedelta as _td
            m_dt.now.return_value = _real_dt.fromisoformat(hoje + "T00:05:00")
            m_dt.strptime = _real_dt.strptime
            novo = daily.trocar_estudo_amanha(r_antigo["review_token"], "candidato", cand_novo["id"])
        self.assertIsNotNone(novo)
        self.assertEqual(novo["data"], hoje)          # NÃO virou hoje+1
        # e o que `enviar_slot` vai efetivamente carregar pra HOJE já é o escolhido
        self.assertEqual(daily.draft_store.carregar(hoje)["titulo_pt"], "Novo PT")


if __name__ == "__main__":
    unittest.main()
