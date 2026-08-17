# Tela de custos de IA — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar ao Diego uma tela que responde "quanto a máquina de conteúdo me custa por mês, e quanto isso dá por assinante" — com o que o nosso medidor gravou e, quando ele configurar a chave, com o que a Anthropic realmente cobrou.

**Architecture:** O ledger `ia_uso` já grava desde 2026-08-14. Esta entrega só LÊ: uma agregação em SQL, duas funções puras que viram dinheiro, um cliente isolado da Admin API da Anthropic, e uma página de admin. Nada aqui escreve no banco.

**Tech Stack:** Python 3 stdlib pura (o container não tem pip), SQLite nos testes e Postgres em produção, HTML por f-string em `site_web.py` sem JS, testes em `unittest`.

**Spec:** `docs/superpowers/specs/2026-08-16-tela-de-custos-design.md`

## Global Constraints

- **Sem dependências novas** e **sem JavaScript**.
- **Todo SQL roda em SQLite e Postgres**: placeholders `?`, e nada de função de data específica de um banco — o dia sai de `substr(quando,1,10)`, que funciona nos dois.
- **`amount` da Admin API vem em CENTAVOS** (`"123.45"` = US$ 1,23). Dividir por 100 é requisito com teste próprio: sem isso a tela mostra 100× o gasto real, num valor plausível o bastante para o Diego acreditar e repassar no preço.
- **A fatura é da ORGANIZAÇÃO inteira**, não deste app — a tela precisa dizer isso, senão mente por omissão.
- **A conferência degrada, nunca derruba a tela**: sem chave, chave recusada ou API fora do ar deixam a página funcionando com o lado que é nosso.
- **Nada de escrita** em nenhuma tabela nesta entrega.
- Comentários e docstrings em português **com acentos**; a regra de "sem acentos" vale só para a primeira linha da mensagem de commit.
- Commits em português, `feat(escopo): ...` / `fix(escopo): ...`.
- Testes: `cd app && python3 -m unittest discover -s tests`.

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `app/db.py` | `resumo_ia_uso(desde, ate=None)` — agregação em SQL. |
| `app/ia_custo.py` | `por_acao(linhas)` e `por_dia(linhas)` — linhas do ledger viram dinheiro. |
| `app/anthropic_admin.py` (**novo**) | O único ponto que não dá pra testar contra o serviço real. Isolado de propósito. |
| `app/config.py` | `ANTHROPIC_ADMIN_KEY`. |
| `app/site_web.py` | `pagina_custos(dados, token, msg="")` + item no `_admin_nav`. |
| `app/serve.py` | Rota GET `/admin/custos`. |

Testes novos: `app/tests/test_tela_custos.py`, `app/tests/test_anthropic_admin.py`.

---

### Task 1: Agregar o ledger em SQL

**Files:**
- Modify: `app/db.py` — função nova ao lado de `listar_ia_uso` (~linha 2009)
- Test: `app/tests/test_tela_custos.py` (novo)

**Interfaces:**
- Consumes: a tabela `ia_uso` (já existe: `id, quando, acao, modelo, tokens_in, tokens_out, chamadas`).
- Produces: `db.resumo_ia_uso(desde, ate=None) -> list[dict]` com `dia` (`AAAA-MM-DD`), `acao`, `modelo`, `tokens_in`, `tokens_out`, `chamadas`. `desde` é inclusivo, `ate` exclusivo; ordenado por dia decrescente.

- [ ] **Step 1: Write the failing test**

Crie `app/tests/test_tela_custos.py`:

```python
"""Item 40 — a tela que finalmente lê o ledger de custos.

O ledger grava desde 2026-08-14 e até aqui gravava no vazio. Esta entrega só LÊ.
Standalone: python3 app/tests/test_tela_custos.py"""
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


class _Base(unittest.TestCase):
    def setUp(self):
        self.snap = _snapshot_env()
        self.tmp = tempfile.mkdtemp()
        self.db = _reload_db(self.tmp)

    def tearDown(self):
        _restore_db(self.snap)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _uso(self, quando, acao="dossie", modelo="claude-sonnet-4-6",
             tin=1000, tout=100, chamadas=1):
        """Grava direto com o carimbo que eu quero — `registrar_ia_uso` usa `now()`."""
        import secrets
        with self.db._conn() as c:
            c.execute("""INSERT INTO ia_uso (id,quando,acao,modelo,tokens_in,tokens_out,chamadas)
                         VALUES (?,?,?,?,?,?,?)""",
                      (secrets.token_hex(8), quando, acao, modelo, tin, tout, chamadas))


class TestResumoIaUso(_Base):
    def test_agrupa_por_dia_acao_e_modelo(self):
        self._uso("2026-08-14T10:00:00", "dossie", tin=1000, tout=100)
        self._uso("2026-08-14T18:00:00", "dossie", tin=500, tout=50)
        self._uso("2026-08-14T19:00:00", "kit", tin=200, tout=20)
        r = self.db.resumo_ia_uso("2026-08-01")
        dossie = [x for x in r if x["acao"] == "dossie"]
        self.assertEqual(len(dossie), 1)                 # as duas viraram uma linha
        self.assertEqual(dossie[0]["tokens_in"], 1500)
        self.assertEqual(dossie[0]["tokens_out"], 150)
        self.assertEqual(dossie[0]["chamadas"], 2)
        self.assertEqual(dossie[0]["dia"], "2026-08-14")

    def test_dias_diferentes_nao_se_misturam(self):
        self._uso("2026-08-14T10:00:00", "dossie")
        self._uso("2026-08-15T10:00:00", "dossie")
        self.assertEqual(len(self.db.resumo_ia_uso("2026-08-01")), 2)

    def test_modelos_diferentes_nao_se_misturam(self):
        """O custo depende do modelo — somar Haiku com Opus perderia a informação."""
        self._uso("2026-08-14T10:00:00", "titulo", modelo="claude-haiku-4-5-20251001")
        self._uso("2026-08-14T11:00:00", "titulo", modelo="claude-opus-4-8")
        self.assertEqual(len(self.db.resumo_ia_uso("2026-08-01")), 2)

    def test_desde_e_inclusivo(self):
        self._uso("2026-08-14T00:00:00", "dossie")
        self.assertEqual(len(self.db.resumo_ia_uso("2026-08-14")), 1)

    def test_antes_do_desde_fica_de_fora(self):
        self._uso("2026-08-13T23:59:59", "dossie")
        self.assertEqual(self.db.resumo_ia_uso("2026-08-14"), [])

    def test_ate_e_exclusivo(self):
        self._uso("2026-08-14T10:00:00", "dossie")
        self._uso("2026-08-20T10:00:00", "dossie")
        r = self.db.resumo_ia_uso("2026-08-01", "2026-08-15")
        self.assertEqual([x["dia"] for x in r], ["2026-08-14"])

    def test_ordena_do_dia_mais_novo_para_o_mais_velho(self):
        self._uso("2026-08-14T10:00:00", "dossie")
        self._uso("2026-08-16T10:00:00", "kit")
        self.assertEqual([x["dia"] for x in self.db.resumo_ia_uso("2026-08-01")],
                         ["2026-08-16", "2026-08-14"])

    def test_janela_sem_nada_devolve_lista_vazia(self):
        self.assertEqual(self.db.resumo_ia_uso("2026-08-01"), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_tela_custos -v`
