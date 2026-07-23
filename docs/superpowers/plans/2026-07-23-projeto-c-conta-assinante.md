# Projeto C — Conta do assinante & avisos — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans para executar tarefa a tarefa. Passos usam checkbox (`- [ ]`).

**Goal:** Limpar o fluxo de conta do assinante (`artigos.`), criar a página `/meus-dados` (com troca de celular por OTP), avisar o Dr. Diego por e-mail a cada venda, e aplicar 3 ajustes visuais no estoque.

**Architecture:** App Python stdlib, SQLite/Postgres via `db._conn()`. Camadas: `db`/`subscribers`/`auth_web` (dados+auth), `webhook_asaas` (pagamento), `site_web` (HTML), `serve` (rotas HTTP). Lógica nova vive em funções testáveis; `serve` só roteia.

**Tech Stack:** Python 3.12 stdlib, unittest, SQLite (teste), Resend (e-mail, já ativo), Z-API/deliver (WhatsApp).

## Global Constraints

- Só o host `artigos.` — não tocar `curso.`/ebook (Projetos A/B).
- Tema verde/ouro existente: tokens em `site_web.py:33` (`--verde #0e211a`, `--verde2 #14332a`, `--ouro #c9a227`, `--ouro2 #e7c766`, `--creme #f4f1e7`, `--suave #a9bcb2`). Não inventar paleta.
- Testes: `unittest` stdlib; externos (e-mail, WhatsApp) **mockados**; SQLite tmp (`DSCURSO_ARTIGOS_DB`), sem rede/API real.
- **Nunca** quebrar ativação de pagamento nem login: código novo em pagamento/OTP é `try/except` com log; validação antes de mutar.
- Escapar toda entrada de usuário no HTML (`_esc`).
- Imutabilidade: não mutar dicts recebidos; updates via SQL direto.

---

### Task 1: subscribers — atualizar contato e whatsapp

**Files:**
- Modify: `app/subscribers.py` (após `definir_senha`, ~linha 161)
- Test: `app/tests/test_subscribers.py`

**Interfaces:**
- Produces: `subscribers.atualizar_contato(id, nome, email)`, `subscribers.atualizar_whatsapp(id, novo)`, `subscribers.por_id(id)`

- [ ] **Passo 1: teste que falha**

Adicione ao `test_subscribers.py` (siga o `setUp` já existente do arquivo, que usa SQLite tmp):

```python
def test_atualizar_contato_e_whatsapp(self):
    s = subscribers.adicionar("Fulano", "5543999990000")
    subscribers.atualizar_contato(s["id"], "Fulano Silva", "f@x.com")
    r = subscribers.por_id(s["id"])
    self.assertEqual(r["nome"], "Fulano Silva")
    self.assertEqual(r["email"], "f@x.com")
    subscribers.atualizar_whatsapp(s["id"], "5541988887777")
    r = subscribers.por_id(s["id"])
    self.assertEqual(r["whatsapp"], "5541988887777")   # normalizado
    self.assertIsNone(subscribers.por_id("naoexiste"))
```

- [ ] **Passo 2: rodar e ver falhar**

Run: `cd app && python -m pytest tests/test_subscribers.py -q`
Esperado: FAIL (`atualizar_contato`/`por_id` não existem).

- [ ] **Passo 3: implementar**

Em `app/subscribers.py`:

```python
def por_id(id):
    _ensure()
    with db._conn() as c:
        r = c.execute("SELECT * FROM subscribers WHERE id=?", (id,)).fetchone()
    return dict(r) if r else None


def atualizar_contato(id, nome, email):
    """Atualiza nome e e-mail do assinante (edição na página de dados)."""
    _ensure()
    with db._conn() as c:
        c.execute("UPDATE subscribers SET nome=?, email=? WHERE id=?",
                  ((nome or "").strip(), (email or "").strip(), id))


def atualizar_whatsapp(id, novo):
    """Troca o número (normalizado). Só chamar após confirmação por OTP no número novo."""
    _ensure()
    with db._conn() as c:
        c.execute("UPDATE subscribers SET whatsapp=? WHERE id=?", (_norm(novo), id))
```

- [ ] **Passo 4: rodar e ver passar** — `python -m pytest tests/test_subscribers.py -q` → PASS
- [ ] **Passo 5: commit** — `git add app/subscribers.py app/tests/test_subscribers.py && git commit -m "feat(subscribers): atualizar_contato/atualizar_whatsapp/por_id"`

---

### Task 2: auth_web — troca de número por OTP

