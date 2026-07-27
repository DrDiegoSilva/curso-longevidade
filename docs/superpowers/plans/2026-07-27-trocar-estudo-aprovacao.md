# Trocar o estudo de amanhã na aprovação (Item 23) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar na tela de revisão das 18h um botão "🔁 Trocar por outro estudo" que abre um picker (reserva + candidatos), e ao escolher, refaz o rascunho de amanhã a partir do escolhido de forma assíncrona (novo resumo chega no WhatsApp), devolvendo o recusado ao pool.

**Architecture:** Toda a lógica vive em `daily.py` (montar lista, validar, orquestrar troca) e `review_web.py` (HTML puro). O `serve.py` é só glue fino sobre funções testadas. Reusa `daily._preparar_de_candidato`/`_preparar_da_reserva` (já testados) pra refazer o rascunho. **Não toca agenda/rotação** (área do outro agente).

**Tech Stack:** Python 3 stdlib (`unittest`, `threading`, `html`), sqlite via `db.py`. Sem dependências novas.

## Global Constraints

- **NÃO tocar** em agenda/rotação: `agenda_plan.planejar_agenda`/`_rank`/`materializar_agenda`, `temas_config.json`. Só chamar `_preparar_*` e ler `db.listar_*`. (verbatim da spec)
- **Assíncrono:** a geração roda em `threading.Thread(..., daemon=True)`; o POST responde na hora.
- **HTML sempre escapado** (`html.escape`) — conteúdo vem do banco.
- **Reusar** `daily._preparar_de_candidato(cand_id)` e `daily._preparar_da_reserva(reserva_id=...)` — não reimplementar preparo.
- **Base:** worktree `feat/trocar-estudo-aprovacao` em `6b72d25`. Rodar testes de `app/`: `python3 -m unittest discover -s tests`.
- **Sem push/deploy** neste plano — o deploy é sequenciado depois que o worktree `agenda-tema` aterrissar.
- Ids de reserva/candidato são **strings**; o form manda string; comparar como string.

## File Structure

- `app/daily.py` — **modificar**: + `montar_alternativas(r)`, `alternativa_valida(r, tipo, cid)`, `trocar_estudo_amanha(token, tipo, cid)`, const `ALTERNATIVAS_MAX`.
- `app/review_web.py` — **modificar**: + botão em `pagina_revisao`; + `pagina_trocar_estudo(alternativas, r, token)`; + `pagina_trocando()`.
- `app/serve.py` — **modificar**: no POST `/revisar/<tok>`, tratar `acao=="trocar"` e `acao=="trocar_confirmar"` antes do `aplicar` genérico.
- `app/tests/test_trocar_estudo.py` — **criar**: testes de `daily` + `review_web`.

---

### Task 1: `montar_alternativas` + `alternativa_valida` (daily)

**Files:**
- Modify: `app/daily.py` (adicionar funções + const, perto das `_preparar_*`)
- Test: `app/tests/test_trocar_estudo.py`

**Interfaces:**
- Produces:
  - `montar_alternativas(r: dict) -> list[dict]` — cada item `{"tipo": "reserva"|"candidato", "id": str, "titulo": str, "fonte": str, "tema": str, "score": float}`. Exclui o estudo atual (via `r["reserva_id"]`/`r["candidato_id"]`), reserva primeiro (prioridade desc, score desc), depois candidatos (tema de amanhã = `r["artigo"]["tema"]` primeiro, score desc), corta em `ALTERNATIVAS_MAX`.
  - `alternativa_valida(r, tipo, cid) -> bool`.
- Consumes (existentes): `db.listar_reserva(status)`, `db.listar_candidatos(status)`.

- [ ] **Step 1: Write the failing test**

Criar `app/tests/test_trocar_estudo.py`:

```python
"""Item 23 — trocar o estudo de amanhã na tela de aprovação."""
import importlib
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DSCURSO_DATA", tempfile.mkdtemp())


class TestMontarAlternativas(unittest.TestCase):
    def setUp(self):
        import daily
        importlib.reload(daily)
        self.daily = daily

    def _db(self, reserva, candidatos):
        import db
        return (mock.patch.object(db, "listar_reserva", return_value=reserva),
                mock.patch.object(db, "listar_candidatos", return_value=candidatos))

    def test_reserva_primeiro_e_exclui_atual_e_ordena(self):
        daily = self.daily
        r = {"reserva_id": "res_atual", "candidato_id": None,
             "artigo": {"tema": "Obesidade"}}
        reserva = [
            {"id": "res_atual", "titulo_pt": "Atual", "fonte": "X", "tema": "Obesidade", "prioridade": 0, "score": 9},
            {"id": "res_up", "titulo_pt": "Meu upload", "fonte": "NEJM", "tema": "Obesidade", "prioridade": 1, "score": 2},
            {"id": "res_b", "titulo_pt": "Reserva B", "fonte": "Lancet", "tema": "Hormonal", "prioridade": 0, "score": 5},
        ]
        candidatos = [
            {"id": "c_horm", "titulo": "Cand Hormonal", "fonte": "JCEM", "tema": "Hormonal", "score": 8},
            {"id": "c_obe", "titulo": "Cand Obesidade", "fonte": "Obesity", "tema": "Obesidade", "score": 3},
        ]
        p1, p2 = self._db(reserva, candidatos)
        with p1, p2:
            alts = daily.montar_alternativas(r)
        ids = [(a["tipo"], a["id"]) for a in alts]
        # atual excluído; uploads/reserva no topo (prioridade=1 primeiro, depois score);
        # candidatos depois com tema de amanhã (Obesidade) na frente do Hormonal
        self.assertEqual(ids, [
            ("reserva", "res_up"), ("reserva", "res_b"),
            ("candidato", "c_obe"), ("candidato", "c_horm"),
        ])
        self.assertEqual(alts[0]["titulo"], "Meu upload")

    def test_exclui_candidato_atual_e_normaliza(self):
        daily = self.daily
        r = {"reserva_id": None, "candidato_id": "c_atual", "artigo": {"tema": "Performance"}}
        candidatos = [
            {"id": "c_atual", "titulo": "Atual", "fonte": "X", "tema": "Performance", "score": 5},
            {"id": "c_ok", "titulo": "Outro", "fonte": "Sports Med", "tema": "Performance", "score": 7},
        ]
        p1, p2 = self._db([], candidatos)
        with p1, p2:
            alts = daily.montar_alternativas(r)
        self.assertEqual([a["id"] for a in alts], ["c_ok"])
        self.assertEqual(alts[0], {"tipo": "candidato", "id": "c_ok",
                                   "titulo": "Outro", "fonte": "Sports Med",
                                   "tema": "Performance", "score": 7})

    def test_alternativa_valida(self):
        daily = self.daily
        r = {"reserva_id": None, "candidato_id": None, "artigo": {"tema": "Obesidade"}}
        p1, p2 = self._db([{"id": "res1", "titulo_pt": "R", "fonte": "", "tema": "Obesidade", "prioridade": 0, "score": 1}], [])
        with p1, p2:
            self.assertTrue(daily.alternativa_valida(r, "reserva", "res1"))
            self.assertFalse(daily.alternativa_valida(r, "candidato", "res1"))
            self.assertFalse(daily.alternativa_valida(r, "reserva", "nope"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_trocar_estudo.TestMontarAlternativas -v`
Expected: FAIL com `AttributeError: module 'daily' has no attribute 'montar_alternativas'`.

- [ ] **Step 3: Write minimal implementation**

Em `app/daily.py`, logo acima de `def _preparar_fallback():` (perto das `_preparar_*`), adicionar:

```python
ALTERNATIVAS_MAX = 20


def montar_alternativas(r):
    """Lista de estudos p/ trocar o de amanhã: reserva (uploads no topo) + candidatos
    (tema de amanhã primeiro). Exclui o estudo atual. Normalizado e cortado em ALTERNATIVAS_MAX."""
    import db
    atual_res = r.get("reserva_id")
    atual_cand = r.get("candidato_id")
    tema_amanha = (r.get("artigo") or {}).get("tema", "")
    res_rows = [x for x in db.listar_reserva("pronto") if x["id"] != atual_res]
    res_rows.sort(key=lambda x: (x.get("prioridade", 0) or 0, x.get("score", 0) or 0), reverse=True)
    cand_rows = [x for x in db.listar_candidatos("novo") if x["id"] != atual_cand]
    cand_rows.sort(key=lambda x: (1 if x.get("tema") == tema_amanha else 0, x.get("score", 0) or 0), reverse=True)
    alts = (
        [{"tipo": "reserva", "id": x["id"], "titulo": x.get("titulo_pt", ""),
          "fonte": x.get("fonte", ""), "tema": x.get("tema", ""), "score": x.get("score", 0) or 0}
         for x in res_rows]
        + [{"tipo": "candidato", "id": x["id"], "titulo": x.get("titulo", ""),
            "fonte": x.get("fonte", ""), "tema": x.get("tema", ""), "score": x.get("score", 0) or 0}
           for x in cand_rows]
    )
    return alts[:ALTERNATIVAS_MAX]


def alternativa_valida(r, tipo, cid):
    """True se (tipo,cid) está entre as alternativas atuais (não confia no form)."""
    return any(a["tipo"] == tipo and str(a["id"]) == str(cid) for a in montar_alternativas(r))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_trocar_estudo.TestMontarAlternativas -v`
Expected: PASS (3 testes).

- [ ] **Step 5: Commit**

```bash
git add app/daily.py app/tests/test_trocar_estudo.py
git commit -m "feat(trocar): montar_alternativas + alternativa_valida (reserva no topo, tema de amanhã primeiro)"
```

---

### Task 2: `trocar_estudo_amanha` (orquestração async)

**Files:**
- Modify: `app/daily.py` (adicionar `trocar_estudo_amanha` abaixo de `alternativa_valida`)
- Test: `app/tests/test_trocar_estudo.py` (nova classe)

**Interfaces:**
- Produces: `trocar_estudo_amanha(token: str, tipo: str, cid: str) -> dict | None` — devolve o estudo atual ao pool (candidato→`novo`) e refaz o rascunho de amanhã do escolhido via `_preparar_de_candidato`/`_preparar_da_reserva`. Roda em thread (chamado pelo serve).
- Consumes: `draft_store.por_token`, `db.marcar_candidato_pronto`, `_preparar_de_candidato`, `_preparar_da_reserva`, `deliver.enviar_curador`.

- [ ] **Step 1: Write the failing test**

Adicionar em `app/tests/test_trocar_estudo.py`:

```python
class TestTrocarEstudoAmanha(unittest.TestCase):
    def setUp(self):
        import daily
        importlib.reload(daily)
        self.daily = daily

    def test_candidato_atual_volta_ao_pool_e_prepara_escolhido(self):
        daily = self.daily
        import db
        r = {"candidato_id": "c_velho", "data": "2026-07-28", "artigo": {"tema": "Obesidade"}}
        with mock.patch.object(daily.draft_store, "por_token", return_value=r), \
             mock.patch.object(db, "marcar_candidato_pronto") as m_pool, \
             mock.patch.object(daily, "_preparar_da_reserva", return_value={"review_token": "novo"}) as m_res, \
             mock.patch.object(daily, "_preparar_de_candidato") as m_cand, \
             mock.patch.object(daily.deliver, "enviar_curador") as m_cur:
            out = daily.trocar_estudo_amanha("tok", "reserva", "res_escolhida")
        m_pool.assert_called_once_with("c_velho")          # devolveu o candidato atual ao pool
        m_res.assert_called_once_with(reserva_id="res_escolhida")  # preparou o escolhido (reserva)
        m_cand.assert_not_called()
        m_cur.assert_not_called()                          # sucesso: sem aviso de falha
        self.assertEqual(out["review_token"], "novo")

    def test_reserva_atual_nao_e_descartada(self):
        daily = self.daily
        import db
        r = {"reserva_id": "res_velha", "data": "2026-07-28", "artigo": {"tema": "Obesidade"}}
        with mock.patch.object(daily.draft_store, "por_token", return_value=r), \
             mock.patch.object(db, "marcar_candidato_pronto") as m_pool, \
             mock.patch.object(daily, "_preparar_de_candidato", return_value={"review_token": "n"}) as m_cand, \
             mock.patch.object(daily, "_preparar_da_reserva"), \
             mock.patch.object(daily.deliver, "enviar_curador"):
            daily.trocar_estudo_amanha("tok", "candidato", "c_escolhido")
        m_pool.assert_not_called()                         # reserva atual segue 'pronto' (reusável)
        m_cand.assert_called_once_with("c_escolhido")

    def test_preparo_falha_avisa_curador(self):
        daily = self.daily
        import db
        r = {"candidato_id": "c_velho", "data": "2026-07-28", "artigo": {"tema": "Obesidade"}}
        with mock.patch.object(daily.draft_store, "por_token", return_value=r), \
             mock.patch.object(db, "marcar_candidato_pronto"), \
             mock.patch.object(daily, "_preparar_da_reserva", side_effect=RuntimeError("boom")), \
             mock.patch.object(daily.deliver, "enviar_curador") as m_cur:
            out = daily.trocar_estudo_amanha("tok", "reserva", "res_x")
        self.assertIsNone(out)
        m_cur.assert_called_once()                         # avisou que a troca falhou
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_trocar_estudo.TestTrocarEstudoAmanha -v`
Expected: FAIL com `AttributeError: module 'daily' has no attribute 'trocar_estudo_amanha'`.

- [ ] **Step 3: Write minimal implementation**

Em `app/daily.py`, abaixo de `alternativa_valida`:

```python
def trocar_estudo_amanha(token, tipo, cid):
    """Refaz o rascunho de amanhã a partir do estudo escolhido (roda em thread).
    Devolve o estudo atual ao pool. Fail-safe: exceção -> avisa o curador, o rascunho antigo fica."""
    import db
    r = draft_store.por_token(token)
    if not r:
        deliver.enviar_curador("⚠️ Não consegui trocar o estudo (rascunho não encontrado).")
        return None
    if r.get("candidato_id"):                 # candidato atual volta pro pool; reserva/clássico ficam
        try:
            db.marcar_candidato_pronto(r["candidato_id"])
        except Exception as e:
            print(f"[trocar] devolver candidato ao pool falhou (segue): {e}", flush=True)
    try:
        if tipo == "reserva":
            novo = _preparar_da_reserva(reserva_id=cid)
        elif tipo == "candidato":
            novo = _preparar_de_candidato(cid)
        else:
            novo = None
    except Exception as e:
        print(f"[trocar] preparo do escolhido falhou: {e}", flush=True)
        novo = None
    if not novo:
        deliver.enviar_curador("⚠️ Não consegui trocar o estudo; o anterior segue valendo.")
    return novo
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_trocar_estudo.TestTrocarEstudoAmanha -v`
Expected: PASS (3 testes).

- [ ] **Step 5: Commit**

```bash
git add app/daily.py app/tests/test_trocar_estudo.py
git commit -m "feat(trocar): trocar_estudo_amanha — devolve ao pool + reusa _preparar_* (async, fail-safe)"
```

---

### Task 3: HTML — botão + picker + página "Trocando" (review_web)

**Files:**
- Modify: `app/review_web.py` (`pagina_revisao` + 2 funções novas)
- Test: `app/tests/test_trocar_estudo.py` (nova classe)

**Interfaces:**
- Produces:
  - `pagina_trocar_estudo(alternativas: list[dict], r: dict, token: str) -> str`
  - `pagina_trocando() -> str`
  - `pagina_revisao` passa a conter `<button name="acao" value="trocar">`.
- Consumes: nada novo (HTML puro).

- [ ] **Step 1: Write the failing test**

