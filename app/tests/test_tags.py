"""Fase 1 — tags de estudos."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestTriageTags(unittest.TestCase):
    def test_norm_tags(self):
        import triage
        self.assertEqual(triage._norm_tags(["Retatrutida", "GLP1", "retatrutida", "  x "]),
                         ["retatrutida", "glp1", "x"])
        self.assertEqual(triage._norm_tags(None), [])
        self.assertEqual(triage._norm_tags("retatrutida"), [])
        self.assertEqual(triage._norm_tags([1, "", "  "]), [])

    def test_parse_extrai_tags(self):
        import triage
        txt = ('[{"i":0,"classe":"ENTRA","score":8,"tags":["Retatrutida","GLP1"]},'
               '{"i":1,"classe":"LIXO","score":0}]')
        out = triage._parse(txt, [{"titulo": "A"}, {"titulo": "B"}], "Obesidade")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["tags"], ["retatrutida", "glp1"])

    def test_parse_sem_tags(self):
        import triage
        out = triage._parse('[{"i":0,"classe":"ENTRA","score":8}]', [{"titulo": "A"}], "T")
        self.assertEqual(out[0]["tags"], [])

    def test_triar_devolve_tags(self):
        import triage
        llm = lambda p: '[{"i":0,"classe":"ENTRA","score":9,"tags":["Semaglutida"]}]'
        out = triage.triar([{"titulo": "X", "resumo": "y"}], "Obesidade", llm=llm)
        self.assertEqual(out[0]["tags"], ["semaglutida"])

    def test_taggear_so_tags(self):
        import triage
        llm = lambda p: '[{"i":0,"tags":["Retatrutida"]},{"i":1,"tags":["menopausa","trh"]}]'
        out = triage.taggear([{"titulo": "A"}, {"titulo": "B"}], llm=llm)
        self.assertEqual(out, {0: ["retatrutida"], 1: ["menopausa", "trh"]})

    def test_taggear_vazio(self):
        import triage
        self.assertEqual(triage.taggear([]), {})