**Files:**
- Modify: `app/auth_web.py` (após `logout`, ~linha 134)
- Test: `app/tests/test_troca_numero.py` (novo)

**Interfaces:**
- Consumes: `subscribers.atualizar_whatsapp` (Task 1), `subscribers.por_whatsapp`, `_hash`, `_norm`, `db._conn`, `MAX_TENTATIVAS`, `CODIGO_TTL_MIN`
- Produces: `auth_web.iniciar_troca_numero(sub_id, novo_num, enviar_fn=None) -> "enviado"|"em_uso"|"invalido"`; `auth_web.confirmar_troca_numero(sub_id, antigo_num, novo_num, codigo) -> "ok"|"codigo_errado"|"expirado"|"bloqueado"`; `auth_web._migrar_sessoes_whatsapp(antigo, novo)`

- [ ] **Passo 1: teste que falha** — `app/tests/test_troca_numero.py` (novo):

```python
import os, re, sys, tempfile, importlib, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestTrocaNumero(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ.pop("DATABASE_URL", None)
        import db, subscribers, auth_web
        importlib.reload(db); importlib.reload(subscribers); importlib.reload(auth_web)
        self.db, self.subs, self.auth = db, subscribers, auth_web
        db.init()
        self.cap = {}
        self.fake = lambda num, msg: self.cap.update(
            num=num, code=re.search(r"\b(\d{6})\b", msg).group(1))

    def tearDown(self):
        import shutil; shutil.rmtree(self.tmp, ignore_errors=True)

    def test_troca_ok(self):
        s = self.subs.adicionar("Fulano", "5543999990000")
        self.assertEqual(self.auth.iniciar_troca_numero(s["id"], "5541988887777", self.fake), "enviado")
        self.assertEqual(self.cap["num"], "5541988887777")          # código foi pro número NOVO
        tok = self.auth._criar_sessao("5543999990000", "Fulano")     # sessão no número antigo
        st = self.auth.confirmar_troca_numero(s["id"], "5543999990000", "5541988887777", self.cap["code"])
        self.assertEqual(st, "ok")
        self.assertEqual(self.subs.por_id(s["id"])["whatsapp"], "5541988887777")
        self.assertEqual(self.auth.sessao(f"sid={tok}")["whatsapp"], "5541988887777")  # sessão migrada

    def test_codigo_errado(self):
        s = self.subs.adicionar("F", "5543999990000")
        self.auth.iniciar_troca_numero(s["id"], "5541988887777", self.fake)
        self.assertEqual(self.auth.confirmar_troca_numero(s["id"], "5543999990000", "5541988887777", "000000"), "codigo_errado")
        self.assertEqual(self.subs.por_id(s["id"])["whatsapp"], "5543999990000")  # não trocou

    def test_numero_de_outro_bloqueia(self):
        s = self.subs.adicionar("A", "5543999990000")
        self.subs.adicionar("B", "5541988887777")
        self.assertEqual(self.auth.iniciar_troca_numero(s["id"], "5541988887777", self.fake), "em_uso")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Passo 2: rodar e ver falhar** — `cd app && python -m pytest tests/test_troca_numero.py -q` → FAIL
- [ ] **Passo 3: implementar** — em `app/auth_web.py`:

```python
def _migrar_sessoes_whatsapp(antigo, novo):
    with db._conn() as c:
        c.execute("UPDATE sessions SET whatsapp=? WHERE whatsapp=?", (_norm(novo), _norm(antigo)))


def iniciar_troca_numero(sub_id, novo_num, enviar_fn=None):
    """Envia um código pro número NOVO p/ confirmar a troca. Reusa login_codes/TTL do OTP."""
    num = _norm(novo_num)
    if not num or len(num) < 10:
        return "invalido"
    dono = subscribers.por_whatsapp(num)
    if dono and dono.get("id") != sub_id:
        return "em_uso"
    codigo = f"{secrets.randbelow(1000000):06d}"
    expira = (datetime.now() + timedelta(minutes=CODIGO_TTL_MIN)).isoformat()
    with db._conn() as c:
        c.execute(
            """INSERT INTO login_codes (whatsapp,codigo_hash,expira,tentativas) VALUES (?,?,?,0)
               ON CONFLICT(whatsapp) DO UPDATE SET codigo_hash=excluded.codigo_hash,
                 expira=excluded.expira, tentativas=0""",
            (num, _hash(codigo), expira))
    msg = (f"🔐 Código para confirmar a troca do seu número na *{config.PRODUTO}*: *{codigo}*.\n"
           f"Válido por {CODIGO_TTL_MIN} minutos. Se não foi você, ignore.")
    fn = enviar_fn or _enviar_padrao
    try:
        fn(num, msg)
    except Exception as e:
        print(f"[troca] envio do código falhou: {e}", flush=True)
    return "enviado"


