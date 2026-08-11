"""🔴 PERDA DE DADOS: "✅ Aprovar" jogava fora o texto editado.

Diego, 2026-08-11, sobre o estudo que saiu com o nome dele apesar de ter editado na
véspera: *"eu editei ontem a noite o texto, mas nao apertei regerar audio"*.

O ramo `aprovar` de `draft_store.aplicar` **não usava o parâmetro `texto`** — só o ramo
`editar` gravava. A tela tem UMA caixa de texto e dois botões que parecem salvar; quem
edita e clica no principal (Aprovar, a ação natural de quem está aprovando) perde a
edição **em silêncio**, e o texto original vai pros assinantes.

Nada quebrava, nada avisava, a suíte ficava verde. Só se descobre quando o resultado
errado já saiu. É o item 38 que o Diego levantou como "a ordem dos botões" — que eu
tinha classificado como polimento e era perda de dados.

Decisões dele (2026-08-11):
- Aprovar SALVA o texto.
- Depois de salvar, VOLTA pra tela com o texto (não uma página de confirmação separada).
- "Se não apertar aprovar quer dizer que está aprovado" — o envio automático das 08h já
  funciona assim; a TELA é que nunca disse isso.
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


def _rascunho(resumo="texto com Dr. Diego", status="DRAFT"):
    return {"data": "2026-08-11", "status": status, "review_token": "tok",
            "artigo": {"titulo": "T", "tema": "Obesidade", "fonte": "NEJM"},
            "resumo": resumo, "pdf_path": PREVIEW, "reserva_id": None}


class TestAprovarGravaOTexto(unittest.TestCase):
    def setUp(self):
        import draft_store
        importlib.reload(draft_store)
        self.ds = draft_store

    def _aplicar(self, r, acao, **kw):
        with mock.patch.object(self.ds, "carregar", return_value=r), \
             mock.patch.object(self.ds, "salvar") as m_salvar, \
             mock.patch("db.atualizar_reserva"):
            out = self.ds.aplicar("2026-08-11", acao, **kw)
        return out, m_salvar

    def test_aprovar_com_texto_novo_grava_o_texto(self):
        """O bug. Sem isto, editar + Aprovar manda o texto ORIGINAL pros assinantes."""
        r = _rascunho(resumo="texto com Dr. Diego")
        out, m_salvar = self._aplicar(r, "aprovar", texto="texto limpo")
        self.assertEqual(out["resumo"], "texto limpo")
        self.assertEqual(m_salvar.call_args[0][0]["resumo"], "texto limpo")
        self.assertEqual(out["status"], "APPROVED")

    def test_aprovar_com_texto_novo_invalida_o_pdf_velho(self):
        r = _rascunho()
        out, _ = self._aplicar(r, "aprovar", texto="texto limpo")
        self.assertEqual(out["pdf_path"], "")

    def test_aprovar_sem_mexer_no_texto_preserva_tudo(self):
        r = _rascunho(resumo="mesmo texto")
        out, _ = self._aplicar(r, "aprovar", texto="mesmo texto")
        self.assertEqual(out["resumo"], "mesmo texto")
        self.assertEqual(out["pdf_path"], PREVIEW)      # não paga Chromium à toa

    def test_aprovar_com_texto_vazio_nao_apaga_o_resumo(self):
        """Campo ausente (POST antigo/forjado) não pode zerar o estudo do dia."""
        r = _rascunho(resumo="texto bom")
        out, _ = self._aplicar(r, "aprovar", texto="")
        self.assertEqual(out["resumo"], "texto bom")

    def test_aprovar_sem_o_parametro_texto_continua_funcionando(self):
        r = _rascunho(resumo="texto bom")
        out, _ = self._aplicar(r, "aprovar")
        self.assertEqual(out["resumo"], "texto bom")
        self.assertEqual(out["status"], "APPROVED")

    def test_editar_continua_gravando_como_antes(self):
        r = _rascunho(resumo="velho")
        out, _ = self._aplicar(r, "editar", texto="novo")
        self.assertEqual((out["resumo"], out["status"]), ("novo", "EDITED"))

    def test_vetar_o_dia_nao_grava_texto(self):
        """Vetar não é hora de mexer no conteúdo — mesma regra da área."""
        r = _rascunho(resumo="original")
        out, _ = self._aplicar(r, "nao_enviar", texto="qualquer coisa")
        self.assertEqual(out["resumo"], "original")


class _RotaStub:
    def __init__(self, path, body=b""):
        self.path = path
        self.rfile = io.BytesIO(body)
        self.headers = {"Content-Length": str(len(body)),
                        "Content-Type": "application/x-www-form-urlencoded"}

    def _html(self, s, code=200):
        return {"code": code, "body": s}


class TestVoltaProTextoDepoisDeSalvar(unittest.TestCase):
    """Decisão do Diego: depois de salvar, voltar pra tela COM o texto — pra ele ver o
    resultado, poder continuar editando e conferir o PDF sem reabrir o link do WhatsApp."""

    def setUp(self):
        import serve
        self.serve = serve

    def _post(self, campos, r=None, salvo=None):
        r = r or _rascunho()
        with mock.patch("draft_store.por_token", return_value=r), \
             mock.patch("draft_store.aplicar", return_value=(salvo or r)):
            return self.serve.Handler.do_POST(
                _RotaStub("/revisar/tok", up.urlencode(campos).encode("utf-8")))["body"]

    def test_a_resposta_e_a_tela_de_revisao_e_nao_outra_pagina(self):
        html = self._post({"acao": "aprovar", "texto": "novo"})
        self.assertIn('name="texto"', html)              # a caixa de texto está lá
        self.assertIn('name="area"', html)

    def test_a_tela_mostra_o_texto_SALVO_e_nao_o_antigo(self):
        """Se mostrasse o antigo, o Diego acharia que a edição não pegou de novo."""
        html = self._post({"acao": "aprovar", "texto": "TEXTO LIMPO"},
                          salvo=_rascunho(resumo="TEXTO LIMPO"))
        self.assertIn("TEXTO LIMPO", html)

    def test_o_aviso_diz_qual_acao_aconteceu(self):
        aprovar = self._post({"acao": "aprovar", "texto": "x"})
        editar = self._post({"acao": "editar", "texto": "x"})
        vetar = self._post({"acao": "nao_enviar"})
        self.assertIn("Aprovado", aprovar)
        self.assertIn("salva", editar)
        self.assertIn("Vetado", vetar)
        self.assertNotEqual(aprovar, editar)

    def test_o_link_do_pdf_continua_na_tela(self):
        html = self._post({"acao": "aprovar", "texto": "x"})
        self.assertIn("/pdf/2026-08-11", html)

    def test_a_tela_avisa_que_nao_mexer_ja_significa_aprovado(self):
        """"Se não apertar aprovar quer dizer que está aprovado" — é como o envio das 08h
        já funciona, mas a tela nunca dizia, e isso gera insegurança na hora de fechar."""
        html = self._post({"acao": "aprovar", "texto": "x"})
        self.assertIn("08h", html)
        self.assertIn("automat", html.lower())

    def test_dia_ja_enviado_nao_promete_que_sai_as_08h(self):
        """Editar depois do envio não muda o que já saiu — a tela não pode mentir."""
        html = self._post({"acao": "editar", "texto": "x"},
                          r=_rascunho(status="SENT"), salvo=_rascunho(status="SENT"))
        self.assertIn("já foi enviado", html)


if __name__ == "__main__":
    unittest.main()
