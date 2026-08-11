"""Salvar uma edição na tela das 18h era um beco sem saída, e o PDF mentia.

Diego, 2026-08-10: *"eu fiz uma alteração e salvei a alteração, depois não consigo ver
como fica o pdf?"*.

Dois bugs independentes:
1. O POST respondia `<h3>Feito ✅ Pode fechar.</h3>` — sem link pro PDF nem de volta pra
   revisão. A única saída era reabrir o link antigo do WhatsApp.
2. Editar o texto NÃO invalidava o PDF de prévia gerado às 18h, então o "Ver PDF"
   devolvia a versão velha. Intermitente (o `/data` é apagado a cada deploy, e aí
   regenerava certo) — o que é pior que quebrado sempre, porque não dá pra confiar.
"""
import importlib
import io
import os
import sys
import tempfile
import unittest
import urllib.parse as up
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DSCURSO_DATA", tempfile.mkdtemp())

PREVIEW = "/data/drafts/2026-08-11-preview.pdf"


def _rascunho(tema="Obesidade", resumo="texto velho"):
    return {"data": "2026-08-11", "status": "DRAFT", "review_token": "tok",
            "artigo": {"titulo": "T", "tema": tema, "fonte": "NEJM"},
            "resumo": resumo, "pdf_path": PREVIEW, "reserva_id": None}


class TestEditarInvalidaOPdf(unittest.TestCase):
    def setUp(self):
        import draft_store
        importlib.reload(draft_store)
        self.ds = draft_store

    def _aplicar(self, r, acao, **kw):
        with mock.patch.object(self.ds, "carregar", return_value=r), \
             mock.patch.object(self.ds, "salvar"), mock.patch("db.atualizar_reserva"):
            return self.ds.aplicar("2026-08-11", acao, **kw)

    def test_editar_o_texto_joga_fora_o_pdf_velho(self):
        r = _rascunho(resumo="texto velho")
        out = self._aplicar(r, "editar", texto="texto NOVO")
        self.assertEqual(out["resumo"], "texto NOVO")
        self.assertEqual(out["pdf_path"], "")      # regenera sob demanda com o texto novo

    def test_salvar_sem_mudar_o_texto_preserva_o_pdf(self):
        """Não pode pagar um Chromium por um salvar que não mudou nada."""
        r = _rascunho(resumo="mesmo texto")
        out = self._aplicar(r, "editar", texto="mesmo texto")
        self.assertEqual(out["pdf_path"], PREVIEW)

    def test_texto_vazio_nao_apaga_o_resumo_nem_o_pdf(self):
        """`texto or r['resumo']` já protegia o resumo; o PDF tem que seguir a mesma regra."""
        r = _rascunho(resumo="texto velho")
        out = self._aplicar(r, "editar", texto="")
        self.assertEqual(out["resumo"], "texto velho")
        self.assertEqual(out["pdf_path"], PREVIEW)

    def test_aprovar_sem_editar_preserva_o_pdf(self):
        r = _rascunho()
        self.assertEqual(self._aplicar(r, "aprovar")["pdf_path"], PREVIEW)

    def test_mudar_area_E_texto_invalida_uma_vez_so(self):
        r = _rascunho(tema="Meus estudos", resumo="velho")
        out = self._aplicar(r, "editar", texto="novo", area="Obesidade")
        self.assertEqual(out["artigo"]["tema"], "Obesidade")
        self.assertEqual(out["resumo"], "novo")
        self.assertEqual(out["pdf_path"], "")


class _RotaStub:
    def __init__(self, path, body=b""):
        self.path = path
        self.rfile = io.BytesIO(body)
        self.headers = {"Content-Length": str(len(body)),
                        "Content-Type": "application/x-www-form-urlencoded"}

    def _html(self, s, code=200):
        return {"code": code, "body": s}


class TestTelaDepoisDeSalvar(unittest.TestCase):
    """O beco sem saída: depois de salvar tem que dar pra VER o PDF e VOLTAR."""

    def setUp(self):
        import serve
        self.serve = serve

    def _post(self, campos, r):
        with mock.patch("draft_store.por_token", return_value=r), \
             mock.patch("draft_store.aplicar", return_value=r):
            return self.serve.Handler.do_POST(
                _RotaStub("/revisar/tok", up.urlencode(campos).encode("utf-8")))

    def test_salvar_edicao_oferece_o_pdf_e_a_volta(self):
        out = self._post({"acao": "editar", "texto": "novo"}, _rascunho())
        self.assertIn("/pdf/2026-08-11", out["body"])
        self.assertIn("/revisar/tok", out["body"])
        # URL presente não basta: âncora sem texto é link que ninguém consegue clicar.
        volta = out["body"].split('href="/revisar/tok"', 1)[1].split("</a>", 1)[0]
        self.assertIn("Voltar", volta)

    def test_aprovar_tambem_oferece_o_pdf(self):
        """Aprovar é o fim do fluxo, mas conferir a capa depois de aprovar é legítimo."""
        out = self._post({"acao": "aprovar"}, _rascunho())
        self.assertIn("/pdf/2026-08-11", out["body"])

    def test_diz_o_que_foi_feito_em_vez_de_so_Feito(self):
        editar = self._post({"acao": "editar", "texto": "n"}, _rascunho())["body"]
        aprovar = self._post({"acao": "aprovar"}, _rascunho())["body"]
        vetar = self._post({"acao": "nao_enviar"}, _rascunho())["body"]
        self.assertNotEqual(editar, aprovar)
        self.assertNotEqual(aprovar, vetar)

    def test_vetar_o_dia_nao_oferece_pdf(self):
        """Não faz sentido mandar conferir a capa de um estudo que não vai sair."""
        out = self._post({"acao": "nao_enviar"}, _rascunho())
        self.assertNotIn("/pdf/", out["body"])

    def test_o_link_do_pdf_abre_em_aba_nova(self):
        """Sem isso, ver o PDF ABANDONA a tela de revisão — o beco sem saída de novo."""
        out = self._post({"acao": "editar", "texto": "n"}, _rascunho())
        pedaco = out["body"].split("/pdf/", 1)[1][:120]
        self.assertIn("_blank", pedaco)


if __name__ == "__main__":
    unittest.main()
