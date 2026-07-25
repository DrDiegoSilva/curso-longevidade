"""Testes das colunas de aceite dos termos e da reversão de comissão. Standalone."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestTermosDB(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "subscribers"):
            sys.modules.pop(m, None)
        import db
        self.db = db
        db._INITED = False
        db.init()

    def test_colunas_de_termos_existem(self):
        with self.db._conn() as c:
            cols = [r[1] for r in c.execute("PRAGMA table_info(subscribers)").fetchall()]
        for col in ("termos_versao", "termos_aceito_em", "termos_ip"):
            self.assertIn(col, cols)

    def test_colunas_de_termos_em_pending_signups_existem(self):
        with self.db._conn() as c:
            cols = [r[1] for r in c.execute("PRAGMA table_info(pending_signups)").fetchall()]
        for col in ("termos_versao", "termos_ip"):
            self.assertIn(col, cols)

    def test_coluna_estornada_em_existe(self):
        with self.db._conn() as c:
            cols = [r[1] for r in c.execute("PRAGMA table_info(comissoes)").fetchall()]
        self.assertIn("estornada_em", cols)

    def test_estornar_comissao_marca_a_comissao_do_assinante(self):
        self.db.registrar_comissao("af1", "sub1", "anual", 997.0, 29.91)
        n = self.db.estornar_comissao("sub1")
        self.assertEqual(n, 1)
        com = [c for c in self.db.listar_comissoes() if c["subscriber_id"] == "sub1"][0]
        self.assertTrue(com["estornada_em"])

    def test_estornar_comissao_de_assinante_sem_comissao_devolve_zero(self):
        self.assertEqual(self.db.estornar_comissao("nao-existe"), 0)

    def _criar_subscriber(self, sid):
        with self.db._conn() as c:
            c.execute("INSERT INTO subscribers (id, nome, criado_em) VALUES (?,?,?)",
                      (sid, "Teste", "2026-01-01T00:00:00"))

    def _ler(self, sid):
        with self.db._conn() as c:
            return dict(c.execute("SELECT * FROM subscribers WHERE id=?", (sid,)).fetchone())

    def test_claim_cancelamento_grava_o_cancelamento_inteiro_de_uma_vez(self):
        # O claim É a gravação do estado final: status, cancelado_em, motivo e acesso_ate
        # saem no MESMO update. Não pode existir estado intermediário "reservado, mas o
        # cancelamento ainda não existe" — é nessa janela que moravam os bugs.
        self._criar_subscriber("sub-claim-1")
        self.assertTrue(self.db.claim_cancelamento("sub-claim-1", "caro demais", "2026-12-31"))
        r = self._ler("sub-claim-1")
        self.assertEqual(r["status"], "CANCELADO")
        self.assertEqual(r["cancel_motivo"], "caro demais")
        self.assertEqual(r["acesso_ate"], "2026-12-31")
        self.assertTrue(r["cancelado_em"])

    def test_claim_cancelamento_segunda_chamada_perde_e_nao_sobrescreve(self):
        # Duplo clique/retry concorrente no MESMO assinante: só uma vence, e a perdedora
        # não pode regravar acesso_ate por cima (devolveria acesso a quem foi reembolsado).
        self._criar_subscriber("sub-claim-2")
        self.assertTrue(self.db.claim_cancelamento("sub-claim-2", "arrependi", None))
        self.assertFalse(self.db.claim_cancelamento("sub-claim-2", "outro motivo", "2027-01-01"))
        r = self._ler("sub-claim-2")
        self.assertIsNone(r["acesso_ate"])
        self.assertEqual(r["cancel_motivo"], "arrependi")

    def test_claim_cancelamento_de_id_inexistente_nao_vence(self):
        # Sem linha para atualizar não há cancelamento gravado — não pode dizer que venceu
        # (o vencedor é quem pode estornar).
        self.assertFalse(self.db.claim_cancelamento("nao-existe", "x", None))

    def test_encerrar_acesso_zera_apos_estorno(self):
        # Ajuste POSTERIOR ao claim: o reembolso saiu, então o acesso cessa agora.
        self._criar_subscriber("sub-enc-1")
        self.db.claim_cancelamento("sub-enc-1", "arrependi", "2026-12-31")
        self.assertTrue(self.db.encerrar_acesso("sub-enc-1"))
        self.assertIsNone(self._ler("sub-enc-1")["acesso_ate"])

    def test_encerrar_acesso_nao_mexe_em_quem_voltou_a_ser_ativo(self):
        # Se um webhook de renovação reativou o assinante entre o claim e o ajuste, tirar
        # o acesso dele seria cortar quem está pagando.
        self._criar_subscriber("sub-enc-2")
        self.db.claim_cancelamento("sub-enc-2", "arrependi", "2026-12-31")
        with self.db._conn() as c:
            c.execute("UPDATE subscribers SET status='ATIVO' WHERE id=?", ("sub-enc-2",))
        self.assertFalse(self.db.encerrar_acesso("sub-enc-2"))
        self.assertEqual(self._ler("sub-enc-2")["acesso_ate"], "2026-12-31")


if __name__ == "__main__":
    unittest.main()
