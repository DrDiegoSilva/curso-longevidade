import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import deliver


class TestPayloadPhone(unittest.TestCase):
    def test_evolution_texto_tira_mais(self):
        p = deliver._evolution_texto_payload("+13055551234", "oi")
        self.assertEqual(p["number"], "13055551234")

    def test_evolution_texto_br_inalterado(self):
        p = deliver._evolution_texto_payload("5543999990000", "oi")
        self.assertEqual(p["number"], "5543999990000")

    def test_evolution_media_tira_mais(self):
        p = deliver._evolution_media_payload("+13055551234", __file__, "cap")
        self.assertEqual(p["number"], "13055551234")

    def test_evolution_media_br_inalterado(self):
        p = deliver._evolution_media_payload("5543999990000", __file__, "cap")
        self.assertEqual(p["number"], "5543999990000")

    def test_evolution_audio_tira_mais(self):
        p = deliver._evolution_audio_payload("+13055551234", b"abc")
        self.assertEqual(p["number"], "13055551234")

    def test_evolution_audio_br_inalterado(self):
        p = deliver._evolution_audio_payload("5543999990000", b"abc")
        self.assertEqual(p["number"], "5543999990000")

    def test_zapi_texto_tira_mais(self):
        p = deliver._zapi_texto_payload("+13055551234", "oi")
        self.assertEqual(p["phone"], "13055551234")

    def test_zapi_texto_br_inalterado(self):
        p = deliver._zapi_texto_payload("5543999990000", "oi")
        self.assertEqual(p["phone"], "5543999990000")

    def test_zapi_pdf_tira_mais(self):
        p = deliver._zapi_pdf_payload("+13055551234", "http://x/a.pdf", "cap")
        self.assertEqual(p["phone"], "13055551234")

    def test_zapi_pdf_br_inalterado(self):
        p = deliver._zapi_pdf_payload("5543999990000", "http://x/a.pdf", "cap")
        self.assertEqual(p["phone"], "5543999990000")


if __name__ == "__main__":
    unittest.main()


class TestNomeDoArquivo(unittest.TestCase):
    """A legenda passou a levar o link do estudo; o nome do arquivo saia DELA."""

    def test_nome_do_arquivo_ignora_a_url_da_legenda(self):
        import deliver
        p = deliver._evolution_media_payload(
            "5543999990000", __file__,
            caption="Tirzepatida semanal\n\nEstudo: https://doi.org/10.1056/x",
            nome_arquivo="Tirzepatida semanal")
        self.assertEqual(p["fileName"], "Tirzepatida_semanal.pdf")
        self.assertIn("https://doi.org/10.1056/x", p["caption"])

    def test_sem_nome_explicito_mantem_o_comportamento_antigo(self):
        import deliver
        p = deliver._evolution_media_payload("5543999990000", __file__, caption="Titulo do estudo")
        self.assertEqual(p["fileName"], "Titulo_do_estudo.pdf")
