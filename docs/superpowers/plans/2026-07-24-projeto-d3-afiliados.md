# Projeto D3 — Afiliados — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um afiliado divulga um código de cupom que dá 10% off na 1ª venda ao assinante e gera 3% de comissão pra ele, com relatório e "marcar como paga" no `/admin`.

**Architecture:** Duas tabelas novas em SQLite/Postgres (`afiliados`, `comissoes`) + coluna `afiliado_codigo` no `pending_signups`. O `_post_assinar` detecta o código, aplica o desconto sobre o preço vigente (founder D2) e leva ao checkout Asaas pago, gravando o código no pending. O webhook `ATIVAR` (só venda nova) registra a comissão sobre o valor pago e, no cartão, reseta o valor recorrente da assinatura pro preço cheio (renovação não fica descontada). Gestão numa página `/admin/afiliados` nova.

**Tech Stack:** Python 3 stdlib (http.server, sqlite3/psycopg2 via `db._conn`), unittest. Sem dependências novas.

## Global Constraints

- **Sem dependências novas** — só stdlib + o que o repo já usa (`db`, `pricing`, `asaas`, `subscribers`, `site_web`).
- **Testes:** `unittest`, padrão do repo. Rodar tudo: `cd app && python3 -m unittest discover -s tests`. Arquivos de teste em `app/tests/`, com `sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))` no topo e banco temporário via `os.environ["DSCURSO_ARTIGOS_DB"]`.
- **Cartão é SEM JUROS** (D1): `pricing.valor_cartao(base, n)` devolve `base`. O desconto de afiliado é aplicado ANTES, sobre a base.
- **Preço vigente = founder (D2):** o preço de partida é sempre `pricing.preco_vigente(plano, len(subscribers.ativos()))`. O desconto de afiliado incide sobre esse vigente.
- **Comissão = 3% sobre o valor efetivamente pago** (`pay.value`, já descontado), não sobre o cheio.
- **Cortesia intacta:** o fluxo de cupom de cortesia (`db.cupom_valido` → cadastro grátis) NÃO muda. Afiliado é caminho separado, checado depois da cortesia.
- **Nada pode derrubar a ativação:** registro de comissão e reset da assinatura no webhook são try/except (logam + seguem), padrão já usado no `webhook_asaas.py`.
- **Commits frequentes** na branch `d3-afiliados` (já criada). Convenção: `feat(afiliados): ...` / `test(afiliados): ...`. Sem `Co-Authored-By` (atribuição desligada no repo).
- **Códigos de afiliado são sempre UPPERCASE** ao gravar/consultar (igual cupons).

---

### Task 1: db — tabelas `afiliados`/`comissoes` + coluna no pending + CRUD de afiliado

**Files:**
- Modify: `app/db.py` (bloco `init()` executescript ~L128-140; `_TABELAS` ~L188; `_migrar_colunas` ~L204; funções novas no fim do bloco de cupons ~L307)
- Test: `app/tests/test_afiliados.py` (criar)

**Interfaces:**
- Produces:
  - `db.afiliado_por_codigo(codigo: str) -> dict | None` (só ativos; codigo case-insensitive)
  - `db.criar_afiliado(nome, contato, codigo, pct_desconto=10, pct_comissao=3) -> str` (retorna o código UPPER; ON CONFLICT(codigo) DO NOTHING)
  - `db.toggle_afiliado(id: str, ativo: bool) -> None`
  - Tabela `afiliados(id,nome,contato,codigo UNIQUE,pct_desconto,pct_comissao,ativo,criado_em)`
  - Tabela `comissoes(id,afiliado_id,subscriber_id,plano,valor_venda,valor_comissao,pago,criado_em,pago_em)`
  - Coluna `pending_signups.afiliado_codigo TEXT`

- [ ] **Step 1: Write the failing test**

Criar `app/tests/test_afiliados.py`:

```python
"""Testes de afiliados/comissões (db). Standalone: python3 app/tests/test_afiliados.py"""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAfiliadosDb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import db as _db
        importlib.reload(_db)
        self.db = _db
        self.db.init()

    def test_criar_e_por_codigo(self):
        cod = self.db.criar_afiliado("Dra. Maria", "maria@x.com", "dramaria", 10, 3)
        self.assertEqual(cod, "DRAMARIA")
        af = self.db.afiliado_por_codigo("dramaria")            # case-insensitive
        self.assertIsNotNone(af)
        self.assertEqual(af["nome"], "Dra. Maria")
        self.assertEqual(af["pct_desconto"], 10)
        self.assertEqual(af["pct_comissao"], 3)
        self.assertEqual(self.db.afiliado_por_codigo("naoexiste"), None)

    def test_toggle_desativa(self):
        self.db.criar_afiliado("M", "", "codX")
        af = self.db.afiliado_por_codigo("codx")
        self.db.toggle_afiliado(af["id"], False)
        self.assertIsNone(self.db.afiliado_por_codigo("codx"))  # inativo some da consulta
        self.db.toggle_afiliado(af["id"], True)
        self.assertIsNotNone(self.db.afiliado_por_codigo("codx"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_afiliados -v`
Expected: FAIL com `AttributeError: module 'db' has no attribute 'criar_afiliado'`

- [ ] **Step 3: Implement**

Em `app/db.py`, no `init()` executescript, adicionar as duas tabelas (depois do `CREATE TABLE ... cupons (...)`, antes de `senha_tokens`):

