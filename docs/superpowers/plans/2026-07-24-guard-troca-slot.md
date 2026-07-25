# Guard da troca de slot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Garantir exatamente 1 envio do estudo por assinante por dia, mesmo que ele troque de horário no meio do dia (mata os bugs de envio 2x e 0x).

**Architecture:** Um ledger por-assinante-por-dia (`envios_dia`) vira a fonte da verdade de "já recebeu hoje". O `enviar_slot` passa a fazer um *claim* atômico por assinante (mata 2x). Na troca de horário, se o novo slot já disparou hoje e o assinante ainda não recebeu, o `salvar_horario` dispara um catch-up de 1 destinatário (mata 0x).

**Tech Stack:** Python 3 (stdlib), SQLite/Postgres via `db._conn()`, unittest. Sem dependências novas.

## Global Constraints

- **Padrão de idempotência:** `registrar_*` faz `INSERT ... ON CONFLICT DO NOTHING` e retorna `rowcount > 0` (True na 1ª vez). Igual ao `registrar_envio_slot` existente.
- **Semântica preservada:** envio que falha continua sem retry (logado); `_finalizar_dia` continua 1x/dia; o aviso "sem rascunho" ao curador continua 1x/dia; o seletor do `/meus-dados` continua oferecendo todos os slots com vaga.
- **Imutabilidade / funções pequenas:** seguir o estilo do repo (funções focadas; sem mutar estruturas compartilhadas).
- **Rodar testes:** `cd app && python3 -m unittest discover -s tests` (ou `python3 -m unittest tests.test_horario -v` pra o arquivo).
- **Toda nova tabela entra em `db._TABELAS`** (RLS do Supabase em produção).
- **Referências existentes (não renomear):** `db.registrar_envio_slot(data, slot)`, `daily._hoje_iso()`, `daily._e_dia_util(dt)`, `daily._tema_meta(tema)`, `daily._audio_master(hoje, art, conteudo)`, `daily._pdf_master(hoje, art, conteudo, tmeta)`, `daily.montar_texto_resumo`, `deliver.distribuir(rascunho, assinantes, delay, enviar_fn)`, `deliver.personalizar_rodape`, `subscribers.ativos()`, `subscribers.slot_de(sub)`, `subscribers.por_id(id)`, `subscribers.definir_slot(id, slot)`, `subscribers.slots_com_vaga(teto, slot_atual=None)`.

---

### Task 1: `db.py` — tabela `envios_dia` + helpers de ledger

**Files:**
- Modify: `app/db.py` (schema CREATE TABLE após `envios_slot` ~linha 158; `_TABELAS` ~linha 209; novas funções após `registrar_envio_slot` ~linha 321)
- Test: `app/tests/test_horario.py` (nova classe `TestLedgerDia`)

**Interfaces:**
- Consumes: `db._conn()`, `db._is_pg()`, `db.init()`, `db.registrar_envio_slot(data, slot)`.
- Produces:
  - `db.registrar_envio_assinante(data: str, sub_id: str) -> bool` — True só na 1ª vez do dia p/ aquele assinante (claim atômico).
  - `db.ja_enviou_hoje(data: str, sub_id: str) -> bool` — leitura.
  - `db.slot_ja_enviou(data: str, slot: str) -> bool` — leitura (o tick daquele slot já rodou hoje?).

- [ ] **Step 1: Write the failing tests**

Adicionar ao fim de `app/tests/test_horario.py`, ANTES do bloco `if __name__ == "__main__":`:

```python
class TestLedgerDia(unittest.TestCase):
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

    def test_registrar_envio_assinante_idempotente(self):
        self.assertTrue(self.db.registrar_envio_assinante("2026-07-24", "sub_1"))    # 1ª vez
        self.assertFalse(self.db.registrar_envio_assinante("2026-07-24", "sub_1"))   # repetido
        self.assertTrue(self.db.registrar_envio_assinante("2026-07-24", "sub_2"))    # outro sub
        self.assertTrue(self.db.registrar_envio_assinante("2026-07-25", "sub_1"))    # outro dia

    def test_ja_enviou_hoje(self):
        self.assertFalse(self.db.ja_enviou_hoje("2026-07-24", "sub_1"))
        self.db.registrar_envio_assinante("2026-07-24", "sub_1")
        self.assertTrue(self.db.ja_enviou_hoje("2026-07-24", "sub_1"))

    def test_slot_ja_enviou(self):
        self.assertFalse(self.db.slot_ja_enviou("2026-07-24", "08h"))
        self.db.registrar_envio_slot("2026-07-24", "08h")
        self.assertTrue(self.db.slot_ja_enviou("2026-07-24", "08h"))
        self.assertFalse(self.db.slot_ja_enviou("2026-07-24", "12h"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd app && python3 -m unittest tests.test_horario.TestLedgerDia -v`
Expected: FAIL — `AttributeError: module 'db' has no attribute 'registrar_envio_assinante'`.

- [ ] **Step 3: Add the table to the schema**

Em `app/db.py`, no bloco `CREATE TABLE IF NOT EXISTS`, logo depois do bloco `envios_slot` (que termina na linha `);` após `PRIMARY KEY (data, slot)`), inserir:

```sql
            CREATE TABLE IF NOT EXISTS envios_dia (
                data TEXT, subscriber_id TEXT, enviado_em TEXT,
                PRIMARY KEY (data, subscriber_id)
            );
```

- [ ] **Step 4: Register the table in `_TABELAS`**

Em `app/db.py`, na lista `_TABELAS`, adicionar `"envios_dia"` ao fim:

```python
_TABELAS = ["digests", "login_codes", "sessions", "subscribers",
            "pending_signups", "webhook_events", "cupons", "senha_tokens",
            "curadoria_candidatos", "reserva_resumos", "daily_drafts", "agenda",
            "afiliados", "comissoes", "settings", "envios_slot", "envios_dia"]
```

- [ ] **Step 5: Add the three helper functions**

Em `app/db.py`, logo depois da função `registrar_envio_slot` (após a linha `return cur.rowcount > 0`), inserir:

```python
def registrar_envio_assinante(data, sub_id):
    """True se é a 1ª vez que (data, assinante) é registrado hoje; False se já registrado.
    Claim atômico do envio do dia por assinante (guarda 2x na troca de slot)."""
    from datetime import datetime
    with _conn() as c:
        cur = c.execute("INSERT INTO envios_dia (data,subscriber_id,enviado_em) VALUES (?,?,?) "
                        "ON CONFLICT (data,subscriber_id) DO NOTHING",
                        (data or "", sub_id or "", datetime.now().isoformat()))
        return cur.rowcount > 0


def ja_enviou_hoje(data, sub_id):
    """True se o assinante já recebeu o estudo em `data` (leitura, não escreve)."""
    with _conn() as c:
        r = c.execute("SELECT 1 FROM envios_dia WHERE data=? AND subscriber_id=?",
                      (data or "", sub_id or "")).fetchone()
    return r is not None


def slot_ja_enviou(data, slot):
    """True se o tick daquele slot já rodou em `data` (leitura). Base do gate do catch-up."""
    with _conn() as c:
        r = c.execute("SELECT 1 FROM envios_slot WHERE data=? AND slot=?",
                      (data or "", slot or "")).fetchone()
    return r is not None
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd app && python3 -m unittest tests.test_horario.TestLedgerDia -v`
Expected: PASS (3 testes).

- [ ] **Step 7: Commit**

```bash
git add app/db.py app/tests/test_horario.py
git commit -m "feat(guard-slot): tabela envios_dia + registrar_envio_assinante/ja_enviou_hoje/slot_ja_enviou"
```

---

### Task 2: `daily.py` — refatorar envio + claim no `enviar_slot` (mata 2x)

**Files:**
- Modify: `app/daily.py` (`enviar_slot`, linhas ~446-491)
- Test: `app/tests/test_horario.py` (classe `TestEnviarSlot`)

