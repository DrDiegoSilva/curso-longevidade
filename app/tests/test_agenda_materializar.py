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

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _reserva(self, tema, titulo):
        return self.db.salvar_reserva({"tema": tema, "titulo_pt": titulo, "resumo": "r",
                                       "gancho": "", "grafico": "", "doi": "", "fonte": "NEJM",
                                       "url": "", "data": "2026-07-20"})

    def test_preenche_e_consome_estoque(self):
        for i in range(6):
            self._reserva("Obesidade", f"Estudo {i}")
        # desliga o reabastecimento de rede no teste
        self.daily.reabastecer = lambda: 0
        import agenda_plan as ap
        datas = ap.dias_uteis_desde(datetime.now() + timedelta(days=1), 5, self.daily._dias_envio())
        n = self.daily.materializar_agenda(datas=datas)
        self.assertEqual(n, 5)
        # 5 viraram 'agendado', sobrou 1 pronto
        self.assertEqual(self.db.contar_reserva_pronto(), 1)
        for d in datas:
            self.assertEqual(self.db.agenda_slot(d)["tipo"], "reserva")

    def test_nao_mexe_em_dia_fixado(self):
        for i in range(5):
            self._reserva("Obesidade", f"E{i}")
        self.daily.reabastecer = lambda: 0
        import agenda_plan as ap
        datas = ap.dias_uteis_desde(datetime.now() + timedelta(days=1), 5, self.daily._dias_envio())
        d0 = datas[0]
        self.db.agenda_upsert(d0, tipo="reserva", ref_id="fixo", tema="Longevidade", titulo="FIXO", fixado=1)
        self.daily.materializar_agenda(datas=datas)
        self.assertEqual(self.db.agenda_slot(d0)["ref_id"], "fixo")

    def test_dia_fixado_preserva_e_preenche_resto(self):
        for i in range(6):
            self._reserva("Obesidade", f"E{i}")
        self.daily.reabastecer = lambda: 0
        import agenda_plan as ap
        datas = ap.dias_uteis_desde(datetime.now() + timedelta(days=1), 5, self.daily._dias_envio())
        self.db.agenda_upsert(datas[0], tipo="reserva", ref_id="fixo", tema="Longevidade", titulo="FIXO", fixado=1)
        self.daily.materializar_agenda(datas=datas)
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
        self.daily.materializar_agenda(datas=datas)
        n_rid = sum(1 for d in datas if (self.db.agenda_slot(d) or {}).get("ref_id") == rid)
        self.assertEqual(n_rid, 1)

    def test_reclama_agendado_orfao(self):
        # item 'agendado' que nenhum slot referencia -> reconciliação devolve e reagenda
        rid = self._reserva("Obesidade", "Orfao")
        self.db.marcar_reserva_agendado(rid)
        self.assertEqual(self.db.contar_reserva_pronto(), 0)
        self.daily.reabastecer = lambda: 0
        import agenda_plan as ap
        datas = ap.dias_uteis_desde(datetime.now() + timedelta(days=1), 5, self.daily._dias_envio())
        self.daily.materializar_agenda(datas=datas)
        referenciado = any((self.db.agenda_slot(d) or {}).get("ref_id") == rid for d in datas)
        self.assertTrue(referenciado)

    def test_remover_sem_chave_nao_apaga_tudo(self):
        # remover um artigo sem chave (doi/url/titulo=None) não pode varrer a fila
        self.q._save({"fila": [{"score": 1}, {"score": 2}], "vistos": [], "ultimo_tema": None})
        self.q.remover({"score": 99})   # _chave = None -> no-op
        self.assertEqual(len(self.q.listar()), 2)