```sql
            CREATE TABLE IF NOT EXISTS afiliados (
                id TEXT PRIMARY KEY, nome TEXT, contato TEXT, codigo TEXT UNIQUE,
                pct_desconto REAL DEFAULT 10, pct_comissao REAL DEFAULT 3,
                ativo INTEGER DEFAULT 1, criado_em TEXT
            );
            CREATE TABLE IF NOT EXISTS comissoes (
                id TEXT PRIMARY KEY, afiliado_id TEXT, subscriber_id TEXT, plano TEXT,
                valor_venda REAL, valor_comissao REAL,
                pago INTEGER DEFAULT 0, criado_em TEXT, pago_em TEXT
            );
```

No mesmo `CREATE TABLE ... pending_signups (...)`, adicionar `afiliado_codigo TEXT,` na linha antes de `criado_em TEXT`:

```sql
                plano TEXT, metodo TEXT, parcelas INTEGER, valor REAL,
                afiliado_codigo TEXT,
                criado_em TEXT
```

Em `_TABELAS` (lista), acrescentar `"afiliados", "comissoes"`:

```python
_TABELAS = ["digests", "login_codes", "sessions", "subscribers",
            "pending_signups", "webhook_events", "cupons", "senha_tokens",
            "curadoria_candidatos", "reserva_resumos", "daily_drafts", "agenda",
            "afiliados", "comissoes"]
```

Em `_migrar_colunas`, adicionar (pro Supabase de produção já existente):

```python
        _add_coluna(c, "pending_signups", "afiliado_codigo", "TEXT")
```

Adicionar as funções (depois de `consumir_cupom`, ~L320):

```python
# ── Afiliados / comissões (D3) ──
def afiliado_por_codigo(codigo):
    """Afiliado ATIVO pelo código (case-insensitive). None se não existe ou inativo."""
    if not codigo:
        return None
    with _conn() as c:
        r = c.execute("SELECT * FROM afiliados WHERE codigo=? AND ativo=1",
                      ((codigo or "").strip().upper(),)).fetchone()
    return dict(r) if r else None


def criar_afiliado(nome, contato, codigo, pct_desconto=10, pct_comissao=3):
    """Cadastra um afiliado. Retorna o código (UPPER). ON CONFLICT(codigo) DO NOTHING."""
    import secrets
    from datetime import datetime
    cod = (codigo or "").strip().upper()
    with _conn() as c:
        c.execute("INSERT INTO afiliados (id,nome,contato,codigo,pct_desconto,pct_comissao,ativo,criado_em) "
                  "VALUES (?,?,?,?,?,?,1,?) ON CONFLICT (codigo) DO NOTHING",
                  (secrets.token_hex(6), (nome or "").strip(), (contato or "").strip(), cod,
                   float(pct_desconto or 0), float(pct_comissao or 0), datetime.now().isoformat()))
    return cod


def toggle_afiliado(id, ativo):
    with _conn() as c:
        c.execute("UPDATE afiliados SET ativo=? WHERE id=?", (1 if ativo else 0, id))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_afiliados -v`
Expected: PASS (2 testes)

- [ ] **Step 5: Commit**

```bash
git add app/db.py app/tests/test_afiliados.py
git commit -m "feat(afiliados): tabelas afiliados/comissoes + coluna pending + CRUD de afiliado"
```

---

### Task 2: db — ledger de comissões + agregados por afiliado

**Files:**
- Modify: `app/db.py` (após as funções da Task 1)
- Test: `app/tests/test_afiliados.py` (adicionar testes)

**Interfaces:**
- Consumes: `db.criar_afiliado`, `db.afiliado_por_codigo` (Task 1)
- Produces:
  - `db.registrar_comissao(afiliado_id, subscriber_id, plano, valor_venda, valor_comissao) -> str`
  - `db.listar_comissoes(afiliado_id=None, pago: bool|None=None) -> list[dict]`
  - `db.marcar_comissao_paga(id) -> None`
  - `db.listar_afiliados() -> list[dict]` (cada dict com `n_vendas`, `comissao_total`, `comissao_pendente`)

- [ ] **Step 1: Write the failing test**

Adicionar em `app/tests/test_afiliados.py` (dentro da classe `TestAfiliadosDb`):

```python
    def test_comissoes_ledger_e_agregados(self):
        self.db.criar_afiliado("Dra. Maria", "", "dramaria", 10, 3)
        af = self.db.afiliado_por_codigo("dramaria")
        c1 = self.db.registrar_comissao(af["id"], "sub1", "anual", 897.30, 26.92)
        self.db.registrar_comissao(af["id"], "sub2", "mensal", 89.10, 2.67)
        # lista completa e filtro por pago
        self.assertEqual(len(self.db.listar_comissoes(af["id"])), 2)
        self.assertEqual(len(self.db.listar_comissoes(af["id"], pago=False)), 2)
        self.assertEqual(len(self.db.listar_comissoes(af["id"], pago=True)), 0)
        # marcar 1 como paga
        self.db.marcar_comissao_paga(c1)
        self.assertEqual(len(self.db.listar_comissoes(af["id"], pago=True)), 1)
        pagas = self.db.listar_comissoes(af["id"], pago=True)
        self.assertIsNotNone(pagas[0]["pago_em"])
        # agregados
        linha = next(a for a in self.db.listar_afiliados() if a["codigo"] == "DRAMARIA")
        self.assertEqual(linha["n_vendas"], 2)
        self.assertAlmostEqual(linha["comissao_total"], 29.59, places=2)
        self.assertAlmostEqual(linha["comissao_pendente"], 2.67, places=2)   # c1 já paga
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_afiliados.TestAfiliadosDb.test_comissoes_ledger_e_agregados -v`
Expected: FAIL com `AttributeError: module 'db' has no attribute 'registrar_comissao'`

- [ ] **Step 3: Implement**

Adicionar em `app/db.py` (após `toggle_afiliado`):

