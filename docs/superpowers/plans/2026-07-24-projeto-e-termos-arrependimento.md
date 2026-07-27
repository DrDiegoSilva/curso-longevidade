# Projeto E — Termos, Privacidade & Arrependimento — Plano de Implementação

> **Para workers agênticos:** SUB-SKILL OBRIGATÓRIA: use `superpowers:subagent-driven-development`
> (recomendado) ou `superpowers:executing-plans` para implementar tarefa a tarefa.
> Os passos usam checkbox (`- [ ]`) para acompanhamento.

**Goal:** Publicar termos de uso e política de privacidade versionados, capturar o aceite de
novos e antigos assinantes, e estornar automaticamente a venda quando o cancelamento acontece
dentro dos 7 dias de arrependimento.

**Architecture:** Duas funções puras novas (`refunds.py`) e um módulo de conteúdo (`legal.py`)
alimentam três pontos de integração já existentes: o cancelamento (`serve.py:729`), a área de
conta (`/minha`, `/meus-dados`) e o checkout (`/assinar`). Nenhuma dependência nova — stdlib e
o cliente Asaas que já existe.

**Tech Stack:** Python 3 stdlib, `unittest`, SQLite (produção: Postgres/Supabase via
`DATABASE_URL`), servidor HTTP próprio (`http.server`), HTML gerado em strings f-string.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-24-projeto-e-termos-arrependimento-design.md`
- Branch: `feat/termos-arrependimento` (worktree `.claude/worktrees/termos-arrependimento`)
- **Reembolso após os 7 dias: NENHUM.** Não existe cálculo pro-rata neste projeto.
- Data que conta os 7 dias: `subscribers.criado_em` (gravado na confirmação do pagamento).
- Prazo do arrependimento: **7 dias, inclusivo** (dia 7 ainda tem direito; dia 8 não).
- `legal.VERSAO = "2026-07-24"` — string única usada para aceite e re-aceite.
- Controlador: Clínica Diego Silva LTDA · CNPJ 52.891.914/0001-93 · Av. Adhemar Pereira de
  Barros, 1500, sala 203 — Londrina/PR, CEP 86047-250 · DPO `contato@drdiegosilva.com.br`
- Foro: Londrina/PR **com ressalva expressa do domicílio do consumidor** (CDC art. 101, I).
- Falha de estorno **nunca** bloqueia o cancelamento — vira alerta pro admin.
- Rodar todos os testes: `cd app && python3 -m unittest discover -s tests`
- Teste isolado: `cd app && python3 -m unittest tests.test_refunds -v`
- Commits: `<tipo>(termos): <descrição>` — sem trailer de atribuição.
- **Nunca `git add -A`** — outro agente trabalha no mesmo repositório. Stagear só os arquivos
  da tarefa.

## Estrutura de arquivos

| Arquivo | Responsabilidade | Tarefa |
|---|---|---|
| `app/refunds.py` | **Criar.** Regras puras do arrependimento e do alvo do estorno | 1 |
| `app/tests/test_refunds.py` | **Criar.** Testes das duas funções puras | 1 |
| `app/asaas.py` | **Modificar.** `estornar_pagamento` / `estornar_parcelamento` | 2 |
| `app/tests/test_asaas_estorno.py` | **Criar.** Testes de montagem da chamada | 2 |
| `app/db.py` | **Modificar.** Colunas novas + `estornar_comissao` | 3 |
| `app/tests/test_db_termos.py` | **Criar.** Migração e reversão de comissão | 3 |
| `app/serve.py` | **Modificar.** Estorno no cancelamento; rotas; re-aceite; checkbox | 4, 5, 6, 7 |
| `app/legal.py` | **Criar.** Texto dos termos e da privacidade + `VERSAO` | 5 |
| `app/site_legal.py` | **Criar.** Páginas `/termos`, `/privacidade` e re-aceite | 5, 6 |
| `app/site_web.py` | **Modificar.** Só o checkbox no checkout | 7 |
| `app/tests/test_legal.py` | **Criar.** Versão, cláusulas obrigatórias, escape | 5 |
| `app/tests/test_reaceite.py` | **Criar.** Bloqueio da área de conta | 6 |

---

### Task 1: Regras puras do arrependimento (`refunds.py`)

**Files:**
- Create: `app/refunds.py`
- Test: `app/tests/test_refunds.py`

**Interfaces:**
- Consumes: nada (módulo puro, primeira tarefa)
- Produces:
  - `dentro_arrependimento(criado_em: str | None, hoje: datetime.date, dias: int = 7) -> bool`
  - `alvo_estorno(pagamento: dict) -> tuple[str, str]` — retorna `("installment", id)` quando o
    pagamento faz parte de um parcelamento, senão `("payment", id)`

- [ ] **Step 1: Escrever o teste que falha**

Criar `app/tests/test_refunds.py`:

```python
"""Testes do refunds.py — regra dos 7 dias (CDC art. 49) e alvo do estorno. Standalone."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDentroArrependimento(unittest.TestCase):
    def setUp(self):
        import refunds
        self.r = refunds

    def test_dia_zero_esta_dentro(self):
        self.assertTrue(self.r.dentro_arrependimento("2026-07-24T10:00:00", date(2026, 7, 24)))

    def test_dia_sete_ainda_esta_dentro(self):
        # 7 dias é inclusivo: o consumidor tem o dia 7 inteiro
        self.assertTrue(self.r.dentro_arrependimento("2026-07-24T10:00:00", date(2026, 7, 31)))

    def test_dia_oito_esta_fora(self):
        self.assertFalse(self.r.dentro_arrependimento("2026-07-24T10:00:00", date(2026, 8, 1)))

    def test_data_ausente_fica_fora(self):
        # sem data confiável não estorna automaticamente — dinheiro não sai por chute
        self.assertFalse(self.r.dentro_arrependimento(None, date(2026, 7, 24)))
        self.assertFalse(self.r.dentro_arrependimento("", date(2026, 7, 24)))

    def test_data_malformada_fica_fora(self):
        self.assertFalse(self.r.dentro_arrependimento("ontem", date(2026, 7, 24)))

    def test_data_futura_fica_dentro(self):
        # relógio torto não pode virar negativa de reembolso
        self.assertTrue(self.r.dentro_arrependimento("2026-07-25T10:00:00", date(2026, 7, 24)))

    def test_prazo_configuravel(self):
        self.assertTrue(self.r.dentro_arrependimento("2026-07-24T10:00:00", date(2026, 8, 5), dias=30))


class TestAlvoEstorno(unittest.TestCase):
    def setUp(self):
        import refunds
        self.r = refunds

    def test_pagamento_avulso(self):
        pag = {"id": "pay_123", "value": 997.0}
        self.assertEqual(self.r.alvo_estorno(pag), ("payment", "pay_123"))

    def test_pagamento_parcelado_aponta_pro_parcelamento(self):
        # anual em 12x: estornar só o payment devolveria 1/12 (R$ 83 em vez de R$ 997)
        pag = {"id": "pay_123", "value": 83.08, "installment": "ins_999"}
        self.assertEqual(self.r.alvo_estorno(pag), ("installment", "ins_999"))

    def test_installment_nulo_e_tratado_como_avulso(self):
        pag = {"id": "pay_123", "value": 997.0, "installment": None}
        self.assertEqual(self.r.alvo_estorno(pag), ("payment", "pay_123"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_refunds -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'refunds'`

- [ ] **Step 3: Implementação mínima**

Criar `app/refunds.py`:

```python
"""Regras do direito de arrependimento (CDC art. 49) e escolha do alvo do estorno.
Puro/testável: sem rede, sem banco. Quem chama a API do Asaas é o serve.py.

