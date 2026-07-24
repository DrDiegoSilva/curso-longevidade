# Horário de envio por assinante — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O assinante escolhe em qual horário (slot) recebe o estudo do dia; o envio passa a rodar por slot, espalhando o burst (anti-ban) com teto por slot.

**Architecture:** Slots fixos (07/08/12/18/20). `subscribers.slot_envio` guarda a escolha (default 08h). O `agendador` dispara `daily.enviar_slot(slot)` em cada horário; `enviar_slot` manda o MESMO estudo do dia só pros assinantes daquele slot, com idempotência por (dia, slot) via tabela `envios_slot`. A finalização do dia (status SENT, digest, fila) e o áudio/PDF mestre acontecem 1x/dia (guardados por marcadores na mesma tabela). O `/meus-dados` ganha o seletor de horário (só slots com vaga).

**Tech Stack:** Python 3 stdlib (http.server, sqlite3/psycopg2), unittest. Sem dependências novas.

## Global Constraints

- **Sem dependências novas** — só stdlib + o que o repo já usa.
- **Testes:** unittest. Rodar tudo: `cd app && python3 -m unittest discover -s tests`. Testes em `app/tests/` com `sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))` e banco temp via `DSCURSO_ARTIGOS_DB`.
- **Slots:** `config.SLOTS = ["07h","08h","12h","18h","20h"]`, `config.SLOT_HORA` (mapa hora int), `config.SLOT_DEFAULT = "08h"`, `config.SLOT_TETO_DEFAULT = 100`. Teto real vem de `db.get_config("slot_teto", str(config.SLOT_TETO_DEFAULT))`.
- **Default:** `slot_envio` NULL/vazio conta e recebe como **"08h"** (preserva os atuais).
- **Um estudo/dia:** todos os slots enviam o mesmo estudo; áudio/PDF/finalização são 1x/dia.
- **Idempotência por (dia, slot)** via `envios_slot`; marcadores sintéticos `_skip_aviso` e `_finalizado` (mesma tabela) garantem aviso e finalização 1x/dia.
- **`pode_enviar`** do draft_store é `status not in ("SKIPPED","SENT")`. Per-slot NÃO usa isso — usa "existe rascunho E status != SKIPPED" (o SENT não pode bloquear os outros slots; a idempotência é o `envios_slot`).
- **Anti-ban:** `config.SEND_DELAY_SEC` (4s) entre mensagens, preservado.
- **Commits:** `feat(horario): ...` / `test(horario): ...`. Branch `horario-envio`. Sem `Co-Authored-By`.

---

### Task 1: config SLOTS + coluna `subscribers.slot_envio` + `definir_slot`/`slot_de`

**Files:**
- Modify: `app/config.py` (constantes de slot)
- Modify: `app/db.py` (coluna na CREATE TABLE subscribers + `_migrar_colunas`)
- Modify: `app/subscribers.py` (`_COLS` + `definir_slot` + `slot_de`)
- Test: `app/tests/test_horario.py` (criar)

**Interfaces:**
- Produces:
  - `config.SLOTS`, `config.SLOT_HORA`, `config.SLOT_DEFAULT`, `config.SLOT_TETO_DEFAULT`
  - `subscribers.slot_de(sub: dict) -> str` (NULL/vazio/inválido → SLOT_DEFAULT)
  - `subscribers.definir_slot(id, slot) -> None` (grava só se slot ∈ SLOTS)
  - Coluna `subscribers.slot_envio TEXT`

- [ ] **Step 1: Write the failing test**

Criar `app/tests/test_horario.py`:

```python
"""Testes do horário de envio por assinante (slots). Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestSlotBasico(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        for m in ("config", "db", "subscribers"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, subscribers
        importlib.reload(config); importlib.reload(db); importlib.reload(subscribers)
        self.cfg, self.db, self.s = config, db, subscribers
        self.s._migrado = False
        db.init()

    def test_slot_de_default(self):
        self.assertEqual(self.s.slot_de({}), self.cfg.SLOT_DEFAULT)
        self.assertEqual(self.s.slot_de({"slot_envio": None}), self.cfg.SLOT_DEFAULT)
        self.assertEqual(self.s.slot_de({"slot_envio": "xx"}), self.cfg.SLOT_DEFAULT)  # inválido
        self.assertEqual(self.s.slot_de({"slot_envio": "12h"}), "12h")

    def test_definir_slot(self):
        reg = self.s.adicionar("Fulano", "5543999990000")
        self.s.definir_slot(reg["id"], "18h")
        self.assertEqual(self.s.por_id(reg["id"])["slot_envio"], "18h")
        self.s.definir_slot(reg["id"], "zz")   # inválido -> não muda
        self.assertEqual(self.s.por_id(reg["id"])["slot_envio"], "18h")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd app && python3 -m unittest tests.test_horario -v`