**Interfaces:**
- Consumes: `db.registrar_envio_assinante` (Task 1), `daily._hoje_iso`, `daily._e_dia_util`, `daily._tema_meta`, `daily._audio_master`, `daily._pdf_master`, `daily.montar_texto_resumo`, `deliver.*`, `subscribers.ativos/slot_de`.
- Produces:
  - `daily._montar_ctx(hoje, r) -> dict` — ctx com chaves `r, art, titulo, conteudo, tmeta, audio_bytes, master_pdf`.
  - `daily._ctx_do_dia(hoje) -> dict | None` — None se não é dia útil OU sem rascunho aprovado.
  - `daily._enviar_estudo_para(whatsapp, nome, ctx) -> None` — envia texto+PDF+áudio a 1 assinante.
  - `daily.enviar_slot(slot)` — agora com claim por assinante.

- [ ] **Step 1: Write the failing test**

Adicionar este método à classe `TestEnviarSlot` em `app/tests/test_horario.py` (a classe já tem A no 12h e B no 08h; a mock de `deliver.distribuir` estende `subs`, que são os dicts de assinante com `id`):

```python
    def test_troca_de_slot_nao_reenvia(self):
        self.daily.enviar_slot("12h")                 # A (12h) recebe
        self.assertEqual(len(self.enviados), 1)
        a_id = self.enviados[0]["id"]
        self.enviados.clear()
        self.s.definir_slot(a_id, "20h")              # A troca de horário no meio do dia
        self.daily.enviar_slot("20h")                 # 20h dispara depois
        self.assertEqual(self.enviados, [])           # claim já usado -> NÃO reenvia
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_horario.TestEnviarSlot.test_troca_de_slot_nao_reenvia -v`
Expected: FAIL — hoje o 20h reinclui A (o `enviados` teria 1 item, não `[]`).

- [ ] **Step 3: Replace `enviar_slot` and add the three helpers**

Em `app/daily.py`, substituir a função `enviar_slot` inteira (linhas ~446-491) por estas quatro funções (as três helpers ANTES do `enviar_slot`):

```python
def _montar_ctx(hoje, r):
    """ctx de envio (título/conteúdo/tema + PDF/áudio master cacheados do dia) a partir de um
    rascunho aprovado r. Puro — assume r válido."""
    art = r["artigo"]
    titulo = r.get("titulo_pt") or art.get("titulo", "")
    conteudo = {"titulo_pt": titulo, "resumo": r["resumo"], "gancho": r.get("gancho", ""), "grafico": r.get("grafico")}
    tmeta = _tema_meta(art.get("tema", ""))
    return {"r": r, "art": art, "titulo": titulo, "conteudo": conteudo, "tmeta": tmeta,
            "audio_bytes": _audio_master(hoje, art, conteudo),
            "master_pdf": _pdf_master(hoje, art, conteudo, tmeta)}


def _ctx_do_dia(hoje):
    """ctx pronto p/ enviar, ou None se não é dia útil de envio OU não há rascunho aprovado.
    Usado pelo catch-up (que não tem os guards do enviar_slot)."""
    if not _e_dia_util(datetime.now()):
        return None
    r = draft_store.carregar(hoje)
    if not r or r.get("status") == "SKIPPED":
        return None
    return _montar_ctx(hoje, r)


def _enviar_estudo_para(whatsapp, nome, ctx):
    """Envia o estudo do dia (texto + PDF + áudio) a UM assinante. Falha de mídia é logada."""
    import phone
    whatsapp = phone.normalizar(whatsapp)
    link = f"{config.PUBLIC_URL}/entrar"
    msg = deliver.personalizar_rodape(montar_texto_resumo(ctx["titulo"], ctx["r"]["resumo"], ctx["tmeta"]), nome, link)
    deliver.enviar_texto(whatsapp, msg)
    if ctx["master_pdf"]:
        try:
            deliver.enviar_pdf(whatsapp, ctx["master_pdf"], caption=ctx["titulo"])
        except Exception as e:
            print(f"[enviar] PDF p/ {whatsapp} falhou: {e}", flush=True)
    if ctx["audio_bytes"]:
        try:
            deliver.enviar_audio(whatsapp, ctx["audio_bytes"])
        except Exception as e:
            print(f"[enviar] áudio p/ {whatsapp} falhou: {e}", flush=True)


def enviar_slot(slot):
    """Envia o estudo do dia SÓ pros assinantes de `slot`. Idempotente por (dia, slot) E por
    (dia, assinante) — o claim `registrar_envio_assinante` garante 1 envio/dia mesmo com troca."""
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
    ctx = _montar_ctx(hoje, r)
    # claim por assinante: só quem AINDA não recebeu hoje (mata reenvio na troca de slot)
    destinatarios = [s for s in subscribers.ativos()
                     if subscribers.slot_de(s) == slot and db.registrar_envio_assinante(hoje, s["id"])]
    res = deliver.distribuir(r, destinatarios, config.SEND_DELAY_SEC,
                             lambda w, n: _enviar_estudo_para(w, n, ctx))
    _finalizar_dia(hoje, r, ctx["art"], ctx["conteudo"], ctx["tmeta"])
    if destinatarios:
        deliver.enviar_curador(f"✅ Enviado (slot {slot}, {ctx['art'].get('tema','')}): {res['ok']} assinantes"
                               + (f" · {len(res['falhas'])} falhas" if res["falhas"] else "")
                               + (" · ⚠️ SEM PDF (erro na geração)" if ctx["master_pdf"] is None else ""))
```

