# Séries de estudos (Fase 2 — "furo") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deixar o Diego montar séries temáticas ordenadas (ex.: "Série GLP1", 5 estudos) que ocupam N dias úteis seguidos da agenda (o "furo"), montadas do estoque (busca por tag — Fase 1) + upload, ativadas escolhendo a data de início, cada dia passando pela revisão das 18h.

**Architecture:** Duas tabelas novas (`series`/`serie_itens`) + um módulo `series.py` de orquestração. Ativar uma série apenas **grava os slots** dos próximos N dias úteis livres (reusando o mecanismo do Item 23: `agenda_upsert` + `marcar_*_agendado`); o resto do pipeline (preview 18h → gate → envio 08h) já funciona sem mudança. A série se conclui sozinha (por data) quando o último dia passa, liberando ativar outra.

**Tech Stack:** Python 3 stdlib (`unittest`, `secrets`, `datetime`), sqlite via `db.py`, reuso de `agenda_plan`, `daily`, `curadoria`, `draft_store`. Sem dependências novas.

## Global Constraints

- **Worktree:** trabalhar em `/Users/diegosilva/dev/curso-longevidade/.claude/worktrees/tags-series`, branch `worktree-tags-series`. Rodar testes de `app/`: `cd app && python3 -m unittest discover -s tests`. **Baseline atual = 745 testes verdes** (Fase 1 já mesclada nesta branch, HEAD `9cf6acd`).
- **Repo multi-agente:** stagear só os arquivos de cada task; **nunca** `git add -A`.
- **DEPENDE da Fase 1 (Tags):** usa `db.buscar_por_tag(termo)` → `[{tipo,id,titulo,tema,tags}]`.
- **Uma série ATIVA por vez.** `ativar_serie` recusa se já houver série `status='ativa'` (depois de `reconciliar`).
- **Respeita fixado/pulado:** não sobrescreve dia `fixado`; pula dia `tipo='pulado'`; usa o próximo dia útil livre.
- **Gate 18h intacto:** a série nunca envia sem revisão. A série só **grava slots**; `daily.preparar_18h` monta o rascunho.
- **Fail-safe:** ativação em `try/except` por dia; consumo (`marcar_*_agendado`) **só após** gravar o slot (evita órfão, igual Item 23); falha parcial → avisa, não fica silenciosa.
- **Admin-gated:** `/series` usa `config.ADMIN_TOKEN` como as outras telas admin (mesmo check `q.get("token")==config.ADMIN_TOKEN` no GET, `g("token")==config.ADMIN_TOKEN` no POST).
- **Desvios conscientes da spec (refinamentos deste plano):**
  - `serie_itens` ganha `titulo` e `tema` (cache de exibição + do slot) — evita um `obter_candidato` inexistente e refetch por render. Não duplica o estudo (só o rótulo).
  - `serie_itens` ganha `data` (o dia atribuído na ativação; `''` em rascunho). A **conclusão é por DATA**: `reconciliar` fecha a série quando `max(item.data) < hoje` — sem fiar no pipeline de envio. `enviado` fica no schema **reservado** (não usado no MVP).
- Sem push/deploy neste plano.

## File Structure

- `app/db.py` — **modificar**: 2 `CREATE TABLE` novas em `init()` + CRUD de séries (`criar_serie`, `listar_series`, `obter_serie`, `adicionar_serie_item`, `remover_serie_item`, `reordenar_serie_item`, `atualizar_serie`, `set_serie_item_data`).
- `app/series.py` — **criar**: `contexto_pagina`, `_dias_livres`, `_liberar_dia`, `_eh_dia_util`, `reconciliar`, `ativar_serie`, `dia_minimo_inicio`.
- `app/site_web.py` — **modificar**: `pagina_series` (o montador) + link `/series` no `_admin_nav`.
- `app/serve.py` — **modificar**: GET `/series` + POST `/series` (multipart upload + ações urlencoded).
- `app/tests/test_series.py` — **criar**.

---

### Task 1: db — tabelas `series`/`serie_itens` + CRUD

**Files:**
- Modify: `app/db.py` (bloco `c.executescript` em `init()` ~linha 90; CRUD perto das outras funções de estoque)
- Test: `app/tests/test_series.py` (criar)

**Interfaces:**
- Produces:
  - `criar_serie(nome) -> str` (id)
  - `listar_series() -> list[dict]` (todas, `criado_em DESC`)
  - `obter_serie(serie_id) -> {"serie": dict, "itens": list[dict]}` | `None` (itens `ORDER BY ordem`)
  - `adicionar_serie_item(serie_id, ref_tipo, ref_id, titulo="", tema="") -> str` (id; `ordem = max+1`)
  - `remover_serie_item(item_id) -> None`
  - `reordenar_serie_item(item_id, direcao) -> None` (`direcao` ∈ {"cima","baixo"}; troca `ordem` com o vizinho)
  - `atualizar_serie(serie_id, **campos) -> None` (whitelist: nome/status/data_inicio/ativada_em)
  - `set_serie_item_data(item_id, data) -> None`

- [ ] **Step 1: Write the failing test** — criar `app/tests/test_series.py`:

```python
"""Fase 2 — séries de estudos (item 8)."""
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _reload_db(tmp):
    os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(tmp, "t.db")
    os.environ.pop("DATABASE_URL", None)
    import importlib, db as _db
    importlib.reload(_db)
    _db.init()
    return _db


class TestDbSeries(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = _reload_db(self.tmp)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_criar_listar_obter(self):
        sid = self.db.criar_serie("Série GLP1")
        self.assertTrue(sid)
        todas = self.db.listar_series()
        self.assertEqual(len(todas), 1)
        self.assertEqual(todas[0]["nome"], "Série GLP1")
        self.assertEqual(todas[0]["status"], "rascunho")
        det = self.db.obter_serie(sid)
        self.assertEqual(det["serie"]["id"], sid)
        self.assertEqual(det["itens"], [])
        self.assertIsNone(self.db.obter_serie("nao-existe"))

    def test_adicionar_itens_ordena(self):
        sid = self.db.criar_serie("S")
        a = self.db.adicionar_serie_item(sid, "reserva", "r1", titulo="A", tema="Obesidade")
        b = self.db.adicionar_serie_item(sid, "candidato", "c1", titulo="B", tema="Obesidade")
        itens = self.db.obter_serie(sid)["itens"]
        self.assertEqual([i["ordem"] for i in itens], [0, 1])
        self.assertEqual([i["id"] for i in itens], [a, b])
        self.assertEqual(itens[0]["ref_tipo"], "reserva")
        self.assertEqual(itens[0]["titulo"], "A")
        self.assertEqual(itens[0]["data"], "")

    def test_reordenar_troca_vizinho(self):
        sid = self.db.criar_serie("S")
        a = self.db.adicionar_serie_item(sid, "reserva", "r1", titulo="A")
        b = self.db.adicionar_serie_item(sid, "reserva", "r2", titulo="B")
        self.db.reordenar_serie_item(b, "cima")
        ordem = [i["id"] for i in self.db.obter_serie(sid)["itens"]]
        self.assertEqual(ordem, [b, a])
        self.db.reordenar_serie_item(b, "cima")   # já é o primeiro -> no-op
        self.assertEqual([i["id"] for i in self.db.obter_serie(sid)["itens"]], [b, a])

    def test_remover_item(self):
        sid = self.db.criar_serie("S")
        a = self.db.adicionar_serie_item(sid, "reserva", "r1")
        self.db.adicionar_serie_item(sid, "reserva", "r2")
        self.db.remover_serie_item(a)
        itens = self.db.obter_serie(sid)["itens"]
        self.assertEqual([i["ref_id"] for i in itens], ["r2"])

    def test_atualizar_serie_e_item_data(self):
        sid = self.db.criar_serie("S")
        iid = self.db.adicionar_serie_item(sid, "reserva", "r1")
        self.db.atualizar_serie(sid, status="ativa", data_inicio="2026-08-10")
        s = self.db.obter_serie(sid)["serie"]
        self.assertEqual(s["status"], "ativa")
        self.assertEqual(s["data_inicio"], "2026-08-10")
        self.db.set_serie_item_data(iid, "2026-08-10")
        self.assertEqual(self.db.obter_serie(sid)["itens"][0]["data"], "2026-08-10")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_series.TestDbSeries -v`
Expected: FAIL (`criar_serie`/`obter_serie`/etc. não existem; tabelas ausentes).

- [ ] **Step 3: Write minimal implementation** — em `app/db.py`:

**(a)** No bloco `c.executescript("""...""")` dentro de `init()`, adicionar as 2 tabelas (logo após a `CREATE TABLE IF NOT EXISTS agenda (...)`, antes do fim do script):

```sql
            CREATE TABLE IF NOT EXISTS series (
                id TEXT PRIMARY KEY,
                nome TEXT,
                status TEXT DEFAULT 'rascunho',
                data_inicio TEXT DEFAULT '',
                criado_em TEXT,
                ativada_em TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS serie_itens (
                id TEXT PRIMARY KEY,
                serie_id TEXT,
                ordem INTEGER DEFAULT 0,
                ref_tipo TEXT,
                ref_id TEXT,
                titulo TEXT DEFAULT '',
                tema TEXT DEFAULT '',
                data TEXT DEFAULT '',
                enviado INTEGER DEFAULT 0
            );
```

**(b)** Adicionar o CRUD (perto das outras funções de estoque; `json` e `datetime` já estão no módulo, `secrets` é usado por `salvar_candidatos` — importe local onde faltar):

```python
# ── Séries de estudos (item 8, Fase 2) ──
def criar_serie(nome):
    import secrets
    sid = secrets.token_hex(8)
    with _conn() as c:
        c.execute(
            "INSERT INTO series (id,nome,status,data_inicio,criado_em,ativada_em) "
            "VALUES (?,?, 'rascunho', '', ?, '')",
            (sid, nome or "", datetime.now().isoformat()))
    return sid


def listar_series():
    with _conn() as c:
        rows = c.execute("SELECT * FROM series ORDER BY criado_em DESC").fetchall()
    return [dict(r) for r in rows]


def obter_serie(serie_id):
    with _conn() as c:
        s = c.execute("SELECT * FROM series WHERE id=?", (serie_id,)).fetchone()
        if not s:
            return None
        itens = c.execute("SELECT * FROM serie_itens WHERE serie_id=? ORDER BY ordem",
                          (serie_id,)).fetchall()
    return {"serie": dict(s), "itens": [dict(i) for i in itens]}


def adicionar_serie_item(serie_id, ref_tipo, ref_id, titulo="", tema=""):
    import secrets
    iid = secrets.token_hex(8)
    with _conn() as c:
        r = c.execute("SELECT COALESCE(MAX(ordem), -1) AS m FROM serie_itens WHERE serie_id=?",
                      (serie_id,)).fetchone()
        ordem = int(dict(r)["m"]) + 1
        c.execute(
            "INSERT INTO serie_itens (id,serie_id,ordem,ref_tipo,ref_id,titulo,tema,data,enviado) "
            "VALUES (?,?,?,?,?,?,?, '', 0)",
            (iid, serie_id, ordem, ref_tipo, ref_id, titulo or "", tema or ""))
    return iid


def remover_serie_item(item_id):
    with _conn() as c:
        c.execute("DELETE FROM serie_itens WHERE id=?", (item_id,))


def reordenar_serie_item(item_id, direcao):
    """Troca a 'ordem' do item com o vizinho ('cima' = ordem menor, 'baixo' = maior)."""
    with _conn() as c:
        it = c.execute("SELECT * FROM serie_itens WHERE id=?", (item_id,)).fetchone()
        if not it:
            return
        it = dict(it)
        if direcao == "cima":
            viz = c.execute("SELECT * FROM serie_itens WHERE serie_id=? AND ordem<? "
                            "ORDER BY ordem DESC LIMIT 1", (it["serie_id"], it["ordem"])).fetchone()
        else:
            viz = c.execute("SELECT * FROM serie_itens WHERE serie_id=? AND ordem>? "
                            "ORDER BY ordem ASC LIMIT 1", (it["serie_id"], it["ordem"])).fetchone()
        if not viz:
            return
        viz = dict(viz)
        c.execute("UPDATE serie_itens SET ordem=? WHERE id=?", (viz["ordem"], it["id"]))
        c.execute("UPDATE serie_itens SET ordem=? WHERE id=?", (it["ordem"], viz["id"]))


def atualizar_serie(serie_id, **campos):
    permitidos = {"nome", "status", "data_inicio", "ativada_em"}
    sets = {k: v for k, v in campos.items() if k in permitidos}
    if not sets:
        return
    cols = ", ".join(f"{k}=?" for k in sets)
    with _conn() as c:
        c.execute(f"UPDATE series SET {cols} WHERE id=?", (*sets.values(), serie_id))


def set_serie_item_data(item_id, data):
    with _conn() as c:
        c.execute("UPDATE serie_itens SET data=? WHERE id=?", (data or "", item_id))
```

