# Admin de preços editáveis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Tela `/admin/precos` pra o Diego mudar o preço do Mensal e do Anual de forma autônoma (sem código/redeploy); o valor editado vale na hora nas vendas novas, com "R$ X"/nota derivados do número, e "voltar ao padrão" por plano.

**Architecture:** Approach A — resolver no `config`: o preço vive em `settings` (`preco_base_<slug>`, via `db.get_config`/`set_config`) e `config.plano_por_slug`/`planos_venda`/`plano_por_base` aplicam o override devolvendo uma CÓPIA do plano com `base`/`base_pos` trocados e `preco`/`nota` re-derivados. Todos os consumidores (landing, /assinar, checkout, webhook, régua) passam a ver o preço vigente. Sem override salvo, o comportamento é idêntico ao de hoje.

**Tech Stack:** Python 3 stdlib, sqlite via `db.py` (`settings` k/v já existe), reuso de `pricing`/`site_web`/`serve`. Sem dependências novas.

## Global Constraints

- **Worktree:** `/Users/diegosilva/dev/curso-longevidade/.claude/worktrees/precos-lancamento`, branch `precos-lancamento`. Testes: `cd app && python3 -m unittest discover -s tests`. **Baseline = 741 testes verdes.**
- **Repo multi-agente:** stagear só os arquivos de cada task; **nunca** `git add -A`.
- **DINHEIRO REAL:** o valor editado é o cobrado. Validar entrada (número > 0). Sem push/deploy neste plano.
- **Decisões (spec 2026-07-28):** edita só o número (Mensal/Anual); "R$ X"/nota derivam; "voltar ao padrão" por plano; cupom LANCAMENTO segue −R$500 fixo sobre o vigente; assinantes atuais intocados (renovação = `valor_contratado`).
- **Contrato de derivação:** `preco` = estilo `"R$ 1.497"` (sem centavos, milhar com "."); `nota` do **anual** = `f"≈ R$ {round(base/12)}/mês · em até 12x sem juros"`, dos outros = `""`.
- **Sem override, tudo idêntico:** `get_config` é defensivo (default se faltar tabela) e o resolver devolve cópia dos valores do código — a suíte 741 segue verde.

## File Structure

- `app/config.py` — **modificar**: `parse_preco`, `_preco_str`, `_nota_derivada`, `_preco_override`, `_aplicar_override`; `plano_por_slug`/`plano_por_base` override-aware; `planos_venda()` novo.
- `app/site_web.py` — **modificar**: `pagina_precos` novo; link 💰 no `_admin_nav`; landing (`:434`) e `_pick_planos` (`:1836`) passam a usar `config.planos_venda()`.
- `app/serve.py` — **modificar**: rotas GET/POST `/admin/precos`.
- `app/tests/test_admin_precos.py` — **criar**.

---

### Task 1: config — resolver override-aware + `parse_preco`

**Files:**
- Modify: `app/config.py` (perto de `PLANOS`/`plano_por_slug`, ~linha 100)
- Test: `app/tests/test_admin_precos.py` (criar)

**Interfaces:**
- Produces:
  - `parse_preco(s) -> float | None` (número > 0 com ≤2 casas; senão None)
  - `plano_por_slug(slug)` e `plano_por_base(valor)` passam a aplicar o override (devolvem cópia)
  - `planos_venda() -> list[dict]` (planos não-ocultos, override aplicado)
- Consumes: `db.get_config` (lazy import).

- [ ] **Step 1: Write the failing test** — criar `app/tests/test_admin_precos.py`:

```python
"""Admin de preços editáveis (resolver + página + rotas). Standalone."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _reload_db(tmp):
    os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(tmp, "t.db")
    os.environ.pop("DATABASE_URL", None)
    import importlib, db as _db
    importlib.reload(_db)
    _db.init()
    return _db


def _snapshot_env():
    return (os.environ.get("DSCURSO_ARTIGOS_DB"), os.environ.get("DATABASE_URL"))


def _restore_db(snap):
    import importlib
    a, d = snap
    if a is None:
        os.environ.pop("DSCURSO_ARTIGOS_DB", None)
    else:
        os.environ["DSCURSO_ARTIGOS_DB"] = a
    if d is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = d
    import db as _db
    importlib.reload(_db)


class TestParsePreco(unittest.TestCase):
    def test_valido(self):
        import config
        self.assertEqual(config.parse_preco("1600"), 1600.0)
        self.assertEqual(config.parse_preco("1600,50"), 1600.5)
        self.assertEqual(config.parse_preco(" 1497.00 "), 1497.0)

    def test_invalido(self):
        import config
        for bad in ("", "0", "-5", "abc", None, "1.2.3"):
            self.assertIsNone(config.parse_preco(bad))


class TestPrecoResolver(unittest.TestCase):
    def setUp(self):
        self.snap = _snapshot_env()
        self.tmp = tempfile.mkdtemp()
        self.db = _reload_db(self.tmp)
        import importlib, config
        importlib.reload(config)
        self.cfg = config

    def tearDown(self):
        import shutil
        _restore_db(self.snap)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sem_override_usa_default(self):
        pl = self.cfg.plano_por_slug("anual")
        self.assertEqual(pl["base"], 1497.0)
        self.assertEqual(pl["preco"], "R$ 1.497")

    def test_override_aplica_e_deriva(self):
        self.db.set_config("preco_base_anual", "1600")
        pl = self.cfg.plano_por_slug("anual")
        self.assertEqual(pl["base"], 1600.0)
        self.assertEqual(pl["base_pos"], 1600.0)
        self.assertEqual(pl["preco"], "R$ 1.600")
        self.assertEqual(pl["nota"], "≈ R$ 133/mês · em até 12x sem juros")   # round(1600/12)=133
        mensal = self.cfg.plano_por_slug("mensal")
        self.db.set_config("preco_base_mensal", "159")
        mensal = self.cfg.plano_por_slug("mensal")
        self.assertEqual(mensal["base"], 159.0)
        self.assertEqual(mensal["preco"], "R$ 159")
        self.assertEqual(mensal["nota"], "")

    def test_override_nao_muta_PLANOS(self):
        self.db.set_config("preco_base_anual", "1600")
        self.cfg.plano_por_slug("anual")
        cru = next(p for p in self.cfg.PLANOS if p["slug"] == "anual")
        self.assertEqual(cru["base"], 1497.0)                # PLANOS intacto

    def test_planos_venda_aplica_override(self):
        self.db.set_config("preco_base_anual", "1600")
        venda = {p["slug"]: p for p in self.cfg.planos_venda()}
        self.assertNotIn("teste", venda)                     # ocultos fora
        self.assertEqual(venda["anual"]["base"], 1600.0)

    def test_plano_por_base_enxerga_override(self):
        self.db.set_config("preco_base_anual", "1600")
        self.assertEqual(self.cfg.plano_por_base(1600.0)["slug"], "anual")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_admin_precos.TestParsePreco tests.test_admin_precos.TestPrecoResolver -v`
Expected: FAIL (`parse_preco`/`planos_venda` inexistentes; override não aplicado).

- [ ] **Step 3: Write minimal implementation** — em `app/config.py`, perto de `plano_por_slug` (~linha 100):

```python
def parse_preco(s):
    """Número > 0 com no máx. 2 casas (aceita vírgula ou ponto). None se inválido."""
    if s is None:
        return None
    try:
        v = round(float(str(s).replace(",", ".").strip()), 2)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _preco_str(base):
    """Estilo 'R$ 1.497' (sem centavos, milhar com '.')."""
    return "R$ " + f"{float(base):,.0f}".replace(",", ".")


def _nota_derivada(slug, base):
    if slug == "anual":
        return f"≈ R$ {round(float(base) / 12)}/mês · em até 12x sem juros"
    return ""


def _preco_override(slug):
    """Override salvo em settings (float > 0) ou None. Defensivo: qualquer falha -> None."""
    try:
        import db
        return parse_preco(db.get_config(f"preco_base_{slug}", ""))
    except Exception:
        return None


def _aplicar_override(plano):
    """CÓPIA do plano com base/base_pos e textos derivados do override (se houver).
    Sem override -> cópia com os valores do código (nunca muta PLANOS)."""
    p = dict(plano)
    ov = _preco_override(plano["slug"])
    if ov is None:
        return p
    p["base"] = ov
    p["preco"] = _preco_str(ov)
    p["nota"] = _nota_derivada(plano["slug"], ov)
    if "base_pos" in plano:
        p["base_pos"] = ov
        p["preco_pos"] = _preco_str(ov)
    if "nota_pos" in plano:
        p["nota_pos"] = _nota_derivada(plano["slug"], ov)
    return p
```

Trocar `plano_por_slug` e `plano_por_base` p/ aplicar o override, e adicionar `planos_venda`:

```python
def plano_por_slug(slug):
    for p in PLANOS:
        if p["slug"] == slug:
            return _aplicar_override(p)
    return None


def planos_venda():
    """Planos visíveis (não ocultos) com o preço vigente (override aplicado). P/ a landing."""
    return [_aplicar_override(p) for p in PLANOS if not p.get("oculto")]


def plano_por_base(valor):
    """Casa o valor pago com a base VIGENTE do plano (override aplicado)."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    for p in PLANOS:
        pr = _aplicar_override(p)
        if abs(float(pr["base"]) - v) < 0.01:
            return pr
    return None
```

*(Manter `plano_por_cycle` como está — não depende de preço.)*

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_admin_precos.TestParsePreco tests.test_admin_precos.TestPrecoResolver -v`
Expected: PASS (8 testes).

- [ ] **Step 5: Rodar a suíte inteira (regressão do resolver)**

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -6`
Expected: `OK` (741 + 8 = 749). Sem override salvo, `plano_por_slug`/`plano_por_base` devolvem os defaults do código — nenhum teste de preço/checkout/webhook existente quebra. Se algum quebrar, é sinal de leitura de `settings` poluída entre testes — investigar isolamento, não afrouxar o teste.

- [ ] **Step 6: Commit**

```bash
git add app/config.py app/tests/test_admin_precos.py
git commit -m "feat(admin-precos): resolver de preço vigente (override em settings) + parse_preco + planos_venda"
```

---

### Task 2: site_web — `pagina_precos` + nav + landing/picker usam `planos_venda`

**Files:**
- Modify: `app/site_web.py` (`_admin_nav` ~656; landing ~434; `_pick_planos` ~1836; `pagina_precos` novo perto de `pagina_agenda`)
- Test: `app/tests/test_admin_precos.py` (nova classe)

**Interfaces:**
- Consumes: `config.planos_venda`, `pricing.opcoes_parcelas`, `pricing.fmt_brl`, `_esc`, `_admin_nav`, `_pagina`.
- Produces: `pagina_precos(planos, token, msg="") -> str` (`planos` = lista dos dicts vigentes de Mensal e Anual).

- [ ] **Step 1: Write the failing test** — adicionar em `app/tests/test_admin_precos.py`:

```python
class TestPaginaPrecos(unittest.TestCase):
    def _planos(self):
        return [
            {"slug": "mensal", "nome": "Mensal", "base": 147.0, "preco": "R$ 147", "nota": ""},
            {"slug": "anual", "nome": "Anual", "base": 1497.0, "preco": "R$ 1.497",
             "nota": "≈ R$ 125/mês · em até 12x sem juros", "pix_desconto_pct": 5},
        ]

    def test_renderiza_planos_e_forms(self):
        import site_web
        html = site_web.pagina_precos(self._planos(), "tok")
        self.assertIn("Mensal", html)
        self.assertIn("Anual", html)
        self.assertIn("R$ 1.497", html)                 # preview
        self.assertIn('value="147"', html)              # input com base vigente (mensal)
        self.assertIn('value="salvar_preco"', html)     # form salvar
        self.assertIn('value="resetar_preco"', html)    # voltar ao padrão
        self.assertIn("/admin/precos", html)

    def test_escapa(self):
        import site_web
        maligno = [{"slug": "x", "nome": "<script>x</script>", "base": 1.0, "preco": "R$ 1", "nota": ""}]
        html = site_web.pagina_precos(maligno, "tok")
        self.assertNotIn("<script>x</script>", html)
        self.assertIn("&lt;script&gt;", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_admin_precos.TestPaginaPrecos -v`
Expected: FAIL (`pagina_precos` não existe).

- [ ] **Step 3: Write minimal implementation** — em `app/site_web.py`:

**(a)** No `_admin_nav` (junto dos outros `lk(...)`), adicionar após o `/agenda`:

```python
            + lk("/admin/precos", "💰 Preços", "precos")
```

**(b)** Trocar a fonte dos planos na landing (linha ~434) e no `_pick_planos` (linha ~1836): onde está `for p in config.PLANOS if not p.get("oculto")`, usar `for p in config.planos_venda()`. (Nos dois lugares; o `planos_venda()` já filtra ocultos e aplica override.)

**(c)** Adicionar `pagina_precos` (perto de `pagina_agenda`):

