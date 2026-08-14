"""A tela do bloco editável (item 33, parte B). Standalone:
python3 app/tests/test_dossie_fixar_ui.py"""
import importlib
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _dossie_row(blocos, tema="Obesidade"):
    return {"tema": tema, "atualizado_em": "2026-08-13T10:00:00", "n_estudos": 3,
            "conteudo": json.dumps({"blocos": blocos}, ensure_ascii=False)}


def _bloco(afirmacao="GLP-1 reduz massa magra", bid="b1", fixado=False, editado_em=""):
    b = {"id": bid, "afirmacao": afirmacao,
         "estudos": [{"titulo": "Estudo A", "fonte": "NEJM", "data": "2026-03"}]}
    if fixado:
        b["fixado"] = True
        b["editado_em"] = editado_em or "2026-08-13T18:22:00"
    return b


class TestBlocoEditavel(unittest.TestCase):
    def setUp(self):
        import site_web
        importlib.reload(site_web)
        self.sw = site_web

    def test_bloco_ganha_form_de_editar_com_o_texto_atual(self):
        html = self.sw._dossie_html([_dossie_row([_bloco()])], None, token="tok")
        self.assertIn("editar_bloco", html)
        self.assertIn("GLP-1 reduz massa magra", html)
        self.assertIn("<textarea", html)

    def test_o_id_do_bloco_viaja_no_form(self):
        html = self.sw._dossie_html([_dossie_row([_bloco(bid="abc123")])], None, token="tok")
        self.assertIn("abc123", html)

    def test_bloco_fixado_mostra_o_marcador_e_a_data(self):
        html = self.sw._dossie_html(
            [_dossie_row([_bloco(fixado=True, editado_em="2026-08-13T18:22:00")])],
            None, token="tok")
        self.assertIn("📌", html)
        self.assertIn("2026-08-13", html)

    def test_bloco_fixado_oferece_soltar(self):
        html = self.sw._dossie_html([_dossie_row([_bloco(fixado=True)])], None, token="tok")
        self.assertIn("soltar_bloco", html)

    def test_bloco_solto_NAO_oferece_soltar(self):
        html = self.sw._dossie_html([_dossie_row([_bloco()])], None, token="tok")
        self.assertNotIn("soltar_bloco", html)

    def test_bloco_solto_nao_mostra_o_marcador(self):
        html = self.sw._dossie_html([_dossie_row([_bloco()])], None, token="tok")
        self.assertNotIn("📌", html)

    def test_escapa_a_afirmacao(self):
        html = self.sw._dossie_html(
            [_dossie_row([_bloco(afirmacao="<script>alert(1)</script>")])], None, token="tok")
        self.assertNotIn("<script>alert(1)</script>", html)

    def test_bloco_sem_id_nao_oferece_editar(self):
        """Dossiê antigo, gravado antes desta fatia: sem id não há como apontar o bloco.
        Melhor não oferecer do que oferecer um botão que erra o alvo."""
        b = {"afirmacao": "Sem id", "estudos": [{"titulo": "X", "fonte": "", "data": ""}]}
        html = self.sw._dossie_html([_dossie_row([b])], None, token="tok")
        self.assertIn("Sem id", html)
        self.assertNotIn("editar_bloco", html)

    def test_bloco_fixado_sem_id_nao_oferece_soltar(self):
        """Extra da revisão da Task 4: sem id não dá pra apontar o bloco — nem pra
        editar (já gateado) nem pra soltar. Sem este gate, o soltar apontaria pra um
        bloco_id vazio."""
        html = self.sw._dossie_html([_dossie_row([_bloco(bid="", fixado=True)])],
                                    None, token="tok")
        self.assertNotIn("soltar_bloco", html)

    def test_bloco_solto_nao_deixa_vao_vazio(self):
        """Extra cosmético: sem selo (bloco não fixado), a div não é emitida — senão
        sobra um espaço em branco em todo bloco não fixado."""
        html = self.sw._dossie_html([_dossie_row([_bloco()])], None, token="tok")
        self.assertNotIn('<div class="d"></div>', html)

    def test_estudo_excluido_num_bloco_fixado_nao_manda_refazer_o_dossie(self):
        """Achado da revisão final: dentro de um bloco fixado, 'refaça o dossiê (🧠) pra
        ver o efeito' é falso — a reconstrução NUNCA mexe em bloco fixado. O médico
        apertaria 🧠, esperaria minutos e gastaria IA à toa, e a afirmação voltaria igual."""
        painel = {"Obesidade": {"corpus": [], "excluidos": [
            {"titulo": "Estudo A", "fonte": "NEJM", "data": "2026-03",
             "origem": "candidato", "ref": "c1", "escopo": "memoria"}]}}
        html = self.sw._dossie_html([_dossie_row([_bloco(fixado=True)])], painel, token="tok")
        self.assertIn("line-through", html)
        self.assertNotIn("refaça o dossiê (🧠) pra ver o efeito nas afirmações", html)
        self.assertIn("este bloco é seu", html)

    def test_estudo_excluido_num_bloco_NAO_fixado_continua_mandando_refazer(self):
        """O texto antigo continua valendo pro caso comum, onde refazer de fato ajuda."""
        painel = {"Obesidade": {"corpus": [], "excluidos": [
            {"titulo": "Estudo A", "fonte": "NEJM", "data": "2026-03",
             "origem": "candidato", "ref": "c1", "escopo": "memoria"}]}}
        html = self.sw._dossie_html([_dossie_row([_bloco(fixado=False)])], painel, token="tok")
        self.assertIn("line-through", html)
        self.assertIn("refaça o dossiê (🧠) pra ver o efeito nas afirmações", html)
        self.assertNotIn("este bloco é seu", html)


