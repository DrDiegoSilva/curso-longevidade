# Tags de estudos (Fase 1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Etiquetar cada estudo com tags livres geradas pela IA (moléculas/intervenções/tópico), gravar nas 3 tabelas de estudo, carregar candidato→reserva/clássico, com backfill do estoque antigo e uma busca `buscar_por_tag` — pré-requisito das Séries.

**Architecture:** As tags saem da triagem Haiku que já roda (`triage.triar`) pros estudos novos; uma função só-tags (`triage.taggear`) alimenta o backfill (não re-classifica ENTRA/LIXO). Storage em coluna JSON nas 3 tabelas. Busca por substring.

**Tech Stack:** Python 3 stdlib (`unittest`, `json`), sqlite via `db.py`, Haiku via `resumo_diario.claude`. Sem dependências novas.

## Global Constraints

- **Worktree:** trabalhar em `/Users/diegosilva/dev/curso-longevidade/.claude/worktrees/tags-series`, branch `worktree-tags-series` (base b5652b2). Rodar testes de `app/`: `python3 -m unittest discover -s tests`.
- **Repo multi-agente:** stagear só os arquivos do task; nunca `git add -A`.
- Tags: **minúsculas, PT, lista de string, deduplicada**; nome comum da molécula.
- **Contrato:** as funções `db.salvar_*` recebem `tags` como **lista Python**; guardam `json.dumps`. Quem lê do banco recebe **string JSON** e faz `json.loads`.
- **Nunca derrubar a triagem/varredura** por causa de tags: campo ausente/inválido → `[]`.
- **Backfill idempotente:** só processa estudos com tags vazia (`[]`/NULL).
- Sem push/deploy neste plano.

## File Structure

- `app/triage.py` — **modificar**: `_norm_tags`, tags no `_prompt`/`_parse`/`triar`; + `_prompt_tags`/`taggear` (só-tags p/ backfill).
- `app/db.py` — **modificar**: coluna `tags` nas 3 `CREATE TABLE` + `_migrar_colunas`; `salvar_candidatos`/`salvar_reserva`/`salvar_classico` gravam tags; + `buscar_por_tag`, `atualizar_tags`.
- `app/curadoria.py` — **modificar**: `gerar_selecionados` carrega tags candidato→reserva/clássico; `adicionar_meu_estudo` grava tags; + `backfill_tags`.
- `app/serve.py` — **modificar**: ação admin `backfill_tags` na `/curadoria`.
- `app/tests/test_tags.py` — **criar**.

---

### Task 1: triage — tags na triagem + `taggear` (só-tags)

**Files:**
- Modify: `app/triage.py`
- Test: `app/tests/test_tags.py`

**Interfaces:**
- Produces: `_norm_tags(tags) -> list[str]`; `triar(...)` passa a devolver `a["tags"]: list[str]` em cada artigo ENTRA; `taggear(artigos, llm=None) -> dict[int, list[str]]` (índice→tags, sem filtrar ENTRA/LIXO).

- [ ] **Step 1: Write the failing test** — criar `app/tests/test_tags.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_tags.TestTriageTags -v`
Expected: FAIL (`_norm_tags`/`taggear` não existem; `_parse` sem `tags`).

- [ ] **Step 3: Write minimal implementation** — em `app/triage.py`:

Adicionar `_norm_tags` (acima de `_prompt`):

```python
def _norm_tags(tags):
    """Lista de string minúscula, deduplicada; qualquer coisa fora disso -> []."""
    if not isinstance(tags, list):
        return []
    out, seen = [], set()
    for t in tags:
        if isinstance(t, str):
            t = t.strip().lower()
            if t and t not in seen:
                seen.add(t)
                out.append(t)
    return out
```

Em `_prompt`, trocar a última linha (o `Responda SÓ JSON:`) por:

```python
        "Dê um score de importância clínica de 0 a 10 para os que ENTRAM. "
        "Para cada ENTRA, em 'tags' liste 3-6 palavras-chave (moléculas/intervenções + o tópico central), "
        "minúsculas, em português, usando o NOME COMUM da molécula (ex.: 'retatrutida', não 'ly3437943'). "
        'Responda SÓ JSON: [{"i":0,"classe":"ENTRA","score":8,"tags":["retatrutida","glp1","perda de peso"]},'
        '{"i":1,"classe":"LIXO","score":0}]')
```

