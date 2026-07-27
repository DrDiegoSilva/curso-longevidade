# Login por CPF — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir login pelo CPF (CPF+senha, com fallback de código no WhatsApp), destravando assinantes internacionais que não conseguem logar digitando o número.

**Architecture:** As funções de CPF em `auth_web` só **acham o assinante pelo CPF e delegam** para as funções por-WhatsApp já existentes e testadas (`login_senha`, `iniciar_login`, `verificar`). A UI reaproveita `pagina_login`/`pagina_entrar` com um parâmetro `via="whatsapp"|"cpf"`. Rotas novas em `serve.py` espelham as de WhatsApp.

**Tech Stack:** Python stdlib (http.server), unittest. Sem dependências novas.

## Global Constraints

- **Não alterar o comportamento do login por WhatsApp existente.** Parâmetros novos têm default (`via="whatsapp"`); os call-sites atuais (`serve.py:297,299,586,587,597,600`) ficam intactos. A única mudança visível no modo WhatsApp é **um link novo de descoberta** ("Entrar com CPF").
- CPF é comparado **só por dígitos** (`cpf.so_digitos`); aceita `000.000.000-00` ou só números. Sem bloqueio por dígito verificador.
- **Anti-enumeração:** CPF desconhecido → mesma mensagem de erro do senha errada; caminho de código sempre mostra a tela de código.
- Reusar rate limits: `login` (15/5min) e `otp` (5/10min).
- Estilo do repo: f-strings, imports lazy, sem libs novas. Commits em PT, sem trailer de atribuição.
- Rodar testes: `cd app && python3 -m unittest discover -s tests` (ou `cd app && python3 -m unittest tests.<modulo> -v`).
- Branch: `feat/login-cpf` (spec já commitado: `7fc3fb1`).

---

### Task 1: Funções de CPF em `auth_web`

**Files:**
- Modify: `app/auth_web.py` — adicionar 4 funções após `precisa_criar_senha` (~linha 218), sob um comentário `# ── Login por CPF (acha por CPF e delega pro login por WhatsApp) ──`.
- Test: `app/tests/test_login_cpf.py` (novo)

**Interfaces:**
- Consumes (já existem): `login_senha(whatsapp, senha) -> (status, token)`, `iniciar_login(whatsapp, enviar_fn=None) -> bool`, `verificar(whatsapp, codigo) -> token|None`, `subscribers.ativos() -> list[dict]`, `cpf.so_digitos(s) -> str`.
- Produces: `_ativo_por_cpf(cpf_in) -> dict|None`, `login_senha_cpf(cpf_in, senha) -> (str, str|None)`, `iniciar_login_cpf(cpf_in, enviar_fn=None) -> bool`, `verificar_cpf(cpf_in, codigo) -> str|None`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `app/tests/test_login_cpf.py`:

```python
"""Testes do login por CPF (acha por CPF e delega pro login por WhatsApp). Standalone."""
import os
import re
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

CPF_A = "12345678901"   # só dígitos — validade não importa (compara por dígitos)
CPF_B = "98765432100"


class TestLoginCPF(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import db as _db; importlib.reload(_db)
        import subscribers as _s; importlib.reload(_s)
        import passwords as _p; importlib.reload(_p)
        import auth_web as _aw; importlib.reload(_aw)
        self.db, self.subs, self.pw, self.aw = _db, _s, _p, _aw
        self.db.init()

    def _criar(self, cpf, whatsapp="5544999998888", senha="Senha1"):
        reg = self.subs.criar_de_pagamento(
            {"nome": "Fulano", "whatsapp": whatsapp, "cpf": cpf, "email": "",
             "plano": "mensal", "metodo": "PIX"})
        if senha:
            self.subs.definir_senha(reg["id"], self.pw.hash_senha(senha))
        return reg

    # ── senha ──
    def test_senha_ok(self):
        self._criar(CPF_A, senha="Senha1")
        status, token = self.aw.login_senha_cpf(CPF_A, "Senha1")
        self.assertEqual(status, "ok")
        self.assertTrue(token)

    def test_senha_errada(self):
        self._criar(CPF_A, senha="Senha1")
        self.assertEqual(self.aw.login_senha_cpf(CPF_A, "errada")[0], "credenciais")

    def test_sem_senha(self):
        self._criar(CPF_A, senha=None)
        self.assertEqual(self.aw.login_senha_cpf(CPF_A, "qualquer")[0], "sem_senha")

    def test_cpf_desconhecido(self):
        self.assertEqual(self.aw.login_senha_cpf(CPF_B, "x")[0], "inativo")

    def test_cpf_com_pontuacao_casa(self):
        self._criar(CPF_A, senha="Senha1")
        status, token = self.aw.login_senha_cpf("123.456.789-01", "Senha1")
        self.assertEqual(status, "ok")
        self.assertTrue(token)

    def test_intl_loga_por_cpf(self):
        self._criar(CPF_A, whatsapp="+15555551234", senha="Senha1")
        status, token = self.aw.login_senha_cpf(CPF_A, "Senha1")
        self.assertEqual(status, "ok")
        self.assertTrue(token)

    # ── código (OTP) ──
    def test_iniciar_login_cpf_envia_ao_numero_salvo(self):
        self._criar(CPF_A, whatsapp="+15555551234", senha=None)
        enviados = []
        ok = self.aw.iniciar_login_cpf(CPF_A, enviar_fn=lambda num, msg: enviados.append((num, msg)))
        self.assertTrue(ok)
        self.assertEqual(len(enviados), 1)
        self.assertIn("15555551234", enviados[0][0])   # foi pro número SALVO, não digitado

    def test_iniciar_login_cpf_desconhecido(self):
        chamados = []
        ok = self.aw.iniciar_login_cpf(CPF_B, enviar_fn=lambda n, m: chamados.append(n))
        self.assertFalse(ok)
        self.assertEqual(chamados, [])

    def test_verificar_cpf_codigo_certo_e_errado(self):
        self._criar(CPF_A, whatsapp="5544999998888", senha=None)
        enviados = []
        self.aw.iniciar_login_cpf(CPF_A, enviar_fn=lambda num, msg: enviados.append(msg))
        codigo = re.search(r"\*(\d{6})\*", enviados[0]).group(1)
        errado = "000000" if codigo != "000000" else "111111"
        self.assertIsNone(self.aw.verificar_cpf(CPF_A, errado))   # erra 1x (< MAX_TENTATIVAS)
        self.assertTrue(self.aw.verificar_cpf(CPF_A, codigo))     # acerta -> token

    def test_verificar_cpf_desconhecido(self):
        self.assertIsNone(self.aw.verificar_cpf(CPF_B, "123456"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd app && python3 -m unittest tests.test_login_cpf -v`
Expected: FAIL — `AttributeError: module 'auth_web' has no attribute 'login_senha_cpf'` (e as demais).

- [ ] **Step 3: Implementar as 4 funções**

Em `app/auth_web.py`, após `precisa_criar_senha` (~linha 218), adicionar:

