# Tirar estudo da memória + ledger de custos — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar ao Diego um jeito durável de tirar um estudo ruim da memória do dossiê (parte A do item 33) e, junto, começar a medir quanto cada ação de IA custa.

**Architecture:** Duas partes independentes no mesmo branch. (1) O **ledger**: os dois únicos funis pagos do sistema — `resumo_diario.claude()` e `audio.narrar()` — passam a gravar tokens numa tabela `ia_uso`; o custo em dinheiro é calculado na leitura, a partir de uma tabela de preços em `config`. (2) A **exclusão**: uma coluna `excluido` em `curadoria_candidatos` e em `digests`, escondida por padrão dentro do `db.listar_candidatos` (um filtro só, em vez de espalhado pelos cinco consumidores), mais as telas na aba 🧠 Dossiê da /curadoria.

**Tech Stack:** Python 3 stdlib pura (o container não tem pip), SQLite nos testes e Postgres em produção, HTML gerado por f-string em `site_web.py`, testes em `unittest`.

**Spec:** `docs/superpowers/specs/2026-08-12-excluir-estudo-do-corpus-design.md`

## Global Constraints

- **Sem dependências novas.** O container é stdlib pura; nada de `pip install`.
- **Todo SQL roda em SQLite e Postgres.** Placeholders `?` (a camada converte), colunas novas por `db._add_coluna`, nada de sintaxe exclusiva de um banco.
- **Toda tabela nova entra em `db._TABELAS`** — essa lista dirige o `ENABLE ROW LEVEL SECURITY` no Supabase. Tabela fora da lista fica exposta na Data API pública.
- **Contabilidade nunca derruba geração.** Todo registro de custo vai em `try/except` com `print` no log.
- **`db.listar_por_tema` nunca é filtrado** — ele serve o portal do assinante (`serve.py:653-657`). A exclusão de um `digest` vale só dentro de `dossie.corpus_do_tema`.
- **Escopos de exclusão são exatamente três**: `''` (na base), `'memoria'`, `'tudo'`. Qualquer outro valor é erro.
- Rótulos de ação do ledger, fixados: `dossie`, `resumo_estudo`, `boletim`, `triagem`, `perguntas`, `kit`, `titulo`, `grafico`, `aula`, `audio_roteiro`, `audio_tts`, e `desconhecido` para quem esquecer.
- Testes rodam com `cd app && python3 -m unittest discover -s tests`. Um arquivo de teste também roda sozinho: `python3 app/tests/test_x.py`.
- Commits em português, no formato do repo (`feat(escopo): ...`, `fix(escopo): ...`), sem acentos na primeira linha.

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `app/ia_custo.py` (**novo**) | Preço → dinheiro: `custo_usd`, `em_brl`, `registrar`. Não sabe HTTP nem SQL (delega a `db`). |
| `app/config.py` | `PRECOS_IA` e `USD_BRL`, com override por variável de ambiente. |
| `app/db.py` | Tabela `ia_uso` + `registrar_ia_uso`/`listar_ia_uso`; coluna `excluido` nas duas tabelas + `excluir_candidato`/`excluir_digest`/`listar_excluidos`; filtro padrão no `listar_candidatos`. |
| `app/resumo_diario.py` | `_post` isolado + contabilização dentro de `claude()` + parâmetro `acao`. |
| `app/audio.py` | Contabilização do TTS por caractere. |
| `app/dossie.py` | `corpus_do_tema` com `id`/`origem` e filtro de excluídos; `normalizar_titulo`; `casar_titulo`; `painel`. |
| `app/site_web.py` | Render da aba 🧠: ✕ nos blocos, riscado, "Estudos lidos", "Fora da memória", "Refazer este tema", e a página de confirmação. |
| `app/serve.py` | Rotas GET (monta o painel só na aba dossiê) e POST (confirmar, excluir, devolver, refazer tema). |

Testes novos: `app/tests/test_ia_custo.py`, `app/tests/test_ia_uso.py`, `app/tests/test_excluir_corpus.py`, `app/tests/test_excluir_corpus_ui.py`.

---

# PARTE 1 — O LEDGER (tasks 1 a 5)

Vem primeiro por ser menor e não depender de nada da parte 2.

---

### Task 1: Preço em `config` e o cálculo em `ia_custo`

**Files:**
- Create: `app/ia_custo.py`
- Modify: `app/config.py` (no fim do arquivo, junto de `TTS_MODEL`/`TTS_VOICE`, linha ~215)
- Test: `app/tests/test_ia_custo.py`

**Interfaces:**
- Consumes: nada.
- Produces: `ia_custo.custo_usd(modelo, tokens_in, tokens_out=0) -> float`; `ia_custo.em_brl(usd) -> float`; `config.PRECOS_IA: dict[str, tuple[float, float]]`; `config.USD_BRL: float`.

- [ ] **Step 1: Write the failing test**

Crie `app/tests/test_ia_custo.py`:

```python
"""Preço de IA -> dinheiro. O ledger guarda TOKENS; o custo é calculado na leitura, então
preço errado (ou preço que mudou) é recálculo, não perda: a história inteira se revaloriza.
Standalone: python3 app/tests/test_ia_custo.py"""
import importlib
import os
import sys
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_ia_custo -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ia_custo'`.

- [ ] **Step 3: Write minimal implementation**

Em `app/config.py`, logo depois de `TTS_VOICE` (linha ~215):

```python
# ─── Preços de IA (para o ledger de custos) ───────────────────
# US$ por 1M de unidades: (entrada, saída). Para o TTS a unidade é o CARACTERE.
# ⚠️ CONFERIR nas páginas de preço da Anthropic e da OpenAI — preço errado erra a conta
# toda, e essa conta vira preço de assinatura. Dá pra corrigir sem deploy pela env
# DSCURSO_PRECOS_IA (JSON: {"modelo": [entrada, saida]}).
_PRECOS_PADRAO = {
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8": (15.0, 75.0),
    "tts-1-hd": (30.0, 0.0),
    "tts-1": (15.0, 0.0),
}


def _precos_ia():
    precos = dict(_PRECOS_PADRAO)
    bruto = os.environ.get("DSCURSO_PRECOS_IA")
    if bruto:
        try:
            for k, v in (json.loads(bruto) or {}).items():
                precos[k] = (float(v[0]), float(v[1]))
        except Exception as e:      # env quebrada não pode derrubar o boot do site
            print(f"[config] DSCURSO_PRECOS_IA ignorada ({e})", flush=True)
    return precos


PRECOS_IA = _precos_ia()

# Cotação fixa. Média basta: a decisão que esse número sustenta (repassar no preço) não
# muda com 3% de câmbio. A tela sempre mostra qual cotação usou.
try:
    USD_BRL = float(os.environ.get("DSCURSO_USD_BRL") or 5.50)
except ValueError:
    USD_BRL = 5.50
```

Confirme que `config.py` já importa `json` e `os` no topo; se `json` não estiver lá, adicione o import.

Crie `app/ia_custo.py`:

```python
"""Tokens -> dinheiro.

O ledger (`db.ia_uso`) guarda só o CRU: modelo e contagem de unidades. O custo é
calculado aqui, na leitura, a partir de `config.PRECOS_IA`. Consequência que vale o
desenho: preço que eu errei hoje, ou preço que a Anthropic mudar amanhã, é **recálculo** —
a história inteira se revaloriza sozinha. Custo congelado na linha contaminaria os
números para sempre.

Por que não pedir o valor pronto para a API: a resposta das mensagens traz `usage` em
tokens e nenhum campo de dinheiro. Existe a Admin API de custo, mas ela vem agregada por
dia e modelo — sabe quanto gastou de Sonnet na terça, não sabe o que é um dossiê.
"""
import config

_SEM_PRECO = set()          # avisa uma vez por modelo, não a cada chamada


def custo_usd(modelo, tokens_in, tokens_out=0):
    """US$ de uma linha do ledger. Modelo sem preço vira 0.0 + aviso no log: a tela de
    custos não pode cair porque entrou um modelo novo."""
    preco = config.PRECOS_IA.get(modelo)
    if not preco:
        if modelo not in _SEM_PRECO:
            _SEM_PRECO.add(modelo)
            print(f"[custo] modelo sem preço em PRECOS_IA: {modelo}", flush=True)
        return 0.0
    p_in, p_out = preco
    return (tokens_in or 0) * p_in / 1e6 + (tokens_out or 0) * p_out / 1e6


def em_brl(usd):
    return (usd or 0.0) * config.USD_BRL
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_ia_custo -v`
Expected: PASS (12 testes).

- [ ] **Step 5: Commit**

```bash
git add app/ia_custo.py app/config.py app/tests/test_ia_custo.py
git commit -m "feat(custos): preco por modelo no config e o calculo em ia_custo"
```

---

### Task 2: A tabela `ia_uso` e as funções de banco

**Files:**
- Modify: `app/db.py` (bloco `CREATE TABLE` dentro de `init()`, antes do fechamento na linha ~279; lista `_TABELAS` na linha ~293; funções novas no fim do arquivo)
- Test: `app/tests/test_ia_uso.py`

**Interfaces:**
- Consumes: nada.
- Produces: `db.registrar_ia_uso(acao, modelo, tokens_in, tokens_out=0, chamadas=1) -> None`; `db.listar_ia_uso() -> list[dict]` (mais novo primeiro), cada dict com `acao`, `modelo`, `tokens_in`, `tokens_out`, `chamadas`, `quando`.

- [ ] **Step 1: Write the failing test**

Crie `app/tests/test_ia_uso.py`:

```python
"""Ledger de uso de IA: a tabela e quem escreve nela.

Pedido do Diego (2026-08-12): saber quanto custa cada coisa pra repassar na precificação.
O sistema tem só DOIS pontos pagos — `resumo_diario.claude()` e `audio.narrar()` —, então
instrumentar os dois mede tudo. Standalone: python3 app/tests/test_ia_uso.py"""
import io
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_ia_uso -v`
Expected: FAIL — `AttributeError: module 'db' has no attribute 'registrar_ia_uso'`, e o teste de RLS falha apontando `{'ia_uso'}` depois que a tabela existir.

- [ ] **Step 3: Write minimal implementation**

Em `app/db.py`, dentro do `executescript` do `init()`, depois do bloco `avisos_renovacao` (linha ~278):

```sql
            CREATE TABLE IF NOT EXISTS ia_uso (
                id TEXT PRIMARY KEY,
                quando TEXT,
                acao TEXT DEFAULT '',
                modelo TEXT DEFAULT '',
                tokens_in INTEGER DEFAULT 0,
                tokens_out INTEGER DEFAULT 0,
                chamadas INTEGER DEFAULT 1
            );
```

Na lista `_TABELAS` (linha ~293), acrescente `"ia_uso"` ao fim.

No fim de `db.py`:

```python
def registrar_ia_uso(acao, modelo, tokens_in, tokens_out=0, chamadas=1):
    """Uma linha por chamada paga. Guarda só o CRU (unidades); dinheiro é calculado na
    leitura por `ia_custo.custo_usd`, pra preço errado virar recálculo e não perda."""
    import secrets
    from datetime import datetime
    with _conn() as c:
        c.execute("""INSERT INTO ia_uso (id,quando,acao,modelo,tokens_in,tokens_out,chamadas)
                     VALUES (?,?,?,?,?,?,?)""",
                  (secrets.token_hex(8), datetime.now().isoformat(), acao or "",
                   modelo or "", int(tokens_in or 0), int(tokens_out or 0),
                   int(chamadas or 1)))


def listar_ia_uso():
    with _conn() as c:
        return [dict(r) for r in
                c.execute("SELECT * FROM ia_uso ORDER BY quando DESC").fetchall()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_ia_uso -v`
Expected: PASS (4 testes).

- [ ] **Step 5: Commit**

```bash
git add app/db.py app/tests/test_ia_uso.py
git commit -m "feat(custos): tabela ia_uso, com RLS coberta por teste"
```

---

### Task 3: `claude()` passa a gravar o uso

**Files:**
- Modify: `app/resumo_diario.py:47-69` (a função `claude`)
- Modify: `app/ia_custo.py` (função `registrar`)
- Test: `app/tests/test_ia_uso.py` (acrescentar classes)

**Interfaces:**
- Consumes: `db.registrar_ia_uso` (Task 2).
- Produces: `ia_custo.registrar(acao, modelo, unidades_in, unidades_out=0, chamadas=1) -> None` (nunca levanta); `resumo_diario._post(body) -> dict` (o POST isolado, que os testes substituem); `resumo_diario.claude(model, prompt, system="", max_tokens=2000, cont=4, acao="")`.

- [ ] **Step 1: Write the failing test**

Acrescente a `app/tests/test_ia_uso.py`, antes do `if __name__`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_ia_uso -v`
Expected: FAIL — `AttributeError: module 'resumo_diario' has no attribute '_post'`.

- [ ] **Step 3: Write minimal implementation**

Acrescente ao fim de `app/ia_custo.py`:

```python
def registrar(acao, modelo, unidades_in, unidades_out=0, chamadas=1):
    """Grava uma linha do ledger. NUNCA levanta: perder uma linha de custo é aceitável,
    perder o estudo do dia não é."""
    try:
        import db
        db.init()
        db.registrar_ia_uso(acao or "desconhecido", modelo, unidades_in,
                            unidades_out, chamadas)
    except Exception as e:
        print(f"[custo] não registrei o uso ({acao}): {e}", flush=True)
