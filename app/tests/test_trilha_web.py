"""Testes das rotas da trilha: página do assinante, '✅ fiz' e download. Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPaginaTrilha(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        for m in ("config", "db", "subscribers", "trilha", "site_web"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, subscribers, trilha, site_web
        for m in (config, db, subscribers, trilha, site_web):
            importlib.reload(m)
        subscribers._migrado = False
        db.init()
        self.cfg, self.db, self.subs, self.t, self.w = config, db, subscribers, trilha, site_web
        self.t.semear()

    def test_pagina_mostra_a_peca_e_o_botao(self):
        itens = [{"numero": 1, "titulo": "O custo real da sua hora", "feito": False,
                  "ferramenta_slug": ""}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens)
        self.assertIn("O custo real da sua hora", h)
        self.assertIn("fiz", h.lower())

    def test_peca_feita_nao_mostra_botao_de_novo(self):
        itens = [{"numero": 1, "titulo": "X", "feito": True, "ferramenta_slug": ""}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens)
        self.assertNotIn('value="marcar_feito"', h)

    def test_ferramenta_vira_link_de_download(self):
        itens = [{"numero": 1, "titulo": "X", "feito": False, "ferramenta_slug": "planilha-x"}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens)
        self.assertIn("/ferramentas/planilha-x", h)

    def test_escapa_titulo(self):
        itens = [{"numero": 1, "titulo": "<script>x</script>", "feito": False,
                  "ferramenta_slug": ""}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens)
        self.assertNotIn("<script>x", h)


class TestFerramentaSegura(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["DSCURSO_TRILHA_DIR"] = self.tmp
        for m in ("config", "db", "trilha"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, trilha
        for m in (config, db, trilha):
            importlib.reload(m)
        db.init()
        self.cfg, self.t = config, trilha
        os.makedirs(os.path.join(self.tmp, "ferramentas"), exist_ok=True)
        with open(os.path.join(self.tmp, "ferramentas", "planilha-x.csv"), "w") as f:
            f.write("a,b\n")

    def test_acha_a_ferramenta_existente(self):
        self.assertTrue(self.t.caminho_ferramenta("planilha-x"))

    def test_slug_inexistente_devolve_none(self):
        self.assertIsNone(self.t.caminho_ferramenta("nao-existe"))

    def test_path_traversal_e_barrado(self):
        for mau in ("../db.py", "..%2Fdb.py", "a/../../etc/passwd", "/etc/passwd",
                    "..", ".", "a\\..\\b"):
            self.assertIsNone(self.t.caminho_ferramenta(mau), f"passou: {mau}")


if __name__ == "__main__":
    unittest.main()
