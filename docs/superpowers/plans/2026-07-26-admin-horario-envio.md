# Admin ver/trocar horário de envio — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Na tela de Assinantes do admin, mostrar a distribuição por horário (resumo) e uma coluna "Horário" por linha pra trocar o slot do assinante (admin fura o teto; catch-up reusa a lógica do /meus-dados).

**Architecture:** UI em `site_web.pagina_admin` (param `contagem_slots`, resumo, coluna com `<select>` de todos os `config.SLOTS`); handler em `serve.py` (`acao=definir_slot`) chama `subscribers.definir_slot` (sem teto) e, se o novo slot já disparou hoje, `daily.enviar_catch_up` (protegido pelo claim `envios_dia`). GET passa `subscribers.contar_por_slot()`.

**Tech Stack:** Python stdlib, unittest. Sem dependências novas.

## Global Constraints

- **Admin fura o teto:** o `<select>` oferece TODOS os `config.SLOTS`; `subscribers.definir_slot` já valida só slot ∈ SLOTS (não checa teto). Não mexer em `definir_slot` nem no teto.
- **Não mexer** no `/meus-dados`, em `daily.enviar_catch_up`, nem em `subscribers`.
- **Catch-up seguro:** só chamar `enviar_catch_up` quando `db.slot_ja_enviou(hoje, novo)`; o claim `envios_dia` (dentro do catch-up) garante que quem já recebeu hoje não recebe de novo.
- Estilo: f-strings, imports lazy, sem libs novas. Commits em PT, sem trailer de atribuição.
- Rodar testes: `cd app && python3 -m unittest discover -s tests`.
- Branch: `feat/admin-horario` (spec já commitado: `ab6d0b3`).

---

### Task 1: UI — resumo + coluna "Horário" em `pagina_admin`

**Files:**
- Modify: `app/site_web.py` — `pagina_admin` (assinatura em ~843; row/thead/colspan em ~914-958). Ancore pelos STRINGS abaixo (não por número de linha).
- Test: `app/tests/test_admin_horario_ui.py` (novo)

**Interfaces:**
- Produces: `pagina_admin(assinantes, token="", cupons=None, confirmar_id=None, erro="", reenviar_id=None, sucesso="", contagem_slots=None) -> str`. Em `contagem_slots` presente → renderiza o resumo; cada linha ganha `<select name="slot">` com todos os `config.SLOTS` (atual via `subscribers.slot_de`) postando `acao=definir_slot`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `app/tests/test_admin_horario_ui.py`:

```python
"""Testes de render da coluna/resumo de horário no admin. Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAdminHorarioUI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import site_web as _sw
        importlib.reload(_sw)
        self.sw = _sw

    def _sub(self, **kw):
        base = {"id": 7, "nome": "X", "whatsapp": "5544999998888",
                "email": "", "plano": "mensal", "status": "ATIVO", "slot_envio": "12h"}
        base.update(kw)
        return base

    def _cont(self, **kw):
        base = {"07h": 0, "08h": 0, "12h": 0, "18h": 0, "20h": 0}
        base.update(kw)
        return base

    def test_coluna_horario_select_com_todos_e_atual(self):
        html = self.sw.pagina_admin([self._sub(slot_envio="12h")], token="tk",
                                     contagem_slots=self._cont(**{"12h": 1}))
        self.assertIn('name="acao" value="definir_slot"', html)
        self.assertIn('<option value="07h"', html)     # oferece todos os slots
        self.assertIn('<option value="20h"', html)
        self.assertIn('<option value="12h" selected', html)   # atual selecionado

    def test_resumo_por_horario(self):
        html = self.sw.pagina_admin([self._sub()], token="tk",
                                     contagem_slots=self._cont(**{"08h": 12}))
        self.assertIn("08h: 12", html)

    def test_sub_sem_slot_usa_default(self):
        html = self.sw.pagina_admin([self._sub(slot_envio=None)], token="tk",
                                     contagem_slots=self._cont())
        self.assertIn('<option value="08h" selected', html)   # SLOT_DEFAULT


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd app && python3 -m unittest tests.test_admin_horario_ui -v`
Expected: FAIL — `TypeError: pagina_admin() got an unexpected keyword argument 'contagem_slots'`.

