import os, sys, unittest
from datetime import date
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import daily

class TestEFresco(unittest.TestCase):
    def test_recente_e_fresco(self):
        self.assertTrue(daily._e_fresco("2026-07-01", ref=date(2026, 7, 25)))   # 24 dias

    def test_borda_30_dias(self):
        self.assertTrue(daily._e_fresco("2026-06-25", ref=date(2026, 7, 25)))   # 30 dias exatos
        self.assertFalse(daily._e_fresco("2026-06-24", ref=date(2026, 7, 25)))  # 31 dias

    def test_futuro_conta_como_fresco(self):
        self.assertTrue(daily._e_fresco("2026-07-30", ref=date(2026, 7, 25)))   # publicação futura

    def test_data_vazia_ou_invalida_false(self):
        self.assertFalse(daily._e_fresco("", ref=date(2026, 7, 25)))
        self.assertFalse(daily._e_fresco("lixo", ref=date(2026, 7, 25)))
        self.assertFalse(daily._e_fresco("2026-07", ref=date(2026, 7, 25)))     # parcial

if __name__ == "__main__":
    unittest.main()