Regra de negócio (spec 2026-07-24): reembolso existe SOMENTE dentro dos 7 dias.
Depois disso o cancelamento não devolve valor — o acesso segue até o fim do período pago.
"""
from datetime import datetime


def dentro_arrependimento(criado_em, hoje, dias=7):
    """True se `hoje` está dentro do prazo de arrependimento contado de `criado_em`.

    `criado_em` é o ISO de `subscribers.criado_em`, gravado quando o webhook confirma o
    pagamento — é a data da contratação efetiva, que é o marco do art. 49.
    O prazo é INCLUSIVO: no dia `dias` o consumidor ainda tem direito.

    Data ausente ou malformada devolve False de propósito: sem data confiável, dinheiro
    não sai automaticamente. Esses casos seguem pelo caminho manual.
    """
    if not criado_em:
        return False
    try:
        d = datetime.fromisoformat(str(criado_em)).date()
    except (TypeError, ValueError):
        return False
    return (hoje - d).days <= int(dias)


def alvo_estorno(pagamento):
    """Decide o que estornar a partir do objeto de pagamento do Asaas.

    Cartão parcelado vira um `installment` com N cobranças: estornar só o `payment` da
    parcela 1 devolveria 1/12 do valor. Quando o campo `installment` existe, o alvo é o
    parcelamento inteiro.

    Retorna ("installment", id) ou ("payment", id).
    """
    inst = (pagamento or {}).get("installment")
    if inst:
        return ("installment", inst)
    return ("payment", (pagamento or {}).get("id"))
```

- [ ] **Step 4: Rodar o teste e confirmar que passa**

Run: `cd app && python3 -m unittest tests.test_refunds -v`
Expected: PASS — 10 testes OK

- [ ] **Step 5: Commit**

```bash
git add app/refunds.py app/tests/test_refunds.py
git commit -m "feat(termos): refunds.py com regra dos 7 dias e alvo do estorno"
```

---

### Task 2: Estorno na API do Asaas (`asaas.py`)

**Files:**
- Modify: `app/asaas.py` (acrescentar ao final, depois de `adiar_vencimento`)
- Test: `app/tests/test_asaas_estorno.py`

**Interfaces:**
- Consumes: `asaas._req(caminho, metodo, payload)` — já existe em `app/asaas.py:56`
- Produces:
  - `estornar_pagamento(pid: str, valor: float | None = None) -> dict`
  - `estornar_parcelamento(iid: str, valor: float | None = None) -> dict`
  - `valor=None` significa estorno **total** (é sempre o caso neste projeto)

- [ ] **Step 1: Escrever o teste que falha**

Criar `app/tests/test_asaas_estorno.py`:

```python
"""Testes das funções de estorno do asaas.py. Sem rede: _req é substituído. Standalone."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestEstorno(unittest.TestCase):
    def setUp(self):
        import asaas
        self.a = asaas
        self.chamadas = []
        self._req_original = asaas._req

        def fake_req(caminho, metodo="GET", payload=None):
            self.chamadas.append({"caminho": caminho, "metodo": metodo, "payload": payload})
            return {"ok": True}

        asaas._req = fake_req

    def tearDown(self):
        self.a._req = self._req_original

    def test_estorno_total_de_pagamento_nao_manda_valor(self):
        # sem `value` o Asaas estorna o total — é o que queremos no arrependimento
        self.a.estornar_pagamento("pay_123")
        self.assertEqual(self.chamadas[0]["caminho"], "payments/pay_123/refund")
        self.assertEqual(self.chamadas[0]["metodo"], "POST")
        self.assertNotIn("value", self.chamadas[0]["payload"])

    def test_estorno_de_pagamento_com_valor(self):
        self.a.estornar_pagamento("pay_123", 50.0)
        self.assertEqual(self.chamadas[0]["payload"]["value"], 50.0)

    def test_estorno_total_de_parcelamento(self):
        self.a.estornar_parcelamento("ins_999")
        self.assertEqual(self.chamadas[0]["caminho"], "installments/ins_999/refund")
        self.assertEqual(self.chamadas[0]["metodo"], "POST")
        self.assertNotIn("value", self.chamadas[0]["payload"])

    def test_estorno_leva_descricao(self):
        self.a.estornar_pagamento("pay_123")
        self.assertIn("description", self.chamadas[0]["payload"])
        self.assertIn("arrependimento", self.chamadas[0]["payload"]["description"].lower())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_asaas_estorno -v`
Expected: FAIL com `AttributeError: module 'asaas' has no attribute 'estornar_pagamento'`

- [ ] **Step 3: Implementação mínima**

Acrescentar ao final de `app/asaas.py`:

```python
_DESC_ESTORNO = "Cancelamento no prazo de arrependimento (CDC art. 49)."


def _payload_estorno(valor):
    p = {"description": _DESC_ESTORNO}
    if valor is not None:                 # sem `value` o Asaas estorna o total
        p["value"] = float(valor)
    return p


def estornar_pagamento(pid, valor=None):
    """POST /payments/{id}/refund. valor=None => estorno total.
    O saldo sai da conta Asaas; no cartão leva até 10 dias úteis pra aparecer na fatura."""
    return _req(f"payments/{pid}/refund", "POST", _payload_estorno(valor))


def estornar_parcelamento(iid, valor=None):
    """POST /installments/{id}/refund. valor=None => estorno total do parcelamento.
    Usado quando o pagamento faz parte de um parcelamento no cartão — estornar só a
    parcela devolveria uma fração do valor."""
    return _req(f"installments/{iid}/refund", "POST", _payload_estorno(valor))
