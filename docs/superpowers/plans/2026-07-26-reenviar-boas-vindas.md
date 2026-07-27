# Reenviar boas-vindas (WhatsApp) no admin — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar um botão por linha na tabela de Assinantes do admin que reenvia a boas-vindas do WhatsApp (link novo de criar-senha, 7 dias), com confirmação antes e feedback ✅/❌ do resultado.

**Architecture:** Nova função `auth_web.reenviar_boas_vindas_wa(assinante, enviar_fn=None)` reaproveita `preparar_primeiro_acesso` + `mensagens.wa_boas_vindas` e envia só por WhatsApp (`deliver.enviar_texto`), retornando `(ok, detalhe)`. A UI (`site_web.pagina_admin`) ganha botão + caixa de confirmação + feedback de sucesso; o handler POST `/admin` (`serve.py`) despacha `reenviar` (mostra confirmação) e `reenviar_confirmar` (envia + redireciona com resultado).

**Tech Stack:** Python stdlib (http.server, urllib), unittest. Sem dependências novas.

## Global Constraints

- **Só WhatsApp.** Nenhuma chamada a `email_send` no caminho novo.
- **Não alterar** `webhook_asaas._boas_vindas` (fluxo automático segue WhatsApp + e-mail).
- Estilo do repo: imports lazy dentro de funções quando o módulo não é usado no load (padrão de `auth_web`), f-strings, sem libs novas.
- Rodar testes: `cd app && python3 -m unittest discover -s tests` (ou um módulo: `cd app && python3 -m unittest tests.<modulo> -v`).
- Commits em português, sem trailer de atribuição (config global + convenção do repo).
- Branch de trabalho: `feat/reenviar-boas-vindas` (já criado; spec já commitado nele).

---

### Task 1: `auth_web.reenviar_boas_vindas_wa`

**Files:**
- Modify: `app/auth_web.py` (adicionar função nova; boa posição: logo após `preparar_primeiro_acesso`, ~linha 229)
- Test: `app/tests/test_reenviar_boas_vindas.py` (novo)

**Interfaces:**
- Consumes: `preparar_primeiro_acesso(whatsapp) -> str` (link), `_enviar_padrao(num, msg)` (default sender já existente em `auth_web`), `mensagens.wa_boas_vindas(link, nome) -> str`.
- Produces: `reenviar_boas_vindas_wa(assinante: dict, enviar_fn=None) -> tuple[bool, str]` — `(True, "")` em sucesso; `(False, motivo)` sem WhatsApp ou em falha de envio.

- [ ] **Step 1: Escrever os testes que falham**

Criar `app/tests/test_reenviar_boas_vindas.py`:

```python
"""Testes do reenvio de boas-vindas (WhatsApp only) do admin. Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestReenviarBoasVindas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import db as _db
        importlib.reload(_db)
        import auth_web as _aw
        importlib.reload(_aw)
        self.db, self.aw = _db, _aw
        self.db.init()

    def test_sucesso_envia_so_whatsapp_com_link(self):
        enviados = []
        assinante = {"id": 1, "nome": "Gleidson", "whatsapp": "5544999998888"}
        ok, detalhe = self.aw.reenviar_boas_vindas_wa(
            assinante, enviar_fn=lambda num, msg: enviados.append((num, msg)))
        self.assertTrue(ok)
        self.assertEqual(detalhe, "")
        self.assertEqual(len(enviados), 1)               # exatamente 1 envio (WhatsApp)
        self.assertEqual(enviados[0][0], "5544999998888")
        self.assertIn("/criar-senha?token=", enviados[0][1])   # link novo no texto

    def test_falha_de_envio_retorna_motivo(self):
        def boom(num, msg):
            raise RuntimeError("evolution 500")
        ok, detalhe = self.aw.reenviar_boas_vindas_wa(
            {"id": 1, "nome": "X", "whatsapp": "5544999998888"}, enviar_fn=boom)
        self.assertFalse(ok)
        self.assertIn("evolution 500", detalhe)

    def test_sem_whatsapp_nao_envia(self):
        chamados = []
        ok, detalhe = self.aw.reenviar_boas_vindas_wa(
            {"id": 1, "nome": "SemZap", "whatsapp": ""},
            enviar_fn=lambda num, msg: chamados.append(num))
        self.assertFalse(ok)
        self.assertEqual(chamados, [])                    # não tentou enviar


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd app && python3 -m unittest tests.test_reenviar_boas_vindas -v`
Expected: FAIL — `AttributeError: module 'auth_web' has no attribute 'reenviar_boas_vindas_wa'`.