Em `_parse`, dentro do `if c.get("classe") == "ENTRA"...`, depois do bloco do `score`, adicionar:

```python
            a["tags"] = _norm_tags(c.get("tags"))
```

Adicionar, ao final do arquivo, o caminho só-tags:

```python
def _prompt_tags(artigos):
    lista = "\n".join(
        f"[{i}] {a.get('titulo','')} | {(a.get('resumo','') or a.get('abstract','') or '')[:500]}"
        for i, a in enumerate(artigos))
    return (
        "Para CADA estudo abaixo, liste 3-6 palavras-chave (moléculas/intervenções + o tópico central), "
        "minúsculas, em português, usando o nome comum da molécula.\n"
        f"{lista}\n\n"
        'Responda SÓ JSON: [{"i":0,"tags":["retatrutida","glp1"]},{"i":1,"tags":["menopausa"]}]')


def taggear(artigos, llm=None):
    """Só tags (sem ENTRA/LIXO) — p/ backfill do estoque. Retorna {i: [tags]}."""
    if not artigos:
        return {}
    if llm is None:
        from resumo_diario import claude, HAIKU
        llm = lambda p: claude(HAIKU, p, system=SYS, max_tokens=700)
    import jsonx
    bruto = jsonx.primeiro_array(llm(_prompt_tags(artigos)))
    try:
        cls = json.loads(bruto) if bruto else []
    except Exception:
        cls = []
    return {c["i"]: _norm_tags(c.get("tags")) for c in cls if isinstance(c.get("i"), int)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_tags.TestTriageTags -v`
Expected: PASS (6 testes).

- [ ] **Step 5: Commit**

```bash
git add app/triage.py app/tests/test_tags.py
git commit -m "feat(tags): triagem devolve tags + taggear (só-tags p/ backfill)"
```

---

### Task 2: db — coluna `tags`, salvar, `buscar_por_tag`, `atualizar_tags`

**Files:**
- Modify: `app/db.py`
- Test: `app/tests/test_tags.py` (nova classe)

**Interfaces:**
- Produces: `salvar_candidatos`/`salvar_reserva`/`salvar_classico` gravam `tags` (recebem lista); `buscar_por_tag(termo) -> list[{tipo,id,titulo,tema,tags}]`; `atualizar_tags(tipo, id_, tags)`.
- Consumes: contrato — recebem `tags` como lista Python.

- [ ] **Step 1: Write the failing test** — adicionar em `app/tests/test_tags.py`:

```python
class TestDbTags(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ.pop("DATABASE_URL", None)
        import importlib, db as _db
        importlib.reload(_db)
        self.db = _db
        self.db.init()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_reserva_salva_e_le_tags(self):
        import json
        rid = self.db.salvar_reserva({"tema": "Obesidade", "titulo_pt": "Reta X",
                                      "resumo": "r", "tags": ["retatrutida", "glp1"]})
        self.assertEqual(json.loads(self.db.obter_reserva(rid)["tags"]), ["retatrutida", "glp1"])

    def test_default_vazio(self):
        import json
        rid = self.db.salvar_reserva({"tema": "T", "titulo_pt": "Sem tags"})
        self.assertEqual(json.loads(self.db.obter_reserva(rid)["tags"]), [])

    def test_buscar_por_tag_cruza_e_substring(self):
        self.db.salvar_reserva({"tema": "Obesidade", "titulo_pt": "R1", "tags": ["retatrutida"]})
        self.db.salvar_classico({"tema": "Obesidade", "titulo_pt": "C1", "tags": ["retatrutida", "glp1"]})
        self.db.salvar_candidatos([{"tema": "Obesidade", "titulo": "K1", "chave": "k1",
                                    "tags": ["semaglutida"]}])
        achados = self.db.buscar_por_tag("RETA")             # substring + case-insensitive
        self.assertEqual(sorted(a["titulo"] for a in achados), ["C1", "R1"])
        self.assertEqual(self.db.buscar_por_tag("semaglutida")[0]["tipo"], "candidato")
        self.assertEqual(self.db.buscar_por_tag(""), [])     # vazio -> []

    def test_atualizar_tags(self):
        import json
        rid = self.db.salvar_reserva({"tema": "T", "titulo_pt": "X"})
        self.db.atualizar_tags("reserva", rid, ["nova"])
        self.assertEqual(json.loads(self.db.obter_reserva(rid)["tags"]), ["nova"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_tags.TestDbTags -v`
