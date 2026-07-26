# Editar número + suporte internacional — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Suportar telefone internacional (E.164) sem quebrar os números BR, com um seletor de país (BR default) em 3 superfícies (adicionar cortesia, editar número no admin, checkout público), pra o admin corrigir o número do irmão (EUA) e permitir brasileiros no exterior.

**Architecture:** Fundação em `phone.py` (normalização canônica idempotente + helpers), consumida no envio (`deliver`), num widget reutilizável `_seletor_pais` (`site_web`) e nos handlers (`serve`). Lista de países curada em `paises.py`. Reusa `subscribers.atualizar_whatsapp` (já existe).

**Tech Stack:** Python 3 stdlib, unittest. Sem libs novas.

## Global Constraints

- **Testes:** `cd app && python3 -m unittest discover -s tests` (rodar de `app/`). Sem rede nos testes.
- **INVARIANTE CRÍTICA:** números **BR não podem regredir** — continuam canônicos `55…` (sem "+"), como hoje. Qualquer teste que prove isso é obrigatório.
- **`normalizar` canônico:** BR → dígitos `55…`; internacional (entrada com "+") → `+CC…` (mantém "+"); BR sem país (10–11 díg) → prepend `55`. **Idempotente** (normalizar 2x = igual).
- **`para_api(w)`** = `normalizar(w).lstrip("+")` (WhatsApp recebe só dígitos).
- **`montar_e164(dial, local)`** = `"+" + digitos(dial) + digitos(local)`.
- **`pais_dial` vazio → default `"55"`** (compat com form antigo/cache).
- **CPF e pagamento do checkout inalterados.**
- **`_seletor_pais` é UMA peça** reutilizada nos 3 forms (DRY).
- Attribution DESLIGADA — nenhum `Co-Authored-By` nos commits.
- Branch `feat/editar-numero-intl`. A Task 6 toca `pagina_assinar` (checkout) — o controller reconcilia com `feat/landing-copy-pizza` no merge (não é uma task).

---

### Task 1: `phone.py` — normalização canônica + helpers

**Files:**
- Modify: `app/phone.py` (reescreve `normalizar`, adiciona `para_api`, `montar_e164`)
- Test: `app/tests/test_phone.py` (criar)

**Interfaces:**
- Produces: `phone.normalizar(w) -> str` (canônico); `phone.para_api(w) -> str` (só dígitos); `phone.montar_e164(dial, local) -> str` (`+<dial><digitos>`).

- [ ] **Step 1: Escrever os testes que falham**

```python
# app/tests/test_phone.py
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import phone

class TestNormalizar(unittest.TestCase):
    def test_br_sem_pais_ganha_55(self):
        self.assertEqual(phone.normalizar("(43) 99999-0000"), "5543999990000")
    def test_br_com_mais_55_vira_digitos(self):
        self.assertEqual(phone.normalizar("+55 43 99999-0000"), "5543999990000")
    def test_br_ja_normalizado_inalterado(self):
        self.assertEqual(phone.normalizar("5543999990000"), "5543999990000")
    def test_eua_com_mais_mantem_e_nao_ganha_55(self):
        self.assertEqual(phone.normalizar("+1 (305) 555-1234"), "+13055551234")
    def test_idempotente_eua(self):
        once = phone.normalizar("+1 (305) 555-1234")
        self.assertEqual(phone.normalizar(once), once)   # +13055551234 -> +13055551234
    def test_idempotente_br(self):
        once = phone.normalizar("43 99999-0000")
        self.assertEqual(phone.normalizar(once), once)
    def test_vazio(self):
        self.assertEqual(phone.normalizar(""), "")

class TestParaApi(unittest.TestCase):
    def test_tira_mais_internacional(self):
        self.assertEqual(phone.para_api("+13055551234"), "13055551234")
    def test_br_inalterado(self):
        self.assertEqual(phone.para_api("5543999990000"), "5543999990000")

class TestMontarE164(unittest.TestCase):
    def test_junta_dial_e_local(self):
        self.assertEqual(phone.montar_e164("1", "(305) 555-1234"), "+13055551234")
    def test_br(self):
        self.assertEqual(phone.montar_e164("55", "43 99999-0000"), "+5543999990000")

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd app && python3 -m unittest tests.test_phone -v`
Expected: FAIL (`para_api`/`montar_e164` inexistentes; EUA vira `551…` no normalizar antigo).