Expected: FAIL — `AttributeError: module 'subscribers' has no attribute 'slot_de'`

- [ ] **Step 3: Implement**

Em `app/config.py`, adicionar (perto de `FOUNDER_LIMITE`):

```python
# Horário de envio por assinante (slots). Assinante escolhe 1 no /meus-dados; NULL/vazio => SLOT_DEFAULT.
SLOTS = ["07h", "08h", "12h", "18h", "20h"]
SLOT_HORA = {"07h": 7, "08h": 8, "12h": 12, "18h": 18, "20h": 20}
SLOT_DEFAULT = "08h"
SLOT_TETO_DEFAULT = 100
```

Em `app/db.py`, na CREATE TABLE `subscribers`, adicionar a coluna `slot_envio TEXT` (na última linha de colunas):

```sql
                senha_hash TEXT, curador INTEGER DEFAULT 0, slot_envio TEXT
```

Em `_migrar_colunas` (pro Postgres de produção):

```python
        _add_coluna(c, "subscribers", "slot_envio", "TEXT")
```

Em `app/subscribers.py`, adicionar `"slot_envio"` ao final de `_COLS`:

```python
         "criado_em", "cancelado_em", "cancel_motivo", "oferta_retencao_em", "senha_hash", "slot_envio"]
```

E as funções (perto de `definir_curador`):

```python
def slot_de(sub):
    """Slot do assinante (config.SLOTS). NULL/vazio/inválido -> config.SLOT_DEFAULT."""
    s = (sub or {}).get("slot_envio")
    return s if s in config.SLOTS else config.SLOT_DEFAULT


def definir_slot(id, slot):
    """Grava o slot de envio (só se ∈ config.SLOTS). Fora de _COLS de propósito não é —
    slot_envio ESTÁ em _COLS, mas o upsert de pagamento não manda slot, então preserva."""
    if slot not in config.SLOTS:
        return
    _ensure()
    with db._conn() as c:
        c.execute("UPDATE subscribers SET slot_envio=? WHERE id=?", (slot, id))
```

Nota: `slot_envio` entra em `_COLS`, mas `criar_de_pagamento`/`adicionar` não passam `slot_envio` (fica NULL → default). O `definir_slot` usa UPDATE direto (não upsert), então não zera outros campos.

- [ ] **Step 4: Run to verify it passes**

Run: `cd app && python3 -m unittest tests.test_horario -v`
Expected: PASS (2 testes)

- [ ] **Step 5: Commit**

```bash
git add app/config.py app/db.py app/subscribers.py app/tests/test_horario.py
git commit -m "feat(horario): slots (config) + coluna subscribers.slot_envio + slot_de/definir_slot"
```

---

### Task 2: `subscribers.contar_por_slot` + `slots_com_vaga`

**Files:**
- Modify: `app/subscribers.py`
- Test: `app/tests/test_horario.py`

**Interfaces:**
- Consumes: `subscribers.ativos()`, `subscribers.slot_de` (Task 1)
- Produces:
  - `subscribers.contar_por_slot() -> dict[str,int]` (só ATIVOS; NULL conta como SLOT_DEFAULT; chaves = config.SLOTS)
  - `subscribers.slots_com_vaga(teto, slot_atual=None) -> list[str]` (slots com count < teto, na ordem de SLOTS, sempre incluindo slot_atual)

- [ ] **Step 1: Write the failing test**

Adicionar em `app/tests/test_horario.py`:

```python
class TestVaga(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        for m in ("config", "db", "subscribers"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, subscribers
        importlib.reload(config); importlib.reload(db); importlib.reload(subscribers)
        self.cfg, self.db, self.s = config, db, subscribers
        self.s._migrado = False
        db.init()

    def test_contar_por_slot_default(self):
        a = self.s.adicionar("A", "5543000000001")   # sem slot -> 08h
        self.s.definir_slot(self.s.adicionar("B", "5543000000002")["id"], "12h")
        cont = self.s.contar_por_slot()
        self.assertEqual(cont["08h"], 1)
        self.assertEqual(cont["12h"], 1)
        self.assertEqual(cont["20h"], 0)

    def test_slots_com_vaga_esconde_cheio_mas_mantem_atual(self):
        for i in range(3):
            self.s.definir_slot(self.s.adicionar(f"C{i}", f"554300001000{i}")["id"], "07h")
        vaga = self.s.slots_com_vaga(teto=3)          # 07h cheio (3/3)
        self.assertNotIn("07h", vaga)
        self.assertIn("08h", vaga)
        # mesmo cheio, o slot_atual do assinante é ofertado (pra ele manter)
        vaga2 = self.s.slots_com_vaga(teto=3, slot_atual="07h")
        self.assertIn("07h", vaga2)
        self.assertEqual(vaga2, [s for s in self.cfg.SLOTS if s in vaga2])  # ordem preservada
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd app && python3 -m unittest tests.test_horario.TestVaga -v`
Expected: FAIL — `AttributeError: ... 'contar_por_slot'`

- [ ] **Step 3: Implement**

Adicionar em `app/subscribers.py`:

```python
def contar_por_slot():
    """Quantos assinantes ATIVOS em cada slot (config.SLOTS). NULL/vazio conta como default."""
    cont = {s: 0 for s in config.SLOTS}
    for s in ativos():
        cont[slot_de(s)] = cont.get(slot_de(s), 0) + 1
    return cont


def slots_com_vaga(teto, slot_atual=None):
    """Slots (na ordem de config.SLOTS) com count < teto. O slot_atual é sempre incluído
    (pra o assinante poder manter o horário mesmo se lotou depois)."""
    cont = contar_por_slot()
    return [s for s in config.SLOTS if cont.get(s, 0) < int(teto) or s == slot_atual]
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd app && python3 -m unittest tests.test_horario -v`
Expected: PASS (4 testes)

- [ ] **Step 5: Commit**

```bash
git add app/subscribers.py app/tests/test_horario.py
git commit -m "feat(horario): contar_por_slot + slots_com_vaga (esconde cheio, mantém o atual)"
```

---

### Task 3: `db.envios_slot` + `registrar_envio_slot` (idempotência)

**Files:**
- Modify: `app/db.py` (tabela + `_TABELAS` + função)
- Test: `app/tests/test_horario.py`

**Interfaces:**
- Produces: `db.registrar_envio_slot(data, slot) -> bool` (True na 1ª vez p/ o par; False se já registrado)
- Tabela `envios_slot(data, slot, enviado_em, PRIMARY KEY(data,slot))`

- [ ] **Step 1: Write the failing test**

Adicionar em `app/tests/test_horario.py` (dentro de `TestSlotBasico`):

```python
    def test_registrar_envio_slot_idempotente(self):
        self.assertTrue(self.db.registrar_envio_slot("2026-07-24", "08h"))    # 1ª vez
        self.assertFalse(self.db.registrar_envio_slot("2026-07-24", "08h"))   # repetido
        self.assertTrue(self.db.registrar_envio_slot("2026-07-24", "12h"))    # outro slot
        self.assertTrue(self.db.registrar_envio_slot("2026-07-25", "08h"))    # outro dia
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd app && python3 -m unittest tests.test_horario.TestSlotBasico.test_registrar_envio_slot_idempotente -v`
Expected: FAIL — `AttributeError: ... 'registrar_envio_slot'`

- [ ] **Step 3: Implement**

Em `app/db.py`, na CREATE TABLE (após `settings`):

```sql
            CREATE TABLE IF NOT EXISTS envios_slot (
                data TEXT, slot TEXT, enviado_em TEXT,
                PRIMARY KEY (data, slot)
            );
```

Em `_TABELAS`, acrescentar `"envios_slot"`:

```python
            "afiliados", "comissoes", "settings", "envios_slot"]
```

Adicionar a função (perto de `registrar_webhook`):

```python
def registrar_envio_slot(data, slot):
    """True se é a 1ª vez que (data,slot) é registrado hoje; False se já registrado.
    Guarda idempotência do envio por slot (restart não reenvia)."""
    from datetime import datetime
    with _conn() as c:
        cur = c.execute("INSERT INTO envios_slot (data,slot,enviado_em) VALUES (?,?,?) "
                        "ON CONFLICT (data,slot) DO NOTHING",
                        (data or "", slot or "", datetime.now().isoformat()))
        return cur.rowcount > 0
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd app && python3 -m unittest tests.test_horario -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/db.py app/tests/test_horario.py
git commit -m "feat(horario): tabela envios_slot + registrar_envio_slot (idempotência por dia/slot)"
```

---

### Task 4: `daily.enviar_slot` (refatora `enviar_08h`) + finalização 1x/dia + `rotina_08h`

**Files:**
- Modify: `app/daily.py` (`enviar_08h` → `enviar_slot`; helpers `_audio_master`/`_pdf_master`/`_finalizar_dia`; `rotina_08h`)
- Test: `app/tests/test_horario.py`

**Interfaces:**
- Consumes: `subscribers.slot_de`/`ativos` (Task 1), `db.registrar_envio_slot` (Task 3), `config.SEND_DELAY_SEC`, `draft_store`, `deliver.distribuir`
- Produces:
  - `daily.enviar_slot(slot)` — envia o estudo do dia só pros do slot; idempotente; finaliza o dia 1x
  - `rotina_08h()` passa a chamar `enviar_slot("08h")`

- [ ] **Step 1: Write the failing test**

Adicionar em `app/tests/test_horario.py` uma classe que mocka o envio pesado:

```python
class TestEnviarSlot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        for m in ("config", "db", "subscribers", "draft_store", "daily"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, subscribers, draft_store, daily
        for mod in (config, db, subscribers, draft_store, daily):
            importlib.reload(mod)
        self.cfg, self.db, self.s, self.ds, self.daily = config, db, subscribers, draft_store, daily
        self.s._migrado = False
        db.init()
        # rascunho aprovado de hoje
        hoje = self.daily._hoje_iso()
        r = self.ds.novo_rascunho(hoje, {"tema": "Obesidade", "titulo": "T", "doi": "10.1/x"}, "resumo", None)
        r["status"] = "APPROVED"; self.ds.salvar(r)
        # captura destinatários (mocka o envio pesado)
        self.enviados = []
        self.daily.deliver.distribuir = lambda r, subs, delay, fn: (
            self.enviados.extend(subs) or {"ok": len(subs), "falhas": []})
        self.daily.deliver.enviar_curador = lambda msg: None
        self.daily._audio_master = lambda *a, **k: None
        self.daily._pdf_master = lambda *a, **k: None
        self.daily._e_dia_util = lambda dt: True
        # 2 assinantes: um no 12h, um no default (08h)
        self.s.definir_slot(self.s.adicionar("A", "5543000000001")["id"], "12h")
        self.s.adicionar("B", "5543000000002")   # 08h default

    def test_envia_so_do_slot(self):
        self.daily.enviar_slot("12h")
        self.assertEqual(len(self.enviados), 1)
        self.assertEqual(self.s.slot_de(self.enviados[0]), "12h")

    def test_idempotente_por_slot(self):
        self.daily.enviar_slot("12h")
        self.enviados.clear()
        self.daily.enviar_slot("12h")             # 2ª vez no mesmo dia/slot
        self.assertEqual(self.enviados, [])       # não reenvia

    def test_default_recebe_no_08h(self):
        self.daily.enviar_slot("08h")
        self.assertEqual(len(self.enviados), 1)
        self.assertEqual(self.enviados[0]["nome"], "B")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd app && python3 -m unittest tests.test_horario.TestEnviarSlot -v`
Expected: FAIL — `AttributeError: module 'daily' has no attribute 'enviar_slot'`

- [ ] **Step 3: Implement**

Em `app/daily.py`, substituir a função `enviar_08h` por `enviar_slot` + helpers. Novo código (mantém a lógica de conteúdo/áudio/PDF/_envia de hoje, mas filtra por slot, com idempotência e finalização 1x/dia):

