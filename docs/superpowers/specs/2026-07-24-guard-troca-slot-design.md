# Guard da troca de slot — Design (exatamente 1 envio/dia)

**Data:** 2026-07-24 · **Host:** `artigos.` (assinatura) · Relacionado a [[horario-envio-assinante]] e ao [[projeto-c-conta-assinante]] (`/meus-dados`).
**Status:** Design aprovado (brainstorming) — aguardando revisão do spec.

## Problema

Desde o horário de envio por slot, o `enviar_slot(slot)` monta os destinatários lendo o slot **ao vivo**:

```python
destinatarios = [s for s in subscribers.ativos() if subscribers.slot_de(s) == slot]
```

A idempotência de hoje (`envios_slot` via `db.registrar_envio_slot`) é só por **(dia, slot)** — nunca por assinante. Isso deixa duas brechas quando o assinante troca de horário no meio do dia:

- **2x:** recebe no 08h → às 10h troca pro 12h → às 12h o `enviar_slot("12h")` inclui ele de novo e reenvia.
- **0x:** está no 20h (ainda não recebeu) → às 10h troca pro 08h (que já disparou) → às 20h ele não é mais do slot 20h, e o 08h já rodou → **não recebe nada**.

O handler `salvar_horario` (`serve.py`) hoje troca o slot livremente (só valida vaga), sem guardar nada sobre o envio do dia.

## Objetivo

Garantir **exatamente 1 envio do estudo por assinante por dia**, independente de quantas vezes ele troque de horário. Mata 2x e 0x.

## Decisão central (Diego, 2026-07-24)

- **Ledger por-assinante-por-dia** vira a fonte da verdade de "já recebeu o estudo de hoje". A idempotência por `(dia, slot)` continua (guarda restart); a nova por `(dia, assinante)` guarda a troca.
- **Caso 0x = catch-up (envio na hora):** quando o assinante troca pra um slot que **já disparou hoje** e **ainda não recebeu**, o estudo do dia é enviado a ele **imediatamente** na troca (1 destinatário, reusando PDF/áudio já gerados). A troca vale já hoje.

## Arquitetura

### 1. `db.py` — tabela + helpers

- Tabela nova (no bloco `CREATE TABLE IF NOT EXISTS` do schema):
  ```sql
  CREATE TABLE IF NOT EXISTS envios_dia (
      data TEXT, subscriber_id TEXT, enviado_em TEXT,
      PRIMARY KEY (data, subscriber_id)
  );
  ```
  Entra na lista `_TABELAS` (RLS).
- `registrar_envio_assinante(data, sub_id) -> bool` — `INSERT ... ON CONFLICT (data, subscriber_id) DO NOTHING`, retorna `rowcount > 0`. True só na 1ª vez do dia. Mesmo padrão do `registrar_envio_slot`. **É o claim atômico** que impede 2x mesmo com corrida scheduler×web.
- `ja_enviou_hoje(data, sub_id) -> bool` — `SELECT 1 FROM envios_dia WHERE data=? AND subscriber_id=?` (leitura, não escreve).
- `slot_ja_enviou(data, slot) -> bool` — `SELECT 1 FROM envios_slot WHERE data=? AND slot=?` (leitura; sinaliza que o tick daquele slot já rodou hoje).

### 2. `daily.py` — refatorar o envio p/ reaproveitar em 1 destinatário

- **`_enviar_estudo_para(whatsapp, nome, ctx)`** — extrai o corpo do `_envia` (hoje aninhado no `enviar_slot`) p/ o nível do módulo: normaliza número, monta a mensagem com rodapé, envia texto + PDF (se houver) + áudio (se houver). Mantém os `try/except` por-mídia de hoje.
- **`_montar_ctx(hoje, r)`** — a partir de um rascunho aprovado `r`, monta o dicionário `ctx` com `r`, `art`, `titulo`, `conteudo`, `tmeta`, `master_pdf` (via `_pdf_master`, cacheado do dia) e `audio_bytes` (via `_audio_master`, cacheado). Puro (assume `r` válido).
- **`_ctx_do_dia(hoje) -> dict | None`** — usado pelo catch-up: retorna `None` se não é dia útil de envio **ou** não há rascunho aprovado (`not r or status == "SKIPPED"`); senão retorna `_montar_ctx(hoje, r)`.
- **`enviar_slot(slot)`** — mantém os guards de hoje **inline** (idempotência de slot, dia útil, e o aviso 1x ao curador quando `not r or status == "SKIPPED"`), carrega `r` como hoje e monta `ctx = _montar_ctx(hoje, r)` (não usa `_ctx_do_dia`, pra preservar a distinção do aviso). Chama `_finalizar_dia` 1x como hoje. Muda só a montagem dos destinatários, que passa pelo **claim**:
  ```python
  destinatarios = [s for s in subscribers.ativos()
                   if subscribers.slot_de(s) == slot
                   and db.registrar_envio_assinante(hoje, s["id"])]   # claim: só quem não recebeu hoje
  ```
  O `_envia` inline vira `lambda w, n: _enviar_estudo_para(w, n, ctx)`.
