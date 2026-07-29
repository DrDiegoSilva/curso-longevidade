# Preços de lançamento (147/1497) + cupom LANCAMENTO (−R$500 anual) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Subir o preço vigente para mensal **R$147** / anual **R$1.497** (encerrando o founder), e criar um cupom promocional **LANCAMENTO** de valor fixo **−R$500** que só desconta o **anual** (→ R$997), multi-uso, sem comissão.

**Architecture:** Preços vivem em `config.PLANOS`; encerrar founder = pôr `base`=`base_pos` (147/1497), tornando a maquinaria founder inerte (sem tocar `pricing.py`). Cupom de valor fixo é um tipo NOVO: hoje a tabela `cupons` só dá cortesia (dias grátis) e o % só vem de afiliado. Adiciona-se `desconto_valor`+`plano_slug` ao cupom; `pricing.base_cobrada` ganha um desconto fixo (aplicado ANTES do Pix, que empilha por cima → 997−5%=947,15); e o checkout roteia o cupom promocional pro caminho PAGO (nunca cortesia grátis), sem comissão.

**Tech Stack:** Python 3 stdlib, sqlite via `db.py`, `pricing.py` (puro), checkout Asaas via `serve.py`/`asaas.py`. Sem dependências novas.

## Global Constraints

- **Worktree:** `/Users/diegosilva/dev/curso-longevidade/.claude/worktrees/precos-lancamento`, branch `precos-lancamento` (base = origin/main `b5652b2`). Testes: `cd app && python3 -m unittest discover -s tests`. **Baseline = 729 testes verdes.**
- **Repo multi-agente:** stagear só os arquivos de cada task; **nunca** `git add -A`.
- **DINHEIRO REAL (Asaas produção):** nenhum push/deploy neste plano. Toda mudança de valor tem teste. O cupom promocional **NUNCA** pode conceder acesso grátis (não pode cair no ramo de cortesia).
- **Decisões do Diego (2026-07-28):** encerrar founder → 147/1497 pra todos já · cupom **valor fixo −R$500** (anual → 997) · código **LANCAMENTO** · **multi-uso, sem expiração** · Pix **empilha** (997 − 5% = 947,15).
- **Renovação = preço contratado:** o cupom é desconto de 1ª venda (igual ao afiliado). `valor_base` gravado no pending continua sendo a base vigente (1497), então a renovação cobra o preço de tabela, não o promocional. Não alterar isso.
- **Anual 12x já funciona** (a tela usa `pricing.opcoes_parcelas(base)` default 12; `montar_checkout` manda `installmentCount`; `test_asaas_payload.test_anual_cartao_parcelado` cobre). Não precisa de código — só confirmar.

## File Structure

- `app/config.py` — **modificar**: `PLANOS` (mensal/anual `base`+`preco`+`nota`).
- `app/db.py` — **modificar**: coluna `desconto_valor`+`plano_slug` em `cupons` (CREATE TABLE + `_migrar_colunas`); `criar_cupom` ganha os params; `cupom_desconto(codigo, plano_slug)` novo; seed idempotente do LANCAMENTO.
- `app/pricing.py` — **modificar**: `base_cobrada` ganha `cupom_valor` (desconto fixo, antes do Pix).
- `app/serve.py` — **modificar**: no POST `/assinar`, cortesia só p/ cupom sem desconto; cupom promocional → caminho pago com desconto fixo, sem comissão.
- `app/tests/test_precos_lancamento.py` — **criar** (cupom fixo + config + pricing).
- Atualizar testes que quebram: `app/tests/test_pricing.py`, `app/tests/test_asaas_payload.py` (e quaisquer outros que afirmem o preço vigente ANTIGO).

---

### Task 1: config — preços 147/1497 (encerra founder) + consertar testes que quebram

**Files:**
- Modify: `app/config.py` (`PLANOS`, ~linha 90/95)
- Modify: `app/tests/test_pricing.py`, `app/tests/test_asaas_payload.py` (+ qualquer outro que quebrar)