```

Em `app/resumo_diario.py`, substitua a função `claude` (linhas 47-69) por:

```python
def _post(body):
    """O POST isolado — é o ponto que os testes substituem pra provar a contabilidade
    sem rede."""
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=json.dumps(body).encode("utf-8"),
        method="POST", headers={"x-api-key": KEY, "anthropic-version": "2023-06-01",
                                "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


def claude(model, prompt, system="", max_tokens=2000, cont=4, acao=""):
    """Chama a API. Se a resposta bater o teto de tokens (stop_reason='max_tokens'),
    continua automaticamente de onde parou — garante que a aula NUNCA é cortada.

    `acao` é o rótulo do ledger de custos (dossie, kit, boletim...). Uma linha por
    chamada de `claude`, somando o laço de continuação: 5 idas à API são UM trabalho.
    """
    msgs = [{"role": "user", "content": prompt}]
    partes = []
    tin = tout = idas = 0
    try:
        for _ in range(cont + 1):
            body = {"model": model, "max_tokens": max_tokens, "messages": msgs}
            if system:
                body["system"] = system
            d = _post(body)
            uso = d.get("usage") or {}
            tin += int(uso.get("input_tokens") or 0)
            tout += int(uso.get("output_tokens") or 0)
            idas += 1
            chunk = "".join(b.get("text", "") for b in d.get("content", []))
            partes.append(chunk)
            if d.get("stop_reason") != "max_tokens":
                break  # terminou naturalmente
            # truncou -> pede continuação exata
            msgs.append({"role": "assistant", "content": chunk})
            msgs.append({"role": "user", "content": "Continue EXATAMENTE de onde parou, sem repetir nada nem recomeçar."})
    finally:
        # `finally`: se a 2ª ida estourar, a 1ª já foi cobrada pela Anthropic do mesmo
        # jeito — o que foi pago tem que aparecer na conta.
        if idas:
            import ia_custo
            ia_custo.registrar(acao or "desconhecido", model, tin, tout, idas)
    return "".join(partes).strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_ia_uso -v`
Expected: PASS (10 testes).

- [ ] **Step 5: Rode a suíte inteira** — `claude()` é o coração de tudo

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -5`
Expected: OK, mesmo número de falhas que antes de começar (zero).

- [ ] **Step 6: Commit**

```bash
git add app/resumo_diario.py app/ia_custo.py app/tests/test_ia_uso.py
git commit -m "feat(custos): claude() grava tokens no ledger, somando o laco de continuacao"
```

---

### Task 4: Rotular os pontos de chamada

**Files:**
- Modify: `app/dossie.py:118`, `app/audio.py:38`, `app/content.py:236,239,242`, `app/curadoria.py:169,325,350,447`, `app/resumo_diario.py:120,142,147,181,282`, `app/triage.py:76`
- Test: `app/tests/test_ia_uso.py` (acrescentar classe)

**Interfaces:**
- Consumes: `resumo_diario.claude(..., acao=...)` (Task 3).
- Produces: nada de novo; só rótulos corretos no ledger.

- [ ] **Step 1: Write the failing test**

Acrescente a `app/tests/test_ia_uso.py`, antes do `if __name__`:

```python
class TestRotulosNosCaminhosReais(unittest.TestCase):
    """Não basta o parâmetro existir — o que importa é o ponto de chamada REAL passar o
    rótulo. Com `_post` substituído dá pra rodar o caminho de verdade sem rede.

    (Lição da fatia anterior do item 33: grep no fonte não prova call site.)"""

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
        import importlib, triage
        importlib.reload(triage)
        triage.taggear([{"titulo": "T", "resumo": "r"}])
        self.assertEqual(self._acoes(), ["triagem"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_ia_uso.TestRotulosNosCaminhosReais -v`
Expected: FAIL — as ações saem como `desconhecido`.

- [ ] **Step 3: Write minimal implementation**

Acrescente `acao=` em cada chamada. A lista completa, com o rótulo de cada uma:

| Arquivo:linha | Chamada | `acao=` |
|---|---|---|
| `dossie.py:118` | `claude(SONNET, p, system=SYS, max_tokens=4000)` | `"dossie"` |
| `audio.py:38` | `resumo_diario.claude(...SONNET..., system=_SISTEMA, max_tokens=800)` | `"audio_roteiro"` |
| `content.py:236` | `claude(SONNET, _prompt_gancho(a), ...)` | `"kit"` |
| `content.py:239` | `claude(HAIKU, _prompt_grafico(a), max_tokens=300)` | `"grafico"` |
| `content.py:242` | `claude(HAIKU, _prompt_titulo(a), max_tokens=80)` | `"titulo"` |
| `curadoria.py:169` | `claude(SONNET, content._prompt_gancho(a), ...)` | `"kit"` |
| `curadoria.py:325` | `claude(HAIKU, p, max_tokens=1500)` | `"perguntas"` |
| `curadoria.py:350` | `claude(mdl, "Resuma ESTE estudo...", ...)` | `"resumo_estudo"` |
| `curadoria.py:447` | `claude(HAIKU, content._prompt_titulo_do_texto(a), max_tokens=80)` | `"titulo"` |
| `resumo_diario.py:120` | `claude(HAIKU, f"Tema do médico...")` | `"triagem"` |
| `resumo_diario.py:142` | `claude(OPUS, ...SYS_APROF...)` | `"boletim"` |
| `resumo_diario.py:147` | `claude(SONNET, ...SYS_MENC...)` | `"boletim"` |
| `resumo_diario.py:181` | `claude(OPUS, ...SYS_CURSO...)` (`_gerar_aula`) | `"aula"` |
| `resumo_diario.py:282` | `claude(OPUS, "Resuma ESTE estudo...")` (`gerar_texto_do_artigo`) | `"resumo_estudo"` |
| `triage.py:76` | `claude(HAIKU, p, system=SYS, max_tokens=900)` | `"triagem"` |

Exemplo do formato (`dossie.py:118`):

```python
    return lambda p: claude(SONNET, p, system=SYS, max_tokens=4000, acao="dossie")
```

E em `audio.py:38`:

```python
    return resumo_diario.claude(resumo_diario.SONNET,
                                "Faça o roteiro de áudio deste estudo:\n\n" + material,
                                system=_SISTEMA, max_tokens=800, acao="audio_roteiro").strip()
```

Confira ao fim: `grep -n "claude(" app/*.py | grep -v "acao=" | grep -v "def claude"` não deve devolver nenhuma chamada de geração (só a definição e imports).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_ia_uso -v`
Expected: PASS (14 testes).

- [ ] **Step 5: Commit**

```bash
git add app/dossie.py app/audio.py app/content.py app/curadoria.py app/resumo_diario.py app/triage.py app/tests/test_ia_uso.py
git commit -m "feat(custos): rotula cada ponto de chamada de IA para o ledger"
```

---

### Task 5: O TTS do áudio entra no ledger

**Files:**
- Modify: `app/audio.py:44-52` (`narrar`)
- Test: `app/tests/test_ia_uso.py` (acrescentar classe)

**Interfaces:**
- Consumes: `ia_custo.registrar` (Task 3).
- Produces: nada de novo.

- [ ] **Step 1: Write the failing test**

Acrescente a `app/tests/test_ia_uso.py`, antes do `if __name__`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_ia_uso.TestTtsNoLedger -v`
Expected: FAIL — `AttributeError: module 'audio' has no attribute '_post_tts'`.

- [ ] **Step 3: Write minimal implementation**

Em `app/audio.py`, substitua `narrar` (linhas 44-52):

```python
def _post_tts(body):
    """POST isolado — ponto de substituição dos testes, mesmo padrão do
    `resumo_diario._post`."""
    req = urllib.request.Request("https://api.openai.com/v1/audio/speech", data=body,
                                 headers={"Authorization": "Bearer " + config.OPENAI_API_KEY,
                                          "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def narrar(texto):
    """Texto -> mp3 bytes via OpenAI TTS. Requer config.OPENAI_API_KEY.

    O TTS é cobrado por caractere e a resposta não traz contagem nenhuma: o que entra no
    ledger é o tamanho do texto REALMENTE enviado — ou seja, já cortado em 4000.
    """
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY não configurada")
    falado = (texto or "")[:4000]
    body = json.dumps({"model": config.TTS_MODEL, "voice": config.TTS_VOICE,
                       "input": falado, "response_format": "mp3"}).encode()
    try:
        return _post_tts(body)
    finally:
        import ia_custo
        ia_custo.registrar("audio_tts", config.TTS_MODEL, len(falado), 0, 1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_ia_uso -v`
Expected: PASS (17 testes).

- [ ] **Step 5: Commit**

```bash
git add app/audio.py app/tests/test_ia_uso.py
git commit -m "feat(custos): TTS do audio entra no ledger, pelo texto que foi mandado"
```

---

# PARTE 2 — TIRAR ESTUDO DA MEMÓRIA (tasks 6 a 10)

---

### Task 6: A coluna `excluido` e o filtro no banco

**Files:**
- Modify: `app/db.py` — `CREATE TABLE curadoria_candidatos` (linha ~183) e `digests` (linha ~102); `_migrar_colunas` (linha ~316); `listar_candidatos` (linha ~1026); funções novas no fim
- Test: `app/tests/test_excluir_corpus.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `db.listar_candidatos(status=None, tema=None, tipo=None, incluir_excluidos=False)` — esconde `excluido='tudo'` por padrão;
  - `db.excluir_candidato(cand_id, escopo) -> None` (escopo em `''|'memoria'|'tudo'`, senão `ValueError`);
  - `db.excluir_digest(tema_slug, data, escopo) -> None` (mesma validação);
  - `db.listar_excluidos(tema) -> list[dict]` com `origem` (`'candidato'|'digest'`), `ref`, `titulo`, `fonte`, `data`, `escopo`.

**Formato do `ref`:** candidato → o `id`; digest → `f"{tema_slug}|{data}"` (a tabela `digests` não tem `id`; a PK é `(data, tema_slug)`).

- [ ] **Step 1: Write the failing test**

Crie `app/tests/test_excluir_corpus.py`:

```python
"""Tirar um estudo da MEMÓRIA do dossiê (item 33, parte A).

Diego, lendo o dossiê: *"tirar algum dado de estudo que não faça sentido"*. Como o dossiê
é reconstruído do zero, edição manual seria apagada sem aviso — então o conserto durável é
tirar o estudo do CORPUS, pra toda reconstrução futura já ignorá-lo.

Dois escopos, escolhidos no clique: 'memoria' (sai só do dossiê) e 'tudo' (sai também da
fila de envio). Standalone: python3 app/tests/test_excluir_corpus.py"""
import os
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


def _cand(chave, titulo="Estudo X", tema="Obesidade", tipo="varredura"):
    return {"chave": chave, "titulo": titulo, "tema": tema, "tipo": tipo,
            "fonte": "NEJM", "data": "2026-03-01", "doi": "10.1/" + chave,
            "url": "", "abstract": "abstract do estudo", "pergunta": "", "score": 7,
            "citacoes": 0, "tags": []}


class _Base(unittest.TestCase):
    def setUp(self):
        self.snap = _snapshot_env()
        self.tmp = tempfile.mkdtemp()
        self.db = _reload_db(self.tmp)

    def tearDown(self):
        _restore_db(self.snap)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _id_de(self, titulo):
        return next(c["id"] for c in self.db.listar_candidatos(incluir_excluidos=True)
                    if c["titulo"] == titulo)


class TestFiltroNoListarCandidatos(_Base):
    """O filtro mora DENTRO do listar_candidatos, e não espalhado pelos 5 consumidores —
    é a classe de erro que vazou o `tipo='corpus'` pro picker do 🔁."""

    def setUp(self):
        super().setUp()
        self.db.salvar_candidatos([_cand("k1", "Fica"), _cand("k2", "Sai da fila"),
                                   _cand("k3", "So da memoria")])

    def test_escopo_tudo_some_da_listagem_padrao(self):
        self.db.excluir_candidato(self._id_de("Sai da fila"), "tudo")
        titulos = [c["titulo"] for c in self.db.listar_candidatos()]
        self.assertNotIn("Sai da fila", titulos)

    def test_escopo_memoria_CONTINUA_na_fila(self):
        """'memoria' tira do dossiê e só. Some daqui também seria tirar da fila sem ele
        ter pedido."""
        self.db.excluir_candidato(self._id_de("So da memoria"), "memoria")
        titulos = [c["titulo"] for c in self.db.listar_candidatos()]
        self.assertIn("So da memoria", titulos)

    def test_o_resto_continua_aparecendo(self):
        self.db.excluir_candidato(self._id_de("Sai da fila"), "tudo")
        self.assertIn("Fica", [c["titulo"] for c in self.db.listar_candidatos()])

    def test_incluir_excluidos_traz_todos(self):
        self.db.excluir_candidato(self._id_de("Sai da fila"), "tudo")
        self.assertEqual(len(self.db.listar_candidatos(incluir_excluidos=True)), 3)

    def test_filtro_convive_com_os_outros(self):
        self.db.excluir_candidato(self._id_de("Sai da fila"), "tudo")
        r = self.db.listar_candidatos(status="novo", tema="Obesidade", tipo="varredura")
        self.assertEqual(sorted(c["titulo"] for c in r), ["Fica", "So da memoria"])

    def test_devolver_traz_de_volta(self):
        cid = self._id_de("Sai da fila")
        self.db.excluir_candidato(cid, "tudo")
        self.db.excluir_candidato(cid, "")
        self.assertIn("Sai da fila", [c["titulo"] for c in self.db.listar_candidatos()])

    def test_escopo_invalido_levanta_em_vez_de_gravar_lixo(self):
        """Escopo com typo gravado no banco nunca filtraria nada, e o Diego acharia que
        excluiu."""
        with self.assertRaises(ValueError):
            self.db.excluir_candidato(self._id_de("Fica"), "memória")


class TestExclusaoSobreviveAVarredura(_Base):
    """`excluido` é coluna à parte: o upsert de `salvar_candidatos` atualiza os campos do
    paper e a exclusão continua de pé — inclusive na promoção corpus -> varredura."""

    def test_o_mesmo_paper_varrido_de_novo_continua_excluido(self):
        self.db.salvar_candidatos([_cand("k9", "Repetido", tipo="corpus")])
        self.db.excluir_candidato(self._id_de("Repetido"), "tudo")
        self.db.salvar_candidatos([_cand("k9", "Repetido", tipo="varredura")])
        self.assertEqual(self.db.listar_candidatos(), [])
        linha = self.db.listar_candidatos(incluir_excluidos=True)[0]
        self.assertEqual(linha["tipo"], "varredura")     # promoveu
        self.assertEqual(linha["excluido"], "tudo")      # e continua fora


class TestPortalNaoMuda(_Base):
    """`listar_por_tema` serve o portal do assinante (serve.py:653-657). Estudo enviado
    não se des-envia: a exclusão de um digest vale só dentro do corpus do dossiê."""

    def setUp(self):
        super().setUp()
        self.db.registrar_digest(
            {"tema": "Obesidade", "doi": "10.1/d", "fonte": "NEJM", "url": "",
             "titulo": "orig"},
            {"titulo_pt": "Estudo enviado", "resumo": "r", "gancho": "g", "grafico": None},
            None, data="2026-07-19")

    def test_digest_excluido_da_memoria_continua_no_portal(self):
        self.db.excluir_digest("obesidade", "2026-07-19", "memoria")
        titulos = [d["titulo_pt"] for d in self.db.listar_por_tema("obesidade")]
        self.assertEqual(titulos, ["Estudo enviado"])

    def test_digest_excluido_com_escopo_tudo_TAMBEM_continua_no_portal(self):
        self.db.excluir_digest("obesidade", "2026-07-19", "tudo")
        self.assertEqual(len(self.db.listar_por_tema("obesidade")), 1)

    def test_escopo_invalido_no_digest_tambem_levanta(self):
        with self.assertRaises(ValueError):
            self.db.excluir_digest("obesidade", "2026-07-19", "sim")


class TestListarExcluidos(_Base):
    def test_junta_candidato_e_digest_do_tema(self):
        self.db.salvar_candidatos([_cand("k1", "Candidato fora")])
        self.db.excluir_candidato(self._id_de("Candidato fora"), "memoria")
        self.db.registrar_digest(
            {"tema": "Obesidade", "doi": "10.1/d", "fonte": "NEJM", "url": "",
             "titulo": "orig"},
            {"titulo_pt": "Digest fora", "resumo": "r", "gancho": "g", "grafico": None},
            None, data="2026-07-19")
        self.db.excluir_digest("obesidade", "2026-07-19", "memoria")
        ex = self.db.listar_excluidos("Obesidade")
        self.assertEqual(sorted(e["titulo"] for e in ex), ["Candidato fora", "Digest fora"])
        self.assertEqual(sorted(e["origem"] for e in ex), ["candidato", "digest"])
        self.assertEqual({e["escopo"] for e in ex}, {"memoria"})

    def test_ref_do_digest_carrega_slug_e_data(self):
        self.db.registrar_digest(
            {"tema": "Obesidade", "doi": "10.1/d", "fonte": "NEJM", "url": "",
             "titulo": "orig"},
            {"titulo_pt": "Digest fora", "resumo": "r", "gancho": "g", "grafico": None},
            None, data="2026-07-19")
        self.db.excluir_digest("obesidade", "2026-07-19", "memoria")
        self.assertEqual(self.db.listar_excluidos("Obesidade")[0]["ref"],
                         "obesidade|2026-07-19")

    def test_tema_sem_exclusao_devolve_lista_vazia(self):
        self.assertEqual(self.db.listar_excluidos("Longevidade"), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_excluir_corpus -v`
Expected: FAIL — `AttributeError: module 'db' has no attribute 'excluir_candidato'`.

- [ ] **Step 3: Write minimal implementation**

Em `app/db.py`:

1. No `CREATE TABLE ... curadoria_candidatos` (linha ~188), acrescente a coluna ao fim da lista, depois de `tags TEXT DEFAULT '[]'`:

```sql
                status TEXT DEFAULT 'novo', criado_em TEXT, tags TEXT DEFAULT '[]',
                excluido TEXT DEFAULT ''
```

2. No `CREATE TABLE ... digests` (linha ~114), antes do `PRIMARY KEY`:

```sql
                criado_em TEXT,
                excluido TEXT DEFAULT '',
                PRIMARY KEY (data, tema_slug)
```

3. Em `_migrar_colunas` (junto das outras chamadas, linha ~318) — é o que cobre o Postgres de produção, criado antes destas colunas:

```python
        _add_coluna(c, "curadoria_candidatos", "excluido", "TEXT DEFAULT ''")
        _add_coluna(c, "digests", "excluido", "TEXT DEFAULT ''")
```

4. Substitua `listar_candidatos` (linha 1026):

```python
def listar_candidatos(status=None, tema=None, tipo=None, incluir_excluidos=False):
    """Candidatos da curadoria.

    O filtro de excluídos mora AQUI, e não nos cinco consumidores (agenda, triagem,
    clássicos, backfill de tags, picker do 🔁): esquecer um deles é exatamente como o
    `tipo='corpus'` vazou pro picker. `excluido='memoria'` continua aparecendo — esse
    escopo tira do dossiê, não da fila.
    """
    q = "SELECT * FROM curadoria_candidatos"
    conds, params = [], []
    if status:
        conds.append("status=?"); params.append(status)
    if tema:
        conds.append("tema=?"); params.append(tema)
    if tipo:
        conds.append("tipo=?"); params.append(tipo)
    if not incluir_excluidos:
        conds.append("(excluido IS NULL OR excluido <> 'tudo')")
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY tema, score DESC, criado_em DESC"
    with _conn() as c:
        return [dict(r) for r in c.execute(q, params).fetchall()]
```

5. No fim de `db.py`:

```python
ESCOPOS_EXCLUSAO = ("", "memoria", "tudo")


def _valida_escopo(escopo):
    """Escopo com typo gravado no banco nunca filtraria nada — e o Diego acharia que
    excluiu. Falha fechada."""
    e = escopo or ""
    if e not in ESCOPOS_EXCLUSAO:
        raise ValueError(f"escopo inválido: {escopo!r} (use {ESCOPOS_EXCLUSAO})")
    return e


def excluir_candidato(cand_id, escopo):
    """Tira (ou devolve, com escopo='') um candidato da memória do dossiê."""
    e = _valida_escopo(escopo)
    with _conn() as c:
        c.execute("UPDATE curadoria_candidatos SET excluido=? WHERE id=?", (e, cand_id))


def excluir_digest(tema_slug, data, escopo):
    """Idem para estudo JÁ ENVIADO. Vale só dentro do corpus do dossiê: `listar_por_tema`
    (o portal do assinante) nunca filtra por esta coluna — não se des-envia um estudo."""
    e = _valida_escopo(escopo)
    with _conn() as c:
        c.execute("UPDATE digests SET excluido=? WHERE tema_slug=? AND data=?",
                  (e, tema_slug, data))


def listar_excluidos(tema):
    """O que está fora da memória neste tema, das duas fontes, para a lista de devolver."""
    with _conn() as c:
        cands = c.execute(
            "SELECT id,titulo,fonte,data,excluido FROM curadoria_candidatos "
            "WHERE tema=? AND excluido IS NOT NULL AND excluido <> '' "
            "ORDER BY titulo", (tema,)).fetchall()
        digs = c.execute(
            "SELECT tema_slug,data,titulo_pt,fonte,excluido FROM digests "
            "WHERE tema=? AND excluido IS NOT NULL AND excluido <> '' "
            "ORDER BY data DESC", (tema,)).fetchall()
    out = [{"origem": "candidato", "ref": r["id"], "titulo": r["titulo"],
            "fonte": r["fonte"], "data": r["data"], "escopo": r["excluido"]}
           for r in cands]
    out += [{"origem": "digest", "ref": f'{r["tema_slug"]}|{r["data"]}',
             "titulo": r["titulo_pt"], "fonte": r["fonte"], "data": r["data"],
             "escopo": r["excluido"]} for r in digs]
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_excluir_corpus -v`
Expected: PASS (16 testes).

- [ ] **Step 5: Rode a suíte inteira** — mexer em `listar_candidatos` toca agenda, triagem e picker

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -5`
Expected: OK, zero falhas.

- [ ] **Step 6: Commit**

```bash
git add app/db.py app/tests/test_excluir_corpus.py
git commit -m "feat(corpus): coluna excluido nas duas fontes e filtro dentro do listar_candidatos"
```

---

### Task 7: `corpus_do_tema` devolve id/origem e respeita a exclusão

**Files:**
- Modify: `app/dossie.py:124-137` (`corpus_do_tema`)
- Test: `app/tests/test_excluir_corpus.py` (acrescentar classe)

**Interfaces:**
- Consumes: `db.listar_candidatos` (esconde `'tudo'`), `db.listar_por_tema` (não filtra nada) — Task 6.
- Produces: `dossie.corpus_do_tema(tema, db_mod=None) -> list[dict]` com as chaves `id`, `origem` (`'candidato'|'digest'`), `titulo`, `fonte`, `data`, `abstract`.

- [ ] **Step 1: Write the failing test**

Acrescente a `app/tests/test_excluir_corpus.py`, antes do `if __name__`:

```python
class TestCorpusDoTema(_Base):
    """O corpus tem DUAS fontes e a exclusão precisa valer nas duas."""

    def setUp(self):
        super().setUp()
        self.db.salvar_candidatos([_cand("k1", "Candidato bom"), _cand("k2", "Candidato ruim")])
        self.db.registrar_digest(
            {"tema": "Obesidade", "doi": "10.1/d", "fonte": "NEJM", "url": "",
             "titulo": "orig"},
            {"titulo_pt": "Enviado bom", "resumo": "r", "gancho": "g", "grafico": None},
            None, data="2026-07-19")
        import importlib, dossie
        importlib.reload(dossie)
        self.dossie = dossie

    def _titulos(self):
        return sorted(e["titulo"] for e in self.dossie.corpus_do_tema("Obesidade", self.db))

    def test_junta_as_duas_fontes(self):
        self.assertEqual(self._titulos(), ["Candidato bom", "Candidato ruim", "Enviado bom"])

    def test_candidato_excluido_da_memoria_sai_do_corpus(self):
        self.db.excluir_candidato(self._id_de("Candidato ruim"), "memoria")
        self.assertEqual(self._titulos(), ["Candidato bom", "Enviado bom"])

    def test_candidato_excluido_de_tudo_tambem_sai_do_corpus(self):
        self.db.excluir_candidato(self._id_de("Candidato ruim"), "tudo")
        self.assertEqual(self._titulos(), ["Candidato bom", "Enviado bom"])

    def test_digest_excluido_da_memoria_sai_do_corpus(self):
        self.db.excluir_digest("obesidade", "2026-07-19", "memoria")
        self.assertEqual(self._titulos(), ["Candidato bom", "Candidato ruim"])

    def test_cada_item_carrega_id_e_origem(self):
        itens = {e["titulo"]: e for e in self.dossie.corpus_do_tema("Obesidade", self.db)}
        self.assertEqual(itens["Candidato bom"]["origem"], "candidato")
        self.assertTrue(itens["Candidato bom"]["id"])
        self.assertEqual(itens["Enviado bom"]["origem"], "digest")
        self.assertEqual(itens["Enviado bom"]["id"], "obesidade|2026-07-19")

    def test_construir_continua_funcionando_com_os_campos_novos(self):
        """`_linha` lê título/fonte/data/abstract; campo extra não pode atrapalhar."""
        estudos = self.dossie.corpus_do_tema("Obesidade", self.db)
        d = self.dossie.construir(
            estudos, gerar_fn=lambda p: '{"blocos":[{"afirmacao":"a","estudos":'
                                        '[{"titulo":"Candidato bom"}]}]}')
        self.assertTrue(d["blocos"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_excluir_corpus.TestCorpusDoTema -v`
Expected: FAIL — `KeyError: 'origem'` / estudos excluídos ainda aparecem.

- [ ] **Step 3: Write minimal implementation**

Substitua `corpus_do_tema` em `app/dossie.py`:

```python
def corpus_do_tema(tema, db_mod=None):
    """Os estudos do tema, das 3 fontes que acumulam: candidatos da varredura e do
    backfill (com o abstract inteiro), estudos já enviados e clássicos bancados.

    Cada item carrega `id` e `origem` — é o que permite a tela oferecer um ✕ que aponta
    para uma linha de verdade do banco, em vez de para um título solto.

    Excluídos ficam de fora: `listar_candidatos` já esconde o escopo 'tudo', e o
    'memoria' é filtrado aqui (ele continua na fila, só não alimenta a memória). Nos
    digests o filtro é SÓ aqui: `listar_por_tema` serve o portal do assinante.
    """
    if db_mod is None:
        import db as db_mod
    fonte = []
    for c in db_mod.listar_candidatos(tema=tema):
        if (c.get("excluido") or "").strip():
            continue
        if (c.get("abstract") or "").strip():
            fonte.append({"id": c.get("id", ""), "origem": "candidato",
                          "titulo": c.get("titulo", ""), "fonte": c.get("fonte", ""),
                          "data": c.get("data", ""), "abstract": c.get("abstract", "")})
    for d in db_mod.listar_por_tema(slug_de(tema, db_mod)):
        if (d.get("excluido") or "").strip():
            continue
        fonte.append({"id": f'{d.get("tema_slug","")}|{d.get("data","")}',
                      "origem": "digest", "titulo": d.get("titulo_pt", ""),
                      "fonte": d.get("fonte", ""), "data": d.get("data", ""),
                      "abstract": d.get("resumo", "")})
    return fonte
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_excluir_corpus tests.test_dossie -v`
Expected: PASS (os 22 do arquivo novo + os de `test_dossie` intactos).

- [ ] **Step 5: Commit**

```bash
git add app/dossie.py app/tests/test_excluir_corpus.py
git commit -m "feat(corpus): corpus_do_tema devolve id/origem e ignora o que foi excluido"
```

---

### Task 8: Casar o título que a IA escreveu com o estudo real

**Files:**
- Modify: `app/dossie.py` (funções novas, depois de `parse`)
- Test: `app/tests/test_excluir_corpus.py` (acrescentar classe)

**Interfaces:**
- Consumes: nada.
- Produces: `dossie.normalizar_titulo(t) -> str`; `dossie.casar_titulo(titulo, corpus) -> dict | None` (o item do corpus).

- [ ] **Step 1: Write the failing test**

Acrescente a `app/tests/test_excluir_corpus.py`, antes do `if __name__`:

```python
class TestCasarTitulo(unittest.TestCase):
    """O dossiê guarda o título COMO A IA ESCREVEU. O ✕ do bloco precisa achar a linha
    real do banco — e, quando não achar, dizer isso em vez de fingir que excluiu."""

    def setUp(self):
        import importlib, dossie
        importlib.reload(dossie)
        self.d = dossie
        self.corpus = [
            {"id": "a", "origem": "candidato",
             "titulo": "Once-Weekly Semaglutide in Adults with Overweight or Obesity"},
            {"id": "b", "origem": "candidato",
             "titulo": "Efeitos da reposição hormonal na densidade óssea"},
            {"id": "c", "origem": "digest", "titulo": "Tirzepatide Once Weekly for Obesity"},
        ]

    def test_titulo_igual_acha(self):
        r = self.d.casar_titulo("Tirzepatide Once Weekly for Obesity", self.corpus)
        self.assertEqual(r["id"], "c")

    def test_ignora_caixa_pontuacao_e_acento(self):
        r = self.d.casar_titulo("EFEITOS DA REPOSICAO HORMONAL NA DENSIDADE OSSEA!",
                                self.corpus)
        self.assertEqual(r["id"], "b")

    def test_titulo_truncado_pela_IA_ainda_acha(self):
        r = self.d.casar_titulo("Once-Weekly Semaglutide in Adults with Over", self.corpus)
        self.assertEqual(r["id"], "a")

    def test_titulo_inexistente_devolve_None(self):
        self.assertIsNone(self.d.casar_titulo("Estudo que a IA inventou", self.corpus))

    def test_prefixo_curto_demais_nao_casa(self):
        """'Once' casaria com meio corpus — casamento frouxo excluiria o estudo errado,
        e o Diego só descobriria na reconstrução seguinte."""
        self.assertIsNone(self.d.casar_titulo("Once", self.corpus))

    def test_ambiguo_devolve_None_em_vez_de_chutar(self):
        corpus = [{"id": "x", "titulo": "Estudo repetido no banco"},
                  {"id": "y", "titulo": "Estudo repetido no banco"}]
        self.assertIsNone(self.d.casar_titulo("Estudo repetido no banco", corpus))

    def test_titulo_vazio_devolve_None(self):
        for t in ("", None, "   "):
            with self.subTest(t=t):
                self.assertIsNone(self.d.casar_titulo(t, self.corpus))

    def test_corpus_vazio_devolve_None(self):
        self.assertIsNone(self.d.casar_titulo("Qualquer coisa", []))

    def test_normalizar_tira_acento_e_pontuacao(self):
        self.assertEqual(self.d.normalizar_titulo("Ação: Reposição — Hormonal!"),
                         "acao reposicao hormonal")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_excluir_corpus.TestCasarTitulo -v`
Expected: FAIL — `AttributeError: module 'dossie' has no attribute 'casar_titulo'`.

- [ ] **Step 3: Write minimal implementation**

Em `app/dossie.py`, depois de `parse` (e acrescente `import re` e `import unicodedata` ao topo):

```python
MIN_PREFIXO = 30      # abaixo disso, "Once" casaria com meio corpus


def normalizar_titulo(t):
    """Minúsculas, sem acento, sem pontuação, espaços colapsados."""
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", t.lower())).strip()


def casar_titulo(titulo, corpus):
    """O estudo do corpus que corresponde ao título escrito pela IA no dossiê, ou None.

    Três degraus: igual depois de normalizar; truncado (um é prefixo do outro, com pelo
    menos MIN_PREFIXO caracteres); nada.

    Ambíguo devolve None de propósito. O que NÃO se pode fazer é chutar — excluir o
    estudo errado é invisível até a reconstrução seguinte, quando a afirmação some sem
    explicação.
    """
    alvo = normalizar_titulo(titulo)
    if not alvo or not corpus:
        return None
    iguais = [e for e in corpus if normalizar_titulo(e.get("titulo")) == alvo]
    if len(iguais) == 1:
        return iguais[0]
    if iguais:
        return None                      # repetido no banco: manda pra lista
    if len(alvo) < MIN_PREFIXO:
        return None
    prefixos = []
    for e in corpus:
        n = normalizar_titulo(e.get("titulo"))
        if len(n) >= MIN_PREFIXO and (n.startswith(alvo) or alvo.startswith(n)):
            prefixos.append(e)
    return prefixos[0] if len(prefixos) == 1 else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_excluir_corpus -v`
Expected: PASS (31 testes).

- [ ] **Step 5: Commit**

```bash
git add app/dossie.py app/tests/test_excluir_corpus.py
git commit -m "feat(corpus): casar o titulo do dossie com o estudo real, sem chutar"
```

---

### Task 9: O painel do tema e as telas

**Files:**
- Modify: `app/dossie.py` (função `painel`)
- Modify: `app/site_web.py:1424-1452` (`_dossie_html`) e `pagina_curadoria` (linha ~1679); função nova `pagina_confirmar_exclusao`
- Test: `app/tests/test_excluir_corpus_ui.py`

**Interfaces:**
- Consumes: `dossie.corpus_do_tema`, `dossie.normalizar_titulo` (Tasks 7-8), `db.listar_excluidos` (Task 6).
- Produces:
  - `dossie.painel(db_mod=None) -> dict[str, dict]` — `{tema: {"corpus": [...sem abstract...], "excluidos": [...]}}`;
  - `site_web._dossie_html(dossies, painel=None, token="")`;
  - `site_web.pagina_confirmar_exclusao(estudo, tema, token) -> str`;
  - `site_web.pagina_curadoria(..., dossies=None, painel=None)`.

- [ ] **Step 1: Write the failing test**

Crie `app/tests/test_excluir_corpus_ui.py`:

```python
"""As telas da exclusão, na aba 🧠 Dossiê. Standalone:
python3 app/tests/test_excluir_corpus_ui.py"""
import importlib
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _dossie(tema="Obesidade", afirmacao="GLP-1 reduz massa magra",
            estudos=("Once-Weekly Semaglutide in Adults with Overweight",)):
    return {"tema": tema, "atualizado_em": "2026-08-12T10:00:00", "n_estudos": 3,
            "conteudo": json.dumps({"blocos": [
                {"afirmacao": afirmacao,
                 "estudos": [{"titulo": t, "fonte": "NEJM", "data": "2026-03"}
                             for t in estudos]}]}, ensure_ascii=False)}


def _painel(corpus=None, excluidos=None, tema="Obesidade"):
    return {tema: {"corpus": corpus if corpus is not None else [
        {"id": "c1", "origem": "candidato",
         "titulo": "Once-Weekly Semaglutide in Adults with Overweight",
         "fonte": "NEJM", "data": "2026-03-01"}],
        "excluidos": excluidos or []}}


class TestDossieHtml(unittest.TestCase):
    def setUp(self):
        import site_web
        importlib.reload(site_web)
        self.sw = site_web

    def test_estudo_do_bloco_ganha_botao_de_tirar_da_memoria(self):
        html = self.sw._dossie_html([_dossie()], _painel(), token="tok")
        self.assertIn("confirmar_exclusao", html)
        self.assertIn("Once-Weekly Semaglutide in Adults with Overweight", html)

    def test_o_aviso_de_que_o_x_nao_e_para_discordar_aparece(self):
        """Sem esse texto o ✕ vira ferramenta de apagar o que contraria a leitura do
        Diego — e a memória vira eco."""
        html = self.sw._dossie_html([_dossie()], _painel(), token="tok")
        self.assertIn("divergência", html)

    def test_estudo_ja_excluido_sai_riscado_e_sem_botao(self):
        ex = [{"origem": "candidato", "ref": "c1",
               "titulo": "Once-Weekly Semaglutide in Adults with Overweight",
               "fonte": "NEJM", "data": "2026-03-01", "escopo": "memoria"}]
        html = self.sw._dossie_html([_dossie()], _painel(corpus=[], excluidos=ex), token="tok")
        self.assertIn("line-through", html)
        self.assertIn("refaça o dossiê", html)

    def test_lista_estudos_lidos_traz_os_dois_escopos(self):
        html = self.sw._dossie_html([_dossie()], _painel(), token="tok")
        self.assertIn("Estudos lidos", html)
        self.assertIn('value="memoria"', html)
        self.assertIn('value="tudo"', html)

    def test_estudo_ja_enviado_so_oferece_tirar_da_memoria(self):
        """Não se des-envia um estudo: o escopo 'tudo' não faz sentido para um digest."""
        corpus = [{"id": "obesidade|2026-07-19", "origem": "digest",
                   "titulo": "Estudo enviado", "fonte": "NEJM", "data": "2026-07-19"}]
        html = self.sw._dossie_html([_dossie()], _painel(corpus=corpus), token="tok")
        self.assertIn('value="memoria"', html)
        self.assertNotIn('value="tudo"', html)

    def test_lista_de_excluidos_tem_devolver(self):
        ex = [{"origem": "candidato", "ref": "c1", "titulo": "Estudo fora",
               "fonte": "NEJM", "data": "2026-03-01", "escopo": "tudo"}]
        html = self.sw._dossie_html([_dossie()], _painel(excluidos=ex), token="tok")
        self.assertIn("Fora da memória", html)
        self.assertIn("devolver_corpus", html)

    def test_botao_de_refazer_so_este_tema(self):
        html = self.sw._dossie_html([_dossie()], _painel(), token="tok")
        self.assertIn("refazer_dossie_tema", html)

    def test_sem_painel_nao_quebra(self):
        """A aba pode ser renderizada sem painel (ex.: outra aba ativa)."""
        html = self.sw._dossie_html([_dossie()], None, token="tok")
        self.assertIn("GLP-1 reduz massa magra", html)

    def test_escapa_titulo_com_html(self):
        d = _dossie(estudos=("<script>alert(1)</script>",))
        html = self.sw._dossie_html([d], _painel(corpus=[]), token="tok")
        self.assertNotIn("<script>alert(1)</script>", html)


class TestPaginaConfirmar(unittest.TestCase):
    def setUp(self):
        import site_web
        importlib.reload(site_web)
        self.sw = site_web
        self.estudo = {"id": "c1", "origem": "candidato", "titulo": "Estudo de verdade",
                       "fonte": "NEJM", "data": "2026-03-01"}

    def test_mostra_o_estudo_que_casou_e_os_dois_botoes(self):
        html = self.sw.pagina_confirmar_exclusao(self.estudo, "Obesidade", "tok")
        self.assertIn("Estudo de verdade", html)
        self.assertIn('value="memoria"', html)
        self.assertIn('value="tudo"', html)
        self.assertIn("c1", html)

    def test_tem_saida_sem_excluir(self):
        html = self.sw.pagina_confirmar_exclusao(self.estudo, "Obesidade", "tok")
        self.assertIn("Cancelar", html)

    def test_digest_nao_oferece_tirar_da_fila(self):
        est = {"id": "obesidade|2026-07-19", "origem": "digest", "titulo": "Enviado",
               "fonte": "NEJM", "data": "2026-07-19"}
        html = self.sw.pagina_confirmar_exclusao(est, "Obesidade", "tok")
        self.assertIn('value="memoria"', html)
        self.assertNotIn('value="tudo"', html)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_excluir_corpus_ui -v`
Expected: FAIL — `TypeError: _dossie_html() takes 1 positional argument but 3 were given`.

- [ ] **Step 3: Write minimal implementation**

**3a.** Em `app/dossie.py`, no fim:

```python
def painel(db_mod=None, temas=None):
    """O material da aba 🧠: por tema, o corpus lido (sem os abstracts — a tela não
    precisa deles, e eles são o peso da consulta) e o que está fora da memória.

    Montado só quando a aba do dossiê está aberta: são centenas de linhas por tema.
    """
    if db_mod is None:
        import db as db_mod
    if temas is None:
        import area_estudo
        temas = area_estudo.areas()
    out = {}
    for t in temas:
        corpus = [{k: e.get(k, "") for k in ("id", "origem", "titulo", "fonte", "data")}
                  for e in corpus_do_tema(t, db_mod)]
        out[t] = {"corpus": corpus, "excluidos": db_mod.listar_excluidos(t)}
    return out
```

**3b.** Em `app/site_web.py`, substitua `_dossie_html` (linhas 1424-1452):

```python
_AVISO_X = ("tirar da memória — estudo fora do tema, duplicado ou fraco. Não use pra "
            "discordar do achado: a divergência entre estudos é o que o dossiê existe "
            "pra guardar.")


def _form_curadoria(token, acao, campos, label, classe="actbtn ghost", titulo=""):
    """Um botão POST da /curadoria. Os campos extras viajam em hidden."""
    ocultos = "".join(f'<input type="hidden" name="{_esc(k)}" value="{_esc(v)}">'
                      for k, v in campos.items())
    tit = f' title="{_esc(titulo)}"' if titulo else ""
    return (f'<form method="post" action="/curadoria" style="display:inline">'
            f'<input type="hidden" name="token" value="{_esc(token)}">'
            f'<input type="hidden" name="acao" value="{_esc(acao)}">{ocultos}'
            f'<button class="{classe}" type="submit"{tit}>{label}</button></form>')


def _botoes_escopo(token, item, tema):
    """Os dois escopos, decisão do Diego de escolher no clique. Estudo já enviado só
    oferece 'memória': não se des-envia."""
    campos = {"origem": item.get("origem", ""), "ref": item.get("id") or item.get("ref", ""),
              "tema": tema}
    b = _form_curadoria(token, "excluir_corpus", dict(campos, escopo="memoria"),
                        "só da memória", titulo=_AVISO_X)
    if item.get("origem") != "digest":
        b += " " + _form_curadoria(token, "excluir_corpus", dict(campos, escopo="tudo"),
                                   "memória + fila", titulo=_AVISO_X)
    return b


def _dossie_html(dossies, painel=None, token=""):
    """O dossiê é AFIRMAÇÃO + os estudos que a sustentam — nunca prosa. A tela mostra
    exatamente isso, pra o Diego conseguir julgar se a memória tem lastro (e não só se
    o texto ficou bonito).

    Cada estudo citado ganha um ✕ que abre a confirmação (o título do dossiê é o que a IA
    escreveu; a confirmação mostra qual estudo REAL casou). Estudo já tirado da memória
    aparece riscado, não some: o dossiê guardado ainda é o antigo, e sumir faria parecer
    que a memória já foi refeita sem ele.
    """
    import json as _json
    import dossie as _dossie
    if not dossies:
        return ('<p class="hint">Nenhum dossiê ainda. Rode <strong>🧠 Construir o dossiê</strong> '
                'em Ferramentas — ele lê os estudos da base e organiza a memória por tema.</p>')
    painel = painel or {}
    cards = []
    for d in dossies:
        tema = d.get("tema") or ""
        dados = painel.get(tema) or {}
        corpus, excluidos = dados.get("corpus") or [], dados.get("excluidos") or []
        fora = {_dossie.normalizar_titulo(e.get("titulo")) for e in excluidos}
        try:
            blocos = (_json.loads(d.get("conteudo") or "{}") or {}).get("blocos") or []
        except Exception:
            blocos = []
        quando = (d.get("atualizado_em") or "")[:10]

        def _estudo_linha(e):
            rot = _esc(f'{e.get("titulo","")} ({e.get("fonte","")} {e.get("data","")})')
            if _dossie.normalizar_titulo(e.get("titulo")) in fora:
                return (f'<span style="text-decoration:line-through;opacity:.55">{rot}</span> '
                        f'<span class="hint">fora da memória — refaça o dossiê (🧠) pra ver '
                        f'o efeito nas afirmações</span>')
            botao = _form_curadoria(token, "confirmar_exclusao",
                                    {"tema": tema, "titulo": e.get("titulo", "")},
                                    "✕", classe="actbtn ghost", titulo=_AVISO_X)
            return f"{rot} {botao}"

        corpo = "".join(
            f'<div class="item"><div class="t">{_esc(b.get("afirmacao"))}</div>'
            f'<div class="d">' + " · ".join(_estudo_linha(e) for e in (b.get("estudos") or []))
            + '</div></div>'
            for b in blocos) or '<p class="hint">Dossiê vazio — a IA não devolveu nada útil.</p>'

        lidos = "".join(
            f'<div class="item"><div class="d">{_esc(e.get("titulo"))} '
            f'<span class="hint">({_esc(e.get("fonte"))} {_esc(e.get("data"))}'
            + (" · já enviado" if e.get("origem") == "digest" else "") + ')</span> '
            + _botoes_escopo(token, e, tema) + '</div></div>' for e in corpus)
        bloco_lidos = (f'<details class="temacard"><summary>Estudos lidos '
                       f'<span class="cnt">{len(corpus)}</span></summary>'
                       f'<div class="temacard-corpo"><p class="hint">{_esc(_AVISO_X)}</p>'
                       f'{lidos}</div></details>') if corpus else ""

        fora_html = "".join(
            f'<div class="item"><div class="d">{_esc(e.get("titulo"))} '
            f'<span class="hint">({_esc(e.get("escopo"))})</span> '
            + _form_curadoria(token, "devolver_corpus",
                              {"origem": e.get("origem", ""), "ref": e.get("ref", ""),
                               "tema": tema}, "↩︎ Devolver")
            + '</div></div>' for e in excluidos)
        bloco_fora = (f'<details class="temacard"><summary>Fora da memória '
                      f'<span class="cnt">{len(excluidos)}</span></summary>'
                      f'<div class="temacard-corpo">{fora_html}</div></details>'
                      ) if excluidos else ""

        refazer = _form_curadoria(token, "refazer_dossie_tema", {"tema": tema},
                                  "🧠 Refazer só este tema")
        cards.append(
            f'<details name="dossie-tema" class="temacard">'
            f'<summary>{_emoji(tema)} {_esc(tema)} '
            f'<span class="cnt">{len(blocos)}</span></summary>'
            f'<div class="temacard-corpo">'
            f'<p class="hint">{d.get("n_estudos", 0)} estudos lidos · atualizado em '
            f'{_esc(quando)}</p>{corpo}{bloco_lidos}{bloco_fora}'
            f'<div style="margin-top:12px">{refazer}</div></div></details>')
    return "".join(cards)


def pagina_confirmar_exclusao(estudo, tema, token):
    """O ✕ do bloco não exclui na hora: mostra QUAL estudo casou com aquele título antes
    de tirar. O título no dossiê é o que a IA escreveu — ver `dossie.casar_titulo`."""
    origem = "já enviado ao assinante" if estudo.get("origem") == "digest" else "candidato da base"
    voltar = f'/curadoria?token={_esc(token)}&aba=dossie'
    return (f'<div class="panel"><h3>Tirar este estudo da memória?</h3>'
            f'<p class="hint">{_esc(_AVISO_X)}</p>'
            f'<div class="item"><div class="t">{_esc(estudo.get("titulo"))}</div>'
            f'<div class="d">{_esc(estudo.get("fonte"))} · {_esc(estudo.get("data"))} · '
            f'{origem}</div></div>'
            f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:14px">'
            f'{_botoes_escopo(token, estudo, tema)}'
            f'<a class="actbtn ghost" href="{voltar}" style="text-decoration:none">Cancelar</a>'
            f'</div></div>')
```

**3c.** Em `pagina_curadoria` (linha ~1679), acrescente o parâmetro `painel=None` na assinatura e passe adiante:

```python
def pagina_curadoria(estado, amanha, candidatos, reserva, classicos, token,
                     aba="triagem", tema="", msg="", dossies=None, painel=None):
```

e no ramo da aba:

```python
    if aba == "dossie":
        corpo_aba = ('<p class="hint">A memória destilada do que a base sabe. É daqui que a '
                     'opinião do estudo do dia vai sair — em vez de reler centenas de estudos '
                     'todo dia.</p>' + _dossie_html(dossies or [], painel, token))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_excluir_corpus_ui -v`
Expected: PASS (12 testes).

- [ ] **Step 5: Rode a suíte inteira** — `site_web` é compartilhado

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -5`
Expected: OK, zero falhas.

- [ ] **Step 6: Commit**

```bash
git add app/dossie.py app/site_web.py app/tests/test_excluir_corpus_ui.py
git commit -m "feat(corpus): aba do dossie ganha o X, a lista do corpus e o devolver"
```

---

### Task 10: As rotas

**Files:**
- Modify: `app/serve.py:502-505` (GET /curadoria) e o bloco POST `/curadoria` (linhas ~962-1094)
- Test: `app/tests/test_excluir_corpus_ui.py` (acrescentar classe)

**Interfaces:**
- Consumes: tudo das tasks 6-9.
- Produces: as ações POST `confirmar_exclusao` (tema, titulo), `excluir_corpus` (origem, ref, escopo, tema), `devolver_corpus` (origem, ref, tema), `refazer_dossie_tema` (tema).

- [ ] **Step 1: Write the failing test**

Acrescente a `app/tests/test_excluir_corpus_ui.py`, antes do `if __name__`:

```python
import io
import shutil
import tempfile
import urllib.parse as _urlp


class _RouteStub:
    """Mesmo stub de test_cupom_toggle.py — path/headers/rfile + `_html`/`_redirect`,
    sem abrir socket."""

    def __init__(self, path, body=b""):
        self.path = path
        self.rfile = io.BytesIO(body)
        self.headers = {"Content-Length": str(len(body)),
                        "Content-Type": "application/x-www-form-urlencoded"}
        self.client_address = ("127.0.0.1", 0)

    def _html(self, s, code=200):
        return {"code": code, "body": s}

    def _redirect(self, location, token=None, clear=False):
        return {"redirect": location}

    def _sessao(self):
        return None


class TestRotasExclusao(unittest.TestCase):
    def setUp(self):
        self.snap = (os.environ.get("DSCURSO_ARTIGOS_DB"), os.environ.get("DATABASE_URL"),
                     os.environ.get("DSCURSO_ADMIN_TOKEN"))
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ.pop("DATABASE_URL", None)
        os.environ["DSCURSO_ADMIN_TOKEN"] = "tok123"
        import db, config, serve
        importlib.reload(db)
        importlib.reload(config)
        importlib.reload(serve)
        self.db, self.serve = db, serve
        self.db.init()
        self.db.salvar_candidatos([{
            "chave": "k1", "titulo": "Once-Weekly Semaglutide in Adults with Overweight",
            "tema": "Obesidade", "tipo": "varredura", "fonte": "NEJM",
            "data": "2026-03-01", "doi": "10.1/k1", "url": "",
            "abstract": "abs", "pergunta": "", "score": 8, "citacoes": 0, "tags": []}])
        self.cid = self.db.listar_candidatos()[0]["id"]

    def tearDown(self):
        a, d, t = self.snap
        for k, v in (("DSCURSO_ARTIGOS_DB", a), ("DATABASE_URL", d),
                     ("DSCURSO_ADMIN_TOKEN", t)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        import db, config
        importlib.reload(db)
        importlib.reload(config)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _post(self, campos):
        body = _urlp.urlencode(campos).encode("utf-8")
        return self.serve.Handler.do_POST(_RouteStub("/curadoria", body))

    def test_sem_token_403_e_nada_muda(self):
        r = self._post({"acao": "excluir_corpus", "origem": "candidato",
                        "ref": self.cid, "escopo": "tudo", "tema": "Obesidade"})
        self.assertEqual(r["code"], 403)
        self.assertEqual(len(self.db.listar_candidatos()), 1)

    def test_excluir_candidato_do_escopo_tudo(self):
        r = self._post({"token": "tok123", "acao": "excluir_corpus", "origem": "candidato",
                        "ref": self.cid, "escopo": "tudo", "tema": "Obesidade"})
        self.assertIn("redirect", r)
        self.assertEqual(self.db.listar_candidatos(), [])

    def test_devolver_traz_de_volta(self):
        self.db.excluir_candidato(self.cid, "tudo")
        self._post({"token": "tok123", "acao": "devolver_corpus", "origem": "candidato",
                    "ref": self.cid, "tema": "Obesidade"})
        self.assertEqual(len(self.db.listar_candidatos()), 1)

    def test_escopo_invalido_nao_derruba_a_rota(self):
        """Campo vindo do navegador é entrada não confiável."""
        r = self._post({"token": "tok123", "acao": "excluir_corpus", "origem": "candidato",
                        "ref": self.cid, "escopo": "sim", "tema": "Obesidade"})
        self.assertIn("redirect", r)
        self.assertEqual(len(self.db.listar_candidatos()), 1)

    def test_confirmar_com_titulo_que_casa_mostra_a_tela(self):
        r = self._post({"token": "tok123", "acao": "confirmar_exclusao",
                        "tema": "Obesidade",
                        "titulo": "Once-Weekly Semaglutide in Adults with Overweight"})
        self.assertEqual(r["code"], 200)
        self.assertIn("Tirar este estudo da memória?", r["body"])

    def test_confirmar_com_titulo_que_nao_casa_avisa_e_nao_exclui(self):
        """Falha aberta: fingir que excluiu é o pior resultado possível."""
        r = self._post({"token": "tok123", "acao": "confirmar_exclusao",
                        "tema": "Obesidade", "titulo": "Estudo que a IA inventou"})
        self.assertIn("redirect", r)
        self.assertIn("Estudos+lidos", r["redirect"].replace("%20", "+"))
        self.assertEqual(len(self.db.listar_candidatos()), 1)

    def test_refazer_tema_responde_sem_esperar_a_IA(self):
        """A reconstrução são ~10 chamadas Sonnet: a rota tem que devolver na hora e
        avisar no WhatsApp depois. E tem que pedir UM tema, não os cinco."""
        chamado = {}
        import dossie, deliver

        def _fake(temas=None, **k):
            chamado["temas"] = temas
            return {}

        dossie.reconstruir_todos = _fake
        deliver.enviar_curador = lambda msg: None     # sem rede no teste
        r = self._post({"token": "tok123", "acao": "refazer_dossie_tema",
                        "tema": "Obesidade"})
        self.assertIn("redirect", r)
        import time
        for _ in range(50):                     # a thread é daemon; espera curta
            if chamado:
                break
            time.sleep(0.02)
        self.assertEqual(chamado.get("temas"), ["Obesidade"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_excluir_corpus_ui.TestRotasExclusao -v`
Expected: FAIL — as ações caem no `else` e nada acontece (ou `KeyError`).

- [ ] **Step 3: Write minimal implementation**

**3a.** No GET (`app/serve.py:502-505`), monte o painel só quando a aba do dossiê está aberta:

```python
            aba_atual = q.get("aba", ["triagem"])[0]
            painel = None
            if aba_atual == "dossie":
                try:
                    import dossie
                    painel = dossie.painel()
                except Exception as e:          # a aba tem que abrir mesmo sem o painel
                    print(f"[curadoria] painel do dossiê falhou: {e}", flush=True)
            return self._html(site_web.pagina_curadoria(
                estado, amanha, cands, db.listar_reserva(), classicos, config.ADMIN_TOKEN,
                aba=aba_atual, tema=q.get("tema", [""])[0],
                msg=q.get("msg", [""])[0], dossies=db.listar_dossies(), painel=painel), 200)
```

**3b.** No POST `/curadoria`, acrescente os ramos depois de `elif acao == "construir_dossie":` (linha ~1042, antes de `elif acao == "regerar_kit":`):

```python
            elif acao == "confirmar_exclusao":
                # O título vem do dossiê — é o que a IA ESCREVEU. Resolve contra o corpus
                # e mostra o estudo real antes de tirar; sem casamento, avisa em vez de
                # fingir que excluiu (a próxima reconstrução traria o estudo de volta).
                import dossie, site_web
                t = g("tema")
                achado = dossie.casar_titulo(g("titulo"), dossie.corpus_do_tema(t))
                if achado:
                    return self._html(site_web.pagina_confirmar_exclusao(
                        achado, t, config.ADMIN_TOKEN), 200)
                aba, msg = "dossie", ("Não achei este estudo na base com esse título "
                                      "(a IA pode ter reescrito). Abra Estudos lidos "
                                      "e tire de lá.")
            elif acao in ("excluir_corpus", "devolver_corpus"):
                escopo = "" if acao == "devolver_corpus" else g("escopo")
                origem, ref = g("origem"), g("ref")
                aba = "dossie"
                try:
                    if origem == "digest":
                        slug, _, data = ref.partition("|")
                        db.excluir_digest(slug, data, escopo)
                    else:
                        db.excluir_candidato(ref, escopo)
                    msg = ("Estudo devolvido à memória." if not escopo else
                           "Fora da memória — refaça o dossiê (🧠) pra ver o efeito "
                           "nas afirmações." if escopo == "memoria" else
                           "Fora da memória e da fila — refaça o dossiê (🧠) pra ver o "
                           "efeito nas afirmações.")
                except ValueError as e:         # escopo vindo do navegador é entrada suja
                    print(f"[curadoria] exclusão recusada: {e}", flush=True)
                    msg = "Não entendi o que era pra tirar — tente de novo pela lista."
            elif acao == "refazer_dossie_tema":
                # Mesmo desenho do botão que refaz tudo (thread + aviso no WhatsApp): são
                # ~10 chamadas Sonnet e o navegador desistiria antes.
                import threading
                tema_alvo = g("tema")

                def _um_tema(t=tema_alvo):
                    try:
                        import dossie
                        r = dossie.reconstruir_todos(temas=[t])
                        if r.get("ja_rodando"):
                            return
                        import deliver
                        deliver.enviar_curador(
                            f"🧠 Dossiê de {t} refeito a partir de {r.get(t, 0)} estudos.")
                    except Exception as e:
                        print(f"[dossie] refazer {t} explodiu: {e}", flush=True)
                        try:
                            import deliver
                            deliver.enviar_curador(f"🧠 Refazer o dossiê de {t} falhou — "
                                                   "dá pra tentar de novo.")
                        except Exception:
                            pass

                threading.Thread(target=_um_tema, daemon=True).start()
                aba = "dossie"
                msg = (f"🧠 Refazendo o dossiê de {tema_alvo} em segundo plano — te aviso "
                       "no WhatsApp quando terminar.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_excluir_corpus_ui -v`
Expected: PASS (19 testes).

- [ ] **Step 5: Rode a suíte inteira**

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -5`
Expected: OK, zero falhas.

- [ ] **Step 6: Commit**

```bash
git add app/serve.py app/tests/test_excluir_corpus_ui.py
git commit -m "feat(corpus): rotas de confirmar, excluir, devolver e refazer um tema"
```

---

### Task 11: Bateria de mutação — quebrar cada guarda e ver a suíte cair

Suíte verde não é prova de nada. Cada mutação abaixo é uma versão do código em que uma
guarda foi desligada; **a suíte tem que ficar vermelha em todas**. Sobrevivente é buraco
de teste — ou âncora errada minha (já aconteceu duas vezes neste item; ver
`mutacao-pyc-e-restauro`).

**Files:**
- Nenhum arquivo de produção muda ao fim. Rascunhos no scratchpad.

- [ ] **Step 1: Prepare**

```bash
cd app && find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null; true
cp db.py dossie.py resumo_diario.py audio.py /tmp/mut-backup/ 2>/dev/null || (mkdir -p /tmp/mut-backup && cp db.py dossie.py resumo_diario.py audio.py /tmp/mut-backup/)
```

- [ ] **Step 2: Rode as mutações, uma por vez**

Para cada linha da tabela: aplique a troca, rode `cd app && python3 -m unittest discover -s tests 2>&1 | tail -3`, **confirme que FALHOU**, e restaure com `cp /tmp/mut-backup/<arquivo> app/<arquivo>`.

| # | Arquivo | Troca | Teste que tem que cair |
|---|---|---|---|
| 1 | `db.py` `listar_candidatos` | apague a linha `conds.append("(excluido IS NULL OR excluido <> 'tudo')")` | `test_escopo_tudo_some_da_listagem_padrao` |
| 2 | `db.py` `listar_candidatos` | troque `<> 'tudo'` por `= ''` (esconderia também o 'memoria') | `test_escopo_memoria_CONTINUA_na_fila` |
| 3 | `db.py` `_valida_escopo` | `return e` direto, sem o `raise` | `test_escopo_invalido_levanta_em_vez_de_gravar_lixo` |
| 4 | `db.py` `listar_por_tema` | acrescente `AND (excluido IS NULL OR excluido='')` ao SQL | `test_digest_excluido_da_memoria_continua_no_portal` |
| 5 | `dossie.py` `corpus_do_tema` | apague o `continue` do candidato excluído | `test_candidato_excluido_da_memoria_sai_do_corpus` |
| 6 | `dossie.py` `corpus_do_tema` | apague o `continue` do digest excluído | `test_digest_excluido_da_memoria_sai_do_corpus` |
| 7 | `dossie.py` `casar_titulo` | `if iguais: return None` → `return iguais[0]` | `test_ambiguo_devolve_None_em_vez_de_chutar` |
| 8 | `dossie.py` `casar_titulo` | `MIN_PREFIXO = 30` → `MIN_PREFIXO = 1` | `test_prefixo_curto_demais_nao_casa` |
| 9 | `dossie.py` `casar_titulo` | `return prefixos[0] if len(prefixos) == 1` → `if prefixos` | (esperado: pode SOBREVIVER — se sobreviver, acrescente um teste com dois prefixos que casam) |
| 10 | `resumo_diario.py` `claude` | tire o `finally`, deixe o registro depois do `return` | `test_falha_no_meio_do_laco_preserva_o_que_ja_foi_pago` |
| 11 | `resumo_diario.py` `claude` | registre dentro do laço (uma linha por ida) | `test_laco_de_continuacao_vira_UMA_linha_somada` |
| 12 | `ia_custo.py` `registrar` | tire o `try/except` | `test_banco_fora_do_ar_nao_derruba_a_geracao` |
| 13 | `audio.py` `narrar` | registre `len(texto)` em vez de `len(falado)` | `test_grava_o_que_foi_MANDADO_e_nao_o_original` |
| 14 | `db.py` | tire `"ia_uso"` de `_TABELAS` | `test_toda_tabela_criada_no_init_esta_em_tabelas` |

- [ ] **Step 3: Conserte o que sobreviver**

Mutação que sobrevive é **hipótese, não veredito**: confira primeiro se a âncora estava
certa (o arquivo mudou mesmo? o `__pycache__` foi limpo?). Confirmada a sobrevivência,
escreva o teste que faltava e rode de novo.

- [ ] **Step 4: Confirme que a árvore voltou ao original**

```bash
git status --short        # tem que estar limpo
cd app && python3 -m unittest discover -s tests 2>&1 | tail -3
```

- [ ] **Step 5: Commit (só se algum teste novo nasceu)**

```bash
git add app/tests/
git commit -m "test(corpus): fecha os buracos que a bateria de mutacao revelou"
```

---

## Depois do plano

1. **Revisão de código** antes do merge (`superpowers:requesting-code-review`).
2. **Merge na main** e deploy pelo EasyPanel — ver `easypanel-deploy-curso`; conferir
   `git ls-remote origin refs/heads/main` == HEAD antes de disparar, e **nunca imprimir o
   corpo do erro** do deploy (vaza todas as credenciais em texto puro).
3. **Ações que só o Diego faz, depois do deploy:**
   - conferir `PRECOS_IA` e `USD_BRL` contra as páginas de preço (é a base do número que
     vai virar preço de assinatura);
   - abrir a aba 🧠, tirar um estudo ruim e apertar **🧠 Refazer só este tema** — é o
     ciclo completo da entrega;
   - **julgar o dossiê**, que continua sendo o gate da fatia 2b (a opinião do dia).
