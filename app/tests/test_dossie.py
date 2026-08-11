"""Item 33, fatia 2a — o DOSSIÊ por tema.

Ideia do Diego (2026-08-11), depois do backfill trazer 617 estudos: *"não tem como já
analisar isso e já indexar em um artigo pra ir atrás somente desse artigo do que fica
lendo todos estudos toda vez, aí vai só acrescentando nesse documento cada arquivo novo?"*

Mandar os ~250 estudos do tema a cada dia dá ~100 mil tokens por chamada — e o custo
**cresce para sempre** conforme a base engorda. Lendo o dossiê são ~6 mil, e fica igual.
O argumento não é o preço de hoje: é que um escala e o outro não.

Duas travas que definem o formato:

1. **Telefone sem fio.** Reescrever resumo de resumo degrada em silêncio. Os abstracts
   brutos ficam no banco, então o dossiê é RECONSTRUÍVEL do zero — e é isso que impede a
   degradação de virar permanente.
2. **Rastreabilidade.** Dossiê em prosa mata a guarda de ancoragem. O dossiê é
   **afirmação + os estudos que a sustentam** (título, revista, data), nunca texto corrido.
"""
import importlib
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _estudo(i, titulo=None):
    return {"titulo": titulo or f"Estudo {i}", "fonte": "NEJM", "data": f"2026-0{i % 9 + 1}-01",
            "doi": f"10.1/e{i}", "abstract": "abstract " * 60}


def _bloco(afirmacao="GLP-1 reduz massa magra", refs=("Estudo 1",)):
    return {"afirmacao": afirmacao,
            "estudos": [{"titulo": t, "fonte": "NEJM", "data": "2026-03"} for t in refs]}


def _resposta(blocos):
    return json.dumps({"blocos": blocos}, ensure_ascii=False)


class TestParse(unittest.TestCase):
    """Mesma disciplina do `content.parse_gancho`: nunca levanta, nunca devolve None."""

    def setUp(self):
        import dossie
        importlib.reload(dossie)
        self.d = dossie

    def test_le_o_formato_esperado(self):
        d = self.d.parse(_resposta([_bloco()]))
        self.assertEqual(len(d["blocos"]), 1)
        self.assertEqual(d["blocos"][0]["afirmacao"], "GLP-1 reduz massa magra")

    def test_json_com_cerca_de_codigo_e_preambulo(self):
        """A IA responde com ```json e com "Segue o dossiê:" — o repo já tropeçou nisso."""
        bruto = "Segue o dossiê pedido:\n```json\n" + _resposta([_bloco()]) + "\n```"
        self.assertEqual(len(self.d.parse(bruto)["blocos"]), 1)

    def test_lixo_vira_dossie_vazio_em_vez_de_explodir(self):
        for bruto in ("", None, "não consegui", "{quebrado"):
            with self.subTest(bruto=bruto):
                self.assertEqual(self.d.parse(bruto), {"blocos": []})

    def test_bloco_sem_afirmacao_e_descartado(self):
        d = self.d.parse(_resposta([{"estudos": [{"titulo": "X"}]}, _bloco()]))
        self.assertEqual(len(d["blocos"]), 1)

    def test_bloco_sem_estudo_e_descartado(self):
        """Afirmação sem lastro é opinião solta — é exatamente o que o dossiê existe
        pra impedir."""
        d = self.d.parse(_resposta([{"afirmacao": "algo", "estudos": []}, _bloco()]))
        self.assertEqual(len(d["blocos"]), 1)


class TestConstruir(unittest.TestCase):
    """Map-reduce: o tema não cabe numa chamada só, então vai em lotes e depois funde."""

    def setUp(self):
        import dossie
        importlib.reload(dossie)
        self.d = dossie

    def test_quebra_em_lotes_em_vez_de_uma_chamada_gigante(self):
        chamadas = []
        estudos = [_estudo(i) for i in range(50)]
        self.d.construir(estudos, lote=20,
                         gerar_fn=lambda p: chamadas.append(p) or _resposta([_bloco()]))
        self.assertGreaterEqual(len(chamadas), 3)      # 50/20 = 3 lotes + a fusão

    def test_o_dossie_final_junta_o_que_veio_dos_lotes(self):
        estudos = [_estudo(i) for i in range(40)]
        d = self.d.construir(estudos, lote=20, gerar_fn=lambda p: _resposta([_bloco()]))
        self.assertTrue(d["blocos"])

    def test_corpus_vazio_devolve_dossie_vazio_sem_chamar_IA(self):
        chamou = []
        d = self.d.construir([], gerar_fn=lambda p: chamou.append(1) or _resposta([]))
        self.assertEqual(d["blocos"], [])
        self.assertEqual(chamou, [])

    def test_um_lote_que_falha_nao_derruba_o_dossie(self):
        estudos = [_estudo(i) for i in range(40)]
        n = {"i": 0}

        def gerar_fn(p):
            n["i"] += 1
            if n["i"] == 1:
                raise RuntimeError("IA fora do ar")
            return _resposta([_bloco()])

        d = self.d.construir(estudos, lote=20, gerar_fn=gerar_fn)
        self.assertTrue(d["blocos"])                   # o resto entrou

    def test_fusao_que_falha_preserva_os_parciais(self):
        """A fusão é a ÚLTIMA chamada, depois de ~10 lotes já pagos. Se ela falhar e o
        código devolvesse o vazio dela, todo esse trabalho iria pro lixo."""
        estudos = [_estudo(i) for i in range(40)]
        n = {"i": 0}

        def gerar_fn(p):
            n["i"] += 1
            if "memórias parciais" in p:      # a chamada de fusão
                raise RuntimeError("fora do ar")
            return _resposta([_bloco()])

        d = self.d.construir(estudos, lote=20, gerar_fn=gerar_fn)
        self.assertTrue(d["blocos"], "os parciais não podem ser jogados fora")

    def test_todos_os_lotes_falhando_devolve_vazio_em_vez_de_explodir(self):
        estudos = [_estudo(i) for i in range(20)]

        def bomba(p):
            raise RuntimeError("fora do ar")

        self.assertEqual(self.d.construir(estudos, lote=20, gerar_fn=bomba), {"blocos": []})

    def test_o_prompt_leva_titulo_revista_e_data_de_cada_estudo(self):
        """Sem isso o dossiê não consegue citar de volta, e a ancoragem morre."""
        vistos = []
        self.d.construir([_estudo(1, titulo="Tirzepatida e massa magra")], lote=20,
                         gerar_fn=lambda p: vistos.append(p) or _resposta([_bloco()]))
        self.assertIn("Tirzepatida e massa magra", vistos[0])
        self.assertIn("NEJM", vistos[0])