- [ ] **Step 4: Run the whole `TestEnviarSlot` class**

Run: `cd app && python3 -m unittest tests.test_horario.TestEnviarSlot -v`
Expected: PASS em todos — o novo `test_troca_de_slot_nao_reenvia` e os antigos (`test_envia_so_do_slot`, `test_idempotente_por_slot`, `test_default_recebe_no_08h`, `test_sent_nao_bloqueia_outro_slot_e_finaliza_1x`). Os antigos usam assinantes distintos, então cada claim é a 1ª vez → continuam iguais.

- [ ] **Step 5: Commit**

```bash
git add app/daily.py app/tests/test_horario.py
git commit -m "feat(guard-slot): enviar_slot com claim por assinante (mata reenvio 2x na troca) + extrai _montar_ctx/_ctx_do_dia/_enviar_estudo_para"
```

---

### Task 3: `daily.py` — `enviar_catch_up` (mata 0x)

**Files:**
- Modify: `app/daily.py` (nova função após `enviar_slot`)
- Test: `app/tests/test_horario.py` (classe `TestEnviarSlot` — adicionar mock de `_enviar_estudo_para` no `setUp` + 3 testes)

**Interfaces:**
- Consumes: `daily._ctx_do_dia` (Task 2), `daily._enviar_estudo_para` (Task 2), `db.registrar_envio_assinante` (Task 1), `subscribers.por_id`.
- Produces: `daily.enviar_catch_up(sub) -> bool` — envia o estudo de hoje a UM assinante; True se enviou, False se nada a enviar OU já recebeu.

- [ ] **Step 1: Add the `_enviar_estudo_para` mock to `TestEnviarSlot.setUp`**

Em `app/tests/test_horario.py`, na classe `TestEnviarSlot`, no `setUp`, logo depois da linha `self.daily._e_dia_util = lambda dt: True`, adicionar:

```python
        self.daily._enviar_estudo_para = lambda w, n, ctx: self.enviados.append({"whatsapp": w, "nome": n})
```

(É inofensivo pros testes de `enviar_slot`: lá a mock de `deliver.distribuir` substitui o loop inteiro, então `_enviar_estudo_para` não é chamado.)

- [ ] **Step 2: Write the failing tests**

Adicionar à classe `TestEnviarSlot`:

```python
    def test_catch_up_envia_uma_vez(self):
        reg = self.s.adicionar("C", "5543000000003")
        self.s.definir_slot(reg["id"], "20h")
        c = self.s.por_id(reg["id"])
        self.assertTrue(self.daily.enviar_catch_up(c))              # envia
        self.assertEqual([e["nome"] for e in self.enviados], ["C"])
        self.enviados.clear()
        self.assertFalse(self.daily.enviar_catch_up(c))            # já recebeu -> não repete
        self.assertEqual(self.enviados, [])

    def test_catch_up_sem_rascunho_nao_envia(self):
        self.daily._ctx_do_dia = lambda hoje: None                 # simula dia sem rascunho / não útil
        reg = self.s.adicionar("D", "5543000000004")
        d = self.s.por_id(reg["id"])
        self.assertFalse(self.daily.enviar_catch_up(d))
        self.assertEqual(self.enviados, [])
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd app && python3 -m unittest tests.test_horario.TestEnviarSlot.test_catch_up_envia_uma_vez -v`
Expected: FAIL — `AttributeError: module 'daily' has no attribute 'enviar_catch_up'`.

- [ ] **Step 4: Add `enviar_catch_up`**

Em `app/daily.py`, logo depois da função `enviar_slot`, inserir:

```python
def enviar_catch_up(sub):
    """Envia o estudo de hoje a UM assinante que trocou pra um slot já disparado e ainda não
    recebeu. Idempotente (claim em envios_dia). Retorna True se enviou; False se nada a enviar
    ou já recebeu. NÃO chama _finalizar_dia (já rodou no 1º slot do dia)."""
    import db
    hoje = _hoje_iso()
    ctx = _ctx_do_dia(hoje)
    if ctx is None:
        return False
    if not db.registrar_envio_assinante(hoje, sub["id"]):   # já recebeu hoje -> não repete
        return False
    _enviar_estudo_para(sub["whatsapp"], sub.get("nome", ""), ctx)
    return True
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd app && python3 -m unittest tests.test_horario.TestEnviarSlot -v`
Expected: PASS em todos (incluindo os dois novos de catch-up e os anteriores).

- [ ] **Step 6: Commit**

```bash
git add app/daily.py app/tests/test_horario.py
git commit -m "feat(guard-slot): enviar_catch_up (envia a 1 assinante que trocou p/ slot já disparado)"
```

---

### Task 4: `serve.py` — `salvar_horario` dispara o catch-up (mata 0x na troca real)

**Files:**
- Modify: `app/serve.py` (bloco `if acao == "salvar_horario":`, linhas ~591-602)
- Test: `app/tests/test_horario.py` (classe `TestEnviarSlot` — 1 teste de integração que simula a decisão do handler)

**Interfaces:**
- Consumes: `db.slot_ja_enviou` (Task 1), `daily.enviar_catch_up` (Task 3), `daily._hoje_iso`, `subscribers.definir_slot/por_id/slot_de/slots_com_vaga`.
- Produces: (nenhuma nova API — só liga o catch-up no handler)

- [ ] **Step 1: Write the failing integration test**

Adicionar à classe `TestEnviarSlot` em `app/tests/test_horario.py` (reproduz a decisão do `salvar_horario` com as funções reais):

```python
    def test_troca_para_slot_ja_disparado_dispara_catch_up(self):
        self.daily.enviar_slot("08h")                 # 08h dispara (B recebe) -> slot_ja_enviou True
        self.enviados.clear()
        reg = self.s.adicionar("E", "5543000000005")  # E não recebeu ainda
        self.s.definir_slot(reg["id"], "20h")
        # --- simula a lógica do salvar_horario ao trocar 20h -> 08h (já passou) ---
        hoje = self.daily._hoje_iso()
        self.s.definir_slot(reg["id"], "08h")
        if self.db.slot_ja_enviou(hoje, "08h"):
            self.daily.enviar_catch_up(self.s.por_id(reg["id"]))
        # ---
        self.assertEqual([e["nome"] for e in self.enviados], ["E"])   # recebeu na hora (1x)

    def test_slot_futuro_nao_esta_disparado(self):
        hoje = self.daily._hoje_iso()
        self.assertFalse(self.db.slot_ja_enviou(hoje, "20h"))   # 20h não rodou -> handler não faz catch-up
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd app && python3 -m unittest tests.test_horario.TestEnviarSlot.test_troca_para_slot_ja_disparado_dispara_catch_up -v`
Expected: PASS já é possível (usa só funções das Tasks 1-3). Se `slot_ja_enviou`/`enviar_catch_up` não existirem ainda, FAIL com AttributeError — nesse caso as Tasks 1-3 precisam estar aplicadas. (Este teste valida a lógica que o handler vai chamar.)

