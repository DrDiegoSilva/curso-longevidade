"""As telas da exclusão, na aba 🧠 Dossiê. Standalone:
python3 app/tests/test_excluir_corpus_ui.py"""
import importlib
import json
import os
import sys
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


if __name__ == "__main__":
    unittest.main()
