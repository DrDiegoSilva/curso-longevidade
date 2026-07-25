# Máquina de conteúdo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Religar o pipeline automático de conteúdo com frescor (varredura semanal, selo "Estudo recente"), fila priorizada sem piso, e uma pirâmide de fontes (fresco → reserva → clássicos → empréstimo entre temas) que garante "nunca faltar", mantendo o preview das 18h como gate humano universal.

**Architecture:** Reusa a máquina existente (`curadoria` → `reserva`/`candidatos` → `agenda_plan` → `daily.preparar_18h`/`enviar_slot`). Adiciona: (1) noção de "fresco" derivada da data de publicação, calculada no envio; (2) candidatos alimentam a agenda direto (resumo JIT), sem gate manual; (3) um banco de clássicos evergreen por citações; (4) `_rank` fresh-first + clássico-como-piso; (5) cron de varredura no domingo de manhã. Segue o padrão de funções puras testáveis em `agenda_plan` e injeção de rede/IA em `curadoria`/`sources`.

**Tech Stack:** Python 3 (stdlib), unittest, SQLite (dev) / Postgres-Supabase (prod) via `db.py`, Europe PMC + OpenAlex (`sources.py`), Claude Haiku/Sonnet (`resumo_diario`).

## Global Constraints

- **Testes:** `cd app && python3 -m unittest discover -s tests` (rodar da pasta `app/`). Cada teste novo é um arquivo/classe em `app/tests/`.
- **Gate humano:** o preview das 18h (`preparar_18h` → `/revisar`) NUNCA é removido. Nada vai pro assinante sem passar por ele. Silêncio = envia 08h.
- **Frescor = ≤ `config.FRESCO_DIAS` (default 30) dias**, medido pela **data de publicação no dia do envio**. Selo único: **`🆕 *Estudo recente*`**. Acima de 30d: sem selo.
- **Sem piso de qualidade:** todo candidato ENTRA entra; `score` = prioridade na fila; teto por tema (`curadoria.CAPS`) corta a cauda no scan.
- **Fresco fura a fila do TEMA dele, mas respeita a rotação/variedade** (espera o dia do tema).
- **Envio segue seg–sex** (`_dias_envio`); o cron de varredura roda domingo mas não envia domingo.
- **Imutabilidade / estilo:** funções puras onde der (padrão `agenda_plan`); rede/IA injetáveis (`buscar_fn`/`triar_fn`/`llm_fn`); nada de `git add -A` (stagear só os arquivos da task).
- **Clássicos NÃO são consumidos no envio** (reusáveis por ciclo); reserva/candidato são consumidos (status `enviado`/`resumido`).
- **Sem mexer no layout de páginas** (Curadoria): a aprovação visual de clássicos é follow-up a brainstormar com o Diego ([[feedback-nao-supor-landing]]). Este plano entrega o motor + gatilhos (CLI + botão admin no padrão atual).

---

## Fase 1 — Frescor (selo)

### Task 1: Helper de frescor `_e_fresco` + `config.FRESCO_DIAS`

**Files:**
- Modify: `app/config.py` (junto aos outros parâmetros de env, ~linha 68)
- Modify: `app/daily.py` (novo helper após `_hoje_iso`, ~linha 65)
- Test: `app/tests/test_fresco.py` (criar)

**Interfaces:**
- Produces: `config.FRESCO_DIAS: int` (default 30); `daily._e_fresco(data_pub: str, ref: date|None = None) -> bool` — True se `data_pub` (YYYY-MM-DD, tolera vazio/parcial) está a 0..FRESCO_DIAS dias de `ref` (default hoje).

- [ ] **Step 1: Escrever o teste que falha**

```python
# app/tests/test_fresco.py
import os, sys, unittest
from datetime import date
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import daily

class TestEFresco(unittest.TestCase):
    def test_recente_e_fresco(self):
        self.assertTrue(daily._e_fresco("2026-07-01", ref=date(2026, 7, 25)))   # 24 dias

    def test_borda_30_dias(self):
        self.assertTrue(daily._e_fresco("2026-06-25", ref=date(2026, 7, 25)))   # 30 dias exatos
        self.assertFalse(daily._e_fresco("2026-06-24", ref=date(2026, 7, 25)))  # 31 dias

    def test_futuro_conta_como_fresco(self):
        self.assertTrue(daily._e_fresco("2026-07-30", ref=date(2026, 7, 25)))   # publicação futura

    def test_data_vazia_ou_invalida_false(self):
        self.assertFalse(daily._e_fresco("", ref=date(2026, 7, 25)))
        self.assertFalse(daily._e_fresco("lixo", ref=date(2026, 7, 25)))
        self.assertFalse(daily._e_fresco("2026-07", ref=date(2026, 7, 25)))     # parcial

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd app && python3 -m unittest tests.test_fresco -v`
Expected: FAIL (`AttributeError: module 'daily' has no attribute '_e_fresco'`)

- [ ] **Step 3: Implementar**

Em `app/config.py`, logo após `SLOT_TETO_DEFAULT` (~linha 68):
```python
# ── Máquina de conteúdo ──
FRESCO_DIAS = int(os.environ.get("DSCURSO_FRESCO_DIAS") or 30)   # ≤ N dias = "Estudo recente"
```

Em `app/daily.py`, após `_hoje_iso` (~linha 65):
```python
def _e_fresco(data_pub, ref=None):
    """True se o paper foi publicado nos últimos config.FRESCO_DIAS dias (medido em `ref`,
    default hoje). Tolera data vazia/parcial/inválida (retorna False). Publicação futura conta."""
    from datetime import date
    ref = ref or date.today()
    try:
        pub = date.fromisoformat((data_pub or "")[:10])
    except (ValueError, TypeError):
        return False
    idade = (ref - pub).days
    return idade <= config.FRESCO_DIAS       # idade negativa (futuro) também é fresco
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd app && python3 -m unittest tests.test_fresco -v`
Expected: PASS (4 testes)

- [ ] **Step 5: Commit**

```bash
git add app/config.py app/daily.py app/tests/test_fresco.py
git commit -m "feat(conteudo): helper _e_fresco + config.FRESCO_DIAS (janela de 30 dias)"
```

---

### Task 2: Selo "Estudo recente" na mensagem

**Files:**
- Modify: `app/daily.py` — `montar_texto_resumo` (~linha 374), `_montar_ctx` (~linha 447), `_enviar_estudo_para` (~linha 470)
- Test: `app/tests/test_texto_resumo.py` (adicionar casos)

**Interfaces:**
- Consumes: `daily._e_fresco` (Task 1).
- Produces: `daily.montar_texto_resumo(titulo, resumo, tmeta, fresco=False) -> str` — prefixa `🆕 *Estudo recente*` quando `fresco`; `ctx["fresco"]: bool` em `_montar_ctx`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# app/tests/test_texto_resumo.py  (adicionar à classe existente ou criar TestSeloFresco)
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import daily