import io
import shutil
import tempfile
import urllib.parse as _urlp


class _RouteStub:
    """Mesmo stub dos outros testes de rota — path/headers/rfile + `_html`/`_redirect`,
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


class TestRotasBloco(unittest.TestCase):
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
        self.db.salvar_dossie("Obesidade", {"blocos": [
            {"afirmacao": "Texto da IA",
             "estudos": [{"titulo": "Estudo A", "fonte": "NEJM", "data": "2026-03"}]}]}, 5)
        self.bid = self.db.blocos_do_dossie("Obesidade")[0]["id"]

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

    def _bloco(self):
        return self.db.blocos_do_dossie("Obesidade")[0]

    def test_sem_token_403_e_nada_muda(self):
        r = self._post({"acao": "editar_bloco", "tema": "Obesidade", "bloco": self.bid,
                        "afirmacao": "invadido"})
        self.assertEqual(r["code"], 403)
        self.assertEqual(self._bloco()["afirmacao"], "Texto da IA")

    def test_editar_persiste_e_fixa(self):
        r = self._post({"token": "tok123", "acao": "editar_bloco", "tema": "Obesidade",
                        "bloco": self.bid, "afirmacao": "Texto do Diego"})
        self.assertIn("redirect", r)
        self.assertEqual(self._bloco()["afirmacao"], "Texto do Diego")
        self.assertTrue(self._bloco().get("fixado"))

    def test_texto_vazio_avisa_e_nao_grava(self):
        """Falha aberta: sem a mensagem ele clica, nada acontece e não sabe por quê."""
        r = self._post({"token": "tok123", "acao": "editar_bloco", "tema": "Obesidade",
                        "bloco": self.bid, "afirmacao": "   "})
        self.assertIn("redirect", r)
        self.assertIn("vazia", r["redirect"].replace("%20", " ").replace("+", " ").lower())
        self.assertEqual(self._bloco()["afirmacao"], "Texto da IA")

    def test_bloco_inexistente_avisa(self):
        r = self._post({"token": "tok123", "acao": "editar_bloco", "tema": "Obesidade",
                        "bloco": "nao-existe", "afirmacao": "X"})
        self.assertIn("redirect", r)
        self.assertEqual(self._bloco()["afirmacao"], "Texto da IA")

    def test_soltar_pela_rota(self):
        self.db.dossie_editar_bloco("Obesidade", self.bid, "Texto do Diego")
        r = self._post({"token": "tok123", "acao": "soltar_bloco", "tema": "Obesidade",
                        "bloco": self.bid})
        self.assertIn("redirect", r)
        self.assertFalse(self._bloco().get("fixado"))

    def test_volta_para_a_aba_do_dossie(self):
        r = self._post({"token": "tok123", "acao": "editar_bloco", "tema": "Obesidade",
                        "bloco": self.bid, "afirmacao": "Texto do Diego"})
        self.assertIn("aba=dossie", r["redirect"])


if __name__ == "__main__":
    unittest.main()