class TestPoolPiramide(unittest.TestCase):
    def setUp(self):   # padrão do repo (igual TestMaterializar neste arquivo)
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
        _db.init()
        self.daily.reabastecer = lambda: 0   # desliga rede (Europe PMC/OpenAlex/Anthropic) no teste

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_candidato_fresco_entra_como_candidato(self):
        self.db.salvar_candidatos([{"tema": "Obesidade", "titulo": "Fresco", "chave": "k1", "score": 6,
                                    "tipo": "varredura", "data": self.daily._hoje_iso()}])
        self.daily.materializar_agenda(datas=["2026-07-27"])   # segunda futura
        slot = self.db.agenda_slot("2026-07-27")
        self.assertEqual(slot["tipo"], "candidato")

    def test_classico_preenche_quando_nao_ha_fresco_nem_reserva(self):
        self.db.salvar_classico({"tema": "Obesidade", "titulo_pt": "STEP", "resumo": "r",
                                 "data": "2021-01-01", "citacoes": 4000})
        self.daily.materializar_agenda(datas=["2026-07-27"])
        self.assertEqual(self.db.agenda_slot("2026-07-27")["tipo"], "classico")

    def test_remateralizar_nao_double_booka_nem_sobrescreve_candidato(self):
        # Condição de falha parcial (consume meio-falho): um slot já aponta pro
        # candidato, mas o candidato ainda está 'novo' (marcar_candidato_agendado
        # nunca rodou) -- então ele continua aparecendo no pool. Um 2o dia tem
        # outra fonte no pool (reserva do MESMO tema, não-fresca) pra garantir que
        # o candidato "vazado" seria o preferido do ranking se não fosse excluído
        # (fresh-first desempata a favor dele quando tema/variedade empatam).
        self.db.salvar_candidatos([{"tema": "Obesidade", "titulo": "Fresco", "chave": "k1",
                                    "score": 6, "tipo": "varredura",
                                    "data": self.daily._hoje_iso()}])
        cand_id = self.db.listar_candidatos(tipo="varredura")[0]["id"]

        dateA, dateB = "2026-07-27", "2026-07-28"
        # pré-planta o slot de dateA apontando pro candidato SEM marcá-lo agendado
        # (é exatamente a condição de falha parcial que os guards defendem).
        self.db.agenda_upsert(dateA, tipo="candidato", ref_id=cand_id,
                               tema="Obesidade", titulo="Fresco")
        self.assertEqual(self.db.listar_candidatos(status="novo")[0]["id"], cand_id)

        # outra fonte no pool p/ dateB: reserva do MESMO tema, mas antiga (não-fresca)
        # -- se o candidato "vazado" não for excluído do pool (Fix 1), o fresh-first
        # o escolhe sobre essa reserva quando tema/variedade empatam.
        rid_reserva = self.db.salvar_reserva({"tema": "Obesidade", "titulo_pt": "Reserva B",
                                              "resumo": "r", "gancho": "", "grafico": "",
                                              "doi": "", "fonte": "NEJM", "url": "",
                                              "data": "2020-01-01"})

        self.daily.materializar_agenda(datas=[dateA, dateB])

        slot_depois = self.db.agenda_slot(dateA)
        self.assertEqual(slot_depois["tipo"], "candidato")
        self.assertEqual(slot_depois["ref_id"], cand_id)   # slot de dateA preservado, não sobrescrito

        # não existe um segundo slot referenciando o mesmo candidato (double-book)
        datas = [dateA, dateB]
        n_ref = sum(1 for d in datas if (self.db.agenda_slot(d) or {}).get("ref_id") == cand_id)
        self.assertEqual(n_ref, 1)

    def test_reserva_bate_candidato_mesmo_tema_por_nota_real(self):
        # regressão: reserva (curada, nota=9) vence candidato (cru, nota=5) do MESMO
        # tema/dia — TIER decide, e a nota usada no pool vem do campo 'score' real da
        # reserva (não mais 'prioridade', que soterrava a curadoria).
        self.db.salvar_candidatos([{"tema": "Obesidade", "titulo": "Cru", "chave": "k1",
                                    "score": 5, "tipo": "varredura", "data": "2020-01-01"}])
        self.db.salvar_reserva({"tema": "Obesidade", "titulo_pt": "Curada", "resumo": "r",
                                "gancho": "", "grafico": "", "doi": "", "fonte": "NEJM",
                                "url": "", "data": "2020-01-01", "score": 9})
        self.daily.materializar_agenda(datas=["2026-07-27"])
        slot = self.db.agenda_slot("2026-07-27")
        self.assertEqual(slot["tipo"], "reserva")
        self.assertEqual(slot["titulo"], "Curada")

    def test_estoque_cheio_de_candidatos_nao_chama_reabastecer(self):
        # o reabastecer (rede) só deve rodar se o estoque TOTAL (reserva+candidato+
        # clássico) não cobre o horizonte — não só reserva+fila.
        chamadas = []
        self.daily.reabastecer = lambda: chamadas.append(1)
        for i in range(10):
            self.db.salvar_candidatos([{"tema": "Obesidade", "titulo": f"C{i}", "chave": f"k{i}",
                                        "score": 5, "tipo": "varredura", "data": "2020-01-01"}])
        import agenda_plan as ap
        datas = ap.dias_uteis_desde(datetime.now() + timedelta(days=1), 5, self.daily._dias_envio())
        self.daily.materializar_agenda(datas=datas)
        self.assertEqual(chamadas, [])   # estoque de candidatos (10) cobre o horizonte (5)


if __name__ == "__main__":
    unittest.main()