- [ ] **Step 3: Implementar** — substituir TODO o `app/phone.py`

```python
"""Normalização de número de WhatsApp (E.164 canônico).
- BR: dígitos '55'+DDD+número (sem '+', igual ao legado). Números de 10-11 dígitos
  sem país ganham o 55.
- Internacional: entrada com '+' mantém o '+CC…' (idempotente). Só o Brasil é +55,
  então '+55…' é canonizado de volta pra '55…' (consistente com o legado BR).
O WhatsApp recebe só dígitos (ver para_api)."""


def normalizar(w):
    w = (w or "").strip()
    intl = w.startswith("+")
    d = "".join(c for c in w if c.isdigit())
    if intl:
        return d if d.startswith("55") else "+" + d
    if len(d) in (10, 11):
        return "55" + d
    return d


def para_api(w):
    """Formato que o WhatsApp aceita: só dígitos com código do país (sem '+')."""
    return normalizar(w).lstrip("+")


def montar_e164(dial, local):
    """Junta o código do país (do seletor) + número local -> '+<dial><digitos>'."""
    d = "".join(c for c in (local or "") if c.isdigit())
    dd = "".join(c for c in (dial or "") if c.isdigit())
    return "+" + dd + d
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd app && python3 -m unittest tests.test_phone -v` → PASS.
Depois regressão: `cd app && python3 -m unittest tests.test_subscribers tests.test_troca_numero -v` → PASS (BR intocado). Se algum quebrar, é sinal de regressão BR — investigar antes de commitar.

- [ ] **Step 5: Commit**

```bash
git add app/phone.py app/tests/test_phone.py
git commit -m "feat(numero-intl): phone.normalizar canônico (BR 55…, intl +CC…) + para_api + montar_e164"
```

---

### Task 2: `deliver.py` — WhatsApp recebe só dígitos (`para_api`)

**Files:**
- Modify: `app/deliver.py` (todos os builders de payload que colocam o número)
- Test: `app/tests/test_deliver_phone.py` (criar)

**Interfaces:**
- Consumes: `phone.para_api` (Task 1).
- Produces: todo payload de envio usa o número via `phone.para_api(...)` (sem "+").

- [ ] **Step 1: Localizar todos os builders de payload**

Run: `cd app && grep -n '"number"\|"phone"\|numero\|whatsapp' deliver.py`
Espera-se: `_evolution_texto_payload` (~l.33), `_evolution_media_payload` (~l.37) usam `{"number": whatsapp}`; e o(s) payload(s) Z-API (`_zapi_*`) usam `{"phone": …}`. Cobrir TODOS (texto, mídia/PDF, áudio) nos dois backends.

- [ ] **Step 2: Escrever o teste que falha**

```python
# app/tests/test_deliver_phone.py
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import deliver

class TestPayloadPhone(unittest.TestCase):
    def test_evolution_texto_tira_mais(self):
        p = deliver._evolution_texto_payload("+13055551234", "oi")
        self.assertEqual(p["number"], "13055551234")
    def test_evolution_texto_br_inalterado(self):
        p = deliver._evolution_texto_payload("5543999990000", "oi")
        self.assertEqual(p["number"], "5543999990000")
    def test_evolution_media_tira_mais(self):
        p = deliver._evolution_media_payload("+13055551234", "/tmp/x.pdf", "cap")
        self.assertEqual(p["number"], "13055551234")
```
(Se os payloads Z-API forem funções isoladas, adicionar casos análogos pra elas.)

