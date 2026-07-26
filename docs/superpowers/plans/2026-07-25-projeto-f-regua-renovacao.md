# Projeto F — Régua de renovação — Plano de Implementação

> **Para workers agênticos:** SUB-SKILL OBRIGATÓRIA: use `superpowers:subagent-driven-development`
> (recomendado) ou `superpowers:executing-plans` para implementar tarefa a tarefa.
> Os passos usam checkbox (`- [ ]`) para acompanhamento.

**Goal:** Criar o caminho de renovação (`/renovar`) e uma régua de mensagens configurável que
avisa, pelo WhatsApp, quem tem plano anual sem renovação automática — antes e depois do
vencimento.

**Architecture:** Dois módulos puros novos (`regua.py`, `renovacao.py`) com as regras de
elegibilidade, datas e preço; uma tabela de automações que o Diego edita no admin; um ledger
de idempotência no padrão do `envios_dia`; e um disparador diário pendurado na rotina das 08h
que já existe.

**Tech Stack:** Python 3 stdlib, `unittest`, SQLite (produção: Postgres/Supabase via
`DATABASE_URL`), servidor HTTP próprio (`http.server`), HTML em f-strings.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-25-projeto-f-regua-renovacao-design.md`
- Branch: `feat/termos-arrependimento` (worktree `.claude/worktrees/termos-arrependimento`)
- **Público da régua:** plano anual, `asaas_subscription_id` **vazio**, `cancelado_em` **vazio**.
  Não inventar critério por método de pagamento — o sinal é a ausência de assinatura recorrente.
- **Convenção de sinal:** `offset_vencimento` devolve `hoje - vencimento`. Faltando 7 dias = `-7`;
  no dia = `0`; vencido há 15 = `+15`. Igualdade direta com o campo `dias` da automação.
- **Automações padrão:** `-7, -3, 0, +1, +3, +15`, todas no canal `whatsapp`.
- **Bônus de +1 mês (30 dias) só quando o acesso JÁ expirou.** Renovar no dia do vencimento
  ainda conta como "tem acesso" — sem bônus.
- **Renovação cobra o valor contratado**, não o de tabela. Sem cupom de afiliado. Desconto Pix vale.
- **Canais:** régua e confirmação de renovação manual no WhatsApp; confirmação de renovação
  automática no e-mail; boas-vindas nos dois (inalterado). Nenhuma mensagem sai duplicada.
- Envio que falha **não** grava o ledger e **nunca** interrompe os outros assinantes nem o
  envio diário dos estudos.
- Rodar todos os testes: `cd app && python3 -m unittest discover -s tests`
- Baseline ao iniciar: **340 testes verdes**
- Commits: `<tipo>(regua): <descrição>` — sem trailer de atribuição.
- **Nunca `git add -A`** — stagear só os arquivos da tarefa.

## Estrutura de arquivos

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `app/regua.py` | **Criar.** Regras puras + o disparador (mesma forma do `billing_notices.py`) | 1, 4 |
| `app/renovacao.py` | **Criar.** Preço e datas da renovação (puro) | 2 |
| `app/db.py` | **Modificar.** Tabelas `automacoes_renovacao` e `avisos_renovacao`, CRUD, seed, coluna `valor_contratado` | 3 |
| `app/webhook_asaas.py` | **Modificar.** Grava `valor_contratado`; divide a confirmação por canal | 3, 7 |
| `app/daily.py` | **Modificar.** `rotina_08h` chama o disparador | 4 |
| `app/billing_notices.py` | **Modificar.** Passa a alcançar só quem tem renovação automática | 4 |
| `app/site_web.py` | **Modificar.** Seção de automações no admin; Pix fora do mensal | 5, 7 |
| `app/serve.py` | **Modificar.** POST das automações; rota `/renovar` | 5, 6 |
| `app/config.py` | **Modificar.** Mensal sem Pix | 7 |

---

### Task 1: Regras puras da régua (`regua.py`)

**Files:**
- Create: `app/regua.py`
- Test: `app/tests/test_regua.py`

**Interfaces:**
- Consumes: nada (primeira tarefa)
- Produces:
  - `offset_vencimento(vencimento, hoje) -> int | None`
  - `na_regua(sub: dict, plano: dict) -> bool`
  - `automacoes_do_dia(automacoes: list[dict], offset: int | None) -> list[dict]`

- [ ] **Step 1: Escrever o teste que falha**

Criar `app/tests/test_regua.py`:

```python
"""Testes das regras puras da régua de renovação. Standalone."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ANUAL = {"slug": "anual", "cycle": "YEARLY"}
MENSAL = {"slug": "mensal", "cycle": "MONTHLY"}


def _sub(**kw):
    base = {"id": "s1", "asaas_subscription_id": None, "cancelado_em": None,
            "proximo_vencimento": "2026-08-01"}
    base.update(kw)
    return base


class TestOffsetVencimento(unittest.TestCase):
    def setUp(self):
        import regua
        self.r = regua

    def test_faltando_sete_dias_da_menos_sete(self):
        self.assertEqual(self.r.offset_vencimento("2026-08-01", date(2026, 7, 25)), -7)

    def test_no_dia_do_vencimento_da_zero(self):
        self.assertEqual(self.r.offset_vencimento("2026-08-01", date(2026, 8, 1)), 0)

    def test_vencido_ha_quinze_dias_da_mais_quinze(self):
        self.assertEqual(self.r.offset_vencimento("2026-08-01", date(2026, 8, 16)), 15)

    def test_aceita_iso_com_hora(self):
        self.assertEqual(self.r.offset_vencimento("2026-08-01T10:30:00", date(2026, 8, 1)), 0)

    def test_data_ausente_ou_malformada_da_none(self):
        # None mantém o assinante fora da régua em vez de mandar mensagem errada
        self.assertIsNone(self.r.offset_vencimento(None, date(2026, 8, 1)))
        self.assertIsNone(self.r.offset_vencimento("", date(2026, 8, 1)))
        self.assertIsNone(self.r.offset_vencimento("amanhã", date(2026, 8, 1)))


class TestNaRegua(unittest.TestCase):
    def setUp(self):
        import regua
        self.r = regua

    def test_anual_sem_assinatura_recorrente_entra(self):
        # Pix e cartão parcelado não criam subscription no Asaas -> não renovam sozinhos
        self.assertTrue(self.r.na_regua(_sub(), ANUAL))

    def test_anual_com_assinatura_recorrente_fica_fora(self):
        # cartão à vista renova sozinho, não precisa ser avisado
        self.assertFalse(self.r.na_regua(_sub(asaas_subscription_id="sub_1"), ANUAL))

    def test_mensal_fica_fora(self):
        # mensal só existe no cartão, e cartão mensal renova sozinho
        self.assertFalse(self.r.na_regua(_sub(), MENSAL))

    def test_quem_cancelou_a_renovacao_fica_fora(self):
        # ele já comunicou que quer sair; insistir no WhatsApp gera bloqueio
        self.assertFalse(self.r.na_regua(_sub(cancelado_em="2026-07-20T10:00:00"), ANUAL))

    def test_plano_ausente_fica_fora(self):
        self.assertFalse(self.r.na_regua(_sub(), {}))
        self.assertFalse(self.r.na_regua(_sub(), None))


class TestAutomacoesDoDia(unittest.TestCase):
    def setUp(self):
        import regua
        self.r = regua
        self.autos = [
            {"id": "a1", "dias": -7, "ativo": 1, "canal": "whatsapp", "texto": "x"},
            {"id": "a2", "dias": -3, "ativo": 1, "canal": "whatsapp", "texto": "x"},
            {"id": "a3", "dias": -3, "ativo": 0, "canal": "whatsapp", "texto": "x"},
        ]

    def test_casa_apenas_o_offset_exato(self):
        r = self.r.automacoes_do_dia(self.autos, -7)
        self.assertEqual([a["id"] for a in r], ["a1"])

    def test_automacao_inativa_nao_dispara(self):
        r = self.r.automacoes_do_dia(self.autos, -3)
        self.assertEqual([a["id"] for a in r], ["a2"])

    def test_offset_sem_automacao_devolve_vazio(self):
        self.assertEqual(self.r.automacoes_do_dia(self.autos, -99), [])

    def test_offset_none_devolve_vazio(self):
        self.assertEqual(self.r.automacoes_do_dia(self.autos, None), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_regua -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'regua'`

- [ ] **Step 3: Implementação mínima**

Criar `app/regua.py`:

```python
"""Régua de renovação: quem avisar, quando, e com qual automação.