```python
def _audio_master(hoje, art, conteudo):
    """Áudio do dia (o MESMO p/ todos). Gera 1x e cacheia em arquivo; regenera se sumir."""
    if not config.audio_ligado():
        return None
    caminho = os.path.join(config.drafts_dir(), f"{hoje}-master.mp3")
    if os.path.exists(caminho):
        try:
            return open(caminho, "rb").read()
        except Exception:
            pass
    try:
        import audio as audiomod
        b = audiomod.gerar_audio_do_estudo(art, conteudo)
        try:
            os.makedirs(config.drafts_dir(), exist_ok=True)
            open(caminho, "wb").write(b)
        except Exception:
            pass
        return b
    except Exception as e:
        print(f"[enviar] áudio falhou (segue sem): {e}", flush=True)
        return None


def _pdf_master(hoje, art, conteudo, tmeta):
    """PDF único do dia (marca do curso, sem nome). Gera 1x em arquivo; reusa se existir."""
    caminho = os.path.join(config.drafts_dir(), f"{hoje}-master.pdf")
    if os.path.exists(caminho):
        return caminho
    try:
        os.makedirs(config.drafts_dir(), exist_ok=True)
        pdfmod.gerar_pdf(pdfmod.montar_html(art, conteudo, tmeta), caminho)
        return caminho
    except Exception as e:
        print(f"[enviar] PDF mestre falhou (segue sem PDF): {e}", flush=True)
        return None


def _finalizar_dia(hoje, r, art, conteudo, tmeta):
    """Fecha o dia UMA vez (1º slot que enviar): status SENT, confirma fila, registra no
    arquivo, tira da reserva, marca DOI. Guardado por marcador em envios_slot."""
    import db
    if not db.registrar_envio_slot(hoje, "_finalizado"):
        return
    import resumo_diario as rd
    r["status"] = "SENT"
    draft_store.salvar(r)
    queue_store.confirmar_envio(art)
    try:
        db.registrar_digest(art, conteudo, tmeta, data=hoje)
    except Exception as e:
        print(f"[enviar] falha ao registrar no arquivo: {e}", flush=True)
    if r.get("reserva_id"):
        try:
            db.marcar_reserva_enviado(r["reserva_id"])
        except Exception as e:
            print(f"[enviar] marcar reserva enviado falhou: {e}", flush=True)
    rd.registrar([art["doi"]] if art.get("doi") else [])


def enviar_slot(slot):
    """Envia o estudo do dia SÓ pros assinantes de `slot` (config.SLOTS). Idempotente por
    (dia, slot). Áudio/PDF/finalização são 1x/dia. O SENT não bloqueia os outros slots —
    o guard de reenvio é o envios_slot."""
    import db
    hoje = _hoje_iso()
    if not db.registrar_envio_slot(hoje, slot):     # slot já processado hoje -> não repete
        return
    if not _e_dia_util(datetime.now()):
        return                                       # silencioso (sem spam por slot)
    r = draft_store.carregar(hoje)
    if not r or r.get("status") == "SKIPPED":        # sem rascunho ou vetado
        if db.registrar_envio_slot(hoje, "_skip_aviso"):   # avisa o curador 1x/dia
            deliver.enviar_curador(f"⏭️ Nada enviado hoje ({'sem rascunho' if not r else 'vetado'}).")
        return
    art = r["artigo"]
    titulo = r.get("titulo_pt") or art.get("titulo", "")
    conteudo = {"titulo_pt": titulo, "resumo": r["resumo"], "gancho": r.get("gancho", ""), "grafico": r.get("grafico")}
    tmeta = _tema_meta(art.get("tema", ""))
    audio_bytes = _audio_master(hoje, art, conteudo)
    master_pdf = _pdf_master(hoje, art, conteudo, tmeta)

    def _envia(whatsapp, nome):
        import phone
        whatsapp = phone.normalizar(whatsapp)
        link = f"{config.PUBLIC_URL}/entrar"
        msg = deliver.personalizar_rodape(montar_texto_resumo(titulo, r['resumo'], tmeta), nome, link)
        deliver.enviar_texto(whatsapp, msg)
        if master_pdf:
            try:
                deliver.enviar_pdf(whatsapp, master_pdf, caption=titulo)
            except Exception as e:
                print(f"[enviar] PDF p/ {whatsapp} falhou: {e}", flush=True)
        if audio_bytes:
            try:
                deliver.enviar_audio(whatsapp, audio_bytes)
            except Exception as e:
                print(f"[enviar] áudio p/ {whatsapp} falhou: {e}", flush=True)

    destinatarios = [s for s in subscribers.ativos() if subscribers.slot_de(s) == slot]
    res = deliver.distribuir(r, destinatarios, config.SEND_DELAY_SEC, _envia)
    _finalizar_dia(hoje, r, art, conteudo, tmeta)
    deliver.enviar_curador(f"✅ Enviado (slot {slot}, {art.get('tema','')}): {res['ok']} assinantes"
                           + (f" · {len(res['falhas'])} falhas" if res["falhas"] else "")
                           + (" · ⚠️ SEM PDF (erro na geração)" if master_pdf is None else ""))
```

