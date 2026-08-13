"""As telas da exclusão, na aba 🧠 Dossiê. Standalone:
python3 app/tests/test_excluir_corpus_ui.py"""
import importlib
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _dossie(tema="Obesidade", afirmacao="GLP-1 reduz massa magra",
            estudos=("Once-Weekly Semaglutide in Adults with Overweight",)):
    return {"tema": tema, "atualizado_em": "2026-08-12T10:00:00", "n_estudos": 3,
            "conteudo": json.dumps({"blocos": [
                {"afirmacao": afirmacao,
                 "estudos": [{"titulo": t, "fonte": "NEJM", "data": "2026-03"}
                             for t in estudos]}]}, ensure_ascii=False)}


def _painel(corpus=None, excluidos=None, tema="Obesidade"):
    return {tema: {"corpus": corpus if corpus is not None else [
        {"id": "c1", "origem": "candidato",
         "titulo": "Once-Weekly Semaglutide in Adults with Overweight",
         "fonte": "NEJM", "data": "2026-03-01"}],
        "excluidos": excluidos or []}}


# ── banco de verdade, pro dossie.painel() (mesmo padrão de tests/test_excluir_corpus.py) ──
def _snapshot_env():
    return (os.environ.get("DSCURSO_ARTIGOS_DB"), os.environ.get("DATABASE_URL"))


def _reload_db(tmp):
    os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(tmp, "t.db")
    os.environ.pop("DATABASE_URL", None)
    import db as _db
    importlib.reload(_db)
    _db.init()
    return _db


def _restore_db(snap):
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


def _cand(chave, titulo="Estudo X", tema="Obesidade", abstract="abstract do estudo"):
    return {"chave": chave, "titulo": titulo, "tema": tema, "tipo": "varredura",
            "fonte": "NEJM", "data": "2026-03-01", "doi": "10.1/" + chave,
            "url": "", "abstract": abstract, "pergunta": "", "score": 7,
            "citacoes": 0, "tags": []}


class TestDossieHtml(unittest.TestCase):
    def setUp(self):
        import site_web
        importlib.reload(site_web)
        self.sw = site_web

    def test_estudo_do_bloco_ganha_botao_de_tirar_da_memoria(self):
        html = self.sw._dossie_html([_dossie()], _painel(), token="tok")
        self.assertIn("confirmar_exclusao", html)
        self.assertIn("Once-Weekly Semaglutide in Adults with Overweight", html)

    def test_o_aviso_de_que_o_x_nao_e_para_discordar_aparece(self):
        """Sem esse texto o ✕ vira ferramenta de apagar o que contraria a leitura do
        Diego — e a memória vira eco."""
        html = self.sw._dossie_html([_dossie()], _painel(), token="tok")
        self.assertIn("divergência", html)

    def test_estudo_ja_excluido_sai_riscado_e_sem_botao(self):
        ex = [{"origem": "candidato", "ref": "c1",
               "titulo": "Once-Weekly Semaglutide in Adults with Overweight",
               "fonte": "NEJM", "data": "2026-03-01", "escopo": "memoria"}]
        html = self.sw._dossie_html([_dossie()], _painel(corpus=[], excluidos=ex), token="tok")
        self.assertIn("line-through", html)
        self.assertIn("refaça o dossiê", html)

    def test_riscado_casa_titulo_que_so_bate_apos_normalizar(self):
        """O título no bloco e o título em `excluidos` quase nunca chegam char a char
        iguais (um vem do texto que a IA escreveu, o outro do banco). Se a comparação
        virar um `==` cru em vez de `normalizar_titulo(...) in fora`, este caso — que
        só bate depois de tirar caixa, acento e pontuação — deixa de riscar."""
        d = _dossie(afirmacao="Reposição hormonal ajuda",
                    estudos=("Efeitos da reposição hormonal na densidade óssea",))
        ex = [{"origem": "candidato", "ref": "c1",
               "titulo": "EFEITOS DA REPOSICAO HORMONAL NA DENSIDADE OSSEA!",
               "fonte": "NEJM", "data": "2026-03-01", "escopo": "memoria"}]
        html = self.sw._dossie_html([d], _painel(corpus=[], excluidos=ex), token="tok")
        self.assertIn("line-through", html)

    def test_lista_estudos_lidos_traz_os_dois_escopos(self):
        html = self.sw._dossie_html([_dossie()], _painel(), token="tok")
        self.assertIn("Estudos lidos", html)
        self.assertIn('value="memoria"', html)
        self.assertIn('value="tudo"', html)

    def test_estudo_ja_enviado_so_oferece_tirar_da_memoria(self):
        """Não se des-envia um estudo: o escopo 'tudo' não faz sentido para um digest."""
        corpus = [{"id": "obesidade|2026-07-19", "origem": "digest",
                   "titulo": "Estudo enviado", "fonte": "NEJM", "data": "2026-07-19"}]
        html = self.sw._dossie_html([_dossie()], _painel(corpus=corpus), token="tok")
        self.assertIn('value="memoria"', html)
        self.assertNotIn('value="tudo"', html)

    def test_lista_de_excluidos_tem_devolver(self):
        ex = [{"origem": "candidato", "ref": "c1", "titulo": "Estudo fora",
               "fonte": "NEJM", "data": "2026-03-01", "escopo": "tudo"}]
        html = self.sw._dossie_html([_dossie()], _painel(excluidos=ex), token="tok")
        self.assertIn("Fora da memória", html)
        self.assertIn("devolver_corpus", html)

    def test_botao_de_refazer_so_este_tema(self):
        html = self.sw._dossie_html([_dossie()], _painel(), token="tok")
        self.assertIn("refazer_dossie_tema", html)

    def test_sem_painel_nao_quebra(self):
        """A aba pode ser renderizada sem painel (ex.: outra aba ativa)."""
        html = self.sw._dossie_html([_dossie()], None, token="tok")
        self.assertIn("GLP-1 reduz massa magra", html)

    def test_escapa_titulo_com_html(self):
        d = _dossie(estudos=("<script>alert(1)</script>",))
        html = self.sw._dossie_html([d], _painel(corpus=[]), token="tok")
        self.assertNotIn("<script>alert(1)</script>", html)


