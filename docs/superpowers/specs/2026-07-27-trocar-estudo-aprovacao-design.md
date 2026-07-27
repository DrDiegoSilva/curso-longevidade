# Trocar o estudo de amanhã na tela de aprovação (Item 23) — Design

**Data:** 2026-07-27
**Status:** aprovado (brainstorming) → aguardando plano
**Branch:** feat/trocar-estudo-aprovacao (base 6b72d25 = main local: curadoria + SYS_ESTUDO)
**Backlog:** item 23
**Coordenação:** outro agente ativo no worktree `agenda-tema` (`feat/agenda-tema-por-dia`) mexendo em agenda/rotação. **Este design NÃO toca a LÓGICA de rotação/planejamento** (`agenda_plan.planejar_agenda`/`_rank`/`materializar_agenda`/`temas_config.json`). Deploy é **sequenciado** (entra depois que a mudança de datas dele aterrissar).

## Emenda 2026-07-27 (Opção A — aprovada pelo Diego, após review da Task 2)

O review da Task 2 pegou um **risco real de envio duplicado**: o pipeline normal "consome" um estudo gravando o slot da agenda E marcando-o `agendado` **juntos** (e há auto-heal que devolve ao pool todo `agendado` que nenhum slot referencia). Se a troca refaz o rascunho **sem** gravar o slot, o estudo escolhido continua no pool → a máquina pode **re-enviá-lo** num dia seguinte. **Correção (Opção A):** `trocar_estudo_amanha` passa a **gravar o slot de amanhã no escolhido** (`db.agenda_upsert` + `db.marcar_reserva_agendado`/`marcar_candidato_agendado`, exatamente como o `materializar_agenda`) e **devolve o estudo atual ao pool** (`marcar_candidato_pronto`/`marcar_reserva_pronto`). Isso mexe **só na TABELA `agenda` (dado)** — não na lógica de rotação do agente `agenda-tema`. Bônus: a grade da `/agenda` deixa de ficar desatualizada (não é mais "cosmético fora de escopo").

## Objetivo

No `/revisar` das 18h, quando o Diego não gosta do estudo preparado p/ amanhã, poder **trocar por outro que ELE escolhe**, sem ir na agenda. O recusado **volta pro pool**. Reaproveita o pipeline de preparo já testado (`daily._preparar_*`). A geração é **assíncrona**: o clique responde na hora e o novo resumo chega no WhatsApp com link novo, igual ao preview das 18h.

Origem: "não tenho a opção de trocar o estudo pro próximo da lista caso eu não goste na minha tela de aprovação, só tem na tela da agenda". Confirmado no código: `review_web.pagina_revisao` só tem Aprovar/Editar/Regerar-áudio/Não-enviar; a Agenda só troca estudo **entre dias**, não substitui pelo próximo/por um escolhido.

## Decisões (brainstorming 2026-07-27)

- **Picker (Diego escolhe), não "próximo" cego.** Cravado pelo cenário real: ele subiu um retatrutida específico e quer ESSE amanhã. O 1º da lista já é "o próximo da fila", mas ele pode rolar e escolher outro.
- **O recusado VOLTA pro pool** ("devolver pro banco de dados"), não descarta. (Descartar-de-vez / sinal de treino p/ score = fora de escopo.)
- **Assíncrono** — a geração leva ~1–2 min (candidato cru, resumo JIT) ou ~30–60s (reserva, resumo pronto); trava demais p/ segurar o request. Responde na hora, entrega no WhatsApp.
- **Lista de escolha = reserva (`pronto`) + candidatos (`novo`).** Clássicos ficam **fora do picker** no MVP (são o piso/fallback, raramente o que se escolhe à mão; incluir depois é trivial — mesma `_preparar_de_classico`).
- **Sem limite de trocas/dia** no MVP (é o Diego, manual). Add teto depois se custar.

## Descobertas que moldam a implementação