- **`enviar_catch_up(sub) -> bool`** — envio a UM assinante que trocou pra um slot já disparado:
  ```python
  def enviar_catch_up(sub):
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
  **Não** chama `_finalizar_dia` (já rodou no 1º slot do dia).

### 3. `serve.py` — `salvar_horario` dispara o catch-up

Depois do `definir_slot`, se o **novo** slot já disparou hoje e o assinante ainda não recebeu, envia na hora:

```python
if novo != atual and novo in subscribers.slots_com_vaga(teto):
    subscribers.definir_slot(sub["id"], novo)
    hoje = _daily._hoje_iso()
    if _db.slot_ja_enviou(hoje, novo):        # novo horário já passou hoje -> catch-up
        try:
            _daily.enviar_catch_up(subscribers.por_id(sub["id"]))
        except Exception as e:
            print(f"[meus-dados] catch-up falhou: {e}", flush=True)  # não derruba a página
```

Se o novo slot ainda não passou, não faz nada: recebe natural no tick, e o claim garante 1x.

## Matriz de comportamento

| Situação | Resultado |
|---|---|
| Recebeu no 08h → troca 12h | 12h pula (claim falha) → **1x** |
| No 20h, não recebeu → troca 08h (já passou) | catch-up na hora → **1x** |
| No 20h, não recebeu → troca 12h (não passou) | recebe no tick 12h → **1x** |
| Troca várias vezes no dia | claim garante no máximo **1x** |
| Dia sem rascunho / não útil | catch-up não envia (`_ctx_do_dia` = None); ninguém recebe |

## Erros & bordas

- **Corrida scheduler × web:** o claim (`registrar_envio_assinante`, `INSERT ON CONFLICT`) é atômico — só um lado ganha; o outro é pulado.
- **Envio que falha:** mantém a semântica de hoje — o claim é feito antes do envio (o assinante já está em exatamente um slot, sem "próximo slot" pra re-tentar); falha é logada, sem retry. (Fora de escopo mudar isso.)
- **Catch-up em dia sem envio:** `_ctx_do_dia` retorna `None` → não envia; `ja_enviou_hoje` continua False (igual a todo mundo que não recebeu naquele dia).
- **`slot_ja_enviou` True em dia sem draft:** `registrar_envio_slot(hoje, slot)` roda no topo do `enviar_slot` mesmo sem draft, então `slot_ja_enviou` pode ser True sem ter enviado nada. Não é problema: o catch-up cai no `_ctx_do_dia = None` e não envia.
- **Falha de WhatsApp no catch-up:** encapsulada em `try/except` no handler — não derruba a página `/meus-dados`.

## Testes (unittest, `cd app && python3 -m unittest discover -s tests`)

- **`db`:** `registrar_envio_assinante` True na 1ª / False na 2ª (mesmo dia/sub); dias/subs diferentes independentes; `ja_enviou_hoje` reflete o registro; `slot_ja_enviou` False antes / True depois de `registrar_envio_slot`.
- **`daily` (2x):** assinante recebe no slot 12h, troca pro 20h, `enviar_slot("20h")` **não** reenvia (claim falha).
- **`daily` (catch-up):** assinante que não recebeu → `enviar_catch_up` envia 1x; 2ª chamada não repete (claim); dia sem rascunho → `enviar_catch_up` retorna False sem enviar.
- **`serve`:** `salvar_horario` com slot já disparado chama `enviar_catch_up` (mockado); com slot futuro, não chama.
- **Regressão:** os testes atuais de `enviar_slot` (`test_envia_so_do_slot`, `test_idempotente_por_slot`, `test_default_recebe_no_08h`, `test_sent_nao_bloqueia_outro_slot_e_finaliza_1x`) continuam passando.

## Fora de escopo (YAGNI)

- Re-tentar automaticamente um envio que falhou (mantém a semântica atual).
- "Pending slot" / troca que "vale a partir de amanhã" (o catch-up já resolve o 0x hoje).
- Qualquer mudança no seletor de horário do `/meus-dados` (continua oferecendo todos os slots com vaga).
