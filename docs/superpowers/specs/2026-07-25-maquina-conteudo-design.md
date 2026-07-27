# Máquina de conteúdo — Design (varredura automática + frescor + nunca faltar)

**Data:** 2026-07-25 · **Host:** `artigos.` (assinatura) · Relacionado a [[horario-envio-assinante]], [[guard-troca-slot]], ao item 8 do backlog (séries) e ao item 16 (acurácia da varredura).
**Status:** Design aprovado (brainstorming) — aguardando revisão do spec.

## Contexto

O item 17 do backlog é o **coração do app**: religar o pipeline automático de conteúdo com **frescor**, sem quebrar o selo "revisado por médico".

- **Como o Diego imaginava:** varredura por área; se achar estudo bom, já resumir e enviar destacando "saiu recente"; extras vão pra fila.
- **Como está hoje (código):** a varredura (`curadoria.rodar_varredura`) é **manual** (botão/CLI); varre os 5 temas → candidatos triados (Haiku, score 0–10, `triage.triar`) → **curadoria humana** (`gerar_selecionados`) gera o resumo (Sonnet) → **reserva**; a **rotação diária** (`daily.materializar_agenda` + `agenda_plan.planejar_agenda`) manda 1/dia do **estoque**, **sem** destaque de recência e **sem** varredura agendada. Fallback quando não há nada = avisa curador e não envia nada (`_preparar_da_reserva` → "📭 Nada preparado").
- **Gap:** não há varredura automática, não há noção de "fresco", e o fallback pode deixar o assinante sem estudo.

## Objetivo

Religar o pipeline automático com **frescor** e **nunca faltar**, mantendo o **preview das 18h como gate humano universal** (o assinante nunca recebe algo que o Diego não pôde revisar). Reusa `preparar_18h`/`enviar_slot` inteiros.

## Decisões centrais (Diego, 2026-07-25)

1. **Aprovação implícita (gate universal).** O preview das 18h continua sendo o único portão: o Diego **sempre** revisa o estudo de amanhã (fresco ou não); silêncio = envia às 08h. Nada é 100% automático sem review.
2. **Varredura geral semanal, domingo de manhã.** 1x/semana varre as 5 áreas (reusa `rodar_varredura`); roda **domingo de manhã** pra o preparo das 18h de domingo já ter candidato pra segunda.
3. **Frescor = ≤30 dias**, medido pela **data de publicação do paper no momento do envio** (nunca mente). Selo único **"🆕 Estudo recente"** quando ≤30d; acima disso, envia sem selo.
4. **Fila priorizada, sem piso de qualidade.** Todo estudo que passa a triagem (ENTRA) entra, por tema; **score = posição na fila** (o melhor sai primeiro); descarta só a **cauda** no excesso, via teto por tema (`curadoria.CAPS`, já existe). Resumo gerado **na hora (18h)** só pro estudo escolhido do dia — candidatos ficam baratos (só triagem + pergunta) até subir.
5. **Fresco fura a fila do tema, mas espera o dia do tema.** Inverte o `_rank` atual (que hoje prefere reserva sobre fila): fresco (≤30d) vai pra frente da fila **do tema dele**. Respeita a rotação/variedade — o fresco espera o dia do tema no rodízio (com 30d a espera de ~até 5 dias não estoura a janela).
6. **Nunca faltar (pirâmide):** `🆕 Fresco (≤30d) → 📚 Reserva → 🏛️ Clássicos → ↔️ Empréstimo entre temas`. O ebook sai de cena como fallback.
7. **Clássicos = banco grande evergreen por tema, construção híbrida.** Scan por **nº de citações** (janela ~10 anos) propõe os estudos-marco → Diego aprova na Curadoria → gera resumo → banca. Reusáveis por ciclo (mais antigo primeiro, com piso de meses). **Selecionáveis à mão** (o Diego pode mandar um clássico específico / montar séries — orquestração de séries fica no item 8). A curadoria manual atual **coexiste**.

## Modelo: pirâmide de fontes (nunca zera)