def confirmar_troca_numero(sub_id, antigo_num, novo_num, codigo):
    """Confere o código enviado ao número novo; sucesso -> troca o número + migra as sessões."""
    num = _norm(novo_num)
    with db._conn() as c:
        row = c.execute("SELECT * FROM login_codes WHERE whatsapp=?", (num,)).fetchone()
        if not row:
            return "expirado"
        if row["tentativas"] >= MAX_TENTATIVAS:
            return "bloqueado"
        if datetime.fromisoformat(row["expira"]) < datetime.now():
            c.execute("DELETE FROM login_codes WHERE whatsapp=?", (num,))
            return "expirado"
        if _hash(codigo) != row["codigo_hash"]:
            c.execute("UPDATE login_codes SET tentativas=tentativas+1 WHERE whatsapp=?", (num,))
            return "codigo_errado"
        c.execute("DELETE FROM login_codes WHERE whatsapp=?", (num,))
    subscribers.atualizar_whatsapp(sub_id, num)
    _migrar_sessoes_whatsapp(antigo_num, num)
    return "ok"
```

- [ ] **Passo 4: rodar e ver passar** — `python -m pytest tests/test_troca_numero.py -q` → PASS
- [ ] **Passo 5: commit** — `git add app/auth_web.py app/tests/test_troca_numero.py && git commit -m "feat(auth): troca de número por OTP no número novo + migração de sessão"`

---

### Task 3: aviso de venda por e-mail

**Files:**
- Modify: `app/config.py` (após `EMAIL_BACKEND`, ~linha 126)
- Modify: `app/webhook_asaas.py` (nova função + chamada no path "ativado", `:108`)
- Test: `app/tests/test_webhook.py`

**Interfaces:**
- Consumes: `email_send.enviar(to, assunto, html)`, `subscribers.ativos()`, `config.ADMIN_EMAIL`
- Produces: `config.ADMIN_EMAIL`; `webhook_asaas._avisar_venda(nome, plano, valor, contato, ativos)`

- [ ] **Passo 1: teste que falha** — em `test_webhook.py`, mockando `email_send.enviar`:

```python
def test_avisar_venda_monta_email(self):
    import webhook_asaas, email_send
    chamado = {}
    orig = email_send.enviar
    email_send.enviar = lambda to, assunto, html: chamado.update(to=to, assunto=assunto, html=html)
    try:
        webhook_asaas._avisar_venda("Fulano", "Anual", "960", "f@x.com", 37)
    finally:
        email_send.enviar = orig
    self.assertIn("Anual", chamado["assunto"])
    self.assertIn("Fulano", chamado["html"])
    self.assertIn("37", chamado["html"])

def test_avisar_venda_nao_propaga_erro(self):
    import webhook_asaas, email_send
    orig = email_send.enviar
    email_send.enviar = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("smtp down"))
    try:
        webhook_asaas._avisar_venda("F", "Mensal", "99", "x", 1)  # não pode levantar
    finally:
        email_send.enviar = orig
```

- [ ] **Passo 2: rodar e ver falhar** — `cd app && python -m pytest tests/test_webhook.py -q` → FAIL
- [ ] **Passo 3a: config** — em `app/config.py`, após `EMAIL_BACKEND`:

```python
# E-mail do admin (Dr. Diego) para avisos de venda. Env sobrescreve.
ADMIN_EMAIL = os.environ.get("DSCURSO_ADMIN_EMAIL") or "edson-diego@live.com"
```

- [ ] **Passo 3b: webhook** — em `app/webhook_asaas.py`, adicionar a função (perto de `_alertar_admin`):

```python
def _avisar_venda(nome, plano, valor, contato, ativos):
    """E-mail instantâneo ao admin quando uma venda ativa. Nunca pode quebrar a ativação."""
    try:
        import email_send
        esc = __import__("html").escape
        assunto = f"🎉 Nova venda — {plano} · R$ {valor}"
        corpo = (
            f'<div style="font-family:Georgia,serif;background:#0e211a;color:#e8efe9;'
            f'padding:28px;border-radius:14px;max-width:520px;margin:0 auto">'
            f'<h1 style="color:#e7c766;font-size:23px;margin:0 0 14px">🎉 Nova venda</h1>'
            f'<p style="margin:6px 0"><b>{esc(nome or "—")}</b></p>'
            f'<p style="margin:6px 0;color:#a9bcb2">Plano: <b style="color:#e8efe9">{esc(plano or "—")}</b> · '
            f'Valor: <b style="color:#e8efe9">R$ {esc(str(valor))}</b></p>'
            f'<p style="margin:6px 0;color:#a9bcb2">Contato: {esc(contato or "—")}</p>'
            f'<p style="margin:16px 0 0;color:#e7c766">Agora você tem <b>{ativos}</b> assinantes ativos.</p>'
            f'</div>')
        email_send.enviar(config.ADMIN_EMAIL, assunto, corpo)
    except Exception as e:
        print(f"[webhook] aviso de venda falhou: {e}", flush=True)
