import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import paises

class TestPaises(unittest.TestCase):
    def test_brasil_primeiro(self):
        self.assertEqual(paises.PAISES[0][0], "BR")
        self.assertEqual(paises.PAISES[0][3], "55")
    def test_tem_eua_e_portugal(self):
        dials = {iso: dial for iso, _, _, dial in paises.PAISES}
        self.assertEqual(dials["US"], "1")
        self.assertEqual(dials["PT"], "351")
    def test_estrutura_4_campos(self):
        for p in paises.PAISES:
            self.assertEqual(len(p), 4)
