# Séries de estudos (Fase 2 — "furo") — Design

**Data:** 2026-07-28
**Status:** aprovado (brainstorming) → aguardando plano · **DEPENDE da Fase 1 (Tags)**
**Branch:** worktree-tags-series (base b5652b2)
**Backlog:** item 8

## Objetivo

Deixar o Diego montar **séries temáticas ordenadas** (ex.: "Série GLP1" com 5 estudos) que **ocupam N dias úteis seguidos** da agenda (o "furo" que toma a semana), no lugar da rotação normal. Monta a série a partir do **estoque** (busca por **tag** — Fase 1) + upload de estudo novo. Ativa escolhendo a **data de início**. Cada estudo da série passa pela **revisão das 18h** normal.

## Decisões (brainstorming 2026-07-28)

- **Fonte = híbrido:** puxa do estoque (reserva/candidatos/clássicos via `buscar_por_tag`) + "➕ Adicionar meu estudo" (reusa o fluxo que já joga na reserva).
- **Ocupação = bloco/furo:** a série toma os próximos N dias úteis livres EM ORDEM; a rotação normal preenche o resto.
- **Uma série ATIVA por vez** (pode ter várias salvas como rascunho).
- **Página `/series` própria** (não aba da curadoria).
- **Data de início escolhida** na ativação.
- **Gate mantido:** cada dia da série flui pelo pipeline normal (preview 18h → revisar/aprovar → envio 08h).

## Descobertas que moldam a implementação (reuso máximo)

- `agenda_plan.dias_uteis_desde(inicio, n, dias_envio)` → próximos n dias úteis (YYYY-MM-DD).
- `db.agenda_upsert(data, tipo, ref_id, payload, tema, titulo, fixado)` + `db.marcar_reserva_agendado`/`marcar_candidato_agendado` — **o mesmo mecanismo do Item 23** pra gravar um slot e consumir o estudo. Clássico: `agenda_upsert(tipo="classico")` (reusável, não consome).
- `db.agenda_slot(data)` / `agenda_listar` — pra saber se um dia está fixado/pulado/preenchido.
- `daily.preparar_18h` → `agenda_plan.classificar_slot` → `_preparar_da_reserva`/`_preparar_de_candidato`/`_preparar_de_classico` — o preparo já lê o slot e monta o rascunho. **A série só precisa gravar os slots**; o resto do pipeline (preview, gate, envio) já funciona.
- `buscar_por_tag(termo)` (Fase 1) — a busca do montador.

## Dados (2 tabelas novas)

- `series`: `id, nome, status ('rascunho'|'ativa'|'concluida'), data_inicio, criado_em, ativada_em`.
- `serie_itens`: `id, serie_id, ordem, ref_tipo ('reserva'|'candidato'|'classico'), ref_id, enviado (0/1)`. Aponta pro estoque — não duplica o estudo.

## Página `/series` (o montador)

- **Lista** as séries (rascunhos + a ativa/concluídas) com status.
- **Montar/editar** (rascunho): caixa de **busca por tag** → resultados do estoque com "➕ adicionar"; a **lista da série** com **ordenar (↑/↓)** e remover; **"➕ Adicionar meu estudo"** (reusa `adicionar_meu_estudo` → reserva → entra na série). Salvar.
- **Ativar:** escolhe a **data de início** (dia útil, futuro) → só permite se **nenhuma outra série ativa**.
- Admin-gated (token OU sessão admin), como as outras telas admin; nav.

## Orquestração — ativar a série

`series.ativar_serie(serie_id, data_inicio)`:
1. Valida: existe, é rascunho, não há outra ativa, `data_inicio` é dia útil futuro.
2. Calcula os **próximos N dias úteis LIVRES** a partir de `data_inicio` (N = nº de itens): pula dias **fixados** e **pulados** (usa o próximo livre). Não sobrescreve slots fixados.
3. Pra cada (dia, item) em ordem: `agenda_upsert(dia, tipo=item.ref_tipo, ref_id=item.ref_id, tema, titulo)` + consome (`marcar_reserva_agendado`/`marcar_candidato_agendado`; clássico não consome). Guard try/except com aviso ao curador (igual Item 23).
4. `series.status='ativa'`, `ativada_em=now`.
5. Cada dia depois: `preparar_18h` monta o rascunho do slot (reuso) → curador revisa às 18h → envia 08h. **Concluir:** a série vira `status='concluida'` quando **todos os `serie_itens` estão `enviado`** OU o **último dia colocado já passou** (`< hoje`) — checado ao abrir `/series` (e/ou num passo leve da rotina diária). Isso **libera ativar outra** (a trava "uma ativa" olha `status='ativa'`). Depois disso a rotação normal volta sozinha, pois os dias seguintes ficam livres.

**Borda "dia já preparado":** se `data_inicio` cair num dia cujo rascunho **já foi montado** (preview das 18h já rodou), gravar o slot não troca o rascunho pronto (mesma limitação do Item 23). Por isso: **validar `data_inicio` ≥ o próximo dia ainda não preparado**; pra o 1º dia já preparado, usar o **🔁 Trocar (Item 23)**.

## Guarda-corpos

- Só **uma ativa**: `ativar_serie` recusa se já há série `ativa`.
- Respeita **fixado/pulado** (não sobrescreve fixado; pula pulado).
- Ativação é **fail-safe** (try/except + aviso ao curador; se um `agenda_upsert` falha, avisa e não deixa estado meio-feito silencioso).
- **Gate 18h intacto** — a série nunca envia sem a revisão.
- Reordenar/editar **depois de ativar** = fora do MVP (a série já está gravada na agenda; mudar exige desativar/regravar).

## Testes (TDD)

- `db`: cria series/serie_itens; CRUD (criar, add item ordenado, listar, obter, status).
- `series.ativar_serie` (db + agenda injetados): grava os N itens nos N dias úteis livres em ordem (`agenda_upsert` com ref certo + consumo); pula fixado/pulado; recusa 2ª ativa; valida data_inicio.
- Borda: data_inicio em dia já preparado → recusa/avisa.
- `pagina_series`: renderiza lista + montador + form de ativar (escape).
- `serve` `/series`: GET renderiza; POST (criar/add/remover/reordenar/ativar) roteia.
- **Regressão:** materializar/rotação normal intactos; suíte verde.

## Critérios de aceite

- [ ] Monto uma série buscando por tag + upload, ordeno, salvo.
- [ ] Ativo com data de início → os estudos ocupam os N dias úteis seguidos, em ordem, na agenda.
- [ ] Cada dia aparece no preview das 18h pra eu revisar; envia 08h.
- [ ] Só uma série ativa por vez; fixados/pulados respeitados.
- [ ] Ao acabar, a rotação normal volta sozinha. Suíte verde.

## Arquivos

- `app/db.py` (tabelas + CRUD series), `app/series.py` (novo — orquestração), `app/site_web.py` (`pagina_series`), `app/serve.py` (rotas `/series`), `app/tests/test_series.py` (novo). Usa `buscar_por_tag` (Fase 1).

## Fora de escopo

- Várias séries ativas; intercalação com a rotação; reordenar/editar após ativar; série automática (a IA montar sozinha). Tudo backlog.