class TestSeloFresco(unittest.TestCase):
    def test_fresco_tem_selo(self):
        tmeta = {"rotulo": "Obesidade", "emoji": "⚖️"}
        txt = daily.montar_texto_resumo("Título X", "corpo", tmeta, fresco=True)
        self.assertIn("🆕", txt)
        self.assertIn("Estudo recente", txt)
        self.assertTrue(txt.index("Estudo recente") < txt.index("Título X"))  # selo no topo

    def test_nao_fresco_sem_selo(self):
        txt = daily.montar_texto_resumo("Título X", "corpo", {"rotulo": "Obesidade"}, fresco=False)
        self.assertNotIn("Estudo recente", txt)

    def test_default_sem_selo(self):
        txt = daily.montar_texto_resumo("T", "c", {})
        self.assertNotIn("Estudo recente", txt)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd app && python3 -m unittest tests.test_texto_resumo.TestSeloFresco -v`
Expected: FAIL (`montar_texto_resumo() got an unexpected keyword argument 'fresco'`)

- [ ] **Step 3: Implementar**

`montar_texto_resumo` (substituir a função inteira, ~linha 374):
```python
def montar_texto_resumo(titulo, resumo, tmeta, fresco=False):
    """Texto do WhatsApp p/ o assinante: selo de recência (se fresco) + badge do tema
    (emoji + rótulo) + título + resumo."""
    rot = (tmeta or {}).get("rotulo", "")
    emoji = (tmeta or {}).get("emoji", "")
    selo = "🆕 *Estudo recente*\n" if fresco else ""
    hdr = f"{emoji} *{rot}*\n".lstrip() if rot else ""
    return f"{selo}{hdr}🔬 *{titulo}*\n\n{resumo}"
```

`_montar_ctx` — adicionar `fresco` ao dict retornado (~linha 454):
```python
    return {"r": r, "art": art, "titulo": titulo, "conteudo": conteudo, "tmeta": tmeta,
            "fresco": _e_fresco(art.get("data", "")),
            "audio_bytes": _audio_master(hoje, art, conteudo),
            "master_pdf": _pdf_master(hoje, art, conteudo, tmeta)}
```

`_enviar_estudo_para` — passar `ctx["fresco"]` (~linha 475):
```python
    msg = deliver.personalizar_rodape(
        montar_texto_resumo(ctx["titulo"], ctx["r"]["resumo"], ctx["tmeta"], fresco=ctx.get("fresco", False)),
        nome, link)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd app && python3 -m unittest tests.test_texto_resumo -v`
Expected: PASS (novos + regressão dos existentes)

- [ ] **Step 5: Commit**

```bash
git add app/daily.py app/tests/test_texto_resumo.py
git commit -m "feat(conteudo): selo 'Estudo recente' na msg quando o estudo é fresco (≤30d no envio)"
```

---

## Fase 2 — Citações (fonte dos clássicos)

### Task 3: `parse_openalex` puro com `citacoes` (cited_by_count)

**Files:**
- Modify: `app/sources.py` — extrair `parse_openalex(data)` puro de `_openalex_normalizado` (~linha 112)
- Test: `app/tests/test_sources.py` (adicionar)

**Interfaces:**
- Produces: `sources.parse_openalex(data: dict) -> list[dict]` — cada item ganha `"citacoes": int`. `_openalex_normalizado` passa a chamar `parse_openalex`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# app/tests/test_sources.py  (adicionar)
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sources

class TestParseOpenAlex(unittest.TestCase):
    def _fake(self, inv, cited):
        return {"results": [{
            "title": "Semaglutide CV outcomes",
            "abstract_inverted_index": inv,
            "primary_location": {"source": {"display_name": "NEJM"}},
            "doi": "https://doi.org/10.1/x", "id": "https://openalex.org/W1",
            "publication_date": "2023-01-01", "type": "article",
            "cited_by_count": cited,
        }]}

    def test_extrai_citacoes(self):
        inv = {w: [i] for i, w in enumerate(("a " * 40).split())}   # abstract >120 chars
        got = sources.parse_openalex(self._fake(inv, 3120))
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["citacoes"], 3120)
        self.assertEqual(got[0]["banco"], "openalex")

    def test_sem_citacoes_default_zero(self):
        inv = {w: [i] for i, w in enumerate(("a " * 40).split())}
        d = self._fake(inv, 0); del d["results"][0]["cited_by_count"]
        self.assertEqual(sources.parse_openalex(d)[0]["citacoes"], 0)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd app && python3 -m unittest tests.test_sources.TestParseOpenAlex -v`
Expected: FAIL (`module 'sources' has no attribute 'parse_openalex'`)

- [ ] **Step 3: Implementar**

Em `app/sources.py`, substituir `_openalex_normalizado` (~linha 112) por um parser puro + o wrapper de rede:
```python
def parse_openalex(data):
    """Normaliza a resposta do OpenAlex. Só artigos COM abstract. Puro/testável.
    Inclui 'citacoes' (cited_by_count) p/ ranquear clássicos."""
    out = []
    for w in (data or {}).get("results", []) or []:
        ab = reconstruir_abstract(w.get("abstract_inverted_index"))
        if len(ab) < 120:
            continue
        src = (w.get("primary_location") or {}).get("source") or {}
        doi = (w.get("doi") or "").replace("https://doi.org/", "")
        out.append({
            "titulo": (w.get("title") or "").strip(),
            "resumo": " ".join(ab.split()),
            "fonte": src.get("display_name") or "",
            "doi": doi,
            "url": w.get("doi") or w.get("id") or "",
            "data": w.get("publication_date", ""),
            "tipo": w.get("type", ""),
            "citacoes": int(w.get("cited_by_count", 0) or 0),
            "banco": "openalex",
        })
    return out


def _openalex_normalizado(query, desde, ate):
    """OpenAlex: 250M+ trabalhos, abstract + citações, sem chave. Só artigos COM abstract."""
    filtro = f"from_publication_date:{desde},to_publication_date:{ate},type:article,has_abstract:true"
    url = ("https://api.openalex.org/works?search=" + urllib.parse.quote(query)
           + "&filter=" + urllib.parse.quote(filtro)
           + "&per-page=40&sort=relevance_score:desc&mailto=" + urllib.parse.quote(_MAILTO))
    return parse_openalex(_get(url))
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd app && python3 -m unittest tests.test_sources -v`
Expected: PASS (novos + regressão)

- [ ] **Step 5: Commit**

```bash
git add app/sources.py app/tests/test_sources.py
git commit -m "refactor(sources): parse_openalex puro + expõe 'citacoes' (cited_by_count) p/ clássicos"
```

---

## Fase 3 — Camada de dados (clássicos + candidatos na agenda)

### Task 4: `db` — tabela `classicos`, colunas de candidato e helpers de pool

**Files:**
- Modify: `app/config.py` (~linha 68, junto de FRESCO_DIAS)
- Modify: `app/db.py` — schema (~linha 174), `_TABELAS` (210), `_migrar_colunas` (227), `salvar_candidatos` (541), `listar_candidatos` (564), novos helpers
- Test: `app/tests/test_db.py` (adicionar)

**Interfaces:**
- Produces:
  - `config.CLASSICO_REUSO_MESES: int` (default 6)
  - `db.salvar_classico(reg: dict) -> str` (id)
  - `db.listar_classicos(tema: str|None = None, elegiveis: bool = True) -> list[dict]` — quando `elegiveis`, só clássicos nunca-enviados OU com `ultimo_envio` mais antigo que o piso; ordena por `ultimo_envio` asc (nulos primeiro), `citacoes` desc.
  - `db.obter_classico(cid) -> dict|None`
  - `db.marcar_classico_enviado(cid: str, data: str) -> None` (seta `ultimo_envio`, NÃO deleta)
  - `db.listar_candidatos(status=None, tema=None, tipo=None)` — filtro `tipo` novo
  - `db.marcar_candidato_agendado(cid) -> None` / `db.marcar_candidato_pronto(cid) -> None` (status `agendado`/`novo`)
  - `db.agenda_ref_ids(tipo: str) -> set[str]`
  - `salvar_candidatos` grava `citacoes` e `tipo`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# app/tests/test_db.py  (adicionar; usa o setUp de banco temporário já padrão nos testes de db)
import os, sys, unittest, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

