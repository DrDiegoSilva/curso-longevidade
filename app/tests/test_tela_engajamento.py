"""Tela de engajamento (quem lê o que a gente manda) -- pedido do Diego (2026-09-25).
Testa a função de renderização e a rota /admin/engajamento via stub, mesmo padrão de
test_admin_precos.py / test_tela_custos.py. Standalone."""
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPaginaAdminEngajamento(unittest.TestCase):
    def setUp(self):
        import importlib, site_web
        importlib.reload(site_web)
        self.sw = site_web

    def _linhas(self):
        return [
            {"nome": "Ana", "enviado": 0, "entregue": 0, "lida": 8, "reproduzida": 2},
            {"nome": "Beto", "enviado": 3, "entregue": 0, "lida": 0, "reproduzida": 0},
        ]

    def test_devolve_pagina_completa(self):
        html = self.sw.pagina_admin_engajamento(self._linhas(), "tok")
        self.assertTrue(html.lstrip().lower().startswith("<!doctype html>"))

    def test_lista_os_assinantes(self):
        html = self.sw.pagina_admin_engajamento(self._linhas(), "tok")
        self.assertIn("Ana", html)
        self.assertIn("Beto", html)

    def test_calcula_percentual_por_assinante(self):
        # Ana: 10 enviadas (0+0+8+2), 10 lidas (8+2) -> 100%. Beto: 3 enviadas, 0 lidas -> 0%.
        html = self.sw.pagina_admin_engajamento(self._linhas(), "tok")
        self.assertIn("100%", html)
        self.assertIn("0%", html)

    def test_percentual_geral_agrega_todo_mundo(self):
        # total enviado = 10 + 3 = 13; total lido = 10 -> 77%
        html = self.sw.pagina_admin_engajamento(self._linhas(), "tok")
        self.assertIn("77%", html)

    def test_lista_vazia_nao_quebra(self):
        html = self.sw.pagina_admin_engajamento([], "tok")
        self.assertIn("Sem mensagens rastreadas", html)

    def test_escapa_nome(self):
        linhas = [{"nome": "<script>x</script>", "enviado": 1, "entregue": 0, "lida": 0, "reproduzida": 0}]
        html = self.sw.pagina_admin_engajamento(linhas, "tok")
        self.assertNotIn("<script>x", html)

    def test_deixa_claro_que_lida_nao_e_pdf_aberto(self):
        html = self.sw.pagina_admin_engajamento(self._linhas(), "tok")
        self.assertIn("não confirma que o PDF foi aberto", html)


class _RouteStub:
    def __init__(self, path):
        self.path = path

    def _html(self, s, code=200):
        return {"code": code, "body": s}

    def _sessao(self):
        return None


class TestRotaAdminEngajamento(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ADMIN_TOKEN"] = "tok123"
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import importlib, config, db, serve, subscribers
        for m in (config, db, serve, subscribers):
            importlib.reload(m)
        self.cfg, self.db, self.serve, self.subs = config, db, serve, subscribers
        self.db.init()

    def _get(self, qs=""):
        stub = _RouteStub("/admin/engajamento" + (f"?{qs}" if qs else ""))
        return self.serve.Handler.do_GET(stub)

    def test_sem_token_403(self):
        r = self._get()
        self.assertEqual(r["code"], 403)

    def test_com_token_mostra_pagina(self):
        r = self._get("token=tok123")
        self.assertEqual(r["code"], 200)
        self.assertIn("Engajamento", r["body"])

    def test_agrega_por_nome_do_assinante(self):
        reg = self.subs.adicionar("Carla", "5543999990000")
        self.db.registrar_mensagem_enviada("M1", reg["id"], "estudo_texto")
        self.db.atualizar_status_mensagem("M1", "lida")
        r = self._get("token=tok123")
        self.assertIn("CARLA", r["body"])   # subscribers.por_id guarda o nome em maiúsculas


if __name__ == "__main__":
    unittest.main()
