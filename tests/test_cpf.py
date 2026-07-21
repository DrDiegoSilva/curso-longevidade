import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import cpf


class TestCpf(unittest.TestCase):
    def test_validos(self):
        self.assertTrue(cpf.valida("529.982.247-25"))   # com máscara
        self.assertTrue(cpf.valida("52998224725"))       # só dígitos

    def test_invalidos(self):
        self.assertFalse(cpf.valida("111.111.111-11"))   # todos iguais
        self.assertFalse(cpf.valida("529.982.247-24"))   # dígito verificador errado
        self.assertFalse(cpf.valida("123"))              # curto
        self.assertFalse(cpf.valida(""))                 # vazio
        self.assertFalse(cpf.valida(None))               # None

    def test_so_digitos_e_formata(self):
        self.assertEqual(cpf.so_digitos("529.982.247-25"), "52998224725")
        self.assertEqual(cpf.formata("52998224725"), "529.982.247-25")


if __name__ == "__main__":
    unittest.main()