class TestPainel(unittest.TestCase):
    """`dossie.painel` é o encanamento de verdade: percorre os temas, chama
    `corpus_do_tema` e `db.listar_excluidos`, e filtra as chaves que a tela usa. Banco
    de verdade (sqlite temporário) — é a peça que liga as tasks 6-8 ao que aparece
    na tela, e não tinha teste nenhum."""

    def setUp(self):
        self.snap = _snapshot_env()
        self.tmp = tempfile.mkdtemp()
        self.db = _reload_db(self.tmp)
        import dossie
        importlib.reload(dossie)
        self.dossie = dossie

    def tearDown(self):
        _restore_db(self.snap)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_traz_o_tema_com_corpus_e_excluidos(self):
        self.db.salvar_candidatos([_cand("k1", "Fica na memória")])
        cid = next(c["id"] for c in self.db.listar_candidatos()
                  if c["titulo"] == "Fica na memória")
        self.db.salvar_candidatos([_cand("k2", "Sai da memória")])
        eid = next(c["id"] for c in self.db.listar_candidatos()
                  if c["titulo"] == "Sai da memória")
        self.db.excluir_candidato(eid, "memoria")

        out = self.dossie.painel(db_mod=self.db, temas=["Obesidade"])

        self.assertIn("Obesidade", out)
        titulos_corpus = [e["titulo"] for e in out["Obesidade"]["corpus"]]
        self.assertEqual(titulos_corpus, ["Fica na memória"])
        titulos_excluidos = [e["titulo"] for e in out["Obesidade"]["excluidos"]]
        self.assertEqual(titulos_excluidos, ["Sai da memória"])

    def test_corpus_nao_traz_abstract(self):
        """O ponto que mais importa: é o peso da consulta numa tela que carrega
        centenas de linhas por tema. Prova que a CHAVE está ausente, não só vazia."""
        self.db.salvar_candidatos([_cand("k1", "Estudo pesado",
                                         abstract="x" * 5000)])
        out = self.dossie.painel(db_mod=self.db, temas=["Obesidade"])
        item = out["Obesidade"]["corpus"][0]
        self.assertNotIn("abstract", item)
        self.assertEqual(set(item.keys()), {"id", "origem", "titulo", "fonte", "data"})

    def test_estudo_excluido_sai_do_corpus_e_aparece_em_excluidos(self):
        self.db.salvar_candidatos([_cand("k1", "Estudo fraco")])
        eid = next(c["id"] for c in self.db.listar_candidatos()
                  if c["titulo"] == "Estudo fraco")
        self.db.excluir_candidato(eid, "tudo")

        out = self.dossie.painel(db_mod=self.db, temas=["Obesidade"])

        self.assertEqual(out["Obesidade"]["corpus"], [])
        titulos_excluidos = [e["titulo"] for e in out["Obesidade"]["excluidos"]]
        self.assertEqual(titulos_excluidos, ["Estudo fraco"])

    def test_temas_explicito_e_respeitado_sem_ler_config_de_areas(self):
        """Passar `temas=[...]` não pode depender de `area_estudo.areas()` — o teste
        roda com uma lista que nem existe na config real."""
        self.db.salvar_candidatos([_cand("k1", "Estudo qualquer", tema="Tema Inventado")])
        out = self.dossie.painel(db_mod=self.db, temas=["Tema Inventado"])
        self.assertEqual(set(out.keys()), {"Tema Inventado"})
        titulos = [e["titulo"] for e in out["Tema Inventado"]["corpus"]]
        self.assertEqual(titulos, ["Estudo qualquer"])


