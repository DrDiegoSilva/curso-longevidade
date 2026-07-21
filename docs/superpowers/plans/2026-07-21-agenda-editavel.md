# Calendário editável de envios — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Materializar os próximos ~15 dias úteis de envio numa agenda que o sistema pré-preenche e o Dr. Diego reordena/edita numa tela `/agenda`.

**Architecture:** Uma função pura de planejamento (`agenda_plan.py`) decide quais estudos vão em quais dias (rotação de tema + variedade + preferência reserva>fila). Uma tabela `agenda` (SQLite/Postgres via `db.py`) persiste `data → estudo`. `daily.materializar_agenda` faz a cola (lê estoques → planeja → grava, tirando o item do estoque). `preparar_18h` passa a ler o slot de amanhã com fallback pro comportamento atual. Painel `/agenda` (server-rendered no `site_web.py`, gated por `ADMIN_TOKEN`) com arrastar-e-soltar e fallback sem JS.

**Tech Stack:** Python 3.12 stdlib apenas (sem pip). SQLite local (testes) / Postgres-Supabase (prod) via `db._conn`. HTML server-rendered em `site_web.py`. JS vanilla inline (sem biblioteca). Testes `unittest` rodados com pytest.

## Global Constraints

- **Sem dependências novas** — só stdlib do Python. (Projeto roda em container sem pip.)
- **Banco via `db._conn()`** — placeholders `?` (traduzidos p/ `%s` no Postgres pelo `_Wrap`); nunca f-string com valores.
- **Persistência em `/data`** — `queue.json` usa `config.DATA`; SQLite usa `config.artigos_db()`. Testes sobrescrevem via env `DSCURSO_DATA` e `DSCURSO_ARTIGOS_DB`.
- **Dias de envio** — seg–sex (`temas_config.json → dias_envio`). Nomes: `["segunda","terca","quarta","quinta","sexta","sabado","domingo"]`, indexados por `datetime.weekday()`.
- **Rotas admin gated** — `if not config.ADMIN_TOKEN or g("token") != config.ADMIN_TOKEN: return self._html("<h3>Acesso negado</h3>", 403)`.
- **HTML sempre escapado** — usar `site_web._esc()` em qualquer valor dinâmico.
- **Fallback nunca falha um dia útil** — se a agenda não tiver item válido, cai no fluxo atual (fila→reserva).
- **Branch de trabalho:** `feat/agenda-editavel` (já criada).
- **Commits pequenos e frequentes**, mensagens em pt-BR no formato `tipo(escopo): descrição`.

---

## Estrutura de arquivos

| arquivo | responsabilidade |
|---|---|
| `app/agenda_plan.py` (novo) | Funções **puras**: cálculo de dias úteis, planejamento (rotação+variedade), classificação de slot, decisão de reabastecimento, agrupamento por semana. Sem I/O. |
| `app/db.py` (modificar) | Tabela `agenda` + CRUD + status `agendado` na reserva. |
| `app/queue_store.py` (modificar) | `listar()`, `remover(artigo)`, `devolver(artigo)`. |
| `app/daily.py` (modificar) | `materializar_agenda()` (cola); `preparar_18h` lê o slot com fallback; `_preparar_da_reserva(reserva_id=None)`; `_preparar_de_artigo(art)`; ajuste C no reabastecimento. |
| `app/serve.py` (modificar) | Rota `/agenda` (GET render + POST ações), gated por `ADMIN_TOKEN`. |
| `app/site_web.py` (modificar) | `pagina_agenda(...)` (grade + DnD inline + fallback). |
| `app/temas_config.json` (modificar) | `rotacao_semana` opcional. |
| `app/tests/test_agenda_plan.py` (novo) | Testes das funções puras. |
| `app/tests/test_agenda_db.py` (novo) | Testes do CRUD + status reserva. |
| `app/tests/test_agenda_materializar.py` (novo) | Teste da cola (estoque temporário). |

---

## Task 1: Funções puras de planejamento (`agenda_plan.py`)

**Files:**
- Create: `app/agenda_plan.py`
- Test: `app/tests/test_agenda_plan.py`

**Interfaces:**
- Consumes: nada (stdlib `datetime` só).
- Produces:
  - `dias_uteis_desde(inicio: datetime, n: int, dias_envio: set[str]) -> list[str]` — próximos `n` dias úteis `YYYY-MM-DD` a partir de `inicio` (inclui `inicio` se útil).
  - `planejar_agenda(dias_ordenados: list[tuple[str, str|None, bool]], candidatos: list[dict], rotacao: list[str], tema_anterior: str|None) -> dict[str, dict]` — mapa `data → candidato escolhido` só p/ os dias vazios. Candidato: `{"tipo":"reserva"|"fila","tema":str,"titulo":str,"ref_id":str|None,"payload":dict|None}`.
  - `classificar_slot(slot: dict|None) -> tuple[str, object]` — `("pulado"|"reserva"|"fila"|"fallback", ref)`; ref = `ref_id` (reserva), `payload` (fila) ou `None`.
  - `precisa_reabastecer(fila_n: int, reserva_n: int, horizonte: int) -> bool`.
  - `agrupar_por_semana(slots_ordenados: list[dict]) -> list[list[dict]]` — quebra em blocos por semana ISO.

- [ ] **Step 1: Escrever os testes que falham**

Criar `app/tests/test_agenda_plan.py`:

```python
"""Testes das funções puras de planejamento da agenda. Sem I/O."""
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import agenda_plan as ap


def _cand(tema, tipo="reserva", titulo="t", ref_id="r", payload=None):
    return {"tipo": tipo, "tema": tema, "titulo": titulo, "ref_id": ref_id, "payload": payload}


class TestDiasUteis(unittest.TestCase):
    def test_pula_fim_de_semana(self):
        envio = {"segunda", "terca", "quarta", "quinta", "sexta"}
        # 2026-07-24 é sexta; próximos 3 úteis = sex, seg, ter
        got = ap.dias_uteis_desde(datetime(2026, 7, 24), 3, envio)
        self.assertEqual(got, ["2026-07-24", "2026-07-27", "2026-07-28"])

    def test_conta_certa(self):
        envio = {"segunda", "terca", "quarta", "quinta", "sexta"}
        self.assertEqual(len(ap.dias_uteis_desde(datetime(2026, 7, 20), 15, envio)), 15)


class TestPlanejar(unittest.TestCase):
    def _dias(self, datas):
        return [(d, None, False) for d in datas]

    def test_variedade_nao_repete_tema(self):
        dias = self._dias(["2026-07-27", "2026-07-28", "2026-07-29"])
        cands = [_cand("A"), _cand("A"), _cand("B"), _cand("B")]
        plano = ap.planejar_agenda(dias, cands, ["A", "B"], None)
        temas = [plano[d]["tema"] for d in ["2026-07-27", "2026-07-28", "2026-07-29"]]
        self.assertNotEqual(temas[0], temas[1])
        self.assertNotEqual(temas[1], temas[2])

    def test_respeita_dia_bloqueado(self):
        # dia do meio fixado/pulado (bloqueado) não recebe plano; seu tema alimenta variedade
        dias = [("2026-07-27", None, False), ("2026-07-28", "A", True), ("2026-07-29", None, False)]
        cands = [_cand("A"), _cand("A")]
        plano = ap.planejar_agenda(dias, cands, ["A"], None)
        self.assertNotIn("2026-07-28", plano)
        self.assertIn("2026-07-27", plano)
        # 29 vem depois de bloqueado tema A -> variedade tenta != A, mas só há A -> ainda preenche
        self.assertIn("2026-07-29", plano)

    def test_reserva_antes_de_fila(self):
        dias = self._dias(["2026-07-27"])
        cands = [_cand("A", tipo="fila", ref_id=None, payload={"x": 1}), _cand("A", tipo="reserva")]
        plano = ap.planejar_agenda(dias, cands, ["A"], None)
        self.assertEqual(plano["2026-07-27"]["tipo"], "reserva")

    def test_estoque_magro_deixa_vazio(self):
        dias = self._dias(["2026-07-27", "2026-07-28"])
        cands = [_cand("A")]
        plano = ap.planejar_agenda(dias, cands, ["A"], None)
        self.assertEqual(len(plano), 1)

    def test_nao_reusa_candidato(self):
        dias = self._dias(["2026-07-27", "2026-07-28"])
        cands = [_cand("A", ref_id="r1"), _cand("B", ref_id="r2")]
        plano = ap.planejar_agenda(dias, cands, ["A", "B"], None)
        self.assertNotEqual(plano["2026-07-27"]["ref_id"], plano["2026-07-28"]["ref_id"])


class TestClassificarSlot(unittest.TestCase):
    def test_none_e_fallback(self):
        self.assertEqual(ap.classificar_slot(None), ("fallback", None))

    def test_pulado(self):
        self.assertEqual(ap.classificar_slot({"tipo": "pulado"}), ("pulado", None))

    def test_reserva(self):
        self.assertEqual(ap.classificar_slot({"tipo": "reserva", "ref_id": "abc"}), ("reserva", "abc"))

    def test_fila(self):
        self.assertEqual(ap.classificar_slot({"tipo": "fila", "payload": "{}"}), ("fila", "{}"))

    def test_vazio_e_fallback(self):
        self.assertEqual(ap.classificar_slot({"tipo": "vazio"}), ("fallback", None))


class TestReabastecer(unittest.TestCase):
    def test_abaixo_do_horizonte(self):
        self.assertTrue(ap.precisa_reabastecer(2, 3, 15))

    def test_estoque_suficiente(self):
        self.assertFalse(ap.precisa_reabastecer(10, 10, 15))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python3 -m pytest app/tests/test_agenda_plan.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'agenda_plan'`.

- [ ] **Step 3: Implementar `agenda_plan.py`**

Criar `app/agenda_plan.py`:

```python
"""Planejamento puro da agenda de envios — sem I/O (testável em memória).

Regras: preencher só os dias VAZIOS; rotação de tema como guia + variedade
(não repetir o tema do dia anterior quando houver alternativa) + preferência
reserva pronta > fila fresca. Não consome candidato duas vezes.
"""
from datetime import timedelta

DIAS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]


def dias_uteis_desde(inicio, n, dias_envio):
    """Próximos n dias úteis (YYYY-MM-DD) a partir de `inicio` (datetime), inclusive."""
    out, d = [], inicio
    while len(out) < n:
        if DIAS[d.weekday()] in dias_envio:
            out.append(d.strftime("%Y-%m-%d"))
        d = d + timedelta(days=1)
    return out


def _rank(cand, preferido, prev):
    return (
        1 if cand["tema"] == preferido else 0,     # bate a rotação do dia
        1 if cand["tema"] != prev else 0,           # variedade
        1 if cand["tipo"] == "reserva" else 0,      # pronto antes de fresco
    )


def _escolher(candidatos, usados, preferido, prev):
    disp = [(i, c) for i, c in enumerate(candidatos) if i not in usados]
    if not disp:
        return None, None
    return max(disp, key=lambda ic: _rank(ic[1], preferido, prev))


def planejar_agenda(dias_ordenados, candidatos, rotacao, tema_anterior):
    """dias_ordenados: [(data, tema_atual|None, bloqueado)]. Retorna {data: candidato}
    só p/ os dias vazios (tema_atual None e não-bloqueado)."""
    prev = tema_anterior
    usados, plano = set(), {}
    rot = rotacao or []
    rot_i = 0
    for data, tema_atual, bloqueado in dias_ordenados:
        if bloqueado or tema_atual is not None:
            prev = tema_atual
            continue
        preferido = rot[rot_i % len(rot)] if rot else None
        idx, cand = _escolher(candidatos, usados, preferido, prev)
        if cand is None:
            prev = None
            continue
        plano[data] = cand
        usados.add(idx)
        prev = cand["tema"]
        rot_i += 1
    return plano


def classificar_slot(slot):
    """Decide a fonte do preparo das 18h a partir do slot (função pura)."""
    if not slot:
        return ("fallback", None)
    t = slot.get("tipo")
    if t == "pulado":
        return ("pulado", None)
    if t == "reserva" and slot.get("ref_id"):
        return ("reserva", slot["ref_id"])
    if t == "fila" and slot.get("payload"):
        return ("fila", slot["payload"])
    return ("fallback", None)


def precisa_reabastecer(fila_n, reserva_n, horizonte):
    """Reabastece enquanto o estoque total não cobre o horizonte (acumula os frescos
    da semana em vez de só reabastecer quando a fila esvazia)."""
    return (fila_n + reserva_n) < horizonte


def agrupar_por_semana(slots_ordenados):
    """Quebra a lista de slots (ordenada por data) em blocos por semana ISO."""
    semanas, atual, chave = [], [], None
    from datetime import datetime
    for s in slots_ordenados:
        wk = datetime.strptime(s["data"], "%Y-%m-%d").isocalendar()[:2]
        if chave is not None and wk != chave:
            semanas.append(atual)
            atual = []
        atual.append(s)
        chave = wk
    if atual:
        semanas.append(atual)
    return semanas
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python3 -m pytest app/tests/test_agenda_plan.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add app/agenda_plan.py app/tests/test_agenda_plan.py
git commit -m "feat(agenda): planejamento puro (dias úteis, rotação+variedade, classificação de slot)"
```

---

## Task 2: Tabela `agenda` + CRUD + status `agendado` na reserva (`db.py`)

**Files:**
- Modify: `app/db.py` (bloco `init()` executescript ~linha 160; lista `_TABELAS` ~linha 177; novas funções após `marcar_reserva_enviado` ~linha 461)
- Test: `app/tests/test_agenda_db.py`

