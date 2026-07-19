"""Testes da normalização de WhatsApp. Standalone."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPhone(unittest.TestCase):
    def setUp(self):
        import phone
        self.n = phone.normalizar

    def test_adiciona_55_celular(self):
        self.assertEqual(self.n("(43) 99999-0000"), "5543999990000")   # 11 díg -> +55

    def test_adiciona_55_fixo(self):
        self.assertEqual(self.n("43 3333-4444"), "554333334444")       # 10 díg -> +55

    def test_ja_tem_pais(self):
        self.assertEqual(self.n("5543991398360"), "5543991398360")     # 13 díg, igual
        self.assertEqual(self.n("55 43 3333-4444"), "554333334444")    # 12 díg, igual

    def test_vazio(self):
        self.assertEqual(self.n(""), "")
        self.assertEqual(self.n(None), "")


if __name__ == "__main__":
    unittest.main()
