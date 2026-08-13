"""Preço de IA -> dinheiro. O ledger guarda TOKENS; o custo é calculado na leitura, então
preço errado (ou preço que mudou) é recálculo, não perda: a história inteira se revaloriza.
Standalone: python3 app/tests/test_ia_custo.py"""
import glob
import importlib
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestCustoUsd(unittest.TestCase):
    def setUp(self):
        import config, ia_custo
        importlib.reload(config)
        importlib.reload(ia_custo)
        self.cfg, self.ia = config, ia_custo

    def test_um_milhao_de_tokens_de_entrada_custa_o_preco_de_entrada(self):
        p_in, _ = self.cfg.PRECOS_IA["claude-sonnet-4-6"]
        self.assertAlmostEqual(self.ia.custo_usd("claude-sonnet-4-6", 1_000_000, 0), p_in)

    def test_soma_entrada_e_saida(self):
        p_in, p_out = self.cfg.PRECOS_IA["claude-sonnet-4-6"]
        self.assertAlmostEqual(self.ia.custo_usd("claude-sonnet-4-6", 500_000, 100_000),
                               p_in / 2 + p_out / 10)

    def test_tts_cobra_por_caractere_na_entrada(self):
        p_in, _ = self.cfg.PRECOS_IA["tts-1-hd"]
        self.assertAlmostEqual(self.ia.custo_usd("tts-1-hd", 1_000_000, 0), p_in)

    def test_modelo_sem_preco_devolve_zero_em_vez_de_explodir(self):
        """Modelo novo não pode derrubar a tela de custos — vira zero e um aviso no log."""
        self.assertEqual(self.ia.custo_usd("modelo-que-nao-existe", 10_000, 1_000), 0.0)

    def test_zero_tokens_custa_zero(self):
        self.assertEqual(self.ia.custo_usd("claude-sonnet-4-6", 0, 0), 0.0)

    def test_none_nao_explode(self):
        self.assertEqual(self.ia.custo_usd("claude-sonnet-4-6", None, None), 0.0)


class TestEmBrl(unittest.TestCase):
    def setUp(self):
        import config, ia_custo
        importlib.reload(config)
        importlib.reload(ia_custo)
        self.cfg, self.ia = config, ia_custo

    def test_usa_a_cotacao_do_config(self):
        self.assertAlmostEqual(self.ia.em_brl(2.0), 2.0 * self.cfg.USD_BRL)


class TestOverrideDeEnv(unittest.TestCase):
    """Preço errado tem que dar pra corrigir SEM deploy — é a chave de admin do Diego
    que está longe, não o código."""

    def setUp(self):
        self.snap = (os.environ.get("DSCURSO_PRECOS_IA"), os.environ.get("DSCURSO_USD_BRL"))

    def tearDown(self):
        import importlib, config
        for k, v in zip(("DSCURSO_PRECOS_IA", "DSCURSO_USD_BRL"), self.snap):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        importlib.reload(config)

    def test_env_troca_o_preco_de_um_modelo(self):
        import importlib, config, ia_custo
        os.environ["DSCURSO_PRECOS_IA"] = '{"claude-sonnet-4-6": [9.0, 90.0]}'
        importlib.reload(config)
        importlib.reload(ia_custo)
        self.assertAlmostEqual(ia_custo.custo_usd("claude-sonnet-4-6", 1_000_000, 0), 9.0)

    def test_env_quebrado_cai_no_padrao_em_vez_de_derrubar_o_boot(self):
        import importlib, config
        os.environ["DSCURSO_PRECOS_IA"] = "{isso não é json"
        importlib.reload(config)
        self.assertIn("claude-sonnet-4-6", config.PRECOS_IA)

    def test_env_troca_a_cotacao_do_dolar(self):
        import importlib, config
        os.environ["DSCURSO_USD_BRL"] = "6.25"
        importlib.reload(config)
        self.assertAlmostEqual(config.USD_BRL, 6.25)

    def test_entrada_valida_aplica_mesmo_com_entrada_ruim_no_mesmo_json(self):
        """Uma entrada ruim não pode engolir as irmãs válidas. Testa ambas as ordens."""
        import importlib, config, ia_custo
        # Ordem 1: entrada ruim ANTES da válida
        os.environ["DSCURSO_PRECOS_IA"] = '{"modelo-ruim": [1.0], "claude-sonnet-4-6": [9.0, 90.0]}'
        importlib.reload(config)
        importlib.reload(ia_custo)
        self.assertAlmostEqual(ia_custo.custo_usd("claude-sonnet-4-6", 1_000_000, 0), 9.0)

        # Ordem 2: entrada ruim DEPOIS da válida
        os.environ["DSCURSO_PRECOS_IA"] = '{"claude-sonnet-4-6": [9.0, 90.0], "modelo-ruim": [1.0]}'
        importlib.reload(config)
        importlib.reload(ia_custo)
        self.assertAlmostEqual(ia_custo.custo_usd("claude-sonnet-4-6", 1_000_000, 0), 9.0)

    def test_json_que_eh_lista_cai_no_padrao(self):
        """JSON válido mas que é lista, não objeto, deve cair no padrão sem derrubar o boot."""
        import importlib, config
        os.environ["DSCURSO_PRECOS_IA"] = '[1, 2]'
        importlib.reload(config)
        self.assertIn("claude-sonnet-4-6", config.PRECOS_IA)
        self.assertEqual(config.PRECOS_IA["claude-sonnet-4-6"], (3.0, 15.0))

    def test_json_que_eh_string_cai_no_padrao(self):
        """JSON válido mas que é string, não objeto, deve cair no padrão sem derrubar o boot."""
        import importlib, config
        os.environ["DSCURSO_PRECOS_IA"] = '"claude"'
        importlib.reload(config)
        self.assertIn("claude-sonnet-4-6", config.PRECOS_IA)
        self.assertEqual(config.PRECOS_IA["claude-sonnet-4-6"], (3.0, 15.0))

    def test_json_que_eh_numero_cai_no_padrao(self):
        """JSON válido mas que é número, não objeto, deve cair no padrão sem derrubar o boot."""
        import importlib, config
        os.environ["DSCURSO_PRECOS_IA"] = '42'
        importlib.reload(config)
        self.assertIn("claude-sonnet-4-6", config.PRECOS_IA)
        self.assertEqual(config.PRECOS_IA["claude-sonnet-4-6"], (3.0, 15.0))

    def test_entrada_com_valor_dict_eh_ignorada(self):
        """Entrada cujo valor é um dict (em vez de lista) deve ser pulada com log, não derrubar boot."""
        import importlib, config, ia_custo
        os.environ["DSCURSO_PRECOS_IA"] = '{"m": {"a": 1}, "claude-sonnet-4-6": [9.0, 90.0]}'
        importlib.reload(config)
        importlib.reload(ia_custo)
        self.assertAlmostEqual(ia_custo.custo_usd("claude-sonnet-4-6", 1_000_000, 0), 9.0)