Adicionar em `app/tests/test_trocar_estudo.py`:

```python
class TestReviewWebTrocar(unittest.TestCase):
    def test_pagina_revisao_tem_botao_trocar(self):
        import review_web
        html = review_web.pagina_revisao({"artigo": {"titulo": "T"}, "data": "2026-07-28",
                                          "resumo": "x", "review_token": "tok"})
        self.assertIn('value="trocar"', html)
        self.assertIn("🔁", html)

    def test_pagina_trocar_lista_e_escapa(self):
        import review_web
        alts = [{"tipo": "reserva", "id": "res1", "titulo": "T <b>x</b>",
                 "fonte": "NEJM", "tema": "Obesidade", "score": 9}]
        r = {"artigo": {"titulo": "Atual"}}
        html = review_web.pagina_trocar_estudo(alts, r, "tok")
        self.assertIn("T &lt;b&gt;x&lt;/b&gt;", html)          # título escapado
        self.assertIn('value="trocar_confirmar"', html)
        self.assertIn('name="tipo" value="reserva"', html)
        self.assertIn('name="id" value="res1"', html)
        self.assertIn("/revisar/tok", html)                    # form + voltar

    def test_pagina_trocar_vazio(self):
        import review_web
        html = review_web.pagina_trocar_estudo([], {"artigo": {"titulo": "Atual"}}, "tok")
        self.assertIn("Sem outros estudos", html)

    def test_pagina_trocando(self):
        import review_web
        self.assertIn("Trocando", review_web.pagina_trocando())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_trocar_estudo.TestReviewWebTrocar -v`
Expected: FAIL — `pagina_revisao` sem `value="trocar"` e `AttributeError` em `pagina_trocar_estudo`/`pagina_trocando`.

- [ ] **Step 3: Write minimal implementation**

Em `app/review_web.py`, na `pagina_revisao`, trocar a linha do botão "Não enviar hoje" por (adiciona o botão de trocar logo depois):

```python
{btn_audio}  <button name="acao" value="nao_enviar">🚫 Não enviar hoje</button>
  <button name="acao" value="trocar">🔁 Trocar por outro estudo</button>
```

E adicionar as duas funções ao final do arquivo:

```python
def pagina_trocar_estudo(alternativas, r, token):
    esc = _html.escape
    tok = esc(token)
    atual = esc((r.get("artigo") or {}).get("titulo", ""))
    if not alternativas:
        corpo = "<p>Sem outros estudos disponíveis para trocar agora.</p>"
    else:
        itens = "".join(
            f'<li style="margin:12px 0">'
            f'<form method="post" action="/revisar/{tok}" '
            f'style="display:flex;gap:10px;align-items:center;justify-content:space-between">'
            f'<span><b>{esc(a["titulo"])}</b><br>'
            f'<small style="color:#6b7a76">{esc(a["tema"])} · {esc(a["fonte"])} · '
            f'nota {esc(str(a["score"]))} · {esc(a["tipo"])}</small></span>'
            f'<input type="hidden" name="acao" value="trocar_confirmar">'
            f'<input type="hidden" name="tipo" value="{esc(a["tipo"])}">'
            f'<input type="hidden" name="id" value="{esc(str(a["id"]))}">'
            f'<button type="submit">Usar este amanhã</button>'
            f'</form></li>'
            for a in alternativas
        )
        corpo = f'<ul style="list-style:none;padding:0">{itens}</ul>'
    return f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<body style="font-family:system-ui;max-width:680px;margin:24px auto;padding:0 16px;color:#1a2b28">
<div style="color:#0f4c3a;font-weight:600">Trocar o estudo de amanhã</div>
<p style="color:#6b7a76;font-size:14px">Atual: {atual}. Escolha outro — o resumo novo chega no seu WhatsApp em ~1-2 min, com link de revisão novo.</p>
{corpo}
<p style="margin-top:16px"><a href="/revisar/{tok}">← Voltar para a revisão</a></p>
</body>"""


def pagina_trocando():
    return ('<!doctype html><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<body style="font-family:system-ui;max-width:600px;margin:40px auto;padding:0 16px;color:#1a2b28">'
            '<h3>🔄 Trocando…</h3>'
            '<p>O novo resumo está sendo gerado. Em ~1-2 min você recebe no WhatsApp o estudo novo '
            '(com PDF, áudio e um link de revisão novo). Pode fechar esta página.</p></body>')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_trocar_estudo.TestReviewWebTrocar -v`