```python
def registrar_comissao(afiliado_id, subscriber_id, plano, valor_venda, valor_comissao):
    """1 linha no ledger de comissões (pago=0). Retorna o id."""
    import secrets
    from datetime import datetime
    cid = secrets.token_hex(8)
    with _conn() as c:
        c.execute("INSERT INTO comissoes (id,afiliado_id,subscriber_id,plano,valor_venda,valor_comissao,pago,criado_em) "
                  "VALUES (?,?,?,?,?,?,0,?)",
                  (cid, afiliado_id, subscriber_id, plano or "",
                   float(valor_venda or 0), float(valor_comissao or 0), datetime.now().isoformat()))
    return cid


def listar_comissoes(afiliado_id=None, pago=None):
    q = "SELECT * FROM comissoes"
    conds, params = [], []
    if afiliado_id is not None:
        conds.append("afiliado_id=?"); params.append(afiliado_id)
    if pago is not None:
        conds.append("pago=?"); params.append(1 if pago else 0)
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY criado_em DESC"
    with _conn() as c:
        return [dict(r) for r in c.execute(q, params).fetchall()]


def marcar_comissao_paga(id):
    from datetime import datetime
    with _conn() as c:
        c.execute("UPDATE comissoes SET pago=1, pago_em=? WHERE id=?", (datetime.now().isoformat(), id))


def listar_afiliados():
    """Afiliados + agregados de comissão (n_vendas, comissao_total, comissao_pendente)."""
    with _conn() as c:
        afs = [dict(r) for r in c.execute("SELECT * FROM afiliados ORDER BY criado_em DESC").fetchall()]
        for a in afs:
            ag = c.execute(
                "SELECT COUNT(*) n, COALESCE(SUM(valor_comissao),0) tot, "
                "COALESCE(SUM(CASE WHEN pago=0 THEN valor_comissao ELSE 0 END),0) pend "
                "FROM comissoes WHERE afiliado_id=?", (a["id"],)).fetchone()
            a["n_vendas"] = ag["n"]
            a["comissao_total"] = round(float(ag["tot"] or 0), 2)
            a["comissao_pendente"] = round(float(ag["pend"] or 0), 2)
    return afs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_afiliados -v`
Expected: PASS (3 testes)

- [ ] **Step 5: Commit**

```bash
git add app/db.py app/tests/test_afiliados.py
git commit -m "feat(afiliados): ledger de comissoes (registrar/listar/marcar paga) + agregados"
```

---

### Task 3: db — `criar_pending` grava `afiliado_codigo`

**Files:**
- Modify: `app/db.py` (`criar_pending` ~L238-251)
- Test: `app/tests/test_afiliados.py`

**Interfaces:**
- Consumes: coluna `pending_signups.afiliado_codigo` (Task 1)
- Produces: `criar_pending(dados)` passa a persistir `dados["afiliado_codigo"]`; `obter_pending(token)["afiliado_codigo"]` disponível.

- [ ] **Step 1: Write the failing test**

Adicionar em `app/tests/test_afiliados.py`:

```python
    def test_pending_guarda_afiliado_codigo(self):
        tok = self.db.criar_pending({"nome": "X", "whatsapp": "5543", "plano": "anual",
                                     "afiliado_codigo": "DRAMARIA", "valor": 897.30})
        p = self.db.obter_pending(tok)
        self.assertEqual(p["afiliado_codigo"], "DRAMARIA")
        # sem o campo -> continua funcionando (default vazio)
        tok2 = self.db.criar_pending({"nome": "Y", "whatsapp": "5544", "plano": "mensal"})
        self.assertIn(self.db.obter_pending(tok2)["afiliado_codigo"], (None, ""))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_afiliados.TestAfiliadosDb.test_pending_guarda_afiliado_codigo -v`
Expected: FAIL — `KeyError`/coluna não gravada (`afiliado_codigo` volta None mesmo passando "DRAMARIA")

- [ ] **Step 3: Implement**

Substituir o corpo de `criar_pending` em `app/db.py`:

```python
def criar_pending(dados):
    """Cadastro em aberto (antes do redirect ao checkout). Retorna o token (externalReference)."""
    import secrets
    from datetime import datetime
    token = secrets.token_hex(16)
    with _conn() as c:
        c.execute(
            """INSERT INTO pending_signups (token,nome,email,cpf,whatsapp,plano,metodo,parcelas,valor,afiliado_codigo,criado_em)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (token, dados.get("nome", ""), dados.get("email", ""), dados.get("cpf", ""),
             dados.get("whatsapp", ""), dados.get("plano", ""), dados.get("metodo", ""),
             int(dados.get("parcelas", 1)), float(dados.get("valor", 0)),
             (dados.get("afiliado_codigo", "") or ""), datetime.now().isoformat()),
        )
    return token
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_afiliados -v`
Expected: PASS (4 testes)

- [ ] **Step 5: Commit**

```bash
git add app/db.py app/tests/test_afiliados.py
git commit -m "feat(afiliados): criar_pending persiste afiliado_codigo"
```

---

### Task 4: pricing — `valor_com_desconto` + `comissao`

**Files:**
- Modify: `app/pricing.py` (adicionar funções puras)
- Test: `app/tests/test_pricing.py`

**Interfaces:**
- Produces:
  - `pricing.valor_com_desconto(base, pct) -> float` (arredonda 2 casas)
  - `pricing.comissao(valor_venda, pct) -> float` (arredonda 2 casas)

- [ ] **Step 1: Write the failing test**

Adicionar em `app/tests/test_pricing.py` (dentro de `TestPricing`):