class TestRegistrarNuncaLevanta(unittest.TestCase):
    """`registrar` precisa da própria guarda: os dois chamadores reais (`resumo_diario.
    claude` e `audio.narrar`) JÁ embrulham a chamada num try/except deles — o que
    mascara, no teste de cada um, se a guarda AQUI dentro sumiu. Um chamador futuro sem
    guarda própria não pode cair porque o banco caiu."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.snap = (os.environ.get("DSCURSO_ARTIGOS_DB"), os.environ.get("DATABASE_URL"))
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ.pop("DATABASE_URL", None)
        import db, ia_custo
        importlib.reload(db)
        importlib.reload(ia_custo)
        self.db, self.ia = db, ia_custo

    def tearDown(self):
        import db
        a, d = self.snap
        if a is None:
            os.environ.pop("DSCURSO_ARTIGOS_DB", None)
        else:
            os.environ["DSCURSO_ARTIGOS_DB"] = a
        if d is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = d
        importlib.reload(db)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_banco_fora_do_ar_nao_derruba_a_geracao(self):
        """Perder uma linha de custo é aceitável; perder o estudo do dia não é —
        e essa garantia é do `registrar`, não de quem o chama."""
        def explode(*a, **k):
            raise RuntimeError("banco caiu")
        original = self.db.registrar_ia_uso
        self.db.registrar_ia_uso = explode
        try:
            self.ia.registrar("kit", "claude-sonnet-4-6", 100, 10, 1)  # não pode levantar
        finally:
            self.db.registrar_ia_uso = original


class TestVocabularioDeRotulos(unittest.TestCase):
    """A spec fixa 14 rótulos pro ledger justamente pra tela futura não nascer com
    sinônimos. Sem esta lista em código, um typo em `acao="dossiee"` não cai num
    `desconhecido` visível — cria uma linha nova silenciosa, e ninguém percebe.

    Varre os `acao=` REAIS do código-fonte (não os dos testes) — grep no fonte já
    provou enganar antes (ver `TestRotulosNosCaminhosReais`, em test_ia_uso.py)."""

    def _rotulos_no_codigo(self):
        raiz = os.path.join(os.path.dirname(__file__), "..")
        kw = re.compile(r'acao="([a-zA-Z_]+)"')
        posicional = re.compile(r'ia_custo\.registrar\("([a-zA-Z_]+)"')
        achados = set()
        for caminho in glob.glob(os.path.join(raiz, "*.py")):
            fonte = open(caminho, encoding="utf-8").read()
            achados.update(kw.findall(fonte))
            achados.update(posicional.findall(fonte))
        return achados

    def test_a_regex_acha_rotulo_algum(self):
        """Se isto for vazio, a regex quebrou e o teste seguinte passaria por nada
        vasculhar — falso verde."""
        self.assertTrue(self._rotulos_no_codigo())

    def test_todo_rotulo_usado_no_codigo_pertence_ao_vocabulario(self):
        import ia_custo
        rotulos = self._rotulos_no_codigo()
        self.assertEqual(rotulos - set(ia_custo.ACOES), set())

    def test_vocabulario_tem_exatamente_os_14_rotulos_fixados(self):
        import ia_custo
        self.assertEqual(set(ia_custo.ACOES), {
            "dossie", "resumo_estudo", "boletim", "triagem", "tags", "metadados",
            "perguntas", "kit", "titulo", "grafico", "aula", "audio_roteiro",
            "audio_tts", "desconhecido"})


if __name__ == "__main__":
    unittest.main()