```python
def pagina_precos(planos, token, msg=""):
    """Admin: editar o preço (base) de cada plano. planos = dicts vigentes."""
    import pricing
    tk = _esc(token)
    aviso = f'<p class="hint">{_esc(msg)}</p>' if msg else ""
    linhas = ""
    for p in planos:
        slug = _esc(p["slug"])
        base = float(p.get("base") or 0)
        extra = ""
        if p.get("slug") == "anual":
            ops = pricing.opcoes_parcelas(base)
            extra = f' · 12x de {_esc(pricing.fmt_brl(ops[-1]["por_parcela"]))}'
        preview = f'{_esc(p.get("preco") or "")} <span class=hint>{_esc(p.get("nota") or "")}{extra}</span>'
        linhas += (
            f'<div style="margin:14px 0;padding:12px;border:1px solid #333;border-radius:8px">'
            f'<b>{_esc(p.get("nome") or slug)}</b> — vigente: {preview}<br>'
            f'<form method="post" action="/admin/precos" style="display:inline-block;margin-top:6px">'
            f'<input type="hidden" name="acao" value="salvar_preco">'
            f'<input type="hidden" name="token" value="{tk}">'
            f'<input type="hidden" name="slug" value="{slug}">'
            f'R$ <input name="preco" inputmode="decimal" value="{_esc(f"{base:.0f}" if base == int(base) else base)}" '
            f'style="padding:6px;width:120px"> '
            f'<button type="submit">Salvar</button></form> '
            f'<form method="post" action="/admin/precos" style="display:inline">'
            f'<input type="hidden" name="acao" value="resetar_preco">'
            f'<input type="hidden" name="token" value="{tk}">'
            f'<input type="hidden" name="slug" value="{slug}">'
            f'<button type="submit">Voltar ao padrão</button></form></div>')
    corpo = (f'<div class="wrap">{_admin_nav(token, "precos")}'
             f'<h2>💰 Preços dos planos</h2>{aviso}'
             f'<p class=hint>O valor editado vale nas vendas novas. Assinantes atuais mantêm o valor '
             f'que contrataram.</p>{linhas}</div>')
    return _pagina("Preços · Admin", corpo, logado=True, atual="precos")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_admin_precos.TestPaginaPrecos -v`
Expected: PASS (2 testes).

- [ ] **Step 5: Rodar a suíte (regressão da landing/picker)**

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -6`
Expected: `OK` (749 + 2 = 751). O teste de landing existente (`test_site_web`) segue verde: sem override, `planos_venda()` devolve os mesmos valores do código. Se quebrar, conferir se o loop trocado casa o shape que o card espera (usa `p["preco"]`/`preco_str_vigente`).

- [ ] **Step 6: Commit**

```bash
git add app/site_web.py app/tests/test_admin_precos.py
git commit -m "feat(admin-precos): pagina_precos + link no nav + landing/picker usam planos_venda"
```

---

### Task 3: serve — rotas `/admin/precos` (GET + POST) + regressão

**Files:**
- Modify: `app/serve.py` (GET no `do_GET`; POST no `do_POST`)
- Test: `app/tests/test_admin_precos.py` (nova classe, se houver seam; senão regressão)

**Interfaces:**
- Consumes: `config.planos_venda`, `config.parse_preco`, `db.set_config`, `site_web.pagina_precos`, `config.ADMIN_TOKEN`.

- [ ] **Step 1: Implementar o GET** — em `app/serve.py`, no `do_GET`, ao lado de `/agenda`/`/admin/envio` (mesmo padrão de token):

```python
        if path == "/admin/precos":
            import config, site_web
            token_ok = config.ADMIN_TOKEN and q.get("token", [""])[0] == config.ADMIN_TOKEN
            if not token_ok:
                return self._html("<h3>Acesso negado</h3>", 403)
            visiveis = {p["slug"]: p for p in config.planos_venda()}
            planos = [visiveis[s] for s in ("mensal", "anual") if s in visiveis]
            return self._html(site_web.pagina_precos(planos, config.ADMIN_TOKEN or "",
                                                     msg=q.get("msg", [""])[0]))
