import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import rate_limit


class TestRateLimit(unittest.TestCase):
    def setUp(self):
        rate_limit.resetar()

    def test_libera_ate_o_maximo_e_barra_depois(self):
        t = 1000.0
        # 3 permitidas na janela
        self.assertFalse(rate_limit.limitado("k", 3, 60, agora=t))
        self.assertFalse(rate_limit.limitado("k", 3, 60, agora=t + 1))
        self.assertFalse(rate_limit.limitado("k", 3, 60, agora=t + 2))
        # 4ª estoura
        self.assertTrue(rate_limit.limitado("k", 3, 60, agora=t + 3))

    def test_janela_desliza_e_libera_de_novo(self):
        t = 1000.0
        for i in range(3):
            rate_limit.limitado("k", 3, 60, agora=t + i)
        self.assertTrue(rate_limit.limitado("k", 3, 60, agora=t + 4))     # ainda dentro da janela
        self.assertFalse(rate_limit.limitado("k", 3, 60, agora=t + 200))  # janela passou -> libera

    def test_chaves_independentes(self):
        t = 1000.0
        for i in range(3):
            rate_limit.limitado("a", 3, 60, agora=t)
        self.assertTrue(rate_limit.limitado("a", 3, 60, agora=t))
        self.assertFalse(rate_limit.limitado("b", 3, 60, agora=t))        # outra chave, livre


if __name__ == "__main__":
    unittest.main()
