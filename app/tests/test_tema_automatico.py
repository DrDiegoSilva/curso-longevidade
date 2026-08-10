"""Item 35 C — estudo subido na mão carimbava o chip fixo "MEUS ESTUDOS" na capa.

Agora a área sai da IA (as mesmas 5 do `temas_config.json`), com "Meus estudos"
como rede de segurança: classificar é ENFEITE, subir o estudo é o que importa —
se a IA falhar, o upload não pode falhar junto.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TEMAS = ["Obesidade", "Hormonal", "Lipedema", "Performance", "Longevidade"]


class TestClassificador(unittest.TestCase):
    def setUp(self):
        import triage
        self.t = triage

    def test_devolve_a_chave_que_a_ia_escolheu(self):
        r = self.t.classificar_tema("Tirzepatida e massa magra", "texto", TEMAS,
                                    llm=lambda p: "Obesidade")
        self.assertEqual(r, "Obesidade")

    def test_tolera_resposta_falante(self):
        """Haiku às vezes devolve 'Tema: Performance.' em vez da chave nua."""
        r = self.t.classificar_tema("t", "x", TEMAS, llm=lambda p: "Tema: Performance.")
        self.assertEqual(r, "Performance")

    def test_ia_sem_certeza_devolve_vazio(self):
        self.assertEqual(self.t.classificar_tema("t", "x", TEMAS, llm=lambda p: "NENHUM"), "")

    def test_resposta_fora_da_lista_nao_inventa_tema(self):
        self.assertEqual(self.t.classificar_tema("t", "x", TEMAS, llm=lambda p: "Cardiologia"), "")

    def test_falha_da_ia_nao_derruba_a_classificacao(self):
        def explode(p):
            raise RuntimeError("sem rede")
        self.assertEqual(self.t.classificar_tema("t", "x", TEMAS, llm=explode), "")

    def test_o_texto_do_estudo_chega_no_prompt(self):
        visto = {}
        self.t.classificar_tema("Titulo do paper", "CORPO-DO-ESTUDO", TEMAS,
                                llm=lambda p: visto.setdefault("p", p) or "Obesidade")
        self.assertIn("CORPO-DO-ESTUDO", visto["p"])
        self.assertIn("Titulo do paper", visto["p"])
        for t in TEMAS:
            self.assertIn(t, visto["p"])


class TestUploadCarimbaAArea(unittest.TestCase):
    def setUp(self):
        import importlib
        import shutil
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        for m in ("config", "db", "curadoria"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import db, curadoria
        importlib.reload(db)
        importlib.reload(curadoria)
        self.db, self.cur = db, curadoria
        db.init()

    def _subir(self, classificar_fn):
        return self.cur.adicionar_meu_estudo(
            "texto integral do estudo em PDF...", titulo="Meu PDF",
            triar_fn=lambda arts, tema: [], classificar_fn=classificar_fn,
            gerar_resumo=lambda a: "resumo", gerar_gancho=lambda a: "g",
            gerar_grafico_json=lambda a: "null", gerar_titulo=lambda a: "T")

    def test_area_detectada_vira_o_tema_do_estudo(self):
        self._subir(lambda titulo, texto, temas: "Obesidade")
        self.assertEqual(self.db.listar_reserva(status="pronto")[0]["tema"], "Obesidade")

    def test_sem_deteccao_cai_no_meus_estudos_de_sempre(self):
        self._subir(lambda titulo, texto, temas: "")
        self.assertEqual(self.db.listar_reserva(status="pronto")[0]["tema"], "Meus estudos")

    def test_classificador_que_explode_nao_impede_o_upload(self):
        """A capa é enfeite; perder o estudo do Diego não é aceitável."""
        def explode(titulo, texto, temas):
            raise RuntimeError("caiu")
        self._subir(explode)
        fila = self.db.listar_reserva(status="pronto")
        self.assertEqual(len(fila), 1)
        self.assertEqual(fila[0]["tema"], "Meus estudos")

    def test_o_classificador_recebe_as_5_areas_reais_do_config(self):
        visto = {}

        def espiar(titulo, texto, temas):
            visto["t"] = temas
            return ""

        self._subir(espiar)
        self.assertIn("Obesidade", visto["t"])
        self.assertIn("Longevidade", visto["t"])
        self.assertNotIn("Meus estudos", visto["t"])


if __name__ == "__main__":
    unittest.main()