- [ ] **Step 3: Implementar a função**

Em `app/auth_web.py`, logo após `preparar_primeiro_acesso` (linha ~229), adicionar:

```python
def reenviar_boas_vindas_wa(assinante, enviar_fn=None):
    """Reenvia SÓ a boas-vindas do WhatsApp (link novo de criar-senha, 7 dias).
    Não dispara e-mail. Retorna (ok, detalhe) p/ o admin ver o resultado."""
    import mensagens
    whatsapp = (assinante or {}).get("whatsapp", "").strip()
    if not whatsapp:
        return (False, "assinante sem WhatsApp")
    try:
        link = preparar_primeiro_acesso(whatsapp)
        texto = mensagens.wa_boas_vindas(link, assinante.get("nome", ""))
        fn = enviar_fn or _enviar_padrao
        fn(whatsapp, texto)
        return (True, "")
    except Exception as e:
        print(f"[reenviar] boas-vindas WhatsApp falhou: {e}", flush=True)
        return (False, str(e))
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd app && python3 -m unittest tests.test_reenviar_boas_vindas -v`
Expected: PASS (3 testes).

- [ ] **Step 5: Commit**

```bash
git add app/auth_web.py app/tests/test_reenviar_boas_vindas.py
git commit -m "feat(reenviar): auth_web.reenviar_boas_vindas_wa (WhatsApp only, link novo) + testes"
```

---

### Task 2: UI na tabela de Assinantes (`pagina_admin`)

**Files:**
- Modify: `app/site_web.py` — `pagina_admin` (linhas 811-937)
- Test: `app/tests/test_admin_reenviar_ui.py` (novo)

**Interfaces:**
- Consumes: nada de Task 1 (renderização pura).
- Produces: `site_web.pagina_admin(assinantes, token="", cupons=None, confirmar_id=None, erro="", reenviar_id=None, sucesso="") -> str` — HTML com botão `acao=reenviar` por linha, caixa de confirmação (`acao=reenviar_confirmar`) quando `reenviar_id` casa, e infobox verde de `sucesso`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `app/tests/test_admin_reenviar_ui.py`:

```python
"""Testes de render do botão/confirmação/feedback de reenviar boas-vindas. Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAdminReenviarUI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import site_web as _sw
        importlib.reload(_sw)
        self.sw = _sw

    def _sub(self, **kw):
        base = {"id": 7, "nome": "Gleidson", "whatsapp": "5544999998888",
                "email": "", "plano": "mensal", "status": "ATIVO"}
        base.update(kw)
        return base

    def test_botao_reenviar_por_linha(self):
        html = self.sw.pagina_admin([self._sub()], token="tk")
        self.assertIn('name="acao" value="reenviar"', html)
        self.assertIn("Reenviar", html)

    def test_caixa_confirmacao_quando_reenviar_id(self):
        html = self.sw.pagina_admin([self._sub()], token="tk", reenviar_id="7")
        self.assertIn('name="acao" value="reenviar_confirmar"', html)
        self.assertIn("Gleidson", html)
        self.assertIn("Confirmar reenvio", html)

    def test_feedback_sucesso(self):
        html = self.sw.pagina_admin([self._sub()], token="tk", sucesso="Boas-vindas reenviadas")
        self.assertIn("Boas-vindas reenviadas", html)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd app && python3 -m unittest tests.test_admin_reenviar_ui -v`
Expected: FAIL — `test_caixa_confirmacao_quando_reenviar_id` e `test_feedback_sucesso` dão `TypeError: pagina_admin() got an unexpected keyword argument 'reenviar_id'` (e `test_botao_reenviar_por_linha` falha por não achar o botão).

- [ ] **Step 3: Alterar a assinatura + feedback + confirmação**

Em `app/site_web.py`, na linha 811, trocar a assinatura:

```python
def pagina_admin(assinantes, token="", cupons=None, confirmar_id=None, erro="",
                 reenviar_id=None, sucesso=""):
```

Logo após `erro_html = ...` (linha 816), adicionar:

```python
    sucesso_html = (f'<div class="infobox" style="border-color:#2f9e6b66;background:#2f9e6b18;margin:14px 0">'
                    f'{_esc(sucesso)}</div>') if sucesso else ""
```