- [ ] **Step 3: Rodar e ver falhar**

Run: `cd app && python3 -m unittest tests.test_deliver_phone -v` → FAIL (payload devolve `+13055551234`).

- [ ] **Step 4: Implementar**

Em cada builder de payload, trocar o número cru por `phone.para_api(...)`. Ex.:
```python
def _evolution_texto_payload(whatsapp, msg):
    return {"number": phone.para_api(whatsapp), "text": msg}

def _evolution_media_payload(whatsapp, pdf_path, caption):
    nome = (re.sub(r"[^\w-]", "_", caption)[:40] or "documento") + ".pdf"
    return {"number": phone.para_api(whatsapp), "mediatype": "document",
            "mimetype": "application/pdf", ...}   # resto igual
```
Aplicar o mesmo em qualquer payload de **áudio** e nos builders **Z-API** (`"phone": phone.para_api(...)`). Garantir `import phone` no topo (provavelmente já existe).

- [ ] **Step 5: Rodar e ver passar + regressão**

Run: `cd app && python3 -m unittest tests.test_deliver_phone -v` → PASS.
Run: `cd app && python3 -m unittest discover -s tests` → tudo verde.

- [ ] **Step 6: Commit**

```bash
git add app/deliver.py app/tests/test_deliver_phone.py
git commit -m "feat(numero-intl): payload do WhatsApp usa phone.para_api (só dígitos, suporta internacional)"
```

---

### Task 3: `paises.py` — lista curada

**Files:**
- Create: `app/paises.py`
- Test: `app/tests/test_paises.py` (criar)

**Interfaces:**
- Produces: `paises.PAISES: list[tuple[str,str,str,str]]` = `(iso, nome, bandeira, dial)`; Brasil é o 1º.

- [ ] **Step 1: Escrever o teste que falha**

```python
# app/tests/test_paises.py
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import paises

class TestPaises(unittest.TestCase):
    def test_brasil_primeiro(self):
        self.assertEqual(paises.PAISES[0][0], "BR")
        self.assertEqual(paises.PAISES[0][3], "55")
    def test_tem_eua_e_portugal(self):
        dials = {iso: dial for iso, _, _, dial in paises.PAISES}
        self.assertEqual(dials["US"], "1")
        self.assertEqual(dials["PT"], "351")
    def test_estrutura_4_campos(self):
        for p in paises.PAISES:
            self.assertEqual(len(p), 4)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd app && python3 -m unittest tests.test_paises -v` → FAIL (módulo inexistente).

- [ ] **Step 3: Implementar**

```python
# app/paises.py
"""Lista curada de países p/ o seletor de telefone. (iso, nome, bandeira, dial).
Brasil é o 1º (default no seletor). Adicionar país = 1 linha."""
PAISES = [
    ("BR", "Brasil", "🇧🇷", "55"), ("US", "Estados Unidos", "🇺🇸", "1"),
    ("PT", "Portugal", "🇵🇹", "351"), ("GB", "Reino Unido", "🇬🇧", "44"),
    ("ES", "Espanha", "🇪🇸", "34"), ("AR", "Argentina", "🇦🇷", "54"),
    ("CA", "Canadá", "🇨🇦", "1"), ("FR", "França", "🇫🇷", "33"),
    ("DE", "Alemanha", "🇩🇪", "49"), ("IT", "Itália", "🇮🇹", "39"),
    ("MX", "México", "🇲🇽", "52"), ("CL", "Chile", "🇨🇱", "56"),
    ("CO", "Colômbia", "🇨🇴", "57"), ("PY", "Paraguai", "🇵🇾", "595"),
    ("UY", "Uruguai", "🇺🇾", "598"), ("JP", "Japão", "🇯🇵", "81"),
    ("AU", "Austrália", "🇦🇺", "61"), ("CH", "Suíça", "🇨🇭", "41"),
    ("NL", "Holanda", "🇳🇱", "31"), ("IE", "Irlanda", "🇮🇪", "353"),
]
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd app && python3 -m unittest tests.test_paises -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add app/paises.py app/tests/test_paises.py
git commit -m "feat(numero-intl): paises.py (lista curada, Brasil default)"
```