**Interfaces:**
- Consumes: `db.init`, `db._conn`, `db.listar_reserva`, `db.proximo_da_reserva`, `db.contar_reserva_pronto` (já existem).
- Produces:
  - `agenda_slot(data: str) -> dict|None`
  - `agenda_listar(desde: str, ate: str) -> dict[str, dict]`
  - `agenda_upsert(data, tipo="vazio", ref_id=None, payload=None, tema="", titulo="", fixado=0) -> None`
  - `agenda_fixar(data: str, on: bool=True) -> None`
  - `agenda_pular(data: str, on: bool=True) -> None`
  - `agenda_mover(data_orig: str, data_dest: str) -> bool` (False se destino fixado)
  - `agenda_devolver(data: str) -> None` (devolve item ao estoque; slot vira `vazio`)
  - `marcar_reserva_agendado(rid: str) -> None`
  - `marcar_reserva_pronto(rid: str) -> None`

- [ ] **Step 1: Escrever os testes que falham**

Criar `app/tests/test_agenda_db.py`:

```python
"""Testes do CRUD da agenda + status 'agendado' na reserva (SQLite temporário)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAgendaDb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ.pop("DATABASE_URL", None)
        import importlib, db as _db
        importlib.reload(_db)
        self.db = _db
        self.db.init()

    def _reserva(self, tema="Obesidade", titulo="Estudo X"):
        return self.db.salvar_reserva({"tema": tema, "titulo_pt": titulo, "resumo": "r",
                                       "gancho": "g", "grafico": "", "doi": "", "fonte": "NEJM",
                                       "url": "", "data": "2026-07-20"})

    def test_upsert_e_slot(self):
        self.db.agenda_upsert("2026-07-27", tipo="reserva", ref_id="abc", tema="Obesidade", titulo="T")
        s = self.db.agenda_slot("2026-07-27")
        self.assertEqual(s["tipo"], "reserva")
        self.assertEqual(s["ref_id"], "abc")
        self.assertEqual(s["titulo"], "T")

    def test_upsert_atualiza(self):
        self.db.agenda_upsert("2026-07-27", tipo="vazio")
        self.db.agenda_upsert("2026-07-27", tipo="pulado")
        self.assertEqual(self.db.agenda_slot("2026-07-27")["tipo"], "pulado")

    def test_listar_intervalo(self):
        self.db.agenda_upsert("2026-07-27", tipo="reserva", ref_id="a")
        self.db.agenda_upsert("2026-07-28", tipo="reserva", ref_id="b")
        self.db.agenda_upsert("2026-08-10", tipo="reserva", ref_id="c")
        m = self.db.agenda_listar("2026-07-27", "2026-07-31")
        self.assertEqual(set(m.keys()), {"2026-07-27", "2026-07-28"})

    def test_agendado_some_da_reserva(self):
        rid = self._reserva()
        self.assertEqual(self.db.contar_reserva_pronto(), 1)
        self.db.marcar_reserva_agendado(rid)
        self.assertEqual(self.db.contar_reserva_pronto(), 0)
        self.assertIsNone(self.db.proximo_da_reserva())
        self.db.marcar_reserva_pronto(rid)
        self.assertEqual(self.db.contar_reserva_pronto(), 1)

    def test_devolver_volta_pronto(self):
        rid = self._reserva()
        self.db.marcar_reserva_agendado(rid)
        self.db.agenda_upsert("2026-07-27", tipo="reserva", ref_id=rid, tema="Obesidade", titulo="T")
        self.db.agenda_devolver("2026-07-27")
        self.assertEqual(self.db.agenda_slot("2026-07-27")["tipo"], "vazio")
        self.assertEqual(self.db.contar_reserva_pronto(), 1)

    def test_mover_swap(self):
        self.db.agenda_upsert("2026-07-27", tipo="reserva", ref_id="a", tema="A", titulo="Ta")
        self.db.agenda_upsert("2026-07-28", tipo="reserva", ref_id="b", tema="B", titulo="Tb")
        self.assertTrue(self.db.agenda_mover("2026-07-27", "2026-07-28"))
        self.assertEqual(self.db.agenda_slot("2026-07-27")["ref_id"], "b")
        self.assertEqual(self.db.agenda_slot("2026-07-28")["ref_id"], "a")

    def test_mover_recusa_destino_fixado(self):
        self.db.agenda_upsert("2026-07-27", tipo="reserva", ref_id="a", tema="A")
        self.db.agenda_upsert("2026-07-28", tipo="reserva", ref_id="b", tema="B", fixado=1)
        self.assertFalse(self.db.agenda_mover("2026-07-27", "2026-07-28"))
        self.assertEqual(self.db.agenda_slot("2026-07-28")["ref_id"], "b")

    def test_pular_devolve_e_marca(self):
        rid = self._reserva()
        self.db.marcar_reserva_agendado(rid)
        self.db.agenda_upsert("2026-07-27", tipo="reserva", ref_id=rid, tema="Obesidade")
        self.db.agenda_pular("2026-07-27", True)
        self.assertEqual(self.db.agenda_slot("2026-07-27")["tipo"], "pulado")
        self.assertEqual(self.db.contar_reserva_pronto(), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python3 -m pytest app/tests/test_agenda_db.py -q`
Expected: FAIL — `AttributeError: module 'db' has no attribute 'agenda_upsert'`.

- [ ] **Step 3a: Adicionar a tabela no `init()`**

Em `app/db.py`, dentro do `executescript` do `init()` (após o bloco `daily_drafts`, antes do `"""` de fechamento na ~linha 168), inserir:

```sql
            CREATE TABLE IF NOT EXISTS agenda (
                data TEXT PRIMARY KEY,
                tipo TEXT DEFAULT 'vazio',
                ref_id TEXT,
                payload TEXT,
                tema TEXT,
                titulo TEXT,
                fixado INTEGER DEFAULT 0,
                criado_em TEXT,
                atualizado_em TEXT
            );
```

E adicionar `"agenda"` ao final da lista `_TABELAS` (~linha 179) para o RLS do Postgres cobrir a tabela:

```python
_TABELAS = ["digests", "login_codes", "sessions", "subscribers",
            "pending_signups", "webhook_events", "cupons", "senha_tokens",
            "curadoria_candidatos", "reserva_resumos", "daily_drafts", "agenda"]
```

- [ ] **Step 3b: Adicionar as funções** (após `marcar_reserva_enviado`, ~linha 461)