class TestClassicos(unittest.TestCase):
    def setUp(self):   # padrão do repo (ver test_agenda_materializar.py)
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ.pop("DATABASE_URL", None)
        import importlib, config as _cfg; importlib.reload(_cfg)
        import db as _db; importlib.reload(_db)
        self.db = _db; _db.init()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_salvar_e_listar_ciclo(self):
        a = self.db.salvar_classico({"tema": "Obesidade", "titulo_pt": "STEP", "resumo": "r",
                                     "data": "2021-01-01", "citacoes": 4200})
        b = self.db.salvar_classico({"tema": "Obesidade", "titulo_pt": "SELECT", "resumo": "r",
                                     "data": "2023-01-01", "citacoes": 3100})
        # ambos nunca-enviados -> elegíveis, mais citado primeiro
        elig = self.db.listar_classicos(tema="Obesidade")
        self.assertEqual([x["id"] for x in elig], [a, b])
        # envia 'a' hoje -> sai da elegibilidade (piso de meses), 'b' fica
        self.db.marcar_classico_enviado(a, "2026-07-25")
        elig2 = self.db.listar_classicos(tema="Obesidade")
        self.assertEqual([x["id"] for x in elig2], [b])
        # 'a' não foi deletado
        self.assertIsNotNone(self.db.obter_classico(a))

    def test_candidato_tipo_e_citacoes(self):
        self.db.salvar_candidatos([{"tema": "Obesidade", "titulo": "T", "chave": "k1",
                                    "score": 8, "citacoes": 900, "tipo": "classico", "data": "2020-01-01"}])
        self.assertEqual(self.db.listar_candidatos(tipo="classico")[0]["citacoes"], 900)
        self.assertEqual(self.db.listar_candidatos(tipo="varredura"), [])
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd app && python3 -m unittest tests.test_db.TestClassicos -v`
Expected: FAIL (`module 'db' has no attribute 'salvar_classico'`)

- [ ] **Step 3: Implementar**

`config.py` (após `FRESCO_DIAS`):
```python
CLASSICO_REUSO_MESES = int(os.environ.get("DSCURSO_CLASSICO_REUSO_MESES") or 6)   # piso p/ repetir um clássico
```

`db.py` — no bloco `CREATE TABLE`, ajustar `curadoria_candidatos` (adicionar 2 colunas) e adicionar `classicos` (após `reserva_resumos`, ~linha 181):
```sql
            CREATE TABLE IF NOT EXISTS curadoria_candidatos (
                id TEXT PRIMARY KEY,
                tema TEXT, titulo TEXT, fonte TEXT, data TEXT, doi TEXT, url TEXT,
                abstract TEXT, pergunta TEXT, score REAL, chave TEXT UNIQUE,
                citacoes INTEGER DEFAULT 0, tipo TEXT DEFAULT 'varredura',
                status TEXT DEFAULT 'novo', criado_em TEXT
            );
            CREATE TABLE IF NOT EXISTS classicos (
                id TEXT PRIMARY KEY, tema TEXT, titulo_pt TEXT, resumo TEXT,
                gancho TEXT, grafico TEXT, doi TEXT, fonte TEXT, url TEXT, data TEXT,
                citacoes INTEGER DEFAULT 0, ultimo_envio TEXT, criado_em TEXT
            );
```

`_TABELAS` (~linha 212): adicionar `"classicos"`.

`_migrar_colunas` (~linha 240): adicionar (p/ o Supabase de produção):
```python
        _add_coluna(c, "curadoria_candidatos", "citacoes", "INTEGER DEFAULT 0")
        _add_coluna(c, "curadoria_candidatos", "tipo", "TEXT DEFAULT 'varredura'")
```

`salvar_candidatos` (~linha 550) — incluir `citacoes` e `tipo` no INSERT:
```python
            cur = c.execute(
                """INSERT INTO curadoria_candidatos
                   (id,tema,titulo,fonte,data,doi,url,abstract,pergunta,score,chave,citacoes,tipo,status,criado_em)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, 'novo', ?)
                   ON CONFLICT (chave) DO NOTHING""",
                (secrets.token_hex(8), x.get("tema", ""), x.get("titulo", ""), x.get("fonte", ""),
                 x.get("data", ""), x.get("doi", ""), x.get("url", ""), x.get("abstract", ""),
                 x.get("pergunta", ""), float(x.get("score", 0) or 0), x.get("chave"),
                 int(x.get("citacoes", 0) or 0), x.get("tipo", "varredura"),
                 datetime.now().isoformat()))
```

`listar_candidatos` (~linha 564) — filtro `tipo`:
```python
def listar_candidatos(status=None, tema=None, tipo=None):
    q = "SELECT * FROM curadoria_candidatos"
    conds, params = [], []
    if status:
        conds.append("status=?"); params.append(status)
    if tema:
        conds.append("tema=?"); params.append(tema)
    if tipo:
        conds.append("tipo=?"); params.append(tipo)
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY tema, score DESC, criado_em DESC"
    with _conn() as c:
        return [dict(r) for r in c.execute(q, params).fetchall()]
```

Helpers novos (após `marcar_candidatos`, ~linha 594):
```python
def marcar_candidato_agendado(cid):
    """Prende um candidato na agenda (sai do pool 'novo' até enviar/soltar)."""
    with _conn() as c:
        c.execute("UPDATE curadoria_candidatos SET status='agendado' WHERE id=?", (cid,))


def marcar_candidato_pronto(cid):
    """Devolve um candidato agendado ao pool (reconciliação de órfão)."""
    with _conn() as c:
        c.execute("UPDATE curadoria_candidatos SET status='novo' WHERE id=?", (cid,))