---

### Task 4: `site_web._seletor_pais` widget + form "Adicionar cortesia"

**Files:**
- Modify: `app/site_web.py` (novo helper `_seletor_pais`; usar no form de cortesia ~l.888-892)
- Modify: `app/serve.py` (handler `acao=adicionar` ~l.461 combina país+local)
- Test: `app/tests/test_site_web.py` (adicionar caso do seletor)

**Interfaces:**
- Consumes: `paises.PAISES` (Task 3), `phone.montar_e164` (Task 1).
- Produces: `site_web._seletor_pais(selecionado="BR") -> str` (HTML `<select name="pais_dial">`, opção `selecionado` com `selected`). Usado nas Tasks 4/5/6.

- [ ] **Step 1: Escrever o teste que falha**

```python
# app/tests/test_site_web.py  (adicionar)
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import site_web

class TestSeletorPais(unittest.TestCase):
    def test_renderiza_com_br_selecionado(self):
        html = site_web._seletor_pais()
        self.assertIn('name="pais_dial"', html)
        self.assertIn("Brasil", html)
        self.assertIn('value="55" selected', html)
        self.assertIn("Estados Unidos", html)   # tem opção internacional
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd app && python3 -m unittest tests.test_site_web.TestSeletorPais -v` → FAIL (`_seletor_pais` inexistente).

- [ ] **Step 3: Implementar**

Em `app/site_web.py`, adicionar o helper (perto dos outros helpers de render, ex.: junto de `_esc`):
```python
def _seletor_pais(selecionado="BR"):
    import paises
    opts = "".join(
        f'<option value="{dial}"{" selected" if iso == selecionado else ""}>{bandeira} {nome} (+{dial})</option>'
        for iso, nome, bandeira, dial in paises.PAISES)
    return f'<select name="pais_dial">{opts}</select>'
```
No form "Adicionar cortesia" (~l.890), colocar o seletor antes do input de número e ajustar o label:
```html
<label>País</label>{_seletor_pais()}
<label>WhatsApp</label><input type="text" name="whatsapp" placeholder="número (com DDD, se BR)">
```

Em `app/serve.py`, no `acao == "adicionar"` (~l.461):
```python
elif acao == "adicionar":
    novo = _phone.montar_e164(g("pais_dial") or "55", g("whatsapp"))
    subscribers.adicionar(g("nome"), novo)
```
(garantir o import do módulo `phone` no `serve.py` — provavelmente já importado como `phone`; usar o nome usado no arquivo.)

- [ ] **Step 4: Rodar e ver passar + regressão**

Run: `cd app && python3 -m unittest tests.test_site_web -v` → PASS (novo + render existentes).
Run: `cd app && python3 -m unittest discover -s tests` → verde.

- [ ] **Step 5: Commit**

```bash
git add app/site_web.py app/serve.py app/tests/test_site_web.py
git commit -m "feat(numero-intl): _seletor_pais + seletor no 'adicionar cortesia' (admin)"
```

---

### Task 5: Admin "✏️ Editar número" (modal + rota) — arruma o irmão

**Files:**
- Modify: `app/site_web.py` (ação/modal "editar número" na lista de assinantes do `/admin`)
- Modify: `app/serve.py` (rota `acao=editar_numero`, junto de `remover`/`remover_confirmar`)
- Test: `app/tests/test_editar_numero.py` (criar)

**Interfaces:**
- Consumes: `_seletor_pais` (Task 4), `phone.montar_e164` (Task 1), `subscribers.atualizar_whatsapp`/`por_whatsapp` (existentes).

- [ ] **Step 1: Escrever o teste que falha**

