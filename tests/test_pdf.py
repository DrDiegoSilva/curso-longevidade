import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import pdf

TEMA = {"rotulo": "Obesidade", "emoji": "⚖️", "cor": "#14332a"}


class TestPdfHtml(unittest.TestCase):
    def _art(self):
        return {"titulo": "Tirzepatida X", "fonte": "NEJM", "doi": "10.1/a",
                "url": "https://doi.org/10.1/a", "data": "2026-07", "tema": "Obesidade"}

    def test_html_completo(self):
        conteudo = {
            "resumo": "💡 *Em resumo*\nPerda de peso robusta.",
            "gancho": "📣 Fale com seus pacientes sobre gordura vs músculo.",
            "grafico": {"titulo": "Peso (%)", "unidade": "%", "barras": [
                {"rotulo": "Tirzepatida", "valor": 20.9}, {"rotulo": "Placebo", "valor": 3.1}]},
        }
        h = pdf.montar_html(self._art(), conteudo, "Dr. Fulano", TEMA)
        self.assertIn("Tirzepatida X", h)          # título
        self.assertIn("NEJM", h)                    # fonte
        self.assertIn("Dr. Fulano", h)              # marca d'água
        self.assertIn("10.1/a", h)                  # DOI
        self.assertIn("Obesidade", h)               # tag do tema
        self.assertIn("<strong>Em resumo</strong>", h)   # *bold* convertido
        self.assertIn("seus pacientes", h)          # gancho
        self.assertIn("Tirzepatida", h)             # barra do gráfico
        self.assertIn("#14332a", h)                 # cor do tema na capa
        self.assertTrue(h.strip().lower().startswith("<!doctype html"))

    def test_resumo_escapa_e_converte_bold(self):
        out = pdf._resumo_html("*forte* e <script>")
        self.assertIn("<strong>forte</strong>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_grafico_none_vazio(self):
        self.assertEqual(pdf._grafico_html(None), "")
        self.assertEqual(pdf._grafico_html({"barras": []}), "")

    def test_gancho_none_vazio(self):
        self.assertEqual(pdf._gancho_html(""), "")


if __name__ == "__main__":
    unittest.main()