```python
# ── Login por CPF (acha por CPF e delega pro login por WhatsApp) ──
def _ativo_por_cpf(cpf_in):
    """Assinante ATIVO cujos dígitos de CPF batem, ou None. (única lógica nova)"""
    import cpf as cpfmod
    n = cpfmod.so_digitos(cpf_in)
    if not n:
        return None
    return next((a for a in subscribers.ativos()
                 if cpfmod.so_digitos(a.get("cpf", "")) == n), None)


def login_senha_cpf(cpf_in, senha):
    """CPF + senha. Resolve o CPF e delega pro login_senha (por WhatsApp).
    (status, token): 'ok' | 'sem_senha' | 'credenciais' | 'inativo'."""
    a = _ativo_por_cpf(cpf_in)
    if not a:
        return ("inativo", None)
    return login_senha(a.get("whatsapp", ""), senha)


def iniciar_login_cpf(cpf_in, enviar_fn=None):
    """Manda o OTP pro WhatsApp SALVO do assinante achado por CPF. Neutro. True se enviou."""
    a = _ativo_por_cpf(cpf_in)
    if not a:
        return False
    return iniciar_login(a.get("whatsapp", ""), enviar_fn)


def verificar_cpf(cpf_in, codigo):
    """Verifica o OTP p/ o assinante achado por CPF. Token da sessão, ou None."""
    a = _ativo_por_cpf(cpf_in)
    if not a:
        return None
    return verificar(a.get("whatsapp", ""), codigo)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd app && python3 -m unittest tests.test_login_cpf -v`
Expected: PASS (11 testes).

Run: `cd app && python3 -m unittest discover -s tests`
Expected: OK (suíte inteira verde).

- [ ] **Step 5: Commit**

```bash
git add app/auth_web.py app/tests/test_login_cpf.py
git commit -m "feat(login-cpf): auth_web login_senha_cpf/iniciar_login_cpf/verificar_cpf (delega pro WhatsApp) + testes"
```

---

### Task 2: UI parametrizada (`pagina_login` + `pagina_entrar`)

**Files:**
- Modify: `app/site_web.py` — substituir `pagina_login` (491-517) e `pagina_entrar` (457-488) pelas versões parametrizadas abaixo. Task 1 não tocou site_web.py, então esses números valem.
- Test: `app/tests/test_login_cpf_ui.py` (novo)

**Interfaces:**
- Produces: `pagina_login(erro="", sem_senha=False, whatsapp="", via="whatsapp") -> str` e `pagina_entrar(etapa="numero", whatsapp="", erro="", via="whatsapp") -> str`. Em `via="cpf"`: campo `name="cpf"`, `action="/entrar-cpf"` (senha) / `action="/entrar-cpf-codigo"` (código). O param `whatsapp` carrega o valor do identificador a repreencher (é o CPF quando `via="cpf"`).

- [ ] **Step 1: Escrever os testes que falham**

Criar `app/tests/test_login_cpf_ui.py`:

```python
"""Testes de render das telas de login em modo CPF. Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestLoginCPFUI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import site_web as _sw
        importlib.reload(_sw)
        self.sw = _sw

    def test_login_cpf_mode(self):
        html = self.sw.pagina_login(via="cpf")
        self.assertIn('action="/entrar-cpf"', html)
        self.assertIn('name="cpf"', html)
        self.assertIn("CPF", html)

    def test_login_whatsapp_inalterado_com_link_descoberta(self):
        html = self.sw.pagina_login()
        self.assertIn('action="/entrar"', html)
        self.assertIn('name="whatsapp"', html)
        self.assertIn('href="/entrar-cpf"', html)   # link de descoberta

    def test_entrar_codigo_cpf_numero(self):
        html = self.sw.pagina_entrar("numero", via="cpf")
        self.assertIn('action="/entrar-cpf-codigo"', html)
        self.assertIn('name="cpf"', html)

    def test_entrar_codigo_cpf_hidden_carrega_valor(self):
        html = self.sw.pagina_entrar("codigo", whatsapp="12345678901", via="cpf")
        self.assertIn('action="/entrar-cpf-codigo"', html)
        self.assertIn('name="cpf"', html)
        self.assertIn('value="12345678901"', html)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd app && python3 -m unittest tests.test_login_cpf_ui -v`
Expected: FAIL — `TypeError: pagina_login() got an unexpected keyword argument 'via'` (e demais).

- [ ] **Step 3: Substituir `pagina_entrar` (linhas 457-488)**

Trocar a função inteira por:

```python
def pagina_entrar(etapa="numero", whatsapp="", erro="", via="whatsapp"):
    """Login por código (OTP). via='whatsapp' (padrão) ou 'cpf'.
    `whatsapp` = valor do identificador a repreencher/embutir (é o CPF quando via='cpf')."""
    cpf_mode = (via == "cpf")
    campo = "cpf" if cpf_mode else "whatsapp"
    action = "/entrar-cpf-codigo" if cpf_mode else "/entrar-codigo"
    senha_href = "/entrar-cpf" if cpf_mode else "/entrar"
    recomecar_txt = "Usar outro CPF" if cpf_mode else "Usar outro número"
    erro_html = f'<div class="erro">{_esc(erro)}</div>' if erro else ""
    if etapa == "codigo":
        corpo = f"""
        <div class="wrap"><div class="panel">
          <h2 class="disp">Digite o código</h2>
          <p class="hint">Enviamos um código de 6 dígitos no seu WhatsApp. Ele vale por 10 minutos.</p>
          {erro_html}
          <form method="post" action="{action}">
            <input type="hidden" name="etapa" value="codigo">
            <input type="hidden" name="{campo}" value="{_esc(whatsapp)}">
            <label>Código</label>
            <input type="text" name="codigo" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="000000" autofocus>
            <button class="cta" type="submit">Entrar</button>
          </form>
          <p class="hint" style="margin-top:16px"><a href="{action}" style="color:var(--ouro2)">{recomecar_txt}</a> &nbsp;·&nbsp; <a href="{senha_href}" style="color:var(--suave)">Entrar com senha</a></p>
        </div></div>"""
    else:
        label = "CPF" if cpf_mode else "WhatsApp (com DDD)"
        imode = "numeric" if cpf_mode else "tel"
        ph = "000.000.000-00" if cpf_mode else "(43) 99999-0000"
        hint = ("Informe o CPF do seu cadastro e enviamos um código de acesso ao WhatsApp da assinatura."
                if cpf_mode else
                "Sem acesso à senha? Informe o WhatsApp da sua assinatura e enviamos um código de acesso.")
        corpo = f"""
        <div class="wrap"><div class="panel">
          <h2 class="disp">Entrar com código</h2>
          <p class="hint">{hint}</p>
          {erro_html}
          <form method="post" action="{action}">
            <input type="hidden" name="etapa" value="numero">
            <label>{label}</label>
            <input type="text" name="{campo}" inputmode="{imode}" placeholder="{ph}" autofocus>
            <button class="cta" type="submit">Enviar código</button>
          </form>
          <p class="hint" style="margin-top:16px"><a href="{senha_href}" style="color:var(--ouro2)">← Entrar com senha</a></p>
        </div></div>"""
    return _pagina(f"Entrar · {PRODUTO}", corpo, logado=False, meta_extra='<meta name="robots" content="noindex">')
```

- [ ] **Step 4: Substituir `pagina_login` (linhas 491-517)**

Trocar a função inteira por:

```python
def pagina_login(erro="", sem_senha=False, whatsapp="", via="whatsapp"):
    """Tela de login principal: identificador + senha. via='whatsapp' (padrão) ou 'cpf'.
    `whatsapp` = valor do identificador a repreencher (é o CPF quando via='cpf')."""
    cpf_mode = (via == "cpf")
    label = "CPF" if cpf_mode else "WhatsApp (com DDD)"
    campo = "cpf" if cpf_mode else "whatsapp"
    imode = "numeric" if cpf_mode else "tel"
    ph = "000.000.000-00" if cpf_mode else "(43) 99999-0000"
    action = "/entrar-cpf" if cpf_mode else "/entrar"
    codigo_href = "/entrar-cpf-codigo" if cpf_mode else "/entrar-codigo"
    titulo_hint = ("Entre com o CPF do seu cadastro e sua senha." if cpf_mode
                   else "Entre com o WhatsApp da sua assinatura e sua senha.")
    erro_html = f'<div class="erro">{_esc(erro)}</div>' if erro else ""
    if sem_senha:
        if cpf_mode:
            erro_html += ('<div class="infobox">Você ainda não criou sua senha. Use '
                          '<strong>Entrar com código no WhatsApp</strong> abaixo (ou peça seu link de acesso).</div>')
        else:
            erro_html += ('<div class="infobox">Você ainda não criou sua senha. Clique em '
                          '<strong>Primeiro acesso / criar senha</strong> abaixo — enviaremos um link por e-mail.</div>')
    if cpf_mode:
        aux = (f'<p class="hint" style="margin-top:16px"><a href="{codigo_href}" style="color:var(--ouro2)">Sem senha? Entrar com código no WhatsApp</a></p>'
               f'<p class="hint" style="margin-top:8px;font-size:13px"><a href="/entrar" style="color:var(--suave)">← Entrar com WhatsApp</a></p>')
    else:
        aux = ('<p class="hint" style="margin-top:16px">'
               '<a href="/primeiro-acesso" style="color:var(--ouro2)">Primeiro acesso / criar senha</a>'
               '&nbsp;·&nbsp;'
               '<a href="/esqueci" style="color:var(--suave)">Esqueci minha senha</a></p>'
               '<p class="hint" style="margin-top:8px;font-size:13px"><a href="/entrar-codigo" style="color:var(--suave)">Problemas? Entrar com código no WhatsApp</a></p>'
               '<p class="hint" style="margin-top:8px;font-size:13px"><a href="/entrar-cpf" style="color:var(--suave)">Assinante fora do Brasil / sem WhatsApp brasileiro? Entrar com CPF</a></p>')
    corpo = f"""
    <div class="wrap"><div class="panel">
      <h2 class="disp">Área do assinante</h2>
      <p class="hint">{titulo_hint}</p>
      {erro_html}
      <form method="post" action="{action}">
        <label>{label}</label>
        <input type="text" name="{campo}" inputmode="{imode}" value="{_esc(whatsapp)}" placeholder="{ph}" autofocus>
        <label>Senha</label>
        <input type="password" name="senha" placeholder="sua senha">
        <button class="cta" type="submit">Entrar</button>
      </form>
      {aux}
      <p class="hint" style="margin-top:14px">Ainda não assina? <a href="/" style="color:var(--ouro2)">Conheça o plano</a>.</p>
    </div></div>"""
    return _pagina(f"Entrar · {PRODUTO}", corpo, logado=False, meta_extra='<meta name="robots" content="noindex">')
```

- [ ] **Step 5: Rodar os testes (novos + suíte cheia)**

Run: `cd app && python3 -m unittest tests.test_login_cpf_ui -v`
Expected: PASS (4 testes).

Run: `cd app && python3 -m unittest discover -s tests`
Expected: OK (nada quebrou — o login por WhatsApp segue igual, com o link novo).

- [ ] **Step 6: Commit**

```bash
git add app/site_web.py app/tests/test_login_cpf_ui.py
git commit -m "feat(login-cpf): pagina_login/pagina_entrar com via='cpf' + link de descoberta"
```

---

### Task 3: Rotas em `serve.py`

**Files:**
- Modify: `app/serve.py` — 2 rotas GET (após `/entrar-codigo` GET, ~linha 299) e 2 POST (após o bloco `/entrar-codigo` POST, ~linha 600). Tasks 1-2 não tocaram serve.py; os números valem.

**Interfaces:**
- Consumes: `auth_web.login_senha_cpf/iniciar_login_cpf/verificar_cpf` (Task 1), `site_web.pagina_login(via=)`/`pagina_entrar(via=)` (Task 2). `g(...)`, `self._rate_ok`, `self._redirect`, `self._html` já existem no handler.

> Nota: não há harness de teste HTTP no repo (os testes cobrem as funções puras de Task 1/2). Glue fino; verificação = suíte inteira + `python3 -c "import serve"` + smoke manual opcional.

- [ ] **Step 1: Adicionar as rotas GET**