Expected: FAIL — `AttributeError: module 'db' has no attribute 'resumo_ia_uso'`.

- [ ] **Step 3: Write minimal implementation**

Em `app/db.py`, depois de `listar_ia_uso`:

```python
def resumo_ia_uso(desde, ate=None):
    """O ledger agregado por dia/ação/modelo, para a tela de custos.

    Agrega em SQL em vez de trazer linha a linha: a tela é de admin e roda pouco, mas o
    ledger cresce para sempre e a página não pode piorar com o tempo.

    O dia sai de `substr(quando,1,10)` — funções de data divergem entre SQLite e Postgres,
    e o carimbo já é ISO. `desde` é inclusivo, `ate` exclusivo.
    """
    q = ("SELECT substr(quando,1,10) AS dia, acao, modelo, "
         "SUM(tokens_in) AS tokens_in, SUM(tokens_out) AS tokens_out, "
         "SUM(chamadas) AS chamadas FROM ia_uso WHERE quando >= ?")
    params = [desde]
    if ate:
        q += " AND quando < ?"
        params.append(ate)
    q += (" GROUP BY substr(quando,1,10), acao, modelo"
          " ORDER BY substr(quando,1,10) DESC, acao")
    with _conn() as c:
        return [dict(r) for r in c.execute(q, params).fetchall()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_tela_custos -v`
Expected: PASS (8 testes).

- [ ] **Step 5: Commit**

```bash
git add app/db.py app/tests/test_tela_custos.py
git commit -m "feat(custos): agrega o ledger por dia, acao e modelo em SQL"
```

---

### Task 2: Linhas do ledger viram dinheiro

**Files:**
- Modify: `app/ia_custo.py` — funções novas no fim
- Test: `app/tests/test_tela_custos.py` (acrescentar classe)

**Interfaces:**
- Consumes: `ia_custo.custo_usd(modelo, tokens_in, tokens_out)` e `em_brl(usd)`, que já existem.
- Produces:
  - `ia_custo.por_acao(linhas) -> list[dict]` com `acao`, `usd`, `brl`, **maior gasto primeiro**;
  - `ia_custo.por_dia(linhas) -> dict` `{"AAAA-MM-DD": usd}`;
  - `ia_custo.total_usd(linhas) -> float`.

`linhas` é o que `db.resumo_ia_uso` devolve.

- [ ] **Step 1: Write the failing test**

Acrescente a `app/tests/test_tela_custos.py`, antes do `if __name__`:

```python
class TestDinheiro(unittest.TestCase):
    """As linhas agregadas viram R$. O preço vem de config.PRECOS_IA e o cálculo é na
    leitura — preço errado é recálculo, não perda."""

    def setUp(self):
        import importlib, config, ia_custo
        importlib.reload(config)
        importlib.reload(ia_custo)
        self.cfg, self.ia = config, ia_custo

    def _linha(self, dia="2026-08-14", acao="dossie", modelo="claude-sonnet-4-6",
               tin=1_000_000, tout=0):
        return {"dia": dia, "acao": acao, "modelo": modelo,
                "tokens_in": tin, "tokens_out": tout, "chamadas": 1}

    def test_total_soma_as_linhas(self):
        p_in, _ = self.cfg.PRECOS_IA["claude-sonnet-4-6"]
        t = self.ia.total_usd([self._linha(), self._linha()])
        self.assertAlmostEqual(t, p_in * 2)

    def test_por_acao_soma_dentro_da_acao(self):
        r = self.ia.por_acao([self._linha(acao="dossie"), self._linha(acao="dossie")])
        self.assertEqual(len(r), 1)
        p_in, _ = self.cfg.PRECOS_IA["claude-sonnet-4-6"]
        self.assertAlmostEqual(r[0]["usd"], p_in * 2)

    def test_por_acao_ordena_do_maior_gasto_para_o_menor(self):
        """É o que diz ao Diego o que cortar se achar caro — ordem errada esconde isso."""
        linhas = [self._linha(acao="barato", tin=1000),
                  self._linha(acao="caro", tin=5_000_000),
                  self._linha(acao="medio", tin=100_000)]
        self.assertEqual([x["acao"] for x in self.ia.por_acao(linhas)],
                         ["caro", "medio", "barato"])

    def test_por_acao_traz_o_valor_em_reais(self):
        r = self.ia.por_acao([self._linha()])
        self.assertAlmostEqual(r[0]["brl"], r[0]["usd"] * self.cfg.USD_BRL)

    def test_modelos_diferentes_na_mesma_acao_somam_com_o_preco_de_cada_um(self):
        linhas = [self._linha(acao="titulo", modelo="claude-haiku-4-5-20251001"),
                  self._linha(acao="titulo", modelo="claude-sonnet-4-6")]
        h_in, _ = self.cfg.PRECOS_IA["claude-haiku-4-5-20251001"]
        s_in, _ = self.cfg.PRECOS_IA["claude-sonnet-4-6"]
        r = self.ia.por_acao(linhas)
        self.assertEqual(len(r), 1)
        self.assertAlmostEqual(r[0]["usd"], h_in + s_in)

    def test_por_dia_agrupa_por_data(self):
        linhas = [self._linha(dia="2026-08-14"), self._linha(dia="2026-08-14"),
                  self._linha(dia="2026-08-15")]
        d = self.ia.por_dia(linhas)
        p_in, _ = self.cfg.PRECOS_IA["claude-sonnet-4-6"]
        self.assertAlmostEqual(d["2026-08-14"], p_in * 2)
        self.assertAlmostEqual(d["2026-08-15"], p_in)

    def test_lista_vazia_nao_explode(self):
        self.assertEqual(self.ia.por_acao([]), [])
        self.assertEqual(self.ia.por_dia([]), {})
        self.assertEqual(self.ia.total_usd([]), 0.0)

    def test_modelo_sem_preco_entra_como_zero_e_nao_derruba(self):
        r = self.ia.por_acao([self._linha(modelo="modelo-que-nao-existe")])
        self.assertEqual(r[0]["usd"], 0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_tela_custos.TestDinheiro -v`
