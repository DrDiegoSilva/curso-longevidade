"""O kit de marketing vira editável na tela das 18h.

Diego, 2026-08-11: *"eu não consigo editar a parte do mkt pq não aparece no texto né?
ele é gerado direto no pdf"*. Está certo — a tela só tinha UMA caixa (o resumo clínico).
O kit (frase, bloco do paciente, limites, pautas de Reels com roteiro) mora no campo
`gancho` em JSON e ia direto pro PDF do assinante sem passar por ele.

Mesma família dos consertos de hoje: a tela mostrava menos do que o sistema publica.

Ele escolheu editar TUDO (e não só o bloco do paciente). Riscos que os testes fixam:
- campo ausente/vazio NÃO pode apagar o kit (POST antigo, forjado, ou JS desligado);
- mexer no kit invalida o PDF de prévia, senão o "Ver PDF" mostra a versão velha;
- o kit viaja com APROVAR — foi exatamente o que se perdeu hoje com o texto.
"""
import importlib
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.parse as up
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DSCURSO_DATA", tempfile.mkdtemp())

PREVIEW = "/data/drafts/2026-08-11-preview.pdf"

KIT = {"frase": "A frase do achado", "paciente": "Explico assim no consultório",
       "limites": ["amostra pequena", "só 12 semanas"],
       "reels": [{"titulo": "Pauta 1", "gancho": "Você sabia?",
                  "roteiro": ["passo a", "passo b"], "apoio": "NEJM 2026"}]}


def _form(**over):
    campos = {"kit_frase": ["A frase do achado"],
              "kit_paciente": ["Explico assim no consultório"],
              "kit_limites": ["amostra pequena\nsó 12 semanas"],
              "kit_reel_titulo": ["Pauta 1"], "kit_reel_gancho": ["Você sabia?"],
              "kit_reel_roteiro": ["passo a\npasso b"], "kit_reel_apoio": ["NEJM 2026"]}
    campos.update(over)
    return campos


def _rascunho(gancho=None):
    return {"data": "2026-08-11", "status": "DRAFT", "review_token": "tok",
            "artigo": {"titulo": "T", "tema": "Obesidade", "fonte": "NEJM"},
            "resumo": "resumo", "gancho": json.dumps(gancho or KIT, ensure_ascii=False),
            "pdf_path": PREVIEW, "reserva_id": None}


class TestLerDoFormulario(unittest.TestCase):
    def setUp(self):
        import content
        importlib.reload(content)
        self.c = content

    def test_remonta_o_kit_inteiro(self):
        k = self.c.kit_do_form(_form())
        self.assertEqual(k["frase"], "A frase do achado")
        self.assertEqual(k["paciente"], "Explico assim no consultório")
        self.assertEqual(k["limites"], ["amostra pequena", "só 12 semanas"])
        self.assertEqual(k["reels"][0]["roteiro"], ["passo a", "passo b"])

    def test_varias_pautas_nao_se_embaralham(self):
        k = self.c.kit_do_form(_form(
            kit_reel_titulo=["P1", "P2"], kit_reel_gancho=["G1", "G2"],
            kit_reel_roteiro=["a\nb", "c"], kit_reel_apoio=["A1", "A2"]))
        self.assertEqual([r["titulo"] for r in k["reels"]], ["P1", "P2"])
        self.assertEqual(k["reels"][1]["gancho"], "G2")
        self.assertEqual(k["reels"][1]["roteiro"], ["c"])

    def test_pauta_com_titulo_apagado_e_removida(self):
        """É assim que ele tira uma pauta que não presta: apaga o título."""
        k = self.c.kit_do_form(_form(
            kit_reel_titulo=["P1", ""], kit_reel_gancho=["G1", "G2"],
            kit_reel_roteiro=["a", "b"], kit_reel_apoio=["", ""]))
        self.assertEqual(len(k["reels"]), 1)

    def test_linhas_em_branco_no_roteiro_somem(self):
        k = self.c.kit_do_form(_form(kit_reel_roteiro=["passo a\n\n  \npasso b"]))
        self.assertEqual(k["reels"][0]["roteiro"], ["passo a", "passo b"])

    def test_formulario_SEM_campos_de_kit_devolve_None(self):
        """POST antigo/forjado ou JS fora: não pode APAGAR o kit por omissão."""
        self.assertIsNone(self.c.kit_do_form({"texto": ["x"], "acao": ["aprovar"]}))

    def test_campos_presentes_e_vazios_devolvem_kit_vazio_de_verdade(self):
        """Diferente do caso acima: aqui ele apagou tudo de propósito."""
        k = self.c.kit_do_form({"kit_frase": [""], "kit_paciente": [""],
                                "kit_limites": [""], "kit_reel_titulo": [""]})
        self.assertEqual(k, {"frase": "", "paciente": "", "limites": [], "reels": []})