```python
# ── Status da reserva p/ a agenda ──
def marcar_reserva_agendado(rid):
    """Tira o resumo da reserva 'pronto' e prende na agenda (não conta como estoque)."""
    with _conn() as c:
        c.execute("UPDATE reserva_resumos SET status='agendado' WHERE id=?", (rid,))


def marcar_reserva_pronto(rid):
    """Devolve o resumo agendado ao estoque 'pronto'."""
    with _conn() as c:
        c.execute("UPDATE reserva_resumos SET status='pronto' WHERE id=?", (rid,))


# ── Agenda (data -> estudo) ──
def agenda_slot(data):
    with _conn() as c:
        r = c.execute("SELECT * FROM agenda WHERE data=?", (data,)).fetchone()
    return dict(r) if r else None


def agenda_listar(desde, ate):
    with _conn() as c:
        rows = c.execute("SELECT * FROM agenda WHERE data BETWEEN ? AND ? ORDER BY data",
                         (desde, ate)).fetchall()
    return {r["data"]: dict(r) for r in rows}


def agenda_upsert(data, tipo="vazio", ref_id=None, payload=None, tema="", titulo="", fixado=0):
    from datetime import datetime
    now = datetime.now().isoformat()
    with _conn() as c:
        existe = c.execute("SELECT 1 FROM agenda WHERE data=?", (data,)).fetchone()
        if existe:
            c.execute("UPDATE agenda SET tipo=?, ref_id=?, payload=?, tema=?, titulo=?, "
                      "fixado=?, atualizado_em=? WHERE data=?",
                      (tipo, ref_id, payload, tema, titulo, int(fixado), now, data))
        else:
            c.execute("INSERT INTO agenda (data,tipo,ref_id,payload,tema,titulo,fixado,criado_em,atualizado_em) "
                      "VALUES (?,?,?,?,?,?,?,?,?)",
                      (data, tipo, ref_id, payload, tema, titulo, int(fixado), now, now))


def agenda_fixar(data, on=True):
    with _conn() as c:
        c.execute("UPDATE agenda SET fixado=? WHERE data=?", (1 if on else 0, data))


def agenda_devolver(data):
    """Tira o item do slot e devolve ao estoque; slot vira 'vazio'. Preserva 'fixado'."""
    s = agenda_slot(data)
    if not s:
        return
    if s.get("tipo") == "reserva" and s.get("ref_id"):
        marcar_reserva_pronto(s["ref_id"])
    elif s.get("tipo") == "fila" and s.get("payload"):
        try:
            import json
            import queue_store
            queue_store.devolver(json.loads(s["payload"]))
        except Exception as e:
            print(f"[agenda] devolver fila falhou: {e}", flush=True)
    agenda_upsert(data, tipo="vazio", fixado=s.get("fixado", 0))


def agenda_pular(data, on=True):
    """on=True: devolve item ao estoque e marca 'pulado'. on=False: volta a 'vazio'."""
    if on:
        agenda_devolver(data)
        agenda_upsert(data, tipo="pulado")
    else:
        agenda_upsert(data, tipo="vazio")


def _escrever_slot(data, s):
    if not s:
        agenda_upsert(data, tipo="vazio")
    else:
        agenda_upsert(data, tipo=s.get("tipo", "vazio"), ref_id=s.get("ref_id"),
                      payload=s.get("payload"), tema=s.get("tema", ""),
                      titulo=s.get("titulo", ""), fixado=s.get("fixado", 0))


def agenda_mover(data_orig, data_dest):
    """Troca (swap) os slots das duas datas. Retorna False se o destino está fixado."""
    a, b = agenda_slot(data_orig), agenda_slot(data_dest)
    if b and b.get("fixado"):
        return False
    _escrever_slot(data_orig, b)
    _escrever_slot(data_dest, a)
    return True
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python3 -m pytest app/tests/test_agenda_db.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add app/db.py app/tests/test_agenda_db.py
git commit -m "feat(agenda): tabela agenda + CRUD + status 'agendado' na reserva"
```

---

## Task 3: `queue_store` helpers + `materializar_agenda` (cola)

**Files:**
- Modify: `app/queue_store.py` (adicionar após `confirmar_envio`, ~linha 91)
- Modify: `app/daily.py` (adicionar `import agenda_plan`; novas funções após `reabastecer`, ~linha 67)
- Test: `app/tests/test_agenda_materializar.py`

**Interfaces:**
- Consumes: `agenda_plan.dias_uteis_desde`, `agenda_plan.planejar_agenda`, `agenda_plan.precisa_reabastecer`, `db.agenda_listar/agenda_upsert/marcar_reserva_agendado/listar_reserva/contar_reserva_pronto`, `queue_store.listar/remover/tamanho`.
- Produces:
  - `queue_store.listar() -> list[dict]`
  - `queue_store.remover(artigo: dict) -> None`
  - `queue_store.devolver(artigo: dict) -> None`
  - `daily.materializar_agenda(dias: int = 15) -> int` (quantos slots preencheu)
  - `daily._rotacao() -> list[str]`

- [ ] **Step 1: Escrever o teste que falha**

Criar `app/tests/test_agenda_materializar.py`:

```python
"""Teste da cola materializar_agenda: estoque temporário (SQLite + queue.json)."""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestMaterializar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ.pop("DATABASE_URL", None)
        import importlib
        import config as _cfg
        importlib.reload(_cfg)
        import db as _db
        importlib.reload(_db)
        import queue_store as _q
        importlib.reload(_q)
        import daily as _d
        importlib.reload(_d)
        self.db, self.q, self.daily = _db, _q, _d
        self.db.init()

    def _reserva(self, tema, titulo):
        return self.db.salvar_reserva({"tema": tema, "titulo_pt": titulo, "resumo": "r",
                                       "gancho": "", "grafico": "", "doi": "", "fonte": "NEJM",
                                       "url": "", "data": "2026-07-20"})

    def test_preenche_e_consome_estoque(self):
        for i in range(6):
            self._reserva("Obesidade", f"Estudo {i}")
        # desliga o reabastecimento de rede no teste
        self.daily.reabastecer = lambda: 0
        n = self.daily.materializar_agenda(dias=5)
        self.assertEqual(n, 5)
        # 5 viraram 'agendado', sobrou 1 pronto
        self.assertEqual(self.db.contar_reserva_pronto(), 1)
        amanha = datetime.now() + timedelta(days=1)
        import agenda_plan as ap
        datas = ap.dias_uteis_desde(amanha, 5, self.daily._dias_envio())
        for d in datas:
            self.assertEqual(self.db.agenda_slot(d)["tipo"], "reserva")

    def test_nao_mexe_em_dia_fixado(self):
        for i in range(5):
            self._reserva("Obesidade", f"E{i}")
        self.daily.reabastecer = lambda: 0
        import agenda_plan as ap
        amanha = datetime.now() + timedelta(days=1)
        d0 = ap.dias_uteis_desde(amanha, 1, self.daily._dias_envio())[0]
        self.db.agenda_upsert(d0, tipo="reserva", ref_id="fixo", tema="Longevidade", titulo="FIXO", fixado=1)
        self.daily.materializar_agenda(dias=5)
        self.assertEqual(self.db.agenda_slot(d0)["ref_id"], "fixo")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python3 -m pytest app/tests/test_agenda_materializar.py -q`
Expected: FAIL — `AttributeError: module 'daily' has no attribute 'materializar_agenda'`.

- [ ] **Step 3a: Helpers no `queue_store.py`** (após `confirmar_envio`)

```python
def listar():
    """Cópia da fila atual (leitura; não altera estado)."""
    return list(_load()["fila"])


def remover(artigo):
    """Remove o artigo (por chave) da fila — usado ao materializar na agenda."""
    d = _load()
    k = _chave(artigo)
    d["fila"] = [a for a in d["fila"] if _chave(a) != k]
    _save(d)


def devolver(artigo):
    """Recoloca um artigo na fila (ao desagendar/pular). Reordena por score. Não duplica."""
    d = _load()
    if _chave(artigo) in {_chave(a) for a in d["fila"]}:
        return
    d["fila"].append(artigo)
    d["fila"].sort(key=lambda x: x.get("score", 0), reverse=True)
    _save(d)
```

