"""Testes do db.py (SQLite do arquivo). Roda standalone: python3 app/tests/test_db.py"""
import os
import sys
import json
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import importlib
        import db as _db
        importlib.reload(_db)
        self.db = _db
        self.db.init()

    def _art(self, tema="Obesidade", doi="10.1/x"):
        return {"tema": tema, "doi": doi, "fonte": "NEJM", "url": "http://x", "titulo": "orig"}

    def _cont(self, titulo="Título PT", grafico=None):
        return {"titulo_pt": titulo, "resumo": "Linha 1\nLinha 2", "gancho": "dica", "grafico": grafico}

    def test_slug(self):
        self.assertEqual(self.db.slug("Obesidade"), "obesidade")
        self.assertEqual(self.db.slug("Hormonal"), "hormonal")
        self.assertEqual(self.db.slug("Menopausa & Reposição Hormonal"), "menopausa-reposicao-hormonal")
        self.assertEqual(self.db.slug("Longevidade"), "longevidade")

    def test_registrar_e_obter(self):
        self.db.registrar_digest(self._art(), self._cont(grafico={"barras": [{"rotulo": "A", "valor": 5}]}), None, data="2026-07-19")
        d = self.db.obter("obesidade", "2026-07-19")
        self.assertIsNotNone(d)
        self.assertEqual(d["titulo_pt"], "Título PT")
        self.assertEqual(d["doi"], "10.1/x")
        self.assertEqual(json.loads(d["grafico"])["barras"][0]["rotulo"], "A")

    def test_listar_por_tema_ordem(self):
        self.db.registrar_digest(self._art(), self._cont("Velho"), None, data="2026-07-10")
        self.db.registrar_digest(self._art(), self._cont("Novo"), None, data="2026-07-15")
        lst = self.db.listar_por_tema("obesidade")
        self.assertEqual([x["titulo_pt"] for x in lst], ["Novo", "Velho"])

    def test_listar_temas_conta(self):
        self.db.registrar_digest(self._art("Obesidade"), self._cont(), None, data="2026-07-10")
        self.db.registrar_digest(self._art("Obesidade"), self._cont(), None, data="2026-07-11")
        self.db.registrar_digest(self._art("Lipedema"), self._cont(), None, data="2026-07-12")
        temas = {t["slug"]: t for t in self.db.listar_temas()}
        self.assertEqual(temas["obesidade"]["total"], 2)
        self.assertEqual(temas["lipedema"]["total"], 1)
        self.assertNotIn("performance", temas)  # sem digest => não aparece
        self.assertEqual(temas["obesidade"]["rotulo"], "Obesidade")

    def test_upsert_nao_duplica(self):
        self.db.registrar_digest(self._art(), self._cont("V1"), None, data="2026-07-19")
        self.db.registrar_digest(self._art(), self._cont("V2"), None, data="2026-07-19")
        lst = self.db.listar_por_tema("obesidade")
        self.assertEqual(len(lst), 1)
        self.assertEqual(lst[0]["titulo_pt"], "V2")


if __name__ == "__main__":
    unittest.main()