**Interfaces:**
- Produces: `pricing.preco_vigente(mensal, n)==147.0` e `(anual, n)==1497.0` para qualquer `n` (base==base_pos).

- [ ] **Step 1: Atualizar os testes de preço para a nova realidade (RED)** — em `app/tests/test_pricing.py`:

Trocar `test_anual_1099` por:
```python
    def test_anual_1497(self):
        pl = self.cfg.plano_por_slug("anual")
        self.assertEqual(pl["base"], 1497.0)
        self.assertEqual(pl["preco"], "R$ 1.497")
        self.assertEqual(pl["pix_desconto_pct"], 5)
```
Em `test_preco_vigente_founder_e_pos`, o preço agora é o mesmo pra qualquer `n` (founder encerrado):
```python
    def test_preco_vigente_founder_e_pos(self):
        anual = self.cfg.plano_por_slug("anual")
        self.assertEqual(self.p.preco_vigente(anual, 0), 1497.0)
        self.assertEqual(self.p.preco_vigente(anual, self.cfg.FOUNDER_LIMITE), 1497.0)
        mensal = self.cfg.plano_por_slug("mensal")
        self.assertEqual(self.p.preco_vigente(mensal, 0), 147.0)
        self.assertEqual(self.p.preco_vigente(mensal, 999), 147.0)
        tri = self.cfg.plano_por_slug("trimestral")
        self.assertEqual(self.p.preco_vigente(tri, 999), float(tri["base"]))
```
Em `test_preco_str_vigente`:
```python
    def test_preco_str_vigente(self):
        anual = self.cfg.plano_por_slug("anual")
        self.assertEqual(self.p.preco_str_vigente(anual, 0), "R$ 1.497")
        self.assertEqual(self.p.preco_str_vigente(anual, self.cfg.FOUNDER_LIMITE), "R$ 1.497")
```
Em `app/tests/test_asaas_payload.py`, trocar as duas ocorrências de `99.0` (mensal, linhas ~26 e ~35) por `147.0`. As asserções do anual leem `["base"]` — adaptam sozinhas (o comentário "997" na linha ~51 está velho; pode corrigir p/ "1497").

Run: `cd app && python3 -m unittest tests.test_pricing tests.test_asaas_payload -v`
Expected: FAIL (config ainda tem 99/1099).

- [ ] **Step 2: Mudar os preços** — em `app/config.py`, no `PLANOS`:
  - **mensal:** `"base": 99.0` → `"base": 147.0`; `"preco": "R$ 99"` → `"preco": "R$ 147"`. (`base_pos`/`preco_pos` já são 147 — deixar.)
  - **anual:** `"base": 1099.0` → `"base": 1497.0`; `"preco": "R$ 1.099"` → `"preco": "R$ 1.497"`; `"nota": "≈ R$ 92/mês · em até 12x sem juros"` → `"nota": "≈ R$ 125/mês · em até 12x sem juros"`. (`base_pos`/`preco_pos`/`nota_pos` já 1497 — deixar; agora `base==base_pos`, founder fica inerte.)

- [ ] **Step 3: Rodar os testes de preço (GREEN)**

Run: `cd app && python3 -m unittest tests.test_pricing tests.test_asaas_payload -v`
Expected: PASS.