- [ ] **Step 3b: `materializar_agenda` no `daily.py`**

No topo do `daily.py`, adicionar aos imports: `import agenda_plan`.

Após `reabastecer()` (~linha 67), adicionar:

```python
def _rotacao():
    cfg = _cfg()
    rot = cfg.get("rotacao_semana")
    return rot if rot else list(cfg["temas"].keys())


def materializar_agenda(dias=15):
    """Preenche os próximos `dias` dias úteis vazios na agenda (rotação + variedade,
    reserva pronta antes de fila fresca). Reabastece se o estoque não cobre o horizonte.
    Retorna quantos slots foram preenchidos. Fail-safe: nunca derruba o envio."""
    import db
    import queue_store
    db.init()
    envio = _dias_envio()
    inicio = datetime.now() + timedelta(days=1)
    datas = agenda_plan.dias_uteis_desde(inicio, dias, envio)
    if not datas:
        return 0

    fila_n = queue_store.tamanho()
    reserva_n = db.contar_reserva_pronto()
    if agenda_plan.precisa_reabastecer(fila_n, reserva_n, dias):
        try:
            print(f"[agenda] estoque {fila_n+reserva_n}<{dias} — reabastecendo", flush=True)
            reabastecer()
        except Exception as e:
            print(f"[agenda] reabastecer falhou (segue): {e}", flush=True)

    slots = db.agenda_listar(datas[0], datas[-1])
    ordenados = []
    for d in datas:
        s = slots.get(d)
        if s and (s.get("fixado") or s.get("tipo") in ("reserva", "fila", "pulado")):
            tema = None if s.get("tipo") == "pulado" else s.get("tema")
            ordenados.append((d, tema, True))
        else:
            ordenados.append((d, None, False))

    cands = []
    for r in db.listar_reserva(status="pronto"):
        cands.append({"tipo": "reserva", "tema": r.get("tema", ""), "titulo": r.get("titulo_pt", ""),
                      "ref_id": r["id"], "payload": None})
    for a in queue_store.listar():
        cands.append({"tipo": "fila", "tema": a.get("tema", ""), "titulo": a.get("titulo", ""),
                      "ref_id": None, "payload": a})

    plano = agenda_plan.planejar_agenda(ordenados, cands, _rotacao(), None)
    for data, cand in plano.items():
        if cand["tipo"] == "reserva":
            db.marcar_reserva_agendado(cand["ref_id"])
            payload = None
        else:
            queue_store.remover(cand["payload"])
            payload = json.dumps(cand["payload"], ensure_ascii=False)
        db.agenda_upsert(data, tipo=cand["tipo"], ref_id=cand["ref_id"], payload=payload,
                         tema=cand["tema"], titulo=cand["titulo"], fixado=0)
    return len(plano)
```

(`json` já está importado no topo do `daily.py`.)

- [ ] **Step 4: Rodar e ver passar**

Run: `python3 -m pytest app/tests/test_agenda_materializar.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/queue_store.py app/daily.py app/tests/test_agenda_materializar.py
git commit -m "feat(agenda): materializar_agenda (cola estoque->plano->slots) + helpers da fila"
```

---

## Task 4: `preparar_18h` lê o slot com fallback

**Files:**
- Modify: `app/daily.py` (refatorar `_preparar_da_reserva` ~linha 117; refatorar `preparar_18h` ~linha 154; extrair `_preparar_de_artigo`)
- Test: `app/tests/test_agenda_plan.py` (já cobre `classificar_slot`; aqui adicionamos um teste de roteamento com dublês)

**Interfaces:**
- Consumes: `agenda_plan.classificar_slot`, `db.agenda_slot`, `materializar_agenda`.
- Produces:
  - `_preparar_da_reserva(reserva_id: str|None = None) -> dict|None` (id explícito; None mantém `db.proximo_da_reserva()`)
  - `_preparar_de_artigo(art: dict) -> dict|None` (gera conteúdo + rascunho a partir de um artigo cru)
  - `_preparar_fallback() -> dict|None` (corpo antigo: `queue_store.proximo()` → reserva)
  - `preparar_18h() -> dict|None` (agora lê o slot)

- [ ] **Step 1: Escrever o teste que falha** (roteamento por slot, com dublês)

Adicionar ao final de `app/tests/test_agenda_plan.py` (antes do `if __name__`):

```python
class TestPreparoRoteamento(unittest.TestCase):
    """preparar_18h escolhe a fonte certa a partir do slot (com dublês nas partes de I/O)."""
    def setUp(self):
        import os, tempfile
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
        self.db.init()
        self.chamadas = []
        # dublês: registram a fonte usada, sem tocar rede/IA/PDF
        self.daily.materializar_agenda = lambda dias=15: 0
        self.daily._preparar_da_reserva = lambda reserva_id=None: self.chamadas.append(("reserva", reserva_id))
        self.daily._preparar_de_artigo = lambda art: self.chamadas.append(("artigo", art.get("titulo")))
        self.daily._preparar_fallback = lambda: self.chamadas.append(("fallback", None))

    def _amanha_util(self):
        import agenda_plan as ap
        from datetime import datetime, timedelta
        return ap.dias_uteis_desde(datetime.now() + timedelta(days=1), 1, self.daily._dias_envio())[0]

    def test_slot_reserva(self):
        d = self._amanha_util()
        self.db.agenda_upsert(d, tipo="reserva", ref_id="rid-1", tema="Obesidade", titulo="T")
        self.daily.preparar_18h()
        self.assertEqual(self.chamadas, [("reserva", "rid-1")])

    def test_slot_pulado_nao_prepara(self):
        d = self._amanha_util()
        self.db.agenda_upsert(d, tipo="pulado")
        self.daily.preparar_18h()
        self.assertEqual(self.chamadas, [])

    def test_slot_vazio_cai_no_fallback(self):
        self.daily.preparar_18h()  # sem slot
        self.assertEqual(self.chamadas, [("fallback", None)])
```

> Nota: se `preparar_18h` pular por "amanhã não é dia útil", o teste roda num dia em que amanhã é útil. Como o horizonte é seg–sex, rodar o teste seg–qui garante amanhã útil. Para robustez, `_dias_envio` é lido no `setUp`; se amanhã não for útil, o teste de `pulado`/`reserva` ainda valida via `_amanha_util()` que devolve o próximo útil — mas `preparar_18h` só olha *amanhã*. Manter a suíte determinística: ver Step 3, `preparar_18h` recebe o parâmetro opcional `amanha` só nos testes.

- [ ] **Step 2: Rodar e ver falhar**

Run: `python3 -m pytest app/tests/test_agenda_plan.py::TestPreparoRoteamento -q`
Expected: FAIL (roteamento por slot ainda não existe; `preparar_18h` ignora a agenda).