```

- [ ] **Passo 3c: chamada** — em `webhook_asaas._executar`, no path ATIVAR, logo antes de `return (200, "ativado")`:

```python
        _boas_vindas(whatsapp, nome, email, enviar_fn)
        try:
            _avisar_venda(nome, (plano.get("nome") or plano.get("slug") or "—"),
                          pay.get("value"), email or whatsapp, len(subscribers.ativos()))
        except Exception as e:
            print(f"[webhook] _avisar_venda: {e}", flush=True)
        return (200, "ativado")
```

- [ ] **Passo 4: rodar e ver passar** — `python -m pytest tests/test_webhook.py -q` → PASS
- [ ] **Passo 5: commit** — `git add app/config.py app/webhook_asaas.py app/tests/test_webhook.py && git commit -m "feat(webhook): e-mail ao admin a cada venda (config ADMIN_EMAIL); nunca quebra ativação"`

---

### Task 4: C1 nav + painel do curador em botões-card (tela /minha)

**Files:**
- Modify: `app/site_web.py` — `_topbar` (`:297`), `pagina_minha` (`:1028`), `_admin_nav` (`:528`), CSS (`:33+`)
- Test: `app/tests/test_site_web.py`

**Interfaces:**
- Produces: `_topbar(logado=False, atual="")`, `pagina_minha(sub, admin=False)` (corpo enxuto + painel em cards), `_admin_nav` sem "Minha conta"

- [ ] **Passo 1: teste que falha** — em `test_site_web.py`:

```python
def test_minha_enxuta_e_cards(self):
    import site_web
    html = site_web.pagina_minha({"nome": "Diego"}, admin=True)
    self.assertNotIn("Ir para o arquivo", html)     # não duplica o topo
    self.assertNotIn("Sair desta conta", html)
    self.assertIn("Meus dados", html)               # novo caminho
    self.assertIn("curbtn", html)                   # painel em botões-card
    self.assertIn("Agenda", html)                   # atalho novo incluído
    self.assertNotIn("Cancelar assinatura", html)   # cancelar saiu daqui

def test_topbar_omite_minha_conta_na_propria(self):
    import site_web
    self.assertNotIn(">Minha conta<", site_web._topbar(True, atual="/minha"))
    self.assertIn(">Minha conta<", site_web._topbar(True, atual="/artigos"))
```

- [ ] **Passo 2: rodar e ver falhar** — `cd app && python -m pytest tests/test_site_web.py -q` → FAIL

- [ ] **Passo 3a: `_topbar`** — trocar assinatura e o link condicional:

```python
def _topbar(logado=False, atual=""):
    minha = '' if atual == "/minha" else '<a class="plain" href="/minha">Minha conta</a>'
    direita = ('<a class="plain" href="/artigos">Arquivo</a>' + minha +
               '<a class="pill" href="/sair">Sair</a>'
               if logado else
               '<a class="plain" href="/#planos">Planos</a>'
               '<a class="pill" href="/entrar">Entrar</a>')
    return (f'<div class="wrap"><div class="top">'
            f'<a href="/"><div class="brand">'
            f'<span class="m">{_esc(MARCA)}</span><span class="c">{_esc(CRM)}</span></div></a>'
            f'<nav class="nav">{direita}</nav></div></div>')
```

E em `_pagina` (`:318`), repassar a rota: aceitar `atual=""` e passar a `_topbar(logado, atual)`. Ajustar a chamada de `pagina_minha` p/ `_pagina(..., atual="/minha")`.

- [ ] **Passo 3b: CSS dos cards** — adicionar ao bloco `<style>` (perto de `.infobox`, `:151`):

```css
.curgrid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:6px 0 4px}
.curbtn{display:flex;gap:12px;align-items:flex-start;text-decoration:none;background:rgba(201,162,39,.06);
  border:1px solid rgba(201,162,39,.28);border-radius:14px;padding:14px 15px;color:var(--creme);
  transition:transform .14s,border-color .14s,background .14s}