```python
    def test_valor_com_desconto(self):
        self.assertEqual(self.p.valor_com_desconto(997.0, 10), 897.30)
        self.assertEqual(self.p.valor_com_desconto(99.0, 10), 89.10)
        self.assertEqual(self.p.valor_com_desconto(1497.0, 10), 1347.30)
        self.assertEqual(self.p.valor_com_desconto(100.0, 0), 100.0)   # 0% = base

    def test_comissao(self):
        self.assertEqual(self.p.comissao(897.30, 3), 26.92)
        self.assertEqual(self.p.comissao(89.10, 3), 2.67)
        self.assertEqual(self.p.comissao(1000.0, 0), 0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_pricing.TestPricing.test_valor_com_desconto -v`
Expected: FAIL com `AttributeError: module 'pricing' has no attribute 'valor_com_desconto'`

- [ ] **Step 3: Implement**

Adicionar em `app/pricing.py` (após `valor_cartao`/`opcoes_parcelas`):

```python
def valor_com_desconto(base, pct):
    """Aplica pct% de desconto sobre a base. valor_com_desconto(997, 10) -> 897.30"""
    return round(float(base) * (1 - float(pct) / 100.0), 2)


def comissao(valor_venda, pct):
    """pct% de comissão sobre o valor pago. comissao(897.30, 3) -> 26.92"""
    return round(float(valor_venda) * float(pct) / 100.0, 2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_pricing -v`
Expected: PASS (todos, incluindo os 2 novos)

- [ ] **Step 5: Commit**

```bash
git add app/pricing.py app/tests/test_pricing.py
git commit -m "feat(afiliados): pricing.valor_com_desconto e pricing.comissao"
```

---

### Task 5: asaas — `atualizar_valor_assinatura` + checkout com base descontada

**Files:**
- Modify: `app/asaas.py` (adicionar helper de rede após `adiar_vencimento`)
- Test: `app/tests/test_asaas_payload.py`

**Interfaces:**
- Consumes: `asaas.montar_checkout(plano, metodo, parcelas, dados, token, base_url, base=None)` (já existe — aceita `base`)
- Produces: `asaas.atualizar_valor_assinatura(sid, valor) -> dict` (PUT `/subscriptions/{sid}` com `updatePendingPayments=False`)

- [ ] **Step 1: Write the failing test**

Adicionar em `app/tests/test_asaas_payload.py` um teste de que a base descontada chega no payload (checar o nome real da classe de teste no arquivo e adicionar o método dentro dela; assinatura de `montar_checkout` conforme `app/asaas.py`):

```python
    def test_checkout_com_base_descontada(self):
        import asaas, config
        plano = config.plano_por_slug("anual")
        base_desc = 897.30
        # PIX (à vista): item sai com a base descontada
        p_pix = asaas.montar_checkout(plano, "PIX", 1, {}, "tok", "http://x", base=base_desc)
        self.assertEqual(p_pix["items"][0]["value"], 897.30)
        # CARTÃO (recorrente): 1ª cobrança com a base descontada
        p_card = asaas.montar_checkout(plano, "CARTAO", 1, {}, "tok", "http://x", base=base_desc)
        self.assertEqual(p_card["items"][0]["value"], 897.30)
```

- [ ] **Step 2: Run test to verify it fails / confirm base plumbing**

Run: `cd app && python3 -m unittest tests.test_asaas_payload -v`
Expected: o teste novo PASSA de imediato para o checkout (a base já é plumbed). Se o nome da classe/indentação estiver errado, corrigir. Este passo garante a regressão do desconto no payload. (O helper de rede abaixo não tem teste unitário — é I/O; validado no sandbox.)

- [ ] **Step 3: Implement**

Adicionar em `app/asaas.py` (após `adiar_vencimento`):

```python
def atualizar_valor_assinatura(sid, valor):
    """Atualiza o valor RECORRENTE da assinatura sem tocar cobranças já geradas
    (updatePendingPayments=false). Usado p/ voltar a renovação ao preço cheio depois
    da 1ª cobrança com desconto de afiliado.
    ⚠️ Validar no sandbox: PUT de `value` numa assinatura recém-criada por checkout."""
    return _req(f"subscriptions/{sid}", "PUT",
                {"value": round(float(valor), 2), "updatePendingPayments": False})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_asaas_payload -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/asaas.py app/tests/test_asaas_payload.py
git commit -m "feat(afiliados): asaas.atualizar_valor_assinatura + regressao de checkout descontado"
```

---

### Task 6: serve — `_post_assinar` aplica desconto de afiliado e grava o código

**Files:**
- Modify: `app/serve.py` (`_post_assinar` ~L665-670, o bloco "# Pagamento via checkout Asaas")

**Interfaces:**
- Consumes: `db.afiliado_por_codigo` (Task 1), `pricing.valor_com_desconto` (Task 4), `db.criar_pending` com `afiliado_codigo` (Task 3), `asaas.montar_checkout(..., base=)`
- Produces: quando `cupom` é um código de afiliado ativo, o checkout usa a base descontada e o pending grava `afiliado_codigo`. Cortesia e fluxo normal inalterados.

- [ ] **Step 1: Write the failing test**

Este ponto é glue de handler HTTP (o repo não tem harness de teste de `serve`). A verificação é: (a) a suíte inteira continua verde e (b) smoke manual. Não escreva teste de handler; a lógica de desconto/atribuição já é coberta por Task 3/4 (unit) e Task 7 (webhook, integração). Prossiga para o Step 3.

- [ ] **Step 2: (n/a)**

- [ ] **Step 3: Implement**

Em `app/serve.py`, no `_post_assinar`, substituir o bloco a partir de `# Pagamento via checkout Asaas` (a `import ... asaas` já está no topo do método):