```

- [ ] **Step 4: Rodar o teste e confirmar que passa**

Run: `cd app && python3 -m unittest tests.test_asaas_estorno -v`
Expected: PASS — 4 testes OK

- [ ] **Step 5: Commit**

```bash
git add app/asaas.py app/tests/test_asaas_estorno.py
git commit -m "feat(termos): estornar_pagamento/estornar_parcelamento no cliente Asaas"
```

---

### Task 3: Colunas de aceite e reversão de comissão (`db.py`)

**Files:**
- Modify: `app/db.py` — `_migrar_colunas()` (linha ~227) e uma função nova perto de
  `registrar_comissao` (linha ~453)
- Modify: `app/subscribers.py:15` — `_COLS`
- Test: `app/tests/test_db_termos.py`

**Interfaces:**
- Consumes: `db._add_coluna(c, tabela, coluna, tipo)` (`app/db.py:216`), `db._conn()`
- Produces:
  - Colunas `subscribers.termos_versao`, `subscribers.termos_aceito_em`, `subscribers.termos_ip`
  - Coluna `comissoes.estornada_em`
  - `db.estornar_comissao(subscriber_id: str) -> int` — nº de comissões marcadas

- [ ] **Step 1: Escrever o teste que falha**

Criar `app/tests/test_db_termos.py`:

```python
"""Testes das colunas de aceite dos termos e da reversão de comissão. Standalone."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestTermosDB(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "subscribers"):
            sys.modules.pop(m, None)
        import db
        self.db = db
        db._INITED = False
        db.init()

    def test_colunas_de_termos_existem(self):
        with self.db._conn() as c:
            cols = [r[1] for r in c.execute("PRAGMA table_info(subscribers)").fetchall()]
        for col in ("termos_versao", "termos_aceito_em", "termos_ip"):
            self.assertIn(col, cols)

    def test_coluna_estornada_em_existe(self):
        with self.db._conn() as c:
            cols = [r[1] for r in c.execute("PRAGMA table_info(comissoes)").fetchall()]
        self.assertIn("estornada_em", cols)

    def test_estornar_comissao_marca_a_comissao_do_assinante(self):
        self.db.registrar_comissao("af1", "sub1", "anual", 997.0, 29.91)
        n = self.db.estornar_comissao("sub1")
        self.assertEqual(n, 1)
        com = [c for c in self.db.listar_comissoes() if c["subscriber_id"] == "sub1"][0]
        self.assertTrue(com["estornada_em"])

    def test_estornar_comissao_de_assinante_sem_comissao_devolve_zero(self):
        self.assertEqual(self.db.estornar_comissao("nao-existe"), 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_db_termos -v`
Expected: FAIL — `AssertionError: 'termos_versao' not found in [...]`

- [ ] **Step 3: Implementação mínima**

Em `app/db.py`, dentro de `_migrar_colunas()`, acrescentar depois da linha
`_add_coluna(c, "pending_signups", "afiliado_codigo", "TEXT")`:

```python
        _add_coluna(c, "subscribers", "termos_versao", "TEXT")
        _add_coluna(c, "subscribers", "termos_aceito_em", "TEXT")
        _add_coluna(c, "subscribers", "termos_ip", "TEXT")
        _add_coluna(c, "pending_signups", "termos_versao", "TEXT")
        _add_coluna(c, "pending_signups", "termos_ip", "TEXT")
        _add_coluna(c, "comissoes", "estornada_em", "TEXT")
```

Ainda em `app/db.py`, acrescentar depois de `marcar_comissao_paga` (perto da linha 483):

```python
def estornar_comissao(subscriber_id):
    """Marca como estornada toda comissão gerada por esse assinante (venda devolvida).
    Sem isso o afiliado receberia comissão de uma venda que deixou de existir.
    Retorna quantas linhas foram marcadas."""
    from datetime import datetime
    with _conn() as c:
        cur = c.execute("UPDATE comissoes SET estornada_em=? WHERE subscriber_id=? AND estornada_em IS NULL",
                        (datetime.now().isoformat(), subscriber_id))
        return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
```

Em `app/subscribers.py`, na lista `_COLS` (linha 15), acrescentar as três colunas ao final,
antes de `"senha_hash"`:

```python
_COLS = ["id", "nome", "whatsapp", "email", "cpf", "plano", "metodo", "status",
         "asaas_customer_id", "asaas_subscription_id", "asaas_payment_id",
         "proximo_vencimento", "acesso_ate", "carencia_ate", "aviso_renov_em",
         "criado_em", "cancelado_em", "cancel_motivo", "oferta_retencao_em",
         "termos_versao", "termos_aceito_em", "termos_ip", "senha_hash"]
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `cd app && python3 -m unittest tests.test_db_termos tests.test_db tests.test_subscribers tests.test_afiliados -v`
Expected: PASS — os 4 novos + os existentes seguem verdes (a migração é aditiva)

- [ ] **Step 5: Commit**

```bash
git add app/db.py app/subscribers.py app/tests/test_db_termos.py
git commit -m "feat(termos): colunas de aceite em subscribers/pending + estornar_comissao"
```

---

### Task 4: Estorno automático no cancelamento (`serve.py`)

**Files:**
- Modify: `app/serve.py:729-747` (`_executar_cancelamento`) e um helper novo antes dela
- Test: `app/tests/test_cancelamento_estorno.py`

**Interfaces:**
- Consumes: `refunds.dentro_arrependimento`, `refunds.alvo_estorno` (Task 1);
  `asaas.estornar_pagamento`, `asaas.estornar_parcelamento` (Task 2);
  `db.estornar_comissao` (Task 3); `asaas.obter_pagamento` (`app/asaas.py:81`, já existe);
  `webhook_asaas._alertar_admin(pid, sid, motivo)` (`app/webhook_asaas.py:56`, já existe)
- Produces: função módulo-nível `serve.estornar_arrependimento(sub) -> float | None` — devolve o
  valor estornado, ou `None` se não havia direito/cobrança ou se o estorno falhou

**Nota de design:** a lógica vai numa **função de módulo**, não num método do handler, para
ser testável sem instanciar o servidor HTTP.

- [ ] **Step 1: Escrever o teste que falha**

Criar `app/tests/test_cancelamento_estorno.py`:

```python
"""Testes do estorno automático no cancelamento (7 dias). Sem rede. Standalone."""
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _sub(dias_atras, pid="pay_1", sid="sub_1"):
    return {"id": "s1", "nome": "Teste", "email": "t@e.com",
            "asaas_payment_id": pid, "asaas_subscription_id": sid,
            "criado_em": (datetime.now() - timedelta(days=dias_atras)).isoformat()}


class TestEstornoArrependimento(unittest.TestCase):
    def setUp(self):
        import serve, asaas, db
        self.serve, self.asaas, self.db = serve, asaas, db
        self.estornos = []
        self.comissoes = []
        self.alertas = []

        self._orig = (asaas.obter_pagamento, asaas.estornar_pagamento,
                      asaas.estornar_parcelamento, db.estornar_comissao)
        asaas.obter_pagamento = lambda pid: {"id": pid, "value": 997.0}
        asaas.estornar_pagamento = lambda pid, valor=None: self.estornos.append(("payment", pid))
        asaas.estornar_parcelamento = lambda iid, valor=None: self.estornos.append(("installment", iid))
        db.estornar_comissao = lambda sid: self.comissoes.append(sid) or 1

        import webhook_asaas
        self._orig_alerta = webhook_asaas._alertar_admin
        webhook_asaas._alertar_admin = lambda pid, sid, motivo: self.alertas.append(motivo)

    def tearDown(self):
        (self.asaas.obter_pagamento, self.asaas.estornar_pagamento,
         self.asaas.estornar_parcelamento, self.db.estornar_comissao) = self._orig
        import webhook_asaas
        webhook_asaas._alertar_admin = self._orig_alerta

    def test_cancelou_no_dia_3_estorna_integral(self):
        valor = self.serve.estornar_arrependimento(_sub(3))
        self.assertEqual(valor, 997.0)
        self.assertEqual(self.estornos, [("payment", "pay_1")])
        self.assertEqual(self.comissoes, ["s1"])

    def test_cancelou_no_dia_30_nao_estorna(self):
        self.assertIsNone(self.serve.estornar_arrependimento(_sub(30)))
        self.assertEqual(self.estornos, [])

    def test_parcelado_estorna_o_parcelamento_inteiro(self):
        self.asaas.obter_pagamento = lambda pid: {"id": pid, "value": 83.08, "installment": "ins_9"}
        self.serve.estornar_arrependimento(_sub(2))
        self.assertEqual(self.estornos, [("installment", "ins_9")])

    def test_cortesia_sem_pagamento_nao_estorna_nem_alerta(self):
        # cupom de cortesia entra sem asaas_payment_id — não é falha, é ausência de cobrança
        self.assertIsNone(self.serve.estornar_arrependimento(_sub(2, pid=None)))
        self.assertEqual(self.estornos, [])
        self.assertEqual(self.alertas, [])

    def test_falha_no_estorno_alerta_e_devolve_none(self):
        def explode(pid, valor=None):
            raise RuntimeError("saldo insuficiente")
        self.asaas.estornar_pagamento = explode
        self.assertIsNone(self.serve.estornar_arrependimento(_sub(2)))
        self.assertEqual(len(self.alertas), 1)
        self.assertIn("estorno", self.alertas[0].lower())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_cancelamento_estorno -v`
Expected: FAIL com `AttributeError: module 'serve' has no attribute 'estornar_arrependimento'`

- [ ] **Step 3: Implementação mínima**

Em `app/serve.py`, acrescentar como **função de módulo** entre o fim da classe do handler
(`def log_message`, linha ~810) e a linha `class Server(socketserver.ThreadingMixIn, ...)`
(linha ~813). Precisa ser nível de módulo — não método — pra ser testável sem instanciar o
servidor HTTP:

```python
def estornar_arrependimento(sub):
    """Estorno INTEGRAL quando o cancelamento cai dentro dos 7 dias (CDC art. 49).

    Devolve o valor estornado, ou None quando não havia direito, não havia cobrança
    (cortesia por cupom) ou o estorno falhou. Falha aqui NUNCA bloqueia o cancelamento:
    o assinante não pode ficar preso por um problema nosso — vira alerta pro admin.
    """
    from datetime import date
    import asaas, db, refunds, webhook_asaas
    if not refunds.dentro_arrependimento(sub.get("criado_em"), date.today()):
        return None
    pid = sub.get("asaas_payment_id")
    if not pid:                       # cortesia por cupom: não houve cobrança pra estornar
        return None
    try:
        pagamento = asaas.obter_pagamento(pid)
        tipo, alvo = refunds.alvo_estorno(pagamento)
        if tipo == "installment":
            asaas.estornar_parcelamento(alvo)
        else:
            asaas.estornar_pagamento(alvo)
        db.estornar_comissao(sub["id"])
        return float(pagamento.get("value") or 0)
    except Exception as e:
        print(f"[cancelar] estorno de arrependimento falhou: {e}", flush=True)
        webhook_asaas._alertar_admin(
            pid, sub.get("asaas_subscription_id"),
            f"ESTORNO de arrependimento FALHOU para {sub.get('nome') or sub.get('id')} "
            f"({e}) — estorne manualmente no painel do Asaas")
        return None
```

Depois, substituir o corpo de `_executar_cancelamento` (`app/serve.py:729-747`) por:

```python
    def _executar_cancelamento(self, sub, motivo):
        import site_web, subscribers, asaas, email_send
        sid = sub.get("asaas_subscription_id")
        try:
            if sid:
                asaas.cancelar_assinatura(sid)
        except Exception as e:
            print(f"[cancelar] cancelar assinatura Asaas falhou: {e}", flush=True)
        estornado = estornar_arrependimento(sub)      # None fora dos 7 dias ou se falhou
        if estornado:                                  # arrependimento: acesso cessa agora
            acesso_ate = None
        else:                                          # regra normal: acesso até o fim do pago
            acesso_ate = sub.get("proximo_vencimento")
        subscribers.registrar_cancelamento(sub["id"], motivo, acesso_ate=acesso_ate)
        if sub.get("email"):
            if estornado:
                corpo = (f"<p>Confirmamos o cancelamento da sua assinatura da Atualização "
                         f"Científica dentro do prazo de arrependimento.</p>"
                         f"<p>O reembolso integral de <strong>R$ {estornado:.2f}</strong> foi "
                         f"solicitado e aparece em até 10 dias úteis, conforme o meio de "
                         f"pagamento utilizado.</p>")
            else:
                ate = f" Seu acesso segue até {acesso_ate}." if acesso_ate else ""
                corpo = (f"<p>Confirmamos o cancelamento da sua assinatura da Atualização "
                         f"Científica. Não haverá novas cobranças.{site_web._esc(ate)}</p>")
            html = (f"<p>Olá {site_web._esc(sub.get('nome') or '')},</p>{corpo}"
                    f"<p>Se mudar de ideia, é só assinar de novo quando quiser.</p>"
                    f"<p>— Dr. Diego Silva · CRM-PR 54310</p>")
            email_send.enviar(sub["email"], "Confirmação de cancelamento — Atualização Científica", html)
        return self._html(site_web.pagina_cancelado(acesso_ate))
```

> **Nota (2026-07-25, rodada final de revisão da Task 4):** o esboço acima —
> `subscribers.registrar_cancelamento(sub["id"], motivo, acesso_ate=acesso_ate)` gravando
> DEPOIS do estorno — foi a versão inicial do Step 3 e não é mais o desenho implementado.
> `subscribers.registrar_cancelamento` **foi removida**: gravar o cancelamento depois de já
> ter mexido no Asaas deixava uma janela em que uma falha no meio (Asaas cancelado mas o
> banco não gravado, ou vice-versa) corrompia o estado. O desenho atual inverte a ordem —
> **claim atômico primeiro, estorno como ajuste depois**:
>
> - `db.claim_cancelamento(sub["id"], motivo, acesso_ate)` grava o cancelamento
>   **inteiro** (status + cancelado_em + motivo + acesso_ate) num único UPDATE
>   condicional — é ao mesmo tempo o claim contra corrida (duplo clique/retry) e a
>   gravação final. `serve._gravar_cancelamento(sub, motivo, acesso_ate)` envolve essa
>   chamada e trata a ambiguidade de exceção (venceu/perdeu/incerto — ver docstring em
>   `app/serve.py`).
> - Só depois disso o Asaas é cancelado e `estornar_arrependimento(sub)` roda (só
>   quando o claim venceu com certeza — nunca em "incerto").
> - Se o estorno sai, o AJUSTE é `db.encerrar_acesso(sub["id"])` (zera o acesso), não
>   uma segunda gravação do cancelamento inteiro.
> - `estornar_arrependimento` hoje devolve `(valor, tipo)` — não só `float` — porque
>   no cartão parcelado o Asaas estorna o parcelamento inteiro mas `valor` continua
>   sendo o de uma parcela; `tipo` é o que deixa `_email_cancelamento` saber que não
>   pode imprimir esse número.
>
> Ver o código real em `app/serve.py` (`_executar_cancelamento`, `_gravar_cancelamento`,
> `estornar_arrependimento`, `_email_cancelamento`) em vez deste esboço histórico —
> qualquer task futura gerada a partir deste plano deve implementar contra o código
> atual, não reintroduzir `subscribers.registrar_cancelamento`.

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `cd app && python3 -m unittest tests.test_cancelamento_estorno -v && python3 -m unittest discover -s tests`
Expected: PASS — 5 testes novos + suíte inteira verde

- [ ] **Step 5: Commit**

```bash
git add app/serve.py app/tests/test_cancelamento_estorno.py
git commit -m "feat(termos): estorno integral automático no cancelamento dentro dos 7 dias"
```

---

### Task 5: Conteúdo legal e páginas públicas (`legal.py`, `/termos`, `/privacidade`)

**Files:**
- Create: `app/legal.py`
- Create: `app/site_legal.py` — páginas legais em módulo próprio (o `site_web.py` já tem 1545
  linhas e está sendo editado por outro agente; manter as páginas legais fora dele evita
  conflito de merge)
- Modify: `app/serve.py` — duas rotas GET públicas (junto das outras rotas públicas, perto da
  linha 305)
- Test: `app/tests/test_legal.py`

**Interfaces:**
- Consumes: `site_web._pagina(titulo, corpo, logado=False, meta_extra="", atual="")`
  (`app/site_web.py:349`), `site_web._esc`
- Produces:
  - `legal.VERSAO: str` — `"2026-07-24"`
  - `legal.TERMOS: list[tuple[str, str]]` — lista de `(título_da_cláusula, html_do_corpo)`
  - `legal.PRIVACIDADE: list[tuple[str, str]]` — mesma forma
  - `site_legal.pagina_termos() -> str`, `site_legal.pagina_privacidade() -> str`

**Cláusula 2 (renovação):** é a única que depende da verificação pendente descrita no spec
(Risco 2). O texto abaixo descreve a renovação **por método**, que é verdade pelo código
(`asaas.py:40-51`) independentemente de como o Asaas trata `RECURRENT` + `installmentCount`.
Confirmar antes de publicar.

- [ ] **Step 1: Escrever o teste que falha**

Criar `app/tests/test_legal.py`:

```python
"""Testes do conteúdo legal: versão, cláusulas obrigatórias e render das páginas. Standalone."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestLegal(unittest.TestCase):
    def setUp(self):
        import legal
        self.legal = legal

    def test_versao_definida(self):
        self.assertTrue(self.legal.VERSAO)
        self.assertRegex(self.legal.VERSAO, r"^\d{4}-\d{2}-\d{2}$")

    def test_termos_tem_clausula_de_reembolso_negando_apos_o_prazo(self):
        texto = " ".join(corpo for _, corpo in self.legal.TERMOS)
        self.assertIn("NÃO gerando reembolso", texto)

    def test_termos_tem_prazo_de_arrependimento_de_7_dias(self):
        texto = " ".join(corpo for _, corpo in self.legal.TERMOS)
        self.assertIn("7 (sete) dias", texto)

    def test_termos_ressalvam_o_foro_do_consumidor(self):
        # eleição pura de foro contra consumidor é nula (CDC art. 51, IV c/c 101, I)
        texto = " ".join(corpo for _, corpo in self.legal.TERMOS)
        self.assertIn("Londrina", texto)
        self.assertIn("domicílio", texto)
        self.assertIn("101", texto)

    def test_privacidade_identifica_o_controlador(self):
        texto = " ".join(corpo for _, corpo in self.legal.PRIVACIDADE)
        self.assertIn("52.891.914/0001-93", texto)
        self.assertIn("Clínica Diego Silva LTDA", texto)
        self.assertIn("contato@drdiegosilva.com.br", texto)

    def test_privacidade_lista_os_operadores(self):
        texto = " ".join(corpo for _, corpo in self.legal.PRIVACIDADE)
        self.assertIn("Asaas", texto)