```
Dia de envio (tema T do rodízio), em ordem de prioridade:

  1. 🆕 FRESCO   — candidato/reserva do tema T, publicado ≤30d, por score  → selo "Estudo recente"
  2. 📚 RESERVA  — estoque do tema T já curado (>30d), por score            → sem selo
  3. 🏛️ CLÁSSICO — banco evergreen do tema T (não enviado no ciclo), por citações/score → sem selo
  4. ↔️ EMPRÉSTIMO — se T secar em 1–3, o melhor clássico de OUTRO tema
                     (na prática, os gigantes Obesidade/Hormonal), enviado no tema REAL dele
```

A camada 4 cai fora naturalmente do planejador: `planejar_agenda` escolhe entre **todos** os candidatos (rotação é só desempate), então quando o tema do dia não tem candidato, o melhor de outro tema é pego — desde que os clássicos estejam no pool. Nunca há dia vazio enquanto o banco de clássicos tiver item.

## Arquitetura (por arquivo)

### 1. `sources.py` — citações no OpenAlex

- `_openalex_normalizado` passa a extrair `cited_by_count` (campo nativo do OpenAlex) → `"citacoes": w.get("cited_by_count", 0)` no dict normalizado. (Europe PMC também tem `citedByCount`, mas OpenAlex é a fonte primária de citações aqui.)
- `search_all` propaga `citacoes` (default 0 quando o banco não informa).

### 2. `curadoria.py` — varredura de clássicos + auto-fila

- **`varrer_classicos(caps=None, buscar_fn=None, triar_fn=None, anos=10)`** — por tema, busca numa janela ampla (`desde = hoje - anos`) e ordena por **citações desc** (em vez de score de recência); triagem normal (ENTRA/LIXO) pra cortar ruído; top-N por tema. Retorna candidatos marcados `origem="classico"`. Injetável (teste sem rede), espelhando `varrer`.
- **`rodar_varredura_classicos()`** — orquestra `varrer_classicos` + `gerar_perguntas` + `db.salvar_candidatos(..., tipo="classico")`. Alimenta a fila de aprovação de clássicos (não a reserva diretamente).
- **`gerar_selecionados`** ganha um parâmetro de destino: os selecionados `origem="classico"` vão pro **banco de clássicos** (`db.salvar_classico`), os demais pra `reserva` (comportamento de hoje). Reusa `gerar_resumo` (Sonnet) — mesma qualidade.
- `CAPS` (teto por tema) segue como o mecanismo de "descartar a cauda no excesso" da decisão 4.

### 3. `db.py` — banco de clássicos + candidatos como fonte da agenda

- **Tabela nova `classicos`** (evergreen, **não** consumida no envio):
  ```sql
  CREATE TABLE IF NOT EXISTS classicos (
      id TEXT PRIMARY KEY, tema TEXT, titulo_pt TEXT, resumo TEXT,
      gancho TEXT, grafico TEXT, doi TEXT, fonte TEXT, url TEXT, data TEXT,
      citacoes INTEGER DEFAULT 0, ultimo_envio TEXT, criado_em TEXT
  );
  ```
  Entra em `_TABELAS` (RLS). Helpers:
  - `salvar_classico(dados) -> id`
  - `listar_classicos(tema=None, elegiveis=True)` — quando `elegiveis`, filtra por **ciclo**: `ultimo_envio` nulo OU mais antigo que o piso de reuso (`config.CLASSICO_REUSO_MESES`, default 6), ordenado por `ultimo_envio` asc (mais antigo/nunca-enviado primeiro) e `citacoes` desc.
  - `marcar_classico_enviado(id, data)` — seta `ultimo_envio` (não deleta — reusável).
- **Candidatos como fonte da agenda (auto, sem gate manual):** `listar_candidatos` ganha um modo que devolve **todos os candidatos ENTRA** (status `novo`, `tipo` normal — não clássico) ainda **não** resumidos nem selecionados à mão (com `data` e `score`) pra alimentar a agenda como itens "fila" (resumo JIT). É a decisão 4 ("quero todos os artigos"): não há aprovação prévia — o gate é o preview das 18h. A seleção manual continua sendo o caminho **alternativo** (candidato → `gerar_selecionados` → reserva pré-gerada). Candidato agendado é marcado (`status="agendado"`) pra não ser double-booked, no mesmo espírito do `marcar_reserva_agendado`.

### 4. `agenda_plan.py` — `_rank` fresh-first + clássico como piso + empréstimo