.curbtn:hover{transform:translateY(-2px);border-color:rgba(201,162,39,.65);background:rgba(201,162,39,.12)}
.curbtn:focus-visible{outline:2px solid var(--ouro2);outline-offset:2px}
.curbtn .ic{font-size:20px;line-height:1.1;flex:none}
.curbtn .nm{font-family:system-ui,sans-serif;font-size:14.5px;font-weight:700;color:var(--creme);display:block;margin-bottom:2px}
.curbtn .ds{font-family:system-ui,sans-serif;font-size:12px;color:var(--suave);line-height:1.4;display:block}
@media(max-width:520px){.curgrid{grid-template-columns:1fr}}
```

- [ ] **Passo 3c: `pagina_minha`** — corpo enxuto + painel em cards:

```python
def pagina_minha(sub, admin=False):
    def card(href, ic, nm, ds):
        return (f'<a class="curbtn" href="{href}"><span class="ic">{ic}</span>'
                f'<span><span class="nm">{nm}</span><span class="ds">{ds}</span></span></a>')
    admin_html = ('<p class="plabel" style="margin-top:18px;font-family:system-ui,sans-serif;'
                  'font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--ouro2)">Painel do curador</p>'
                  '<div class="curgrid">'
                  + card("/curadoria", "🔬", "Curadoria &amp; Estoque", "Varredura, seleção e fila de resumos")
                  + card("/agenda", "📅", "Agenda de envios", "O que sai cada dia da semana")
                  + card("/admin", "👥", "Assinantes", "Quem recebe e status das contas")
                  + card("/admin/whatsapp", "📱", "WhatsApp", "Conexão e envio das mensagens")
                  + '</div>') if admin else ""
    corpo = f"""
    <div class="wrap"><div class="panel">
      <h2 class="disp">Minha assinatura</h2>
      <p class="hint">Olá, {_esc(sub.get("nome") or "assinante")}. Sua assinatura está ativa.</p>
      {admin_html}
      <p style="margin:22px 0 0"><a class="cta ghost" href="/meus-dados">Meus dados</a></p>
    </div></div>"""
    return _pagina(f"Minha assinatura · {PRODUTO}", corpo, logado=True, atual="/minha",
                   meta_extra='<meta name="robots" content="noindex">')
```

- [ ] **Passo 3d: `_admin_nav`** — remover a linha do `'← Minha conta'` (o topo já leva).

- [ ] **Passo 4: rodar e ver passar** — `python -m pytest tests/test_site_web.py -q` → PASS
- [ ] **Passo 5: commit** — `git add app/site_web.py app/tests/test_site_web.py && git commit -m "feat(conta): /minha enxuta + painel do curador em cards (+Agenda); topbar única"`

---

### Task 5: C-UI estoque — cartões de número + chip de score

**Files:**
- Modify: `app/site_web.py` — `pagina_curadoria` (`stats` `:699`, item do candidato `:718-727`), CSS (`:33+`)
- Test: `app/tests/test_curadoria.py` ou `test_site_web.py`

**Interfaces:**
- Produces: helper `_chip_score(score) -> (classe, html)`; `stats` como cartões

- [ ] **Passo 1: teste que falha**:

```python
def test_estoque_cards_e_chip(self):
    import site_web
    cont = {"novo": 12, "selecionado": 4, "resumido": 31}
    reserva = [{"status": "pronto", "tema": "Obesidade", "titulo_pt": "X"}]
    cand = [{"id": "1", "tema": "Obesidade", "titulo": "T", "pergunta": "P",
             "fonte": "NEJM", "data": "2026-01-01", "score": 8.5, "doi": ""}]
    html = site_web.pagina_curadoria(cand, reserva, cont, "tok")
    self.assertIn("statcard", html)        # números viraram cartões
    self.assertIn("chip hi", html)         # score 8.5 -> chip verde (alto)
    self.assertIn("importância clínica", html)  # legenda do score
