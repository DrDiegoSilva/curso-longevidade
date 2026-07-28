# Tags de estudos (Fase 1 — pré-requisito das Séries) — Design

**Data:** 2026-07-28
**Status:** aprovado (brainstorming) → aguardando plano
**Branch:** worktree-tags-series (base b5652b2 = main com Item 23 + curadoria + agenda-tema)
**Backlog:** item 8 (séries) — Fase 1 · liga com item 16 (acurácia da varredura)

## Objetivo

Etiquetar cada estudo com **tags livres geradas pela IA** (moléculas, intervenções, tópico central), pra permitir **busca por tópico fino** — ex.: digitar "retatrutida" e achar todos os estudos sobre isso no estoque. Hoje os estudos só têm os 5 temas amplos (Obesidade, Hormonal…), então "todos de retatrutida" não é filtrável. As tags viabilizam o montador de **Séries** (Fase 2).

## Decisões (brainstorming 2026-07-28)

- **Tags livres pela IA** (não vocabulário controlado, não híbrido). A IA lista moléculas/intervenções/tópico central, **minúsculas/PT**, priorizando o **nome comum** da molécula (mitiga "retatrutida" vs "Retatrutide" vs "LY3437943").
- **Embutidas na triagem que já roda** (Haiku, `triage.triar`, por estudo na varredura + no upload) → custo marginal ~zero (mesma chamada, só mais tokens de saída).
- **Storage:** coluna `tags` (JSON array de string) nas 3 tabelas de estudo. Tags geradas no candidato **carregam** pra reserva/clássico quando promovido.
- **Backfill** dos estudos existentes sem tags (1x, idempotente, ~US$1-2 em Haiku).
- **Busca por substring** (case-insensitive) sobre as tags.

## Descobertas que moldam a implementação

- `triage.triar(artigos, tema, llm)` (`app/triage.py`) manda um batch e recebe JSON `[{"i":0,"classe":"ENTRA","score":8},…]` (`_prompt` linhas ~13-26, `_parse` ~28-49). É AQUI que a IA já olha cada estudo — o lugar natural pra pedir as tags no mesmo JSON.
- `db.salvar_candidatos` (`db.py:789`) faz `INSERT` com colunas `(id,tema,titulo,fonte,data,doi,url,abstract,pergunta,score,chave,citacoes,tipo,status,criado_em)`. Adicionar `tags` aqui.
- Migração idempotente já existe: `db._add_coluna(c, tabela, coluna, tipo)` (`db.py:236`), chamado no `init()`. Padrão pra adicionar `tags TEXT DEFAULT '[]'`.
- `curadoria.gerar_selecionados` (`curadoria.py:305`) copia campos do candidato → `salvar_reserva`/`salvar_classico` (roteia por `tipo`). Adicionar `tags` no `reg`.
- `curadoria.adicionar_meu_estudo` (`curadoria.py:224`) triага o upload (score) → `salvar_reserva`. A mesma triagem passa a devolver tags → grava.
- Tabelas: `curadoria_candidatos`, `reserva_resumos`, `classicos` (todas em `db.py`).

## Componentes / mudanças

1. `app/triage.py`
   - `_prompt`: pedir, por estudo ENTRA, uma lista curta de `tags` (moléculas/intervenções/tópico, minúsculas/PT, nome comum). JSON: `[{"i":0,"classe":"ENTRA","score":8,"tags":["retatrutida","glp1","perda de peso"]},…]`.
   - `_parse`: extrair `tags` (lista de string, minúsculas, deduplicada); ausente/inválida → `[]`. Anexar `a["tags"]` a cada artigo ENTRA.
   - `triar`: passa a devolver `tags` em cada artigo.
2. `app/db.py`
   - `init()`: `_add_coluna` de `tags TEXT DEFAULT '[]'` em `curadoria_candidatos`, `reserva_resumos`, `classicos`.
   - `salvar_candidatos`: incluir `tags` (JSON dump) no INSERT.
   - `salvar_reserva` / `salvar_classico`: incluir `tags` (JSON dump; default `[]`).
   - `listar_candidatos`/`listar_reserva`/`listar_classicos`: já fazem `SELECT *` → devolvem `tags` (string JSON; consumidor faz `json.loads`).
   - **nova** `buscar_por_tag(termo)`: varre as 3 tabelas e devolve estudos cuja `tags` contém o termo (substring, case-insensitive) — normaliza `{tipo,id,titulo,tema,tags}`. (Consumida pela Fase 2.)
3. `app/curadoria.py`
   - `gerar_selecionados`: `reg["tags"] = c.get("tags", "[]")` (carrega candidato→reserva/clássico).
   - `adicionar_meu_estudo`: pega `tags` do resultado da triagem → grava na reserva.
   - **nova** `backfill_tags(db_mod=None, triar_fn=None, limite=None)`: acha estudos das 3 tabelas com `tags` vazia/`[]`, roda a triagem-de-tags (batch por tema), grava. Idempotente (só os sem tags). Retorna quantos.
4. `app/serve.py`: ação admin `backfill_tags` na `/curadoria` (Ferramentas) → chama `curadoria.backfill_tags()`, mostra quantos.

## Guarda-corpos

- Tags sempre **minúsculas**, deduplicadas, lista de string; parse tolerante (JSON quebrado/ausente → `[]`).
- **Nunca derrubar a triagem** por causa das tags — se o campo `tags` faltar no retorno da IA, o estudo entra com `[]` (score/pergunta seguem normais).
- **Backfill idempotente:** só processa estudos com `tags` vazia (`[]`/NULL); reprocessar não duplica custo.
- Busca: substring case-insensitive; termo vazio → lista vazia (não despeja tudo).

## Testes (TDD, `app/tests/test_tags.py`)

- `triage._parse`: extrai `tags` (minúsculas, dedup); tags ausente → `[]`; JSON quebrado → `[]` sem crash.
- `triage.triar` (llm injetado): devolve `tags` por artigo.
- `db`: salva+lê `tags` nas 3 tabelas (candidato/reserva/clássico); default `[]` quando não passado.
- `db.buscar_por_tag`: acha por substring case-insensitive; cruza as 3 tabelas; exclui quem não tem a tag; termo vazio → `[]`.
- `curadoria.gerar_selecionados`: carrega `tags` do candidato pro `salvar_reserva`/`salvar_classico` (monkeypatch).
- `curadoria.backfill_tags`: só toca os sem tags; grava as geradas; idempotente (2ª rodada = 0). (triar_fn injetado, sem rede.)
- **Regressão:** score/pergunta/varredura seguem iguais; suíte inteira verde (baseline 729).

## Critérios de aceite

- [ ] Estudo novo (varredura ou upload) entra com `tags` preenchidas pela triagem.
- [ ] `tags` carrega candidato → reserva/clássico ao gerar.
- [ ] `backfill_tags` etiqueta o estoque antigo (idempotente); ação admin dispara.
- [ ] `buscar_por_tag("retatrutida")` acha os estudos das 3 tabelas com essa tag.
- [ ] Testes passam; suíte inteira verde.

## Arquivos

- `app/triage.py`, `app/db.py`, `app/curadoria.py`, `app/serve.py`, `app/tests/test_tags.py` (novo).

## Fora de escopo (Fase 2 / futuro)

- Página `/series` e a orquestração (Fase 2 — spec separada).
- Canonicalização/merge de sinônimos, vocabulário controlado, edição manual de tag, busca semântica.
- Mostrar/filtrar tags na Curadoria (só a busca programática `buscar_por_tag` no MVP).