Novo `_rank` (tupla, mais significativo primeiro; maior = melhor):

```python
def _rank(cand, preferido, prev):
    return (
        1 if cand["tema"] != prev else 0,        # variedade (regra forte, como hoje)
        1 if cand["tema"] == preferido else 0,   # rotação = tema do dia (guia mais forte que antes)
        1 if cand.get("fresco") else 0,          # fresh-first (≤30d pela data de publicação)
        0 if cand.get("classico") else 1,        # clássico é PISO (só quando não há melhor)
        cand.get("score", 0),                    # qualidade puxa pra frente
    )
```

- `fresco`/`classico`/`score` são anotados no candidato ao montar o pool (ver §5).
- **Empréstimo entre temas** é emergente: quando o tema `preferido` não tem candidato, `max(_rank)` cai no melhor de outro tema (os clássicos dos gigantes dominam o pool de piso). A regra de variedade evita repetir o tema do dia anterior.
- `classificar_slot`/`planejar_agenda`/`precisa_reabastecer` seguem, só recebendo o pool anotado.

### 5. `daily.py` — pool anotado, selo de recência, JIT

- **`_e_fresco(data_pub, ref=None) -> bool`** — `True` se `data_pub` (YYYY-MM-DD) está a ≤ `config.FRESCO_DIAS` (default **30**) de `ref` (hoje). Tolera data vazia/parcial (retorna False). É a **fonte única** do frescor — usada no rank e no selo, sempre contra a data do envio.
- **`materializar_agenda`** monta o pool a partir de: reserva pronta + **candidatos** (auto, via `db.listar_candidatos`) + **clássicos elegíveis** (`db.listar_classicos`). Cada item recebe `fresco = _e_fresco(item["data"])`, `classico = (origem/tabela)`, `score`. Candidato/clássico entram como `tipo="fila"` (payload = artigo cru → resumo JIT em `_preparar_de_artigo`); reserva segue `tipo="reserva"`.
- **`preparar_18h`** não muda de forma: pega o slot de amanhã, gera/carrega o resumo (JIT p/ fila, pronto p/ reserva), manda o preview 18h com link `/revisar`. **Fallback em cascata** já existente (`_preparar_fallback`) segue como rede de segurança se o JIT falhar.
- **Selo de recência:** `montar_texto_resumo(titulo, resumo, tmeta, fresco=False)` prefixa `🆕 *Estudo recente*` acima do badge do tema quando `fresco`. O envio (`_montar_ctx`/`_enviar_estudo_para`) calcula `fresco = _e_fresco(art["data"])` **no dia do envio** e repassa. Assim o selo nunca mente, mesmo que o item tenha esperado dias na fila.
- **`_finalizar_dia`** também marca clássico enviado (`db.marcar_classico_enviado`) quando a origem for clássico, além do já existente `marcar_reserva_enviado`.
- **Fallback ebook removido:** `_preparar_fallback` não recorre mais ao ebook; a pirâmide (fresco→reserva→clássico→empréstimo) é a rede. Se **tudo** estiver vazio (banco de clássicos ainda não semeado), mantém o aviso ao curador de hoje.

### 6. `serve.py` — cron domingo de manhã + scan de clássicos

- **Varredura semanal (domingo AM):** o `agendador` ganha uma tarefa semanal guardada por dia-da-semana (domingo) + hora (`config.HORA_VARREDURA`, default 07h), que roda `curadoria.rodar_varredura()`. Idempotente por semana (marcador tipo `varredura_semana` pra sobreviver a restart), no espírito dos marcadores de `envios_slot`. Fail-safe: erro na varredura loga e não derruba o agendador.
- **Scan de clássicos:** botão/rota na Curadoria dispara `curadoria.rodar_varredura_classicos()` (on-demand — construção do banco não precisa de cron; YAGNI). A superfície de aprovação de clássicos entra na tela de Curadoria (**layout a confirmar com o Diego na implementação** — [[feedback-nao-supor-landing]]; reusa as abas por tema que já existem no branch pages-refresh).

## Frescor — definição e selo (resumo)

| Idade do paper no envio | Prioridade na fila | Selo |
|---|---|---|
| ≤ 30 dias | fura pra frente do tema (por score) | `🆕 Estudo recente` |
| > 30 dias (reserva/candidato) | fila normal por score | — |
| clássico (evergreen) | piso (só quando não há melhor) | — |