As funções deste bloco são puras (sem rede, sem banco) — o disparador que usa o banco e manda
mensagem fica no fim do arquivo, no mesmo formato do billing_notices.py.

Público da régua: plano ANUAL, sem assinatura recorrente no Asaas e que não cancelou.
Cartão à vista e mensal criam `subscription` no Asaas e renovam sozinhos; Pix (DETACHED) e
cartão parcelado não criam — é a ausência desse id que identifica quem precisa agir.
"""
from datetime import datetime


def offset_vencimento(vencimento, hoje):
    """`hoje - vencimento` em dias. Faltando 7 dias => -7; no dia => 0; vencido há 15 => +15.

    Mesma convenção do campo `dias` da automação, então o casamento é igualdade direta.
    Devolve None quando a data é ausente ou malformada: sem data confiável o assinante fica
    fora da régua, em vez de receber um aviso com prazo errado.
    """
    if not vencimento:
        return None
    try:
        d = datetime.fromisoformat(str(vencimento)).date()
    except (TypeError, ValueError):
        return None
    return (hoje - d).days


def na_regua(sub, plano):
    """True se este assinante deve receber a régua."""
    if (plano or {}).get("cycle") != "YEARLY":
        return False
    if (sub or {}).get("asaas_subscription_id"):
        return False                      # renova sozinho no cartão
    if (sub or {}).get("cancelado_em"):
        return False                      # já pediu para sair
    return True


def automacoes_do_dia(automacoes, offset):
    """Automações ativas cujo `dias` bate exatamente com o offset de hoje."""
    if offset is None:
        return []
    return [a for a in (automacoes or [])
            if a.get("ativo") and int(a.get("dias")) == offset]
```

- [ ] **Step 4: Rodar o teste e confirmar que passa**

Run: `cd app && python3 -m unittest tests.test_regua -v`
Expected: PASS — 13 testes OK

- [ ] **Step 5: Commit**

```bash
git add app/regua.py app/tests/test_regua.py
git commit -m "feat(regua): regras puras de elegibilidade e casamento de automação"
```

---

### Task 2: Preço e datas da renovação (`renovacao.py`)

**Files:**
- Create: `app/renovacao.py`
- Modify: `app/webhook_asaas.py:11-12` (mover `_CICLO_DIAS` para o módulo novo)
- Test: `app/tests/test_renovacao.py`

**Interfaces:**
- Consumes: nada de tarefas anteriores
- Produces:
  - `CICLO_DIAS: dict` — mapa de ciclo do Asaas para dias (`{"MONTHLY": 30, ..., "YEARLY": 365}`)
  - `preco_renovacao(sub: dict, plano: dict) -> float`
  - `novo_vencimento(acesso_ate, hoje, dias_ciclo, bonus_dias=0) -> datetime.date`

**Nota:** `webhook_asaas.py` já tem um `_CICLO_DIAS` privado idêntico. Mova a constante para
`renovacao.py` como `CICLO_DIAS` (pública) e faça o `webhook_asaas` importá-la, em vez de
duplicar o mapa em dois arquivos.

- [ ] **Step 1: Escrever o teste que falha**

Criar `app/tests/test_renovacao.py`:

```python
"""Testes de preço e datas da renovação. Standalone."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PLANO = {"slug": "anual", "cycle": "YEARLY", "base": 1099.0}


class TestPrecoRenovacao(unittest.TestCase):
    def setUp(self):
        import renovacao
        self.r = renovacao

    def test_usa_o_valor_contratado_quando_existe(self):
        # founder que entrou a 1099 renova a 1099, mesmo se a tabela já subiu
        self.assertEqual(self.r.preco_renovacao({"valor_contratado": 1099.0}, PLANO), 1099.0)

    def test_valor_contratado_diferente_do_base_e_respeitado(self):
        self.assertEqual(self.r.preco_renovacao({"valor_contratado": 897.30}, PLANO), 897.30)

    def test_sem_valor_contratado_cai_no_base_do_plano(self):
        # base atual de assinantes foi criada antes da coluna existir
        self.assertEqual(self.r.preco_renovacao({}, PLANO), 1099.0)
        self.assertEqual(self.r.preco_renovacao({"valor_contratado": None}, PLANO), 1099.0)
        self.assertEqual(self.r.preco_renovacao({"valor_contratado": 0}, PLANO), 1099.0)

    def test_valor_contratado_invalido_cai_no_base(self):
        self.assertEqual(self.r.preco_renovacao({"valor_contratado": "abc"}, PLANO), 1099.0)


class TestNovoVencimento(unittest.TestCase):
    def setUp(self):
        import renovacao
        self.r = renovacao

    def test_com_acesso_vigente_estende_do_fim_atual(self):
        # renovou faltando 15 dias -> não pode perder esses 15 dias
        novo = self.r.novo_vencimento("2026-08-01", date(2026, 7, 17), 365)
        self.assertEqual(novo, date(2027, 8, 1))

    def test_no_dia_do_vencimento_ainda_conta_como_acesso_vigente(self):
        novo = self.r.novo_vencimento("2026-08-01", date(2026, 8, 1), 365)
        self.assertEqual(novo, date(2027, 8, 1))

    def test_no_dia_do_vencimento_nao_ganha_bonus(self):
        novo = self.r.novo_vencimento("2026-08-01", date(2026, 8, 1), 365, bonus_dias=30)
        self.assertEqual(novo, date(2027, 8, 1))

    def test_expirado_conta_de_hoje(self):
        novo = self.r.novo_vencimento("2026-08-01", date(2026, 8, 10), 365)
        self.assertEqual(novo, date(2027, 8, 10))

    def test_expirado_ganha_o_bonus(self):
        # +1 mês de resgate: só para quem já tinha perdido o acesso
        novo = self.r.novo_vencimento("2026-08-01", date(2026, 8, 10), 365, bonus_dias=30)
        self.assertEqual(novo, date(2027, 9, 9))

    def test_sem_data_de_acesso_conta_de_hoje_com_bonus(self):
        novo = self.r.novo_vencimento(None, date(2026, 8, 10), 365, bonus_dias=30)
        self.assertEqual(novo, date(2027, 9, 9))

    def test_data_malformada_conta_de_hoje(self):
        novo = self.r.novo_vencimento("ontem", date(2026, 8, 10), 365)
        self.assertEqual(novo, date(2027, 8, 10))


class TestCicloDias(unittest.TestCase):
    def test_mapa_publico_cobre_os_ciclos_dos_planos(self):
        import renovacao, config
        for p in config.PLANOS:
            self.assertIn(p["cycle"], renovacao.CICLO_DIAS)

    def test_webhook_usa_o_mesmo_mapa(self):
        # sem duplicar a constante em dois arquivos
        import renovacao, webhook_asaas
        self.assertIs(webhook_asaas._CICLO_DIAS, renovacao.CICLO_DIAS)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_renovacao -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'renovacao'`

- [ ] **Step 3: Implementação mínima**

Criar `app/renovacao.py`:

```python
"""Preço e datas da renovação. Puro/testável: sem rede, sem banco.

Duas regras de negócio moram aqui:
- a renovação cobra o valor que o assinante CONTRATOU, não o de tabela (founder renova como
  founder — é o que a cláusula 2 dos termos promete);
- o bônus de resgate só vale para quem JÁ perdeu o acesso; quem renova em dia não ganha.
"""
from datetime import datetime, timedelta

# Ciclo do Asaas -> dias. Fonte única: o webhook_asaas importa daqui.
CICLO_DIAS = {"WEEKLY": 7, "BIWEEKLY": 14, "MONTHLY": 30, "BIMONTHLY": 61,
              "QUARTERLY": 91, "SEMIANNUALLY": 182, "YEARLY": 365}


def preco_renovacao(sub, plano):
    """Valor a cobrar na renovação: o contratado, ou o base do plano quando não houver.

    O fallback existe porque `valor_contratado` só passou a ser gravado agora — os assinantes
    anteriores entraram no preço de lançamento, que é justamente o `base` do plano.
    """
    try:
        v = float((sub or {}).get("valor_contratado") or 0)
    except (TypeError, ValueError):
        v = 0.0
    return v if v > 0 else float(plano["base"])


