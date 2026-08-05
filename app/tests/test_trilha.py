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


class TestParseESeed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg, self.db, self.subs = _recarregar(self.tmp)
        import trilha
        importlib.reload(trilha)
        self.t = trilha

    def test_parse_le_cabecalho_e_secoes(self):
        p = self.t.parse_peca(
            "titulo: O custo real da sua hora\n"
            "eixo: Saber onde você está\n"
            "ferramenta: planilha-custo-hora\n"
            "\n"
            "## corpo\n"
            "Primeiro parágrafo.\n"
            "\n"
            "Segundo parágrafo.\n"
            "\n"
            "## micro-resultado\n"
            "Calcule o custo da sua hora.\n"
            "\n"
            "## mentalidade\n"
            "Empenho é diferente de desempenho.\n")
        self.assertEqual(p["titulo"], "O custo real da sua hora")
        self.assertEqual(p["eixo"], "Saber onde você está")
        self.assertEqual(p["ferramenta"], "planilha-custo-hora")
        self.assertIn("Segundo parágrafo.", p["corpo"])
        self.assertEqual(p["micro_resultado"], "Calcule o custo da sua hora.")
        self.assertEqual(p["mentalidade"], "Empenho é diferente de desempenho.")

    def test_parse_sem_ferramenta_devolve_vazio(self):
        p = self.t.parse_peca("titulo: X\neixo: Y\n\n## corpo\nz\n")
        self.assertEqual(p["ferramenta"], "")
        self.assertEqual(p["micro_resultado"], "")

    def test_semear_grava_as_pecas_do_diretorio(self):
        d = os.path.join(self.tmp, "trilha")
        os.makedirs(d)
        with open(os.path.join(d, "01-um.md"), "w", encoding="utf-8") as f:
            f.write("titulo: Um\neixo: A\n\n## corpo\ncorpo um\n")
        with open(os.path.join(d, "02-dois.md"), "w", encoding="utf-8") as f:
            f.write("titulo: Dois\neixo: A\n\n## corpo\ncorpo dois\n")
        self.assertEqual(self.t.semear(d), 2)
        self.assertEqual(self.db.trilha_peca(1)["titulo"], "Um")
        self.assertEqual(self.db.trilha_peca(2)["titulo"], "Dois")

    def test_semear_e_idempotente_e_atualiza_texto_editado(self):
        d = os.path.join(self.tmp, "trilha")
        os.makedirs(d)
        caminho = os.path.join(d, "01-um.md")
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("titulo: Um\neixo: A\n\n## corpo\nversao 1\n")
        self.t.semear(d)
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("titulo: Um\neixo: A\n\n## corpo\nversao 2\n")
        self.t.semear(d)
        self.assertIn("versao 2", self.db.trilha_peca(1)["corpo"])

    def test_semear_ignora_arquivo_sem_numero_no_nome(self):
        d = os.path.join(self.tmp, "trilha")
        os.makedirs(d)
        with open(os.path.join(d, "leiame.md"), "w", encoding="utf-8") as f:
            f.write("titulo: X\n\n## corpo\ny\n")
        self.assertEqual(self.t.semear(d), 0)

    def test_semear_diretorio_inexistente_nao_quebra(self):
        self.assertEqual(self.t.semear(os.path.join(self.tmp, "nao-existe")), 0)

    def test_as_12_pecas_do_repo_carregam(self):
        # o diretório real do repo tem que estar parseável e completo
        self.assertEqual(self.t.semear(), self.cfg.TRILHA_TOTAL)
        for n in range(1, self.cfg.TRILHA_TOTAL + 1):
            p = self.db.trilha_peca(n)
            self.assertIsNotNone(p, f"peça {n} não carregou")
            self.assertTrue(p["titulo"].strip(), f"peça {n} sem título")


if __name__ == "__main__":
    unittest.main()