- [ ] **Step 3: Refatorar `daily.py`**

**3a.** Trocar a assinatura de `_preparar_da_reserva` (~linha 117) para aceitar id explícito:

```python
def _preparar_da_reserva(reserva_id=None):
    """Monta o rascunho de amanhã a partir de um resumo PRONTO da reserva. Se
    `reserva_id` vier (slot da agenda), usa aquele; senão, o próximo da fila."""
    import db
    r_res = db.obter_reserva(reserva_id) if reserva_id else db.proximo_da_reserva()
    if not r_res:
        deliver.enviar_curador("📭 Sem estudo fresco E reserva vazia. Nada preparado p/ amanhã.")
        return None
    # ... (resto do corpo atual, inalterado)
```

Adicionar em `db.py` (junto das funções de reserva) o getter por id:

```python
def obter_reserva(rid):
    with _conn() as c:
        r = c.execute("SELECT * FROM reserva_resumos WHERE id=?", (rid,)).fetchone()
    return dict(r) if r else None
```

**3b.** Extrair o miolo "gera conteúdo + monta rascunho de um artigo cru" do `preparar_18h` atual para `_preparar_de_artigo`:

```python
def _preparar_de_artigo(art):
    """Gera conteúdo de um artigo cru (fila/fresco) e monta o rascunho de amanhã."""
    amanha = datetime.now() + timedelta(days=1)
    c = content.gerar_conteudo(art)
    alvo = amanha.strftime("%Y-%m-%d")
    os.makedirs(config.drafts_dir(), exist_ok=True)
    preview = os.path.join(config.drafts_dir(), f"{alvo}-preview.pdf")
    pdfmod.gerar_pdf(pdfmod.montar_html(art, c, _tema_meta(art.get("tema", ""))), preview)
    r = draft_store.novo_rascunho(alvo, art, c["resumo"], preview)
    r["gancho"] = c["gancho"]
    r["grafico"] = c["grafico"]
    r["titulo_pt"] = c["titulo_pt"]
    draft_store.salvar(r)
    link = f"{config.PUBLIC_URL}/revisar/{r['review_token']}"
    extra = "\n🎧 O áudio do estudo chega logo abaixo pra você escutar." if config.audio_ligado() else ""
    deliver.enviar_curador(f"📋 Amanhã · {art.get('tema','')}:\n*{c['titulo_pt']}*\n{art.get('fonte','')}\n"
                           f"Assinantes: {len(subscribers.ativos())}\n\n👉 Revisar/editar: {link}\n"
                           f"(se não mexer, envio automático às 08h){extra}")
    enviar_audio_preview(r)
    return r
```

**3c.** Criar `_preparar_fallback` com o comportamento atual (fila fresca → artigo → reserva):

```python
def _preparar_fallback():
    """Comportamento original: fila fresca (gera conteúdo) e, se vazia, reserva."""
    if queue_store.tamanho() < REFILL_MINIMO:
        print(f"[reabastecer] +{reabastecer()} na fila", flush=True)
    art = queue_store.proximo()
    if not art:
        return _preparar_da_reserva()
    return _preparar_de_artigo(art)
```

**3d.** Reescrever `preparar_18h` para ler o slot (com parâmetro opcional `amanha` só p/ teste determinístico):

```python
def preparar_18h(amanha=None):
    amanha = amanha or (datetime.now() + timedelta(days=1))
    if not _e_dia_util(amanha):
        print("[preparar] amanhã não é dia de envio — pulo", flush=True)
        return None
    try:
        materializar_agenda()
    except Exception as e:
        print(f"[preparar] materializar falhou (segue no fallback): {e}", flush=True)
    import db
    alvo = amanha.strftime("%Y-%m-%d")
    fonte, ref = agenda_plan.classificar_slot(db.agenda_slot(alvo))
    if fonte == "pulado":
        print("[preparar] amanhã marcado como PULADO na agenda — não preparo", flush=True)
        return None
    if fonte == "reserva":
        r = _preparar_da_reserva(reserva_id=ref)
        if r:
            return r
        print("[preparar] item da reserva sumiu — fallback", flush=True)
    elif fonte == "fila":
        try:
            r = _preparar_de_artigo(json.loads(ref))
            if r:
                return r
        except Exception as e:
            print(f"[preparar] slot de fila inválido — fallback: {e}", flush=True)
    return _preparar_fallback()
```

> No teste `TestPreparoRoteamento`, chamar `self.daily.preparar_18h(amanha=<datetime do dia útil>)`. Ajustar `_amanha_util` para devolver o `datetime` e o teste passar a data como objeto. Atualizar os 3 testes para: `from datetime import datetime; self.daily.preparar_18h(amanha=datetime.strptime(d, "%Y-%m-%d"))` onde `d` é `self._amanha_util()`.

- [ ] **Step 4: Rodar e ver passar**

Run: `python3 -m pytest app/tests/test_agenda_plan.py -q`
Expected: PASS (incluindo `TestPreparoRoteamento`).

- [ ] **Step 5: Rodar a suíte inteira (nada quebrou)**

Run: `python3 -m pytest app/tests/ -q`
Expected: PASS (todos os testes existentes + novos).

- [ ] **Step 6: Commit**

```bash
git add app/daily.py app/db.py app/tests/test_agenda_plan.py
git commit -m "feat(agenda): preparar_18h lê o slot da agenda com fallback pro fluxo atual"
```

---

## Task 5: Ajuste C — rotação padrão no `temas_config.json`

**Files:**
- Modify: `app/temas_config.json` (adicionar chave `rotacao_semana`)

**Interfaces:**
- Consumes: lido por `daily._rotacao()` (Task 3).
- Produces: chave `rotacao_semana` no config.

> O intake acumulativo (não perder os frescos da semana) já foi implementado na Task 3 via `precisa_reabastecer` + reabastecimento dentro de `materializar_agenda`. Esta task só fixa a rotação inicial visível.

- [ ] **Step 1: Adicionar a chave**

Em `app/temas_config.json`, no nível raiz (junto de `dias_envio`), adicionar:

```json
  "rotacao_semana": ["Obesidade", "Hormonal", "Longevidade", "Performance", "Lipedema"],
```

(Ordem-base seg→sex; o Diego reordena depois na tela. Ausência dessa chave faz `_rotacao()` cair na ordem de `temas`.)

- [ ] **Step 2: Validar o JSON**

Run: `python3 -c "import json; json.load(open('app/temas_config.json', encoding='utf-8')); print('json ok')"`
Expected: `json ok`

- [ ] **Step 3: Commit**

```bash
git add app/temas_config.json
git commit -m "feat(agenda): rotação-base seg-sex (rotacao_semana) editável na tela"
```

---

## Task 6: Painel `/agenda` (rota + página + ações)