class TestPaginaConfirmar(unittest.TestCase):
    def setUp(self):
        import site_web
        importlib.reload(site_web)
        self.sw = site_web
        self.estudo = {"id": "c1", "origem": "candidato", "titulo": "Estudo de verdade",
                       "fonte": "NEJM", "data": "2026-03-01"}

    def test_mostra_o_estudo_que_casou_e_os_dois_botoes(self):
        html = self.sw.pagina_confirmar_exclusao(self.estudo, "Obesidade", "tok")
        self.assertIn("Estudo de verdade", html)
        self.assertIn('value="memoria"', html)
        self.assertIn('value="tudo"', html)
        self.assertIn("c1", html)

    def test_tem_saida_sem_excluir(self):
        html = self.sw.pagina_confirmar_exclusao(self.estudo, "Obesidade", "tok")
        self.assertIn("Cancelar", html)

    def test_digest_nao_oferece_tirar_da_fila(self):
        est = {"id": "obesidade|2026-07-19", "origem": "digest", "titulo": "Enviado",
               "fonte": "NEJM", "data": "2026-07-19"}
        html = self.sw.pagina_confirmar_exclusao(est, "Obesidade", "tok")
        self.assertIn('value="memoria"', html)
        self.assertNotIn('value="tudo"', html)

    def test_devolve_pagina_completa_nao_fragmento(self):
        """A Task 10 serve isto direto como corpo da resposta HTTP — sem `_pagina(...)`
        o médico veria a tela de confirmação sem CSS, sem topbar e sem `<head>`, no meio
        do fluxo que existe justamente pra ele conferir com calma antes de excluir."""
        html = self.sw.pagina_confirmar_exclusao(self.estudo, "Obesidade", "tok")
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertIn("<head>", html)


import io
import shutil
import tempfile
import urllib.parse as _urlp


class _RouteStub:
    """Mesmo stub de test_cupom_toggle.py — path/headers/rfile + `_html`/`_redirect`,
    sem abrir socket."""

    def __init__(self, path, body=b""):
        self.path = path
        self.rfile = io.BytesIO(body)
        self.headers = {"Content-Length": str(len(body)),
                        "Content-Type": "application/x-www-form-urlencoded"}
        self.client_address = ("127.0.0.1", 0)

    def _html(self, s, code=200):
        return {"code": code, "body": s}

    def _redirect(self, location, token=None, clear=False):
        return {"redirect": location}

    def _sessao(self):
        return None


