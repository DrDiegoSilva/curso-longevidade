"""Testes do extrator robusto de JSON (jsonx). Standalone."""
import os
import sys
import json
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import jsonx


class TestJsonx(unittest.TestCase):
    def test_cerca_e_justificativa_que_quebrava_o_regex(self):
        # caso REAL: Haiku devolve ```json + array + "Justificativa" com [0]/[3] depois
        texto = ('```json\n[\n  {"i":0,"classe":"ENTRA","score":7},\n'
                 '  {"i":1,"classe":"LIXO","score":0}\n]\n```\n\n'
                 '**Justificativa:**\n- **[0]**: ensaio clínico...\n- **[1]**: fora do tema')
        bruto = jsonx.primeiro_array(texto)
        arr = json.loads(bruto)
        self.assertEqual(len(arr), 2)
        self.assertEqual(arr[0]["classe"], "ENTRA")
        self.assertNotIn("Justificativa", bruto)   # não agarrou o texto de depois

    def test_colchete_dentro_de_string_nao_atrapalha(self):
        texto = '[{"pergunta":"A dose [alta] funciona?"},{"pergunta":"E o exercício?"}]'
        arr = json.loads(jsonx.primeiro_array(texto))
        self.assertEqual(arr[0]["pergunta"], "A dose [alta] funciona?")
        self.assertEqual(len(arr), 2)

    def test_objeto_com_cerca(self):
        texto = 'Segue o gráfico:\n```json\n{"titulo":"Perda","barras":[{"rotulo":"A","valor":10}]}\n```'
        obj = json.loads(jsonx.primeiro_objeto(texto))
        self.assertEqual(obj["titulo"], "Perda")
        self.assertEqual(obj["barras"][0]["rotulo"], "A")

    def test_sem_json(self):
        self.assertIsNone(jsonx.primeiro_array("nenhum json aqui"))
        self.assertIsNone(jsonx.primeiro_objeto("null"))
        self.assertIsNone(jsonx.primeiro_array(""))
        self.assertIsNone(jsonx.primeiro_array(None))


if __name__ == "__main__":
    unittest.main()