```

Banco de clássicos (após os helpers de reserva, ~linha 670):
```python
def salvar_classico(reg):
    """Banca um estudo-marco (evergreen, reusável). Retorna o id."""
    import secrets
    from datetime import datetime
    cid = secrets.token_hex(8)
    with _conn() as c:
        c.execute(
            """INSERT INTO classicos
               (id,tema,titulo_pt,resumo,gancho,grafico,doi,fonte,url,data,citacoes,criado_em)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (cid, reg.get("tema", ""), reg.get("titulo_pt", ""), reg.get("resumo", ""),
             reg.get("gancho", ""), reg.get("grafico", ""), reg.get("doi", ""), reg.get("fonte", ""),
             reg.get("url", ""), reg.get("data", ""), int(reg.get("citacoes", 0) or 0),
             datetime.now().isoformat()))
    return cid


def obter_classico(cid):
    with _conn() as c:
        r = c.execute("SELECT * FROM classicos WHERE id=?", (cid,)).fetchone()
    return dict(r) if r else None


def listar_classicos(tema=None, elegiveis=True):
    """Clássicos do banco. elegiveis=True filtra por ciclo: nunca-enviado OU ultimo_envio mais
    antigo que config.CLASSICO_REUSO_MESES; ordena nunca-enviado/mais-antigo primeiro, + citado."""
    q = "SELECT * FROM classicos"
    conds, params = [], []
    if tema:
        conds.append("tema=?"); params.append(tema)
    if elegiveis:
        from datetime import datetime, timedelta
        corte = (datetime.now() - timedelta(days=30 * config.CLASSICO_REUSO_MESES)).isoformat()
        conds.append("(ultimo_envio IS NULL OR ultimo_envio < ?)"); params.append(corte)
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY (ultimo_envio IS NOT NULL), ultimo_envio ASC, citacoes DESC"
    with _conn() as c:
        return [dict(r) for r in c.execute(q, params).fetchall()]


def marcar_classico_enviado(cid, data):
    """Marca o envio de um clássico (NÃO deleta — reusável no próximo ciclo)."""
    with _conn() as c:
        c.execute("UPDATE classicos SET ultimo_envio=? WHERE id=?", (data, cid))
```

Generalizar `agenda_ref_ids_reserva` — adicionar (após ~linha 762):
```python
def agenda_ref_ids(tipo):
    """ref_ids de um tipo de slot (reserva/candidato/classico) — p/ a reconciliação."""
    with _conn() as c:
        rows = c.execute("SELECT ref_id FROM agenda WHERE tipo=? AND ref_id IS NOT NULL", (tipo,)).fetchall()
    return {r["ref_id"] for r in rows}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd app && python3 -m unittest tests.test_db.TestClassicos -v`
Expected: PASS. Depois rode `cd app && python3 -m unittest tests.test_db -v` (regressão).

> **Nota:** o setUp segue o padrão real do repo (`test_agenda_materializar.py`): `DSCURSO_ARTIGOS_DB` + `DSCURSO_DATA` + `pop DATABASE_URL` + reload de `config`/`db`.

- [ ] **Step 5: Commit**

```bash
git add app/config.py app/db.py app/tests/test_db.py
git commit -m "feat(conteudo): tabela classicos (evergreen/reusável) + colunas tipo/citacoes em candidatos + helpers de pool"
```

---

### Task 5: `curadoria.varrer_classicos` + `rodar_varredura_classicos`

**Files:**
- Modify: `app/curadoria.py` — `_normalizar` (~linha 31) inclui `citacoes`; novas funções
- Test: `app/tests/test_curadoria.py` (adicionar)

**Interfaces:**
- Consumes: `sources.parse_openalex`/`search_all` (Task 3), `db.salvar_candidatos` com `tipo`/`citacoes` (Task 4).
- Produces: `curadoria.varrer_classicos(caps=None, buscar_fn=None, triar_fn=None, anos=10) -> list[dict]` (candidatos `tipo="classico"`, ordenados por citações); `curadoria.rodar_varredura_classicos() -> int` (novos salvos).

- [ ] **Step 1: Escrever o teste que falha**

```python
# app/tests/test_curadoria.py  (adicionar)
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import curadoria

class TestVarrerClassicos(unittest.TestCase):
    def test_ordena_por_citacoes_e_marca_tipo(self):
        def fake_buscar(query, desde, ate):
            return [
                {"titulo": "Menos citado", "doi": "d1", "citacoes": 100, "resumo": "x" * 200},
                {"titulo": "Marco", "doi": "d2", "citacoes": 5000, "resumo": "y" * 200},
            ]
        def fake_triar(arts, tema):
            # tudo ENTRA, score fixo; preserva citacoes
            return [dict(a, tema=tema, score=7) for a in arts]
        got = curadoria.varrer_classicos(caps={"Obesidade": 20, "Hormonal": 0, "Performance": 0,
                                               "Longevidade": 0, "Lipedema": 0},
                                        buscar_fn=fake_buscar, triar_fn=fake_triar, anos=10)
        obes = [c for c in got if c["tema"] == "Obesidade"]
        self.assertEqual(obes[0]["titulo"], "Marco")          # mais citado primeiro
        self.assertEqual(obes[0]["tipo"], "classico")
        self.assertEqual(obes[0]["citacoes"], 5000)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd app && python3 -m unittest tests.test_curadoria.TestVarrerClassicos -v`
Expected: FAIL (`module 'curadoria' has no attribute 'varrer_classicos'`)

- [ ] **Step 3: Implementar**

`_normalizar` (~linha 31) — acrescentar `citacoes` e `tipo` ao dict:
```python
def _normalizar(a, tema, tipo="varredura"):
    return {
        "tema": tema,
        "titulo": (a.get("titulo") or "").strip(),
        "fonte": a.get("fonte") or "",
        "data": a.get("data") or "",
        "doi": a.get("doi") or "",
        "url": a.get("url") or "",
        "abstract": (a.get("resumo") or "")[:2500],
        "score": float(a.get("score", 5) or 0),
        "citacoes": int(a.get("citacoes", 0) or 0),
        "tipo": tipo,
        "chave": _chave(a),
    }
```

Novas funções (após `varrer`, ~linha 80):
```python
def varrer_classicos(caps=None, buscar_fn=None, triar_fn=None, anos=10):
    """Estudos-marco por tema: busca numa janela ampla (anos) -> triagem (corta LIXO) ->
    top(cap) por CITAÇÕES desc, dedup global. Candidatos marcados tipo='classico'.
    buscar_fn/triar_fn injetáveis (teste sem rede)."""
    from datetime import date, timedelta
    caps = caps or CAPS
    if buscar_fn is None:
        import sources
        buscar_fn = sources.search_all
    if triar_fn is None:
        import triage
        triar_fn = triage.triar
    cfg = _cfg()
    desde = (date.today() - timedelta(days=365 * anos)).isoformat()
    ate = date.today().isoformat()
    vistos, out = set(), []
    for nome, meta in cfg["temas"].items():
        cap = int(caps.get(nome, 6))
        if cap <= 0:
            continue
        try:
            arts = buscar_fn(meta.get("query", ""), desde, ate)
            bons = []
            for k in range(0, len(arts), 20):
                bons += triar_fn(arts[k:k + 20], nome)
        except Exception as e:
            print(f"[classicos] {nome} falhou: {e}", flush=True)
            continue
        bons.sort(key=lambda x: x.get("citacoes", 0), reverse=True)
        n = 0
        for a in bons:
            k = _chave(a)
            if not k or k in vistos:
                continue
            vistos.add(k)
            out.append(_normalizar(a, nome, tipo="classico"))
            n += 1
            if n >= cap:
                break
    return out


def rodar_varredura_classicos(caps=None):
    """Varre clássicos (por citações) + gera perguntas (Haiku) + salva candidatos tipo='classico'."""
    import db
    db.init()
    cands = varrer_classicos(caps=caps)
    gerar_perguntas(cands)
    n = db.salvar_candidatos(cands)
    print(f"[classicos] varredura: {len(cands)} candidatos, {n} novos salvos", flush=True)
    return n
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd app && python3 -m unittest tests.test_curadoria -v`
Expected: PASS (novos + regressão)

- [ ] **Step 5: Commit**

```bash
git add app/curadoria.py app/tests/test_curadoria.py
git commit -m "feat(conteudo): varredura de clássicos por citações (janela ampla) -> candidatos tipo classico"
```

---

### Task 6: `gerar_selecionados` roteia clássicos pro banco

**Files:**
- Modify: `app/curadoria.py` — `gerar_selecionados` (~linha 211)
- Test: `app/tests/test_curadoria.py` (adicionar)

**Interfaces:**
- Consumes: `db.salvar_classico` (Task 4), candidatos com `tipo` (Task 4/5).
- Produces: `gerar_selecionados` inalterado na assinatura, mas selecionados `tipo="classico"` vão pra `db.salvar_classico` (banco), os demais pra `db.salvar_reserva`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# app/tests/test_curadoria.py  (adicionar)
class TestGerarRoteia(unittest.TestCase):
    def test_classico_vai_pro_banco(self):
        chamados = {"classico": 0, "reserva": 0}
        class FakeDB:
            def init(self): pass
            def listar_candidatos(self, status=None):
                return [{"id": "c1", "tema": "Obesidade", "tipo": "classico", "titulo": "STEP",
                         "abstract": "z" * 300, "citacoes": 4000, "doi": "d", "fonte": "f", "url": "u", "data": "2021-01-01"},
                        {"id": "c2", "tema": "Hormonal", "tipo": "varredura", "titulo": "Novo",
                         "abstract": "w" * 300, "doi": "d2", "fonte": "f", "url": "u", "data": "2026-07-01"}]
            def salvar_classico(self, reg): chamados["classico"] += 1; return "k"
            def salvar_reserva(self, reg): chamados["reserva"] += 1; return "r"
            def marcar_candidatos(self, ids, status): pass
        import curadoria
        curadoria.gerar_selecionados(db_mod=FakeDB(),
                                     gerar_resumo_fn=lambda c: {"titulo_pt": "T", "resumo": "R", "gancho": "", "grafico": None})
        self.assertEqual(chamados, {"classico": 1, "reserva": 1})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd app && python3 -m unittest tests.test_curadoria.TestGerarRoteia -v`
Expected: FAIL (`gerar_selecionados() got an unexpected keyword argument 'db_mod'`)

- [ ] **Step 3: Implementar**

`gerar_selecionados` (substituir a função, ~linha 211) — injeção de db/gerador p/ teste + roteamento:
```python
def gerar_selecionados(db_mod=None, gerar_resumo_fn=None):
    """Gera o resumo (padrão) de cada candidato 'selecionado'. tipo='classico' -> banco de
    clássicos; senão -> reserva. Retorna quantos. db_mod/gerar_resumo_fn injetáveis p/ teste."""
    if db_mod is None:
        import db as db_mod
    db_mod.init()
    _gera = gerar_resumo_fn or gerar_resumo
    feitos = 0
    for c in db_mod.listar_candidatos(status="selecionado"):
        try:
            r = _gera(c)
            reg = {"tema": c["tema"], "titulo_pt": r["titulo_pt"], "resumo": r["resumo"],
                   "gancho": r.get("gancho", ""),
                   "grafico": json.dumps(r["grafico"], ensure_ascii=False) if r.get("grafico") else "",
                   "doi": c.get("doi", ""), "fonte": c.get("fonte", ""), "url": c.get("url", ""),
                   "data": c.get("data", "")}
            if c.get("tipo") == "classico":
                reg["citacoes"] = c.get("citacoes", 0)
                db_mod.salvar_classico(reg)
            else:
                reg["candidato_id"] = c["id"]
                db_mod.salvar_reserva(reg)
            db_mod.marcar_candidatos([c["id"]], "resumido")
            feitos += 1
        except Exception as e:
            print(f"[curadoria] gerar resumo falhou ({c.get('titulo','')[:40]}): {e}", flush=True)
    print(f"[curadoria] {feitos} resumo(s) gerado(s)", flush=True)
    return feitos
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd app && python3 -m unittest tests.test_curadoria -v`
Expected: PASS (novos + regressão — o CLI `gerar` segue chamando `gerar_selecionados()` sem args)

- [ ] **Step 5: Commit**

```bash
git add app/curadoria.py app/tests/test_curadoria.py
git commit -m "feat(conteudo): gerar_selecionados roteia clássicos aprovados pro banco (reserva p/ o resto)"
```

---

## Fase 4 — Agenda fresh-first + pirâmide

### Task 7: `agenda_plan` — `_rank` fresh-first/clássico-piso + `classificar_slot`

**Files:**
- Modify: `app/agenda_plan.py` — `_rank` (~linha 42), `classificar_slot` (~linha 80)
- Test: `app/tests/test_agenda_plan.py` (adicionar/ajustar)

**Interfaces:**
- Produces: `_rank` considera `cand["fresco"]` (bool), `cand["classico"]` (bool), `cand["score"]` (num). `classificar_slot` reconhece `tipo` `"candidato"` e `"classico"` → retorna `("candidato", ref_id)` / `("classico", ref_id)`.
- Consumes (mais tarde): `planejar_agenda` recebe candidatos anotados (Task 8).

- [ ] **Step 1: Escrever o teste que falha**

```python
# app/tests/test_agenda_plan.py  (adicionar)
def _c(tema, tipo="reserva", fresco=False, classico=False, score=5, ref_id="r"):
    return {"tipo": tipo, "tema": tema, "titulo": "t", "ref_id": ref_id, "payload": None,
            "fresco": fresco, "classico": classico, "score": score}

class TestRankPiramide(unittest.TestCase):
    def test_fresco_vence_estoque_mesmo_tema(self):
        dias = [("2026-07-27", None, False)]
        cands = [_c("Obesidade", fresco=False, score=9), _c("Obesidade", fresco=True, score=6, ref_id="f")]
        plano = ap.planejar_agenda(dias, cands, ["Obesidade"], None)
        self.assertEqual(plano["2026-07-27"]["ref_id"], "f")     # fresco fura, mesmo com score menor

    def test_classico_e_piso(self):
        dias = [("2026-07-27", None, False)]
        cands = [_c("Obesidade", classico=True, score=9, ref_id="cl"),
                 _c("Obesidade", classico=False, score=3, ref_id="rs")]
        plano = ap.planejar_agenda(dias, cands, ["Obesidade"], None)
        self.assertEqual(plano["2026-07-27"]["ref_id"], "rs")    # estoque comum > clássico

    def test_emprestimo_entre_temas(self):
        dias = [("2026-07-27", None, False)]
        cands = [_c("Obesidade", classico=True, score=8, ref_id="ob")]   # só há clássico de Obesidade
        plano = ap.planejar_agenda(dias, cands, ["Performance"], None)   # dia pedia Performance
        self.assertEqual(plano["2026-07-27"]["ref_id"], "ob")            # empresta do gigante

    def test_classificar_slot_novos_tipos(self):
        self.assertEqual(ap.classificar_slot({"tipo": "candidato", "ref_id": "x"}), ("candidato", "x"))
        self.assertEqual(ap.classificar_slot({"tipo": "classico", "ref_id": "y"}), ("classico", "y"))
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd app && python3 -m unittest tests.test_agenda_plan.TestRankPiramide -v`
Expected: FAIL (fresco não priorizado; `classificar_slot` não reconhece os tipos novos)

- [ ] **Step 3: Implementar**

`_rank` (substituir, ~linha 42):
```python
def _rank(cand, preferido, prev):
    return (
        1 if cand["tema"] != prev else 0,            # variedade (regra forte)
        1 if cand["tema"] == preferido else 0,       # rotação = tema do dia (guia da vez)
        1 if cand.get("fresco") else 0,              # fresh-first (≤30d)
        0 if cand.get("classico") else 1,            # clássico é PISO (só quando não há melhor)
        cand.get("score", 0),                        # qualidade puxa pra frente
    )
```

`classificar_slot` (substituir, ~linha 80):
```python
def classificar_slot(slot):
    """Decide a fonte do preparo das 18h a partir do slot (função pura)."""
    if not slot:
        return ("fallback", None)
    t = slot.get("tipo")
    if t == "pulado":
        return ("pulado", None)
    if t == "reserva" and slot.get("ref_id"):
        return ("reserva", slot["ref_id"])
    if t == "candidato" and slot.get("ref_id"):
        return ("candidato", slot["ref_id"])
    if t == "classico" and slot.get("ref_id"):
        return ("classico", slot["ref_id"])
    if t == "fila" and slot.get("payload"):
        return ("fila", slot["payload"])
    return ("fallback", None)
```

> **Regressão:** o `_rank` antigo tinha `1 if tipo=="reserva" else 0` (reserva > fila). Isso sai. Ajuste os testes existentes de `test_agenda_plan` que dependiam de "reserva vence fila" — agora o critério é `fresco`/`classico`/`score` (adicione esses campos aos candidatos de teste via o helper `_cand`, default fresco=False/classico=False/score=5).

- [ ] **Step 4: Rodar e ver passar**

Run: `cd app && python3 -m unittest tests.test_agenda_plan -v`
Expected: PASS (novos + existentes ajustados)

- [ ] **Step 5: Commit**

```bash
git add app/agenda_plan.py app/tests/test_agenda_plan.py
git commit -m "feat(conteudo): agenda fresh-first + clássico-como-piso + empréstimo entre temas (_rank) e classificar_slot p/ candidato/classico"
```

---

### Task 8: `daily.materializar_agenda` — pool anotado (reserva + candidatos + clássicos)

**Files:**
- Modify: `app/daily.py` — `materializar_agenda` (~linha 90)
- Test: `app/tests/test_agenda_materializar.py` (adicionar)

**Interfaces:**
- Consumes: `db.listar_reserva`, `db.listar_candidatos(status="novo", tipo="varredura")`, `db.listar_classicos(elegiveis=True)`, `db.agenda_ref_ids(tipo)`, `db.marcar_candidato_agendado/pronto`, `db.marcar_reserva_agendado/pronto` (Task 4), `_e_fresco` (Task 1), `agenda_plan.planejar_agenda` (Task 7).
- Produces: agenda com slots `tipo` ∈ `reserva|candidato|classico`, cada um com `ref_id`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# app/tests/test_agenda_materializar.py  (adicionar; segue o padrão de banco temp já usado no arquivo)
class TestPoolPiramide(unittest.TestCase):
    def setUp(self):   # padrão do repo (igual TestMaterializar neste arquivo)
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ.pop("DATABASE_URL", None)
        import importlib
        import config as _cfg; importlib.reload(_cfg)
        import db as _db; importlib.reload(_db)
        import queue_store as _q; importlib.reload(_q)
        import daily as _d; importlib.reload(_d)
        self.db, self.daily = _db, _d
        _db.init()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_candidato_fresco_entra_como_candidato(self):
        self.db.salvar_candidatos([{"tema": "Obesidade", "titulo": "Fresco", "chave": "k1", "score": 6,
                                    "tipo": "varredura", "data": self.daily._hoje_iso()}])
        self.daily.materializar_agenda(datas=["2026-07-27"])   # segunda futura
        slot = self.db.agenda_slot("2026-07-27")
        self.assertEqual(slot["tipo"], "candidato")

    def test_classico_preenche_quando_nao_ha_fresco_nem_reserva(self):
        self.db.salvar_classico({"tema": "Obesidade", "titulo_pt": "STEP", "resumo": "r",
                                 "data": "2021-01-01", "citacoes": 4000})
        self.daily.materializar_agenda(datas=["2026-07-27"])
        self.assertEqual(self.db.agenda_slot("2026-07-27")["tipo"], "classico")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd app && python3 -m unittest tests.test_agenda_materializar.TestPoolPiramide -v`
Expected: FAIL (candidatos/clássicos ainda não entram no pool)

- [ ] **Step 3: Implementar**

Em `materializar_agenda` (~linha 90), na parte de reconciliação + montagem de `cands`. **Reconciliação** — após o bloco atual da reserva (~linha 111-114), acrescentar candidato e clássico:
```python
    ref_ids = db.agenda_ref_ids("reserva")
    for r in db.listar_reserva(status="agendado"):
        if r["id"] not in ref_ids:
            db.marcar_reserva_pronto(r["id"])
    cand_ref_ids = db.agenda_ref_ids("candidato")
    for c in db.listar_candidatos(status="agendado", tipo="varredura"):
        if c["id"] not in cand_ref_ids:
            db.marcar_candidato_pronto(c["id"])
    classico_ref_ids = db.agenda_ref_ids("classico")   # p/ não repetir o mesmo clássico no horizonte
```

**Montagem do pool** — substituir o bloco `cands = [...]` (~linha 141-151) por:
```python
    cands = []
    for r in db.listar_reserva(status="pronto"):
        if r["id"] in ref_ids:
            continue
        cands.append({"tipo": "reserva", "tema": r.get("tema", ""), "titulo": r.get("titulo_pt", ""),
                      "ref_id": r["id"], "payload": None,
                      "fresco": _e_fresco(r.get("data", "")), "classico": False,
                      "score": float(r.get("prioridade", 0) or 0)})
    for c in db.listar_candidatos(status="novo", tipo="varredura"):
        cands.append({"tipo": "candidato", "tema": c.get("tema", ""), "titulo": c.get("titulo", ""),
                      "ref_id": c["id"], "payload": None,
                      "fresco": _e_fresco(c.get("data", "")), "classico": False,
                      "score": float(c.get("score", 0) or 0)})
    for cl in db.listar_classicos(elegiveis=True):
        if cl["id"] in classico_ref_ids:
            continue
        cands.append({"tipo": "classico", "tema": cl.get("tema", ""), "titulo": cl.get("titulo_pt", ""),
                      "ref_id": cl["id"], "payload": None,
                      "fresco": False, "classico": True,
                      "score": float(cl.get("citacoes", 0) or 0)})
```

**Consumo** — no laço `for data, cand in plano.items()` (~linha 155), adicionar os ramos candidato/classico:
```python
    for data, cand in plano.items():
        try:
            if cand["tipo"] == "reserva":
                db.agenda_upsert(data, tipo="reserva", ref_id=cand["ref_id"], payload=None,
                                 tema=cand["tema"], titulo=cand["titulo"], fixado=0)
                db.marcar_reserva_agendado(cand["ref_id"])
            elif cand["tipo"] == "candidato":
                db.agenda_upsert(data, tipo="candidato", ref_id=cand["ref_id"], payload=None,
                                 tema=cand["tema"], titulo=cand["titulo"], fixado=0)
                db.marcar_candidato_agendado(cand["ref_id"])
            elif cand["tipo"] == "classico":
                db.agenda_upsert(data, tipo="classico", ref_id=cand["ref_id"], payload=None,
                                 tema=cand["tema"], titulo=cand["titulo"], fixado=0)
                # clássico NÃO é consumido (reusável); o ref na agenda já evita repetir no horizonte
            else:
                payload = json.dumps(cand["payload"], ensure_ascii=False)
                db.agenda_upsert(data, tipo="fila", ref_id=None, payload=payload,
                                 tema=cand["tema"], titulo=cand["titulo"], fixado=0)
                queue_store.remover(cand["payload"])
            feitos += 1
        except Exception as e:
            print(f"[agenda] falha ao materializar {data} (segue): {e}", flush=True)
```

> **Nota:** reserva agora usa `prioridade` como `score` (artigos do Diego = prioridade>0 continuam furando). Fila fresca do `queue_store` (artigos do Diego via `adicionar_meu_estudo`) segue como `tipo="fila"`, sem `fresco`/`classico` anotados → default False/0 no `_rank` (comportamento seguro).

- [ ] **Step 4: Rodar e ver passar**

Run: `cd app && python3 -m unittest tests.test_agenda_materializar -v`
Expected: PASS (novos + regressão)

- [ ] **Step 5: Commit**

```bash
git add app/daily.py app/tests/test_agenda_materializar.py
git commit -m "feat(conteudo): materializar_agenda monta pool anotado (reserva+candidatos+clássicos) fresh-first + reconciliação"
```

---

### Task 9: `daily` — preparar de candidato (JIT) e de clássico + finalizar

**Files:**
- Modify: `app/daily.py` — `preparar_18h` (~linha 332), novos `_preparar_de_candidato`/`_preparar_de_classico`, `_finalizar_dia` (~linha 421)
- Test: `app/tests/test_preparar_conteudo.py` (criar)

**Interfaces:**
- Consumes: `agenda_plan.classificar_slot` (Task 7), `db.listar_candidatos`/`obter_classico`/`marcar_candidato_*`/`marcar_classico_enviado` (Task 4), `content.gerar_conteudo`.
- Produces: `preparar_18h` prepara a partir de `candidato`/`classico`; `_finalizar_dia` marca candidato `resumido` e clássico `enviado`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# app/tests/test_preparar_conteudo.py  (criar; banco temp + mocks de rede/IA)
import os, sys, unittest, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

class TestPrepararClassico(unittest.TestCase):
    def setUp(self):   # padrão do repo (ver test_agenda_materializar.py)
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ.pop("DATABASE_URL", None)
        import importlib, config as _cfg; importlib.reload(_cfg)
        import db as _db; importlib.reload(_db)
        _db.init()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_preparar_de_classico_usa_resumo_bancado(self):
        import daily, db, deliver
        cid = db.salvar_classico({"tema": "Obesidade", "titulo_pt": "STEP", "resumo": "resumo-bancado",
                                  "data": "2021-01-01", "citacoes": 4000})
        deliver.enviar_curador = lambda *a, **k: None       # silencia WhatsApp
        r = daily._preparar_de_classico(cid)
        self.assertEqual(r["resumo"], "resumo-bancado")     # NÃO regenerou (usa o banco)
        self.assertEqual(r.get("classico_id"), cid)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd app && python3 -m unittest tests.test_preparar_conteudo -v`
Expected: FAIL (`module 'daily' has no attribute '_preparar_de_classico'`)

- [ ] **Step 3: Implementar**

Novos preparadores (após `_preparar_de_artigo`, ~linha 320):
```python
def _preparar_de_candidato(cand_id):
    """Monta o rascunho de amanhã de um CANDIDATO cru (resumo JIT). Mira _preparar_de_artigo."""
    import db
    c = next((x for x in db.listar_candidatos() if x["id"] == cand_id), None)
    if not c:
        return None
    art = {"titulo": c.get("titulo", ""), "tema": c.get("tema", ""), "fonte": c.get("fonte", ""),
           "doi": c.get("doi", ""), "url": c.get("url", ""), "data": c.get("data", ""),
           "resumo": c.get("abstract", "")}
    r = _preparar_de_artigo(art)          # gera conteúdo, cria draft, manda preview + áudio
    if r:
        r["candidato_id"] = cand_id
        draft_store.salvar(r)
    return r


def _preparar_de_classico(classico_id):
    """Monta o rascunho de amanhã de um CLÁSSICO já bancado (usa o resumo pronto, sem regenerar).
    Mira _preparar_da_reserva."""
    import db
    cl = db.obter_classico(classico_id)
    if not cl:
        return None
    art = {"titulo": cl.get("titulo_pt", ""), "tema": cl.get("tema", ""), "fonte": cl.get("fonte", ""),
           "doi": cl.get("doi", ""), "url": cl.get("url", ""), "data": cl.get("data", "")}
    try:
        grafico = json.loads(cl.get("grafico") or "null")
    except Exception:
        grafico = None
    c = {"titulo_pt": cl.get("titulo_pt", ""), "resumo": cl.get("resumo", ""),
         "gancho": cl.get("gancho", ""), "grafico": grafico}
    alvo = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    os.makedirs(config.drafts_dir(), exist_ok=True)
    preview = os.path.join(config.drafts_dir(), f"{alvo}-preview.pdf")
    try:
        pdfmod.gerar_pdf(pdfmod.montar_html(art, c, _tema_meta(art.get("tema", ""))), preview)
    except Exception as e:
        print(f"[preparar] PDF preview (clássico) falhou (segue sem): {e}", flush=True)
        preview = None
    r = draft_store.novo_rascunho(alvo, art, c["resumo"], preview)
    r["gancho"] = c["gancho"]; r["grafico"] = c["grafico"]; r["titulo_pt"] = c["titulo_pt"]
    r["classico_id"] = classico_id
    draft_store.salvar(r)
    link = f"{config.PUBLIC_URL}/revisar/{r['review_token']}"
    extra = "\n🎧 O áudio do estudo chega logo abaixo pra você escutar." if config.audio_ligado() else ""
    deliver.enviar_curador(f"📋 Amanhã (clássico) · {art.get('tema','')}:\n*{c['titulo_pt']}*\n{art.get('fonte','')}\n"
                           f"Assinantes: {len(subscribers.ativos())}\n\n👉 Revisar/editar: {link}\n"
                           f"(se não mexer, envio automático às 08h){extra}")
    enviar_audio_preview(r)
    return r
```

`preparar_18h` (~linha 344) — adicionar os ramos após o de `reserva`:
```python
        if fonte == "reserva":
            r = _preparar_da_reserva(reserva_id=ref)
            if r:
                return r
            print("[preparar] item da reserva sumiu — fallback", flush=True)
        elif fonte == "candidato":
            r = _preparar_de_candidato(ref)
            if r:
                return r
            print("[preparar] candidato sumiu — fallback", flush=True)
        elif fonte == "classico":
            r = _preparar_de_classico(ref)
            if r:
                return r
            print("[preparar] clássico sumiu — fallback", flush=True)
        elif fonte == "fila":
            r = _preparar_de_artigo(json.loads(ref))
            if r:
                return r
```

`_finalizar_dia` (~linha 421) — marcar candidato/clássico (após o bloco `if r.get("reserva_id")`, ~linha 435):
```python
    if r.get("candidato_id"):
        try:
            db.marcar_candidatos([r["candidato_id"]], "resumido")
        except Exception as e:
            print(f"[enviar] marcar candidato falhou: {e}", flush=True)
    if r.get("classico_id"):
        try:
            db.marcar_classico_enviado(r["classico_id"], hoje)
        except Exception as e:
            print(f"[enviar] marcar clássico falhou: {e}", flush=True)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd app && python3 -m unittest tests.test_preparar_conteudo -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/daily.py app/tests/test_preparar_conteudo.py
git commit -m "feat(conteudo): preparar_18h de candidato (JIT) e de clássico (bancado) + finalizar marca ambos"
```

---

## Fase 5 — Automação (cron) + gatilhos

### Task 10: Cron da varredura semanal (domingo de manhã)

**Files:**
- Modify: `app/config.py` (~linha 68), `app/daily.py` (nova `varredura_semanal`), `app/serve.py` — `agendador` (~linha 32)
- Test: `app/tests/test_varredura_semanal.py` (criar)

**Interfaces:**
- Consumes: `curadoria.rodar_varredura` (existente), `db.registrar_envio_slot` (idempotência por chave-semana), `_dias_envio`/`DIAS`.
- Produces: `config.HORA_VARREDURA: int` (default 6); `daily.varredura_semanal(hoje: date|None=None, rodar_fn=None) -> bool` — roda a varredura 1x por semana ISO, só no dia da semana alvo (domingo). `agendador` agenda `(HORA_VARREDURA, "varredura_semanal")`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# app/tests/test_varredura_semanal.py  (criar; banco temp)
import os, sys, unittest, tempfile
from datetime import date
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

class TestVarreduraSemanal(unittest.TestCase):
    def setUp(self):   # padrão do repo (ver test_agenda_materializar.py)
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ.pop("DATABASE_URL", None)
        import importlib, config as _cfg; importlib.reload(_cfg)
        import db as _db; importlib.reload(_db)
        _db.init()
        self.calls = []

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_roda_domingo_uma_vez(self):
        import daily
        domingo = date(2026, 7, 26)     # 2026-07-26 é domingo
        r1 = daily.varredura_semanal(hoje=domingo, rodar_fn=lambda: self.calls.append(1) or 3)
        r2 = daily.varredura_semanal(hoje=domingo, rodar_fn=lambda: self.calls.append(1) or 3)
        self.assertTrue(r1); self.assertFalse(r2)       # idempotente na mesma semana
        self.assertEqual(len(self.calls), 1)

    def test_nao_roda_fora_de_domingo(self):
        import daily
        segunda = date(2026, 7, 27)
        r = daily.varredura_semanal(hoje=segunda, rodar_fn=lambda: self.calls.append(1))
        self.assertFalse(r); self.assertEqual(self.calls, [])
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd app && python3 -m unittest tests.test_varredura_semanal -v`
Expected: FAIL (`module 'daily' has no attribute 'varredura_semanal'`)

- [ ] **Step 3: Implementar**

`config.py` (após `CLASSICO_REUSO_MESES`):
```python
HORA_VARREDURA = int(os.environ.get("DSCURSO_HORA_VARREDURA") or 6)   # domingo de manhã
DIA_VARREDURA = os.environ.get("DSCURSO_DIA_VARREDURA") or "domingo"
```

`daily.py` — nova função (após `rotina_08h`, ~linha 372):
```python
def varredura_semanal(hoje=None, rodar_fn=None):
    """Roda a varredura geral 1x por semana ISO, só no DIA_VARREDURA (domingo de manhã).
    Idempotente via db.registrar_envio_slot(chave-semana, 'varredura'). Retorna True se rodou."""
    from datetime import date
    hoje = hoje or date.today()
    if DIAS[hoje.weekday()] != config.DIA_VARREDURA:
        return False
    import db
    ano, semana, _ = hoje.isocalendar()
    chave = f"{ano}-W{semana:02d}"
    if not db.registrar_envio_slot(chave, "varredura"):   # já rodou esta semana
        return False
    rodar_fn = rodar_fn or (lambda: __import__("curadoria").rodar_varredura())
    try:
        n = rodar_fn()
        print(f"[varredura-semanal] {chave}: {n} novos candidatos", flush=True)
    except Exception as e:
        print(f"[varredura-semanal] erro: {e}", flush=True)
    return True
```

`serve.py` — `agendador` (~linha 39): registrar a tarefa e o horário:
```python
    tarefas = {"rotina08": daily.rotina_08h, "prep18": _prep_e_18h,
               "varredura_semanal": daily.varredura_semanal}
    for s in config.SLOTS:
        if s not in ("08h", "18h"):
            tarefas[f"slot:{s}"] = (lambda sl=s: daily.enviar_slot(sl))
```
e, na montagem de `horarios` (após o `for s in config.SLOTS` que preenche os horários, ~linha 51):
```python
    horarios.append((config.HORA_VARREDURA, "varredura_semanal"))   # self-gate: só domingo, 1x/semana
```

> **Nota:** `varredura_semanal` dispara todo dia em `HORA_VARREDURA`, mas se auto-limita a domingo + 1x/semana. Como domingo não é dia de envio, os slots de envio de domingo já retornam cedo; e o `prep18` de domingo prepara a segunda com os candidatos recém-varridos.

- [ ] **Step 4: Rodar e ver passar**

Run: `cd app && python3 -m unittest tests.test_varredura_semanal -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/config.py app/daily.py app/serve.py app/tests/test_varredura_semanal.py
git commit -m "feat(conteudo): cron da varredura semanal (domingo de manhã, idempotente por semana ISO)"
```

---

### Task 11: Gatilhos da varredura de clássicos (CLI + botão admin)

**Files:**
- Modify: `app/curadoria.py` — `__main__` (~linha 233)
- Modify: `app/serve.py` — rota da Curadoria (`acao`, ~linha 512)
- Test: `app/tests/test_curadoria.py` (adicionar smoke do CLI dispatch, opcional)

**Interfaces:**
- Consumes: `curadoria.rodar_varredura_classicos` (Task 5).
- Produces: `python curadoria.py classicos` roda a varredura de clássicos; `acao="varrer_classicos"` na Curadoria dispara o mesmo.

- [ ] **Step 1: Implementar o CLI**

`curadoria.py` `__main__` (~linha 233):
```python
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "varrer"
    if cmd == "varrer":
        rodar_varredura()
    elif cmd == "classicos":
        rodar_varredura_classicos()
    elif cmd == "gerar":
        gerar_selecionados()
    else:
        print("uso: python curadoria.py [varrer|classicos|gerar]")
```

- [ ] **Step 2: Implementar o gatilho admin**

`serve.py`, na rota da Curadoria, junto do `elif acao == "varrer":` (~linha 513):
```python
            elif acao == "varrer_classicos":
                try:
                    msg = f"Varredura de clássicos: {curadoria.rodar_varredura_classicos()} novos candidatos."
                except Exception as e:
                    print(f"[classicos] varredura erro: {e}", flush=True); msg = "Falha na varredura de clássicos (ver logs)."
```

- [ ] **Step 3: Rodar a suíte inteira (regressão)**

Run: `cd app && python3 -m unittest discover -s tests`
Expected: PASS (toda a suíte)

- [ ] **Step 4: Commit**

```bash
git add app/curadoria.py app/serve.py app/tests/test_curadoria.py
git commit -m "feat(conteudo): gatilhos da varredura de clássicos (CLI 'classicos' + acao admin varrer_classicos)"
```

> **Follow-up (fora deste plano, brainstorm com o Diego):** a **tela de aprovação de clássicos** na Curadoria (separar visualmente candidatos `tipo='classico'` dos `varredura`, botão de scan, seleção → banco). Layout é decisão de página → aplicar [[feedback-nao-supor-landing]]. Até lá, a aprovação de clássicos pode ser feita marcando os candidatos `tipo='classico'` como `selecionado` e rodando `gerar` (que já roteia pro banco — Task 6). A Curadoria diária **não** deve listar `tipo='classico'` (ajuste o `listar_candidatos` da página com `tipo='varredura'` quando essa tela for feita).

---

## Self-Review

**1. Spec coverage** (spec `2026-07-25-maquina-conteudo-design.md`):
- Aprovação implícita (gate 18h) → preservado em todas as tasks (nada bypassa `preparar_18h`/`enviar_slot`). ✓
- Varredura geral semanal domingo AM → Task 10. ✓
- Fresco ≤30d + selo → Tasks 1, 2. ✓
- Fila priorizada sem piso (candidatos auto na agenda) → Tasks 4 (`listar_candidatos`), 8 (pool). ✓
- Fresco fura fila do tema, espera dia do tema → Task 7 (`_rank`). ✓
- Pirâmide fresco→reserva→clássico→empréstimo → Tasks 7 (`_rank`) + 8 (pool) + 9 (preparar). ✓
- Clássicos híbrido (citações → aprova → banco), reusável por ciclo → Tasks 3, 4, 5, 6, 9. ✓
- OpenAlex citações → Task 3. ✓
- Ebook sai de fallback → não religado (o fallback antigo já é "avisa curador"); a pirâmide é a rede. ✓ (nenhuma task adiciona ebook)
- Curadoria manual coexiste → `gerar_selecionados` mantém o caminho reserva; `varrer`/`gerar` do CLI e admin seguem. ✓

**2. Placeholder scan:** o único "…" é o `setUp` de teste que instrui reusar o padrão de banco temporário do arquivo — com nota explícita de como confirmar o env var real (Task 4 Step 4). Sem TBD/TODO de implementação. Toda step de código tem código.

**3. Type consistency:** `_e_fresco(data, ref)` (Task 1) usado igual em Tasks 2/8. `salvar_classico(reg)/obter_classico/listar_classicos/marcar_classico_enviado` consistentes entre Tasks 4/6/9. `listar_candidatos(status,tema,tipo)` idem Tasks 4/8/9. `classificar_slot` retorna `("candidato"|"classico", ref_id)` (Task 7) consumido em `preparar_18h` (Task 9). `_rank` lê `fresco/classico/score` (Task 7) que o pool anota (Task 8). ✓

**Riscos conhecidos p/ o executor:**
- Task 7 muda o critério "reserva>fila" do `_rank` — **ajustar os testes existentes** de `test_agenda_plan.py` que assumiam isso (nota na task).
- Task 8 reescreve trechos do `materializar_agenda`; rodar `test_agenda_materializar` inteiro (regressão) além dos casos novos.