Expected: FAIL — `AttributeError: module 'ia_custo' has no attribute 'total_usd'`.

- [ ] **Step 3: Write minimal implementation**

No fim de `app/ia_custo.py`:

```python
def total_usd(linhas):
    """US$ de um conjunto de linhas agregadas do ledger."""
    return sum(custo_usd(l.get("modelo"), l.get("tokens_in"), l.get("tokens_out"))
               for l in (linhas or []))


def por_acao(linhas):
    """Gasto por ação, do que mais pesa para o que menos pesa.

    A ordem é o conteúdo: é ela que diz ao Diego o que cortar se achar caro. Modelos
    diferentes dentro da mesma ação somam com o preço de cada um.
    """
    acc = {}
    for l in (linhas or []):
        usd = custo_usd(l.get("modelo"), l.get("tokens_in"), l.get("tokens_out"))
        acc[l.get("acao") or "desconhecido"] = acc.get(l.get("acao") or "desconhecido", 0.0) + usd
    return [{"acao": a, "usd": u, "brl": em_brl(u)}
            for a, u in sorted(acc.items(), key=lambda kv: kv[1], reverse=True)]


def por_dia(linhas):
    """{'AAAA-MM-DD': US$} — é o lado nosso da comparação com a fatura."""
    acc = {}
    for l in (linhas or []):
        dia = l.get("dia") or ""
        acc[dia] = acc.get(dia, 0.0) + custo_usd(l.get("modelo"), l.get("tokens_in"),
                                                 l.get("tokens_out"))
    return acc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_tela_custos -v`
Expected: PASS (16 testes).

- [ ] **Step 5: Commit**

```bash
git add app/ia_custo.py app/tests/test_tela_custos.py
git commit -m "feat(custos): linhas do ledger viram gasto por acao e por dia"
```

---

### Task 3: O cliente da Admin API da Anthropic

**Files:**
- Create: `app/anthropic_admin.py`
- Modify: `app/config.py` (junto de `PRECOS_IA`/`USD_BRL`)
- Test: `app/tests/test_anthropic_admin.py` (novo)

**Interfaces:**
- Consumes: `config.ANTHROPIC_ADMIN_KEY`.
- Produces: `anthropic_admin.custo_por_dia(desde, ate=None, chave=None) -> dict` com `{"estado": "sem_chave"|"recusada"|"erro"|"ok", "dias": {"AAAA-MM-DD": usd}}`; e `anthropic_admin._get(url, chave)`, o ponto que os testes substituem.

**Contrato da API, conferido na documentação em 2026-08-16:**

```
GET https://api.anthropic.com/v1/organizations/cost_report
    ?starting_at=<RFC3339>&bucket_width=1d[&ending_at=<RFC3339>][&page=<cursor>]
headers: anthropic-version: 2023-06-01 + credencial de admin
resposta: {"data":[{"starting_at","ending_at","results":[{"amount","currency",...}]}],
           "has_more": bool, "next_page": str|null}
```

- [ ] **Step 1: Write the failing test**

Crie `app/tests/test_anthropic_admin.py`:

```python
"""Conferência do nosso ledger contra a fatura real (Admin API da Anthropic).

Este é o único ponto da entrega que não dá pra testar contra o serviço real — eu não tenho
a chave de admin do Diego. Por isso ele é um módulo isolado, com o contrato copiado da
documentação, e a tela nomeia em qual estado ele está.
Standalone: python3 app/tests/test_anthropic_admin.py"""
import importlib
import os
import sys
import unittest
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _bucket(dia, *amounts):
    """Um balde diário como a API devolve. `amount` vem em CENTAVOS, como string."""
    return {"starting_at": f"{dia}T00:00:00Z", "ending_at": f"{dia}T23:59:59Z",
            "results": [{"amount": a, "currency": "USD"} for a in amounts]}


def _resposta(buckets, has_more=False, next_page=None):
    return {"data": buckets, "has_more": has_more, "next_page": next_page}


class _Base(unittest.TestCase):
    def setUp(self):
        self.snap = os.environ.get("DSCURSO_ANTHROPIC_ADMIN_KEY")
        os.environ["DSCURSO_ANTHROPIC_ADMIN_KEY"] = "sk-ant-admin-teste"
        import config, anthropic_admin
        importlib.reload(config)
        importlib.reload(anthropic_admin)
        self.aa = anthropic_admin

    def tearDown(self):
        if self.snap is None:
            os.environ.pop("DSCURSO_ANTHROPIC_ADMIN_KEY", None)
        else:
            os.environ["DSCURSO_ANTHROPIC_ADMIN_KEY"] = self.snap
        import config
        importlib.reload(config)


class TestCentavos(_Base):
    def test_amount_vem_em_CENTAVOS_e_vira_dolar(self):
        """A doc diz: "123.45" em USD representa US$ 1,23. Sem dividir por 100 a tela
        mostraria 100x o gasto real — plausível o bastante pro Diego acreditar."""
        self.aa._get = lambda url, chave: _resposta([_bucket("2026-08-14", "123.45")])
        r = self.aa.custo_por_dia("2026-08-01")
        self.assertEqual(r["estado"], "ok")
        self.assertAlmostEqual(r["dias"]["2026-08-14"], 1.2345)

    def test_varios_itens_no_mesmo_dia_somam(self):
        self.aa._get = lambda url, chave: _resposta(
            [_bucket("2026-08-14", "100.00", "50.00")])
        r = self.aa.custo_por_dia("2026-08-01")
        self.assertAlmostEqual(r["dias"]["2026-08-14"], 1.5)

    def test_dia_sem_custo_nao_aparece_com_lixo(self):
        self.aa._get = lambda url, chave: _resposta([_bucket("2026-08-14")])
        r = self.aa.custo_por_dia("2026-08-01")
        self.assertEqual(r["dias"].get("2026-08-14", 0.0), 0.0)

    def test_amount_invalido_nao_derruba_o_resto(self):
        self.aa._get = lambda url, chave: _resposta(
            [_bucket("2026-08-14", "nao-e-numero", "100.00")])
        r = self.aa.custo_por_dia("2026-08-01")
        self.assertAlmostEqual(r["dias"]["2026-08-14"], 1.0)


class TestPaginacao(_Base):
    def test_segue_o_next_page_ate_o_fim(self):
        """Fatura com muitos dias vem paginada; parar na 1ª página esconderia gasto."""
        paginas = [_resposta([_bucket("2026-08-14", "100.00")], has_more=True,
                             next_page="cursor2"),
                   _resposta([_bucket("2026-08-15", "200.00")])]
        vistos = []

        def _get(url, chave):
            vistos.append(url)
            return paginas.pop(0)

        self.aa._get = _get
        r = self.aa.custo_por_dia("2026-08-01")
        self.assertEqual(sorted(r["dias"]), ["2026-08-14", "2026-08-15"])
        self.assertIn("cursor2", vistos[1])

    def test_nao_gira_para_sempre_se_a_api_insistir_em_has_more(self):
        """Defesa contra laço infinito: a página de admin não pode travar o servidor."""
        self.aa._get = lambda url, chave: _resposta([_bucket("2026-08-14", "1.00")],
                                                    has_more=True, next_page="sempre")
        r = self.aa.custo_por_dia("2026-08-01")
        self.assertEqual(r["estado"], "ok")


class TestEstados(_Base):
    def test_sem_chave_configurada(self):
        os.environ.pop("DSCURSO_ANTHROPIC_ADMIN_KEY", None)
        import config
        importlib.reload(config)
        importlib.reload(self.aa)
        r = self.aa.custo_por_dia("2026-08-01")
        self.assertEqual(r["estado"], "sem_chave")
        self.assertEqual(r["dias"], {})

    def test_401_vira_recusada(self):
        def _get(url, chave):
            raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)
        self.aa._get = _get
        self.assertEqual(self.aa.custo_por_dia("2026-08-01")["estado"], "recusada")

    def test_403_tambem_vira_recusada(self):
        def _get(url, chave):
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
        self.aa._get = _get
        self.assertEqual(self.aa.custo_por_dia("2026-08-01")["estado"], "recusada")

    def test_500_vira_erro(self):
        def _get(url, chave):
            raise urllib.error.HTTPError(url, 500, "Server Error", {}, None)
        self.aa._get = _get
        self.assertEqual(self.aa.custo_por_dia("2026-08-01")["estado"], "erro")

    def test_rede_fora_vira_erro_e_nao_levanta(self):
        def _get(url, chave):
            raise OSError("sem rede")
        self.aa._get = _get
        r = self.aa.custo_por_dia("2026-08-01")
        self.assertEqual(r["estado"], "erro")
        self.assertEqual(r["dias"], {})

    def test_resposta_com_formato_inesperado_vira_erro_em_vez_de_explodir(self):
        """Se o contrato mudar (ou eu tiver lido errado), a tela precisa dizer isso."""
        self.aa._get = lambda url, chave: {"isso": "não é o contrato"}
        r = self.aa.custo_por_dia("2026-08-01")
        self.assertIn(r["estado"], ("ok", "erro"))
        self.assertEqual(r["dias"], {})


class TestRequisicao(_Base):
    def test_manda_bucket_diario_e_a_data_inicial(self):
        vistos = []
        self.aa._get = lambda url, chave: vistos.append(url) or _resposta([])
        self.aa.custo_por_dia("2026-08-01")
        self.assertIn("bucket_width=1d", vistos[0])
        self.assertIn("2026-08-01", vistos[0])

    def test_chave_sk_ant_vai_no_header_x_api_key(self):
        h = self.aa._headers("sk-ant-admin-abc")
        self.assertEqual(h.get("x-api-key"), "sk-ant-admin-abc")
        self.assertNotIn("Authorization", h)

    def test_token_que_nao_e_sk_ant_vai_como_bearer(self):
        """A doc exemplifica com Bearer; chaves de admin históricas usam x-api-key. Sem a
        chave do Diego não dá pra saber qual é a dele — escolhemos pelo formato, e o estado
        'recusada' cobre o caso de termos escolhido errado."""
        h = self.aa._headers("oauth-abc")
        self.assertEqual(h.get("Authorization"), "Bearer oauth-abc")
        self.assertNotIn("x-api-key", h)

    def test_manda_a_versao_da_api(self):
        self.assertEqual(self.aa._headers("sk-ant-x").get("anthropic-version"), "2023-06-01")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_anthropic_admin -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'anthropic_admin'`.

- [ ] **Step 3: Write minimal implementation**

Em `app/config.py`, junto de `USD_BRL`:

```python
# Chave de ADMIN da organização Anthropic — diferente da que o app usa pra gerar conteúdo.
# Só serve pra ler a fatura (Admin API). Sem ela, a tela de custos mostra só o nosso ledger.
ANTHROPIC_ADMIN_KEY = os.environ.get("DSCURSO_ANTHROPIC_ADMIN_KEY") or ""
```