class TestRotasExclusao(unittest.TestCase):
    def setUp(self):
        self.snap = (os.environ.get("DSCURSO_ARTIGOS_DB"), os.environ.get("DATABASE_URL"),
                     os.environ.get("DSCURSO_ADMIN_TOKEN"))
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ.pop("DATABASE_URL", None)
        os.environ["DSCURSO_ADMIN_TOKEN"] = "tok123"
        import db, config, serve
        importlib.reload(db)
        importlib.reload(config)
        importlib.reload(serve)
        self.db, self.serve = db, serve
        self.db.init()
        self.db.salvar_candidatos([{
            "chave": "k1", "titulo": "Once-Weekly Semaglutide in Adults with Overweight",
            "tema": "Obesidade", "tipo": "varredura", "fonte": "NEJM",
            "data": "2026-03-01", "doi": "10.1/k1", "url": "",
            "abstract": "abs", "pergunta": "", "score": 8, "citacoes": 0, "tags": []}])
        self.cid = self.db.listar_candidatos()[0]["id"]

    def tearDown(self):
        a, d, t = self.snap
        for k, v in (("DSCURSO_ARTIGOS_DB", a), ("DATABASE_URL", d),
                     ("DSCURSO_ADMIN_TOKEN", t)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        import db, config
        importlib.reload(db)
        importlib.reload(config)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _post(self, campos):
        body = _urlp.urlencode(campos).encode("utf-8")
        return self.serve.Handler.do_POST(_RouteStub("/curadoria", body))

    def test_sem_token_403_e_nada_muda(self):
        r = self._post({"acao": "excluir_corpus", "origem": "candidato",
                        "ref": self.cid, "escopo": "tudo", "tema": "Obesidade"})
        self.assertEqual(r["code"], 403)
        self.assertEqual(len(self.db.listar_candidatos()), 1)

    def test_excluir_candidato_do_escopo_tudo(self):
        r = self._post({"token": "tok123", "acao": "excluir_corpus", "origem": "candidato",
                        "ref": self.cid, "escopo": "tudo", "tema": "Obesidade"})
        self.assertIn("redirect", r)
        self.assertEqual(self.db.listar_candidatos(), [])

    def test_devolver_traz_de_volta(self):
        self.db.excluir_candidato(self.cid, "tudo")
        self._post({"token": "tok123", "acao": "devolver_corpus", "origem": "candidato",
                    "ref": self.cid, "tema": "Obesidade"})
        self.assertEqual(len(self.db.listar_candidatos()), 1)

    def test_escopo_invalido_nao_derruba_a_rota(self):
        """Campo vindo do navegador é entrada não confiável."""
        r = self._post({"token": "tok123", "acao": "excluir_corpus", "origem": "candidato",
                        "ref": self.cid, "escopo": "sim", "tema": "Obesidade"})
        self.assertIn("redirect", r)
        self.assertEqual(len(self.db.listar_candidatos()), 1)

    def test_confirmar_com_titulo_que_casa_mostra_a_tela(self):
        r = self._post({"token": "tok123", "acao": "confirmar_exclusao",
                        "tema": "Obesidade",
                        "titulo": "Once-Weekly Semaglutide in Adults with Overweight"})
        self.assertEqual(r["code"], 200)
        self.assertIn("Tirar este estudo da memória?", r["body"])

    def test_confirmar_com_titulo_que_nao_casa_avisa_e_nao_exclui(self):
        """Falha aberta: fingir que excluiu é o pior resultado possível."""
        r = self._post({"token": "tok123", "acao": "confirmar_exclusao",
                        "tema": "Obesidade", "titulo": "Estudo que a IA inventou"})
        self.assertIn("redirect", r)
        self.assertIn("Estudos+lidos", r["redirect"].replace("%20", "+"))
        self.assertEqual(len(self.db.listar_candidatos()), 1)

    def test_refazer_tema_responde_sem_esperar_a_IA(self):
        """A reconstrução são ~10 chamadas Sonnet: a rota tem que devolver na hora e
        avisar no WhatsApp depois. E tem que pedir UM tema, não os cinco."""
        chamado = {}
        import dossie, deliver

        def _fake(temas=None, **k):
            chamado["temas"] = temas
            return {}

        dossie.reconstruir_todos = _fake
        deliver.enviar_curador = lambda msg: None     # sem rede no teste
        r = self._post({"token": "tok123", "acao": "refazer_dossie_tema",
                        "tema": "Obesidade"})
        self.assertIn("redirect", r)
        import time
        for _ in range(50):                     # a thread é daemon; espera curta
            if chamado:
                break
            time.sleep(0.02)
        self.assertEqual(chamado.get("temas"), ["Obesidade"])


if __name__ == "__main__":
    unittest.main()