Em `app/serve.py`, logo após:
```python
        if path == "/entrar-codigo":
            return self._html(site_web.pagina_entrar("numero"))
```
inserir:
```python
        if path == "/entrar-cpf":
            return self._html(site_web.pagina_login(via="cpf"))
        if path == "/entrar-cpf-codigo":
            return self._html(site_web.pagina_entrar("numero", via="cpf"))
```

- [ ] **Step 2: Adicionar as rotas POST**

Em `app/serve.py`, logo após o fim do bloco POST `/entrar-codigo`:
```python
            auth_web.iniciar_login(wpp)  # neutro: só envia se for assinante ATIVO
            return self._html(site_web.pagina_entrar("codigo", whatsapp=wpp))
```
inserir:
```python
        if path == "/entrar-cpf":
            if not self._rate_ok("login", 15, 300):
                return
            import site_web, auth_web
            doc = g("cpf")
            status, token = auth_web.login_senha_cpf(doc, g("senha"))
            if status == "ok":
                return self._redirect("/artigos", token=token)
            if status == "sem_senha":
                return self._html(site_web.pagina_login(sem_senha=True, whatsapp=doc, via="cpf"))
            return self._html(site_web.pagina_login(erro="CPF ou senha incorretos.", whatsapp=doc, via="cpf"))
        if path == "/entrar-cpf-codigo":
            if not self._rate_ok("otp", 5, 600):
                return
            import site_web, auth_web
            doc = g("cpf")
            if g("etapa") == "codigo":
                token = auth_web.verificar_cpf(doc, g("codigo"))
                if token:
                    return self._redirect("/artigos", token=token)
                return self._html(site_web.pagina_entrar("codigo", whatsapp=doc, via="cpf",
                                  erro="Código inválido ou expirado. Tente novamente."))
            auth_web.iniciar_login_cpf(doc)  # neutro: só envia se achar assinante ativo
            return self._html(site_web.pagina_entrar("codigo", whatsapp=doc, via="cpf"))
```

- [ ] **Step 3: Rodar a suíte + sanidade de import**

Run: `cd app && python3 -m unittest discover -s tests`
Expected: OK.

Run: `cd app && python3 -c "import serve"`
Expected: sem erro.

- [ ] **Step 4: Smoke manual (opcional)**

Abrir `/entrar` → conferir o link "Entrar com CPF" → `/entrar-cpf` (CPF+senha) e o fallback "Sem senha? Entrar com código" → `/entrar-cpf-codigo`. Logar por CPF de um assinante de teste.

- [ ] **Step 5: Commit**

```bash
git add app/serve.py
git commit -m "feat(login-cpf): rotas /entrar-cpf e /entrar-cpf-codigo (GET+POST)"
```

---

## Self-Review (feita)

- **Cobertura do spec:** funções CPF que delegam (Task 1) ✓; UI parametrizada + descoberta (Task 2) ✓; rotas senha+código (Task 3) ✓; robots já cobre `/entrar-cpf` pelo prefixo `/entrar` (sem passo). Anti-enumeração/rate limit nos handlers ✓. Testes cobrem senha (ok/errada/sem/desconhecido/pontuação/intl) + OTP (envia ao nº salvo/desconhecido/verifica) + render.
- **Placeholders:** nenhum — todo passo tem código/comando reais e saída esperada.
- **Consistência de tipos/nomes:** `login_senha_cpf -> (status, token)`, `iniciar_login_cpf -> bool`, `verificar_cpf -> token|None` idênticos entre Task 1 e Task 3; `pagina_login(..., via=)`/`pagina_entrar(..., via=)` idênticos entre Task 2 e Task 3; campo `cpf` e actions `/entrar-cpf`/`/entrar-cpf-codigo` batem entre UI (Task 2) e handlers (Task 3). `subscribers.ativos`, `cpf.so_digitos`, `passwords.hash_senha`, `subscribers.criar_de_pagamento`/`definir_senha` verificados no repo.