def novo_vencimento(acesso_ate, hoje, dias_ciclo, bonus_dias=0):
    """Novo fim do acesso depois de uma renovação paga.

    Com acesso vigente, estende a partir do FIM ATUAL — senão o assinante que renova adiantado
    perde os dias que já tinha pago. Já expirado, conta de hoje e ganha o bônus de resgate.
    O dia do vencimento ainda conta como acesso vigente (ele tem o dia inteiro).
    """
    fim = None
    if acesso_ate:
        try:
            fim = datetime.fromisoformat(str(acesso_ate)).date()
        except (TypeError, ValueError):
            fim = None
    vigente = fim is not None and fim >= hoje
    base = fim if vigente else hoje
    extra = 0 if vigente else int(bonus_dias or 0)
    return base + timedelta(days=int(dias_ciclo) + extra)
```

Em `app/webhook_asaas.py`, trocar a constante privada pela importada. Substituir:

```python
CARENCIA_DIAS = 3
_CICLO_DIAS = {"WEEKLY": 7, "BIWEEKLY": 14, "MONTHLY": 30, "BIMONTHLY": 61,
               "QUARTERLY": 91, "SEMIANNUALLY": 182, "YEARLY": 365}
```

por:

```python
CARENCIA_DIAS = 3
# Fonte única do mapa de ciclos (o renovacao.py também usa) — evita as duas cópias divergirem.
from renovacao import CICLO_DIAS as _CICLO_DIAS
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `cd app && python3 -m unittest tests.test_renovacao tests.test_webhook -v`
Expected: PASS — 13 novos + os de webhook seguem verdes

- [ ] **Step 5: Commit**

```bash
git add app/renovacao.py app/webhook_asaas.py app/tests/test_renovacao.py
git commit -m "feat(regua): renovacao.py com preço contratado e cálculo de vencimento"
```

---

### Task 3: Tabelas, CRUD e `valor_contratado` (`db.py`)

**Files:**
- Modify: `app/db.py` — `init()` (CREATE TABLE), `_TABELAS` (linha ~211), `_migrar_colunas()`
  (linha ~227), funções novas perto de `registrar_envio_assinante` (linha ~334)
- Modify: `app/subscribers.py:15` — `_COLS`
- Modify: `app/webhook_asaas.py` — ramo `ATIVAR`, gravar `valor_contratado`
- Test: `app/tests/test_db_regua.py`

**Interfaces:**
- Consumes: `db._add_coluna`, `db._conn`, padrão de seed do `_seed_cupons` (`db.py:251`)
- Produces:
  - `db.listar_automacoes(so_ativas=False) -> list[dict]` — ordenadas por `dias` crescente
  - `db.salvar_automacao(id, dias, canal, texto, ativo) -> str` (id; gera se vier vazio)
  - `db.remover_automacao(id) -> bool`
  - `db.registrar_aviso(subscriber_id, automacao_id, vencimento_ref) -> bool` — `True` se marcou
    agora, `False` se já estava marcado
  - Coluna `subscribers.valor_contratado` (REAL)

- [ ] **Step 1: Escrever o teste que falha**

Criar `app/tests/test_db_regua.py`:

```python
"""Testes das tabelas da régua: automações, ledger de avisos e valor_contratado. Standalone."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestReguaDB(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "subscribers"):
            sys.modules.pop(m, None)
        import db
        self.db = db
        db._INITED = False
        db.init()

    def test_coluna_valor_contratado_existe(self):
        with self.db._conn() as c:
            cols = [r[1] for r in c.execute("PRAGMA table_info(subscribers)").fetchall()]
        self.assertIn("valor_contratado", cols)

    def test_seed_cria_as_seis_automacoes_padrao(self):
        autos = self.db.listar_automacoes()
        self.assertEqual(sorted(a["dias"] for a in autos), [-7, -3, 0, 1, 3, 15])
        self.assertTrue(all(a["canal"] == "whatsapp" for a in autos))
        self.assertTrue(all(a["texto"] for a in autos))

    def test_seed_e_idempotente(self):
        self.db._INITED = False
        self.db.init()
        self.assertEqual(len(self.db.listar_automacoes()), 6)

    def test_listar_ordena_por_dias(self):
        dias = [a["dias"] for a in self.db.listar_automacoes()]
        self.assertEqual(dias, sorted(dias))

    def test_salvar_automacao_nova_gera_id(self):
        novo = self.db.salvar_automacao("", 30, "email", "texto novo", 1)
        self.assertTrue(novo)
        achou = [a for a in self.db.listar_automacoes() if a["id"] == novo][0]
        self.assertEqual(achou["dias"], 30)
        self.assertEqual(achou["canal"], "email")

    def test_salvar_automacao_existente_atualiza(self):
        alvo = self.db.listar_automacoes()[0]
        self.db.salvar_automacao(alvo["id"], alvo["dias"], "email", "outro texto", 0)
        atual = [a for a in self.db.listar_automacoes() if a["id"] == alvo["id"]][0]
        self.assertEqual(atual["texto"], "outro texto")
        self.assertEqual(atual["canal"], "email")
        self.assertFalse(atual["ativo"])

    def test_so_ativas_filtra(self):
        alvo = self.db.listar_automacoes()[0]
        self.db.salvar_automacao(alvo["id"], alvo["dias"], alvo["canal"], alvo["texto"], 0)
        self.assertEqual(len(self.db.listar_automacoes(so_ativas=True)), 5)

    def test_remover_automacao(self):
        alvo = self.db.listar_automacoes()[0]
        self.assertTrue(self.db.remover_automacao(alvo["id"]))
        self.assertEqual(len(self.db.listar_automacoes()), 5)

    def test_registrar_aviso_marca_uma_vez_so(self):
        self.assertTrue(self.db.registrar_aviso("s1", "a1", "2026-08-01"))
        self.assertFalse(self.db.registrar_aviso("s1", "a1", "2026-08-01"))

    def test_ciclo_novo_libera_o_mesmo_aviso(self):
        # o vencimento_ref muda quando ele renova -> a régua volta a valer no ciclo seguinte
        self.assertTrue(self.db.registrar_aviso("s1", "a1", "2026-08-01"))
        self.assertTrue(self.db.registrar_aviso("s1", "a1", "2027-08-01"))

    def test_assinantes_diferentes_nao_se_bloqueiam(self):
        self.assertTrue(self.db.registrar_aviso("s1", "a1", "2026-08-01"))
        self.assertTrue(self.db.registrar_aviso("s2", "a1", "2026-08-01"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_db_regua -v`
Expected: FAIL — `AssertionError: 'valor_contratado' not found in [...]`

- [ ] **Step 3: Implementação mínima**

Em `app/db.py`, dentro do `executescript` de `init()`, acrescentar junto das outras tabelas:

```sql
            CREATE TABLE IF NOT EXISTS automacoes_renovacao (
                id TEXT PRIMARY KEY, dias INTEGER, canal TEXT, texto TEXT,
                ativo INTEGER DEFAULT 1, criado_em TEXT
            );
            CREATE TABLE IF NOT EXISTS avisos_renovacao (
                subscriber_id TEXT, automacao_id TEXT, vencimento_ref TEXT, enviado_em TEXT,
                PRIMARY KEY (subscriber_id, automacao_id, vencimento_ref)
            );
```

Acrescentar as duas ao final da lista `_TABELAS` (linha ~211), para o `ENABLE ROW LEVEL SECURITY`:

```python
            "afiliados", "comissoes", "settings", "envios_slot", "envios_dia",
            "automacoes_renovacao", "avisos_renovacao"]
```

Em `_migrar_colunas()`, acrescentar:

```python
        _add_coluna(c, "subscribers", "valor_contratado", "REAL")
```

Acrescentar as funções (perto de `registrar_envio_assinante`, ~linha 334):

