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
