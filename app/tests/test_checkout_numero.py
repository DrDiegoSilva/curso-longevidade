"""Combine país+local no checkout público (/assinar). Standalone: python3 app/tests/test_checkout_numero.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import phone


class TestCheckoutNumero(unittest.TestCase):
    def test_monta_whatsapp_do_pais(self):
        # simula o combine que o _post_assinar faz
        got = phone.montar_e164("1" or "55", "(305) 555-1234")
        self.assertEqual(got, "+13055551234")

    def test_default_br_quando_pais_vazio(self):
        got = phone.montar_e164("" or "55", "43 99999-0000")
        self.assertEqual(got, "+5543999990000")


if __name__ == "__main__":
    unittest.main()