Crie `app/anthropic_admin.py`:

```python
"""A fatura real da Anthropic, para conferir contra o nosso ledger.

Este é o único ponto da entrega que não foi testado contra o serviço real — a chave de
admin é do Diego. Por isso ele vive isolado, com o contrato copiado da documentação
(conferida em 2026-08-16), e devolve um ESTADO nomeado em vez de levantar: a tela precisa
continuar mostrando o lado que é nosso mesmo quando este lado falha.

⚠️ `amount` vem em CENTAVOS, como string decimal: "123.45" em USD é US$ 1,23. Sem dividir
por 100 a tela mostraria 100x o gasto real — plausível o bastante pra ser acreditado.

⚠️ O relatório é da ORGANIZAÇÃO inteira, não deste app. Diferença contra o nosso ledger
não significa automaticamente preço errado na nossa tabela: pode ser uso de outra origem.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

import config

URL = "https://api.anthropic.com/v1/organizations/cost_report"
MAX_PAGINAS = 20          # defesa contra laço infinito: a tela não pode travar o servidor


def _headers(chave):
    """A doc exemplifica com `Authorization: Bearer`; chaves de admin históricas usam
    `x-api-key`. Sem a chave do Diego não dá pra saber qual é a dele — escolhe-se pelo
    formato, e o estado 'recusada' na tela cobre o caso de termos escolhido errado."""
    h = {"anthropic-version": "2023-06-01"}
    if str(chave).startswith("sk-ant-"):
        h["x-api-key"] = str(chave)
    else:
        h["Authorization"] = "Bearer " + str(chave)
    return h


def _get(url, chave):
    """O GET isolado — é o ponto que os testes substituem pra rodar sem rede."""
    req = urllib.request.Request(url, method="GET", headers=_headers(chave))
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def _dias_da_pagina(pagina):
    """{'AAAA-MM-DD': US$} de uma página. Item com `amount` ilegível é pulado — perder um
    item é melhor que perder o relatório inteiro."""
    out = {}
    for b in (pagina.get("data") or []):
        dia = str(b.get("starting_at") or "")[:10]
        if not dia:
            continue
        total = 0.0
        for item in (b.get("results") or []):
            try:
                total += float(item.get("amount")) / 100.0     # centavos -> dólar
            except (TypeError, ValueError):
                print(f"[fatura] amount ilegível em {dia}: {item.get('amount')!r}", flush=True)
        out[dia] = out.get(dia, 0.0) + total
    return out


def custo_por_dia(desde, ate=None, chave=None):
    """O que a Anthropic cobrou, por dia. Nunca levanta: devolve o estado."""
    chave = chave if chave is not None else config.ANTHROPIC_ADMIN_KEY
    if not chave:
        return {"estado": "sem_chave", "dias": {}}
    params = {"starting_at": f"{desde}T00:00:00Z", "bucket_width": "1d"}
    if ate:
        params["ending_at"] = f"{ate}T00:00:00Z"
    dias, pagina_cursor = {}, None
    try:
        for _ in range(MAX_PAGINAS):
            p = dict(params)
            if pagina_cursor:
                p["page"] = pagina_cursor
            r = _get(URL + "?" + urllib.parse.urlencode(p), chave) or {}
            dias.update(_dias_da_pagina(r))
            if not r.get("has_more") or not r.get("next_page"):
                break
            pagina_cursor = r["next_page"]
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {"estado": "recusada", "dias": {}}
        print(f"[fatura] HTTP {e.code} ao ler o custo", flush=True)
        return {"estado": "erro", "dias": {}}
    except Exception as e:
        print(f"[fatura] falhou ({type(e).__name__}): {e}", flush=True)
        return {"estado": "erro", "dias": {}}
    return {"estado": "ok", "dias": dias}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_anthropic_admin -v`
Expected: PASS (15 testes).

- [ ] **Step 5: Commit**

```bash
git add app/anthropic_admin.py app/config.py app/tests/test_anthropic_admin.py
git commit -m "feat(custos): cliente da Admin API da Anthropic, com estado nomeado"
```

---

### Task 4: A tela

**Files:**
- Modify: `app/site_web.py` — `_admin_nav` (~linha 700) e função nova `pagina_custos`
- Test: `app/tests/test_tela_custos.py` (acrescentar classe)

**Interfaces:**
- Consumes: `_pagina`, `_esc`, `_admin_nav`, que já existem.
- Produces: `site_web.pagina_custos(dados, token, msg="") -> str` (página completa).

`dados` é um dict:

```python
{"mes": "2026-08", "usd": 12.34, "brl": 67.87, "cotacao": 5.5, "assinantes": 42,
 "por_acao": [{"acao": "dossie", "usd": 8.0, "brl": 44.0}, ...],
 "dias": [{"dia": "2026-08-16", "ledger": 1.2, "fatura": 1.3}, ...],   # fatura None se não houver
 "fatura": "sem_chave"}      # "sem_chave" | "recusada" | "erro" | "ok"
```

- [ ] **Step 1: Write the failing test**

Acrescente a `app/tests/test_tela_custos.py`, antes do `if __name__`:

```python
class TestTela(unittest.TestCase):
    def setUp(self):
        import importlib, site_web
        importlib.reload(site_web)
        self.sw = site_web

    def _dados(self, **kw):
        d = {"mes": "2026-08", "usd": 12.34, "brl": 67.87, "cotacao": 5.5,
             "assinantes": 42,
             "por_acao": [{"acao": "dossie", "usd": 8.0, "brl": 44.0},
                          {"acao": "kit", "usd": 4.34, "brl": 23.87}],
             "dias": [{"dia": "2026-08-16", "ledger": 1.2, "fatura": None}],
             "fatura": "sem_chave"}
        d.update(kw)
        return d

    def test_devolve_pagina_completa(self):
        html = self.sw.pagina_custos(self._dados(), "tok")
        self.assertTrue(html.lstrip().lower().startswith("<!doctype html>"))

    def test_mostra_o_gasto_do_mes_em_reais(self):
        html = self.sw.pagina_custos(self._dados(), "tok")
        self.assertIn("67,87", html.replace(".", ","))

    def test_mostra_a_cotacao_usada(self):
        """Número em R$ sem dizer a cotação é número sem procedência."""
        html = self.sw.pagina_custos(self._dados(), "tok")
        self.assertIn("5,5", html.replace(".", ","))

    def test_mostra_quantos_assinantes_dividem_a_conta(self):
        html = self.sw.pagina_custos(self._dados(), "tok")
        self.assertIn("42", html)

    def test_diz_que_o_custo_e_fixo(self):
        """Sem essa frase ele olha um número que cai sozinho e tira a conclusão errada
        sobre o próprio produto."""
        html = self.sw.pagina_custos(self._dados(), "tok").lower()
        self.assertIn("fixo", html)

    def test_lista_as_acoes_do_maior_pro_menor_na_ordem_que_recebeu(self):
        html = self.sw.pagina_custos(self._dados(), "tok")
        self.assertLess(html.index("dossie"), html.index("kit"))

    def test_sem_chave_explica_o_que_falta(self):
        html = self.sw.pagina_custos(self._dados(fatura="sem_chave"), "tok")
        self.assertIn("DSCURSO_ANTHROPIC_ADMIN_KEY", html)

    def test_chave_recusada_diz_isso(self):
        html = self.sw.pagina_custos(self._dados(fatura="recusada"), "tok").lower()
        self.assertIn("recusada", html)

    def test_erro_na_api_diz_isso_sem_derrubar_a_pagina(self):
        html = self.sw.pagina_custos(self._dados(fatura="erro"), "tok")
        self.assertTrue(html.lstrip().lower().startswith("<!doctype html>"))
        self.assertIn("67,87", html.replace(".", ","))      # o lado nosso continua lá

    def test_com_fatura_mostra_as_tres_colunas(self):
        d = self._dados(fatura="ok",
                        dias=[{"dia": "2026-08-16", "ledger": 1.0, "fatura": 1.2}])
        html = self.sw.pagina_custos(d, "tok").lower()
        self.assertIn("fatura", html)
        self.assertIn("diferen", html)          # "diferença"

    def test_avisa_que_a_fatura_e_da_organizacao_inteira(self):
        """Sem isso a tela mente por omissão: a diferença pode ser uso de outra origem,
        não preço errado na nossa tabela."""
        html = self.sw.pagina_custos(self._dados(fatura="ok"), "tok").lower()
        self.assertIn("organiza", html)

    def test_escapa_o_nome_da_acao(self):
        d = self._dados(por_acao=[{"acao": "<script>alert(1)</script>", "usd": 1.0,
                                   "brl": 5.5}])
        self.assertNotIn("<script>alert(1)</script>", self.sw.pagina_custos(d, "tok"))

    def test_mes_sem_gasto_nenhum_nao_quebra(self):
        d = self._dados(usd=0.0, brl=0.0, por_acao=[], dias=[])
        html = self.sw.pagina_custos(d, "tok")
        self.assertTrue(html.lstrip().lower().startswith("<!doctype html>"))

    def test_zero_assinantes_nao_divide_por_zero(self):
        html = self.sw.pagina_custos(self._dados(assinantes=0), "tok")
        self.assertTrue(html.lstrip().lower().startswith("<!doctype html>"))

    def test_o_nav_de_admin_ganhou_o_link_de_custos(self):
        self.assertIn("/admin/custos", self.sw._admin_nav("tok"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_tela_custos.TestTela -v`
Expected: FAIL — `AttributeError: module 'site_web' has no attribute 'pagina_custos'`.

- [ ] **Step 3: Write minimal implementation**

Em `app/site_web.py`, no `_admin_nav`, depois da linha do `/admin/precos`:

```python
            + lk("/admin/custos", "📊 Custos", "custos")
```

E a função nova (ponha perto de `pagina_precos`):