```python
# Textos padrão da régua. {nome}, {ate} (data do vencimento) e {link} (URL do /renovar).
_AUTOMACOES_SEED = [
    (-7, "whatsapp", "Olá {nome}! Sua assinatura da Atualização Científica vence em {ate} — "
                     "daqui a 7 dias. Para não perder nenhum estudo, renove por aqui:\n{link}"),
    (-3, "whatsapp", "{nome}, faltam 3 dias: sua assinatura vence em {ate}. "
                     "A renovação leva 1 minuto:\n{link}"),
    (0,  "whatsapp", "{nome}, sua assinatura vence hoje. A partir de amanhã os estudos param "
                     "de chegar. Renove agora:\n{link}"),
    (1,  "whatsapp", "{nome}, sua assinatura venceu ontem e os estudos pararam. Volte agora e "
                     "ganhe *1 mês extra* de acesso:\n{link}"),
    (3,  "whatsapp", "{nome}, seu acesso está parado há 3 dias. Se voltar agora, você ganha "
                     "*1 mês a mais* junto com a renovação:\n{link}"),
    (15, "whatsapp", "{nome}, última chamada: volte para a Atualização Científica e ganhe "
                     "*1 mês extra*. Depois desta, não insistimos mais.\n{link}"),
]


def _seed_automacoes():
    """Cria as automações padrão 1× (idempotente pelo id determinístico)."""
    from datetime import datetime
    with _conn() as c:
        for dias, canal, texto in _AUTOMACOES_SEED:
            c.execute("INSERT INTO automacoes_renovacao (id,dias,canal,texto,ativo,criado_em) "
                      "VALUES (?,?,?,?,1,?) ON CONFLICT (id) DO NOTHING",
                      (f"seed{dias}", dias, canal, texto, datetime.now().isoformat()))


def listar_automacoes(so_ativas=False):
    """Automações da régua, da mais antecipada para a mais tardia."""
    q = "SELECT * FROM automacoes_renovacao"
    if so_ativas:
        q += " WHERE ativo=1"
    q += " ORDER BY dias ASC"
    with _conn() as c:
        return [dict(r) for r in c.execute(q).fetchall()]


def salvar_automacao(id, dias, canal, texto, ativo=1):
    """Cria (id vazio) ou atualiza uma automação. Devolve o id."""
    import secrets
    from datetime import datetime
    id = (id or "").strip() or secrets.token_hex(6)
    with _conn() as c:
        c.execute("INSERT INTO automacoes_renovacao (id,dias,canal,texto,ativo,criado_em) "
                  "VALUES (?,?,?,?,?,?) ON CONFLICT (id) DO UPDATE SET "
                  "dias=excluded.dias, canal=excluded.canal, texto=excluded.texto, "
                  "ativo=excluded.ativo",
                  (id, int(dias), canal, texto, 1 if int(ativo or 0) else 0,
                   datetime.now().isoformat()))
    return id


def remover_automacao(id):
    with _conn() as c:
        return c.execute("DELETE FROM automacoes_renovacao WHERE id=?", (id,)).rowcount > 0


def registrar_aviso(subscriber_id, automacao_id, vencimento_ref):
    """Marca que este aviso já saiu para este assinante NESTE ciclo. True se marcou agora.

    O `vencimento_ref` é a data de vencimento vigente no momento do envio: quando o assinante
    renova, ela muda e a régua volta a valer no ciclo seguinte sem precisar limpar nada.
    Mesmo padrão do ledger `envios_dia`, que matou o reenvio duplicado dos estudos.
    """
    from datetime import datetime
    with _conn() as c:
        cur = c.execute("INSERT INTO avisos_renovacao "
                        "(subscriber_id,automacao_id,vencimento_ref,enviado_em) VALUES (?,?,?,?) "
                        "ON CONFLICT (subscriber_id,automacao_id,vencimento_ref) DO NOTHING",
                        (subscriber_id or "", automacao_id or "", vencimento_ref or "",
                         datetime.now().isoformat()))
        return cur.rowcount > 0
```

Chamar o seed no fim de `init()`, junto de `_seed_cupons()`:

```python
    _seed_automacoes()
```

Em `app/subscribers.py`, acrescentar `"valor_contratado"` a `_COLS`, antes de `"senha_hash"`.

Em `app/webhook_asaas.py`, ramo `ATIVAR`, acrescentar o valor pago ao dict de criação:

```python
        reg = subscribers.criar_de_pagamento(
            {"nome": nome, "whatsapp": whatsapp, "email": email, "plano": plano.get("slug", ""),
             "termos_versao": (pending or {}).get("termos_versao", ""),
             "termos_ip": (pending or {}).get("termos_ip", ""),
             "valor_contratado": pay.get("value")},
            {"customer": pay.get("customer"), "subscription": sid, "payment": pid,
             "proximo_vencimento": prox})
```

E em `app/subscribers.py`, `criar_de_pagamento`, gravar o campo no registro:

