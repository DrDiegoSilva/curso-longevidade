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


if __name__ == "__main__":
    unittest.main()
