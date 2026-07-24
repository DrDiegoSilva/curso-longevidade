# Horário de envio por assinante — Design

**Data:** 2026-07-24 · **Host:** `artigos.` (assinatura) · Relacionado ao [[projeto-c-conta-assinante]] (`/meus-dados`) e ao backlog item 2 (escala WhatsApp).
**Status:** Design aprovado (brainstorming) — aguardando revisão do spec.

## Objetivo

Deixar o assinante **escolher o horário** em que recebe o estudo do dia no WhatsApp. Além de melhor UX, isso **espalha os envios** ao longo do dia (menos *burst*) — reduz o risco de **ban** do número não-oficial (Z-API/Evolution), que é o gargalo de escala. Slots com **teto** e **auto-balanceio** (assinante novo só vê horários com vaga).

## Decisões (Diego, 2026-07-24)

- **Slots fixos:** **07h, 08h, 12h, 18h, 20h**. (Editar os horários pelo admin fica p/ depois — MVP hardcoded.)
- **Teto por slot:** configurável em `db.settings` (`slot_teto`), default **100**.
- **Default:** quem não escolher fica no **08h** (preserva o comportamento atual; ninguém deixa de receber).
- **Um estudo por dia:** todos os slots enviam o **mesmo** estudo do dia, só em horários diferentes.
- **Tick das 18h faz as duas coisas:** `preparar_18h` (prepara amanhã + revisão do curador) **e** envia o estudo de hoje pro slot 18h.
- **Escolha vive no `/meus-dados`** (Projeto C).

## Arquitetura

### Slots (constante) — `daily.py`
- `SLOTS = ["07h", "08h", "12h", "18h", "20h"]` + mapa hora: `SLOT_HORA = {"07h":7, "08h":8, "12h":12, "18h":18, "20h":20}`.
- `SLOT_DEFAULT = "08h"`.

### Dados — `db.py` / `subscribers.py`
- Coluna nova `subscribers.slot_envio TEXT` (via CREATE TABLE + `_add_coluna` no `_migrar_colunas` p/ o Postgres de produção + entrar em `subscribers._COLS`). Vazio/NULL → tratado como `SLOT_DEFAULT`.
- `db.settings` já existe (da aba de mensagens): chave `slot_teto` (default 100 via `get_config("slot_teto", "100")`).
- Idempotência: tabela nova `envios_slot(data TEXT, slot TEXT, enviado_em TEXT, PRIMARY KEY (data, slot))` + `db.registrar_envio_slot(data, slot) -> bool` (True na 1ª vez; False se já enviado — igual `registrar_webhook`). Entra em `_TABELAS` (RLS).

### Contagem / vaga — `subscribers.py`
- `contar_por_slot() -> dict` — quantos assinantes **ativos** em cada slot (NULL/vazio conta como `SLOT_DEFAULT`).
- `slots_com_vaga(teto, slot_atual=None) -> list[str]` — slots com `count < teto`, **sempre incluindo o `slot_atual`** do assinante (pra ele poder manter o horário mesmo se o slot lotou depois). Preserva a ordem de `SLOTS`.

### Escolha do assinante — `/meus-dados` (`site_web.py` + `serve.py`)
- Novo bloco "Horário de recebimento" na página `/meus-dados`: um `<select>`/rádios com **só os slots com vaga** (via `slots_com_vaga(teto, slot_atual)`), marcando o slot atual.
- POST em `/meus-dados` com `acao=salvar_horario` → valida que o slot ∈ `SLOTS` e (se mudou) que **tem vaga**; grava via `subscribers.definir_slot(id, slot)`. Se o slot escolhido lotou no meio → mensagem "horário lotou, escolha outro".
- Reusa o padrão de auth do `/meus-dados` (assinante logado).

### Envio por slot — `daily.py`
- Refatorar `enviar_08h` → **`enviar_slot(slot)`**: mesma lógica de hoje (só em dia de envio, com rascunho aprovado, gera PDF, monta a mensagem), mas o loop de destinatários filtra por `slot_envio == slot` (tratando vazio como `SLOT_DEFAULT`). Mantém `SEND_DELAY_SEC` (4s) entre mensagens.
- **Idempotência:** no início, `if not db.registrar_envio_slot(hoje, slot): return` (não reenvia após restart).
- **Pré-renovação:** o aviso de pré-renovação (hoje dentro de `rotina_08h`) continua **só no tick das 08h** (não repete por slot).

### Agendador — `serve.py`
- Hoje: `proximo_disparo(now, [(8,"enviar"), (18,"preparar")])`.
- Novo: disparos = **um "enviar" por slot** + o "preparar" das 18h:
  `[(7,"enviar:07h"), (8,"enviar:08h"), (12,"enviar:12h"), (18,"preparar"), (18,"enviar:18h"), (20,"enviar:20h")]`.
  (Se `proximo_disparo` não suportar dois no mesmo horário, o tick das 18h chama uma função que faz **preparar_18h() + enviar_slot("18h")**.)
- O tick das **08h** faz: aviso de pré-renovação (como hoje) **+** `enviar_slot("08h")`.
- Demais ticks (07/12/20h): só `enviar_slot(<slot>)`. O 18h: `preparar_18h()` + `enviar_slot("18h")`.
- Como o estudo é preparado na véspera (18h), o slot mais cedo (07h) já tem o estudo do dia pronto. ✅

## Erros & bordas

- **Slot lotou entre a página e o submit:** valida vaga no POST; se lotou, não grava e avisa. O `slot_atual` sempre é ofertado (não trava quem já está lá).
- **Restart do container no meio do dia:** `registrar_envio_slot` evita reenviar um slot já disparado hoje.
- **Sem rascunho aprovado / dia sem envio:** `enviar_slot` herda os guards do `enviar_08h` atual (não manda nada; heartbeat preservado).
- **Assinante sem slot (NULL):** conta e recebe como `08h`.
- **Slot inválido no POST:** ignorado (mantém o atual).
- **Teto = 0 ou config inválida:** `get_config` com fallback "100"; parse defensivo.
- **Anti-ban:** o teto por slot + os 4s entre mensagens bordam o burst. Pra escala real (milhares) segue valendo migrar pro WhatsApp Cloud API oficial (backlog).

## Testes (unittest, `cd app && python3 -m unittest discover -s tests`)

- **`subscribers`:** `definir_slot` grava/normaliza; NULL conta como default em `contar_por_slot`; `slots_com_vaga` esconde slots cheios **mas mantém o `slot_atual`**; ordem preservada.
- **`db`:** `registrar_envio_slot` True na 1ª vez, False na 2ª (mesmo dia/slot); dias/slots diferentes independentes.
- **`daily`:** `enviar_slot("12h")` manda só pros do 12h (mock do envio); idempotência (2ª chamada no mesmo dia não reenvia); vazio→08h recebe no slot 08h; pré-renovação só no 08h.
- **`site_web`:** `/meus-dados` renderiza o seletor de horário só com slots disponíveis + marca o atual.
- **`serve`:** POST `salvar_horario` grava; slot cheio → não grava + mensagem. (Se não houver harness p/ o handler, cobrir via as funções `subscribers`/`db` + smoke.)

## Fora de escopo (YAGNI)

- Horários dos slots editáveis no admin (MVP = 5 fixos; adicionar depois, tipo a aba de dias de envio).
- Conteúdo diferente por slot (é o mesmo estudo do dia).
- Migração pro WhatsApp Cloud API oficial (backlog item 2, escala real).
