"""Roteiro de áudio (Claude) -> narração (OpenAI TTS). `gerar_fn`/`_post_tts`
injetáveis, mesmo padrão de test_texto_resumo.py e afins -- sem rede real."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import audio


class TestGerarRoteiro(unittest.TestCase):
    def test_usa_titulo_pt_e_fonte(self):
        art = {"titulo": "Original em inglês", "fonte": "NEJM"}
        conteudo = {"titulo_pt": "Título em português", "resumo": "Resumo do estudo."}
        capturado = {}
        def fake(material):
            capturado["material"] = material
            return "roteiro falado"
        self.assertEqual(audio.gerar_roteiro(art, conteudo, gerar_fn=fake), "roteiro falado")
        self.assertIn("Título em português", capturado["material"])
        self.assertIn("NEJM", capturado["material"])
        self.assertIn("Resumo do estudo.", capturado["material"])

    def test_sem_titulo_pt_cai_no_titulo_original(self):
        art = {"titulo": "Só tem este"}
        conteudo = {"resumo": "R"}
        capturado = {}
        audio.gerar_roteiro(art, conteudo, gerar_fn=lambda m: capturado.setdefault("m", m))
        self.assertIn("Só tem este", capturado["m"])

    def test_limpa_marcacao_e_emoji_do_resumo(self):
        art = {"titulo": "T"}
        conteudo = {"resumo": "🎯 *Resumo* com _ênfase_ e emoji 📊"}
        capturado = {}
        audio.gerar_roteiro(art, conteudo, gerar_fn=lambda m: capturado.setdefault("m", m))
        self.assertNotIn("*", capturado["m"])
        self.assertNotIn("🎯", capturado["m"])
        self.assertNotIn("📊", capturado["m"])


class TestGerarRoteiroPeca(unittest.TestCase):
    """Mesma ideia de gerar_roteiro, mas pra uma peça de trilha (não um estudo) --
    pedido do Diego, 2026-09-14."""

    def test_usa_titulo_eixo_e_corpo(self):
        peca = {"titulo": "MK-677", "eixo": "Secretagogos de GH",
                "corpo": "Texto da aula.", "mentalidade": "O que fica."}
        capturado = {}
        def fake(material):
            capturado["material"] = material
            return "roteiro da aula"
        self.assertEqual(audio.gerar_roteiro_peca(peca, gerar_fn=fake), "roteiro da aula")
        self.assertIn("MK-677", capturado["material"])
        self.assertIn("Secretagogos de GH", capturado["material"])
        self.assertIn("Texto da aula.", capturado["material"])
        self.assertIn("O que fica.", capturado["material"])

    def test_limpa_marcacao_do_corpo_e_da_mentalidade(self):
        peca = {"titulo": "T", "eixo": "E", "corpo": "**Negrito** e _itálico_.",
                "mentalidade": "Outro *ponto*."}
        capturado = {}
        audio.gerar_roteiro_peca(peca, gerar_fn=lambda m: capturado.setdefault("m", m))
        self.assertNotIn("*", capturado["m"])
        self.assertNotIn("_itálico_", capturado["m"])

    def test_sem_gerar_fn_chama_a_ia_de_verdade(self):
        """gerar_fn é o ponto de injeção -- sem ele, a função tenta usar
        resumo_diario.claude (rede). Só confirmamos que ela TENTA (levanta por
        falta de rede/chave), não que a chamada teria sucesso."""
        peca = {"titulo": "T", "eixo": "E", "corpo": "C", "mentalidade": "M"}
        with self.assertRaises(Exception):
            audio.gerar_roteiro_peca(peca)


class TestGerarAudioDaPeca(unittest.TestCase):
    def test_narrar_e_chamado_com_o_roteiro(self):
        peca = {"titulo": "T", "eixo": "E", "corpo": "C", "mentalidade": "M"}
        orig_roteiro, orig_narrar = audio.gerar_roteiro_peca, audio.narrar
        audio.gerar_roteiro_peca = lambda p, gerar_fn=None: "ROTEIRO-X"
        capturado = {}
        def fake_narrar(texto):
            capturado["texto"] = texto
            return b"mp3-bytes"
        audio.narrar = fake_narrar
        try:
            self.assertEqual(audio.gerar_audio_da_peca(peca), b"mp3-bytes")
        finally:
            audio.gerar_roteiro_peca, audio.narrar = orig_roteiro, orig_narrar
        self.assertEqual(capturado["texto"], "ROTEIRO-X")


if __name__ == "__main__":
    unittest.main()