class TestAcrescentar(unittest.TestCase):
    """O "vai só acrescentando cada arquivo novo" do Diego."""

    def setUp(self):
        import dossie
        importlib.reload(dossie)
        self.d = dossie

    def test_o_estudo_novo_entra_sem_reler_o_corpus(self):
        atual = {"blocos": [_bloco()]}
        vistos = []
        novo = self.d.acrescentar(atual, _estudo(99, titulo="Estudo novo"),
                                  gerar_fn=lambda p: vistos.append(p) or _resposta(
                                      [_bloco(), _bloco("achado novo", ("Estudo novo",))]))
        self.assertEqual(len(novo["blocos"]), 2)
        self.assertIn("Estudo novo", vistos[0])
        self.assertIn("GLP-1 reduz massa magra", vistos[0])   # o dossiê atual vai junto

    def test_resposta_ruim_preserva_o_dossie_que_existia(self):
        """Dossiê velho é melhor que dossiê nenhum — mesma regra do kit."""
        atual = {"blocos": [_bloco()]}
        self.assertEqual(self.d.acrescentar(atual, _estudo(1), gerar_fn=lambda p: "lixo"),
                         atual)

    def test_falha_da_IA_preserva_o_dossie(self):
        atual = {"blocos": [_bloco()]}

        def bomba(p):
            raise RuntimeError("fora do ar")

        self.assertEqual(self.d.acrescentar(atual, _estudo(1), gerar_fn=bomba), atual)


class TestGuardarNoBanco(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import db as _db
        importlib.reload(_db)
        self.db = _db
        self.db.init()

    def test_salva_e_le_por_tema(self):
        self.db.salvar_dossie("Obesidade", {"blocos": [_bloco()]}, 250)
        d = self.db.obter_dossie("Obesidade")
        self.assertEqual(d["n_estudos"], 250)
        self.assertEqual(json.loads(d["conteudo"])["blocos"][0]["afirmacao"],
                         "GLP-1 reduz massa magra")

    def test_regravar_o_mesmo_tema_substitui_em_vez_de_duplicar(self):
        self.db.salvar_dossie("Obesidade", {"blocos": [_bloco("velho")]}, 10)
        self.db.salvar_dossie("Obesidade", {"blocos": [_bloco("novo")]}, 20)
        d = self.db.obter_dossie("Obesidade")
        self.assertEqual(d["n_estudos"], 20)
        self.assertEqual(json.loads(d["conteudo"])["blocos"][0]["afirmacao"], "novo")

    def test_tema_sem_dossie_devolve_None(self):
        self.assertIsNone(self.db.obter_dossie("Lipedema"))

    def test_guarda_quando_foi_atualizado(self):
        """A tela precisa mostrar 'atualizado há N dias' — dossiê velho engana."""
        self.db.salvar_dossie("Obesidade", {"blocos": []}, 1)
        self.assertTrue(self.db.obter_dossie("Obesidade")["atualizado_em"])


class TestAbaNaTela(unittest.TestCase):
    """O dossiê precisa ser LEGÍVEL — sem a aba, ele existe no banco e não serve pra nada."""

    def _pagina(self, dossies=None, aba="dossie"):
        import site_web
        return site_web.pagina_curadoria(
            {"pronto": 0, "minimo": 3}, None, [], [], {"candidatos": [], "banco": []},
            "tok", aba=aba, dossies=dossies)

    def test_a_aba_do_dossie_esta_na_navegacao(self):
        self.assertIn("aba=dossie", self._pagina(aba="triagem"))

    def test_mostra_a_afirmacao_E_os_estudos_que_a_sustentam(self):
        """Só a afirmação seria prosa disfarçada; é a lista de estudos que dá pro Diego
        julgar se a memória tem lastro."""
        html = self._pagina([{"tema": "Obesidade", "n_estudos": 247,
                              "atualizado_em": "2026-08-11T10:00:00",
                              "conteudo": json.dumps({"blocos": [_bloco(
                                  "GLP-1 reduz massa magra", ("Tirzepatida e composicao",))]})}])
        self.assertIn("GLP-1 reduz massa magra", html)
        self.assertIn("Tirzepatida e composicao", html)
        self.assertIn("247", html)

    def test_sem_dossie_ensina_a_construir_em_vez_de_ficar_em_branco(self):
        self.assertIn("Construir o dossiê", self._pagina([]))

    def test_conteudo_corrompido_no_banco_nao_derruba_a_tela(self):
        html = self._pagina([{"tema": "Obesidade", "n_estudos": 5,
                              "atualizado_em": "2026-08-11", "conteudo": "{quebrado"}])
        self.assertIn("Obesidade", html)


if __name__ == "__main__":
    unittest.main()
