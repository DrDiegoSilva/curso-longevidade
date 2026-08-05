"""Testes da trilha semanal de empreendedorismo médico. Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _recarregar(tmp):
    """Isola config/db/subscribers/trilha num banco temporário."""
    os.environ["DSCURSO_DATA"] = tmp
    os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(tmp, "t.db")
    for m in ("config", "db", "subscribers", "trilha"):
        if m in sys.modules:
            importlib.reload(sys.modules[m])
    import config, db, subscribers
    importlib.reload(config); importlib.reload(db); importlib.reload(subscribers)
    subscribers._migrado = False
    db.init()
    return config, db, subscribers


class TestBancoTrilha(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg, self.db, self.subs = _recarregar(self.tmp)

    def _peca(self, numero=1):
        self.db.trilha_upsert_peca(numero, "Saber onde você está", f"Peça {numero}",
                                   "corpo", "micro", "mentalidade", "")

    def test_upsert_peca_grava_e_le(self):
        self._peca(1)
        p = self.db.trilha_peca(1)
        self.assertEqual(p["titulo"], "Peça 1")
        self.assertEqual(p["micro_resultado"], "micro")

    def test_upsert_peca_atualiza_em_vez_de_duplicar(self):
        self._peca(1)
        self.db.trilha_upsert_peca(1, "eixo novo", "Título novo", "c", "m", "t", "")
        self.assertEqual(self.db.trilha_peca(1)["titulo"], "Título novo")

    def test_peca_inexistente_devolve_none(self):
        self.assertIsNone(self.db.trilha_peca(13))

    def test_posicao_nasce_em_1(self):
        self.assertEqual(self.db.trilha_posicao("sub-a"), 1)

    def test_registrar_envio_e_idempotente(self):
        self.assertTrue(self.db.trilha_registrar_envio("sub-a", 1))    # 1ª vez
        self.assertFalse(self.db.trilha_registrar_envio("sub-a", 1))   # repetido
        self.assertTrue(self.db.trilha_registrar_envio("sub-a", 2))    # outra peça
        self.assertTrue(self.db.trilha_registrar_envio("sub-b", 1))    # outro assinante

    def test_avancar_move_a_posicao(self):
        self.db.trilha_avancar("sub-a", 1)
        self.assertEqual(self.db.trilha_posicao("sub-a"), 2)

    def test_marcar_feito_e_idempotente(self):
        self.db.trilha_registrar_envio("sub-a", 1)
        self.assertFalse(self.db.trilha_fez("sub-a", 1))
        self.assertTrue(self.db.trilha_marcar_feito("sub-a", 1))
        self.assertTrue(self.db.trilha_fez("sub-a", 1))
        self.assertFalse(self.db.trilha_marcar_feito("sub-a", 1))   # 2º clique não duplica

    def test_marcar_feito_em_peca_nao_enviada_nao_grava(self):
        self.assertFalse(self.db.trilha_marcar_feito("sub-a", 7))
        self.assertFalse(self.db.trilha_fez("sub-a", 7))

    def test_historico_vem_do_mais_recente(self):
        self.db.trilha_registrar_envio("sub-a", 1)
        self.db.trilha_registrar_envio("sub-a", 2)
        h = self.db.trilha_historico("sub-a")
        self.assertEqual([x["numero"] for x in h], [2, 1])

    def test_painel_conta_enviadas_e_feitas(self):
        self.db.trilha_registrar_envio("sub-a", 1)
        self.db.trilha_registrar_envio("sub-a", 2)
        self.db.trilha_marcar_feito("sub-a", 1)
        self.db.trilha_avancar("sub-a", 2)
        linha = [l for l in self.db.trilha_painel() if l["subscriber_id"] == "sub-a"][0]
        self.assertEqual(linha["enviadas"], 2)
        self.assertEqual(linha["feitas"], 1)
        self.assertEqual(linha["proxima_peca"], 3)

    def test_tabelas_novas_estao_na_lista_de_rls(self):
        # fora de _TABELAS, a tabela fica exposta na Data API pública do Supabase
        for t in ("trilha_pecas", "trilha_progresso", "trilha_envios"):
            self.assertIn(t, self.db._TABELAS)


if __name__ == "__main__":
    unittest.main()