- [ ] **Step 3: Adicionar o param na assinatura**

Trocar (em `app/site_web.py`):
```python
def pagina_admin(assinantes, token="", cupons=None, confirmar_id=None, erro="",
                 reenviar_id=None, sucesso=""):
```
por:
```python
def pagina_admin(assinantes, token="", cupons=None, confirmar_id=None, erro="",
                 reenviar_id=None, sucesso="", contagem_slots=None):
```

- [ ] **Step 4: Adicionar a célula `cel_horario`**

Logo após a função `cel_reenviar` (termina em `...📨 Reenviar</button></form>')`), adicionar:
```python
    def cel_horario(s):
        import subscribers
        atual = subscribers.slot_de(s)
        opts = "".join(f'<option value="{sl}"{" selected" if sl == atual else ""}>{sl}</option>'
                       for sl in config.SLOTS)
        return (f'<form method="post" action="/admin" style="display:flex;gap:5px;align-items:center">'
                f'<input type="hidden" name="token" value="{tk}"><input type="hidden" name="acao" value="definir_slot">'
                f'<input type="hidden" name="id" value="{_esc(s.get("id"))}">'
                f'<select name="slot" style="padding:5px 8px;font-size:12px;background:#0e211a;color:var(--creme);border:1px solid rgba(233,225,198,.2);border-radius:8px">{opts}</select>'
                f'<button class="actbtn ghost" style="padding:6px 10px;font-size:12px" type="submit">Salvar</button></form>')
```

- [ ] **Step 5: Inserir a célula na linha da tabela**

Na montagem de `linhas`, logo após a célula do reenviar:
```python
        f'<td style="padding:13px 10px">{cel_reenviar(s)}</td>'
```
inserir (antes da célula de remover):
```python
        f'<td style="padding:13px 10px">{cel_horario(s)}</td>'
```

- [ ] **Step 6: Resumo por horário (computar + injetar)**

Logo antes de `corpo = f"""` (após a linha `cupons_lista = "".join(...)`), adicionar:
```python
    resumo_slots = ""
    if contagem_slots:
        itens = " · ".join(f"{sl}: {contagem_slots.get(sl, 0)}" for sl in config.SLOTS)
        resumo_slots = f'<p class="hint" style="margin-top:2px">Envio por horário — {itens}</p>'
```
E no corpo, logo após a linha do `<p class="hint">{len(assinantes)} no total ...</p>`, inserir `{resumo_slots}`:
```python
      <p class="hint">{len(assinantes)} no total · {ativos} ativos · {n_cur} curador(es) &nbsp;·&nbsp; <a href="/curadoria" style="color:var(--ouro2)">🔬 ir para a Curadoria</a></p>
      {resumo_slots}
      {erro_html}
```

- [ ] **Step 7: Cabeçalho + colspan**

No `<thead>`, trocar:
```python
<th style="padding:8px 10px">Boas-vindas</th><th></th></tr></thead>
```
por:
```python
<th style="padding:8px 10px">Boas-vindas</th><th style="padding:8px 10px">Horário</th><th></th></tr></thead>
```
E o estado vazio: trocar `colspan="10"` por `colspan="11"`.

- [ ] **Step 8: Rodar testes (novos + suíte)**

Run: `cd app && python3 -m unittest tests.test_admin_horario_ui -v`
Expected: PASS (3 testes).

Run: `cd app && python3 -m unittest discover -s tests`
Expected: OK.

- [ ] **Step 9: Commit**

```bash
git add app/site_web.py app/tests/test_admin_horario_ui.py
git commit -m "feat(admin-horario): resumo por horário + coluna de troca de slot na tabela de Assinantes"
```
Stagear APENAS esses 2 arquivos. Não usar `git add -A`.

