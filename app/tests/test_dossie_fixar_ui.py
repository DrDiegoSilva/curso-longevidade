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


if __name__ == "__main__":
    unittest.main()