```python
        # Pagamento via checkout Asaas
        n_ativos = len(subscribers.ativos())
        base_vig = pricing.preco_vigente(plano, n_ativos)
        # Cupom de afiliado: 10% off na 1ª venda + atribuição (segue pro checkout PAGO)
        af = db.afiliado_por_codigo(cupom) if cupom else None
        af_codigo = af["codigo"] if af else ""
        base_final = pricing.valor_com_desconto(base_vig, af["pct_desconto"]) if af else base_vig
        valor = pricing.valor_cartao(base_final, parcelas) if metodo == "CARTAO" else base_final
        token = db.criar_pending({**dados, "plano": plano["slug"], "metodo": metodo,
                                  "parcelas": parcelas, "valor": valor, "afiliado_codigo": af_codigo})
        try:
            payload = asaas.montar_checkout(plano, metodo, parcelas, dados, token, config.PUBLIC_URL, base=base_final)
            res = asaas.criar_checkout(payload)
            if not res.get("url"):
                raise RuntimeError("checkout sem url")
            return self._redirect(res["url"])
        except Exception as e:
            print(f"[assinar] checkout falhou: {e}", flush=True)
            return self._html(site_web.pagina_assinar(plano["slug"],
                "Não conseguimos iniciar o pagamento agora. Tente novamente em instantes."))
```

(A ordem no método continua: 1º checa cortesia `db.cupom_valido(cupom)` → grátis; só chega aqui se NÃO for cortesia. Um código de afiliado nunca é cortesia → cai no desconto.)

- [ ] **Step 4: Verify — suíte inteira**

Run: `cd app && python3 -m unittest discover -s tests`
Expected: OK (0 falhas). Confirma que a mudança não regrediu nada.

- [ ] **Step 5: Commit**

```bash
git add app/serve.py
git commit -m "feat(afiliados): _post_assinar aplica desconto de afiliado e grava o codigo no pending"
```

---

### Task 7: webhook — atribuição da comissão + reset da assinatura no cartão + linha no aviso de venda

**Files:**
- Modify: `app/webhook_asaas.py` (`_executar` bloco `ATIVAR` ~L98-134; `_avisar_venda` ~L69-87)
- Test: `app/tests/test_webhook.py`

**Interfaces:**
- Consumes: `db.afiliado_por_codigo`, `db.registrar_comissao` (Tasks 1-2), `pricing.comissao` (Task 4), `asaas.atualizar_valor_assinatura` (Task 5), `db.obter_pending(...)["afiliado_codigo"]` (Task 3)
- Produces: em `ATIVAR`, se o pending tem afiliado ativo, grava 1 comissão sobre `pay.value`; no cartão (com `subscription`) reseta o valor recorrente pro preço cheio. `RENOVAR` não grava comissão.

- [ ] **Step 1: Write the failing test**

Adicionar em `app/tests/test_webhook.py`, na classe `TestProcessar`:

```python
    def _body_valor(self, event="PAYMENT_CONFIRMED", ext="tok", pid="pay_af", value=897.30, sub=None):
        return {"event": event, "payment": {"id": pid, "externalReference": ext, "value": value,
                "customer": "cus_af", "subscription": sub, "dueDate": "2026-07-19"}}

    def test_ativar_com_afiliado_registra_comissao(self):
        self.db.criar_afiliado("Dra. Maria", "", "dramaria", 10, 3)
        tok = self.db.criar_pending({"nome": "Dr. Novo", "whatsapp": "5543999991111",
                                     "email": "n@x.com", "plano": "anual", "metodo": "PIX",
                                     "afiliado_codigo": "DRAMARIA", "valor": 897.30})
        st, msg = self.w.processar(self._body_valor(ext=tok), "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "ativado"))
        comis = self.db.listar_comissoes()
        self.assertEqual(len(comis), 1)
        self.assertAlmostEqual(comis[0]["valor_venda"], 897.30, places=2)
        self.assertAlmostEqual(comis[0]["valor_comissao"], 26.92, places=2)  # 3% de 897.30

    def test_renovar_nao_registra_comissao(self):
        reg = self.s.criar_de_pagamento({"nome": "B", "whatsapp": "5543", "plano": "mensal"},
                                         {"subscription": "sub_af"})
        self.w.processar(self._body_valor(event="PAYMENT_RECEIVED", pid="pr1", sub="sub_af"),
                         "segredo", enviar_fn=self.envfn)
        self.assertEqual(self.db.listar_comissoes(), [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_webhook.TestProcessar.test_ativar_com_afiliado_registra_comissao -v`
Expected: FAIL — `listar_comissoes()` volta `[]` (comissão ainda não é registrada).

- [ ] **Step 3: Implement**

Em `app/webhook_asaas.py`, no `ATIVAR`, capturar o `reg` e registrar a comissão. Trocar a chamada existente:

```python
        subscribers.criar_de_pagamento(
            {"nome": nome, "whatsapp": whatsapp, "email": email, "plano": plano.get("slug", "")},
            {"customer": pay.get("customer"), "subscription": sid, "payment": pid, "proximo_vencimento": prox})
        _boas_vindas(whatsapp, nome, email, enviar_fn)
```

por:

```python
        reg = subscribers.criar_de_pagamento(
            {"nome": nome, "whatsapp": whatsapp, "email": email, "plano": plano.get("slug", "")},
            {"customer": pay.get("customer"), "subscription": sid, "payment": pid, "proximo_vencimento": prox})
        _boas_vindas(whatsapp, nome, email, enviar_fn)
        # Afiliado (D3): comissão sobre o valor pago; no cartão, reseta a renovação ao preço cheio.
        af = db.afiliado_por_codigo((pending or {}).get("afiliado_codigo") or "")
        if af:
            import pricing
            valor_venda = float(pay.get("value") or 0)
            try:
                db.registrar_comissao(af["id"], reg["id"], plano.get("slug", ""),
                                      valor_venda, pricing.comissao(valor_venda, af["pct_comissao"]))
            except Exception as e:
                print(f"[webhook] registrar_comissao falhou: {e}", flush=True)
            if sid and config.ASAAS_API_KEY and plano.get("base"):
                try:
                    import asaas
                    cheio = pricing.preco_vigente(plano, len(subscribers.ativos()))
                    asaas.atualizar_valor_assinatura(sid, cheio)
                except Exception as e:
                    print(f"[webhook] reset valor assinatura falhou: {e}", flush=True)
                    _alertar_admin(pid, sid, "não consegui resetar o valor da assinatura pós-desconto de afiliado — ajuste manual")
```

