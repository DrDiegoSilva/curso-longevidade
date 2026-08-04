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


if __name__ == "__main__":
    unittest.main()
