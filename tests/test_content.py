import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import content


class TestContent(unittest.TestCase):
    def test_parse_grafico_ok(self):
        g = content._parse_grafico('{"titulo":"Peso","unidade":"%","barras":[{"rotulo":"A","valor":20.9},{"rotulo":"B","valor":3.1}]}')
        self.assertEqual(g["titulo"], "Peso")
        self.assertEqual(len(g["barras"]), 2)
        self.assertEqual(g["barras"][0]["valor"], 20.9)

    def test_parse_grafico_null(self):
        self.assertIsNone(content._parse_grafico("null"))
        self.assertIsNone(content._parse_grafico(""))
        self.assertIsNone(content._parse_grafico("texto sem json"))

    def test_parse_grafico_descarta_barra_sem_numero(self):
        self.assertIsNone(content._parse_grafico('{"barras":[{"rotulo":"A","valor":"muito"}]}'))

    def test_gerar_conteudo_monta_tudo(self):
        art = {"titulo": "T", "fonte": "NEJM", "resumo": "..."}
        out = content.gerar_conteudo(
            art,
            gerar_resumo=lambda a: "resumo clínico",
            gerar_gancho=lambda a: "📣 dica pras redes",
            gerar_grafico_json=lambda a: '{"titulo":"X","barras":[{"rotulo":"A","valor":5}]}',
            gerar_titulo=lambda a: '"Título em Português"',
        )
        self.assertEqual(out["titulo_pt"], "Título em Português")  # aspas removidas
        self.assertEqual(out["resumo"], "resumo clínico")
        self.assertIn("dica", out["gancho"])
        self.assertEqual(out["grafico"]["barras"][0]["valor"], 5)


if __name__ == "__main__":
    unittest.main()