class TestGravarNoRascunho(unittest.TestCase):
    def setUp(self):
        import draft_store
        importlib.reload(draft_store)
        self.ds = draft_store

    def _aplicar(self, r, acao, **kw):
        with mock.patch.object(self.ds, "carregar", return_value=r), \
             mock.patch.object(self.ds, "salvar"), mock.patch("db.atualizar_reserva"):
            return self.ds.aplicar("2026-08-11", acao, **kw)

    def test_APROVAR_grava_o_kit(self):
        """A lição de hoje: Aprovar jogava o texto editado fora. Não repetir com o kit."""
        r = _rascunho()
        novo = dict(KIT, paciente="Fala nova do consultório")
        out = self._aplicar(r, "aprovar", kit=novo)
        self.assertIn("Fala nova do consultório", out["gancho"])
        self.assertEqual(out["status"], "APPROVED")

    def test_editar_tambem_grava(self):
        out = self._aplicar(_rascunho(), "editar", texto="t",
                            kit=dict(KIT, frase="Frase nova"))
        self.assertIn("Frase nova", out["gancho"])

    def test_kit_None_nao_toca_no_que_existia(self):
        r = _rascunho()
        antes = r["gancho"]
        self.assertEqual(self._aplicar(r, "aprovar", kit=None)["gancho"], antes)

    def test_mexer_no_kit_invalida_o_pdf_velho(self):
        out = self._aplicar(_rascunho(), "aprovar", kit=dict(KIT, frase="outra"))
        self.assertEqual(out["pdf_path"], "")

    def test_kit_igual_preserva_o_pdf(self):
        """Aprovar sem mexer no kit não pode pagar um Chromium à toa."""
        out = self._aplicar(_rascunho(), "aprovar", kit=dict(KIT))
        self.assertEqual(out["pdf_path"], PREVIEW)

    def test_vetar_o_dia_nao_grava_kit(self):
        r = _rascunho()
        antes = r["gancho"]
        self.assertEqual(self._aplicar(r, "nao_enviar", kit=dict(KIT, frase="x"))["gancho"],
                         antes)


class TestTela(unittest.TestCase):
    def setUp(self):
        import review_web
        importlib.reload(review_web)
        self.rw = review_web

    def test_a_tela_traz_os_campos_do_kit(self):
        html = self.rw.pagina_revisao(_rascunho())
        for campo in ("kit_frase", "kit_paciente", "kit_limites",
                      "kit_reel_titulo", "kit_reel_gancho", "kit_reel_roteiro"):
            self.assertIn(f'name="{campo}"', html)

    def test_os_campos_vem_preenchidos_com_o_kit_atual(self):
        html = self.rw.pagina_revisao(_rascunho())
        self.assertIn("Explico assim no consultório", html)
        self.assertIn("Você sabia?", html)
        self.assertIn("passo a", html)

    def test_os_campos_estao_DENTRO_do_form(self):
        """Fora do <form> não são postados e a edição some sem avisar."""
        html = self.rw.pagina_revisao(_rascunho())
        corpo = html.split("<form", 1)[1].split("</form>", 1)[0]
        self.assertIn('name="kit_paciente"', corpo)

    def test_estudo_sem_kit_nao_quebra_a_tela(self):
        html = self.rw.pagina_revisao(_rascunho(gancho={}))
        self.assertIn("Aprovar", html)

    def test_escapa_o_conteudo_do_kit(self):
        html = self.rw.pagina_revisao(_rascunho(dict(KIT, frase='x"><script>alert(1)</script>')))
        self.assertNotIn("<script>alert(1)</script>", html)


