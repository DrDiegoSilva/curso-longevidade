import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import pdf


class TestPdfHtml(unittest.TestCase):
    def test_html_contem_dados_e_nome(self):
        art = {"titulo": "Tirzepatida X", "fonte": "NEJM", "doi": "10.1/a",
               "url": "https://doi.org/10.1/a", "data": "2026-07"}
        html = pdf.montar_html(art, "Achado principal: reducao de peso", "Dr. Fulano")
        self.assertIn("Tirzepatida X", html)
        self.assertIn("NEJM", html)
        self.assertIn("Dr. Fulano", html)   # marca d'água / personalização
        self.assertIn("10.1/a", html)        # referência/DOI
        self.assertTrue(html.strip().lower().startswith("<!doctype html"))

    def test_html_escapa_injecao(self):
        art = {"titulo": "<script>x</script>", "fonte": "", "doi": "", "url": "", "data": ""}
        html = pdf.montar_html(art, "corpo", "Dr. <b>Ana</b>")
        self.assertNotIn("<script>x</script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&lt;b&gt;Ana", html)


if __name__ == "__main__":
    unittest.main()
