"""Testes das tabelas da régua: automações, ledger de avisos e valor_contratado. Standalone."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestReguaDB(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "subscribers"):
            sys.modules.pop(m, None)
        import db
        self.db = db
        db._INITED = False
        db.init()

    def test_coluna_valor_contratado_existe(self):
        with self.db._conn() as c:
            cols = [r[1] for r in c.execute("PRAGMA table_info(subscribers)").fetchall()]
        self.assertIn("valor_contratado", cols)

    def test_seed_cria_as_seis_automacoes_padrao(self):
        autos = self.db.listar_automacoes()
        self.assertEqual(sorted(a["dias"] for a in autos), [-7, -3, 0, 1, 3, 15])
        self.assertTrue(all(a["canal"] == "whatsapp" for a in autos))
        self.assertTrue(all(a["texto"] for a in autos))

    def test_seed_e_idempotente(self):
        self.db._INITED = False
        self.db.init()
        self.assertEqual(len(self.db.listar_automacoes()), 6)

    def test_listar_ordena_por_dias(self):
        dias = [a["dias"] for a in self.db.listar_automacoes()]
        self.assertEqual(dias, sorted(dias))

    def test_salvar_automacao_nova_gera_id(self):
        novo = self.db.salvar_automacao("", 30, "email", "texto novo", 1)
        self.assertTrue(novo)
        achou = [a for a in self.db.listar_automacoes() if a["id"] == novo][0]
        self.assertEqual(achou["dias"], 30)
        self.assertEqual(achou["canal"], "email")

    def test_salvar_automacao_existente_atualiza(self):
        alvo = self.db.listar_automacoes()[0]
        self.db.salvar_automacao(alvo["id"], alvo["dias"], "email", "outro texto", 0)
        atual = [a for a in self.db.listar_automacoes() if a["id"] == alvo["id"]][0]
        self.assertEqual(atual["texto"], "outro texto")
        self.assertEqual(atual["canal"], "email")
        self.assertFalse(atual["ativo"])

    def test_so_ativas_filtra(self):
        alvo = self.db.listar_automacoes()[0]
        self.db.salvar_automacao(alvo["id"], alvo["dias"], alvo["canal"], alvo["texto"], 0)
        self.assertEqual(len(self.db.listar_automacoes(so_ativas=True)), 5)

    def test_remover_automacao(self):
        alvo = self.db.listar_automacoes()[0]
        self.assertTrue(self.db.remover_automacao(alvo["id"]))
        self.assertEqual(len(self.db.listar_automacoes()), 5)

    def test_registrar_aviso_marca_uma_vez_so(self):
        self.assertTrue(self.db.registrar_aviso("s1", "a1", "2026-08-01"))
        self.assertFalse(self.db.registrar_aviso("s1", "a1", "2026-08-01"))

    def test_ciclo_novo_libera_o_mesmo_aviso(self):
        # o vencimento_ref muda quando ele renova -> a régua volta a valer no ciclo seguinte
        self.assertTrue(self.db.registrar_aviso("s1", "a1", "2026-08-01"))
        self.assertTrue(self.db.registrar_aviso("s1", "a1", "2027-08-01"))

    def test_assinantes_diferentes_nao_se_bloqueiam(self):
        self.assertTrue(self.db.registrar_aviso("s1", "a1", "2026-08-01"))
        self.assertTrue(self.db.registrar_aviso("s2", "a1", "2026-08-01"))


if __name__ == "__main__":
    unittest.main()