class TestPaginasLegais(unittest.TestCase):
    def test_pagina_termos_renderiza(self):
        import site_legal, legal
        html = site_legal.pagina_termos()
        self.assertIn("<!doctype html>", html)
        self.assertIn(legal.VERSAO, html)
        self.assertIn(legal.TERMOS[0][0], html)

    def test_pagina_privacidade_renderiza(self):
        import site_legal, legal
        html = site_legal.pagina_privacidade()
        self.assertIn("<!doctype html>", html)
        self.assertIn("52.891.914/0001-93", html)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_legal -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'legal'`

- [ ] **Step 3: Implementação mínima**

Criar `app/legal.py`:

```python
"""Conteúdo dos Termos de Assinatura e da Política de Privacidade.

Só CONTEÚDO — o layout fica no site_web. Cada documento é uma lista de
(título da cláusula, HTML do corpo), pra facilitar renderizar numerado e testar cláusula
a cláusula.

VERSAO é a chave do aceite: mudou o texto de forma relevante, sobe a VERSAO e todo mundo
re-aceita no próximo login. Nunca reaproveitar uma versão antiga com texto novo.
"""

VERSAO = "2026-07-24"

CONTROLADOR = {
    "razao_social": "Clínica Diego Silva LTDA",
    "cnpj": "52.891.914/0001-93",
    "endereco": "Av. Adhemar Pereira de Barros, 1500, sala 203 — Londrina/PR, CEP 86047-250",
    "email": "contato@drdiegosilva.com.br",
}