class _RotaStub:
    def __init__(self, path, body=b""):
        self.path = path
        self.rfile = io.BytesIO(body)
        self.headers = {"Content-Length": str(len(body)),
                        "Content-Type": "application/x-www-form-urlencoded"}

    def _html(self, s, code=200):
        return {"code": code, "body": s}


class TestFiacao(unittest.TestCase):
    """Sem isto, um nome de campo errado passa em todos os testes de unidade e a edição
    do kit simplesmente não chega no rascunho."""

    def test_o_kit_do_formulario_chega_no_draft_store(self):
        import serve
        campos = _form(acao=["aprovar"], texto=["t"])
        body = up.urlencode(campos, doseq=True).encode("utf-8")
        with mock.patch("draft_store.por_token", return_value=_rascunho()), \
             mock.patch("draft_store.aplicar", return_value=_rascunho()) as m:
            serve.Handler.do_POST(_RotaStub("/revisar/tok", body))
        kit = m.call_args.kwargs.get("kit")
        self.assertIsNotNone(kit, "o kit não chegou no draft_store")
        self.assertEqual(kit["paciente"], "Explico assim no consultório")


if __name__ == "__main__":
    unittest.main()


class TestCamposDeFraseQuebramLinha(unittest.TestCase):
    """Diego, 2026-08-11: *"faz o campo de titulo com scroll pra baixo e nao lateral"*.

    Título, frase do achado e gancho guardam FRASES — num `<input>` de uma linha só, o
    texto rola pro lado e fica ilegível (pior ainda no celular). Viram `<textarea>`.

    O que isso cria: `textarea` aceita Enter. Um título com quebra de linha estragaria a
    diagramação do PDF, então esses campos normalizam o espaço em branco na volta.
    """

    def setUp(self):
        import content
        import review_web
        importlib.reload(content)
        importlib.reload(review_web)
        self.c, self.rw = content, review_web

    def _campo(self, html, nome):
        i = html.find(f'name="{nome}"')
        self.assertGreater(i, 0, f"campo {nome} não está na tela")
        return html[html.rfind("<", 0, i):i]

    def test_titulo_frase_e_gancho_sao_caixas_que_quebram_linha(self):
        html = self.rw.pagina_revisao(_rascunho())
        for nome in ("kit_frase", "kit_reel_titulo", "kit_reel_gancho"):
            with self.subTest(campo=nome):
                self.assertIn("textarea", self._campo(html, nome))

    def test_o_valor_atual_aparece_dentro_da_caixa(self):
        """`<input value=...>` vira conteúdo do `<textarea>` — trocar a tag sem trocar
        isso deixaria os campos VAZIOS na tela, e ele perderia o kit ao aprovar."""
        html = self.rw.pagina_revisao(_rascunho())
        self.assertIn(">A frase do achado</textarea>", html)
        self.assertIn(">Pauta 1</textarea>", html)
        self.assertIn(">Você sabia?</textarea>", html)

    def test_enter_no_titulo_nao_vira_quebra_de_linha_no_kit(self):
        k = self.c.kit_do_form(_form(kit_reel_titulo=["Pauta\ncom enter"],
                                     kit_frase=["Frase\nquebrada"],
                                     kit_reel_gancho=["Gancho\nquebrado"]))
        self.assertEqual(k["reels"][0]["titulo"], "Pauta com enter")
        self.assertEqual(k["frase"], "Frase quebrada")
        self.assertEqual(k["reels"][0]["gancho"], "Gancho quebrado")

    def test_espaco_repetido_tambem_e_normalizado(self):
        k = self.c.kit_do_form(_form(kit_frase=["  Frase    com   espaco  "]))
        self.assertEqual(k["frase"], "Frase com espaco")

    def test_o_roteiro_CONTINUA_uma_linha_por_passo(self):
        """A normalização não pode vazar pro roteiro, onde a quebra é o separador."""
        k = self.c.kit_do_form(_form(kit_reel_roteiro=["passo a\npasso b"]))
        self.assertEqual(k["reels"][0]["roteiro"], ["passo a", "passo b"])

    def test_os_limites_CONTINUAM_um_por_linha(self):
        k = self.c.kit_do_form(_form(kit_limites=["limite 1\nlimite 2"]))
        self.assertEqual(k["limites"], ["limite 1", "limite 2"])