- **O que sai às 08h é o RASCUNHO salvo, não a agenda.** `daily.enviar_slot(slot)` → `draft_store.carregar(hoje)`. Logo, trocar o envio de amanhã = **refazer o rascunho de amanhã**; mexer na agenda não muda o envio já preparado.
- **1 rascunho por dia** — `draft_store` é keyed por data (`r["data"]`). Refazer = `novo_rascunho(alvo, …)` sobrescreve o rascunho daquela data e gera **novo `review_token`** → link antigo morre, novo chega no WhatsApp.
- **As `_preparar_*` já fazem o trabalho inteiro** (resumo se preciso + PDF com retry + áudio preview + `enviar_curador` com o link + salva o draft):
  - `daily._preparar_de_candidato(cand_id)` — candidato cru, resumo JIT (mira `_preparar_de_artigo`); grava `r["candidato_id"]`.
  - `daily._preparar_da_reserva(reserva_id)` — item da reserva com resumo pronto; grava `r["reserva_id"]`.
  - (`_preparar_de_classico(id)` grava `r["classico_id"]` — não usado no picker MVP.)
  - Todas miram `alvo = now()+1 dia` (= amanhã). Válido no contexto: a revisão é na véspera → `r["data"] == amanhã`.
- **Pool de candidatos** (`curadoria_candidatos.status`): `db.marcar_candidato_pronto(cid)` devolve p/ `novo`; `db.listar_candidatos('novo', tema=…)`; `db.listar_reserva('pronto')`. A reserva **só é marcada `enviado` no envio**, não no preparo — então trocar um item de reserva o deixa intacto (`pronto`), reusável.
- **Rota:** o `/revisar/<token>` (GET e POST) já existe em `serve.py`. O POST despacha por `g("acao")` (ex.: `regerar_audio` renderiza de volta a página). **Reuso o mesmo POST** com ações novas — sem parsing de rota nova.
- **Thread de fundo:** `serve.py` já importa `threading`. `_preparar_*` fazem I/O de rede; rodam bem num `threading.Thread(daemon=True)`.

## Fluxo

1. **`pagina_revisao`** ganha o botão `🔁 Trocar por outro estudo` (`name="acao" value="trocar"`, mesmo form).
2. **POST `/revisar/<tok>` com `acao=trocar`** → monta as alternativas e renderiza **`review_web.pagina_trocar_estudo(alternativas, r, token)`** (lista com título · revista · tema · nota; cada item com `Usar este amanhã` = `acao=trocar_confirmar` + `tipo` + `id`). Botão "voltar" p/ a revisão.
3. **POST `/revisar/<tok>` com `acao=trocar_confirmar` (`tipo`, `id`)** →
   - valida token/draft e que `id`/`tipo` está entre as alternativas válidas;
   - dispara **`threading.Thread`** rodando `daily.trocar_estudo_amanha(token, tipo, id)`;
   - responde **na hora**: `🔄 Trocando — o novo resumo chega no seu WhatsApp em ~1-2 min, com link novo de revisão.`
4. **`daily.trocar_estudo_amanha(token, tipo, id)`** (fundo):
   - `r = draft_store.por_token(token)`; se sumiu → aviso ao curador e sai.
   - **devolve o atual ao pool:** se `r.get("candidato_id")` → `db.marcar_candidato_pronto(...)`; se `reserva_id`/`classico_id` → no-op (reserva segue `pronto`; clássico é reusável); fila/fallback → nada.
   - **prepara o escolhido:** `tipo=="candidato"` → `_preparar_de_candidato(id)`; `tipo=="reserva"` → `_preparar_da_reserva(reserva_id=id)`. Isso sobrescreve o rascunho de amanhã e manda preview + áudio + link novo.
   - sucesso → (opcional) `enviar_curador("🔁 Trocado.")`; falha (exceção) → `enviar_curador("⚠️ Não consegui trocar o estudo; o anterior segue valendo.")` e o rascunho antigo permanece.

## Componentes / mudanças

1. `app/review_web.py`
   - `pagina_revisao`: + botão `🔁 Trocar por outro estudo`.
   - **nova** `pagina_trocar_estudo(alternativas, r, token)`: lista os candidatos (escapando tudo) com o form `acao=trocar_confirmar`/`tipo`/`id`; estado vazio "Sem outros estudos disponíveis" + voltar.
2. `app/daily.py`
   - **nova** `montar_alternativas(r)`: `db.listar_reserva('pronto')` + `db.listar_candidatos('novo')`, **exclui o estudo atual** (por id) e normaliza p/ `{tipo,id,titulo,fonte,tema,score}`. **Ordenação exata:** (1) **reserva primeiro** (prioridade desc, depois score desc) — põe os uploads do Diego no topo; (2) depois os **candidatos**, com o **tema de amanhã primeiro** (= `r["artigo"]["tema"]`) e o resto por score desc. Corta em N (ex.: 20).
   - **nova** `trocar_estudo_amanha(token, tipo, id)`: devolve o atual ao pool + chama o `_preparar_*` certo. Pura orquestração, sem rota.