## Comportamento (matriz)

| Situação | Resultado |
|---|---|
| Fresco ≤30d do tema do dia | sai no dia do tema, resumo JIT, preview 18h, selo "Estudo recente" |
| Fresco de outro tema | espera o dia daquele tema (variedade preservada); selo se ainda ≤30d no envio |
| Sem fresco, tem reserva do tema | envia reserva, sem selo |
| Sem fresco nem reserva do tema, tem clássico do tema | envia clássico do tema, sem selo |
| Tema menor seco em tudo | empréstimo: melhor clássico de tema gigante, no tema real dele |
| >1 fresco bom do mesmo tema | melhor sai; extras ficam na fila (podem virar reserva quando passarem de 30d) |
| Estoque + clássicos vazios (banco não semeado) | aviso ao curador (comportamento de hoje) — some quando o banco de clássicos existir |
| Diego edita/veta no preview 18h | o gate humano manda, como hoje (`/revisar`) |

## Erros & bordas

- **Data de publicação ausente/parcial:** `_e_fresco` retorna False (nunca marca selo sem certeza).
- **JIT de resumo falha (fila/candidato):** cai no `_preparar_fallback` (reserva → clássico), como o `preparar_18h` já faz no `except`. PDF já é fail-safe (try/except + retry).
- **Corrida do cron semanal × restart:** marcador `varredura_semana` (INSERT ON CONFLICT) garante 1 varredura por semana ISO.
- **Clássico nunca "acaba":** `marcar_classico_enviado` só seta `ultimo_envio` (não deleta); o ciclo (`listar_classicos elegiveis`) evita repetir antes do piso de meses — por isso o banco precisa ser grande (decisão 7).
- **Candidato double-book:** marcar `status="agendado"` ao materializar, e reconciliar órfãos (self-healing) como o `materializar_agenda` já faz com reserva.
- **Fresco que envelheceu na fila:** se passar de 30d antes de sair, perde o selo automaticamente (calculado no envio) e vira reserva comum — sem intervenção.

## Testes (unittest, `cd app && python3 -m unittest discover -s tests`)

- **`agenda_plan._rank`:** fresco > reserva-recente > clássico; variedade continua forte (não repete tema do dia anterior); rotação como guia; empréstimo entre temas quando o tema do dia está seco.
- **`daily._e_fresco`:** borda em 30 dias (29=fresco, 31=não), data vazia/parcial = False, sempre contra a data do envio.
- **`daily.montar_texto_resumo`:** prefixa "🆕 Estudo recente" só quando `fresco=True`; sem selo caso contrário.
- **pirâmide:** com/sem fresco/reserva/clássico do tema → escolhe a camada certa; tudo vazio no tema → empréstimo do gigante.
- **`curadoria.varrer_classicos`:** ordena por citações desc (mock `buscar_fn` com `citacoes`), triagem corta LIXO, top-N por tema, `origem="classico"`.
- **`db` clássicos:** `salvar_classico`/`listar_classicos` (ciclo: nunca-enviado e mais-antigo primeiro; respeita piso de reuso); `marcar_classico_enviado` seta `ultimo_envio` sem deletar.
- **cron semanal:** roda domingo na hora certa, idempotente por semana (mock relógio + marcador).
- **`sources._openalex_normalizado`:** extrai `cited_by_count` → `citacoes`.
- **Regressão:** testes atuais de `enviar_slot`, `preparar_18h`, `materializar_agenda`, `guard-troca-slot` continuam passando.

## Fora de escopo (YAGNI)

- **Orquestração de séries temáticas** (item 8) — aqui só garantimos que clássicos sejam **selecionáveis**; a sequência/ponteiro de série é spec própria.
- **Empreendedorismo aos domingos** (item 9) e **envio diário 7d** (item 10) — o cron semanal roda domingo, mas o **envio** segue seg–sex.
- **Re-check de áudio TTS** (item 1) e **tuning de query por tema** (item 16) — separados.
- **Mudança no modelo de pagamento / preços** — nada aqui.
- **Redesign visual da Curadoria** — a aprovação de clássicos reusa as abas existentes; layout novo é outro trabalho.
