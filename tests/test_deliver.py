import sys, os, tempfile, base64, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import deliver


class TestDeliver(unittest.TestCase):
    def test_personalizar_rodape(self):
        out = deliver.personalizar_rodape("corpo", "Dra. Ana", "https://x/minha/abc")
        self.assertIn("corpo", out)
        self.assertIn("Dra. Ana", out)
        self.assertIn("https://x/minha/abc", out)

    def test_evolution_texto_payload(self):
        p = deliver._evolution_texto_payload("5543999990000", "oi")
        self.assertEqual(p, {"number": "5543999990000", "text": "oi"})

    def test_evolution_media_payload_base64(self):
        with tempfile.NamedTemporaryFile("wb", suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 conteudo")
            path = f.name
        try:
            p = deliver._evolution_media_payload("5543", path, "Meu Título! @2026")
            self.assertEqual(p["number"], "5543")
            self.assertEqual(p["mediatype"], "document")
            self.assertEqual(base64.b64decode(p["media"]), b"%PDF-1.4 conteudo")
            self.assertTrue(p["fileName"].endswith(".pdf"))
            self.assertNotIn(" ", p["fileName"])  # nome de arquivo sanitizado
        finally:
            os.unlink(path)

    def test_distribuir_conta_ok_e_falhas(self):
        assinantes = [{"whatsapp": "111", "nome": "A"}, {"whatsapp": "222", "nome": "B"}]
        chamadas = []

        def fake(w, nome):
            chamadas.append(w)
            if w == "222":
                raise RuntimeError("caiu")

        r = deliver.distribuir({}, assinantes, 0, fake)
        self.assertEqual(r["ok"], 1)
        self.assertEqual(len(r["falhas"]), 1)
        self.assertEqual(chamadas, ["111", "222"])


if __name__ == "__main__":
    unittest.main()