_ASSINATURA = "Atualização Científica"

TERMOS = [
    ("Quem somos e o que é o serviço",
     f"<p>O {_ASSINATURA} é um serviço de assinatura operado por "
     f"<strong>{CONTROLADOR['razao_social']}</strong>, CNPJ {CONTROLADOR['cnpj']}, "
     f"com sede em {CONTROLADOR['endereco']}.</p>"
     f"<p>O serviço consiste no envio de resumos de estudos científicos por WhatsApp em dias "
     f"úteis, com acesso ao portal do assinante e ao arquivo das edições. O conteúdo tem "
     f"finalidade informativa e de educação continuada, <strong>não constitui prescrição, "
     f"diagnóstico ou conduta médica</strong>, e não substitui o julgamento clínico do "
     f"assinante.</p>"),

    ("Preço, cobrança e renovação",
     "<p>O preço vigente é o exibido na página de contratação no momento da compra. A cobrança "
     "é processada pelo Asaas (Asaas Gestão Financeira S.A.), que é quem trata os dados de "
     "pagamento.</p>"
     "<p><strong>Renovação depende da forma de pagamento escolhida:</strong></p>"
     "<ul>"
     "<li><strong>Cartão de crédito:</strong> a assinatura é recorrente e <strong>renova "
     "automaticamente</strong> ao fim de cada ciclo, pelo preço vigente à época da renovação, "
     "até que o assinante cancele.</li>"
     "<li><strong>Pix:</strong> o pagamento é avulso e <strong>não renova automaticamente</strong>. "
     "Ao fim do período contratado o acesso se encerra, salvo nova contratação.</li>"
     "</ul>"
     "<p>Avisamos por e-mail antes do fim de cada ciclo.</p>"),

    ("Cancelamento",
     "<p>O assinante pode cancelar a qualquer momento, sem multa, pela área de conta "
     "(<em>Minha conta → Cancelar assinatura</em>). O cancelamento interrompe cobranças "
     "futuras de imediato.</p>"),

    ("Reembolso",
     "<p><strong>4.1 — Direito de arrependimento (7 dias).</strong> Por se tratar de contratação "
     "à distância, o assinante pode desistir em até <strong>7 (sete) dias</strong> contados da "
     "confirmação do pagamento, com <strong>devolução integral</strong> do valor pago, nos termos "
     "do art. 49 do Código de Defesa do Consumidor. Basta cancelar pela área de conta dentro do "
     "prazo: o estorno é solicitado automaticamente e aparece em até 10 dias úteis, conforme o "
     "meio de pagamento.</p>"
     "<p><strong>4.2 — Após o prazo de arrependimento.</strong> O cancelamento do plano Anual "
     "após o prazo de arrependimento interrompe as cobranças futuras, <strong>NÃO gerando "
     "reembolso</strong> dos valores já pagos. O acesso permanece ativo até o término do período "
     "contratado.</p>"),

    ("Uso do conteúdo",
     "<p>O conteúdo é licenciado para uso pessoal e intransferível do assinante. É vedada a "
     "redistribuição, revenda, publicação ou compartilhamento do material com terceiros, "
     "inclusive o repasse do acesso.</p>"
     "<p>O acesso é individual e vinculado ao número de WhatsApp cadastrado. Indícios de "
     "compartilhamento podem levar à suspensão do acesso.</p>"),

    ("Disponibilidade",
     "<p>Envios ocorrem em dias úteis. Eventuais interrupções por manutenção, falha de "
     "terceiros (WhatsApp, provedores de e-mail, processador de pagamento) ou caso fortuito não "
     "caracterizam descumprimento, e o período afetado é compensado na vigência da assinatura "
     "sempre que aplicável.</p>"),

    ("Dados pessoais",
     "<p>O tratamento de dados pessoais está descrito na "
     "<a href=\"/privacidade\">Política de Privacidade</a>, que integra estes Termos.</p>"),

    ("Alterações destes Termos",
     "<p>Estes Termos podem ser alterados. Alterações relevantes são comunicadas e passam a "
     "exigir novo aceite no acesso à área de conta. O assinante que não concordar pode cancelar "
     "nos termos da cláusula 3.</p>"),

    ("Foro",
     "<p>Fica eleito o foro da Comarca de Londrina/PR para dirimir controvérsias, "
     "<strong>ressalvado ao CONSUMIDOR o direito de ajuizar ação no foro de seu domicílio</strong>, "
     "nos termos do art. 101, I, do Código de Defesa do Consumidor.</p>"),
]