**Files:**
- Modify: `app/serve.py` (GET: adicionar `if path.startswith("/agenda")` junto do bloco `/curadoria` ~linha 152; POST: adicionar `if path == "/agenda"` junto do POST `/curadoria` ~linha 315)
- Modify: `app/site_web.py` (adicionar `pagina_agenda(...)` após `pagina_curadoria` ~linha 791; item no `_admin_nav` ~linha 528)
- Test: `app/tests/test_agenda_plan.py` (testar `agrupar_por_semana`)

**Interfaces:**
- Consumes: `db.agenda_listar`, `db.agenda_mover/agenda_fixar/agenda_pular/agenda_devolver/agenda_upsert/marcar_reserva_agendado`, `db.listar_reserva`, `db.contar_reserva_pronto`, `queue_store.listar`, `daily.materializar_agenda`, `agenda_plan.dias_uteis_desde/agrupar_por_semana`, `site_web._pagina/_admin_nav/_esc`, `config.ADMIN_TOKEN`.
- Produces:
  - `site_web.pagina_agenda(semanas: list[list[dict]], estoque: int, token: str, msg: str = "") -> str`
  - Rotas `GET /agenda` e `POST /agenda`.

- [ ] **Step 1: Teste do agrupamento por semana** (pura, já em `agenda_plan`)

Adicionar ao `app/tests/test_agenda_plan.py`:

```python
class TestAgruparSemana(unittest.TestCase):
    def test_quebra_por_semana(self):
        slots = [{"data": "2026-07-27"}, {"data": "2026-07-31"},
                 {"data": "2026-08-03"}]  # seg/sex mesma semana; seg semana seguinte
        semanas = ap.agrupar_por_semana(slots)
        self.assertEqual(len(semanas), 2)
        self.assertEqual(len(semanas[0]), 2)
        self.assertEqual(len(semanas[1]), 1)
```

Run: `python3 -m pytest app/tests/test_agenda_plan.py::TestAgruparSemana -q`
Expected: PASS (a função `agrupar_por_semana` já foi criada na Task 1).

- [ ] **Step 2: `pagina_agenda` no `site_web.py`**

Adicionar após `pagina_curadoria` (~linha 791):

```python
_BADGE = {"reserva": "✓ pronto", "fila": "⏳ gera 18h", "pulado": "💤 folga", "vazio": "⚠️ vazio"}
_DIA_BR = {0: "seg", 1: "ter", 2: "qua", 3: "qui", 4: "sex", 5: "sáb", 6: "dom"}


def _slot_card(s, token, opcoes_html):
    """Card de um dia da agenda (com ações). `s` tem data/tipo/tema/titulo/fixado."""
    from datetime import datetime
    dt = datetime.strptime(s["data"], "%Y-%m-%d")
    dia = _DIA_BR[dt.weekday()]
    tipo = s.get("tipo") or "vazio"
    fixado = s.get("fixado")
    titulo = _esc(s.get("titulo") or "—")
    tema = _esc(s.get("tema") or "")
    badge = _BADGE.get(tipo, tipo)
    pino = "📌 " if fixado else ""
    def _acao(acao, label, extra=""):
        return (f'<form method="post" action="/agenda" style="display:inline">'
                f'<input type="hidden" name="token" value="{_esc(token)}">'
                f'<input type="hidden" name="acao" value="{acao}">'
                f'<input type="hidden" name="data" value="{s["data"]}">{extra}'
                f'<button class="mini">{label}</button></form>')
    mover = (f'<form method="post" action="/agenda" style="display:inline">'
             f'<input type="hidden" name="token" value="{_esc(token)}">'
             f'<input type="hidden" name="acao" value="mover">'
             f'<input type="hidden" name="data" value="{s["data"]}">'
             f'<select name="dest" class="mini"><option value="">mover p/…</option>{opcoes_html}</select>'
             f'<button class="mini">↔︎</button></form>')
    return (f'<div class="slot" draggable="true" data-data="{s["data"]}">'
            f'<div class="slot-h">{dia} · {s["data"][8:10]}/{s["data"][5:7]} '
            f'<span class="badge">{badge}</span></div>'
            f'<div class="slot-tema">{pino}{tema}</div>'
            f'<div class="slot-tit">{titulo}</div>'
            f'<div class="slot-acts">'
            f'{_acao("fixar" if not fixado else "desafixar", "📌" if not fixado else "soltar")}'
            f'{_acao("pular" if tipo != "pulado" else "despular", "💤" if tipo != "pulado" else "reativar")}'
            f'{mover}</div></div>')


def pagina_agenda(semanas, estoque, token, msg=""):
    opcoes = "".join(
        f'<option value="{s["data"]}">{s["data"][8:10]}/{s["data"][5:7]}</option>'
        for sem in semanas for s in sem)
    blocos = ""
    for i, sem in enumerate(semanas):
        cards = "".join(_slot_card(s, token, opcoes) for s in sem)
        blocos += f'<h3 class="sem-h">Semana {i+1}</h3><div class="sem-row">{cards}</div>'
    aviso = f'<div class="infobox">{_esc(msg)}</div>' if msg else ""
    rematerializar = (f'<form method="post" action="/agenda" style="display:inline">'
                      f'<input type="hidden" name="token" value="{_esc(token)}">'
                      f'<input type="hidden" name="acao" value="rematerializar">'
                      f'<button class="actbtn">↻ Rematerializar</button></form>')
    css = """<style>
    .sem-h{color:var(--ouro2);font-family:system-ui;font-size:13px;margin:18px 0 6px}
    .sem-row{display:flex;gap:10px;flex-wrap:wrap}
    .slot{flex:1;min-width:150px;background:rgba(255,255,255,.04);border:1px solid rgba(233,225,198,.14);
          border-radius:12px;padding:10px 12px;cursor:grab}
    .slot.dragover{border-color:var(--ouro)}
    .slot-h{font-family:system-ui;font-size:12px;color:var(--creme);opacity:.8;display:flex;justify-content:space-between;gap:6px}
    .badge{font-size:11px;opacity:.9}
    .slot-tema{font-size:13px;color:var(--ouro2);margin:4px 0 2px}
    .slot-tit{font-size:13px;color:var(--creme);line-height:1.3;min-height:34px}
    .slot-acts{display:flex;gap:4px;margin-top:8px;flex-wrap:wrap}
    button.mini,select.mini{font-family:system-ui;font-size:11px;padding:4px 7px;border-radius:8px;
          border:1px solid rgba(233,225,198,.2);background:rgba(0,0,0,.25);color:var(--creme);cursor:pointer}
    </style>"""
    js = """<script>
    (function(){
      let orig=null;
      document.querySelectorAll('.slot').forEach(function(el){
        el.addEventListener('dragstart',function(){orig=el.dataset.data;});
        el.addEventListener('dragover',function(e){e.preventDefault();el.classList.add('dragover');});
        el.addEventListener('dragleave',function(){el.classList.remove('dragover');});
        el.addEventListener('drop',function(e){
          e.preventDefault();el.classList.remove('dragover');
          var dest=el.dataset.data; if(!orig||orig===dest)return;
          var f=document.createElement('form'); f.method='post'; f.action='/agenda';
          f.innerHTML='<input name="token" value="'+TOKEN+'"><input name="acao" value="mover">'+
            '<input name="data" value="'+orig+'"><input name="dest" value="'+dest+'">';
          document.body.appendChild(f); f.submit();
        });
      });
    })();
    </script>"""
    corpo = (_admin_nav(token, "agenda") + css +
             f'<h2 class="disp" style="font-size:34px;color:var(--creme);margin:6px 0 4px">Agenda de envios</h2>'
             f'<p style="color:var(--creme);opacity:.75;font-size:13px">Arraste um dia sobre outro pra trocar. '
             f'Estoque pronto: <strong>{estoque}</strong>. {rematerializar}</p>'
             f'{aviso}{blocos}'
             + js.replace("TOKEN", '"' + _esc(token) + '"'))
    return _pagina("Agenda · Admin", corpo, logado=True,
                   meta_extra='<meta name="robots" content="noindex">')
```