```

- [ ] **Passo 2: rodar e ver falhar** → FAIL

- [ ] **Passo 3a: CSS** — adicionar ao `<style>`:

```css
.statgroup{margin:0 0 16px}
.statgroup .gh{font-family:system-ui,sans-serif;font-size:13px;font-weight:700;color:var(--creme);margin:0 0 3px}
.statgroup .gsub{font-family:system-ui,sans-serif;font-size:12.5px;color:var(--suave);margin:0 0 10px}
.statcards{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.statcard{background:rgba(255,255,255,.035);border:1px solid rgba(233,225,198,.14);border-radius:14px;padding:15px 16px;position:relative;overflow:hidden}
.statcard.key::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:linear-gradient(180deg,var(--ouro2),var(--ouro))}
.statcard .num{font-family:var(--mono);font-size:28px;font-weight:700;color:var(--creme);font-variant-numeric:tabular-nums;line-height:1}
.statcard.key .num{color:var(--ouro2)}
.statcard .lb{font-family:system-ui,sans-serif;font-size:12.5px;font-weight:600;color:var(--creme);margin-top:6px}
.statcard .hp{font-family:system-ui,sans-serif;font-size:11.5px;color:var(--suave);margin-top:2px;line-height:1.35}
.legend{display:flex;gap:12px 18px;flex-wrap:wrap;align-items:center;background:rgba(255,255,255,.03);
  border:1px solid rgba(233,225,198,.14);border-radius:12px;padding:10px 14px;margin:14px 0;font-family:system-ui,sans-serif;font-size:12.5px;color:var(--suave)}