3. `app/serve.py`
   - No POST `/revisar/<tok>`: tratar `acao=="trocar"` (render picker) e `acao=="trocar_confirmar"` (spawn thread + página "Trocando"). Antes do `draft_store.aplicar` genérico.
4. **Não mexer:** agenda/rotação/`materializar_agenda`/`agenda_plan.planejar_agenda` (só leitura de `_rank` se ajudar a ordenar), `_preparar_*` (reuso), `enviar_slot`, `montar_texto_resumo`, SYS_ESTUDO, aprovar/editar/nao_enviar/regerar_audio.

## Guarda-corpos

- **Sem alternativas** → picker mostra "Sem outros estudos disponíveis" e mantém o atual.
- **Validação:** `trocar_confirmar` só aceita `id`/`tipo` presente na lista de alternativas (não confia no form).
- **Async fail-safe:** exceção na thread → aviso ao curador; rascunho antigo intacto (as `_preparar_*` só sobrescrevem no fim do caminho feliz).
- **Idempotência/concorrência:** mira sempre o rascunho de **amanhã** (mesma data). Duas trocas → a última vence (draft keyed por data). Sem colisão com 08h (envia hoje) nem com o 18h (prepara amanhã, mas roda depois).
- **Pressuposto de data:** a troca assume `r["data"] == amanhã` (contexto real da revisão da véspera). As `_preparar_*` já miram `now()+1`. Fora desse contexto o botão não é oferecido.
- **Grade consistente (Opção A):** a troca grava o slot de amanhã no escolhido (`db.agenda_upsert`), então a grade da `/agenda` reflete o estudo novo — e o escolhido é consumido (não re-enviado). Toca só a tabela `agenda` (dado), não a lógica de rotação do agente `agenda-tema`.

## Testes (TDD, `app/tests/test_trocar_estudo.py` + ajustes)

- `montar_alternativas(r)`: exclui o estudo atual; ordena reserva-primeiro (uploads no topo) e candidatos por tema/score; corta em N. (db injetável/monkeypatch, sem rede.)
- `trocar_estudo_amanha`:
  - candidato atual → `db.marcar_candidato_pronto` chamado com o id certo; `_preparar_de_candidato(escolhido)` chamado. (monkeypatch de `_preparar_*` e `db.*`.)
  - reserva atual → **não** descarta o antigo; `_preparar_da_reserva(reserva_id=escolhido)` chamado.
  - exceção no `_preparar_*` → `enviar_curador` de falha; sem crash.
- `review_web.pagina_trocar_estudo`: renderiza cada alternativa com escape; form leva `tipo`/`id`; vazio → "Sem outros estudos".
- `review_web.pagina_revisao`: contém o botão `🔁 Trocar`.
- `serve` POST `/revisar/<tok>`: `acao=trocar` → HTML do picker; `acao=trocar_confirmar` → dispara a troca (monkeypatch `trocar_estudo_amanha`/Thread) e retorna a página "Trocando".
- **Regressão:** `aprovar`/`editar`/`nao_enviar`/`regerar_audio` inalterados; suíte inteira verde (baseline 703).

## Critérios de aceite

- [ ] Botão `🔁 Trocar` na tela de revisão abre a lista de alternativas (reserva + candidatos), excluindo o atual, com os uploads/reserva no topo e o tema de amanhã priorizado entre os candidatos.
- [ ] Escolher um → resposta imediata "Trocando…"; em ~1–2 min chega no WhatsApp o novo resumo (PDF+áudio) com **link de revisão novo**.
- [ ] O estudo recusado volta pro pool (candidato→`novo`; reserva segue reusável).
- [ ] O envio das 08h passa a ser o estudo novo (rascunho refeito).
- [ ] Nada da agenda/rotação foi tocado; testes verdes.

## Arquivos

- `app/review_web.py` (botão + `pagina_trocar_estudo`)
- `app/daily.py` (`montar_alternativas`, `trocar_estudo_amanha`)
- `app/serve.py` (ações `trocar`/`trocar_confirmar` no POST `/revisar`)
- `app/tests/test_trocar_estudo.py` (novo)

## Fora de escopo (backlog)

- Descartar-de-vez / sinal de treino p/ score (item 23 futuro).
- Clássicos no picker (add trivial depois).
- Limite de trocas/dia.
- Trocar em dias que não sejam "amanhã".