---

### Task 2: Handler `serve.py` (GET contagem + POST definir_slot)

**Files:**
- Modify: `app/serve.py` — GET render de `/admin` (~220) e dispatcher POST `/admin` (novo `elif` antes de `elif acao == "curador":`).

**Interfaces:**
- Consumes: `site_web.pagina_admin(..., contagem_slots=)` (Task 1), `subscribers.contar_por_slot()`, `subscribers.por_id`, `subscribers.definir_slot`, `db.slot_ja_enviou`, `daily.enviar_catch_up`, `daily._hoje_iso`. `config`, `subscribers`, `db`, `up` já no escopo do bloco `/admin`.

> Nota: handler HTTP sem harness de teste no repo. Glue fino; verificação = suíte + `python3 -c "import serve"` + smoke manual.

- [ ] **Step 1: GET passa `contagem_slots`**

Trocar a última linha do render:
```python
                sucesso=q.get("sucesso", [""])[0]), 200)
```
por:
```python
                sucesso=q.get("sucesso", [""])[0],
                contagem_slots=subscribers.contar_por_slot()), 200)
```

- [ ] **Step 2: POST — branch `definir_slot`**

No dispatcher POST `/admin`, inserir imediatamente ANTES de `            elif acao == "curador":`:
```python
            elif acao == "definir_slot":
                import daily as _daily
                sub = subscribers.por_id(g("id"))
                if not sub:
                    erro = up.quote("Assinante não encontrado.")
                    return self._redirect(f"/admin?token={config.ADMIN_TOKEN}&erro={erro}"
                                          if token_ok else f"/admin?erro={erro}")
                novo = g("slot")
                subscribers.definir_slot(sub["id"], novo)   # valida ∈ SLOTS; SEM teto (admin fura)
                if novo in config.SLOTS and db.slot_ja_enviou(_daily._hoje_iso(), novo):
                    try:
                        _daily.enviar_catch_up(subscribers.por_id(sub["id"]))
                    except Exception as e:
                        print(f"[admin] catch-up de slot falhou: {e}", flush=True)
                msg = up.quote("✅ Horário atualizado.")
                return self._redirect(f"/admin?token={config.ADMIN_TOKEN}&sucesso={msg}"
                                      if token_ok else f"/admin?sucesso={msg}")
```

- [ ] **Step 3: Suíte + import**

Run: `cd app && python3 -m unittest discover -s tests`
Expected: OK.

Run: `cd app && python3 -c "import serve"`
Expected: sem erro.

- [ ] **Step 4: Smoke manual (opcional)**

`/admin?token=…` → conferir o resumo "Envio por horário" e a coluna "Horário" com `<select>`; trocar o horário de um assinante e ver o ✅.

- [ ] **Step 5: Commit**

```bash
git add app/serve.py
git commit -m "feat(admin-horario): GET passa contagem por slot + POST acao=definir_slot (com catch-up)"
```
Stagear APENAS `app/serve.py`.

---

## Self-Review (feita)

- **Cobertura do spec:** resumo (Task 1 Step 6) ✓; coluna/select todos os slots + atual (Task 1 Steps 4-5) ✓; GET contagem (Task 2 Step 1) ✓; POST definir_slot override + catch-up gated (Task 2 Step 2) ✓; header/colspan (Task 1 Step 7) ✓.
- **Placeholders:** nenhum — código/comandos reais e saída esperada.
- **Consistência:** `acao=definir_slot`, campo `slot` e `contagem_slots` batem entre UI (Task 1) e handler (Task 2). `subscribers.slot_de/contar_por_slot/definir_slot/por_id`, `db.slot_ja_enviou`, `daily.enviar_catch_up/_hoje_iso`, `config.SLOTS/SLOT_DEFAULT` verificados no repo. colspan atual = 10 (confirmado) → 11.