Depois, na chamada `_avisar_venda` logo abaixo, passar o afiliado:

```python
        try:
            _avisar_venda(nome, (plano.get("nome") or plano.get("slug") or "—"),
                          pay.get("value"), email or whatsapp, len(subscribers.ativos()),
                          afiliado=(af["nome"] if af else None),
                          comissao=(pricing.comissao(float(pay.get("value") or 0), af["pct_comissao"]) if af else None))
        except Exception as e:
            print(f"[webhook] _avisar_venda: {e}", flush=True)
```

E atualizar a assinatura de `_avisar_venda` (aceitar os kwargs novos, retrocompatível):

```python
def _avisar_venda(nome, plano, valor, contato, ativos, afiliado=None, comissao=None):
```

adicionando, dentro do `corpo` (antes de fechar o `</div>` final), quando houver afiliado:

```python
        linha_af = (f'<p style="margin:6px 0;color:#a9bcb2">Afiliado: '
                    f'<b style="color:#e8efe9">{esc(afiliado)}</b> · comissão '
                    f'<b style="color:#e8efe9">R$ {esc(str(comissao))}</b></p>') if afiliado else ""
```

e interpolar `{linha_af}` no HTML (logo após a linha de "Contato:").

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd app && python3 -m unittest tests.test_webhook -v`
Expected: PASS (incluindo `test_ativar_com_afiliado_registra_comissao`, `test_renovar_nao_registra_comissao`, e os antigos como `test_ativar_cria_assinante`).

- [ ] **Step 5: Commit**

```bash
git add app/webhook_asaas.py app/tests/test_webhook.py
git commit -m "feat(afiliados): webhook registra comissao na 1a venda + reset da assinatura (cartao) + aviso"
```

---

### Task 8: site_web — página `/admin/afiliados` + link na navegação

**Files:**
- Modify: `app/site_web.py` (`_admin_nav` — adicionar link; nova função `pagina_admin_afiliados`)
- Test: `app/tests/test_site_web.py`

**Interfaces:**
- Consumes: `db.listar_afiliados()`, `db.listar_comissoes(pago=False)` (Tasks 1-2)
- Produces: `site_web.pagina_admin_afiliados(afiliados: list[dict], comissoes: list[dict], token="") -> str` (HTML). `_admin_nav` ganha item "Afiliados" com key `"afiliados"`.

- [ ] **Step 1: Write the failing test**

Adicionar em `app/tests/test_site_web.py` (na classe `TestRender`):

```python
    def test_pagina_admin_afiliados(self):
        afs = [{"id": "a1", "nome": "Dra. Maria", "contato": "maria@x.com", "codigo": "DRAMARIA",
                "pct_desconto": 10, "pct_comissao": 3, "ativo": 1,
                "n_vendas": 2, "comissao_total": 29.59, "comissao_pendente": 2.67}]
        comis = [{"id": "c1", "afiliado_id": "a1", "subscriber_id": "s1", "plano": "anual",
                  "valor_venda": 897.30, "valor_comissao": 26.92, "pago": 0}]
        h = self.s.pagina_admin_afiliados(afs, comis, token="tk")
        self.assertIn("<!doctype html>", h)
        self.assertIn("DRAMARIA", h)
        self.assertIn("Afiliados", h)
        self.assertIn("criar_afiliado", h)          # form de cadastro
        self.assertIn("marcar_comissao_paga", h)     # botão de baixa
        self.assertIn("26,92", h)                    # comissão formatada BRL

    def test_admin_nav_tem_afiliados(self):
        self.assertIn("/admin/afiliados", self.s._admin_nav("tk", "afiliados"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_site_web.TestRender.test_pagina_admin_afiliados -v`
Expected: FAIL com `AttributeError: module 'site_web' has no attribute 'pagina_admin_afiliados'`

- [ ] **Step 3: Implement**

Em `app/site_web.py`, no `_admin_nav`, adicionar o item antes do WhatsApp:

```python
            + lk("/admin", "👥 Assinantes", "assinantes")
            + lk("/curadoria", "🔬 Curadoria", "curadoria")
            + lk("/agenda", "📅 Agenda", "agenda")
            + lk("/admin/afiliados", "🤝 Afiliados", "afiliados")
            + lk("/admin/whatsapp", "📱 WhatsApp", "whatsapp")
```

Adicionar a função (perto de `pagina_admin`, usa `_esc`, `_pagina`, `_admin_nav`, `fmt_brl` de `pricing`):

```python
def pagina_admin_afiliados(afiliados, comissoes, token=""):
    """Tela de Afiliados: cadastro, tabela com agregados e comissões pendentes."""
    import pricing
    tk = _esc(token)

    def row_af(a):
        on = bool(a.get("ativo"))
        cor = "#2f9e6b" if on else "#7a8a84"
        prox = "0" if on else "1"
        rot = "desativar" if on else "ativar"
        return (
            '<tr style="border-top:1px solid rgba(233,225,198,.1)">'
            f'<td style="padding:11px 10px;font-family:ui-monospace,Menlo,monospace;font-size:14px;color:var(--ouro2)">{_esc(a.get("codigo"))}</td>'
            f'<td style="padding:11px 10px;color:var(--creme)">{_esc(a.get("nome") or "—")}</td>'
            f'<td style="padding:11px 10px;font-size:13px;color:var(--suave)">{_esc(a.get("contato") or "—")}</td>'
            f'<td style="padding:11px 10px;font-size:13px;color:var(--suave)">{_esc(str(a.get("pct_desconto")))}% / {_esc(str(a.get("pct_comissao")))}%</td>'
            f'<td style="padding:11px 10px;color:var(--creme)">{a.get("n_vendas", 0)}</td>'
            f'<td style="padding:11px 10px;color:var(--suave)">{_esc(pricing.fmt_brl(a.get("comissao_total", 0)))}</td>'
            f'<td style="padding:11px 10px;color:var(--ouro2)">{_esc(pricing.fmt_brl(a.get("comissao_pendente", 0)))}</td>'
            f'<td style="padding:11px 10px"><form method="post" action="/admin/afiliados" style="margin:0">'
            f'<input type="hidden" name="token" value="{tk}"><input type="hidden" name="acao" value="toggle_afiliado">'
            f'<input type="hidden" name="id" value="{_esc(a.get("id"))}"><input type="hidden" name="on" value="{prox}">'
            f'<button class="actbtn ghost" style="padding:6px 12px;font-size:12px;color:{cor}">{rot}</button></form></td></tr>')

    linhas = "".join(row_af(a) for a in (afiliados or [])) or \
        '<tr><td colspan="8" style="padding:20px;color:var(--suave)">Nenhum afiliado ainda.</td></tr>'

    nome_af = {a.get("id"): a.get("nome") for a in (afiliados or [])}

    def row_com(c):
        return (
            '<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;padding:11px 0;border-top:1px solid rgba(233,225,198,.1)">'
            f'<div><span style="color:var(--creme)">{_esc(nome_af.get(c.get("afiliado_id"), "—"))}</span>'
            f'<div style="font-family:system-ui;font-size:12px;color:var(--suave)">{_esc(c.get("plano") or "—")} · venda {_esc(pricing.fmt_brl(c.get("valor_venda", 0)))} · '
            f'comissão <b style="color:var(--ouro2)">{_esc(pricing.fmt_brl(c.get("valor_comissao", 0)))}</b></div></div>'
            f'<form method="post" action="/admin/afiliados" style="margin:0">'
            f'<input type="hidden" name="token" value="{tk}"><input type="hidden" name="acao" value="marcar_comissao_paga">'
            f'<input type="hidden" name="id" value="{_esc(c.get("id"))}">'
            f'<button class="actbtn" style="padding:6px 13px;font-size:12px">marcar como paga</button></form></div>')

    comis_lista = "".join(row_com(c) for c in (comissoes or [])) or \
        '<p class="hint" style="margin-top:8px">Nenhuma comissão pendente.</p>'

    corpo = f"""
    <div class="wrap">
      {_admin_nav(token, "afiliados")}
      <div class="sectag" style="margin-top:8px">Painel do curador</div>
      <h2 class="disp" style="font-size:40px;color:var(--creme);margin:2px 0 4px">Afiliados</h2>
      <p class="hint">Código dá <strong>desconto na 1ª venda</strong> ao assinante e gera <strong>comissão</strong> pro afiliado. Pagamento da comissão é manual.</p>
      <div style="overflow-x:auto;margin:18px 0">
        <table style="width:100%;border-collapse:collapse;min-width:760px">
          <thead><tr style="font-family:system-ui;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--suave);text-align:left">
            <th style="padding:8px 10px">Código</th><th style="padding:8px 10px">Nome</th><th style="padding:8px 10px">Contato</th>
            <th style="padding:8px 10px">Desc./Com.</th><th style="padding:8px 10px">Vendas</th>
            <th style="padding:8px 10px">Comissão total</th><th style="padding:8px 10px">Pendente</th><th></th></tr></thead>
          <tbody>{linhas}</tbody>
        </table>
      </div>
      <div style="display:flex;gap:18px;flex-wrap:wrap;margin:10px 0">
        <div class="panel" style="max-width:none;margin:0;flex:1;min-width:300px">
          <h3 style="font-family:'Cormorant Garamond',Georgia,serif;font-size:23px;color:var(--ouro2);margin-bottom:6px">Cadastrar afiliado</h3>
          <form method="post" action="/admin/afiliados">
            <input type="hidden" name="token" value="{tk}"><input type="hidden" name="acao" value="criar_afiliado">
            <label>Nome</label><input type="text" name="nome" placeholder="Dra. Maria">
            <label style="margin-top:10px">Contato (e-mail/WhatsApp p/ pagar)</label><input type="text" name="contato">
            <label style="margin-top:10px">Código do cupom</label><input type="text" name="codigo" placeholder="DRAMARIA">
            <div style="display:flex;gap:10px">
              <div style="flex:1"><label style="margin-top:10px">% desconto</label><input type="number" step="0.1" name="pct_desconto" value="10"></div>
              <div style="flex:1"><label style="margin-top:10px">% comissão</label><input type="number" step="0.1" name="pct_comissao" value="3"></div>
            </div>
            <button class="actbtn" type="submit" style="margin-top:14px">➕ Cadastrar afiliado</button>
          </form>
        </div>
        <div class="panel" style="max-width:none;margin:0;flex:1;min-width:300px">
          <h3 style="font-family:'Cormorant Garamond',Georgia,serif;font-size:23px;color:var(--ouro2);margin-bottom:6px">Comissões pendentes</h3>
          <p class="hint" style="margin-bottom:6px">Pague por fora e clique em "marcar como paga" pra dar baixa.</p>
          <div style="margin-top:10px">{comis_lista}</div>
        </div>
      </div>
    </div>"""
    return _pagina("Afiliados · Admin", corpo, logado=True, meta_extra='<meta name="robots" content="noindex">')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_site_web -v`
Expected: PASS (incluindo os 2 testes novos e os antigos de landing/nav).

- [ ] **Step 5: Commit**

```bash
git add app/site_web.py app/tests/test_site_web.py
git commit -m "feat(afiliados): pagina /admin/afiliados (cadastro + relatorio) + link na navegacao"
```

---

### Task 9: serve — rotas `GET`/`POST /admin/afiliados`

**Files:**
- Modify: `app/serve.py` (GET: antes de `if path.startswith("/admin"):` ~L159; POST: junto aos handlers de `/admin` ~L336-369)

**Interfaces:**
- Consumes: `site_web.pagina_admin_afiliados` (Task 8), `db.listar_afiliados`, `db.listar_comissoes`, `db.criar_afiliado`, `db.toggle_afiliado`, `db.marcar_comissao_paga`
- Produces: `GET /admin/afiliados` renderiza a página; `POST /admin/afiliados` com `acao ∈ {criar_afiliado, toggle_afiliado, marcar_comissao_paga}`.

- [ ] **Step 1: (glue de rota — verificação por suíte + smoke)**

Sem teste de handler (padrão do repo). Verificação = suíte verde + smoke manual no fim.

- [ ] **Step 2: (n/a)**

- [ ] **Step 3: Implement**

Em `app/serve.py`, no `do_GET`, ADICIONAR **antes** de `if path.startswith("/admin"):` (a linha ~159):

```python
        if path == "/admin/afiliados":
            import config, site_web, auth_web, db
            q = up.parse_qs(up.urlparse(self.path).query)
            sess = self._sessao()
            token_ok = config.ADMIN_TOKEN and q.get("token", [""])[0] == config.ADMIN_TOKEN
            if not (token_ok or (sess and auth_web.eh_admin(sess["whatsapp"]))):
                return self._html("<h3>Acesso negado</h3>", 403)
            db.init()
            return self._html(site_web.pagina_admin_afiliados(
                db.listar_afiliados(), db.listar_comissoes(pago=False), config.ADMIN_TOKEN or ""), 200)
```

No `do_POST`, ADICIONAR (junto aos handlers de `/admin`, ex. logo após o bloco `if path == "/admin/whatsapp":` e antes de `if path == "/admin":`):

```python
        if path == "/admin/afiliados":
            import config, auth_web, db
            sess = self._sessao()
            token_ok = bool(config.ADMIN_TOKEN) and g("token") == config.ADMIN_TOKEN
            if not (token_ok or (sess and auth_web.eh_admin(sess["whatsapp"]))):
                return self._html("<h3>Acesso negado</h3>", 403)
            db.init()
            acao = g("acao")
            if acao == "criar_afiliado":
                try:
                    pdesc = float(g("pct_desconto") or "10")
                    pcom = float(g("pct_comissao") or "3")
                except ValueError:
                    pdesc, pcom = 10.0, 3.0
                db.criar_afiliado(g("nome"), g("contato"), g("codigo"), pdesc, pcom)
            elif acao == "toggle_afiliado":
                db.toggle_afiliado(g("id"), g("on") == "1")
            elif acao == "marcar_comissao_paga":
                db.marcar_comissao_paga(g("id"))
            return self._redirect(f"/admin/afiliados?token={config.ADMIN_TOKEN}" if token_ok else "/admin/afiliados")
```

- [ ] **Step 4: Verify — suíte inteira**

Run: `cd app && python3 -m unittest discover -s tests`
Expected: OK (0 falhas) — todos os testes das Tasks 1-8 + os antigos.

- [ ] **Step 5: Commit**

```bash
git add app/serve.py
git commit -m "feat(afiliados): rotas GET/POST /admin/afiliados (cadastro, toggle, baixa de comissao)"
```

---

## Verificação final (smoke manual)

Com `ASAAS_*` de sandbox configurados e o servidor rodando localmente:

1. `GET /admin/afiliados?token=...` → cadastrar afiliada "Dra. Maria" código `DRAMARIA` (10% / 3%).
2. `GET /assinar?plano=anual` → preencher dados, cupom `DRAMARIA`, método PIX → checkout deve mostrar **R$ 897,30** (10% de 997).
3. Simular `PAYMENT_CONFIRMED` (webhook) → assinante ativado; `GET /admin/afiliados` deve listar 1 venda e **comissão pendente R$ 26,92**; e-mail de venda com linha "Afiliado: Dra. Maria".
4. No cartão (sandbox): confirmar que a assinatura teve o `value` resetado pro cheio (renovação futura não descontada). ⚠️ Ponto a validar no sandbox (Task 5/7).
5. "marcar como paga" → some das pendentes.

## Self-Review (feito)

- **Cobertura da spec:** dados (Task 1-2) ✅ · coluna pending (Task 1/3) ✅ · desconto no checkout (Task 4/6) ✅ · "só 1ª venda"/reset cartão (Task 5/7) ✅ · comissão sobre pay.value (Task 7) ✅ · painel admin cadastro+relatório+baixa (Task 8-9) ✅ · aviso de venda com afiliado (Task 7) ✅ · cortesia intacta (Task 6, ordem preservada) ✅.
- **Placeholders:** nenhum — todo passo tem código/comando reais.
- **Consistência de tipos:** `afiliado_por_codigo`→dict; `criar_afiliado`→código str; `listar_afiliados` expõe `n_vendas/comissao_total/comissao_pendente` (usados no render Task 8); `registrar_comissao(afiliado_id, subscriber_id, plano, valor_venda, valor_comissao)` mesma assinatura em Task 2/7; `atualizar_valor_assinatura(sid, valor)` idem Task 5/7; `pagina_admin_afiliados(afiliados, comissoes, token)` idem Task 8/9.
```