```python
# app/tests/test_editar_numero.py  (banco temp, padrão do repo)
import os, sys, unittest, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

class TestEditarNumero(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ.pop("DATABASE_URL", None)
        import importlib, config as _c; importlib.reload(_c)
        import db as _db; importlib.reload(_db)
        import subscribers as _s; importlib.reload(_s)
        self.db, self.subs = _db, _s; _db.init()
    def tearDown(self):
        import shutil; shutil.rmtree(self.tmp, ignore_errors=True)

    def test_atualiza_para_numero_eua(self):
        s = self.subs.adicionar("Irmão", "5511999998888")   # cadastrado (BR mangled p/ simular)
        import phone
        novo = phone.montar_e164("1", "(305) 555-1234")      # +13055551234
        self.subs.atualizar_whatsapp(s["id"], novo)
        got = self.subs.por_whatsapp("+1 305 555 1234")
        self.assertIsNotNone(got)
        self.assertEqual(got["id"], s["id"])                 # casa pelo internacional
        self.assertEqual(phone.para_api(got["whatsapp"]), "13055551234")
```
(Este teste prova a mecânica de dados/normalização da edição. O handler de rota é glue fina — testar via render/site_web se o repo tiver o padrão.)

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd app && python3 -m unittest tests.test_editar_numero -v` → FALHA antes do fix do `normalizar`? Não — depende da Task 1. Como a Task 1 já entrou, o teste deve refletir a mecânica; se `atualizar_whatsapp` já existe e `normalizar` é o novo, ele valida a integração. Se passar de primeira, adicionar a asserção de colisão (abaixo) que exige o handler.

- [ ] **Step 3: Implementar**

`app/serve.py` — junto de `acao == "remover"` (~l.462):
```python
elif acao == "editar_numero":
    novo = _phone.montar_e164(g("pais_dial") or "55", g("numero"))
    outro = subscribers.por_whatsapp(novo)
    if outro and outro["id"] != g("id"):
        msg = "Esse número já é de outro assinante."
    else:
        subscribers.atualizar_whatsapp(g("id"), novo)
        msg = "Número atualizado."
```
(a auth admin dessa rota já é feita no bloco das ações vizinhas — confirmar que `editar_numero` cai dentro dela.)

`app/site_web.py` — na lista de assinantes do `/admin`, cada linha ganha uma ação "✏️ Editar número" que revela um form (padrão dos modais admin existentes, ex.: o de remover): 
```html
<form method="post" action="/admin" style="...">
  <input type="hidden" name="token" value="{tk}">
  <input type="hidden" name="acao" value="editar_numero">
  <input type="hidden" name="id" value="{_esc(s['id'])}">
  <label>País</label>{_seletor_pais()}
  <label>Novo número</label><input type="text" name="numero">
  <button class="actbtn" type="submit">Salvar número</button>
</form>
```
(seguir o layout/estilo dos controles admin já presentes; não inventar design novo.)

- [ ] **Step 4: Rodar e ver passar + regressão**

Run: `cd app && python3 -m unittest tests.test_editar_numero -v` → PASS.
Run: `cd app && python3 -m unittest discover -s tests` → verde.

- [ ] **Step 5: Commit**

```bash
git add app/serve.py app/site_web.py app/tests/test_editar_numero.py
git commit -m "feat(numero-intl): modal admin 'editar número' (seletor de país) + rota editar_numero"
```

---

### Task 6: Checkout público (`/assinar`) — seletor de país

**Files:**
- Modify: `app/site_web.py` (`pagina_assinar`, form `/assinar` ~l.1459-1488: seletor ao lado do WhatsApp)
- Modify: `app/serve.py` (`_post_assinar` ~l.756-762 combina país+local)
- Test: `app/tests/test_site_web.py` (render) + `app/tests/test_checkout_numero.py` (combine)

**Interfaces:**
- Consumes: `_seletor_pais` (Task 4), `phone.montar_e164` (Task 1). CPF/pagamento inalterados.

- [ ] **Step 1: Escrever os testes que falham**

```python
# app/tests/test_site_web.py  (adicionar)
class TestCheckoutSeletor(unittest.TestCase):
    def test_pagina_assinar_tem_seletor(self):
        html = site_web.pagina_assinar("anual")
        self.assertIn('name="pais_dial"', html)
        self.assertIn('name="cpf"', html)        # CPF continua no form
