import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import phone


class TestNormalizar(unittest.TestCase):
    def test_br_sem_pais_ganha_55(self):
        self.assertEqual(phone.normalizar("(43) 99999-0000"), "5543999990000")

    def test_br_com_mais_55_vira_digitos(self):
        self.assertEqual(phone.normalizar("+55 43 99999-0000"), "5543999990000")

    def test_br_ja_normalizado_inalterado(self):
        self.assertEqual(phone.normalizar("5543999990000"), "5543999990000")

    def test_eua_com_mais_mantem_e_nao_ganha_55(self):
        self.assertEqual(phone.normalizar("+1 (305) 555-1234"), "+13055551234")

    def test_idempotente_eua(self):
        once = phone.normalizar("+1 (305) 555-1234")
        self.assertEqual(phone.normalizar(once), once)   # +13055551234 -> +13055551234

    def test_idempotente_br(self):
        once = phone.normalizar("43 99999-0000")
        self.assertEqual(phone.normalizar(once), once)

    def test_vazio(self):
        self.assertEqual(phone.normalizar(""), "")

    def test_none_vira_vazio(self):
        self.assertEqual(phone.normalizar(None), "")

    def test_br_fixo_10_digitos(self):
        self.assertEqual(phone.normalizar("43 3333-4444"), "554333334444")

    def test_br_com_pais_e_espacos(self):
        self.assertEqual(phone.normalizar("55 43 3333-4444"), "554333334444")


class TestParaApi(unittest.TestCase):
    def test_tira_mais_internacional(self):
        self.assertEqual(phone.para_api("+13055551234"), "13055551234")

    def test_br_inalterado(self):
        self.assertEqual(phone.para_api("5543999990000"), "5543999990000")


class TestMontarE164(unittest.TestCase):
    def test_junta_dial_e_local(self):
        self.assertEqual(phone.montar_e164("1", "(305) 555-1234"), "+13055551234")

    def test_br(self):
        self.assertEqual(phone.montar_e164("55", "43 99999-0000"), "+5543999990000")


if __name__ == "__main__":
    unittest.main()