Expected: PASS (4 testes).

- [ ] **Step 5: Commit**

```bash
git add app/review_web.py app/tests/test_trocar_estudo.py
git commit -m "feat(trocar): botão na revisão + página de picker + página 'Trocando'"
```

---

### Task 4: Wire no serve.py + regressão

**Files:**
- Modify: `app/serve.py` (POST `/revisar/<tok>`, ~linha 479-493)

**Interfaces:**
- Consumes: `daily.montar_alternativas`, `daily.alternativa_valida`, `daily.trocar_estudo_amanha`, `review_web.pagina_trocar_estudo`, `review_web.pagina_trocando`, `review_web.pagina_revisao`.
- Produces: nada (glue de HTTP; não unit-testado, seguindo a convenção do repo — coberto por smoke manual + regressão da suíte).

- [ ] **Step 1: Implementar o wiring**

Em `app/serve.py`, no bloco `if path.startswith("/revisar/"):` do `do_POST`, **antes** da linha `draft_store.aplicar(r["data"], g("acao"), g("texto"))`, adicionar:

```python
            if g("acao") == "trocar":
                import daily
                return self._html(review_web.pagina_trocar_estudo(
                    daily.montar_alternativas(r), r, tok))
            if g("acao") == "trocar_confirmar":
                import daily, threading
                tipo, cid = g("tipo"), g("id")
                if not daily.alternativa_valida(r, tipo, cid):
                    return self._html(review_web.pagina_revisao(
                        r, aviso="Esse estudo saiu da lista — escolha outro.",
                        audio_on=config.audio_ligado()))
                threading.Thread(target=daily.trocar_estudo_amanha,
                                 args=(tok, tipo, cid), daemon=True).start()
                return self._html(review_web.pagina_trocando())
```

(O bloco `if path.startswith("/revisar/"):` já faz `import config, draft_store, review_web` e define `tok`/`r`.)

- [ ] **Step 2: Rodar a suíte inteira (regressão)**

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -5`
Expected: `OK` — baseline 703 + os novos testes (todos verdes). Nenhuma regressão em aprovar/editar/nao_enviar/regerar_audio.

- [ ] **Step 3: Smoke manual (documentar, não bloqueia)**

Checklist a verificar quando o build subir (não roda aqui — precisa do servidor):
1. `/revisar/<token>` mostra o botão "🔁 Trocar por outro estudo".
2. Clicar → lista de alternativas (reserva no topo, tema de amanhã priorizado nos candidatos), sem o estudo atual.
3. "Usar este amanhã" → página "🔄 Trocando…" na hora; em ~1-2 min chega no WhatsApp o novo resumo + PDF + áudio + link de revisão novo.
4. O estudo recusado volta pro pool (candidato reaparece em Triagem; reserva segue disponível).
5. Aprovar/editar/nao_enviar/regerar_audio seguem funcionando.

- [ ] **Step 4: Commit**

```bash
git add app/serve.py
git commit -m "feat(trocar): wire /revisar POST (trocar/trocar_confirmar) — picker + troca async"
```

---

## Notas de execução

- **Não fazer push nem deploy.** O deploy é sequenciado: só depois que o worktree `agenda-tema` (feat/agenda-tema-por-dia) aterrissar na main, pra evitar clobber. Ao integrar, conferir conflitos em `serve.py`/`daily.py` (a curadoria já está na base; o `agenda-tema` mexe em agenda — regiões diferentes das minhas, mas conferir).
- **Showcase da retatrutida** independe deste plano: upload em `/curadoria` já gera o resumo (SYS_ESTUDO) + PDF hoje.
