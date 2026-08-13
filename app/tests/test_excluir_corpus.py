"""Tirar um estudo da MEMÓRIA do dossiê (item 33, parte A).

Diego, lendo o dossiê: *"tirar algum dado de estudo que não faça sentido"*. Como o dossiê
é reconstruído do zero, edição manual seria apagada sem aviso — então o conserto durável é
tirar o estudo do CORPUS, pra toda reconstrução futura já ignorá-lo.

Dois escopos, escolhidos no clique: 'memoria' (sai só do dossiê) e 'tudo' (sai também da
fila de envio). Standalone: python3 app/tests/test_excluir_corpus.py"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _snapshot_env():
    return (os.environ.get("DSCURSO_ARTIGOS_DB"), os.environ.get("DATABASE_URL"))


def _reload_db(tmp):
    os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(tmp, "t.db")
    os.environ.pop("DATABASE_URL", None)
    import importlib, db as _db
    importlib.reload(_db)
    _db.init()
    return _db


def _restore_db(snap):
    import importlib
    a, d = snap
    if a is None:
        os.environ.pop("DSCURSO_ARTIGOS_DB", None)
    else:
        os.environ["DSCURSO_ARTIGOS_DB"] = a
    if d is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = d
    import db as _db
    importlib.reload(_db)


def _cand(chave, titulo="Estudo X", tema="Obesidade", tipo="varredura"):
    return {"chave": chave, "titulo": titulo, "tema": tema, "tipo": tipo,
            "fonte": "NEJM", "data": "2026-03-01", "doi": "10.1/" + chave,
            "url": "", "abstract": "abstract do estudo", "pergunta": "", "score": 7,
            "citacoes": 0, "tags": []}


class _Base(unittest.TestCase):
    def setUp(self):
        self.snap = _snapshot_env()
        self.tmp = tempfile.mkdtemp()
        self.db = _reload_db(self.tmp)

    def tearDown(self):
        _restore_db(self.snap)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _id_de(self, titulo):
        return next(c["id"] for c in self.db.listar_candidatos(incluir_excluidos=True)
                    if c["titulo"] == titulo)


class TestFiltroNoListarCandidatos(_Base):
    """O filtro mora DENTRO do listar_candidatos, e não espalhado pelos 5 consumidores —
    é a classe de erro que vazou o `tipo='corpus'` pro picker do 🔁."""

    def setUp(self):
        super().setUp()
        self.db.salvar_candidatos([_cand("k1", "Fica"), _cand("k2", "Sai da fila"),
                                   _cand("k3", "So da memoria")])

    def test_escopo_tudo_some_da_listagem_padrao(self):
        self.db.excluir_candidato(self._id_de("Sai da fila"), "tudo")
        titulos = [c["titulo"] for c in self.db.listar_candidatos()]
        self.assertNotIn("Sai da fila", titulos)

    def test_escopo_memoria_CONTINUA_na_fila(self):
        """'memoria' tira do dossiê e só. Some daqui também seria tirar da fila sem ele
        ter pedido."""
        self.db.excluir_candidato(self._id_de("So da memoria"), "memoria")
        titulos = [c["titulo"] for c in self.db.listar_candidatos()]
        self.assertIn("So da memoria", titulos)

    def test_o_resto_continua_aparecendo(self):
        self.db.excluir_candidato(self._id_de("Sai da fila"), "tudo")
        self.assertIn("Fica", [c["titulo"] for c in self.db.listar_candidatos()])

    def test_incluir_excluidos_traz_todos(self):
        self.db.excluir_candidato(self._id_de("Sai da fila"), "tudo")
        self.assertEqual(len(self.db.listar_candidatos(incluir_excluidos=True)), 3)

    def test_filtro_convive_com_os_outros(self):
        self.db.excluir_candidato(self._id_de("Sai da fila"), "tudo")
        r = self.db.listar_candidatos(status="novo", tema="Obesidade", tipo="varredura")
        self.assertEqual(sorted(c["titulo"] for c in r), ["Fica", "So da memoria"])

    def test_devolver_traz_de_volta(self):
        cid = self._id_de("Sai da fila")
        self.db.excluir_candidato(cid, "tudo")
        self.db.excluir_candidato(cid, "")
        self.assertIn("Sai da fila", [c["titulo"] for c in self.db.listar_candidatos()])

    def test_escopo_invalido_levanta_em_vez_de_gravar_lixo(self):
        """Escopo com typo gravado no banco nunca filtraria nada, e o Diego acharia que
        excluiu."""
        with self.assertRaises(ValueError):
            self.db.excluir_candidato(self._id_de("Fica"), "memória")


class TestExclusaoSobreviveAVarredura(_Base):
    """`excluido` é coluna à parte: o upsert de `salvar_candidatos` atualiza os campos do
    paper e a exclusão continua de pé — inclusive na promoção corpus -> varredura."""

    def test_o_mesmo_paper_varrido_de_novo_continua_excluido(self):
        self.db.salvar_candidatos([_cand("k9", "Repetido", tipo="corpus")])
        self.db.excluir_candidato(self._id_de("Repetido"), "tudo")
        self.db.salvar_candidatos([_cand("k9", "Repetido", tipo="varredura")])
        self.assertEqual(self.db.listar_candidatos(), [])
        linha = self.db.listar_candidatos(incluir_excluidos=True)[0]
        self.assertEqual(linha["tipo"], "varredura")     # promoveu
        self.assertEqual(linha["excluido"], "tudo")      # e continua fora


class TestPortalNaoMuda(_Base):
    """`listar_por_tema` serve o portal do assinante (serve.py:653-657). Estudo enviado
    não se des-envia: a exclusão de um digest vale só dentro do corpus do dossiê."""

    def setUp(self):
        super().setUp()
        self.db.registrar_digest(
            {"tema": "Obesidade", "doi": "10.1/d", "fonte": "NEJM", "url": "",
             "titulo": "orig"},
            {"titulo_pt": "Estudo enviado", "resumo": "r", "gancho": "g", "grafico": None},
            None, data="2026-07-19")

    def test_digest_excluido_da_memoria_continua_no_portal(self):
        self.db.excluir_digest("obesidade", "2026-07-19", "memoria")
        titulos = [d["titulo_pt"] for d in self.db.listar_por_tema("obesidade")]
        self.assertEqual(titulos, ["Estudo enviado"])

    def test_digest_excluido_com_escopo_tudo_TAMBEM_continua_no_portal(self):
        self.db.excluir_digest("obesidade", "2026-07-19", "tudo")
        self.assertEqual(len(self.db.listar_por_tema("obesidade")), 1)

    def test_escopo_invalido_no_digest_tambem_levanta(self):
        with self.assertRaises(ValueError):
            self.db.excluir_digest("obesidade", "2026-07-19", "sim")


class TestListarExcluidos(_Base):
    def test_junta_candidato_e_digest_do_tema(self):
        self.db.salvar_candidatos([_cand("k1", "Candidato fora")])
        self.db.excluir_candidato(self._id_de("Candidato fora"), "memoria")
        self.db.registrar_digest(
            {"tema": "Obesidade", "doi": "10.1/d", "fonte": "NEJM", "url": "",
             "titulo": "orig"},
            {"titulo_pt": "Digest fora", "resumo": "r", "gancho": "g", "grafico": None},
            None, data="2026-07-19")
        self.db.excluir_digest("obesidade", "2026-07-19", "memoria")
        ex = self.db.listar_excluidos("Obesidade")
        self.assertEqual(sorted(e["titulo"] for e in ex), ["Candidato fora", "Digest fora"])
        self.assertEqual(sorted(e["origem"] for e in ex), ["candidato", "digest"])
        self.assertEqual({e["escopo"] for e in ex}, {"memoria"})

    def test_ref_do_digest_carrega_slug_e_data(self):
        self.db.registrar_digest(
            {"tema": "Obesidade", "doi": "10.1/d", "fonte": "NEJM", "url": "",
             "titulo": "orig"},
            {"titulo_pt": "Digest fora", "resumo": "r", "gancho": "g", "grafico": None},
            None, data="2026-07-19")
        self.db.excluir_digest("obesidade", "2026-07-19", "memoria")
        self.assertEqual(self.db.listar_excluidos("Obesidade")[0]["ref"],
                         "obesidade|2026-07-19")

    def test_tema_sem_exclusao_devolve_lista_vazia(self):
        self.assertEqual(self.db.listar_excluidos("Longevidade"), [])


class TestCasarTitulo(unittest.TestCase):
    """O dossiê guarda o título COMO A IA ESCREVEU. O ✕ do bloco precisa achar a linha
    real do banco — e, quando não achar, dizer isso em vez de fingir que excluiu."""

    def setUp(self):
        import importlib, dossie
        importlib.reload(dossie)
        self.d = dossie
        self.corpus = [
            {"id": "a", "origem": "candidato",
             "titulo": "Once-Weekly Semaglutide in Adults with Overweight or Obesity"},
            {"id": "b", "origem": "candidato",
             "titulo": "Efeitos da reposição hormonal na densidade óssea"},
            {"id": "c", "origem": "digest", "titulo": "Tirzepatide Once Weekly for Obesity"},
        ]

    def test_titulo_igual_acha(self):
        r = self.d.casar_titulo("Tirzepatide Once Weekly for Obesity", self.corpus)
        self.assertEqual(r["id"], "c")

    def test_ignora_caixa_pontuacao_e_acento(self):
        r = self.d.casar_titulo("EFEITOS DA REPOSICAO HORMONAL NA DENSIDADE OSSEA!",
                                self.corpus)
        self.assertEqual(r["id"], "b")

    def test_titulo_truncado_pela_IA_ainda_acha(self):
        r = self.d.casar_titulo("Once-Weekly Semaglutide in Adults with Over", self.corpus)
        self.assertEqual(r["id"], "a")

    def test_titulo_inexistente_devolve_None(self):
        self.assertIsNone(self.d.casar_titulo("Estudo que a IA inventou", self.corpus))

    def test_prefixo_curto_demais_nao_casa(self):
        """'Once' casaria com meio corpus — casamento frouxo excluiria o estudo errado,
        e o Diego só descobriria na reconstrução seguinte."""
        self.assertIsNone(self.d.casar_titulo("Once", self.corpus))

    def test_ambiguo_devolve_None_em_vez_de_chutar(self):
        corpus = [{"id": "x", "titulo": "Estudo repetido no banco"},
                  {"id": "y", "titulo": "Estudo repetido no banco"}]
        self.assertIsNone(self.d.casar_titulo("Estudo repetido no banco", corpus))

    def test_titulo_vazio_devolve_None(self):
        for t in ("", None, "   "):
            with self.subTest(t=t):
                self.assertIsNone(self.d.casar_titulo(t, self.corpus))

    def test_corpus_vazio_devolve_None(self):
        self.assertIsNone(self.d.casar_titulo("Qualquer coisa", []))

    def test_normalizar_tira_acento_e_pontuacao(self):
        self.assertEqual(self.d.normalizar_titulo("Ação: Reposição — Hormonal!"),
                         "acao reposicao hormonal")

    def test_titulo_exato_mas_prefixo_de_outro_devolve_None(self):
        """Se o alvo (normalizado) é prefixo exato de outro estudo, é ambíguo —
        pode ser uma truncagem da IA. Só com a lista o médico resolve."""
        corpus = [
            {"id": "adulto", "titulo": "Semaglutide for Weight Management"},
            {"id": "adolesc", "titulo": "Semaglutide for Weight Management in Adolescents"},
        ]
        # O alvo "Semaglutide for Weight Management" bate exato com "adulto",
        # mas é prefixo de "adolesc". Ambíguo.
        self.assertIsNone(self.d.casar_titulo("Semaglutide for Weight Management", corpus))

    def test_titulo_longo_com_prefixo_curto_no_corpus_ainda_acha(self):
        """Mas o título longo (completo) do adolescente ainda funciona."""
        corpus = [
            {"id": "adulto", "titulo": "Semaglutide for Weight Management"},
            {"id": "adolesc", "titulo": "Semaglutide for Weight Management in Adolescents"},
        ]
        r = self.d.casar_titulo("Semaglutide for Weight Management in Adolescents", corpus)
        self.assertEqual(r["id"], "adolesc")

    def test_titulo_exato_unico_sem_parente_continua_casando(self):
        """Título único e sem parente por prefixo continua funcionando."""
        corpus = [
            {"id": "c1", "titulo": "Estudo X"},
            {"id": "c2", "titulo": "Estudo Y diferente"},
        ]
        r = self.d.casar_titulo("Estudo X", corpus)
        self.assertEqual(r["id"], "c1")

    def test_prefixo_ambiguo_entre_dois_do_corpus_devolve_None(self):
        """O alvo truncado é prefixo de DOIS estudos do corpus (nenhum bate exato) —
        chutar o primeiro excluiria o estudo errado sem o Diego perceber. Tem que
        devolver None, igual ao ambíguo por título igual."""
        corpus = [
            {"id": "obesidade", "titulo": "Semaglutide Reduces Weight in Adult Patients With Obesity"},
            {"id": "diabetes", "titulo": "Semaglutide Reduces Weight in Adult Patients With Diabetes"},
        ]
        alvo = "Semaglutide Reduces Weight in Adult Patients With"
        self.assertIsNone(self.d.casar_titulo(alvo, corpus))


class TestCorpusDoTema(_Base):
    """O corpus tem DUAS fontes e a exclusão precisa valer nas duas."""

    def setUp(self):
        super().setUp()
        self.db.salvar_candidatos([_cand("k1", "Candidato bom"), _cand("k2", "Candidato ruim")])
        self.db.registrar_digest(
            {"tema": "Obesidade", "doi": "10.1/d", "fonte": "NEJM", "url": "",
             "titulo": "orig"},
            {"titulo_pt": "Enviado bom", "resumo": "r", "gancho": "g", "grafico": None},
            None, data="2026-07-19")
        import importlib, dossie
        importlib.reload(dossie)
        self.dossie = dossie

    def _titulos(self):
        return sorted(e["titulo"] for e in self.dossie.corpus_do_tema("Obesidade", self.db))

    def test_junta_as_duas_fontes(self):
        self.assertEqual(self._titulos(), ["Candidato bom", "Candidato ruim", "Enviado bom"])

    def test_candidato_excluido_da_memoria_sai_do_corpus(self):
        self.db.excluir_candidato(self._id_de("Candidato ruim"), "memoria")
        self.assertEqual(self._titulos(), ["Candidato bom", "Enviado bom"])

    def test_candidato_excluido_de_tudo_tambem_sai_do_corpus(self):
        self.db.excluir_candidato(self._id_de("Candidato ruim"), "tudo")
        self.assertEqual(self._titulos(), ["Candidato bom", "Enviado bom"])

    def test_digest_excluido_da_memoria_sai_do_corpus(self):
        self.db.excluir_digest("obesidade", "2026-07-19", "memoria")
        self.assertEqual(self._titulos(), ["Candidato bom", "Candidato ruim"])

    def test_digest_excluido_de_tudo_tambem_sai_do_corpus(self):
        self.db.excluir_digest("obesidade", "2026-07-19", "tudo")
        self.assertEqual(self._titulos(), ["Candidato bom", "Candidato ruim"])

    def test_cada_item_carrega_id_e_origem(self):
        itens = {e["titulo"]: e for e in self.dossie.corpus_do_tema("Obesidade", self.db)}
        self.assertEqual(itens["Candidato bom"]["origem"], "candidato")
        self.assertTrue(itens["Candidato bom"]["id"])
        self.assertEqual(itens["Enviado bom"]["origem"], "digest")
        self.assertEqual(itens["Enviado bom"]["id"], "obesidade|2026-07-19")

    def test_construir_continua_funcionando_com_os_campos_novos(self):
        """`_linha` lê título/fonte/data/abstract; campo extra não pode atrapalhar."""
        estudos = self.dossie.corpus_do_tema("Obesidade", self.db)
        d = self.dossie.construir(
            estudos, gerar_fn=lambda p: '{"blocos":[{"afirmacao":"a","estudos":'
                                        '[{"titulo":"Candidato bom"}]}]}')
        self.assertTrue(d["blocos"])


if __name__ == "__main__":
    unittest.main()