Expected: FAIL (coluna `tags` inexistente / `buscar_por_tag`/`atualizar_tags` não existem).

- [ ] **Step 3: Write minimal implementation** — em `app/db.py`:

**(a)** Nas 3 `CREATE TABLE`, adicionar a coluna `tags` (antes do `)` de cada):
- `curadoria_candidatos`: após `status TEXT DEFAULT 'novo', criado_em TEXT` → `, tags TEXT DEFAULT '[]'`.
- `classicos`: após `ultimo_envio TEXT, criado_em TEXT` → `, tags TEXT DEFAULT '[]'`.
- `reserva_resumos`: após `score REAL DEFAULT 0` → `, tags TEXT DEFAULT '[]'`.

**(b)** Em `_migrar_colunas`, adicionar:

```python
        _add_coluna(c, "curadoria_candidatos", "tags", "TEXT DEFAULT '[]'")
        _add_coluna(c, "reserva_resumos", "tags", "TEXT DEFAULT '[]'")
        _add_coluna(c, "classicos", "tags", "TEXT DEFAULT '[]'")
```

**(c)** `salvar_candidatos` — adicionar `import json` (junto de `secrets`/`datetime`); incluir `tags` na coluna+valor (após `tipo`):

```python
                """INSERT INTO curadoria_candidatos
                   (id,tema,titulo,fonte,data,doi,url,abstract,pergunta,score,chave,citacoes,tipo,tags,status,criado_em)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'novo', ?)
                   ON CONFLICT (chave) DO NOTHING""",
                (secrets.token_hex(8), x.get("tema", ""), x.get("titulo", ""), x.get("fonte", ""),
                 x.get("data", ""), x.get("doi", ""), x.get("url", ""), x.get("abstract", ""),
                 x.get("pergunta", ""), float(x.get("score", 0) or 0), x.get("chave"),
                 int(x.get("citacoes", 0) or 0), x.get("tipo", "varredura"),
                 json.dumps(x.get("tags") or []), datetime.now().isoformat()))
```

**(d)** `salvar_reserva` — `import json`; incluir `tags` (após `score`):

```python
            """INSERT INTO reserva_resumos
               (id,candidato_id,tema,titulo_pt,resumo,gancho,grafico,doi,fonte,url,data,status,prioridade,origem,criado_em,score,tags)
               VALUES (?,?,?,?,?,?,?,?,?,?,?, 'pronto', ?,?,?,?,?)""",
            (rid, reg.get("candidato_id"), reg.get("tema", ""), reg.get("titulo_pt", ""),
             reg.get("resumo", ""), reg.get("gancho", ""), reg.get("grafico", ""), reg.get("doi", ""),
             reg.get("fonte", ""), reg.get("url", ""), reg.get("data", ""),
             int(reg.get("prioridade", 0) or 0), reg.get("origem", "varredura"), datetime.now().isoformat(),
             float(reg.get("score", 0) or 0), json.dumps(reg.get("tags") or [])))
```

**(e)** `salvar_classico` — `import json`; incluir `tags` (após `criado_em`):

```python
            """INSERT INTO classicos
               (id,tema,titulo_pt,resumo,gancho,grafico,doi,fonte,url,data,citacoes,criado_em,tags)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (cid, reg.get("tema", ""), reg.get("titulo_pt", ""), reg.get("resumo", ""),
             reg.get("gancho", ""), reg.get("grafico", ""), reg.get("doi", ""), reg.get("fonte", ""),
             reg.get("url", ""), reg.get("data", ""), int(reg.get("citacoes", 0) or 0),
             datetime.now().isoformat(), json.dumps(reg.get("tags") or [])))
```

**(f)** Adicionar, perto das outras funções de estudo:

```python
_TAG_TAB = {"candidato": "curadoria_candidatos", "reserva": "reserva_resumos", "classico": "classicos"}


def atualizar_tags(tipo, id_, tags):
    import json
    tab = _TAG_TAB.get(tipo)
    if not tab:
        return
    with _conn() as c:
        c.execute(f"UPDATE {tab} SET tags=? WHERE id=?", (json.dumps(tags or []), id_))


def buscar_por_tag(termo):
    """Estudos (reserva+candidatos+clássicos) cuja 'tags' contém `termo` (substring, sem case).
    Retorna [{tipo,id,titulo,tema,tags}]. Termo vazio -> []."""
    import json
    termo = (termo or "").strip().lower()
    if not termo:
        return []
    like = f"%{termo}%"
    out = []
    with _conn() as c:
        for tipo, tab, tcol in (("reserva", "reserva_resumos", "titulo_pt"),
                                ("candidato", "curadoria_candidatos", "titulo"),
                                ("classico", "classicos", "titulo_pt")):
            for r in c.execute(f"SELECT id, {tcol} AS titulo, tema, tags FROM {tab} "
                               f"WHERE lower(tags) LIKE ?", (like,)).fetchall():
                d = dict(r)
                try:
                    tags = json.loads(d.get("tags") or "[]")
                except Exception:
                    tags = []
                out.append({"tipo": tipo, "id": d["id"], "titulo": d.get("titulo") or "",
                            "tema": d.get("tema") or "", "tags": tags})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_tags.TestDbTags -v`
Expected: PASS (4 testes).

- [ ] **Step 5: Commit**

```bash
git add app/db.py app/tests/test_tags.py
git commit -m "feat(tags): coluna tags nas 3 tabelas + salvar + buscar_por_tag + atualizar_tags"
```

---

### Task 3: curadoria — carregar tags + `backfill_tags`

**Files:**
- Modify: `app/curadoria.py`
- Test: `app/tests/test_tags.py` (nova classe)

**Interfaces:**
- Consumes: `db.salvar_reserva`/`salvar_classico` (tags lista), `db.listar_*`, `db.atualizar_tags`, `triage.taggear`.
- Produces: `gerar_selecionados` carrega tags; `adicionar_meu_estudo` grava tags; `backfill_tags(db_mod=None, taggear_fn=None, lote=20) -> int`.

- [ ] **Step 1: Write the failing test** — adicionar em `app/tests/test_tags.py`:

```python
class TestCuradoriaTags(unittest.TestCase):
    def test_gerar_selecionados_carrega_tags(self):
        import curadoria
        from unittest import mock
        cand = {"id": "c1", "tema": "Obesidade", "titulo": "T", "tipo": "varredura",
                "tags": '["retatrutida","glp1"]'}
        salvos = {}
        fake_db = mock.Mock()
        fake_db.listar_candidatos.return_value = [cand]
        fake_db.salvar_reserva.side_effect = lambda reg: salvos.update(reg) or "rid"
        gerar = lambda c: {"titulo_pt": "Tpt", "resumo": "r", "gancho": "", "grafico": None}
        curadoria.gerar_selecionados(db_mod=fake_db, gerar_resumo_fn=gerar)
        self.assertEqual(salvos.get("tags"), ["retatrutida", "glp1"])   # string do banco -> lista

    def test_backfill_so_sem_tags_e_idempotente(self):
        import curadoria
        from unittest import mock
        fake_db = mock.Mock()
        fake_db.listar_candidatos.return_value = [
            {"id": "a", "tema": "Obesidade", "titulo": "A", "abstract": "x", "tags": "[]"},
            {"id": "b", "tema": "Obesidade", "titulo": "B", "abstract": "y", "tags": '["ja"]'}]
        fake_db.listar_reserva.return_value = []
        fake_db.listar_classicos.return_value = []
        taggear = lambda arts: {i: ["nova"] for i in range(len(arts))}
        n = curadoria.backfill_tags(db_mod=fake_db, taggear_fn=taggear)
        self.assertEqual(n, 1)                                  # só o 'a' (sem tags)
        fake_db.atualizar_tags.assert_called_once_with("candidato", "a", ["nova"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_tags.TestCuradoriaTags -v`
Expected: FAIL (tags não carregadas; `backfill_tags` não existe).

- [ ] **Step 3: Write minimal implementation** — em `app/curadoria.py`:

**(a)** Em `gerar_selecionados`, no dict `reg`, adicionar a linha de tags (carrega a string do candidato como lista):

```python
            reg = {"tema": c["tema"], "titulo_pt": r["titulo_pt"], "resumo": r["resumo"],
                   "gancho": r.get("gancho", ""),
                   "grafico": json.dumps(r["grafico"], ensure_ascii=False) if r.get("grafico") else "",
                   "doi": c.get("doi", ""), "fonte": c.get("fonte", ""), "url": c.get("url", ""),
                   "data": c.get("data", ""), "score": c.get("score", 0),
                   "tags": json.loads(c.get("tags") or "[]")}
```