PRIVACIDADE = [
    ("Controlador",
     f"<p>O controlador dos dados é <strong>{CONTROLADOR['razao_social']}</strong>, "
     f"CNPJ {CONTROLADOR['cnpj']}, {CONTROLADOR['endereco']}.</p>"
     f"<p>Canal do titular e do encarregado: "
     f"<a href=\"mailto:{CONTROLADOR['email']}\">{CONTROLADOR['email']}</a>.</p>"),

    ("Dados que coletamos",
     "<ul>"
     "<li><strong>Cadastro:</strong> nome, e-mail, CPF e número de WhatsApp.</li>"
     "<li><strong>Pagamento:</strong> processado pelo Asaas. Dados de cartão são coletados e "
     "armazenados pelo Asaas — <strong>não temos acesso a eles</strong>. Recebemos apenas "
     "identificadores da cobrança, valor e status.</li>"
     "<li><strong>Uso:</strong> registros de acesso, preferências de horário de envio e histórico "
     "de envios.</li>"
     "</ul>"),

    ("Finalidade e base legal",
     "<ul>"
     "<li><strong>Executar o contrato</strong> (art. 7º, V da LGPD): entregar os resumos, dar "
     "acesso ao portal, processar cobranças e enviar avisos de renovação e cancelamento.</li>"
     "<li><strong>Cumprir obrigação legal</strong> (art. 7º, II): emissão fiscal e guarda de "
     "registros.</li>"
     "<li><strong>Legítimo interesse</strong> (art. 7º, IX): prevenção a fraude e a "
     "compartilhamento indevido de acesso.</li>"
     "</ul>"
     "<p>O CPF é coletado por exigência do processador de pagamento para emissão da cobrança.</p>"),

    ("Com quem compartilhamos",
     "<p>Compartilhamos o mínimo necessário com operadores que viabilizam o serviço:</p>"
     "<ul>"
     "<li><strong>Asaas</strong> — processamento de pagamentos e emissão de cobranças.</li>"
     "<li><strong>Provedor de mensagens WhatsApp</strong> — entrega dos resumos.</li>"
     "<li><strong>Provedor de e-mail</strong> — avisos transacionais.</li>"
     "<li><strong>Infraestrutura de hospedagem e banco de dados.</strong></li>"
     "</ul>"
     "<p>Não vendemos dados pessoais e não os cedemos para publicidade de terceiros.</p>"),

    ("Por quanto tempo guardamos",
     "<p>Dados de cadastro e de assinatura são mantidos enquanto durar a relação e, após o "
     "encerramento, pelo prazo necessário ao cumprimento de obrigações legais e à defesa em "
     "eventual processo. Depois disso são eliminados ou anonimizados.</p>"),

    ("Direitos do titular",
     "<p>O titular pode solicitar confirmação de tratamento, acesso, correção, anonimização, "
     "portabilidade, informação sobre compartilhamento e eliminação de dados tratados com base "
     "no consentimento, nos termos do art. 18 da LGPD.</p>"
     f"<p>Os pedidos devem ser feitos por "
     f"<a href=\"mailto:{CONTROLADOR['email']}\">{CONTROLADOR['email']}</a> e são respondidos "
     f"nos prazos legais. Parte dos dados pode ser mantida quando houver obrigação legal ou "
     f"necessidade de defesa em processo.</p>"),

    ("Segurança",
     "<p>Adotamos medidas técnicas e administrativas para proteger os dados, incluindo controle "
     "de acesso, autenticação do assinante por código enviado ao WhatsApp cadastrado, e tráfego "
     "criptografado. Nenhum sistema é infalível — incidentes relevantes são comunicados aos "
     "titulares e à ANPD conforme a LGPD.</p>"),

    ("Cookies",
     "<p>Usamos apenas cookie de sessão para manter o assinante autenticado. Não usamos cookies "
     "de publicidade nem rastreamento de terceiros.</p>"),

    ("Alterações desta Política",
     "<p>Esta Política pode ser atualizada. Alterações relevantes são comunicadas e passam a "
     "exigir novo aceite no acesso à área de conta.</p>"),
]
```

Criar `app/site_legal.py`:

```python
"""Páginas dos documentos legais. Reaproveita o layout do site_web (_pagina/_esc/PRODUTO)
sem engordar aquele arquivo, que já é o maior do projeto."""
from site_web import _pagina, _esc, PRODUTO


def _pagina_legal(titulo, secoes):
    """Renderiza um documento legal numerado (termos ou privacidade)."""
    import legal
    itens = "".join(
        f'<section style="margin:26px 0"><h3 style="color:var(--cream);font-size:19px;'
        f'margin:0 0 8px">{i}. {_esc(tit)}</h3>{corpo}</section>'
        for i, (tit, corpo) in enumerate(secoes, start=1))
    corpo = (f'<div class="wrap"><div class="panel" style="max-width:760px;line-height:1.65">'
             f'<h2 class="disp">{_esc(titulo)}</h2>'
             f'<p class="hint">Versão {_esc(legal.VERSAO)}</p>'
             f'{itens}'
             f'<p class="hint" style="margin-top:28px">'
             f'<a href="/termos" style="color:var(--ouro2)">Termos de Assinatura</a> · '
             f'<a href="/privacidade" style="color:var(--ouro2)">Política de Privacidade</a>'
             f'</p></div></div>')
    return _pagina(f"{titulo} · {PRODUTO}", corpo, logado=False)


def pagina_termos():
    import legal
    return _pagina_legal("Termos de Assinatura", legal.TERMOS)


def pagina_privacidade():
    import legal
    return _pagina_legal("Política de Privacidade", legal.PRIVACIDADE)
```

Em `app/serve.py`, junto das rotas GET públicas (perto da linha 305, antes do bloco
`if path == "/minha":`), acrescentar:

```python
        if path == "/termos":
            return self._html(site_legal.pagina_termos())
        if path == "/privacidade":
            return self._html(site_legal.pagina_privacidade())
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `cd app && python3 -m unittest tests.test_legal -v && python3 -m unittest discover -s tests`
Expected: PASS — 8 testes novos + suíte verde

- [ ] **Step 5: Commit**

```bash
git add app/legal.py app/site_legal.py app/serve.py app/tests/test_legal.py
git commit -m "feat(termos): legal.py + páginas públicas /termos e /privacidade"
```

---

### Task 6: Re-aceite bloqueando a área de conta

**Files:**
- Modify: `app/serve.py` — rotas GET `/minha` (linha ~310) e `/meus-dados` (linha ~320);
  rota POST `/aceitar-termos` nova (perto da linha 579)
- Modify: `app/site_legal.py` — `pagina_aceite_termos`
- Modify: `app/subscribers.py` — `registrar_aceite`
- Test: `app/tests/test_reaceite.py`

**Interfaces:**
- Consumes: `legal.VERSAO` (Task 5), `db._conn` / `subscribers.marcar_status` (`app/subscribers.py:143`)
- Produces:
  - `subscribers.precisa_aceitar(sub: dict) -> bool`
  - `subscribers.registrar_aceite(id: str, versao: str, ip: str = "") -> None`
  - `site_legal.pagina_aceite_termos(destino: str) -> str`

- [ ] **Step 1: Escrever o teste que falha**

Criar `app/tests/test_reaceite.py`:

```python
"""Testes do re-aceite dos termos pela base atual. Standalone."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPrecisaAceitar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "subscribers"):
            sys.modules.pop(m, None)
        import db, subscribers, legal
        db._INITED = False
        db.init()
        self.subs, self.legal = subscribers, legal

    def test_assinante_sem_aceite_precisa_aceitar(self):
        self.assertTrue(self.subs.precisa_aceitar({"termos_versao": None}))
        self.assertTrue(self.subs.precisa_aceitar({}))

    def test_assinante_com_versao_antiga_precisa_aceitar(self):
        self.assertTrue(self.subs.precisa_aceitar({"termos_versao": "2020-01-01"}))

    def test_assinante_com_versao_atual_nao_precisa(self):
        self.assertFalse(self.subs.precisa_aceitar({"termos_versao": self.legal.VERSAO}))

    def test_registrar_aceite_grava_versao_data_e_ip(self):
        reg = self.subs.criar_de_pagamento(
            {"nome": "T", "whatsapp": "43999990000", "email": "t@e.com", "plano": "anual"}, {})
        self.subs.registrar_aceite(reg["id"], self.legal.VERSAO, "203.0.113.7")
        atual = [s for s in self.subs.listar() if s["id"] == reg["id"]][0]
        self.assertEqual(atual["termos_versao"], self.legal.VERSAO)
        self.assertTrue(atual["termos_aceito_em"])
        self.assertEqual(atual["termos_ip"], "203.0.113.7")
        self.assertFalse(self.subs.precisa_aceitar(atual))


class TestPaginaAceite(unittest.TestCase):
    def test_pagina_tem_checkbox_e_links(self):
        import site_legal
        html = site_legal.pagina_aceite_termos("/minha")
        self.assertIn('name="aceito"', html)
        self.assertIn('action="/aceitar-termos"', html)
        self.assertIn('href="/termos"', html)
        self.assertIn('href="/privacidade"', html)
        self.assertIn('value="/minha"', html)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_reaceite -v`
Expected: FAIL com `AttributeError: module 'subscribers' has no attribute 'precisa_aceitar'`

- [ ] **Step 3: Implementação mínima**

Acrescentar ao final de `app/subscribers.py`:

```python
def precisa_aceitar(sub):
    """True quando o assinante ainda não aceitou a versão vigente dos termos.
    Vale tanto pra base antiga (nunca aceitou) quanto pra quem aceitou versão anterior."""
    import legal
    return (sub or {}).get("termos_versao") != legal.VERSAO


def registrar_aceite(id, versao, ip=""):
    """Grava o aceite: versão, momento e IP — é a prova de que o assinante concordou."""
    _ensure()
    with db._conn() as c:
        c.execute("UPDATE subscribers SET termos_versao=?, termos_aceito_em=?, termos_ip=? WHERE id=?",
                  (versao, datetime.now().isoformat(), ip or "", id))
```

Acrescentar ao final de `app/site_legal.py`:

```python
def pagina_aceite_termos(destino="/minha"):
    """Tela de re-aceite. Bloqueia a área de conta — NÃO interrompe o envio diário:
    o assinante continua recebendo o que pagou."""
    import legal
    corpo = f"""
    <div class="wrap"><div class="panel" style="max-width:560px">
      <h2 class="disp">Atualizamos nossos termos</h2>
      <p class="hint">Publicamos os <strong>Termos de Assinatura</strong> e a
        <strong>Política de Privacidade</strong> do serviço. Para continuar usando sua conta,
        confirme que leu e concorda. Seus envios diários seguem normalmente.</p>
      <p class="hint">
        <a href="/termos" target="_blank" style="color:var(--ouro2)">Ler os Termos</a> ·
        <a href="/privacidade" target="_blank" style="color:var(--ouro2)">Ler a Política de Privacidade</a>
      </p>
      <form method="post" action="/aceitar-termos">
        <input type="hidden" name="destino" value="{_esc(destino)}">
        <label class="section-label" style="display:flex;gap:10px;align-items:flex-start;margin:18px 0">
          <input type="checkbox" name="aceito" value="1" required>
          <span>Li e aceito os Termos de Assinatura e a Política de Privacidade
            (versão {_esc(legal.VERSAO)}).</span>
        </label>
        <button class="cta" type="submit">Continuar</button>
      </form>
    </div></div>"""
    return _pagina(f"Atualizamos nossos termos · {PRODUTO}", corpo, logado=True)
```

Em `app/serve.py`, na rota GET `/minha` (linha ~310), inserir a checagem **depois** de
resolver a sessão e **antes** de renderizar a página:

```python
        if path == "/minha":
            sub = self._sessao()
            if not sub:
                return self._redirect("/entrar")
            import subscribers as _subs
            reg = self._sub_logado()
            if reg and _subs.precisa_aceitar(reg):
                return self._html(site_legal.pagina_aceite_termos("/minha"))
            import auth_web
            return self._html(site_web.pagina_minha(sub, admin=auth_web.eh_admin(sub["whatsapp"])))
```

Na rota GET `/meus-dados` (linha ~320), logo depois de `sub = self._sub_logado()` e do
redirect de não-logado:

```python
            import subscribers as _subs_t
            if _subs_t.precisa_aceitar(sub):
                return self._html(site_legal.pagina_aceite_termos("/meus-dados"))
```

E acrescentar a rota POST (perto da linha 579, junto de `/cancelar`):

```python
        if path == "/aceitar-termos":
            return self._aceitar_termos(g)
```

Com o handler (junto de `_cancelar_motivo`, perto da linha 692):