- [ ] **Step 4: Rodar a suíte inteira e consertar quaisquer OUTROS testes que quebraram pelo preço**

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -20`
Regra pra consertar: se um teste quebrou porque **afirmava o preço vigente ANTIGO** (99/1099/"R$ 92/mês" como preço de tabela atual), atualize pro novo (147/1497). **NÃO** altere dados de teste que modelam um **contrato histórico específico** (ex.: `valor_contratado=1099.0`, `valor_base=1099.0`, `_pagar(valor=1099.0)`, `registrar_comissao(..., 1099.0, ...)`) — esses testam preservação/estorno de um valor já contratado e devem continuar 1099. Se não tiver certeza de um caso, PARE e reporte em vez de adivinhar.
Expected: `OK` no fim.

- [ ] **Step 5: Commit**
```bash
git add app/config.py app/tests/test_pricing.py app/tests/test_asaas_payload.py   # + outros testes que você ajustou
git commit -m "feat(precos): mensal R$147 / anual R$1.497 (encerra founder) + testes"
```

---

### Task 2: db — cupom de valor fixo (`desconto_valor`/`plano_slug`) + `cupom_desconto` + seed LANCAMENTO

**Files:**
- Modify: `app/db.py`
- Test: `app/tests/test_precos_lancamento.py` (criar)

**Interfaces:**
- Consumes: `_conn`, `_add_coluna`, `_migrar_colunas`, `criar_cupom`, `obter_cupom`, `init`.
- Produces:
  - `criar_cupom(descricao="", uso_unico=True, dias_acesso=0, codigo=None, desconto_valor=0, plano_slug="") -> str`
  - `cupom_desconto(codigo, plano_slug) -> float` (R$ off do cupom promocional ATIVO cujo escopo casa o plano; 0 se não é promocional/ativo/escopo diferente)
  - seed idempotente: cupom `LANCAMENTO` (desconto_valor=500, plano_slug="anual", uso_unico=False).

- [ ] **Step 1: Write the failing test** — criar `app/tests/test_precos_lancamento.py`:

```python
"""Preços de lançamento + cupom LANCAMENTO (valor fixo). Standalone."""
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


class TestCupomFixo(unittest.TestCase):
    def setUp(self):
        self.snap = (os.environ.get("DSCURSO_ARTIGOS_DB"), os.environ.get("DATABASE_URL"))
        self.tmp = tempfile.mkdtemp()
        self.db = _reload_db(self.tmp)

    def tearDown(self):
        import shutil, importlib
        a, d = self.snap
        os.environ["DSCURSO_ARTIGOS_DB"] = a if a is not None else ""
        if a is None:
            os.environ.pop("DSCURSO_ARTIGOS_DB", None)
        if d is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = d
        import db as _db
        importlib.reload(_db)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_seed_lancamento_existe(self):
        info = self.db.obter_cupom("LANCAMENTO")
        self.assertIsNotNone(info)
        self.assertEqual(float(info["desconto_valor"]), 500.0)
        self.assertEqual(info["plano_slug"], "anual")
        self.assertEqual(info["uso_unico"], 0)          # multi-uso
        self.assertEqual(info["ativo"], 1)

    def test_cupom_desconto_escopo(self):
        self.assertEqual(self.db.cupom_desconto("LANCAMENTO", "anual"), 500.0)
        self.assertEqual(self.db.cupom_desconto("LANCAMENTO", "mensal"), 0.0)   # fora do escopo
        self.assertEqual(self.db.cupom_desconto("INEXISTENTE", "anual"), 0.0)

    def test_cupom_desconto_ignora_cortesia(self):
        self.db.criar_cupom(codigo="CORTESIA30", dias_acesso=30)               # cortesia, sem desconto_valor
        self.assertEqual(self.db.cupom_desconto("CORTESIA30", "anual"), 0.0)

    def test_cupom_desconto_inativo(self):
        self.db.criar_cupom(codigo="PROMO2", desconto_valor=200, plano_slug="", uso_unico=True)
        self.assertEqual(self.db.cupom_desconto("PROMO2", "anual"), 200.0)     # escopo vazio = qualquer plano
        self.db.consumir_cupom("PROMO2")                                       # uso único -> desativa
        self.assertEqual(self.db.cupom_desconto("PROMO2", "anual"), 0.0)       # inativo -> 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_precos_lancamento.TestCupomFixo -v`
Expected: FAIL (colunas/`cupom_desconto`/seed inexistentes).

- [ ] **Step 3: Write minimal implementation** — em `app/db.py`:

**(a)** Na `CREATE TABLE IF NOT EXISTS cupons (...)` dentro do `executescript` de `init()`, acrescentar as colunas:
```
codigo TEXT PRIMARY KEY, ativo INTEGER DEFAULT 1, descricao TEXT, criado_em TEXT,
desconto_valor REAL DEFAULT 0, plano_slug TEXT DEFAULT ''
```
(mantendo as que já existem; as migradas — usos/uso_unico/dias_acesso — seguem vindo do `_migrar_colunas`.)

**(b)** Em `_migrar_colunas`, adicionar (idempotente p/ o banco de produção que já tem a tabela):
```python
        _add_coluna(c, "cupons", "desconto_valor", "REAL DEFAULT 0")
        _add_coluna(c, "cupons", "plano_slug", "TEXT DEFAULT ''")
```

**(c)** `criar_cupom` — acrescentar os 2 params e gravá-los:
```python
def criar_cupom(descricao="", uso_unico=True, dias_acesso=0, codigo=None, desconto_valor=0, plano_slug=""):
    """Gera um cupom. dias_acesso>0 => cortesia (N dias grátis). desconto_valor>0 =>
    cupom PROMOCIONAL de valor fixo (R$ off no checkout pago), escopável por plano_slug
    ('' = qualquer). Retorna o código (UPPER)."""
    import secrets
    from datetime import datetime
    cod = (codigo or secrets.token_hex(4)).strip().upper()
    with _conn() as c:
        c.execute("INSERT INTO cupons (codigo,ativo,descricao,usos,uso_unico,dias_acesso,criado_em,desconto_valor,plano_slug) "
                  "VALUES (?,1,?,0,?,?,?,?,?) ON CONFLICT (codigo) DO NOTHING",
                  (cod, descricao or "", 1 if uso_unico else 0, int(dias_acesso or 0),
                   datetime.now().isoformat(), float(desconto_valor or 0), (plano_slug or "").strip()))
    return cod
```

**(d)** Novo `cupom_desconto` (perto de `obter_cupom`):
```python
def cupom_desconto(codigo, plano_slug):
    """R$ de desconto fixo de um cupom PROMOCIONAL ativo cujo escopo casa o plano.
    0 se não existe, está inativo, não é promocional, ou o escopo não bate."""
    info = obter_cupom(codigo)
    if not info or not info.get("ativo"):
        return 0.0
    val = float(info.get("desconto_valor") or 0)
    if val <= 0:
        return 0.0
    escopo = (info.get("plano_slug") or "").strip()
    if escopo and escopo != plano_slug:
        return 0.0
    return val
```