- [ ] **Step 3: Wire the catch-up into `salvar_horario`**

Em `app/serve.py`, substituir o bloco `if acao == "salvar_horario":` (linhas ~591-602) por:

```python
            if acao == "salvar_horario":
                import db as _db, config as _cfg, daily as _daily
                novo = g("slot")
                atual = subscribers.slot_de(sub)
                teto = int(_db.get_config("slot_teto", str(_cfg.SLOT_TETO_DEFAULT)) or _cfg.SLOT_TETO_DEFAULT)
                if novo != atual and novo in subscribers.slots_com_vaga(teto):
                    subscribers.definir_slot(sub["id"], novo)
                    hoje = _daily._hoje_iso()
                    if _db.slot_ja_enviou(hoje, novo):     # novo horário já disparou hoje -> catch-up
                        try:
                            _daily.enviar_catch_up(subscribers.por_id(sub["id"]))
                        except Exception as e:
                            print(f"[meus-dados] catch-up falhou: {e}", flush=True)  # não derruba a página
                sub2 = subscribers.por_id(sub["id"])
                atual2 = subscribers.slot_de(sub2)
                return self._html(site_web.pagina_meus_dados(
                    sub2, msg="Horário salvo.",
                    slots=subscribers.slots_com_vaga(teto, atual2), slot_atual=atual2), 200)
```

- [ ] **Step 4: Run the full test suite**

Run: `cd app && python3 -m unittest discover -s tests`
Expected: PASS em tudo (a suíte inteira, ~207+ testes). O `serve.py` não é importado pelos testes (o handler HTTP não tem harness), então o wiring é validado pela lógica equivalente do Step 1 + smoke manual.

- [ ] **Step 5: Commit**

```bash
git add app/serve.py app/tests/test_horario.py
git commit -m "feat(guard-slot): salvar_horario dispara catch-up quando o novo slot já passou (mata 0x)"
```

---

## Self-Review

**Spec coverage:**
- `db.envios_dia` + `registrar_envio_assinante`/`ja_enviou_hoje`/`slot_ja_enviou` → Task 1. ✅
- Refatorar `_enviar_estudo_para`/`_montar_ctx`/`_ctx_do_dia` + claim no `enviar_slot` (mata 2x) → Task 2. ✅
- `enviar_catch_up` → Task 3. ✅
- `salvar_horario` dispara catch-up com gate `slot_ja_enviou` (mata 0x) → Task 4. ✅
- Matriz de comportamento (2x/0x/troca múltipla/dia sem rascunho) coberta pelos testes das Tasks 2-4. ✅
- Bordas: corrida (claim atômico, Task 1), envio que falha sem retry (semântica preservada, Task 2), catch-up em dia sem envio (Task 3 `test_catch_up_sem_rascunho_nao_envia`), `try/except` no handler (Task 4). ✅

**Placeholder scan:** sem TBD/TODO; todo passo com código real e comando esperado. ✅

**Type consistency:** `registrar_envio_assinante(data, sub_id)`, `ja_enviou_hoje(data, sub_id)`, `slot_ja_enviou(data, slot)`, `enviar_catch_up(sub)`, ctx com chaves `r/art/titulo/conteudo/tmeta/audio_bytes/master_pdf` — usados consistentemente entre as tasks. ✅

## Notas de execução

- **Migração em produção:** `db.init()` roda o `CREATE TABLE IF NOT EXISTS envios_dia` no boot; nenhuma migração manual. Em produção (Postgres) a RLS é aplicada porque a tabela entra em `_TABELAS`.
- **Sem impacto retroativo:** `envios_dia` começa vazia; no dia do deploy, quem já recebeu antes do deploy não está no ledger — mas o `enviar_slot` de cada slot só roda 1x/dia (guard `envios_slot`), e o cenário de troca só ocorre após o deploy. Sem risco de reenvio em massa.