**(b)** Em `adicionar_meu_estudo`, após obter `score` da triagem, pegar as tags e passar no `salvar_reserva`:

```python
    score = triados[0].get("score", 0) if triados else 7   # LIXO/no-return -> default 7 (Diego escolheu)
    tags = triados[0].get("tags", []) if triados else []
```

e no `db.salvar_reserva({...})` adicionar `"tags": tags` ao dict.

**(c)** Adicionar a função de backfill (ao final do módulo, antes do `if __name__`):

```python
def backfill_tags(db_mod=None, taggear_fn=None, lote=20):
    """Etiqueta estudos das 3 tabelas SEM tags ([]/NULL). Idempotente. Retorna quantos.
    Usa taggear (só-tags, não re-classifica). taggear_fn injetável p/ teste."""
    if db_mod is None:
        import db as db_mod
    if taggear_fn is None:
        import triage
        taggear_fn = triage.taggear
    db_mod.init()
    pend = []
    for tipo, itens, tk in (
            ("candidato", db_mod.listar_candidatos(), "titulo"),
            ("reserva", db_mod.listar_reserva(), "titulo_pt"),
            ("classico", db_mod.listar_classicos(elegiveis=False), "titulo_pt")):   # elegiveis=False = TODOS os bancados
        for e in itens:
            if (e.get("tags") or "[]") in ("[]", "", None):
                pend.append((tipo, e["id"],
                             {"titulo": e.get(tk, ""), "resumo": e.get("resumo") or e.get("abstract", "")}))
    feitos = 0
    for i in range(0, len(pend), lote):
        chunk = pend[i:i + lote]
        tags_por_i = taggear_fn([p[2] for p in chunk])
        for j, (tipo, eid, _) in enumerate(chunk):
            db_mod.atualizar_tags(tipo, eid, tags_por_i.get(j, []))
            feitos += 1
    return feitos
```

*(`db.listar_classicos(tema=None, elegiveis=True)` — `elegiveis=False` pega TODOS os bancados, que é o que o backfill quer. O mock do teste (`listar_classicos.return_value`) ignora o arg.)*

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_tags.TestCuradoriaTags -v`
Expected: PASS (2 testes).

- [ ] **Step 5: Commit**

```bash
git add app/curadoria.py app/tests/test_tags.py
git commit -m "feat(tags): gerar_selecionados/adicionar_meu_estudo carregam tags + backfill_tags"
```

---

### Task 4: serve — ação admin backfill + regressão

**Files:**
- Modify: `app/serve.py`

**Interfaces:**
- Consumes: `curadoria.backfill_tags`.

- [ ] **Step 1: Implementar o wiring** — em `app/serve.py`, no POST `/curadoria` (junto de `varrer`/`varrer_classicos`), adicionar um ramo:

```python
            elif acao == "backfill_tags":
                try:
                    import curadoria
                    msg = f"Tags: {curadoria.backfill_tags()} estudo(s) etiquetado(s)."
                except Exception as e:
                    print(f"[tags] backfill erro: {e}", flush=True)
                    msg = "Falha no backfill de tags (ver logs)."
```

E um botão em `site_web._curadoria_ferramentas` (Ferramentas), no mesmo padrão do `varrer_classicos`:
`🏷️ Etiquetar estudos (tags)` → form POST `/curadoria` com `acao=backfill_tags` + token.

- [ ] **Step 2: Rodar a suíte inteira (regressão)**

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -5`
Expected: `OK` — baseline 729 + os novos testes (12), todos verdes. Score/pergunta/varredura intactos.

- [ ] **Step 3: Smoke manual (documentar, não bloqueia)**

1. Estudo novo (upload ou varredura) entra com tags.
2. `/curadoria` → Ferramentas → **🏷️ Etiquetar estudos** → mostra "N etiquetados"; rodar de novo → 0 (idempotente).
3. (Fase 2 usará `buscar_por_tag`.)

- [ ] **Step 4: Commit**

```bash
git add app/serve.py app/site_web.py
git commit -m "feat(tags): ação admin de backfill de tags na /curadoria"
```

---

## Notas de execução

- **Deploy junto com a Fase 2** (ou sozinho, se quiser as tags/backfill no ar antes) — decidir com o Diego.
- A **Fase 2 (Séries)** ganha o próprio plano depois desta.
