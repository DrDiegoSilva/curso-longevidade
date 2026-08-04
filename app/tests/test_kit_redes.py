"""Parser e render do kit de redes (rodape do PDF). Standalone."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestParseGancho(unittest.TestCase):
    def setUp(self):
        import content
        self.c = content

    def test_json_novo_completo(self):
        bruto = ('{"frase": "Perdeu 20,9% do peso.",'
                 ' "reels": [{"angulo": "Nao e forca de vontade.", "apoio": "O comparador perdeu 3,1%."}]}')
        r = self.c.parse_gancho(bruto)
        self.assertEqual(r["frase"], "Perdeu 20,9% do peso.")
        self.assertEqual(len(r["reels"]), 1)
        self.assertEqual(r["reels"][0]["angulo"], "Nao e forca de vontade.")
        self.assertEqual(r["reels"][0]["apoio"], "O comparador perdeu 3,1%.")

    def test_texto_puro_antigo_vira_um_reel(self):
        """Formato legado: o banco de reserva/classicos esta cheio deles."""
        r = self.c.parse_gancho("Fale sobre obesidade como doenca cronica.")
        self.assertEqual(r["frase"], "")
        self.assertEqual(len(r["reels"]), 1)
        self.assertEqual(r["reels"][0]["angulo"], "Fale sobre obesidade como doenca cronica.")
        self.assertEqual(r["reels"][0]["apoio"], "")

    def test_vazio_nao_quebra(self):
        for entrada in ("", None, "   "):
            r = self.c.parse_gancho(entrada)
            self.assertEqual(r["frase"], "")
            self.assertEqual(r["reels"], [])

    def test_json_so_com_frase(self):
        r = self.c.parse_gancho('{"frase": "So a frase."}')
        self.assertEqual(r["frase"], "So a frase.")
        self.assertEqual(r["reels"], [])

    def test_item_sem_apoio(self):
        r = self.c.parse_gancho('{"reels": [{"angulo": "So o angulo."}]}')
        self.assertEqual(r["reels"][0]["apoio"], "")

    def test_corta_em_tres(self):
        """A IA vai extrapolar alguma hora; nao pode virar bloco gigante no PDF."""
        itens = ",".join('{"angulo": "a%d"}' % i for i in range(5))
        r = self.c.parse_gancho('{"reels": [%s]}' % itens)
        self.assertEqual(len(r["reels"]), 3)

    def test_item_sem_angulo_e_descartado(self):
        r = self.c.parse_gancho('{"reels": [{"apoio": "orfao"}, {"angulo": "bom"}]}')
        self.assertEqual(len(r["reels"]), 1)
        self.assertEqual(r["reels"][0]["angulo"], "bom")

    def test_nunca_imprime_none(self):
        r = self.c.parse_gancho('{"frase": null, "reels": [{"angulo": "x", "apoio": null}]}')
        self.assertEqual(r["frase"], "")
        self.assertEqual(r["reels"][0]["apoio"], "")


class TestKitHtml(unittest.TestCase):
    def setUp(self):
        import pdf
        self.pdf = pdf
        self.artigo = {"titulo_original": "Tirzepatide Once Weekly for Obesity",
                       "titulo": "Tirzepatida semanal para obesidade",
                       "fonte": "N Engl J Med", "data": "2022", "doi": "10.1056/NEJMoa2206038"}
        self.gancho = ('{"frase": "Perdeu 20,9% do peso em 72 semanas.",'
                       ' "reels": [{"angulo": "Nao e forca de vontade.", "apoio": "O comparador perdeu 3,1%."},'
                       '           {"angulo": "Nao acontece em um mes.", "apoio": "Foram 72 semanas."}]}')

    def test_mostra_titulo_original_em_ingles(self):
        html = self.pdf._kit_html(self.gancho, self.artigo)
        self.assertIn("Tirzepatide Once Weekly for Obesity", html)
        self.assertNotIn("Tirzepatida semanal", html)     # o pt fica no topo do PDF, nao aqui

    def test_cai_para_titulo_quando_nao_ha_original(self):
        art = dict(self.artigo)
        del art["titulo_original"]
        html = self.pdf._kit_html(self.gancho, art)
        self.assertIn("Tirzepatida semanal para obesidade", html)

    def test_mostra_frase_e_os_reels(self):
        html = self.pdf._kit_html(self.gancho, self.artigo)
        self.assertIn("Perdeu 20,9% do peso em 72 semanas.", html)
        self.assertIn("Nao e forca de vontade.", html)
        self.assertIn("Nao acontece em um mes.", html)
        self.assertIn("O comparador perdeu 3,1%.", html)

    def test_um_reel_so_renderiza_igual_bem(self):
        """Caso ESPERADO agora (o prompt prefere menos): nao pode sobrar item vazio."""
        html = self.pdf._kit_html('{"reels": [{"angulo": "Unico."}]}', self.artigo)
        self.assertEqual(html.count('class="reel"'), 1)
        self.assertNotIn("None", html)

    def test_texto_legado_nao_quebra(self):
        html = self.pdf._kit_html("Fale sobre obesidade como doenca cronica.", self.artigo)
        self.assertIn("Fale sobre obesidade como doenca cronica.", html)
        self.assertNotIn("None", html)

    def test_gancho_vazio_ainda_mostra_o_cartao_do_estudo(self):
        """O recorte do paper vale por si so, mesmo sem texto de IA."""
        html = self.pdf._kit_html("", self.artigo)
        self.assertIn("Tirzepatide Once Weekly for Obesity", html)

    def test_sem_gancho_e_sem_estudo_devolve_vazio(self):
        self.assertEqual(self.pdf._kit_html("", {}), "")

    def test_escapa_html_do_conteudo(self):
        art = dict(self.artigo, titulo_original="A <script>alert(1)</script> B")
        html = self.pdf._kit_html("", art)
        self.assertNotIn("<script>", html)


if __name__ == "__main__":
    unittest.main()
