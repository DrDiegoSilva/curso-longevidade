import sys, os, unittest
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import serve


class TestScheduler(unittest.TestCase):
    def test_proximo_e_18h_quando_agora_e_meiodia(self):
        now = datetime(2026, 7, 18, 12, 0)
        alvo, tarefa = serve.proximo_disparo(now, [(8, "enviar"), (18, "preparar")])
        self.assertEqual((alvo.hour, tarefa), (18, "preparar"))

    def test_vira_o_dia_quando_passou_das_18(self):
        now = datetime(2026, 7, 18, 19, 0)
        alvo, tarefa = serve.proximo_disparo(now, [(8, "enviar"), (18, "preparar")])
        self.assertEqual((alvo.day, alvo.hour, tarefa), (19, 8, "enviar"))

    def test_de_madrugada_o_proximo_e_08h(self):
        now = datetime(2026, 7, 18, 3, 0)
        alvo, tarefa = serve.proximo_disparo(now, [(8, "enviar"), (18, "preparar")])
        self.assertEqual((alvo.day, alvo.hour, tarefa), (18, 8, "enviar"))


if __name__ == "__main__":
    unittest.main()