Logo após o bloco do `confirm_html` (termina na linha 830, antes de `def badge(st):`), adicionar a caixa de reenvio:

```python
    alvo_re = next((s for s in assinantes if str(s.get("id")) == str(reenviar_id)), None) if reenviar_id else None
    reenviar_html = ""
    if alvo_re:
        reenviar_html = (
            '<div class="infobox" style="border-color:#c9a22766;background:#c9a22718;margin:14px 0">'
            f'<strong>Reenviar boas-vindas (WhatsApp) para '
            f'{_esc(alvo_re.get("nome") or alvo_re.get("whatsapp") or "este assinante")}?</strong> '
            f'Vai um link novo de criar-senha para {_esc(alvo_re.get("whatsapp") or "—")}.'
            '<div style="display:flex;gap:10px;margin-top:12px">'
            '<form method="post" action="/admin" style="margin:0">'
            f'<input type="hidden" name="token" value="{tk}"><input type="hidden" name="acao" value="reenviar_confirmar">'
            f'<input type="hidden" name="id" value="{_esc(alvo_re.get("id"))}">'
            '<button class="actbtn" style="background:#2f9e6b;color:#fff;padding:8px 16px">Confirmar reenvio</button></form>'
            f'<a class="actbtn ghost" href="/admin?token={tk}" style="padding:8px 16px;text-decoration:none">Cancelar</a>'
            '</div></div>')
```

- [ ] **Step 4: Adicionar a célula/botão por linha**

Em `app/site_web.py`, logo após a função `cel_editar_numero` (termina na linha 858), adicionar:

```python
    def cel_reenviar(s):
        return (f'<form method="post" action="/admin" style="margin:0">'
                f'<input type="hidden" name="token" value="{tk}"><input type="hidden" name="acao" value="reenviar">'
                f'<input type="hidden" name="id" value="{_esc(s.get("id"))}">'
                f'<button class="actbtn ghost" style="padding:6px 13px;font-size:12px" type="submit">📨 Reenviar</button></form>')
```

No monte da linha (`linhas = "".join(...)`), inserir a célula nova imediatamente após a célula de `cel_editar_numero` (linha 868), antes da célula de remover (linha 869):

```python
        f'<td style="padding:13px 10px">{cel_reenviar(s)}</td>'
```

- [ ] **Step 5: Cabeçalho, colspan e injeção no corpo**

No `<thead>` (linha 899), inserir a coluna "Boas-vindas" antes do `<th></th>` final:

De:
```python
<th style="padding:8px 10px">Curadoria</th><th style="padding:8px 10px">Editar número</th><th></th></tr></thead>
```
Para:
```python
<th style="padding:8px 10px">Curadoria</th><th style="padding:8px 10px">Editar número</th><th style="padding:8px 10px">Boas-vindas</th><th></th></tr></thead>
```

Na linha do estado vazio (linha 900), trocar `colspan="9"` por `colspan="10"`.

No corpo (linhas 892-893), trocar:
```python
      {erro_html}
      {confirm_html}
```
Por:
```python
      {erro_html}
      {sucesso_html}
      {confirm_html}
      {reenviar_html}
```

- [ ] **Step 6: Rodar os testes (novos + suíte cheia)**

Run: `cd app && python3 -m unittest tests.test_admin_reenviar_ui -v`
Expected: PASS (3 testes).

Run: `cd app && python3 -m unittest discover -s tests`
Expected: OK (suíte inteira verde).

- [ ] **Step 7: Commit**

```bash
git add app/site_web.py app/tests/test_admin_reenviar_ui.py
git commit -m "feat(reenviar): botão + confirmação + feedback de sucesso na tabela de Assinantes"
```

---

### Task 3: Handler POST `/admin` + params do GET (`serve.py`)

**Files:**
- Modify: `app/serve.py` — GET render (linhas 220-223) e dispatcher POST `/admin` (perto da linha 485).

**Interfaces:**
- Consumes: `subscribers.por_id(id) -> dict | None`, `auth_web.reenviar_boas_vindas_wa(sub) -> (ok, detalhe)` (Task 1), `site_web.pagina_admin(..., reenviar_id=, sucesso=)` (Task 2). `up` = `urllib.parse`, `auth_web`/`subscribers`/`config` já importados no bloco.
- Produces: rotas `acao=reenviar` (mostra confirmação) e `acao=reenviar_confirmar` (envia + redireciona com `sucesso`/`erro`).

