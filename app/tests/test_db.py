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

    def test_pending_roundtrip(self):
        tok = self.db.criar_pending({"nome": "Dr. X", "whatsapp": "5543", "plano": "anual",
                                     "metodo": "CARTAO", "parcelas": 12, "valor": 1000.4})
        p = self.db.obter_pending(tok)
        self.assertEqual(p["plano"], "anual")
        self.assertEqual(p["parcelas"], 12)
        self.assertIsNone(self.db.obter_pending("inexistente"))

    def test_webhook_idempotente(self):
        self.assertTrue(self.db.registrar_webhook("pay_1", "PAYMENT_CONFIRMED"))
        self.assertFalse(self.db.registrar_webhook("pay_1", "PAYMENT_CONFIRMED"))  # já visto
        self.assertTrue(self.db.registrar_webhook("pay_1", "PAYMENT_RECEIVED"))    # outro evento

    def test_token_senha_roundtrip_e_uso_unico(self):
        tok = self.db.criar_token_senha("5543999990000", validade_horas=1)
        r = self.db.obter_token_senha(tok)
        self.assertEqual(r["whatsapp"], "5543999990000")
        self.db.consumir_token_senha(tok)
        self.assertIsNone(self.db.obter_token_senha(tok))          # usado => inválido
        self.assertIsNone(self.db.obter_token_senha("naoexiste"))
        self.assertIsNone(self.db.obter_token_senha(""))

    def test_token_senha_expirado(self):
        from datetime import datetime, timedelta
        tok = self.db.criar_token_senha("5543", validade_horas=1)
        with self.db._conn() as c:
            c.execute("UPDATE senha_tokens SET expira=? WHERE token=?",
                      ((datetime.now() - timedelta(minutes=1)).isoformat(), tok))
        self.assertIsNone(self.db.obter_token_senha(tok))

    def _cand(self, chave, tema="Obesidade", titulo="X"):
        return {"tema": tema, "titulo": titulo, "fonte": "NEJM", "data": "2026-02-01",
                "doi": chave, "url": "", "abstract": "abc", "pergunta": "Funciona?",
                "score": 8.0, "chave": chave}

    def test_candidatos_dedup_e_selecao(self):
        n = self.db.salvar_candidatos([self._cand("10.1/a"), self._cand("10.1/b"), self._cand("10.1/a")])
        self.assertEqual(n, 2)                                    # dedup por chave
        self.assertEqual(self.db.salvar_candidatos([self._cand("10.1/a")]), 0)   # já existe
        cands = self.db.listar_candidatos(status="novo")
        self.assertEqual(len(cands), 2)
        ids = [c["id"] for c in cands]
        self.db.definir_selecao([ids[0]])
        self.assertEqual(len(self.db.listar_candidatos(status="selecionado")), 1)
        # tirar da seleção volta p/ novo
        self.db.definir_selecao([])
        self.assertEqual(len(self.db.listar_candidatos(status="selecionado")), 0)
        self.assertEqual(len(self.db.listar_candidatos(status="novo")), 2)

    def test_reserva_roundtrip(self):
        self.db.salvar_candidatos([self._cand("10.1/z")])
        cid = self.db.listar_candidatos()[0]["id"]
        self.db.marcar_candidatos([cid], "resumido")
        self.db.salvar_reserva({"candidato_id": cid, "tema": "Obesidade", "titulo_pt": "Título",
                                "resumo": "corpo", "gancho": "g", "grafico": "", "doi": "10.1/z"})
        res = self.db.listar_reserva(status="pronto")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["titulo_pt"], "Título")
        self.assertEqual(self.db.contar_candidatos().get("resumido"), 1)

    def test_cupom(self):
        import importlib
        os.environ["DSCURSO_CUPONS"] = "DIEGO2026, cortesia"
        import config as _c
        importlib.reload(_c)
        importlib.reload(self.db)
        self.db.init()
        self.assertTrue(self.db.cupom_valido("diego2026"))   # case-insensitive
        self.assertTrue(self.db.cupom_valido("CORTESIA"))
        self.assertFalse(self.db.cupom_valido("naoexiste"))
        del os.environ["DSCURSO_CUPONS"]


if __name__ == "__main__":
    unittest.main()