```python
    def _aceitar_termos(self, g):
        import subscribers, legal
        sub = self._sub_logado()
        if not sub:
            return self._redirect("/entrar")
        if g("aceito") != "1":
            return self._html(site_legal.pagina_aceite_termos(g("destino") or "/minha"))
        ip = (self.headers.get("X-Forwarded-For", "").split(",")[0].strip()
              or self.client_address[0])
        subscribers.registrar_aceite(sub["id"], legal.VERSAO, ip)
        destino = g("destino") or "/minha"
        if not destino.startswith("/"):        # nunca redireciona pra fora do site
            destino = "/minha"
        return self._redirect(destino)
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `cd app && python3 -m unittest tests.test_reaceite -v && python3 -m unittest discover -s tests`
Expected: PASS — 5 testes novos + suíte verde

- [ ] **Step 5: Commit**

```bash
git add app/subscribers.py app/site_legal.py app/serve.py app/tests/test_reaceite.py
git commit -m "feat(termos): re-aceite bloqueando /minha e /meus-dados"
```

---

### Task 7: Checkbox de aceite no checkout — **EXECUTAR POR ÚLTIMO**

> **PARE ANTES DE COMEÇAR.** Esta tarefa mexe em `site_web.pagina_assinar` e
> `serve._post_assinar` — os mesmos pontos que **outro agente** estava editando no branch
> `feat/landing-copy-pizza` (preços e landing). Antes de qualquer edição:
>
> ```bash
> git -C /Users/diegosilva/dev/curso-longevidade log --oneline -5 feat/landing-copy-pizza
> git -C /Users/diegosilva/dev/curso-longevidade status --short
> ```
>
> Se o trabalho dele ainda não foi mesclado na `main`, **pare e pergunte ao Diego**. Se já foi,
> rode `git rebase main` neste branch antes de editar, para trabalhar sobre a versão final
> dele — o código abaixo pode precisar de ajuste conforme a landing que ele entregou.

**Files:**
- Modify: `app/site_web.py` — `pagina_assinar` (linha ~1480, junto do campo de cupom)
- Modify: `app/serve.py` — `_post_assinar` (linha ~756, junto das validações)
- Modify: `app/db.py` — `criar_pending` (linha 263)
- Modify: `app/webhook_asaas.py` — ramo `ATIVAR` (linha ~131)
- Test: `app/tests/test_aceite_checkout.py`

**Interfaces:**
- Consumes: `legal.VERSAO` (Task 5), `subscribers.criar_de_pagamento` (`app/subscribers.py:129`)
- Produces: aceite gravado no `pending_signups` e copiado pro assinante na ativação

- [ ] **Step 1: Escrever o teste que falha**

Criar `app/tests/test_aceite_checkout.py`:

```python
"""Testes do aceite no checkout: obrigatório no POST e propagado na ativação. Standalone."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAceiteNoCheckout(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "subscribers"):
            sys.modules.pop(m, None)
        import db, legal
        db._INITED = False
        db.init()
        self.db, self.legal = db, legal

    def test_pagina_assinar_tem_checkbox_obrigatorio(self):
        import site_web
        html = site_web.pagina_assinar("anual")
        self.assertIn('name="aceito"', html)
        self.assertIn('href="/termos"', html)
        self.assertIn('href="/privacidade"', html)

    def test_pending_guarda_a_versao_aceita(self):
        token = self.db.criar_pending({"nome": "T", "email": "t@e.com", "cpf": "1", "whatsapp": "43999990000",
                                       "plano": "anual", "metodo": "PIX", "parcelas": 1, "valor": 997.0,
                                       "termos_versao": self.legal.VERSAO, "termos_ip": "203.0.113.7"})
        p = self.db.obter_pending(token)
        self.assertEqual(p["termos_versao"], self.legal.VERSAO)
        self.assertEqual(p["termos_ip"], "203.0.113.7")

    def test_ativacao_copia_o_aceite_pro_assinante(self):
        import subscribers
        reg = subscribers.criar_de_pagamento(
            {"nome": "T", "whatsapp": "43999990000", "email": "t@e.com", "plano": "anual",
             "termos_versao": self.legal.VERSAO, "termos_ip": "203.0.113.7"}, {})
        atual = [s for s in subscribers.listar() if s["id"] == reg["id"]][0]
        self.assertEqual(atual["termos_versao"], self.legal.VERSAO)
        self.assertFalse(subscribers.precisa_aceitar(atual))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_aceite_checkout -v`
Expected: FAIL — `AssertionError: 'name="aceito"' not found`

- [ ] **Step 3: Implementação mínima**

Em `app/site_web.py`, dentro de `pagina_assinar`, logo **depois** do campo de cupom
(a linha que contém `placeholder="cortesia ou afiliado"`) e **antes** do
`<button class="btn-pay"`:

```python
            <label class="section-label" style="display:flex;gap:10px;align-items:flex-start;margin:16px 0;font-weight:400">
              <input type="checkbox" name="aceito" value="1" required>
              <span>Li e aceito os <a href="/termos" target="_blank" style="color:var(--ouro2)">Termos de Assinatura</a>
                e a <a href="/privacidade" target="_blank" style="color:var(--ouro2)">Política de Privacidade</a>.</span>
            </label>
```

Em `app/serve.py`, dentro de `_post_assinar`, logo depois da validação do CPF
(`if not cpfval.valida(...)`), acrescentar:

```python
        if g("aceito") != "1":
            return self._html(site_web.pagina_assinar(
                plano["slug"], "É preciso aceitar os Termos e a Política de Privacidade."))
```

E, na chamada de `db.criar_pending` (linha ~797), acrescentar os dois campos:

```python
        import legal
        ip_cliente = (self.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                      or self.client_address[0])
        token = db.criar_pending({**dados, "plano": plano["slug"], "metodo": metodo,
                                  "parcelas": parcelas, "valor": valor, "afiliado_codigo": af_codigo,
                                  "termos_versao": legal.VERSAO, "termos_ip": ip_cliente})
```

Em `app/db.py`, `criar_pending` (linha 263) passa a gravar as colunas novas:

```python
def criar_pending(dados):
    """Cadastro em aberto (antes do redirect ao checkout). Retorna o token (externalReference)."""
    import secrets
    from datetime import datetime
    token = secrets.token_hex(16)
    with _conn() as c:
        c.execute(
            """INSERT INTO pending_signups (token,nome,email,cpf,whatsapp,plano,metodo,parcelas,valor,afiliado_codigo,termos_versao,termos_ip,criado_em)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (token, dados.get("nome", ""), dados.get("email", ""), dados.get("cpf", ""),
             dados.get("whatsapp", ""), dados.get("plano", ""), dados.get("metodo", ""),
             int(dados.get("parcelas", 1)), float(dados.get("valor", 0)),
             (dados.get("afiliado_codigo", "") or ""),
             (dados.get("termos_versao", "") or ""), (dados.get("termos_ip", "") or ""),
             datetime.now().isoformat()),
        )
    return token
```

Em `app/subscribers.py`, `criar_de_pagamento` (linha 129) passa a copiar o aceite:

```python
    reg = {"id": secrets.token_hex(6), "nome": pending.get("nome", ""),
           "whatsapp": _norm(pending.get("whatsapp", "")), "email": pending.get("email", ""),
           "cpf": pending.get("cpf", ""), "plano": pending.get("plano", ""),
           "metodo": pending.get("metodo", ""), "status": status,
           "asaas_customer_id": a.get("customer"), "asaas_subscription_id": a.get("subscription"),
           "asaas_payment_id": a.get("payment"), "proximo_vencimento": a.get("proximo_vencimento"),
           "termos_versao": pending.get("termos_versao") or "",
           "termos_aceito_em": datetime.now().isoformat() if pending.get("termos_versao") else "",
           "termos_ip": pending.get("termos_ip") or "",
           "criado_em": datetime.now().isoformat()}
```

Em `app/webhook_asaas.py`, no ramo `ATIVAR` (linha ~131), passar o aceite do pending adiante:

```python
        reg = subscribers.criar_de_pagamento(
            {"nome": nome, "whatsapp": whatsapp, "email": email, "plano": plano.get("slug", ""),
             "termos_versao": (pending or {}).get("termos_versao", ""),
             "termos_ip": (pending or {}).get("termos_ip", "")},
            {"customer": pay.get("customer"), "subscription": sid, "payment": pid, "proximo_vencimento": prox})
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `cd app && python3 -m unittest tests.test_aceite_checkout -v && python3 -m unittest discover -s tests`
Expected: PASS — 3 testes novos + suíte inteira verde (atenção especial a
`tests.test_site_web` e `tests.test_webhook`, que tocam essas funções)

- [ ] **Step 5: Commit**

```bash
git add app/site_web.py app/serve.py app/db.py app/subscribers.py app/webhook_asaas.py app/tests/test_aceite_checkout.py
git commit -m "feat(termos): checkbox de aceite no checkout, propagado do pending ao assinante"
```

---

## Antes de publicar

- [ ] **Confirmar a cláusula 2 (renovação).** É o item em aberto do spec (Risco 2): o Asaas
      aceita `RECURRENT` + `installmentCount` juntos? O texto atual descreve a renovação por
      método de pagamento, o que é verdade pelo código — mas se a verificação mostrar que o
      anual no cartão **não** renova, a cláusula 2 precisa ser reescrita antes de ir ao ar.
      Scripts prontos em `scratchpad/verificar_recorrencia.py` e `scratchpad/testar_checkout_anual.py`.
- [ ] Suíte inteira verde: `cd app && python3 -m unittest discover -s tests`
- [ ] Abrir `/termos` e `/privacidade` no navegador e conferir o layout no tema verde/ouro
- [ ] Fazer login com um assinante de teste e confirmar que a tela de re-aceite aparece e some
      depois de aceitar
- [ ] Deploy: `git push origin main` + `services.app.deployService` no EasyPanel