```

- [ ] **Step 2: Implementar o POST** — em `app/serve.py`, no `do_POST` (após o `g = lambda k: ...`, junto das outras rotas admin):

```python
        if path == "/admin/precos":
            import config, db
            token_ok = bool(config.ADMIN_TOKEN) and g("token") == config.ADMIN_TOKEN
            if not token_ok:
                return self._html("<h3>Acesso negado</h3>", 403)
            db.init()
            slug, acao = g("slug"), g("acao")
            msg = ""
            if slug not in ("mensal", "anual"):
                msg = "Plano inválido."
            elif acao == "resetar_preco":
                db.set_config(f"preco_base_{slug}", "")
                pl = config.plano_por_slug(slug) or {}
                msg = f"{slug.capitalize()} voltou ao padrão ({pl.get('preco','')})."
            elif acao == "salvar_preco":
                valor = config.parse_preco(g("preco"))
                if valor is None:
                    msg = "Preço inválido — use um número maior que zero (ex.: 1600)."
                else:
                    db.set_config(f"preco_base_{slug}", str(valor))
                    msg = f"✅ {slug.capitalize()}: {config._preco_str(valor)}."
            import urllib.parse as _up
            return self._redirect(f"/admin/precos?token={config.ADMIN_TOKEN}&msg={_up.quote(msg)}")
```

*(Confirme o nome exato do lambda de leitura do form (`g`) e do `self._redirect` lendo uma rota POST vizinha, ex.: `/admin/envio`.)*

- [ ] **Step 3: (Se viável) teste de rota** — se o harness de `/admin/*` já existir nos testes (ex.: um `_get`/`_post` helper em `test_site_web`/`test_afiliados`), adicionar em `app/tests/test_admin_precos.py` uma classe que:
  - POST `salvar_preco` slug=anual, preco="1600" com token → grava (`db.get_config("preco_base_anual")=="1600.0"`) e depois `config.plano_por_slug("anual")["base"]==1600.0`.
  - POST `salvar_preco` preco="abc" → NÃO grava (get_config segue "").
  - POST `resetar_preco` → limpa.
  - GET sem token → 403.
  Se não houver harness reutilizável fácil, pular (a lógica de validação já é coberta por `TestParsePreco`; documentar no report que o POST foi validado por smoke manual).

- [ ] **Step 4: Rodar a suíte inteira (regressão)**

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -6`
Expected: `OK`. 751 + (testes de rota que você adicionou). Nenhuma rota existente quebrada.

- [ ] **Step 5: Smoke manual (documentar, não bloqueia)**

1. `/admin/precos?token=…` → mostra Mensal R$147 / Anual R$1.497 + preview 12x.
2. Editar Anual pra 1600 → Salvar → landing e /assinar mostram R$1.600 (e 12x de R$133,33); cupom LANCAMENTO → 1100.
3. "Voltar ao padrão" no Anual → volta a R$1.497.
4. Preço inválido (0/vazio/texto) → mensagem de erro, não grava.

- [ ] **Step 6: Commit**

```bash
git add app/serve.py app/tests/test_admin_precos.py
git commit -m "feat(admin-precos): rotas /admin/precos (GET tela + POST salvar/resetar com validação)"
```

---

## Notas de execução

- **Review final** (mexe em preço ao vivo): rodar code-reviewer no branch. Ponto crítico: sem override, comportamento idêntico (regressão verde); com override, o preço vigente propaga pra landing/assinar/checkout/webhook via o resolver; entrada inválida nunca grava.
- **Deploy junto do preço de lançamento** (mesmo branch) — decisão do Diego. Sem push/deploy neste plano.

## Self-Review (checklist do autor)

- **Cobertura da spec:** editar só o número (Task 1 resolver + Task 3 POST) ✓; Mensal/Anual só (Task 3 GET filtra) ✓; texto deriva (Task 1 `_preco_str`/`_nota_derivada`) ✓; voltar ao padrão (Task 3 `resetar_preco`) ✓; efeito imediato sem redeploy (resolver lê settings a cada chamada) ✓; assinantes intocados (nada mexe em `valor_contratado`; aviso na tela) ✓; landing/assinar/checkout/webhook enxergam (planos_venda + plano_por_slug/plano_por_base override-aware) ✓; validação de dinheiro (parse_preco > 0) ✓; sem override = idêntico (regressão) ✓.
- **Consistência de tipos:** `planos_venda() -> list[dict]`; `pagina_precos(planos, token, msg)`; `parse_preco(s)->float|None`; `plano_por_slug`/`plano_por_base` devolvem dict (cópia) com override. Chaves de settings `preco_base_mensal`/`preco_base_anual` idênticas em Task 1 (leitura) e Task 3 (escrita).
- **Sem placeholders:** todo passo tem código real. Os 2 pontos de "confirmar" (nome do `g`/`_redirect`; harness de teste de rota) são checagens de integração contra código existente.
