"""Ledger de uso de IA: a tabela e quem escreve nela.

Pedido do Diego (2026-08-12): saber quanto custa cada coisa pra repassar na precificação.
O sistema tem só DOIS pontos pagos — `resumo_diario.claude()` e `audio.narrar()` —, então
instrumentar os dois mede tudo. Standalone: python3 app/tests/test_ia_uso.py"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _snapshot_env():
    return (os.environ.get("DSCURSO_ARTIGOS_DB"), os.environ.get("DATABASE_URL"))


def _reload_db(tmp):
    os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(tmp, "t.db")
    os.environ.pop("DATABASE_URL", None)
    import importlib, db as _db
    importlib.reload(_db)
    _db.init()
    return _db


def _restore_db(snap):
    import importlib
    a, d = snap
    if a is None:
        os.environ.pop("DSCURSO_ARTIGOS_DB", None)
    else:
        os.environ["DSCURSO_ARTIGOS_DB"] = a
    if d is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = d
    import db as _db
    importlib.reload(_db)


class TestTabelaIaUso(unittest.TestCase):
    def setUp(self):
        self.snap = _snapshot_env()
        self.tmp = tempfile.mkdtemp()
        self.db = _reload_db(self.tmp)

    def tearDown(self):
        _restore_db(self.snap)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_registra_e_lista(self):
        self.db.registrar_ia_uso("dossie", "claude-sonnet-4-6", 10_000, 2_000, 3)
        linhas = self.db.listar_ia_uso()
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]["acao"], "dossie")
        self.assertEqual(linhas[0]["modelo"], "claude-sonnet-4-6")
        self.assertEqual(linhas[0]["tokens_in"], 10_000)
        self.assertEqual(linhas[0]["tokens_out"], 2_000)
        self.assertEqual(linhas[0]["chamadas"], 3)
        self.assertTrue(linhas[0]["quando"])

    def test_duas_linhas_nao_se_sobrescrevem(self):
        self.db.registrar_ia_uso("dossie", "claude-sonnet-4-6", 1, 1)
        self.db.registrar_ia_uso("kit", "claude-sonnet-4-6", 2, 2)
        self.assertEqual(len(self.db.listar_ia_uso()), 2)

    def test_chamadas_tem_padrao_um(self):
        self.db.registrar_ia_uso("kit", "claude-sonnet-4-6", 5, 5)
        self.assertEqual(self.db.listar_ia_uso()[0]["chamadas"], 1)

    def test_lista_ordem_desc_mais_novo_primeiro(self):
        """listar_ia_uso promete ordenacao DESC (mais novo primeiro).
        Força timestamps distintos via UPDATE para testar a ordem."""
        self.db.registrar_ia_uso("dossie", "claude-sonnet-4-6", 1, 1)
        self.db.registrar_ia_uso("kit", "claude-sonnet-4-6", 2, 2)
        # Força timestamps distintos: a primeira fica mais velha, a segunda mais nova
        with self.db._conn() as c:
            c.execute("UPDATE ia_uso SET quando=? WHERE acao=?",
                      ("2026-08-12T10:00:00.000000", "dossie"))
            c.execute("UPDATE ia_uso SET quando=? WHERE acao=?",
                      ("2026-08-12T10:00:01.000000", "kit"))
        linhas = self.db.listar_ia_uso()
        # Mais recente (kit) deve estar PRIMEIRO
        self.assertEqual(linhas[0]["acao"], "kit")
        self.assertEqual(linhas[1]["acao"], "dossie")


class TestTodaTabelaTemRls(unittest.TestCase):
    """`_TABELAS` dirige o ENABLE ROW LEVEL SECURITY no Supabase. Tabela criada e esquecida
    nessa lista fica exposta na Data API pública — e ninguém percebe, porque o app conecta
    direto e ignora RLS."""

    def test_toda_tabela_criada_no_init_esta_em_tabelas(self):
        import db
        fonte = open(os.path.join(os.path.dirname(__file__), "..", "db.py"),
                     encoding="utf-8").read()
        criadas = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", fonte))
        self.assertTrue(criadas)                       # a regex tem que achar algo
        self.assertEqual(criadas - set(db._TABELAS), set())


def _resposta_api(texto="ok", tin=100, tout=20, stop="end_turn"):
    return {"content": [{"type": "text", "text": texto}],
            "stop_reason": stop,
            "usage": {"input_tokens": tin, "output_tokens": tout}}


class TestClaudeGravaOUso(unittest.TestCase):
    """O POST vira uma função pequena (`_post`) só pra o teste poder provar a
    contabilidade sem rede — o que importa aqui é o efeito no banco, não o HTTP."""

    def setUp(self):
        self.snap = _snapshot_env()
        self.tmp = tempfile.mkdtemp()
        self.db = _reload_db(self.tmp)
        import importlib, resumo_diario
        importlib.reload(resumo_diario)
        self.rd = resumo_diario

    def tearDown(self):
        _restore_db(self.snap)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_uma_chamada_vira_uma_linha_com_a_acao_e_o_modelo(self):
        self.rd._post = lambda body: _resposta_api(tin=1234, tout=56)
        self.rd.claude(self.rd.SONNET, "oi", acao="dossie")
        linhas = self.db.listar_ia_uso()
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]["acao"], "dossie")
        self.assertEqual(linhas[0]["modelo"], self.rd.SONNET)
        self.assertEqual(linhas[0]["tokens_in"], 1234)
        self.assertEqual(linhas[0]["tokens_out"], 56)
        self.assertEqual(linhas[0]["chamadas"], 1)

    def test_laco_de_continuacao_vira_UMA_linha_somada(self):
        """`cont=4` pode render 5 idas à API numa chamada só. Duas linhas fariam a tela
        contar duas 'ações' onde houve uma."""
        respostas = [_resposta_api("parte1", 100, 10, stop="max_tokens"),
                     _resposta_api("parte2", 200, 20)]
        self.rd._post = lambda body: respostas.pop(0)
        self.rd.claude(self.rd.SONNET, "oi", acao="boletim")
        linhas = self.db.listar_ia_uso()
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]["tokens_in"], 300)
        self.assertEqual(linhas[0]["tokens_out"], 30)
        self.assertEqual(linhas[0]["chamadas"], 2)

    def test_sem_acao_cai_no_balde_desconhecido(self):
        """Ponto de chamada que eu esquecer de rotular tem que APARECER na conta, não
        sumir dela."""
        self.rd._post = lambda body: _resposta_api()
        self.rd.claude(self.rd.HAIKU, "oi")
        self.assertEqual(self.db.listar_ia_uso()[0]["acao"], "desconhecido")

    def test_o_texto_devolvido_continua_o_mesmo(self):
        self.rd._post = lambda body: _resposta_api("resposta da IA")
        self.assertEqual(self.rd.claude(self.rd.SONNET, "oi", acao="kit"), "resposta da IA")

    def test_banco_fora_do_ar_nao_derruba_a_geracao(self):
        """Perder uma linha de custo é aceitável; perder o estudo do dia não é."""
        import db
        def explode(*a, **k):
            raise RuntimeError("banco caiu")
        db.registrar_ia_uso = explode
        self.rd._post = lambda body: _resposta_api("saiu mesmo assim")
        self.assertEqual(self.rd.claude(self.rd.SONNET, "oi", acao="kit"), "saiu mesmo assim")

    def test_falha_no_meio_do_laco_preserva_o_que_ja_foi_pago(self):
        """A 1ª ida já foi cobrada pela Anthropic mesmo que a 2ª estoure."""
        chamadas = {"n": 0}

        def _post(body):
            chamadas["n"] += 1
            if chamadas["n"] == 1:
                return _resposta_api("p1", 500, 50, stop="max_tokens")
            raise RuntimeError("rede caiu")

        self.rd._post = _post
        with self.assertRaises(RuntimeError):
            self.rd.claude(self.rd.SONNET, "oi", acao="boletim")
        linhas = self.db.listar_ia_uso()
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]["tokens_in"], 500)


class _IaCustoQuebrado:
    """Substituto de `ia_custo` que quebra na chamada — simula import ok mas módulo
    com o método renomeado/corrompido."""
    def registrar(self, *a, **k):
        raise ImportError("ia_custo quebrado de propósito")


class TestFinallyDaContabilidadeEProtegido(unittest.TestCase):
    """O `import ia_custo` + a chamada `ia_custo.registrar(...)` dentro do `finally` de
    `claude()` também precisam da própria guarda: se `ia_custo` quebrar um dia (erro de
    sintaxe, atributo renomeado...), isso não pode nem estourar uma geração saudável nem
    mascarar a exceção real do laço."""

    def setUp(self):
        self.snap = _snapshot_env()
        self.tmp = tempfile.mkdtemp()
        self.db = _reload_db(self.tmp)
        import importlib, resumo_diario
        importlib.reload(resumo_diario)
        self.rd = resumo_diario
        self._ia_custo_original = sys.modules.get("ia_custo")
        self.addCleanup(self._restaurar_ia_custo)
        sys.modules["ia_custo"] = _IaCustoQuebrado()

    def tearDown(self):
        _restore_db(self.snap)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _restaurar_ia_custo(self):
        if self._ia_custo_original is not None:
            sys.modules["ia_custo"] = self._ia_custo_original
        else:
            sys.modules.pop("ia_custo", None)

    def test_geracao_saudavel_nao_estoura_por_causa_do_ia_custo_quebrado(self):
        self.rd._post = lambda body: _resposta_api("saiu mesmo com ia_custo quebrado")
        self.assertEqual(
            self.rd.claude(self.rd.SONNET, "oi", acao="kit"),
            "saiu mesmo com ia_custo quebrado")

    def test_excecao_original_do_laco_nao_e_mascarada_pela_do_ia_custo(self):
        """A prova que importa: quem sobe pro chamador é o RuntimeError da rede, não o
        ImportError da contabilidade quebrada."""
        chamadas = {"n": 0}

        def _post(body):
            chamadas["n"] += 1
            if chamadas["n"] == 1:
                return _resposta_api("p1", 500, 50, stop="max_tokens")
            raise RuntimeError("rede caiu")

        self.rd._post = _post
        with self.assertRaises(RuntimeError):
            self.rd.claude(self.rd.SONNET, "oi", acao="boletim")


class TestRotulosNosCaminhosReais(unittest.TestCase):
    """Não basta o parâmetro existir — o que importa é o ponto de chamada REAL passar o
    rótulo. Com `_post` substituído dá pra rodar o caminho de verdade sem rede.

    (Lição da fatia anterior do item 33: grep no fonte não prova call site.)

    `triage.py` tem TRÊS chamadas, não uma: triar (classifica a varredura semanal),
    taggear (etiqueta o estoque no backfill) e extrair_metadados (lê área/fonte/data de
    um PDF recém-subido). São atividades diferentes, com gatilhos e frequências
    diferentes — por isso três rótulos (`triagem`, `tags`, `metadados`), não um só
    (decisão do controlador 2026-08-12, corrigindo o levantamento incompleto do brief)."""

    def setUp(self):
        self.snap = _snapshot_env()
        self.tmp = tempfile.mkdtemp()
        self.db = _reload_db(self.tmp)
        import importlib, resumo_diario
        importlib.reload(resumo_diario)
        self.rd = resumo_diario
        self.rd._post = lambda body: _resposta_api(json.dumps({"blocos": []}))

    def tearDown(self):
        _restore_db(self.snap)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _acoes(self):
        return [l["acao"] for l in self.db.listar_ia_uso()]

    def test_dossie_se_rotula_dossie(self):
        import importlib, dossie
        importlib.reload(dossie)
        dossie._gerador_padrao()("prompt qualquer")
        self.assertEqual(self._acoes(), ["dossie"])

    def test_roteiro_do_audio_se_rotula_audio_roteiro(self):
        import importlib, audio
        importlib.reload(audio)
        audio.gerar_roteiro({"titulo": "T", "fonte": "NEJM"}, {"resumo": "r"})
        self.assertEqual(self._acoes(), ["audio_roteiro"])

    def test_resumo_do_estudo_se_rotula_resumo_estudo(self):
        self.rd.gerar_texto_do_artigo({"titulo": "T", "fonte": "NEJM", "resumo": "r"})
        self.assertEqual(self._acoes(), ["resumo_estudo"])

    def test_triagem_se_rotula_triagem(self):
        """Dirige `triage.triar` (classificar ENTRA/LIXO da varredura semanal)."""
        import importlib, triage
        importlib.reload(triage)
        triage.triar([{"titulo": "T", "fonte": "NEJM", "resumo": "r"}], "Obesidade")
        self.assertEqual(self._acoes(), ["triagem"])

    def test_tags_se_rotula_tags(self):
        """Dirige `triage.taggear` (etiquetar o estoque, backfill) — rótulo próprio,
        separado de `triagem` (era o que o brief original testava sob o nome errado)."""
        import importlib, triage
        importlib.reload(triage)
        triage.taggear([{"titulo": "T", "resumo": "r"}])
        self.assertEqual(self._acoes(), ["tags"])

    def test_metadados_se_rotula_metadados(self):
        """Dirige `triage.extrair_metadados` (área/fonte/data do PDF recém-subido) —
        a terceira chamada de triage.py, sem teste nenhum no brief original."""
        import importlib, triage
        importlib.reload(triage)
        triage.extrair_metadados("T", "corpo do estudo", ["Obesidade"])
        self.assertEqual(self._acoes(), ["metadados"])


class TestTtsNoLedger(unittest.TestCase):
    """O TTS é cobrado por CARACTERE, então não há `usage` pra ler — o que se paga é o
    tamanho do que a gente manda."""

    def setUp(self):
        self.snap = _snapshot_env()
        self.tmp = tempfile.mkdtemp()
        self.db = _reload_db(self.tmp)
        self.snap_key = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = "sk-teste"
        import importlib, config, audio
        importlib.reload(config)
        importlib.reload(audio)
        self.audio = audio
        self.audio._post_tts = lambda body: b"mp3"

    def tearDown(self):
        if self.snap_key is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = self.snap_key
        _restore_db(self.snap)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_grava_o_tamanho_do_texto_como_entrada(self):
        self.audio.narrar("a" * 500)
        linha = self.db.listar_ia_uso()[0]
        self.assertEqual(linha["acao"], "audio_tts")
        self.assertEqual(linha["tokens_in"], 500)
        self.assertEqual(linha["tokens_out"], 0)

    def test_grava_o_que_foi_MANDADO_e_nao_o_original(self):
        """`narrar` corta em 4000 caracteres antes de enviar (audio.py:47) — cobrado é o
        cortado. Registrar 5000 aqui inflaria a conta de propósito."""
        self.audio.narrar("b" * 5000)
        self.assertEqual(self.db.listar_ia_uso()[0]["tokens_in"], 4000)

    def test_o_mp3_continua_voltando(self):
        self.assertEqual(self.audio.narrar("oi"), b"mp3")


if __name__ == "__main__":
    unittest.main()
