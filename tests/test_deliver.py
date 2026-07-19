import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import deliver


class TestDeliver(unittest.TestCase):
    def test_personalizar_rodape(self):
        out = deliver.personalizar_rodape("corpo", "Dra. Ana", "https://x/minha/abc")
        self.assertIn("corpo", out)
        self.assertIn("Dra. Ana", out)
        self.assertIn("https://x/minha/abc", out)

    def test_distribuir_conta_ok_e_falhas(self):
        assinantes = [{"whatsapp": "111", "nome": "A"}, {"whatsapp": "222", "nome": "B"}]
        chamadas = []

        def fake(w, nome):
            chamadas.append(w)
            if w == "222":
                raise RuntimeError("z-api caiu")

        r = deliver.distribuir({"resumo": "x"}, assinantes, 0, fake)
        self.assertEqual(r["ok"], 1)
        self.assertEqual(len(r["falhas"]), 1)
        self.assertEqual(r["falhas"][0]["whatsapp"], "222")
        self.assertEqual(chamadas, ["111", "222"])


if __name__ == "__main__":
    unittest.main()