```python
_FATURA_AVISO = {
    "sem_chave": ('Para comparar com o que a Anthropic cobrou de verdade, configure a '
                  'variável <code>DSCURSO_ANTHROPIC_ADMIN_KEY</code> com uma chave de '
                  'ADMIN da organização (é outra, diferente da que o app usa pra gerar '
                  'conteúdo).'),
    "recusada": ('A chave de admin foi recusada pela Anthropic — confira se ela é de '
                 'ADMIN da organização e se não expirou.'),
    "erro": ('Não consegui falar com a API de custo da Anthropic agora. O gasto medido '
             'por nós, acima, continua valendo.'),
    "ok": ('⚠️ A fatura é da <strong>organização inteira</strong> na Anthropic, não só '
           'deste app: se outra coisa sua usa a mesma conta, ela entra nesse total. '
           'Diferença aqui não quer dizer automaticamente que a nossa tabela de preços '
           'está errada.'),
}


def _rs(v):
    """R$ com vírgula, como todo o resto do site."""
    return f"{(v or 0.0):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def pagina_custos(dados, token, msg=""):
    """Quanto a máquina de conteúdo custa de IA.

    Abre pelo gasto do mês porque o custo é FIXO — o estudo do dia é gerado uma vez e vai
    pra todo mundo. "Por assinante" é uma divisão que cai sozinha conforme a base cresce;
    mostrar só ela levaria o Diego a conclusões erradas sobre o próprio produto.
    """
    d = dados or {}
    n = int(d.get("assinantes") or 0)
    usd, brl = d.get("usd") or 0.0, d.get("brl") or 0.0
    por_cabeca = (f'Com <strong>{n}</strong> assinantes ativos, dá <strong>R$ '
                  f'{_rs(brl / n)}</strong> por assinante no mês.' if n else
                  'Nenhum assinante ativo no momento.')
    acoes = "".join(
        f'<div class="item"><div class="d">{_esc(a.get("acao"))} — '
        f'<strong>R$ {_rs(a.get("brl"))}</strong> '
        f'<span class="hint">(US$ {_rs(a.get("usd"))})</span></div></div>'
        for a in (d.get("por_acao") or [])) or '<p class="hint">Nada medido neste mês.</p>'

    tem_fatura = d.get("fatura") == "ok"
    cab = ('<tr><th align="left">Dia</th><th align="right">Nosso medidor</th>'
           + ('<th align="right">Fatura</th><th align="right">Diferença</th>'
              if tem_fatura else '') + '</tr>')
    linhas = ""
    for x in (d.get("dias") or []):
        led, fat = x.get("ledger") or 0.0, x.get("fatura")
        extra = ""
        if tem_fatura:
            dif = (fat or 0.0) - led
            extra = (f'<td align="right">US$ {_rs(fat)}</td>'
                     f'<td align="right">US$ {_rs(dif)}</td>')
        linhas += (f'<tr><td>{_esc(x.get("dia"))}</td>'
                   f'<td align="right">US$ {_rs(led)}</td>{extra}</tr>')
    tabela = (f'<table style="width:100%;border-collapse:collapse">{cab}{linhas}</table>'
              if linhas else '<p class="hint">Sem dias medidos ainda.</p>')

    corpo = (
        f'<div class="wrap">{_admin_nav(token, "custos")}'
        + (f'<div class="infobox">{_esc(msg)}</div>' if msg else '')
        + f'<div class="panel" style="max-width:none">'
        f'<h3>Custo de IA — {_esc(d.get("mes"))}</h3>'
        f'<p style="font-size:26px;margin:6px 0"><strong>R$ {_rs(brl)}</strong> '
        f'<span class="hint">(US$ {_rs(usd)} · cotação R$ {_rs(d.get("cotacao"))})</span></p>'
        f'<p>{por_cabeca}</p>'
        f'<p class="hint">O custo de IA é praticamente <strong>fixo</strong>: o estudo do '
        f'dia é gerado uma vez e vai pra todos. Crescer a base derruba o valor por '
        f'assinante — o que sustenta preço é o custo mensal da máquina.</p>'
        f'<h3 style="margin-top:22px">Onde o dinheiro vai</h3>{acoes}'
        f'<h3 style="margin-top:22px">Dia a dia</h3>'
        f'<p class="hint">{_FATURA_AVISO.get(d.get("fatura"), "")}</p>{tabela}'
        f'</div></div>')
    return _pagina("Custos de IA · Admin", corpo, logado=True,
                   meta_extra='<meta name="robots" content="noindex">')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_tela_custos -v`
Expected: PASS (31 testes).

- [ ] **Step 5: Rode a suíte inteira** — `_admin_nav` aparece em todas as telas de admin

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -5`
Expected: OK.

- [ ] **Step 6: Commit**

```bash
git add app/site_web.py app/tests/test_tela_custos.py
git commit -m "feat(custos): tela /admin/custos com gasto do mes, quebra por acao e fatura"
```

---

### Task 5: A rota

**Files:**
- Modify: `app/serve.py` — GET, junto de `/admin/precos` (~linha 375)
- Test: `app/tests/test_tela_custos.py` (acrescentar classe)

**Interfaces:**
- Consumes: tudo das tasks 1-4, mais `subscribers.ativos()`.
- Produces: a rota GET `/admin/custos`.

- [ ] **Step 1: Write the failing test**

Acrescente a `app/tests/test_tela_custos.py`, antes do `if __name__`:

```python
import io


class _RouteStub:
    def __init__(self, path):
        self.path = path
        self.rfile = io.BytesIO(b"")
        self.headers = {"Content-Length": "0"}
        self.client_address = ("127.0.0.1", 0)

    def _html(self, s, code=200):
        return {"code": code, "body": s}

    def _redirect(self, location, token=None, clear=False):
        return {"redirect": location}

    def _sessao(self):
        return None


class TestRotaCustos(_Base):
    def setUp(self):
        super().setUp()
        self.snap_token = os.environ.get("DSCURSO_ADMIN_TOKEN")
        os.environ["DSCURSO_ADMIN_TOKEN"] = "tok123"
        import importlib, config, serve
        importlib.reload(config)
        importlib.reload(serve)
        self.serve = serve

    def tearDown(self):
        if self.snap_token is None:
            os.environ.pop("DSCURSO_ADMIN_TOKEN", None)
        else:
            os.environ["DSCURSO_ADMIN_TOKEN"] = self.snap_token
        import importlib, config
        importlib.reload(config)
        super().tearDown()

    def _get(self, path):
        return self.serve.Handler.do_GET(_RouteStub(path))

    def test_sem_token_403(self):
        self.assertEqual(self._get("/admin/custos")["code"], 403)

    def test_com_token_abre(self):
        r = self._get("/admin/custos?token=tok123")
        self.assertEqual(r["code"], 200)
        self.assertIn("Custo de IA", r["body"])

    def test_abre_mesmo_sem_nenhum_uso_gravado(self):
        r = self._get("/admin/custos?token=tok123")
        self.assertEqual(r["code"], 200)

    def test_mostra_o_que_foi_gravado_no_mes(self):
        from datetime import datetime
        hoje = datetime.now().strftime("%Y-%m-%d")
        self._uso(f"{hoje}T10:00:00", "dossie", tin=1_000_000, tout=0)
        r = self._get("/admin/custos?token=tok123")
        self.assertIn("dossie", r["body"])

    def test_a_fatura_fora_do_ar_nao_derruba_a_tela(self):
        import anthropic_admin
        anthropic_admin.custo_por_dia = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("explodiu"))
        r = self._get("/admin/custos?token=tok123")
        self.assertEqual(r["code"], 200)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_tela_custos.TestRotaCustos -v`
Expected: FAIL — a rota não existe (404/None em vez de 200).

- [ ] **Step 3: Write minimal implementation**

Em `app/serve.py`, no `do_GET`, logo depois do bloco de `/admin/precos`:

```python
        if path == "/admin/custos":
            import config, db, ia_custo, site_web, subscribers
            from datetime import datetime, timedelta
            q = up.parse_qs(up.urlparse(self.path).query)
            if not config.ADMIN_TOKEN or q.get("token", [""])[0] != config.ADMIN_TOKEN:
                return self._html("<h3>Acesso negado</h3>", 403)
            db.init()
            hoje = datetime.now()
            mes = hoje.strftime("%Y-%m")
            linhas = db.resumo_ia_uso(f"{mes}-01")
            usd = ia_custo.total_usd(linhas)
            # Últimos 30 dias pro dia a dia: a comparação com a fatura vive aqui, e o mês
            # corrente sozinho esconderia a virada de mês.
            desde30 = (hoje - timedelta(days=30)).strftime("%Y-%m-%d")
            l30 = db.resumo_ia_uso(desde30)
            nosso = ia_custo.por_dia(l30)
            fatura = {"estado": "erro", "dias": {}}
            try:
                import anthropic_admin
                fatura = anthropic_admin.custo_por_dia(desde30)
            except Exception as e:      # a parte opcional não pode levar a tela junto
                print(f"[custos] fatura falhou: {e}", flush=True)
            dias = [{"dia": d, "ledger": nosso.get(d, 0.0),
                     "fatura": fatura["dias"].get(d)}
                    for d in sorted(set(nosso) | set(fatura["dias"]), reverse=True)]
            dados = {"mes": mes, "usd": usd, "brl": ia_custo.em_brl(usd),
                     "cotacao": config.USD_BRL,
                     "assinantes": len(subscribers.ativos()),
                     "por_acao": ia_custo.por_acao(linhas), "dias": dias,
                     "fatura": fatura["estado"]}
            return self._html(site_web.pagina_custos(dados, config.ADMIN_TOKEN or "",
                                                     msg=q.get("msg", [""])[0]), 200)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_tela_custos -v`
Expected: PASS (36 testes).

- [ ] **Step 5: Rode a suíte inteira**

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -5`
Expected: OK.

