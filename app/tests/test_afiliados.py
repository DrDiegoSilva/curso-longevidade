"""Testes de afiliados/comissões (db). Standalone: python3 app/tests/test_afiliados.py"""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAfiliadosDb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import db as _db
        importlib.reload(_db)
        self.db = _db
        self.db.init()

    def test_criar_e_por_codigo(self):
        cod = self.db.criar_afiliado("Dra. Maria", "maria@x.com", "dramaria", 10, 3)
        self.assertEqual(cod, "DRAMARIA")
        af = self.db.afiliado_por_codigo("dramaria")            # case-insensitive
        self.assertIsNotNone(af)
        self.assertEqual(af["nome"], "Dra. Maria")
        self.assertEqual(af["pct_desconto"], 10)
        self.assertEqual(af["pct_comissao"], 3)
        self.assertEqual(self.db.afiliado_por_codigo("naoexiste"), None)

    def test_toggle_desativa(self):
        self.db.criar_afiliado("M", "", "codX")
        af = self.db.afiliado_por_codigo("codx")
        self.db.toggle_afiliado(af["id"], False)
        self.assertIsNone(self.db.afiliado_por_codigo("codx"))  # inativo some da consulta
        self.db.toggle_afiliado(af["id"], True)
        self.assertIsNotNone(self.db.afiliado_por_codigo("codx"))

    def test_comissoes_ledger_e_agregados(self):
        self.db.criar_afiliado("Dra. Maria", "", "dramaria", 10, 3)
        af = self.db.afiliado_por_codigo("dramaria")
        c1 = self.db.registrar_comissao(af["id"], "sub1", "anual", 897.30, 26.92)
        self.db.registrar_comissao(af["id"], "sub2", "mensal", 89.10, 2.67)
        # lista completa e filtro por pago
        self.assertEqual(len(self.db.listar_comissoes(af["id"])), 2)
        self.assertEqual(len(self.db.listar_comissoes(af["id"], pago=False)), 2)
        self.assertEqual(len(self.db.listar_comissoes(af["id"], pago=True)), 0)
        # marcar 1 como paga
        self.db.marcar_comissao_paga(c1)
        self.assertEqual(len(self.db.listar_comissoes(af["id"], pago=True)), 1)
        pagas = self.db.listar_comissoes(af["id"], pago=True)
        self.assertIsNotNone(pagas[0]["pago_em"])
        # agregados
        linha = next(a for a in self.db.listar_afiliados() if a["codigo"] == "DRAMARIA")
        self.assertEqual(linha["n_vendas"], 2)
        self.assertAlmostEqual(linha["comissao_total"], 29.59, places=2)
        self.assertAlmostEqual(linha["comissao_pendente"], 2.67, places=2)   # c1 já paga

    def test_pending_guarda_afiliado_codigo(self):
        tok = self.db.criar_pending({"nome": "X", "whatsapp": "5543", "plano": "anual",
                                     "afiliado_codigo": "DRAMARIA", "valor": 897.30})
        p = self.db.obter_pending(tok)
        self.assertEqual(p["afiliado_codigo"], "DRAMARIA")
        # sem o campo -> continua funcionando (default vazio)
        tok2 = self.db.criar_pending({"nome": "Y", "whatsapp": "5544", "plano": "mensal"})
        self.assertIn(self.db.obter_pending(tok2)["afiliado_codigo"], (None, ""))


if __name__ == "__main__":
    unittest.main()
