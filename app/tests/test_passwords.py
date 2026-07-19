"""Testes da lib pura de senha (hash/conferir/força). Standalone:
python3 app/tests/test_passwords.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import passwords


class TestPasswords(unittest.TestCase):
    def test_hash_roundtrip(self):
        h = passwords.hash_senha("abc123")
        self.assertTrue(passwords.conferir_senha("abc123", h))

    def test_senha_errada(self):
        h = passwords.hash_senha("abc123")
        self.assertFalse(passwords.conferir_senha("abc124", h))
        self.assertFalse(passwords.conferir_senha("", h))

    def test_hash_tem_salt_aleatorio(self):
        # duas chamadas p/ a mesma senha geram hashes diferentes (salt por usuário)
        self.assertNotEqual(passwords.hash_senha("abc123"), passwords.hash_senha("abc123"))

    def test_formato_stored_invalido_nao_explode(self):
        self.assertFalse(passwords.conferir_senha("x", ""))
        self.assertFalse(passwords.conferir_senha("x", None))
        self.assertFalse(passwords.conferir_senha("x", "lixo-sem-cifrao"))

    def test_forca_ok(self):
        self.assertTrue(passwords.validar_forca("abc123"))
        self.assertTrue(passwords.validar_forca("Senha1"))
        self.assertTrue(passwords.validar_forca("12ab34"))

    def test_forca_curta(self):
        self.assertFalse(passwords.validar_forca("ab12"))       # < 6
        self.assertFalse(passwords.validar_forca(""))
        self.assertFalse(passwords.validar_forca(None))

    def test_forca_sem_numero_ou_sem_letra(self):
        self.assertFalse(passwords.validar_forca("abcdef"))     # sem número
        self.assertFalse(passwords.validar_forca("123456"))     # sem letra


if __name__ == "__main__":
    unittest.main()