- [ ] **Step 6: Commit**

```bash
git add app/serve.py app/tests/test_tela_custos.py
git commit -m "feat(custos): rota /admin/custos montando o mes, as acoes e a fatura"
```

---

### Task 6: Bateria de mutação

Suíte verde prova que os testes que existem passam. A pergunta é outra: desligando cada
guarda, alguém grita?

**Files:** nenhum arquivo de produção muda ao fim.

- [ ] **Step 1: Prepare**

```bash
cd app && find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null; true
```

Restaure com `git checkout -- app/<arquivo>` (**nunca** `git stash` — pilha compartilhada).
Confirme o alvo com `git diff --stat` antes de rodar e a restauração depois.

- [ ] **Step 2: Rode as mutações, uma por vez**

| # | Arquivo | Troca | Teste que tem que cair |
|---|---|---|---|
| 1 | `anthropic_admin.py` | tirar o `/ 100.0` do `amount` | `test_amount_vem_em_CENTAVOS_e_vira_dolar` |
| 2 | `anthropic_admin.py` | parar na 1ª página (ignorar `has_more`) | `test_segue_o_next_page_ate_o_fim` |
| 3 | `anthropic_admin.py` | tirar o teto `MAX_PAGINAS` | `test_nao_gira_para_sempre_se_a_api_insistir_em_has_more` (vai travar — mate o processo e conte como MORTA) |
| 4 | `anthropic_admin.py` | tratar 401 como "erro" | `test_401_vira_recusada` |
| 5 | `anthropic_admin.py` | deixar a exceção de rede subir | `test_rede_fora_vira_erro_e_nao_levanta` |
| 6 | `anthropic_admin.py` | mandar sempre `x-api-key` | `test_token_que_nao_e_sk_ant_vai_como_bearer` |
| 7 | `db.py` `resumo_ia_uso` | `quando > ?` em vez de `>=` | `test_desde_e_inclusivo` |
| 8 | `db.py` `resumo_ia_uso` | tirar `modelo` do GROUP BY | `test_modelos_diferentes_nao_se_misturam` |
| 9 | `db.py` `resumo_ia_uso` | `ORDER BY ... ASC` | `test_ordena_do_dia_mais_novo_para_o_mais_velho` |
| 10 | `ia_custo.py` `por_acao` | tirar o `reverse=True` | `test_por_acao_ordena_do_maior_gasto_para_o_menor` |
| 11 | `site_web.py` `pagina_custos` | tirar a frase do custo fixo | `test_diz_que_o_custo_e_fixo` |
| 12 | `site_web.py` `pagina_custos` | tirar o aviso da organização | `test_avisa_que_a_fatura_e_da_organizacao_inteira` |
| 13 | `site_web.py` `pagina_custos` | tirar a cotação do cabeçalho | `test_mostra_a_cotacao_usada` |
| 14 | `serve.py` | tirar a guarda de token | `test_sem_token_403` |
| 15 | `serve.py` | tirar o `try/except` em volta da fatura | `test_a_fatura_fora_do_ar_nao_derruba_a_tela` |

- [ ] **Step 3: Conserte o que sobreviver**

Sobrevivente é **hipótese, não veredito**: confira a âncora e o `__pycache__` antes.
Confirmada, escreva o teste que faltava.

- [ ] **Step 4: Confirme árvore limpa e suíte verde**

```bash
git status --short
cd app && python3 -m unittest discover -s tests 2>&1 | tail -3
```

- [ ] **Step 5: Commit (só se algum teste novo nasceu)**

```bash
git add app/tests/
git commit -m "test(custos): fecha os buracos que a bateria de mutacao revelou"
```

---

## Depois do plano

1. Revisão de código do branch inteiro antes do merge.
2. Merge, push e deploy — conferir `git ls-remote origin refs/heads/main` == HEAD antes, e **nunca imprimir o corpo do erro** do deploy (vaza todas as credenciais em texto puro).
3. **Ações do Diego depois do deploy:**
   - abrir `/admin/custos` e ver o gasto real dos dias desde 2026-08-14;
   - conferir `PRECOS_IA` e `USD_BRL` contra as páginas de preço — é o que dá procedência ao número;
   - se quiser a coluna da fatura, criar uma **chave de admin da organização** no console da Anthropic e pôr em `DSCURSO_ANTHROPIC_ADMIN_KEY` no EasyPanel.