```
```python
# app/tests/test_checkout_numero.py
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import phone
class TestCheckoutNumero(unittest.TestCase):
    def test_monta_whatsapp_do_pais(self):
        # simula o combine que o _post_assinar faz
        got = phone.montar_e164("1" or "55", "(305) 555-1234")
        self.assertEqual(got, "+13055551234")
    def test_default_br_quando_pais_vazio(self):
        got = phone.montar_e164("" or "55", "43 99999-0000")
        self.assertEqual(got, "+5543999990000")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd app && python3 -m unittest tests.test_site_web.TestCheckoutSeletor tests.test_checkout_numero -v` → FAIL (form sem `pais_dial`).

- [ ] **Step 3: Implementar**

`app/site_web.py` `pagina_assinar` (form `/assinar`, perto do campo WhatsApp ~l.1469-1488): adicionar antes do input de WhatsApp:
```html
<div class="field"><label>País</label>{_seletor_pais()}</div>
```
(manter o campo WhatsApp, CPF, nome como estão.)

`app/serve.py` `_post_assinar` (~l.756-762): trocar a montagem do whatsapp:
```python
dados = {..., "cpf": g("cpf").strip(),
         "whatsapp": _phone.montar_e164(g("pais_dial") or "55", g("whatsapp"))}
```
(resto do fluxo — pending, montar_checkout, Asaas — inalterado.)

- [ ] **Step 4: Rodar e ver passar + regressão**

Run: `cd app && python3 -m unittest tests.test_site_web tests.test_checkout_numero -v` → PASS.
Run: `cd app && python3 -m unittest discover -s tests` → verde.

- [ ] **Step 5: Commit**

```bash
git add app/site_web.py app/serve.py app/tests/test_site_web.py app/tests/test_checkout_numero.py
git commit -m "feat(numero-intl): seletor de país no checkout público (/assinar); CPF/pagamento inalterados"
```

---

## Depois da implementação (operacional, não é task de código)
- **Arrumar o irmão:** no `/admin` (assinantes), abrir "✏️ Editar número" do registro do irmão → escolher 🇺🇸 Estados Unidos (+1) → digitar o número dele → salvar. Testar mandando um estudo.
- **Deploy:** merge na main + push + EasyPanel (como no [[easypanel-deploy-curso]]).
- **Checkout na landing:** quando a `feat/landing-copy-pizza` for mexer no checkout, ela rebaseia na main (já com `paises.py`/`_seletor_pais`) e reusa a peça — o controller concilia se encostar na mesma região.

## Self-Review
- **Cobertura do spec:** normalizar canônico (T1) · para_api no envio (T2) · paises curada (T3) · _seletor_pais + cortesia (T4) · editar número admin (T5) · checkout público (T6). montar_e164 (T1) usado em T4/5/6. ✓
- **Placeholders:** nenhum "TBD"; os pontos de UI dizem "seguir o estilo existente" (deferimento intencional ao padrão do arquivo, não lacuna). Códigos concretos em cada step.
- **Consistência de tipos:** `normalizar`/`para_api`/`montar_e164` (T1) e `_seletor_pais` (T4) têm as mesmas assinaturas em todos os consumidores. `pais_dial` sempre com fallback `"55"`.
- **Invariante BR:** T1 Step 4 roda regressão de subscribers/troca_numero; T2/T4/T5/T6 rodam a suíte inteira. Qualquer regressão BR trava o commit.
- **Risco:** o nome do módulo phone no `serve.py` (`phone` vs `_phone`) — o implementer confirma o alias real no arquivo antes de usar (grep `import phone`).