Adicionar o link no `_admin_nav` (~linha 528): incluir uma aba `agenda` na lista de abas existente (seguir o padrão das outras abas do `_admin_nav`, com `href=f"/agenda?token={token}"` e rótulo "Agenda").

- [ ] **Step 3: Rotas no `serve.py`**

**GET** — junto do bloco `if path.startswith("/curadoria")` (~linha 152), adicionar antes dele:

```python
        if path.startswith("/agenda"):
            import config, db, daily, agenda_plan, site_web
            from datetime import datetime, timedelta
            if not config.ADMIN_TOKEN or g("token") != config.ADMIN_TOKEN:
                return self._html("<h3>Acesso negado</h3>", 403)
            db.init()
            try:
                daily.materializar_agenda()
            except Exception as e:
                print(f"[agenda] materializar no GET falhou: {e}", flush=True)
            datas = agenda_plan.dias_uteis_desde(datetime.now() + timedelta(days=1), 15, daily._dias_envio())
            mapa = db.agenda_listar(datas[0], datas[-1]) if datas else {}
            slots = [mapa.get(d, {"data": d, "tipo": "vazio", "tema": "", "titulo": "", "fixado": 0}) for d in datas]
            semanas = agenda_plan.agrupar_por_semana(slots)
            import urllib.parse as up
            msg = up.parse_qs(up.urlparse(self.path).query).get("msg", [""])[0]
            return self._html(site_web.pagina_agenda(semanas, db.contar_reserva_pronto(), config.ADMIN_TOKEN, msg))
```

**POST** — junto do bloco `if path == "/curadoria"` (~linha 315), adicionar:

```python
        if path == "/agenda":
            import config, db, daily
            import urllib.parse as up
            if not config.ADMIN_TOKEN or g("token") != config.ADMIN_TOKEN:
                return self._html("<h3>Acesso negado</h3>", 403)
            db.init()
            acao, data, msg = g("acao"), g("data"), ""
            if acao == "mover":
                ok = db.agenda_mover(data, g("dest"))
                msg = "Trocado." if ok else "Destino fixado — não trocado."
            elif acao == "fixar":
                db.agenda_fixar(data, True); msg = "Fixado."
            elif acao == "desafixar":
                db.agenda_fixar(data, False); msg = "Solto."
            elif acao == "pular":
                db.agenda_pular(data, True); msg = "Dia marcado como folga."
            elif acao == "despular":
                db.agenda_pular(data, False); msg = "Dia reativado."
            elif acao == "rematerializar":
                n = daily.materializar_agenda(); msg = f"{n} dia(s) preenchido(s)."
            return self._redirect(f"/agenda?token={config.ADMIN_TOKEN}&msg={up.quote(msg)}")
```

- [ ] **Step 4: Smoke test manual local**

Run:
```bash
cd app && DSCURSO_DATA=/tmp/ag DSCURSO_ARTIGOS_DB=/tmp/ag/t.db DSCURSO_ADMIN_TOKEN=x \
  python3 -c "import os; os.makedirs('/tmp/ag',exist_ok=True); import db,daily,agenda_plan,site_web; \
db.init(); \
[db.salvar_reserva({'tema':'Obesidade','titulo_pt':f'E{i}','resumo':'r','gancho':'','grafico':'','doi':'','fonte':'NEJM','url':'','data':'2026-07-20'}) for i in range(8)]; \
daily.reabastecer=lambda:0; daily.materializar_agenda(dias=15); \
from datetime import datetime,timedelta; \
datas=agenda_plan.dias_uteis_desde(datetime.now()+timedelta(days=1),15,daily._dias_envio()); \
m=db.agenda_listar(datas[0],datas[-1]); slots=[m.get(d,{'data':d,'tipo':'vazio','tema':'','titulo':'','fixado':0}) for d in datas]; \
html=site_web.pagina_agenda(agenda_plan.agrupar_por_semana(slots), db.contar_reserva_pronto(),'x'); \
assert 'Agenda de envios' in html and 'slot' in html; print('render ok, len',len(html))"
```
Expected: `render ok, len <n>`

- [ ] **Step 5: Rodar a suíte inteira**

Run: `python3 -m pytest app/tests/ -q`
Expected: PASS (todos).

- [ ] **Step 6: Commit**

```bash
git add app/serve.py app/site_web.py app/tests/test_agenda_plan.py
git commit -m "feat(agenda): painel /agenda (grade 3 semanas, arrastar-e-soltar, fixar/pular/mover)"
```

---

## Self-Review

**1. Spec coverage:**
- §4 Modelo de dados → Task 2 (tabela + colunas + invariante `agendado`). ✔
- §5 Materializador (pura + orquestração) → Task 1 (`planejar_agenda`) + Task 3 (`materializar_agenda`). ✔
- §6 Integração 18h com fallback → Task 4. ✔
- §7 Painel `/agenda` (DnD + fallback + ações) → Task 6. ✔
- §8 Ajuste C (intake acumulativo) → Task 3 (`precisa_reabastecer` + reabastecer no horizonte) + Task 5 (rotação). ✔
- §9 Erros/bordas → Task 4 (fallback slot inválido), Task 2 (mover recusa fixado), Task 3 (reabastecer fail-safe). ✔
- §10 Testes → Tasks 1/2/3/4/6. ✔
- §11 Arquivos → todos cobertos; `queue.json` em `/data` confirmado. ✔

**2. Placeholder scan:** Sem "TBD/TODO"; todo passo de código traz o código. A única prosa não-código é a nota de determinismo do teste no Task 4 (justificada e acionável via parâmetro `amanha`). ✔

**3. Type consistency:** `planejar_agenda` devolve candidatos `{"tipo","tema","titulo","ref_id","payload"}`; `materializar_agenda` consome exatamente esses campos; `agenda_upsert` recebe `tipo/ref_id/payload/tema/titulo/fixado` idênticos; `classificar_slot` devolve `("reserva", ref_id)` / `("fila", payload)` e `preparar_18h` trata `ref` como id (reserva) e como JSON string (fila) — consistente com `agenda_upsert(payload=json.dumps(...))`. ✔

---

## Execution Handoff

Ver mensagem do assistente após salvar o plano.
</content>
</invoke>