E `rotina_08h` passa a chamar `enviar_slot("08h")`:

```python
def rotina_08h():
    """Tarefa das 08h: avisa pré-renovação (todo dia) + envia o slot das 08h."""
    try:
        import billing_notices
        n = billing_notices.avisar_pre_renovacao()
        if n:
            print(f"[pre-renovacao] {n} aviso(s) enviado(s)", flush=True)
    except Exception as e:
        print(f"[pre-renovacao] erro: {e}", flush=True)
    enviar_slot("08h")
```

(Remover a antiga `enviar_08h`. Conferir que nada mais a chama: `grep -rn "enviar_08h" app` deve sobrar só em comentários/docstrings — se houver chamada em teste, ajustar pro `enviar_slot`.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd app && python3 -m unittest tests.test_horario -v`
Expected: PASS (todas as classes)

Depois: `cd app && grep -rn "enviar_08h" --include=*.py .` — se algum teste/arquivo ainda chama `enviar_08h`, trocar por `enviar_slot("08h")` (ou `rotina_08h`) e re-rodar.

- [ ] **Step 5: Run the FULL suite**

Run: `cd app && python3 -m unittest discover -s tests`
Expected: OK (0 falhas).

- [ ] **Step 6: Commit**

```bash
git add app/daily.py app/tests/test_horario.py
git commit -m "feat(horario): enviar_slot (filtra por slot, idempotente, finaliza 1x/dia) + rotina_08h usa enviar_slot('08h')"
```

---

### Task 5: `agendador` dispara por slot

**Files:**
- Modify: `app/serve.py` (`agendador`)

**Interfaces:**
- Consumes: `config.SLOTS`/`SLOT_HORA` (Task 1), `daily.enviar_slot`/`rotina_08h`/`preparar_18h` (Task 4)
- Produces: o agendador dispara `enviar_slot` em cada horário de slot; 08h = `rotina_08h`; 18h = `preparar_18h()` + `enviar_slot("18h")`.

- [ ] **Step 1: (glue de scheduler — verificação por suíte + smoke)**

Sem teste unitário do loop do agendador (é I/O/tempo). Verificação: a suíte continua verde + `python3 -c "import serve"`. A lógica de envio já é testada na Task 4.

- [ ] **Step 2: (n/a)**

- [ ] **Step 3: Implement**

Em `app/serve.py`, substituir a função `agendador`:

```python
def agendador():
    """Dispara o envio em CADA slot (config.SLOTS) + prepara às 18h. Fuso TZ.
    08h: pré-renovação + envio do slot 08h. 18h: prepara amanhã + envia o slot 18h."""
    import daily, config
    def _prep_e_18h():
        daily.preparar_18h()
        daily.enviar_slot("18h")
    tarefas = {"rotina08": daily.rotina_08h, "prep18": _prep_e_18h}
    for s in config.SLOTS:
        if s not in ("08h", "18h"):
            tarefas[f"slot:{s}"] = (lambda sl=s: daily.enviar_slot(sl))
    # (hora, nome) — 08h e 18h têm tarefas especiais; os demais slots enviam direto.
    horarios = []
    for s in config.SLOTS:
        h = config.SLOT_HORA[s]
        if s == "08h":
            horarios.append((h, "rotina08"))
        elif s == "18h":
            horarios.append((h, "prep18"))
        else:
            horarios.append((h, f"slot:{s}"))
    while True:
        now = _now().replace(tzinfo=None)
        alvo, nome = proximo_disparo(now, horarios)
        espera = max(60, (alvo - now).total_seconds())
        print(f"[agendador] próximo: {nome} {alvo:%Y-%m-%d %H:%M} (em {int(espera)}s)", flush=True)
        time.sleep(espera)
        try:
            print(f"[agendador] rodando {nome} {_now():%Y-%m-%d %H:%M}", flush=True)
            tarefas[nome]()
        except Exception as e:
            print(f"[agendador] {nome} erro: {e}", flush=True)
```

- [ ] **Step 4: Verify**

Run: `cd app && python3 -c "import serve" && python3 -m unittest discover -s tests`
Expected: import OK + suíte OK.

- [ ] **Step 5: Commit**

```bash
git add app/serve.py
git commit -m "feat(horario): agendador dispara enviar_slot por horário (18h = preparar + enviar slot 18h)"
```

---

### Task 6: seletor de horário no `/meus-dados`

**Files:**
- Modify: `app/site_web.py` (`pagina_meus_dados` — bloco do horário)
- Modify: `app/serve.py` (POST `/meus-dados` `acao=salvar_horario`)
- Test: `app/tests/test_horario.py` (render)

**Interfaces:**
- Consumes: `subscribers.slot_de`/`slots_com_vaga`/`definir_slot` (Tasks 1-2), `db.get_config("slot_teto", ...)`
- Produces: `pagina_meus_dados` mostra o seletor de horário (só slots com vaga + o atual); POST salva.

- [ ] **Step 1: Write the failing test**

Adicionar em `app/tests/test_horario.py`:

```python
class TestMeusDadosHorario(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("DSCURSO_DATA", tempfile.mkdtemp())
        import site_web
        importlib.reload(site_web)
        self.sw = site_web

    def test_seletor_horario_render(self):
        sub = {"nome": "A", "email": "a@x.com", "whatsapp": "5543", "slot_envio": "12h"}
        h = self.sw.pagina_meus_dados(sub, slots=["07h", "08h", "12h"], slot_atual="12h")
        self.assertIn("salvar_horario", h)
        self.assertIn('value="12h"', h)
        self.assertIn("07h", h)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd app && python3 -m unittest tests.test_horario.TestMeusDadosHorario -v`
Expected: FAIL — `pagina_meus_dados() got an unexpected keyword argument 'slots'`

- [ ] **Step 3: Implement**

Em `app/site_web.py`, mudar a assinatura de `pagina_meus_dados` p/ aceitar `slots`/`slot_atual` e renderizar o bloco. Nova assinatura:

```python
def pagina_meus_dados(sub, msg="", etapa_troca=None, novo_num="", slots=None, slot_atual=None):
```

E adicionar, no `corpo` (antes do `<hr>` do cancelar), o bloco do horário:

```python
    slots = slots if slots is not None else []
    slot_atual = slot_atual or ""
    opts_slot = "".join(
        f'<option value="{_esc(s)}"{" selected" if s == slot_atual else ""}>{_esc(s[:2])}h — {_esc(s)}</option>'
        for s in slots) or '<option>—</option>'
    horario_html = (
        '<h3 class="disp" style="font-size:22px;color:var(--ouro2);margin:26px 0 6px">Horário de recebimento</h3>'
        '<p class="hint" style="margin-top:0">Escolha quando receber o estudo do dia no WhatsApp.</p>'
        '<form method="post" action="/meus-dados" style="margin-bottom:8px">'
        '<input type="hidden" name="acao" value="salvar_horario">'
        f'<select name="slot">{opts_slot}</select>'
        '<button class="actbtn" type="submit" style="margin-left:8px">Salvar horário</button>'
        '</form>')
```

Interpolar `{horario_html}` no `corpo` logo antes do `<hr ...>`:

```python
      {troca}
      {horario_html}
      <hr style="border:none;border-top:1px solid rgba(233,225,198,.12);margin:30px 0 16px">
```

Corrigir o rótulo do option (o `s[:2]h — s` fica redundante); usar só o slot:

```python
        f'<option value="{_esc(s)}"{" selected" if s == slot_atual else ""}>{_esc(s)}</option>'
```

Em `app/serve.py`, no GET `/meus-dados`, passar os slots com vaga:

```python
        if path == "/meus-dados":
            sub = self._sub_logado()
            if not sub:
                return self._redirect("/entrar")
            import subscribers as _subs, db as _db, config as _cfg
            atual = _subs.slot_de(sub)
            teto = int(_db.get_config("slot_teto", str(_cfg.SLOT_TETO_DEFAULT)) or _cfg.SLOT_TETO_DEFAULT)
            return self._html(site_web.pagina_meus_dados(
                sub, slots=_subs.slots_com_vaga(teto, atual), slot_atual=atual))
```

No POST `/meus-dados`, adicionar o tratamento de `salvar_horario`. Localizar o handler POST de `/meus-dados` (procurar `acao == "salvar_contato"`) e adicionar um ramo:

```python
            elif acao == "salvar_horario":
                import subscribers as _subs, db as _db, config as _cfg
                novo = g("slot")
                atual = _subs.slot_de(sub)
                teto = int(_db.get_config("slot_teto", str(_cfg.SLOT_TETO_DEFAULT)) or _cfg.SLOT_TETO_DEFAULT)
                if novo == atual:
                    pass
                elif novo in _subs.slots_com_vaga(teto):     # tem vaga (exclui o atual, mas mudança é p/ outro)
                    _subs.definir_slot(sub["id"], novo)
                # se lotou no meio, cai fora silenciosamente (o render seguinte mostra o estado real)
```

(Ajustar ao shape real do handler POST `/meus-dados` — ele já resolve `sub` e `acao`; seguir o mesmo padrão dos ramos `salvar_contato`/`iniciar_troca`. Reusar o `sub` e o redirect/render que os irmãos usam.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd app && python3 -m unittest tests.test_horario -v`
Expected: PASS

- [ ] **Step 5: Run the FULL suite + import**

Run: `cd app && python3 -c "import serve" && python3 -m unittest discover -s tests`
Expected: import OK + OK.

- [ ] **Step 6: Commit**

```bash
git add app/site_web.py app/serve.py app/tests/test_horario.py
git commit -m "feat(horario): seletor de horário no /meus-dados (só slots com vaga) + POST salvar_horario"
```

---

## Verificação final (smoke, produção)

1. `/meus-dados` (logado) → aparece "Horário de recebimento" com os slots disponíveis; trocar p/ 12h → Salvar → recarrega marcando 12h.
2. Admin/log: no horário de um slot, o `agendador` roda `enviar_slot(<slot>)` e o curador recebe "✅ Enviado (slot X): N".
3. Restart do container no meio do dia não reenvia um slot já disparado (idempotência `envios_slot`).
4. Assinantes atuais (sem `slot_envio`) continuam recebendo às 08h.

## Self-Review (feito)

- **Cobertura da spec:** slots/config (T1) ✅ · slot_envio + default (T1) ✅ · contagem/vaga (T2) ✅ · idempotência (T3) ✅ · envio por slot + finaliza 1x + áudio/PDF cache (T4) ✅ · agendador por slot + 18h duplo (T5) ✅ · /meus-dados seletor (T6) ✅ · anti-ban SEND_DELAY_SEC (T4, preservado) ✅ · migração default 08h (T1) ✅.
- **Placeholders:** nenhum — todo passo tem código/comando. (T5/T6 têm ramos glue verificados por suíte+smoke, padrão do repo; T6 pede ajuste ao shape real do POST /meus-dados, com o padrão dos irmãos citado.)
- **Consistência de tipos:** `slot_de(sub)->str`, `slots_com_vaga(teto,slot_atual)->list`, `contar_por_slot()->dict`, `registrar_envio_slot(data,slot)->bool`, `enviar_slot(slot)`, `pagina_meus_dados(...,slots,slot_atual)` — mesmas assinaturas entre tasks. `pode_enviar` NÃO é usado no per-slot (usa status!=SKIPPED), conforme constraint.