*(Confirme que `datetime` está importado no topo de `db.py` — `salvar_reserva` já usa `datetime.now()`. `_conn()` faz commit no fim do `with`.)*

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_series.TestDbSeries -v`
Expected: PASS (5 testes).

- [ ] **Step 5: Commit**

```bash
git add app/db.py app/tests/test_series.py
git commit -m "feat(series): tabelas series/serie_itens + CRUD (criar/listar/obter/add/remover/reordenar/atualizar)"
```

---

### Task 2: series.py — `ativar_serie` + `reconciliar` + `contexto_pagina` + helpers

**Files:**
- Create: `app/series.py`
- Test: `app/tests/test_series.py` (nova classe)

**Interfaces:**
- Consumes (do db, Task 1 + existentes): `listar_series`, `obter_serie`, `atualizar_serie`, `set_serie_item_data`, `buscar_por_tag`, `agenda_slot`, `agenda_upsert`, `marcar_reserva_agendado`, `marcar_candidato_agendado`, `marcar_reserva_pronto`, `marcar_candidato_pronto`, `init`. De `agenda_plan`: `DIAS`. De `daily`: `_dias_envio`. De `draft_store`: `carregar`.
- Produces:
  - `contexto_pagina(db_mod=None, serie_aberta_id=None, termo="") -> {"series","aberta","resultados"}`
  - `reconciliar(db_mod=None, hoje=None) -> list[str]` (ids concluídos)
  - `ativar_serie(serie_id, data_inicio, dia_min=None, db_mod=None, dias_envio=None) -> (bool, str)`
  - `dia_minimo_inicio(db_mod=None, hoje=None, dias_envio=None, preparado_fn=None) -> str` (YYYY-MM-DD)

- [ ] **Step 1: Write the failing test** — adicionar em `app/tests/test_series.py`:

```python
class TestSeriesAtivar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = _reload_db(self.tmp)
        self.dias = ["segunda", "terca", "quarta", "quinta", "sexta"]
        # uma segunda-feira ~2 semanas no futuro (determinístico)
        base = date.today() + timedelta(days=14)
        self.seg = base - timedelta(days=base.weekday())          # segunda
        self.seg_iso = self.seg.isoformat()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _serie_com(self, n):
        import curadoria  # noqa: garante que db reload não quebrou import chain
        sid = self.db.criar_serie("S")
        ids = []
        for k in range(n):
            rid = self.db.salvar_reserva({"tema": "Obesidade", "titulo_pt": f"R{k}",
                                          "resumo": "r", "tags": ["glp1"]})
            self.db.adicionar_serie_item(sid, "reserva", rid, titulo=f"R{k}", tema="Obesidade")
            ids.append(rid)
        return sid, ids

    def test_ativa_grava_n_dias_uteis_em_ordem_e_consome(self):
        import series
        sid, rids = self._serie_com(3)
        ok, msg = series.ativar_serie(sid, self.seg_iso, db_mod=self.db, dias_envio=self.dias)
        self.assertTrue(ok, msg)
        # seg, ter, qua recebem os 3 estudos em ordem
        esperados = [(self.seg + timedelta(days=k)).isoformat() for k in range(3)]
        for dia, rid in zip(esperados, rids):
            slot = self.db.agenda_slot(dia)
            self.assertEqual(slot["tipo"], "reserva")
            self.assertEqual(slot["ref_id"], rid)
            self.assertEqual(self.db.obter_reserva(rid)["status"], "agendado")  # consumido
        self.assertEqual(self.db.obter_serie(sid)["serie"]["status"], "ativa")
        self.assertEqual([i["data"] for i in self.db.obter_serie(sid)["itens"]], esperados)

    def test_pula_fixado_e_pulado(self):
        import series
        sid, rids = self._serie_com(2)
        ter = (self.seg + timedelta(days=1)).isoformat()
        qua = (self.seg + timedelta(days=2)).isoformat()
        self.db.agenda_fixar(ter, True)          # terça fixada -> pular
        ok, msg = series.ativar_serie(sid, self.seg_iso, db_mod=self.db, dias_envio=self.dias)
        self.assertTrue(ok, msg)
        datas = [i["data"] for i in self.db.obter_serie(sid)["itens"]]
        self.assertEqual(datas, [self.seg_iso, qua])   # seg e qua; terça pulada
        self.assertEqual(self.db.agenda_slot(ter)["fixado"], 1)  # fixado intacto

    def test_recusa_segunda_ativa(self):
        import series
        sid1, _ = self._serie_com(1)
        sid2, _ = self._serie_com(1)
        self.db.atualizar_serie(sid1, status="ativa")
        ok, msg = series.ativar_serie(sid2, self.seg_iso, db_mod=self.db, dias_envio=self.dias)
        self.assertFalse(ok)
        self.assertIn("ativa", msg.lower())

    def test_recusa_data_nao_util_e_abaixo_do_min(self):
        import series
        sid, _ = self._serie_com(1)
        sab = (self.seg + timedelta(days=5)).isoformat()   # sábado
        ok, _ = series.ativar_serie(sid, sab, db_mod=self.db, dias_envio=self.dias)
        self.assertFalse(ok)
        ok2, msg2 = series.ativar_serie(sid, self.seg_iso, dia_min="2099-01-01",
                                        db_mod=self.db, dias_envio=self.dias)
        self.assertFalse(ok2)
        self.assertIn("2099-01-01", msg2)

    def test_reconciliar_fecha_serie_vencida(self):
        import series
        sid, _ = self._serie_com(1)
        self.db.atualizar_serie(sid, status="ativa")
        self.db.set_serie_item_data(self.db.obter_serie(sid)["itens"][0]["id"], "2020-01-01")
        fechados = series.reconciliar(db_mod=self.db, hoje="2026-07-28")
        self.assertIn(sid, fechados)
        self.assertEqual(self.db.obter_serie(sid)["serie"]["status"], "concluida")

    def test_dia_minimo_pula_dia_ja_preparado(self):
        import series
        amanha = (date.today() + timedelta(days=1))
        # força amanhã a ser dia útil escolhendo dias_envio = todos
        todos = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
        preparado = {amanha.isoformat()}
        dm = series.dia_minimo_inicio(db_mod=self.db, hoje=date.today().isoformat(),
                                      dias_envio=todos, preparado_fn=lambda d: d in preparado)
        self.assertGreater(dm, amanha.isoformat())   # pulou amanhã (já preparado)

    def test_contexto_pagina(self):
        import series
        sid = self.db.criar_serie("S")
        self.db.salvar_reserva({"tema": "Obesidade", "titulo_pt": "Reta",
                                "resumo": "r", "tags": ["retatrutida"]})
        ctx = series.contexto_pagina(db_mod=self.db, serie_aberta_id=sid, termo="retatrutida")
        self.assertEqual(len(ctx["series"]), 1)
        self.assertEqual(ctx["aberta"]["serie"]["id"], sid)
        self.assertEqual(ctx["resultados"][0]["titulo"], "Reta")
        self.assertEqual(series.contexto_pagina(db_mod=self.db)["resultados"], [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_series.TestSeriesAtivar -v`
Expected: FAIL (`series` não existe).

- [ ] **Step 3: Write minimal implementation** — criar `app/series.py`:

```python
"""Séries temáticas (item 8, Fase 2) — orquestração.

Montar o contexto da página /series e ATIVAR uma série: grava os N estudos nos
próximos N dias úteis livres da agenda, reusando o mecanismo do Item 23
(agenda_upsert + marcar_*_agendado). A série só grava slots; o pipeline das 18h
(preview → gate → envio) já cuida do resto. Conclui por data (reconciliar)."""
from datetime import date, datetime, timedelta

import agenda_plan


def contexto_pagina(db_mod=None, serie_aberta_id=None, termo=""):
    """Dados da /series: lista de séries, a série aberta (ou None) e os resultados
    da busca por tag (ou [])."""
    if db_mod is None:
        import db as db_mod
    db_mod.init()
    series = db_mod.listar_series()
    aberta = db_mod.obter_serie(serie_aberta_id) if serie_aberta_id else None
    resultados = db_mod.buscar_por_tag(termo) if (termo or "").strip() else []
    return {"series": series, "aberta": aberta, "resultados": resultados}


def _dias_uteis_validos(dias_envio):
    validos = set(dias_envio) & set(agenda_plan.DIAS)
    if not validos:
        raise ValueError("dias_envio não contém dia útil válido")
    return validos


def _eh_dia_util(data_inicio, dias_envio):
    d = datetime.strptime(data_inicio, "%Y-%m-%d").date()
    return agenda_plan.DIAS[d.weekday()] in _dias_uteis_validos(dias_envio)


def _dias_livres(db_mod, data_inicio, n, dias_envio):
    """Próximos n dias úteis (YYYY-MM-DD) a partir de data_inicio que NÃO estão
    fixados nem pulados. Pula dias fixados/pulados (usa o próximo livre)."""
    validos = _dias_uteis_validos(dias_envio)
    d = datetime.strptime(data_inicio, "%Y-%m-%d").date()
    out = []
    while len(out) < n:
        if agenda_plan.DIAS[d.weekday()] in validos:
            s = db_mod.agenda_slot(d.isoformat())
            if not (s and (s.get("fixado") or s.get("tipo") == "pulado")):
                out.append(d.isoformat())
        d = d + timedelta(days=1)
    return out


def _liberar_dia(db_mod, dia):
    """Se o dia já tem estudo consumível (reserva/candidato), devolve ao estoque
    ANTES de a série sobrescrever o slot — evita órfão (mesmo cuidado do Item 23).
    Clássico não é consumido; vazio/fila não têm dono no estoque de estudos."""
    s = db_mod.agenda_slot(dia)
    if not s or not s.get("ref_id"):
        return
    if s.get("tipo") == "reserva":
        db_mod.marcar_reserva_pronto(s["ref_id"])
    elif s.get("tipo") == "candidato":
        db_mod.marcar_candidato_pronto(s["ref_id"])


def reconciliar(db_mod=None, hoje=None):
    """Fecha séries ATIVAS cujo último dia atribuído já passou (< hoje). Libera
    ativar outra. Retorna os ids concluídos."""
    if db_mod is None:
        import db as db_mod
    hoje = hoje or date.today().isoformat()
    fechados = []
    for s in db_mod.listar_series():
        if s.get("status") != "ativa":
            continue
        det = db_mod.obter_serie(s["id"])
        datas = [i.get("data") for i in det["itens"] if i.get("data")]
        if datas and max(datas) < hoje:
            db_mod.atualizar_serie(s["id"], status="concluida")
            fechados.append(s["id"])
    return fechados


def dia_minimo_inicio(db_mod=None, hoje=None, dias_envio=None, preparado_fn=None):
    """Primeiro dia útil a partir de AMANHÃ cujo preview das 18h ainda NÃO foi
    montado. Ativar num dia já preparado não trocaria o rascunho pronto (limitação
    do Item 23) — esse é o piso da data de início."""
    if db_mod is None:
        import db as db_mod
    if dias_envio is None:
        import daily
        dias_envio = daily._dias_envio()
    if preparado_fn is None:
        import draft_store
        preparado_fn = lambda d: draft_store.carregar(d) is not None
    validos = _dias_uteis_validos(dias_envio)
    d = (datetime.strptime(hoje, "%Y-%m-%d").date() if hoje else date.today()) + timedelta(days=1)
    while True:
        iso = d.isoformat()
        if agenda_plan.DIAS[d.weekday()] in validos and not preparado_fn(iso):
            return iso
        d = d + timedelta(days=1)


def ativar_serie(serie_id, data_inicio, dia_min=None, db_mod=None, dias_envio=None):
    """Grava os itens da série nos próximos N dias úteis livres a partir de
    data_inicio. Retorna (ok, msg). Não crasha: falha parcial → (False, aviso)."""
    if db_mod is None:
        import db as db_mod
    if dias_envio is None:
        import daily
        dias_envio = daily._dias_envio()
    db_mod.init()
    reconciliar(db_mod=db_mod)                        # fecha vencidas antes da trava
    det = db_mod.obter_serie(serie_id)
    if not det:
        return (False, "Série não encontrada.")
    if det["serie"].get("status") != "rascunho":
        return (False, "Só dá pra ativar uma série em rascunho.")
    itens = det["itens"]
    if not itens:
        return (False, "A série está vazia — adicione estudos antes de ativar.")
    if any(s.get("status") == "ativa" for s in db_mod.listar_series()):
        return (False, "Já existe uma série ativa. Espere ela terminar antes de ativar outra.")
    if not _eh_dia_util(data_inicio, dias_envio):
        return (False, "A data de início precisa cair num dia de envio (dia útil configurado).")
    if dia_min and data_inicio < dia_min:
        return (False, f"Escolha uma data a partir de {dia_min} — dias anteriores já podem ter o "
                       f"preview pronto. Pro 1º dia já preparado, use o 🔁 Trocar na revisão.")
    dias = _dias_livres(db_mod, data_inicio, len(itens), dias_envio)
    falhou = False
    for dia, item in zip(dias, itens):
        try:
            _liberar_dia(db_mod, dia)
            tipo, ref_id = item["ref_tipo"], item["ref_id"]
            db_mod.agenda_upsert(dia, tipo=tipo, ref_id=ref_id, payload=None,
                                 tema=item.get("tema", ""), titulo=item.get("titulo", ""), fixado=0)
            if tipo == "reserva":
                db_mod.marcar_reserva_agendado(ref_id)       # consome só APÓS gravar o slot
            elif tipo == "candidato":
                db_mod.marcar_candidato_agendado(ref_id)
            # clássico: agenda_upsert basta (reusável, não consome)
            db_mod.set_serie_item_data(item["id"], dia)
        except Exception as e:
            print(f"[series] falha ao gravar '{item.get('titulo','')}' em {dia}: {e}", flush=True)
            falhou = True
    db_mod.atualizar_serie(serie_id, status="ativa", data_inicio=data_inicio,
                           ativada_em=datetime.now().isoformat())
    if falhou:
        return (False, "Série ativada com falhas em alguns dias — confira a /agenda pra não faltar/repetir estudo.")
    return (True, f"Série ativada: {len(dias)} estudos a partir de {data_inicio}. Revise cada dia às 18h.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_series.TestSeriesAtivar -v`
Expected: PASS (7 testes).

- [ ] **Step 5: Commit**

```bash
git add app/series.py app/tests/test_series.py
git commit -m "feat(series): ativar_serie (grava N dias úteis livres + consome) + reconciliar + contexto_pagina"
```

---

### Task 3: site_web — `pagina_series` (o montador) + link no nav

**Files:**
- Modify: `app/site_web.py` (`pagina_series` novo; link `/series` em `_admin_nav` ~linha 656)
- Test: `app/tests/test_series.py` (nova classe)

**Interfaces:**
- Consumes: o dict de `series.contexto_pagina` (`{"series","aberta","resultados"}`), `_esc`, `_admin_nav`.
- Produces: `pagina_series(ctx, token, serie_aberta_id="", dia_min="", msg="") -> str` (HTML).

- [ ] **Step 1: Write the failing test** — adicionar em `app/tests/test_series.py`:

```python
class TestPaginaSeries(unittest.TestCase):
    def _ctx(self, aberta=None, resultados=None):
        return {"series": [{"id": "s1", "nome": "Série GLP1", "status": "rascunho"}],
                "aberta": aberta, "resultados": resultados or []}

    def test_lista_e_form_nova(self):
        import site_web
        html = site_web.pagina_series(self._ctx(), "tok")
        self.assertIn("Série GLP1", html)
        self.assertIn("/series", html)
        self.assertIn('name="acao"', html)          # form de criar
        self.assertIn("value=\"criar\"", html)

    def test_montador_com_itens_e_ativar(self):
        import site_web
        aberta = {"serie": {"id": "s1", "nome": "Série GLP1", "status": "rascunho", "data_inicio": ""},
                  "itens": [{"id": "i1", "ordem": 0, "ref_tipo": "reserva", "ref_id": "r1",
                             "titulo": "Retatrutida 24s", "tema": "Obesidade", "data": ""}]}
        resultados = [{"tipo": "reserva", "id": "r2", "titulo": "Semaglutida", "tema": "Obesidade",
                       "tags": ["semaglutida"]}]
        html = site_web.pagina_series(self._ctx(aberta, resultados), "tok",
                                      serie_aberta_id="s1", dia_min="2026-08-10")
        self.assertIn("Retatrutida 24s", html)       # item na série
        self.assertIn("Semaglutida", html)           # resultado da busca
        self.assertIn('value="ativar"', html)        # form de ativar (rascunho)
        self.assertIn("2026-08-10", html)            # min da data de início

    def test_escapa_titulo_malicioso(self):
        import site_web
        aberta = {"serie": {"id": "s1", "nome": "S", "status": "rascunho", "data_inicio": ""},
                  "itens": [{"id": "i1", "ordem": 0, "ref_tipo": "reserva", "ref_id": "r1",
                             "titulo": "<script>x</script>", "tema": "", "data": ""}]}
        html = site_web.pagina_series(self._ctx(aberta), "tok", serie_aberta_id="s1")
        self.assertNotIn("<script>x</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_ativa_nao_mostra_form_ativar(self):
        import site_web
        aberta = {"serie": {"id": "s1", "nome": "S", "status": "ativa", "data_inicio": "2026-08-10"},
                  "itens": []}
        html = site_web.pagina_series(self._ctx(aberta), "tok", serie_aberta_id="s1")
        self.assertNotIn('value="ativar"', html)
        self.assertIn("ativa", html.lower())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_series.TestPaginaSeries -v`
Expected: FAIL (`pagina_series` não existe).

- [ ] **Step 3: Write minimal implementation** — em `app/site_web.py`:

**(a)** No `_admin_nav` (dentro do `return (...)`, junto dos outros `lk(...)`), adicionar o link depois do `/agenda`:

```python
            + lk("/series", "🎬 Séries", "series")
```

**(b)** Adicionar `pagina_series` (perto de `pagina_curadoria`/`pagina_agenda`). Usa `_esc`, `_admin_nav`, e o mesmo shell `<div class="wrap">…</div>` das outras telas admin:

```python
def pagina_series(ctx, token, serie_aberta_id="", dia_min="", msg=""):
    """Montador de séries: lista + (rascunho aberto) busca por tag + itens ordenados
    + adicionar meu estudo + ativar com data de início."""
    tk = _esc(token)
    aviso = f'<p class="hint">{_esc(msg)}</p>' if msg else ""

    def _badge(st):
        cor = {"rascunho": "#8a7", "ativa": "var(--ouro2)", "concluida": "#999"}.get(st, "#999")
        return f'<span style="color:{cor};font-size:12px;text-transform:uppercase">{_esc(st)}</span>'

    linhas = ""
    for s in ctx.get("series", []):
        linhas += (f'<li style="margin:6px 0"><a href="/series?serie={_esc(s["id"])}&token={tk}" '
                   f'style="color:var(--ouro2);text-decoration:none">{_esc(s.get("nome") or "(sem nome)")}</a> '
                   f'&nbsp;{_badge(s.get("status",""))}</li>')
    lista = f'<ul style="list-style:none;padding:0">{linhas or "<li class=hint>Nenhuma série ainda.</li>"}</ul>'

    nova = (f'<form method="post" action="/series" style="margin:10px 0">'
            f'<input type="hidden" name="acao" value="criar">'
            f'<input type="hidden" name="token" value="{tk}">'
            f'<input name="nome" placeholder="Nome da nova série (ex.: Série GLP1)" '
            f'style="padding:8px;min-width:280px">'
            f'<button type="submit">➕ Criar série</button></form>')

    montador = ""
    aberta = ctx.get("aberta")
    if aberta:
        sid = _esc(aberta["serie"]["id"])
        st = aberta["serie"].get("status", "")
        # itens da série
        its = ""
        for it in aberta.get("itens", []):
            iid = _esc(it["id"])
            dia = f' · <b>{_esc(it["data"])}</b>' if it.get("data") else ""
            its += (f'<li style="margin:5px 0;display:flex;gap:6px;align-items:center">'
                    f'<span>{_esc(it.get("titulo") or it.get("ref_id"))} '
                    f'<span class=hint>({_esc(it.get("ref_tipo"))}{dia})</span></span>')
            if st == "rascunho":
                for direc, seta in (("cima", "↑"), ("baixo", "↓")):
                    its += (f'<form method="post" action="/series" style="display:inline">'
                            f'<input type="hidden" name="acao" value="reordenar">'
                            f'<input type="hidden" name="token" value="{tk}">'
                            f'<input type="hidden" name="serie" value="{sid}">'
                            f'<input type="hidden" name="item" value="{iid}">'
                            f'<input type="hidden" name="direcao" value="{direc}">'
                            f'<button type="submit">{seta}</button></form>')
                its += (f'<form method="post" action="/series" style="display:inline">'
                        f'<input type="hidden" name="acao" value="remover_item">'
                        f'<input type="hidden" name="token" value="{tk}">'
                        f'<input type="hidden" name="serie" value="{sid}">'
                        f'<input type="hidden" name="item" value="{iid}">'
                        f'<button type="submit">🗑️</button></form>')
            its += "</li>"
        itens_html = f'<ul style="list-style:none;padding:0">{its or "<li class=hint>Vazia.</li>"}</ul>'

        if st == "rascunho":
            # busca por tag
            busca = (f'<form method="post" action="/series" style="margin:10px 0">'
                     f'<input type="hidden" name="acao" value="buscar">'
                     f'<input type="hidden" name="token" value="{tk}">'
                     f'<input type="hidden" name="serie" value="{sid}">'
                     f'<input name="termo" placeholder="Buscar no estoque por tag (ex.: glp1)" '
                     f'style="padding:8px;min-width:260px">'
                     f'<button type="submit">🔎 Buscar</button></form>')
            res = ""
            for r in ctx.get("resultados", []):
                res += (f'<li style="margin:4px 0">'
                        f'<form method="post" action="/series" style="display:inline">'
                        f'<input type="hidden" name="acao" value="add_item">'
                        f'<input type="hidden" name="token" value="{tk}">'
                        f'<input type="hidden" name="serie" value="{sid}">'
                        f'<input type="hidden" name="tipo" value="{_esc(r.get("tipo"))}">'
                        f'<input type="hidden" name="id" value="{_esc(r.get("id"))}">'
                        f'<input type="hidden" name="titulo" value="{_esc(r.get("titulo"))}">'
                        f'<input type="hidden" name="tema" value="{_esc(r.get("tema"))}">'
                        f'<button type="submit">➕</button> {_esc(r.get("titulo"))} '
                        f'<span class=hint>({_esc(r.get("tipo"))} · {_esc(", ".join(r.get("tags", [])))})</span>'
                        f'</form></li>')
            resultados_html = (f'<ul style="list-style:none;padding:0">{res}</ul>' if res else "")

            # adicionar meu estudo (upload) — multipart, mesmo campo do /curadoria
            meu = (f'<form method="post" action="/series" enctype="multipart/form-data" '
                   f'style="margin:12px 0;padding:10px;border:1px solid #333;border-radius:8px">'
                   f'<b>➕ Adicionar meu estudo</b><br>'
                   f'<input type="hidden" name="acao" value="add_meu_estudo">'
                   f'<input type="hidden" name="token" value="{tk}">'
                   f'<input type="hidden" name="serie" value="{sid}">'
                   f'<input name="titulo" placeholder="Título (opcional)" style="padding:6px"><br>'
                   f'<input type="file" name="pdf" accept="application/pdf"><br>'
                   f'<textarea name="texto" placeholder="…ou cole o resumo" '
                   f'style="width:100%;height:70px"></textarea>'
                   f'<button type="submit">Enviar</button></form>')

            ativar = (f'<form method="post" action="/series" style="margin:12px 0">'
                      f'<input type="hidden" name="acao" value="ativar">'
                      f'<input type="hidden" name="token" value="{tk}">'
                      f'<input type="hidden" name="serie" value="{sid}">'
                      f'<label>Data de início: '
                      f'<input type="date" name="data_inicio" min="{_esc(dia_min)}" '
                      f'value="{_esc(dia_min)}" required></label> '
                      f'<button type="submit">🚀 Ativar série</button>'
                      f'<span class=hint> (ocupa os próximos dias úteis livres, em ordem)</span></form>')
            montador = (f'<h3>{_esc(aberta["serie"].get("nome"))} {_badge(st)}</h3>'
                        f'{itens_html}{busca}{resultados_html}{meu}{ativar}')
        else:
            montador = (f'<h3>{_esc(aberta["serie"].get("nome"))} {_badge(st)}</h3>'
                        f'<p class=hint>Início: {_esc(aberta["serie"].get("data_inicio") or "—")}. '
                        f'Série já ativada/concluída — edição de itens é fora do MVP.</p>{itens_html}')

    corpo = (f'<div class="wrap">{_admin_nav(token, "series")}'
             f'<h2>🎬 Séries de estudos</h2>{aviso}{nova}{lista}{montador}</div>')
    return _pagina("Séries · Admin", corpo, logado=True, atual="series")
```

*(Wrapper confirmado: `_pagina(titulo, corpo, logado=False, meta_extra="", atual="")` em `site_web.py:398` — `titulo` PRIMEIRO, `corpo` SEGUNDO; `pagina_curadoria`/`pagina_agenda` chamam com `logado=True`. As classes `.wrap`/`.hint`/`.actbtn` já existem no CSS.)*

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_series.TestPaginaSeries -v`
Expected: PASS (4 testes).

- [ ] **Step 5: Commit**

```bash
git add app/site_web.py app/tests/test_series.py
git commit -m "feat(series): pagina_series (montador: busca/itens/upload/ativar) + link no admin nav"
```

---

### Task 4: serve — rotas `/series` (GET + POST) + regressão

**Files:**
- Modify: `app/serve.py` (GET `/series` no `do_GET`; POST `/series` no `do_POST` — branch multipart + ações urlencoded)
- Test: regressão (suíte inteira)

**Interfaces:**
- Consumes: `series.contexto_pagina`, `series.dia_minimo_inicio`, `series.ativar_serie`, `site_web.pagina_series`, `db.criar_serie`/`adicionar_serie_item`/`remover_serie_item`/`reordenar_serie_item`, `curadoria.adicionar_meu_estudo`, `curadoria.extrair_texto_pdf`, `config.ADMIN_TOKEN`.

- [ ] **Step 1: Implementar GET `/series`** — em `app/serve.py`, no `do_GET`, ao lado de `/curadoria`/`/agenda` (mesmo padrão de token e `pagina_*`):

```python
        if path == "/series":
            import config, series, site_web
            token_ok = config.ADMIN_TOKEN and q.get("token", [""])[0] == config.ADMIN_TOKEN
            if not token_ok:
                return self._html("<h3>Acesso negado</h3>", 403)
            sid = q.get("serie", [""])[0] or None
            termo = q.get("termo", [""])[0]
            ctx = series.contexto_pagina(serie_aberta_id=sid, termo=termo)
            dia_min = series.dia_minimo_inicio()
            return self._html(site_web.pagina_series(
                ctx, config.ADMIN_TOKEN or "", serie_aberta_id=sid or "",
                dia_min=dia_min, msg=q.get("msg", [""])[0]))
```

- [ ] **Step 2: Implementar POST `/series` multipart (upload do meu estudo)** — em `app/serve.py`, no `do_POST`, junto do branch multipart do `/curadoria` (~linha 475):

```python
        if path == "/series" and ctype.startswith("multipart/form-data"):
            return self._series_upload(raw, ctype)
```

E o método (perto de `_curadoria_upload`, mesmo padrão):

```python
    def _series_upload(self, raw, ctype):
        """POST /series (multipart) -> adicionar meu estudo à reserva e à série aberta."""
        import config, db, curadoria
        campos, arquivos = self._parse_multipart(ctype, raw)
        if not config.ADMIN_TOKEN or campos.get("token") != config.ADMIN_TOKEN:
            return self._html("<h3>Acesso negado</h3>", 403)
        db.init()
        sid = campos.get("serie", "")
        msg = ""
        try:
            texto = ""
            _, pdf = arquivos.get("pdf", (None, None))
            if pdf:
                texto = curadoria.extrair_texto_pdf(pdf)
            if not (texto or "").strip():
                texto = campos.get("texto", "")
            if not (texto or "").strip():
                msg = "Envie um PDF com texto selecionável, ou cole o resumo do estudo."
            else:
                rid, tit = curadoria.adicionar_meu_estudo(texto, titulo=campos.get("titulo", ""))
                db.adicionar_serie_item(sid, "reserva", rid, titulo=tit, tema="Meus estudos")
                msg = f"✅ Adicionado à série: {tit}"
        except ValueError as e:
            msg = str(e)
        except Exception as e:
            print(f"[series] add meu estudo erro: {e}", flush=True)
            msg = "Falha ao processar o estudo (ver logs)."
        import urllib.parse as _up
        return self._redirect(f"/series?serie={_up.quote(sid)}&token={config.ADMIN_TOKEN}&msg={_up.quote(msg)}")
```

- [ ] **Step 3: Implementar POST `/series` urlencoded (ações)** — em `app/serve.py`, no `do_POST` (após o `g = lambda k: ...`, junto das outras rotas POST):

```python
        if path == "/series":
            import config, db, series
            token_ok = bool(config.ADMIN_TOKEN) and g("token") == config.ADMIN_TOKEN
            if not token_ok:
                return self._html("<h3>Acesso negado</h3>", 403)
            db.init()
            acao, sid, msg = g("acao"), g("serie"), ""
            if acao == "criar":
                sid = db.criar_serie(g("nome"))
            elif acao == "buscar":
                import urllib.parse as _up
                return self._redirect(
                    f"/series?serie={_up.quote(sid)}&token={config.ADMIN_TOKEN}"
                    f"&termo={_up.quote(g('termo'))}")
            elif acao == "add_item":
                db.adicionar_serie_item(sid, g("tipo"), g("id"), titulo=g("titulo"), tema=g("tema"))
                msg = "Adicionado."
            elif acao == "remover_item":
                db.remover_serie_item(g("item"))
                msg = "Removido."
            elif acao == "reordenar":
                db.reordenar_serie_item(g("item"), g("direcao"))
            elif acao == "ativar":
                ok, msg = series.ativar_serie(sid, g("data_inicio"), dia_min=series.dia_minimo_inicio())
            import urllib.parse as _up
            alvo = f"/series?serie={_up.quote(sid)}&token={config.ADMIN_TOKEN}"
            if msg:
                alvo += f"&msg={_up.quote(msg)}"
            return self._redirect(alvo)
```

*(Confirme a assinatura de `self._parse_multipart` e `self._redirect` lendo `_curadoria_upload` — são os mesmos usados aqui. O branch multipart de `/series` precisa vir ANTES do `form = up.parse_qs(...)`, igual ao de `/curadoria`.)*

- [ ] **Step 4: Rodar a suíte inteira (regressão)**

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -6`
Expected: `OK`. Baseline 745 + os novos (`TestDbSeries` 5 + `TestSeriesAtivar` 7 + `TestPaginaSeries` 4 = 16) → **761 testes**, todos verdes. Materialize/rotação normal intactos (a série só grava slots via o mesmo `agenda_upsert`).

- [ ] **Step 5: Smoke manual (documentar, não bloqueia)**

1. `/series?token=…` → Criar série → abrir → 🔎 buscar por tag → ➕ adicionar 2-3 → ↑/↓ ordenar.
2. ➕ Adicionar meu estudo (PDF/colado) → entra na série.
3. 🚀 Ativar com data de início (dia útil ≥ `dia_min`) → conferir na `/agenda` que os N dias úteis seguidos receberam os estudos em ordem.
4. Cada dia cai no preview das 18h; enviar 08h. Ao passar o último dia, `/series` mostra "concluída" e libera ativar outra.
5. Bordas: tentar 2ª série ativa → recusa; data em dia já preparado (< `dia_min`) → recusa com dica do 🔁 Trocar.

- [ ] **Step 6: Commit**

```bash
git add app/serve.py
git commit -m "feat(series): rotas /series (GET montador + POST criar/buscar/add/remover/reordenar/ativar/upload)"
```

---

## Notas de execução

- **Deploy:** decidir com o Diego (junto da Fase 1, que ainda não foi pushada/deployada, ou depois). Sem push/deploy neste plano.
- **Fora de escopo (backlog):** várias séries ativas; intercalar com a rotação; reordenar/editar depois de ativar; série montada pela IA; flip de `serie_itens.enviado` pelo pipeline de envio (o MVP conclui por data). Ver [[tags-series]].
- **Follow-up de robustez herdado da Fase 1:** `triage._parse` tem o mesmo bug latente do `taggear` (assume dict antes de `.get("i")`) no caminho diário — hardening de 1 linha, independente desta fase.

## Self-Review (checklist do autor)

- **Cobertura da spec:** montar por tag+upload (Task 3 busca/upload + Task 4 rotas) ✓; ordenar/remover (Task 1 CRUD + Task 3 UI + Task 4 rotas) ✓; ativar com data de início ocupando N dias úteis em ordem (Task 2) ✓; uma ativa por vez (Task 2 trava + reconciliar) ✓; respeita fixado/pulado (Task 2 `_dias_livres`) ✓; gate 18h intacto (só grava slots — nenhuma mudança no pipeline) ✓; conclui e libera outra (Task 2 `reconciliar`) ✓; borda "dia já preparado" (Task 2 `dia_minimo_inicio` + validação em `ativar_serie`) ✓; página admin-gated + nav (Task 3/4) ✓; regressão (Task 4) ✓.
- **Consistência de tipos:** `ativar_serie` devolve `(bool,str)` — consumido no POST `ativar` como `ok, msg`; `contexto_pagina` devolve `{"series","aberta","resultados"}` — consumido por `pagina_series`; `buscar_por_tag` → `[{tipo,id,titulo,tema,tags}]` — usado em `add_item` (tipo/id/titulo/tema) e nos resultados. `obter_serie` → `{"serie","itens"}` em todos os consumidores.
- **Sem placeholders:** todo passo tem código real. Os 2 pontos de "confirmar nome" (wrapper de página em `pagina_series`; `_parse_multipart`/`_redirect`) são checagens de integração contra código existente, não lacunas de design — o implementer confirma lendo `pagina_agenda`/`_curadoria_upload`.