> Nota: o dispatcher HTTP não tem harness de teste no repo (os testes cobrem as funções puras de Task 1/2). Esta task é glue fino; a verificação é a suíte + smoke manual do Step 4.

- [ ] **Step 1: Passar os params novos no GET**

Em `app/serve.py`, trocar o bloco de render (linhas 220-223):

De:
```python
            return self._html(site_web.pagina_admin(
                subscribers.listar(), config.ADMIN_TOKEN or "", db.listar_cupons(),
                confirmar_id=q.get("confirmar", [""])[0] or None,
                erro=q.get("erro", [""])[0]), 200)
```
Para:
```python
            return self._html(site_web.pagina_admin(
                subscribers.listar(), config.ADMIN_TOKEN or "", db.listar_cupons(),
                confirmar_id=q.get("confirmar", [""])[0] or None,
                erro=q.get("erro", [""])[0],
                reenviar_id=q.get("reenviar", [""])[0] or None,
                sucesso=q.get("sucesso", [""])[0]), 200)
```

- [ ] **Step 2: Despachar as ações no POST `/admin`**

Em `app/serve.py`, no dispatcher do POST `/admin`, logo após o branch `elif acao == "editar_numero":` (termina na linha 485, antes de `elif acao == "curador":`), inserir:

```python
            elif acao == "reenviar":
                return self._redirect(f"/admin?token={config.ADMIN_TOKEN}&reenviar={g('id')}"
                                      if token_ok else f"/admin?reenviar={g('id')}")
            elif acao == "reenviar_confirmar":
                sub = subscribers.por_id(g("id"))
                if not sub:
                    erro = up.quote("Assinante não encontrado.")
                    return self._redirect(f"/admin?token={config.ADMIN_TOKEN}&erro={erro}"
                                          if token_ok else f"/admin?erro={erro}")
                ok, detalhe = auth_web.reenviar_boas_vindas_wa(sub)
                if ok:
                    msg = up.quote("✅ Boas-vindas reenviadas por WhatsApp.")
                    return self._redirect(f"/admin?token={config.ADMIN_TOKEN}&sucesso={msg}"
                                          if token_ok else f"/admin?sucesso={msg}")
                erro = up.quote(f"❌ Falha ao reenviar: {detalhe}")
                return self._redirect(f"/admin?token={config.ADMIN_TOKEN}&erro={erro}"
                                      if token_ok else f"/admin?erro={erro}")
```

- [ ] **Step 3: Rodar a suíte inteira**

Run: `cd app && python3 -m unittest discover -s tests`
Expected: OK (nada quebrou; import de `serve.py` compila).

Sanidade de compilação do módulo alterado:
Run: `cd app && python3 -c "import serve"`
Expected: sem erro.

- [ ] **Step 4: Smoke manual (opcional, recomendado)**

Subir o app local e abrir `/admin?token=<ADMIN_TOKEN>`, conferir:
- Coluna "Boas-vindas" com botão `📨 Reenviar` em cada linha.
- Clicar → aparece a caixa "Reenviar boas-vindas (WhatsApp) para …?" com Confirmar/Cancelar.
- Cancelar volta sem enviar; Confirmar dispara e a página volta com a infobox verde (ou vermelha, se falhar).

- [ ] **Step 5: Commit**

```bash
git add app/serve.py
git commit -m "feat(reenviar): handler POST /admin (reenviar/reenviar_confirmar) + params no GET"
```

---

## Self-Review (feita)

- **Cobertura do spec:** função WhatsApp-only com retorno (Task 1) ✓; botão + confirmação + feedback (Task 2) ✓; handler reenviar/reenviar_confirmar + params GET (Task 3) ✓; webhook intocado ✓; testes 1/2/3 do spec cobertos em Task 1; render coberto em Task 2.
- **Placeholders:** nenhum — todo passo tem código/comando reais e saída esperada.
- **Consistência de tipos:** `reenviar_boas_vindas_wa(assinante, enviar_fn=None) -> (bool, str)` usado igual em Task 1 e Task 3; `pagina_admin(..., reenviar_id=None, sucesso="")` idêntico entre Task 2 e Task 3; `subscribers.por_id` (existe em `subscribers.py:164`), `_enviar_padrao` (existe em `auth_web.py:73`), `up`/`auth_web`/`subscribers` já no escopo do handler.
