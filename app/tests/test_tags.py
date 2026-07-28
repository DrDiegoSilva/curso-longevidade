"""Fase 1 — tags de estudos."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestTriageTags(unittest.TestCase):
    def test_norm_tags(self):
        import triage
        self.assertEqual(triage._norm_tags(["Retatrutida", "GLP1", "retatrutida", "  x "]),
                         ["retatrutida", "glp1", "x"])
        self.assertEqual(triage._norm_tags(None), [])
        self.assertEqual(triage._norm_tags("retatrutida"), [])
        self.assertEqual(triage._norm_tags([1, "", "  "]), [])

    def test_parse_extrai_tags(self):
        import triage
        txt = ('[{"i":0,"classe":"ENTRA","score":8,"tags":["Retatrutida","GLP1"]},'
               '{"i":1,"classe":"LIXO","score":0}]')
        out = triage._parse(txt, [{"titulo": "A"}, {"titulo": "B"}], "Obesidade")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["tags"], ["retatrutida", "glp1"])

    def test_parse_sem_tags(self):
        import triage
        out = triage._parse('[{"i":0,"classe":"ENTRA","score":8}]', [{"titulo": "A"}], "T")
        self.assertEqual(out[0]["tags"], [])

    def test_triar_devolve_tags(self):
        import triage
        llm = lambda p: '[{"i":0,"classe":"ENTRA","score":9,"tags":["Semaglutida"]}]'
        out = triage.triar([{"titulo": "X", "resumo": "y"}], "Obesidade", llm=llm)
        self.assertEqual(out[0]["tags"], ["semaglutida"])

    def test_taggear_so_tags(self):
        import triage
        llm = lambda p: '[{"i":0,"tags":["Retatrutida"]},{"i":1,"tags":["menopausa","trh"]}]'
        out = triage.taggear([{"titulo": "A"}, {"titulo": "B"}], llm=llm)
        self.assertEqual(out, {0: ["retatrutida"], 1: ["menopausa", "trh"]})

    def test_taggear_vazio(self):
        import triage
        self.assertEqual(triage.taggear([]), {})


class TestDbTags(unittest.TestCase):
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

    def test_reserva_salva_e_le_tags(self):
        import json
        rid = self.db.salvar_reserva({"tema": "Obesidade", "titulo_pt": "Reta X",
                                      "resumo": "r", "tags": ["retatrutida", "glp1"]})
        self.assertEqual(json.loads(self.db.obter_reserva(rid)["tags"]), ["retatrutida", "glp1"])

    def test_default_vazio(self):
        import json
        rid = self.db.salvar_reserva({"tema": "T", "titulo_pt": "Sem tags"})
        self.assertEqual(json.loads(self.db.obter_reserva(rid)["tags"]), [])

    def test_buscar_por_tag_cruza_e_substring(self):
        self.db.salvar_reserva({"tema": "Obesidade", "titulo_pt": "R1", "tags": ["retatrutida"]})
        self.db.salvar_classico({"tema": "Obesidade", "titulo_pt": "C1", "tags": ["retatrutida", "glp1"]})
        self.db.salvar_candidatos([{"tema": "Obesidade", "titulo": "K1", "chave": "k1",
                                    "tags": ["semaglutida"]}])
        achados = self.db.buscar_por_tag("RETA")             # substring + case-insensitive
        self.assertEqual(sorted(a["titulo"] for a in achados), ["C1", "R1"])
        self.assertEqual(self.db.buscar_por_tag("semaglutida")[0]["tipo"], "candidato")
        self.assertEqual(self.db.buscar_por_tag(""), [])     # vazio -> []

    def test_atualizar_tags(self):
        import json
        rid = self.db.salvar_reserva({"tema": "T", "titulo_pt": "X"})
        self.db.atualizar_tags("reserva", rid, ["nova"])
        self.assertEqual(json.loads(self.db.obter_reserva(rid)["tags"]), ["nova"])


class TestCuradoriaTags(unittest.TestCase):
    def test_gerar_selecionados_carrega_tags(self):
        import curadoria
        from unittest import mock
        cand = {"id": "c1", "tema": "Obesidade", "titulo": "T", "tipo": "varredura",
                "tags": '["retatrutida","glp1"]'}
        salvos = {}
        fake_db = mock.Mock()
        fake_db.listar_candidatos.return_value = [cand]
        fake_db.salvar_reserva.side_effect = lambda reg: salvos.update(reg) or "rid"
        gerar = lambda c: {"titulo_pt": "Tpt", "resumo": "r", "gancho": "", "grafico": None}
        curadoria.gerar_selecionados(db_mod=fake_db, gerar_resumo_fn=gerar)
        self.assertEqual(salvos.get("tags"), ["retatrutida", "glp1"])   # string do banco -> lista

    def test_backfill_so_sem_tags_e_idempotente(self):
        import curadoria
        from unittest import mock
        fake_db = mock.Mock()
        fake_db.listar_candidatos.return_value = [
            {"id": "a", "tema": "Obesidade", "titulo": "A", "abstract": "x", "tags": "[]"},
            {"id": "b", "tema": "Obesidade", "titulo": "B", "abstract": "y", "tags": '["ja"]'}]
        fake_db.listar_reserva.return_value = []
        fake_db.listar_classicos.return_value = []
        taggear = lambda arts: {i: ["nova"] for i in range(len(arts))}
        n = curadoria.backfill_tags(db_mod=fake_db, taggear_fn=taggear)
        self.assertEqual(n, 1)                                  # só o 'a' (sem tags)
        fake_db.atualizar_tags.assert_called_once_with("candidato", "a", ["nova"])