**(e)** Seed idempotente do LANCAMENTO. Se existir um `_seed_cupons()` chamado no `init()`, acrescente a linha lá; senão, adicione a chamada no fim de `init()` (após as migrações), guardada por try/except pra nunca derrubar o boot:
```python
    try:
        criar_cupom(codigo="LANCAMENTO", descricao="Lançamento: -R$500 no anual",
                    uso_unico=False, desconto_valor=500, plano_slug="anual")
    except Exception as e:
        print(f"[db] seed LANCAMENTO falhou: {e}", flush=True)
```
*(Confirme onde `init()` termina as migrações e insira o seed logo depois, no mesmo `with _conn()`/fluxo que os outros seeds usam. `ON CONFLICT DO NOTHING` torna repetível.)*

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_precos_lancamento.TestCupomFixo -v`
Expected: PASS (4 testes).

- [ ] **Step 5: Commit**
```bash
git add app/db.py app/tests/test_precos_lancamento.py
git commit -m "feat(precos): cupom de valor fixo (desconto_valor/plano_slug) + cupom_desconto + seed LANCAMENTO"
```

---

### Task 3: pricing — `base_cobrada` com desconto fixo (antes do Pix)

**Files:**
- Modify: `app/pricing.py`
- Test: `app/tests/test_precos_lancamento.py` (nova classe)

**Interfaces:**
- Produces: `base_cobrada(plano, metodo, base_vig, cupom_pct=0.0, cupom_valor=0.0) -> float`. Ordem: desconto fixo → % (afiliado) → Pix. Retrocompatível (chamadas de 4 args seguem iguais).

- [ ] **Step 1: Write the failing test** — adicionar em `app/tests/test_precos_lancamento.py`:

```python
class TestBaseCobradaFixo(unittest.TestCase):
    def setUp(self):
        import pricing, config
        self.p, self.cfg = pricing, config
        self.anual = self.cfg.plano_por_slug("anual")

    def test_cupom_fixo_cartao(self):
        # 1497 - 500 = 997 (cartão não tem desconto Pix)
        self.assertEqual(self.p.base_cobrada(self.anual, "CARTAO", 1497.0, 0.0, 500.0), 997.0)

    def test_cupom_fixo_pix_empilha(self):
        # 1497 - 500 = 997, depois Pix 5% -> 947.15
        self.assertEqual(self.p.base_cobrada(self.anual, "PIX", 1497.0, 0.0, 500.0), 947.15)

    def test_retrocompat_sem_cupom_valor(self):
        # chamada antiga (4 args) inalterada
        self.assertEqual(self.p.base_cobrada(self.anual, "CARTAO", 1497.0, 0.0), 1497.0)
        self.assertEqual(self.p.base_cobrada(self.anual, "PIX", 1497.0, 0.0), round(1497.0 * 0.95, 2))

    def test_nao_fica_negativo(self):
        self.assertEqual(self.p.base_cobrada(self.anual, "CARTAO", 300.0, 0.0, 500.0), 0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_precos_lancamento.TestBaseCobradaFixo -v`
Expected: FAIL (`base_cobrada` não aceita `cupom_valor`).

- [ ] **Step 3: Write minimal implementation** — em `app/pricing.py`, trocar `base_cobrada`:

```python
def base_cobrada(plano, metodo, base_vig, cupom_pct=0.0, cupom_valor=0.0):
    """Valor efetivamente cobrado: aplica o desconto FIXO do cupom promocional (R$), depois
    o cupom % (afiliado), e por fim, se for PIX e o plano oferecer `pix_desconto_pct`, o
    desconto Pix por cima (empilha). Puro/testável."""
    v = round(float(base_vig), 2)
    if cupom_valor:
        v = round(max(0.0, v - float(cupom_valor)), 2)
    if cupom_pct:
        v = valor_com_desconto(v, cupom_pct)
    if (metodo or "").upper() == "PIX" and plano.get("pix_desconto_pct"):
        v = valor_com_desconto(v, plano["pix_desconto_pct"])
    return v
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_precos_lancamento.TestBaseCobradaFixo -v`
Expected: PASS (4 testes).

- [ ] **Step 5: Commit**
```bash
git add app/pricing.py app/tests/test_precos_lancamento.py
git commit -m "feat(precos): base_cobrada aplica desconto fixo do cupom (antes do Pix)"
```

---

### Task 4: serve — checkout aplica o cupom promocional (nunca cortesia) + regressão

**Files:**
- Modify: `app/serve.py` (POST `/assinar`, ~linhas 1214-1257)
- Test: regressão + (se viável) um teste do roteamento

**Interfaces:**
- Consumes: `db.obter_cupom`, `db.cupom_valido`, `db.cupom_desconto`, `db.consumir_cupom`, `db.afiliado_por_codigo`, `pricing.base_cobrada`.

- [ ] **Step 1: Implementar o roteamento do cupom** — em `app/serve.py`, no POST `/assinar`:

**(a)** O ramo de **cortesia** hoje é `if cupom and db.cupom_valido(cupom):` — isso capturaria um cupom promocional (que também é "válido") e criaria assinante GRÁTIS. Trocar a guarda para só cortesia (cupom ativo SEM desconto_valor):
```python
        cupom = g("cupom").strip()
        _cup = db.obter_cupom(cupom) if cupom else None
        _eh_cortesia = bool(_cup and _cup.get("ativo") and float(_cup.get("desconto_valor") or 0) == 0)
        # Cupom de cortesia: ativa na hora, sem Asaas
        if cupom and _eh_cortesia:
            info = _cup
            ...  # (corpo existente da cortesia inalterado)
            return self._redirect("/obrigado")
```
*(Mantenha o corpo da cortesia como está — só a CONDIÇÃO muda de `db.cupom_valido(cupom)` para `_eh_cortesia`.)*

**(b)** No caminho **pago**, calcular o desconto fixo do cupom promocional e passá-lo ao `base_cobrada`, além do afiliado (mutuamente exclusivos na prática, mas o `base_cobrada` aceita os dois):
```python
        promo_valor = db.cupom_desconto(cupom, plano["slug"]) if cupom else 0.0
        af = db.afiliado_por_codigo(cupom) if cupom else None
        af_codigo = af["codigo"] if af else ""
        base_final = pricing.base_cobrada(plano, metodo, base_vig,
                                          af["pct_desconto"] if af else 0.0, promo_valor)
        ...
        # (criar_pending / montar_checkout / criar_checkout inalterados; valor_base = base_vig)
```
E, após criar o pending com sucesso (antes do redirect pro checkout), contabilizar o uso do cupom promocional (multi-uso segue ativo; uso único desativa):
```python
        if promo_valor > 0:
            try:
                db.consumir_cupom(cupom)
            except Exception as e:
                print(f"[assinar] consumir cupom promo falhou: {e}", flush=True)
```
*(Não gerar comissão pro cupom promocional — só o afiliado gera. `valor_base` continua `base_vig` = 1497 pra renovação cobrar o preço de tabela.)*

- [ ] **Step 2: Rodar a suíte inteira (regressão)**

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -6`
Expected: `OK`. Baseline 729 + Task1(ajustes) + Task2(4) + Task3(4) = **737 testes**, todos verdes. Nenhum fluxo de checkout/afiliado/cortesia existente quebrado.

- [ ] **Step 3: Confirmar anual 12x (documentar, não bloqueia)**

`test_asaas_payload.test_anual_cartao_parcelado` já garante `installmentCount==12` no anual cartão, e a tela `/assinar` usa `pricing.opcoes_parcelas(base)` (default 12x). Anotar no report que o 12x anual já está no ar (nenhuma mudança necessária).

- [ ] **Step 4: Smoke manual (documentar, não bloqueia)**

1. `/assinar?plano=anual` → preço mostra **R$ 1.497** e parcelamento até 12x.
2. Aplicar cupom **LANCAMENTO** no anual/cartão → cobra **R$ 997** (12x de ~R$83,08). No Pix → **R$ 947,15**.
3. LANCAMENTO no **mensal** → sem desconto (escopo anual). LANCAMENTO **nunca** cria assinante grátis.
4. Cupom de cortesia existente segue criando acesso grátis normalmente.

- [ ] **Step 5: Commit**
```bash
git add app/serve.py
git commit -m "feat(precos): checkout aplica cupom LANCAMENTO (desconto fixo, nunca cortesia, sem comissão)"
```

---

## Notas de execução

- **Review final OBRIGATÓRIO** (é dinheiro real): rodar security-reviewer + code-reviewer no branch inteiro antes de encerrar. Ponto crítico a verificar: o cupom promocional **nunca** concede acesso grátis (guarda `_eh_cortesia`), e o valor cobrado bate (997 cartão / 947,15 Pix).
- **Antes de deploy (decisão do Diego):** conferir no painel Asaas que o anual em 12x + o valor com cupom batem numa cobrança real (ou um teste R$5). Sem push/deploy neste plano.
- **Founder:** encerrado tornando `base==base_pos`. A maquinaria (`_pos_founder`, `vagas_founder`) fica inerte; remoção total é backlog (YAGNI).
