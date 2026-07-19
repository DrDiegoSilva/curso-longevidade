import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import triage


class TestTriage(unittest.TestCase):
    def _arts(self):
        return [
            {"titulo": "Tirzepatida na obesidade (ECR)", "fonte": "NEJM", "resumo": "..."},
            {"titulo": "Psoríase que cita obesidade de raspão", "fonte": "Derm J", "resumo": "..."},
        ]

    def test_parse_seleciona_entra_com_tema_e_score(self):
        arts = self._arts()
        resp = '[{"i":0,"classe":"ENTRA","score":9},{"i":1,"classe":"LIXO","score":0}]'
        out = triage._parse(resp, arts, "Obesidade")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["titulo"], "Tirzepatida na obesidade (ECR)")
        self.assertEqual(out[0]["tema"], "Obesidade")
        self.assertEqual(out[0]["score"], 9.0)

    def test_parse_resposta_invalida_retorna_vazio(self):
        self.assertEqual(triage._parse("não é json", self._arts(), "Obesidade"), [])

    def test_triar_usa_llm_injetado(self):
        arts = self._arts()
        fake_llm = lambda prompt: '[{"i":0,"classe":"ENTRA","score":7}]'
        out = triage.triar(arts, "Obesidade", llm=fake_llm)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["score"], 7.0)

    def test_triar_lista_vazia(self):
        self.assertEqual(triage.triar([], "Obesidade", llm=lambda p: "[]"), [])


if __name__ == "__main__":
    unittest.main()