```python
           "valor_contratado": pending.get("valor_contratado"),
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `cd app && python3 -m unittest tests.test_db_regua tests.test_db tests.test_subscribers tests.test_webhook -v`
Expected: PASS — 11 novos + os existentes seguem verdes (as mudanças são aditivas)

- [ ] **Step 5: Commit**

```bash
git add app/db.py app/subscribers.py app/webhook_asaas.py app/tests/test_db_regua.py
git commit -m "feat(regua): tabelas de automações e ledger de avisos + valor_contratado"
```

---

### Task 4: O disparador diário

**Files:**
- Modify: `app/regua.py` — acrescentar o orquestrador ao final
- Modify: `app/daily.py:362-371` — `rotina_08h` chama o disparador
- Modify: `app/billing_notices.py` — `assinantes_a_avisar` passa a exigir renovação automática
- Test: `app/tests/test_regua_disparo.py`

**Interfaces:**
- Consumes: `regua.offset_vencimento`, `regua.na_regua`, `regua.automacoes_do_dia` (Task 1);
  `db.listar_automacoes(so_ativas=True)`, `db.registrar_aviso` (Task 3);
  `subscribers.listar()`, `config.plano_por_slug`, `deliver.enviar_texto`, `email_send.enviar`
- Produces: `regua.disparar(hoje=None, enviar_wa=None, enviar_email=None) -> int` (quantas
  mensagens saíram)

- [ ] **Step 1: Escrever o teste que falha**

Criar `app/tests/test_regua_disparo.py`:

```python
"""Testes do disparador da régua. Sem rede, sem banco real. Standalone."""
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDisparo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "subscribers", "regua"):
            sys.modules.pop(m, None)
        import db, subscribers, regua
        db._INITED = False
        db.init()
        self.db, self.subs, self.regua = db, subscribers, regua
        self.wa = []
        self.emails = []
        # só a automação de -7 fica ativa, para o teste ser determinístico
        for a in db.listar_automacoes():
            db.salvar_automacao(a["id"], a["dias"], a["canal"], a["texto"],
                                1 if a["dias"] == -7 else 0)

    def _criar(self, **kw):
        reg = self.subs.criar_de_pagamento(
            {"nome": "Teste", "whatsapp": "43999990000", "email": "t@e.com", "plano": "anual"},
            {"proximo_vencimento": "2026-08-01"})
        if kw:
            self.subs.marcar_status(reg["id"], kw.pop("status", "ATIVO"), **kw)
        return reg

    def _disparar(self, hoje):
        return self.regua.disparar(hoje=hoje,
                                   enviar_wa=lambda w, m: self.wa.append((w, m)),
                                   enviar_email=lambda e, a, c: self.emails.append((e, a)))

    def test_dispara_no_offset_certo(self):
        self._criar()
        n = self._disparar(date(2026, 7, 25))          # -7
        self.assertEqual(n, 1)
        self.assertEqual(len(self.wa), 1)

    def test_nao_dispara_em_outro_dia(self):
        self._criar()
        self.assertEqual(self._disparar(date(2026, 7, 24)), 0)
        self.assertEqual(self.wa, [])

    def test_rodar_duas_vezes_no_mesmo_dia_envia_uma_vez(self):
        self._criar()
        self._disparar(date(2026, 7, 25))
        self._disparar(date(2026, 7, 25))
        self.assertEqual(len(self.wa), 1)

    def test_quem_tem_assinatura_recorrente_nao_recebe(self):
        reg = self._criar()
        self.subs.marcar_status(reg["id"], "ATIVO", asaas_subscription_id="sub_1")
        self.assertEqual(self._disparar(date(2026, 7, 25)), 0)

    def test_quem_cancelou_nao_recebe(self):
        reg = self._criar()
        self.subs.marcar_status(reg["id"], "CANCELADO", cancelado_em="2026-07-20T10:00:00")
        self.assertEqual(self._disparar(date(2026, 7, 25)), 0)

    def test_marcadores_sao_substituidos(self):
        self._criar()
        self._disparar(date(2026, 7, 25))
        msg = self.wa[0][1]
        self.assertNotIn("{nome}", msg)
        self.assertNotIn("{ate}", msg)
        self.assertNotIn("{link}", msg)
        self.assertIn("/renovar", msg)

    def test_falha_de_envio_nao_grava_ledger_e_nao_derruba_os_outros(self):
        self._criar()

        def explode(w, m):
            raise RuntimeError("whatsapp fora do ar")

        n = self.regua.disparar(hoje=date(2026, 7, 25), enviar_wa=explode,
                                enviar_email=lambda e, a, c: None)
        self.assertEqual(n, 0)
        # como não gravou o ledger, a próxima execução do MESMO dia tenta de novo
        n2 = self._disparar(date(2026, 7, 25))
        self.assertEqual(n2, 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_regua_disparo -v`
Expected: FAIL com `AttributeError: module 'regua' has no attribute 'disparar'`

- [ ] **Step 3: Implementação mínima**

Acrescentar ao final de `app/regua.py`:

```python
def _texto(template, sub, vencimento, link):
    """Substitui os marcadores. Data em pt-BR — ninguém lê ISO num WhatsApp."""
    import site_web
    return (template or "").replace("{nome}", (sub.get("nome") or "").split(" ")[0]) \
                           .replace("{ate}", site_web._data_br(vencimento) or "") \
                           .replace("{link}", link)


def disparar(hoje=None, enviar_wa=None, enviar_email=None):
    """Percorre os assinantes da régua e manda as automações que casam com hoje.

    Cada envio é isolado: falha em um assinante não interrompe os demais e NÃO grava o ledger,
    para que a próxima execução do mesmo dia tente de novo. Passado o dia, o disparo é perdido
    de propósito — "vence em 7 dias" chegando no dia 3 confunde mais do que ajuda.

    Devolve quantas mensagens saíram.
    """
    from datetime import date as _date
    import config, db, subscribers
    hoje = hoje or _date.today()
    if enviar_wa is None:
        import deliver
        enviar_wa = deliver.enviar_texto
    if enviar_email is None:
        import email_send
        enviar_email = lambda dest, assunto, corpo: email_send.enviar(dest, assunto, corpo)

    automacoes = db.listar_automacoes(so_ativas=True)
    link = f"{config.ARTIGOS_URL}/renovar"
    enviadas = 0
    for sub in subscribers.listar():
        plano = config.plano_por_slug(sub.get("plano", "")) or {}
        if not na_regua(sub, plano):
            continue
        venc = sub.get("proximo_vencimento")
        off = offset_vencimento(venc, hoje)
        for a in automacoes_do_dia(automacoes, off):
            if not db.registrar_aviso(sub["id"], a["id"], venc):
                continue                      # já saiu neste ciclo
            try:
                msg = _texto(a.get("texto"), sub, venc, link)
                if a.get("canal") == "email":
                    if sub.get("email"):
                        enviar_email(sub["email"], "Sua assinatura — Atualização Científica", msg)
                else:
                    enviar_wa(sub.get("whatsapp"), msg)
                enviadas += 1
            except Exception as e:
                print(f"[regua] envio falhou p/ {sub.get('id')} ({a.get('id')}): {e}", flush=True)
                try:
                    db.remover_aviso(sub["id"], a["id"], venc)   # destrava a retentativa de hoje
                except Exception as e2:
                    print(f"[regua] remover_aviso falhou: {e2}", flush=True)
    return enviadas
```

Acrescentar em `app/db.py`, junto de `registrar_aviso`:

```python
def remover_aviso(subscriber_id, automacao_id, vencimento_ref):
    """Desfaz a marca do ledger — usado quando o envio falha, para a próxima execução do
    mesmo dia tentar de novo."""
    with _conn() as c:
        c.execute("DELETE FROM avisos_renovacao WHERE subscriber_id=? AND automacao_id=? "
                  "AND vencimento_ref=?", (subscriber_id or "", automacao_id or "",
                                           vencimento_ref or ""))
```

Em `app/daily.py`, `rotina_08h`, acrescentar o disparo depois do aviso de pré-renovação e
antes do `enviar_slot("08h")`:

```python
    try:
        import regua
        n = regua.disparar()
        if n:
            print(f"[regua] {n} mensagem(ns) enviada(s)", flush=True)
    except Exception as e:
        print(f"[regua] erro: {e}", flush=True)
```

Em `app/billing_notices.py`, `assinantes_a_avisar`, restringir a quem renova sozinho —
o resto agora é da régua. Depois do `if s.get("status") != "ATIVO": continue`, acrescentar:

```python
        if not s.get("asaas_subscription_id"):
            continue        # sem assinatura recorrente = régua (regua.py), não este aviso
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `cd app && python3 -m unittest tests.test_regua_disparo tests.test_billing_notices -v && python3 -m unittest discover -s tests`
Expected: PASS — 7 novos + suíte inteira verde

- [ ] **Step 5: Commit**

```bash
git add app/regua.py app/db.py app/daily.py app/billing_notices.py app/tests/test_regua_disparo.py
git commit -m "feat(regua): disparador diário na rotina das 08h + ledger de idempotência"
```

---

### Task 5: Automações editáveis no admin

**Files:**
- Modify: `app/site_web.py:744` — `pagina_admin_mensagens` ganha a seção de automações
- Modify: `app/serve.py:219` (GET, passar as automações) e `:490` (POST, novas ações)
- Test: `app/tests/test_admin_automacoes.py`

**Interfaces:**
- Consumes: `db.listar_automacoes()`, `db.salvar_automacao(id, dias, canal, texto, ativo)`,
  `db.remover_automacao(id)` (Task 3)
- Produces: seção HTML com um formulário por automação + um de criação; ações POST
  `salvar_automacao` e `remover_automacao`

- [ ] **Step 1: Escrever o teste que falha**

Criar `app/tests/test_admin_automacoes.py`:

```python
"""Testes da seção de automações no /admin/mensagens. Standalone."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPaginaAutomacoes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "site_web"):
            sys.modules.pop(m, None)
        import db
        db._INITED = False
        db.init()
        self.db = db

    def test_lista_as_automacoes_na_pagina(self):
        import site_web
        html = site_web.pagina_admin_mensagens(
            "wa", "assunto", "corpo", "renov assunto", "renov corpo",
            automacoes=self.db.listar_automacoes(), token="t")
        self.assertIn("salvar_automacao", html)
        self.assertIn("remover_automacao", html)
        self.assertIn('name="dias"', html)
        self.assertIn('name="canal"', html)
        # as seis padrão aparecem
        for d in (-7, -3, 0, 1, 3, 15):
            self.assertIn(f'value="{d}"', html)

    def test_marcadores_documentados_na_tela(self):
        import site_web
        html = site_web.pagina_admin_mensagens(
            "wa", "a", "c", "ra", "rc", automacoes=self.db.listar_automacoes(), token="t")
        for marcador in ("{nome}", "{ate}", "{link}"):
            self.assertIn(marcador, html)

    def test_pagina_funciona_sem_automacoes(self):
        import site_web
        html = site_web.pagina_admin_mensagens("wa", "a", "c", "ra", "rc",
                                               automacoes=[], token="t")
        self.assertIn("salvar_automacao", html)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_admin_automacoes -v`
Expected: FAIL com `TypeError: pagina_admin_mensagens() got an unexpected keyword argument 'automacoes'`

- [ ] **Step 3: Implementação mínima**

Em `app/site_web.py`, alterar a assinatura de `pagina_admin_mensagens` (linha 744) para aceitar
`automacoes=None` e acrescentar a seção ao corpo da página, antes do fechamento:

```python
def pagina_admin_mensagens(wa, email_assunto, email_corpo, email_renov_assunto="",
                           email_renov_corpo="", token="", msg="", automacoes=None):
```

E, dentro do corpo montado pela função, incluir:

```python
    linhas_auto = "".join(
        f'<form method="post" action="/admin/mensagens" style="border:1px solid #2a4a3c;'
        f'border-radius:10px;padding:12px;margin:10px 0">'
        f'<input type="hidden" name="token" value="{tk}">'
        f'<input type="hidden" name="id" value="{_esc(a["id"])}">'
        f'<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">'
        f'<label>Dias <input type="number" name="dias" value="{int(a["dias"])}" '
        f'style="width:80px"></label>'
        f'<label>Canal <select name="canal">'
        f'<option value="whatsapp"{" selected" if a["canal"] == "whatsapp" else ""}>WhatsApp</option>'
        f'<option value="email"{" selected" if a["canal"] == "email" else ""}>E-mail</option>'
        f'</select></label>'
        f'<label><input type="checkbox" name="ativo" value="1"'
        f'{" checked" if a["ativo"] else ""}> ativa</label>'
        f'</div>'
        f'<textarea name="texto" rows="3" style="width:100%;margin-top:8px">{_esc(a["texto"])}</textarea>'
        f'<button class="cta" type="submit" name="acao" value="salvar_automacao">Salvar</button> '
        f'<button type="submit" name="acao" value="remover_automacao" '
        f'onclick="return confirm(\'Remover esta automação?\')">Remover</button>'
        f'</form>' for a in (automacoes or []))

    nova_auto = (
        f'<form method="post" action="/admin/mensagens" style="border:1px dashed #2a4a3c;'
        f'border-radius:10px;padding:12px;margin:10px 0">'
        f'<input type="hidden" name="token" value="{tk}">'
        f'<input type="hidden" name="id" value="">'
        f'<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">'
        f'<label>Dias <input type="number" name="dias" value="-7" style="width:80px"></label>'
        f'<label>Canal <select name="canal">'
        f'<option value="whatsapp">WhatsApp</option><option value="email">E-mail</option>'
        f'</select></label>'
        f'<label><input type="checkbox" name="ativo" value="1" checked> ativa</label></div>'
        f'<textarea name="texto" rows="3" style="width:100%;margin-top:8px" '
        f'placeholder="Texto da mensagem"></textarea>'
        f'<button class="cta" type="submit" name="acao" value="salvar_automacao">Adicionar</button>'
        f'</form>')

    secao_auto = (
        f'<h3 style="color:var(--cream);margin-top:28px">Régua de renovação</h3>'
        f'<p class="hint">Só alcança o plano anual sem renovação automática (Pix e cartão '
        f'parcelado). <b>Dias</b>: negativo antes do vencimento (-7 = sete dias antes), '
        f'0 no dia, positivo depois (+15 = quinze dias depois). '
        f'Marcadores: <code>{{nome}}</code>, <code>{{ate}}</code>, <code>{{link}}</code>.</p>'
        f'{linhas_auto}{nova_auto}')
```

e concatenar `secao_auto` ao corpo já existente da página.

Em `app/serve.py`, no GET `/admin/mensagens` (linha ~227), passar as automações:

```python
            return self._html(site_web.pagina_admin_mensagens(
                db.get_config(mensagens.K_WA, mensagens.WA_DEFAULT),
                db.get_config(mensagens.K_EMAIL_ASSUNTO, mensagens.EMAIL_ASSUNTO_DEFAULT),
                db.get_config(mensagens.K_EMAIL_CORPO, mensagens.EMAIL_CORPO_DEFAULT),
                db.get_config(mensagens.K_EMAIL_RENOV_ASSUNTO, mensagens.EMAIL_RENOV_ASSUNTO_DEFAULT),
                db.get_config(mensagens.K_EMAIL_RENOV_CORPO, mensagens.EMAIL_RENOV_CORPO_DEFAULT),
                config.ADMIN_TOKEN or "", msg=q.get("msg", [""])[0],
                automacoes=db.listar_automacoes()), 200)
```

No POST `/admin/mensagens` (linha ~497), acrescentar as duas ações antes do redirect:

```python
            if g("acao") == "salvar_automacao":
                try:
                    db.salvar_automacao(g("id"), int(g("dias") or 0), g("canal") or "whatsapp",
                                        g("texto"), 1 if g("ativo") == "1" else 0)
                except (TypeError, ValueError):
                    pass          # dias não numérico: ignora em vez de derrubar a tela
            if g("acao") == "remover_automacao":
                db.remover_automacao(g("id"))
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `cd app && python3 -m unittest tests.test_admin_automacoes tests.test_site_web -v && python3 -m unittest discover -s tests`
Expected: PASS — 3 novos + suíte verde

- [ ] **Step 5: Commit**

```bash
git add app/site_web.py app/serve.py app/tests/test_admin_automacoes.py
git commit -m "feat(regua): automações editáveis no /admin/mensagens"
```

---

### Task 6: Rota `/renovar`

**Files:**
- Modify: `app/serve.py` — rota GET (junto de `/meus-dados`, ~linha 331) e POST (~linha 598)
- Modify: `app/site_web.py` — `pagina_renovar`
- Test: `app/tests/test_renovar_rota.py`

**Interfaces:**
- Consumes: `renovacao.preco_renovacao(sub, plano)`, `renovacao.CICLO_DIAS` (Task 2);
  `pricing.base_cobrada(plano, metodo, base, cupom_pct=0.0)`; `asaas.montar_checkout`,
  `asaas.criar_checkout`; `db.criar_pending`
- Produces: `site_web.pagina_renovar(sub, plano, preco_pix, preco_cartao, vencimento, bonus, erro="")`

**Regras que esta tarefa implementa:**
- Exige sessão de assinante; sem sessão redireciona para `/entrar`
- Preço = `renovacao.preco_renovacao` (contratado), **nunca** o de tabela
- **Sem campo de cupom** — o desconto de afiliado é só na 1ª venda
- Desconto Pix aplicado via `pricing.base_cobrada(plano, "PIX", preco, 0.0)`
- Mostra o bônus de +1 mês **apenas** quando o acesso já expirou

- [ ] **Step 1: Escrever o teste que falha**

Criar `app/tests/test_renovar_rota.py`:

```python
"""Testes da tela de renovação. Standalone."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PLANO = {"slug": "anual", "nome": "Anual", "cycle": "YEARLY", "base": 1099.0,
         "pix_desconto_pct": 5}


class TestPaginaRenovar(unittest.TestCase):
    def setUp(self):
        import site_web
        self.sw = site_web

    def test_mostra_plano_preco_e_vencimento(self):
        html = self.sw.pagina_renovar({"nome": "Teste"}, PLANO, 1044.05, 1099.0,
                                      "2026-08-01", bonus=False)
        self.assertIn("Anual", html)
        self.assertIn("1.044,05", html)
        self.assertIn("1.099,00", html)
        self.assertIn("01/08/2026", html)

    def test_nao_tem_campo_de_cupom(self):
        # cupom de afiliado é só na 1ª venda — a tela de renovação não pode oferecer
        html = self.sw.pagina_renovar({"nome": "T"}, PLANO, 1044.05, 1099.0,
                                      "2026-08-01", bonus=False)
        self.assertNotIn('name="cupom"', html)

    def test_bonus_aparece_so_quando_expirado(self):
        com = self.sw.pagina_renovar({"nome": "T"}, PLANO, 1044.05, 1099.0,
                                     "2026-08-01", bonus=True)
        sem = self.sw.pagina_renovar({"nome": "T"}, PLANO, 1044.05, 1099.0,
                                     "2026-08-01", bonus=False)
        self.assertIn("1 mês extra", com)
        self.assertNotIn("1 mês extra", sem)

    def test_form_posta_o_metodo_escolhido(self):
        html = self.sw.pagina_renovar({"nome": "T"}, PLANO, 1044.05, 1099.0,
                                      "2026-08-01", bonus=False)
        self.assertIn('action="/renovar"', html)
        self.assertIn('name="metodo"', html)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_renovar_rota -v`
Expected: FAIL com `AttributeError: module 'site_web' has no attribute 'pagina_renovar'`

- [ ] **Step 3: Implementação mínima**

Acrescentar ao final de `app/site_web.py`:

```python
def pagina_renovar(sub, plano, preco_pix, preco_cartao, vencimento, bonus=False, erro=""):
    """Tela de renovação do assinante logado. Sem campo de cupom de propósito: o desconto de
    afiliado vale só na 1ª venda. O bônus de +1 mês só aparece para quem já perdeu o acesso."""
    erro_html = f'<div class="erro" style="margin-bottom:16px">{_esc(erro)}</div>' if erro else ""
    bonus_html = ('<p class="hint" style="color:var(--ouro2)"><strong>Volte agora e ganhe '
                  '1 mês extra</strong> — 13 meses pelo preço de 12.</p>') if bonus else ""
    corpo = f"""
    <div class="wrap"><div class="panel" style="max-width:520px">
      <h2 class="disp">Renovar assinatura</h2>
      {erro_html}
      <p class="hint">Plano <strong>{_esc(plano.get("nome") or "")}</strong> ·
         {"acesso encerrado em" if bonus else "vence em"}
         <strong>{_esc(_data_br(vencimento))}</strong></p>
      {bonus_html}
      <form method="post" action="/renovar">
        <label class="section-label">Forma de pagamento</label>
        <div class="paytiles">
          <label class="paytile"><input type="radio" name="metodo" value="PIX" checked>
            <span class="pt-ico">⚡</span><span class="pt-nome">Pix</span>
            <span class="pt-desc">{_esc(pricing.fmt_brl(preco_pix))}</span></label>
          <label class="paytile"><input type="radio" name="metodo" value="CARTAO">
            <span class="pt-ico">💳</span><span class="pt-nome">Cartão</span>
            <span class="pt-desc">{_esc(pricing.fmt_brl(preco_cartao))}</span></label>
        </div>
        <button class="btn-pay" type="submit">Continuar para o pagamento →</button>
      </form>
    </div></div>"""
    return _pagina(f"Renovar · {PRODUTO}", corpo, logado=True)
```

Em `app/serve.py`, rota GET (junto das rotas de assinante logado):

```python
        if path == "/renovar":
            import subscribers as _s, config as _c, renovacao as _r, pricing as _p, site_web
            sub = self._sub_logado()
            if not sub:
                return self._redirect("/entrar")
            plano = _c.plano_por_slug(sub.get("plano", "")) or {}
            if not plano:
                return self._redirect("/minha")
            preco = _r.preco_renovacao(sub, plano)
            expirado = not _s.tem_acesso(sub)
            return self._html(site_web.pagina_renovar(
                sub, plano,
                _p.base_cobrada(plano, "PIX", preco, 0.0),
                _p.base_cobrada(plano, "CARTAO", preco, 0.0),
                sub.get("proximo_vencimento"), bonus=expirado))
```

E o POST:

```python
        if path == "/renovar":
            return self._post_renovar(g)
```

com o handler (junto de `_aceitar_termos`):

```python
    def _post_renovar(self, g):
        """Monta o checkout da renovação. Sem cupom: o desconto de afiliado é só na 1ª venda."""
        import site_web, config, db, subscribers, pricing, renovacao, asaas
        sub = self._sub_logado()
        if not sub:
            return self._redirect("/entrar")
        plano = config.plano_por_slug(sub.get("plano", "")) or {}
        if not plano:
            return self._redirect("/minha")
        metodo = "CARTAO" if g("metodo").upper() == "CARTAO" else "PIX"
        preco = renovacao.preco_renovacao(sub, plano)
        base_final = pricing.base_cobrada(plano, metodo, preco, 0.0)
        dados = {"nome": sub.get("nome", ""), "email": sub.get("email", ""),
                 "cpf": sub.get("cpf", ""), "whatsapp": sub.get("whatsapp", "")}
        token = db.criar_pending({**dados, "plano": plano["slug"], "metodo": metodo,
                                  "parcelas": 1, "valor": base_final, "afiliado_codigo": ""})
        try:
            payload = asaas.montar_checkout(plano, metodo, 1, dados, token,
                                            config.PUBLIC_URL, base=base_final)
            res = asaas.criar_checkout(payload)
            if not res.get("url"):
                raise RuntimeError("checkout sem url")
            return self._redirect(res["url"])
        except Exception as e:
            print(f"[renovar] checkout falhou: {e}", flush=True)
            expirado = not subscribers.tem_acesso(sub)
            return self._html(site_web.pagina_renovar(
                sub, plano, pricing.base_cobrada(plano, "PIX", preco, 0.0),
                pricing.base_cobrada(plano, "CARTAO", preco, 0.0),
                sub.get("proximo_vencimento"), bonus=expirado,
                erro="Não conseguimos iniciar o pagamento agora. Tente novamente em instantes."))
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `cd app && python3 -m unittest tests.test_renovar_rota -v && python3 -m unittest discover -s tests`
Expected: PASS — 4 novos + suíte verde

- [ ] **Step 5: Commit**

```bash
git add app/serve.py app/site_web.py app/tests/test_renovar_rota.py
git commit -m "feat(regua): rota /renovar com preço contratado e bônus de resgate"
```

---

### Task 7: Pix sai do mensal e confirmação por canal

**Files:**
- Modify: `app/config.py:73` — plano mensal
- Modify: `app/site_web.py` — `pagina_assinar` esconde o tile de Pix quando o plano não aceita
- Modify: `app/webhook_asaas.py` — `_confirmar_renovacao` se divide por canal
- Test: `app/tests/test_mensal_sem_pix.py`

**Interfaces:**
- Consumes: `mensagens.email_renovacao` (já existe, Projeto E)
- Produces: chave `aceita_pix` nos planos (`False` no mensal); `_confirmar_renovacao(sub,
  vencimento, automatica: bool)` — `True` manda e-mail, `False` manda WhatsApp

**Decisão de negócio:** mensal passa a ser só cartão. Cartão mensal é sempre 1× (`parcelas`
fica travado em 1 para planos com `recorrente_pix`), logo é `RECURRENT` puro e renova sozinho —
por isso o mensal sai inteiramente da régua. Confirmado pelo Diego que **não existe nenhum
assinante mensal pago via Pix**, então não há caminho de migração a implementar.

- [ ] **Step 1: Escrever o teste que falha**

Criar `app/tests/test_mensal_sem_pix.py`:

```python
"""Mensal passa a ser só cartão; confirmação de renovação vai por canal. Standalone."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestMensalSemPix(unittest.TestCase):
    def test_plano_mensal_nao_aceita_pix(self):
        import config
        mensal = config.plano_por_slug("mensal")
        self.assertFalse(mensal.get("aceita_pix", True))

    def test_plano_anual_aceita_pix(self):
        import config
        self.assertTrue(config.plano_por_slug("anual").get("aceita_pix", True))

    def test_checkout_do_mensal_nao_mostra_tile_de_pix(self):
        import site_web
        html = site_web.pagina_assinar("mensal")
        self.assertNotIn('value="PIX"', html)
        self.assertIn('value="CARTAO"', html)

    def test_checkout_do_anual_mostra_os_dois(self):
        import site_web
        html = site_web.pagina_assinar("anual")
        self.assertIn('value="PIX"', html)
        self.assertIn('value="CARTAO"', html)


class TestConfirmacaoPorCanal(unittest.TestCase):
    def setUp(self):
        import webhook_asaas, deliver, email_send
        self.w = webhook_asaas
        self.wa, self.mail = [], []
        self._ow, self._om = deliver.enviar_texto, email_send.enviar
        deliver.enviar_texto = lambda w, m: self.wa.append((w, m))
        email_send.enviar = lambda d, a, c: self.mail.append((d, a))

    def tearDown(self):
        import deliver, email_send
        deliver.enviar_texto, email_send.enviar = self._ow, self._om

    def _sub(self):
        return {"id": "s1", "nome": "Teste", "email": "t@e.com", "whatsapp": "43999990000"}

    def test_renovacao_automatica_vai_por_email(self):
        self.w._confirmar_renovacao(self._sub(), "2027-08-01", automatica=True)
        self.assertEqual(len(self.mail), 1)
        self.assertEqual(self.wa, [])

    def test_renovacao_manual_vai_por_whatsapp(self):
        self.w._confirmar_renovacao(self._sub(), "2027-08-01", automatica=False)
        self.assertEqual(len(self.wa), 1)
        self.assertEqual(self.mail, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_mensal_sem_pix -v`
Expected: FAIL — `AssertionError: True is not false` (o mensal ainda aceita Pix)

- [ ] **Step 3: Implementação mínima**

Em `app/config.py`, acrescentar **apenas** `"aceita_pix": False` ao plano mensal. Os demais
planos **não** ganham a chave: a ausência significa "aceita", que é como o teste lê
(`.get("aceita_pix", True)`). Uma chave só, no único plano que é exceção.

```python
    {"slug": "mensal", ..., "aceita_pix": False, ...},
```

Em `app/site_web.py`, `pagina_assinar`, condicionar o tile de Pix:

```python
    tile_pix = ("" if plano.get("aceita_pix") is False else
                f'<label class="paytile"><input type="radio" name="metodo" value="PIX" checked>'
                f'<span class="pt-ico">⚡</span><span class="pt-nome">Pix</span>'
                f'<span class="pt-desc">{_esc(pix_desc)}</span></label>')
```

e usar `{tile_pix}` no lugar do bloco fixo. Quando o Pix não existe, o rádio do cartão precisa
vir marcado — acrescente `checked` ao tile de cartão nesse caso.

Em `app/webhook_asaas.py`, alterar `_confirmar_renovacao` para escolher o canal:

```python
def _confirmar_renovacao(sub, vencimento, automatica=True):
    """Confirma a renovação. Canal por tipo (decisão do Diego 2026-07-25):
    - automática (cartão recorrente): e-mail, que serve de comprovante de cobrança;
    - manual (o assinante foi lá e renovou): WhatsApp, onde ele já está.
    Nunca derruba a renovação: falha aqui só vira log.
    """
    import config, mensagens, site_web
    link = f"{config.ARTIGOS_URL}/minha"
    ate = site_web._data_br(vencimento) or ""
    try:
        if automatica:
            if not sub.get("email"):
                return
            import email_send
            assunto, html = mensagens.email_renovacao(sub.get("nome", ""), link, ate)
            email_send.enviar(sub["email"], assunto, html)
        else:
            import deliver
            _, corpo = mensagens.email_renovacao(sub.get("nome", ""), link, ate)
            deliver.enviar_texto(sub.get("whatsapp"), site_web._sem_html(corpo))
    except Exception as e:
        print(f"[webhook] confirmação de renovação falhou: {e}", flush=True)
```

`site_web._sem_html` **não existe** — crie-a junto de `_data_br` (`site_web.py:1575`). O corpo
da mensagem de renovação é HTML (foi escrito para e-mail) e o WhatsApp não renderiza tags:

```python
def _sem_html(texto):
    """Texto plano a partir do corpo HTML — WhatsApp não renderiza tags."""
    import re
    t = re.sub(r"<br\s*/?>", "\n", texto or "")
    t = re.sub(r"</p>", "\n\n", t)
    return _html.unescape(re.sub(r"<[^>]+>", "", t)).strip()
```

Ajustar os chamadores: no ramo `RENOVAR` (renovação automática) passar `automatica=True`; na
recontratação do ramo `ATIVAR` e na extensão por recompra Pix, passar `automatica=False`.

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `cd app && python3 -m unittest tests.test_mensal_sem_pix tests.test_webhook tests.test_site_web tests.test_pricing -v && python3 -m unittest discover -s tests`
Expected: PASS — 6 novos + suíte inteira verde

- [ ] **Step 5: Commit**

```bash
git add app/config.py app/site_web.py app/webhook_asaas.py app/tests/test_mensal_sem_pix.py
git commit -m "feat(regua): mensal só no cartão + confirmação de renovação por canal"
```

---

### Task 8: Ligar o bônus e a extensão ao pagamento confirmado

**Files:**
- Modify: `app/webhook_asaas.py:191-194` (extensão por recompra) e o ramo de recontratação
- Test: `app/tests/test_bonus_resgate.py`

**Interfaces:**
- Consumes: `renovacao.novo_vencimento(acesso_ate, hoje, dias_ciclo, bonus_dias=0)` e
  `renovacao.CICLO_DIAS` (Task 2)
- Produces: nada para tarefas seguintes

**Por que esta tarefa existe:** a Task 2 cria `novo_vencimento` com a regra do bônus, mas nada
no webhook a chama — hoje a extensão usa `_proximo_venc`, que sempre conta a partir da data do
pagamento e não conhece bônus nenhum. Sem esta tarefa, **o +1 mês de resgate nunca é concedido**
e a recompra adiantada perde os dias restantes.

**Regra:** os dois caminhos de renovação passam a usar `novo_vencimento(..., bonus_dias=30)`.
A própria função decide: acesso ainda vigente → estende a partir do fim atual, **sem** bônus;
acesso expirado → conta de hoje **com** os 30 dias. A primeira compra (assinante que não
existia) **não** muda — continua no `_proximo_venc`.

- [ ] **Step 1: Escrever o teste que falha**

Criar `app/tests/test_bonus_resgate.py`:

```python
"""O +1 mês de resgate e a extensão a partir do fim atual, no webhook. Standalone."""
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestBonusResgate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "subscribers", "webhook_asaas"):
            sys.modules.pop(m, None)
        import db, subscribers, webhook_asaas
        db._INITED = False
        db.init()
        self.db, self.subs, self.w = db, subscribers, webhook_asaas

    def _assinante(self, acesso_ate):
        reg = self.subs.criar_de_pagamento(
            {"nome": "T", "whatsapp": "43999990000", "email": "t@e.com", "plano": "anual",
             "cpf": "12345678909"},
            {"payment": "pay_1", "proximo_vencimento": acesso_ate})
        self.subs.marcar_status(reg["id"], "ATIVO", acesso_ate=acesso_ate)
        return reg

    def _pagar(self, valor=1099.0):
        """Pagamento Pix avulso (sem subscription, sem installment) do mesmo CPF."""
        return {"id": "pay_2", "value": valor, "customer": "cus_1",
                "cpfCnpj": "12345678909", "dueDate": date.today().isoformat()}

    def test_recompra_com_acesso_vigente_estende_do_fim_atual_sem_bonus(self):
        fim = (date.today() + timedelta(days=15)).isoformat()
        reg = self._assinante(fim)
        self.w._executar("PAYMENT_CONFIRMED", self._pagar(), "pay_2", lambda w, m: None)
        atual = [s for s in self.subs.listar() if s["id"] == reg["id"]][0]
        esperado = (date.today() + timedelta(days=15 + 365)).isoformat()
        self.assertTrue(atual["acesso_ate"].startswith(esperado))

    def test_recompra_apos_vencer_conta_de_hoje_com_bonus(self):
        fim = (date.today() - timedelta(days=5)).isoformat()
        reg = self._assinante(fim)
        self.w._executar("PAYMENT_CONFIRMED", self._pagar(), "pay_2", lambda w, m: None)
        atual = [s for s in self.subs.listar() if s["id"] == reg["id"]][0]
        esperado = (date.today() + timedelta(days=365 + 30)).isoformat()
        self.assertTrue(atual["acesso_ate"].startswith(esperado))

    def test_primeira_compra_nao_ganha_bonus(self):
        # ninguém existe ainda -> caminho normal de ATIVAR, sem bônus
        self.w._executar("PAYMENT_CONFIRMED", self._pagar(), "pay_2", lambda w, m: None)
        novo = self.subs.listar()[0]
        esperado = (date.today() + timedelta(days=365)).isoformat()
        self.assertTrue(novo["acesso_ate"].startswith(esperado))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_bonus_resgate -v`
Expected: FAIL — a data de acesso não inclui o bônus nem parte do fim atual

- [ ] **Step 3: Implementação mínima**

Em `app/webhook_asaas.py`, no ramo de **extensão por recompra** (hoje em ~191-194) e no de
**recontratação**, trocar o cálculo por:

```python
        import renovacao
        from datetime import date as _date
        dias_ciclo = renovacao.CICLO_DIAS.get(plano.get("cycle", "MONTHLY"), 30)
        # bonus_dias=30 sempre: a própria função só aplica quando o acesso JÁ expirou
        # (renovar em dia não ganha nada; renovar depois de vencer ganha o mês de resgate).
        novo_fim = renovacao.novo_vencimento(sub.get("acesso_ate"), _date.today(),
                                             dias_ciclo, bonus_dias=30).isoformat()
        subscribers.marcar_status(sub["id"], "ATIVO",
                                  acesso_ate=novo_fim, proximo_vencimento=novo_fim)
```

Não altere o cálculo da **primeira compra** (assinante inexistente): ele segue usando
`_proximo_venc`, sem bônus.

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `cd app && python3 -m unittest tests.test_bonus_resgate tests.test_webhook -v && python3 -m unittest discover -s tests`
Expected: PASS — 3 novos + suíte inteira verde

- [ ] **Step 5: Commit**

```bash
git add app/webhook_asaas.py app/tests/test_bonus_resgate.py
git commit -m "feat(regua): aplica o bônus de resgate e estende a partir do fim atual"
```

---

## Antes de publicar

- [ ] Suíte inteira verde: `cd app && python3 -m unittest discover -s tests`
- [ ] Abrir `/admin/mensagens` e conferir que as seis automações aparecem, editam e removem
- [ ] Abrir `/renovar` com um assinante de teste: preço correto, sem campo de cupom, bônus só
      aparecendo se o acesso já expirou
- [ ] Conferir no `/assinar?plano=mensal` que o Pix sumiu e o cartão vem marcado
- [ ] Revisar os seis textos padrão da régua — eles vão para o WhatsApp de médicos, e é o
      canal mais sensível do produto
- [ ] Deploy: `git push origin main` + `services.app.deployService` no EasyPanel