.chip{font-family:var(--mono);font-size:12px;font-weight:700;padding:3px 9px;border-radius:100px;display:inline-flex;align-items:center;gap:4px;font-variant-numeric:tabular-nums}
.chip.hi{background:linear-gradient(180deg,#22705a,#1a5344);color:#eafaf3;border:1px solid rgba(127,208,173,.5)}
.chip.md{background:rgba(201,162,39,.16);color:var(--ouro2);border:1px solid rgba(201,162,39,.45)}
.chip.lo{background:rgba(255,255,255,.05);color:var(--suave);border:1px solid rgba(233,225,198,.16)}
@media(max-width:560px){.statcards{grid-template-columns:1fr}}
```

- [ ] **Passo 3b: helper + stats** — em `pagina_curadoria`, trocar o bloco `stats` (`:699-703`) por cartões e adicionar o helper de chip (nível de módulo):

```python
def _chip_score(score):
    v = round(float(score or 0), 1)
    cls = "hi" if v >= 7 else ("md" if v >= 4 else "lo")
    estrela = "★ " if v >= 7 else ""
    return f'<span class="chip {cls}">{estrela}{v:g}</span>'
```

Dentro de `pagina_curadoria`, substituir a montagem de `stats`:

```python
    def sc(lb, n, hp, key=False):
        return (f'<div class="statcard{" key" if key else ""}"><div class="num">{n}</div>'
                f'<div class="lb">{lb}</div><div class="hp">{hp}</div></div>')
    stats = (
        '<div class="statgroup"><p class="gh">Candidatos da varredura</p>'
        '<p class="gsub">Estudos que a busca automática achou — ainda sem resumo.</p><div class="statcards">'
        + sc("Novos", contagem.get("novo", 0), "achados; você ainda não decidiu", key=True)
        + sc("Selecionados", contagem.get("selecionado", 0), "marcados p/ virar resumo")
        + sc("Já resumidos", contagem.get("resumido", 0), "a IA já transformou em resumo")
        + '</div></div>'
        '<div class="statgroup"><p class="gh">Estoque de resumos · fila de envio</p>'
        '<p class="gsub">Resumos prontos que vão pros assinantes.</p><div class="statcards">'
        + sc("Prontos p/ enviar", prontos, "esperando a vez na fila", key=True)
        + sc("Já enviados", enviados, "entregues aos assinantes")
        + sc("Total na reserva", len(reserva), "prontos + enviados")
        + '</div></div>')
```

E logo antes da `<p class="hint">{stats}` no `corpo`, trocar por `{stats}` direto (é HTML de bloco, não parágrafo) e inserir a legenda do score antes de `{form_lista}`:

```python
    legenda = ('<div class="legend"><span><b>score</b> = importância clínica que a IA dá, '
               'de 0 a 10 (só ordena a lista; o assinante não vê)</span>'
               '<span class="chip hi">★ 8</span> alta &nbsp;<span class="chip md">5</span> média '
               '&nbsp;<span class="chip lo">2</span> baixa</div>')
```

- [ ] **Passo 3c: item do candidato** — na montagem de `itens` (`:718-727`), trocar o texto `score X` por `{_chip_score(c.get("score"))}` posicionado à direita do título (usar um wrapper flex simples), e manter `fonte · data · DOI` em `cmeta` sem o score textual.

- [ ] **Passo 4: rodar e ver passar** → PASS
- [ ] **Passo 5: commit** — `git add app/site_web.py app/tests/*.py && git commit -m "feat(estoque): números em cartões + score em chip com legenda"`

---

### Task 6: página /meus-dados (render)

**Files:**
- Modify: `app/site_web.py` (nova função `pagina_meus_dados`, perto de `pagina_minha`)
- Test: `app/tests/test_site_web.py`

**Interfaces:**
- Consumes: `_pagina`, `_esc`
- Produces: `site_web.pagina_meus_dados(sub, msg="", etapa_troca=None, novo_num="")`

- [ ] **Passo 1: teste que falha**:

```python
def test_meus_dados_blocos(self):
    import site_web
    html = site_web.pagina_meus_dados({"nome": "D", "email": "d@x.com", "whatsapp": "5543999990000"})
    self.assertIn("salvar_contato", html)     # form de nome/e-mail
    self.assertIn("iniciar_troca", html)      # trocar número
    self.assertIn("Cancelar assinatura", html)  # cancelar vive aqui agora
    # etapa de código aparece quando pedido
    self.assertIn("confirmar_troca", site_web.pagina_meus_dados(
        {"nome": "D", "whatsapp": "x"}, etapa_troca="codigo", novo_num="5541988887777"))
```

- [ ] **Passo 2: rodar e ver falhar** → FAIL
- [ ] **Passo 3: implementar** — em `app/site_web.py`:

```python
def pagina_meus_dados(sub, msg="", etapa_troca=None, novo_num=""):
    msg_html = f'<div class="infobox">{_esc(msg)}</div>' if msg else ""
    if etapa_troca == "codigo":
        troca = f"""
        <p class="hint">Enviei um código por WhatsApp para <strong>{_esc(novo_num)}</strong>. Digite abaixo para confirmar.</p>
        <form method="post" action="/meus-dados">
          <input type="hidden" name="acao" value="confirmar_troca">
          <input type="hidden" name="novo_numero" value="{_esc(novo_num)}">
          <label>Código recebido</label>
          <input type="text" name="codigo" inputmode="numeric" maxlength="6" required>
          <button class="actbtn" type="submit">Confirmar novo número</button>
        </form>"""
    else:
        troca = f"""
        <p class="hint" style="margin-top:4px">Número atual: <strong>{_esc(sub.get("whatsapp",""))}</strong> — é onde você recebe os estudos e faz login.</p>
        <form method="post" action="/meus-dados">
          <input type="hidden" name="acao" value="iniciar_troca">
          <label>Novo número (com DDD)</label>
          <input type="tel" name="novo_numero" placeholder="5543999990000" required>
          <button class="actbtn ghost" type="submit">Trocar número</button>
          <p class="hint" style="margin-top:8px;font-size:13px">Enviaremos um código ao número novo para confirmar.</p>
        </form>"""
    corpo = f"""
    <div class="wrap"><div class="panel">
      <h2 class="disp">Meus dados</h2>
      {msg_html}
      <form method="post" action="/meus-dados" style="margin-bottom:26px">
        <input type="hidden" name="acao" value="salvar_contato">
        <label>Nome</label>
        <input type="text" name="nome" value="{_esc(sub.get("nome",""))}" required>
        <label>E-mail</label>
        <input type="text" name="email" value="{_esc(sub.get("email",""))}">
        <button class="actbtn" type="submit">Salvar</button>
      </form>
      <h3 class="disp" style="font-size:22px;color:var(--ouro2);margin:0 0 6px">Celular (WhatsApp)</h3>
      {troca}
      <hr style="border:none;border-top:1px solid rgba(233,225,198,.12);margin:30px 0 16px">
      <p class="hint" style="font-size:13px;color:var(--suave)">Não quer mais receber?
        <a href="/cancelar" style="color:#d69a8a">Cancelar assinatura</a></p>
    </div></div>"""
    return _pagina(f"Meus dados · {PRODUTO}", corpo, logado=True, atual="/meus-dados",
                   meta_extra='<meta name="robots" content="noindex">')
```

- [ ] **Passo 4: rodar e ver passar** → PASS
- [ ] **Passo 5: commit** — `git add app/site_web.py app/tests/test_site_web.py && git commit -m "feat(conta): página /meus-dados (contato + troca de número + cancelar)"`

---

### Task 7: serve.py — rotas /meus-dados (GET + POST)

**Files:**
- Modify: `app/serve.py` (GET perto de `/minha` `:239`; POST perto de `/cancelar` `:448`)

**Interfaces:**
- Consumes: `auth_web.sessao`, `auth_web.eh_admin`, `auth_web.iniciar_troca_numero`, `auth_web.confirmar_troca_numero`, `subscribers.por_whatsapp`, `subscribers.atualizar_contato`, `site_web.pagina_meus_dados`

Helpers reais confirmados no `serve.py`: `self._sessao()` (resolve a sessão → sub, usado em `/minha:240`), `self._html(s, code=200)` (`:272`), `self._redirect(location, token=None, clear=False)` (`:72`, **não** aceita `msg` — mostrar mensagem re-renderizando com `_html`), `g = lambda k: form.get(k,[""])[0]` (`:297`, existe no `do_POST`), `self._rate_ok(nome, maximo, janela)` (`:55`, já responde 429 e retorna False → handler dá `return`).

- [ ] **Passo 1: implementar GET** — no `do_GET`, junto do `/minha` (`:239`):

```python
        if path == "/meus-dados":
            sess = self._sessao()
            if not sess:
                return self._redirect("/entrar")
            import subscribers
            sub = subscribers.por_whatsapp(sess["whatsapp"]) or sess
            return self._html(site_web.pagina_meus_dados(sub))
```

- [ ] **Passo 2: implementar POST** — no `do_POST`, handler `/meus-dados` (mensagens re-renderizadas com `_html`, sem `_redirect(msg=)`):

```python
        if path == "/meus-dados":
            sess = self._sessao()
            if not sess:
                return self._redirect("/entrar")
            import subscribers, auth_web
            sub = subscribers.por_whatsapp(sess["whatsapp"])
            if not sub:
                return self._redirect("/entrar")
            acao = g("acao")
            if acao == "salvar_contato":
                subscribers.atualizar_contato(sub["id"], g("nome"), g("email"))
                return self._html(site_web.pagina_meus_dados(subscribers.por_id(sub["id"]), msg="Dados salvos."), 200)
            if acao == "iniciar_troca":
                if not self._rate_ok("otp", 5, 600):
                    return
                r = auth_web.iniciar_troca_numero(sub["id"], g("novo_numero"))
                if r == "enviado":
                    return self._html(site_web.pagina_meus_dados(sub, etapa_troca="codigo", novo_num=g("novo_numero")), 200)
                msg = "Número inválido." if r == "invalido" else "Esse número já é de outro assinante."
                return self._html(site_web.pagina_meus_dados(sub, msg=msg), 200)
            if acao == "confirmar_troca":
                if not self._rate_ok("otp", 5, 600):
                    return
                st = auth_web.confirmar_troca_numero(sub["id"], sess["whatsapp"], g("novo_numero"), g("codigo"))
                if st == "ok":
                    return self._html(site_web.pagina_meus_dados(subscribers.por_id(sub["id"]), msg="Número atualizado."), 200)
                erros = {"codigo_errado": "Código errado.", "expirado": "Código expirado, tente de novo.",
                         "bloqueado": "Muitas tentativas, peça um novo código."}
                return self._html(site_web.pagina_meus_dados(sub, etapa_troca="codigo",
                                  novo_num=g("novo_numero"), msg=erros.get(st, "Não deu.")), 200)
            return self._redirect("/meus-dados")
```

(A sessão migra o `whatsapp` no banco, mas o token do cookie continua o mesmo → `self._sessao()` segue válido após a troca.)

- [ ] **Passo 3: robots** — em `robots.txt` (`site_web.py:1191`), acrescentar `Disallow: /meus-dados`.

- [ ] **Passo 4: verificação manual** — rodar `python -m pytest -q` (suite inteira verde) e revisar o diff do `serve.py` contra os handlers `/minha`, `/curadoria`, `/cancelar` (mesma forma de sessão, `_html`, `_redirect`, `g`). Sem teste automatizado do `serve` (camada HTTP não é testada no repo).

- [ ] **Passo 5: commit** — `git add app/serve.py app/site_web.py && git commit -m "feat(conta): rotas /meus-dados (salvar contato, troca de número por OTP)"`

---

## Ordem e verificação final

Ordem: 1 → 2 → 3 → 4 → 5 → 6 → 7 (dados/auth/webhook antes da UI e do wiring). Ao fim: `cd app && python -m pytest -q` (tudo verde) e revisão de branch inteira. Deploy só depois da revisão final (nada vai pro ar antes).
