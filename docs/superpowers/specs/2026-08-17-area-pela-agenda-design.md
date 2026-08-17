# Item 36, fatia 2 — ver o estudo e corrigir a ÁREA pela `/agenda`

**Data:** 2026-08-17
**Base:** `origin/main` = `aeabced`
**Branch:** `feat/area-pela-agenda`

## O problema

O estudo de **2026-08-10** foi subido à mão antes do deploy da detecção automática de
área. Saiu com **"MEUS ESTUDOS"** na capa do PDF e **segue assim no portal até hoje**: a
página dele vive em `/artigos/meus-estudos/2026-08-10` e o portal mostra uma aba
"MEUS ESTUDOS" só pra ele.

A [fatia 1](2026-08-10-area-no-revisar-design.md) (o `<select>` de área no `/revisar` das
18h) resolveu o caso "amanhã" — de propósito não alcança estudo já enviado, porque depois
do envio o PDF está entregue e o `digests` já foi escrito. **Esta fatia é o retroativo.**

Pedido do Diego (2026-08-10): *"da pra fazer na area da agenda tbm, eu poder ver o estudo
por ali seria melhor"*. A `/agenda` é onde ele olha todo dia; a `/curadoria` é o poço de
estudos antes de agendar.

## Achados da exploração que mudaram o desenho

### 1. A janela da agenda não alcançava o estudo de 10/08

`agenda_plan.semanas_do_mes` começa na **segunda-feira da semana de hoje**
(`agenda_plan.py:48`) e vai 4 semanas pra frente. Numa segunda-feira — como 2026-08-17,
o dia em que este spec foi escrito — a agenda tem **zero dias passados**, e 10/08 fica
fora do alcance.

Sem este achado, a tarefa inteira teria sido construída num lugar que não chega no
problema que a motivou. Conserto: `semanas_atras=1`.

### 2. Corrigir a área move a linha de lugar — e isso é seguro

A chave primária de `digests` é `(data, tema_slug)` (`db.py:116`) e a URL do portal é
`/artigos/<tema_slug>/<data>`. Trocar a área **muda a chave**: a linha sai de
`meus-estudos/2026-08-10` e vai pra `obesidade/2026-08-10`.

Duas conferências que tornam isso aceitável:

- **Nenhum link profundo desses é enviado.** A busca por `ARTIGOS_URL` acha só a raiz e
  rotas de conta (`/minha`, `/primeiro-acesso`, `/criar-senha`, `/ferramentas/<slug>`).
  A mensagem diária não carrega o link da edição, então nada que já saiu no WhatsApp
  quebra.
- **A aba fantasma desaparece sozinha.** `db.listar_temas` monta as abas do portal com um
  `GROUP BY tema_slug` sobre o próprio `digests` (`db.py:1847`). Esvaziado o slug, a aba
  "MEUS ESTUDOS" sai da lista sem limpeza manual.

### 3. `tema` e `tema_slug` têm que andar juntos

O portal filtra por `tema_slug` (`listar_por_tema`), mas `db.listar_excluidos` filtra por
`tema` (`db.py:2096`) e o corpus do dossiê agrupa por tema. Atualizar só um dos dois faz
as visões discordarem **em silêncio** — o estudo apareceria na aba nova e continuaria
contando como do tema velho na memória.

### 4. Os campos do painel já vêm do banco

`db.digest_do_dia` faz `SELECT *` (`db.py:1839`), então resumo/fonte/DOI já estão na mão.
Hoje `serve._slot_view` (`serve.py:509`) joga fora e copia só tema/título. Não há consulta
nova a fazer — só parar de descartar.

## Decisões do Diego (2026-08-17)

1. **Painel dentro do próprio card**, acordeão `<details>` como a Reserva por tema — não
   link pro portal (que exige sessão de assinante e cairia no `/entrar` quando ele abre a
   agenda por `?token=`), nem reuso da prévia do `/revisar` (que lê o **rascunho** do dia,
   arquivo que pode não existir mais pra dia passado).
2. **Só dias passados.** Dia futuro continua como hoje; amanhã já tem o `/revisar` das
   18h. Corrigir área de dia futuro pela reserva é a fatia 3.
3. **A janela da agenda ganha a semana anterior** (1 pra trás + as 4 de hoje), em vez de
   navegação `◀ ▶` por período — que alcançaria julho, mas mexeria num ponto delicado: o
   GET da `/agenda` chama `materializar_agenda()` em toda visita.
4. **Mover a linha do `digests`**, não coluna `area_corrigida` paralela. Uma coluna nova
   deixaria `tema_slug` — a chave, a aba do portal e o agrupamento do dossiê — dizendo
   "meus-estudos", ou seja, o sintoma visível continuaria de pé.

## O que muda na tela

```
AGENDA

── Semana passada ──────────────
┌─ SEG · 10/08 ────── enviado ─┐
│ MEUS ESTUDOS                 │
│ Tirzepatida e massa magra…   │
│ ▾ ver o estudo               │
├──────────────────────────────┤
│ Revista: JAMA · 2026-07      │
│ DOI: 10.1001/jama.2026.123   │
│ Resumo: ensaio randomizado…  │
│                              │
│ Área: [ MEUS ESTUDOS    ▾ ]  │
│       [ Salvar ]             │
│ O PDF que já foi enviado não │
│ muda — isto corrige a página │
│ do portal.                   │
└──────────────────────────────┘

── Semana 1 (atual) ────────────
SEG · 17/08   enviado   ▾ ver o estudo    ← hoje já saiu às 08h
TER · 18/08   📌 Fixar  💤 Folga  ⇄ Trocar…   (como hoje)
```

Regras da tela:

- **Hoje conta como passado.** `serve._slot_view` corta em `d < amanhã` (`serve.py:508`),
  então o estudo que saiu às 08h de hoje já lê do `digests` e também ganha painel. É o
  comportamento certo: o PDF de hoje já foi entregue, e o que ainda dá pra consertar é a
  página do portal.
- Dia passado **sem** digest (folga, ou dia que não teve envio) fica como hoje, sem
  painel — não há o que mostrar nem o que corrigir.
- O `<select>` lista `area_estudo.areas()`. Quando a área atual **não** é uma dessas
  chaves — o caso "MEUS ESTUDOS" — ela entra como opção já selecionada. Sem isso o form
  mandaria uma área diferente sem o curador ter pedido nada.
- A frase sobre o PDF é literal e não promete mais do que entrega. Aviso que promete
  efeito que não acontece foi o erro pego na revisão do bloco fixado do dossiê.

## Arquitetura

| Onde | O quê |
|---|---|
| `area_estudo.aplicar_no_digest(data, tema_slug, area)` | irmão do `aplicar_no_rascunho`; valida pelo `valida()` que já existe e devolve o que aconteceu |
| `db.mover_digest_tema(data, tema_slug, tema_novo)` | `UPDATE` de `tema` **e** `tema_slug`; recusa quando o destino já existe |
| `agenda_plan.semanas_do_mes(..., semanas_atras=0)` | parâmetro novo; default `0` preserva todos os chamadores atuais |
| `serve.py` POST `/agenda` | ação `corrigir_area_digest`, ao lado de fixar/pular/mover/rematerializar |
| `site_web._slot_card` | o painel do dia passado |

`area_estudo.py` continua o dono único da escrita de área — foi feito assim na fatia 1
justamente pra receber este irmão (e o `aplicar_na_reserva` da fatia 3).

`db.mover_digest_tema` espelha `db.excluir_digest(tema_slug, data, escopo)`
(`db.py:2078`), que já é o jeito da casa de mexer numa linha de digest.

## Fluxo

**GET `/agenda`** → janela com `semanas_atras=1` → dia passado lê `digest_do_dia` (já lê)
e `_slot_view` passa a carregar `resumo`, `fonte`, `doi`, `data` do estudo → `_slot_card`
monta o painel.

**POST `/agenda`** com `acao=corrigir_area_digest` → valida token → `aplicar_no_digest` →
mensagem → volta pra agenda.

Efeitos da correção, em ordem de quando aparecem:

1. **Na hora:** a página do estudo passa a viver em `/artigos/<slug-novo>/<data>` e a
   listagem da aba nova o inclui.
2. **Na hora:** a aba antiga desaparece do portal se ficou vazia (`listar_temas` conta do
   `digests`).
3. **Na próxima reconstrução do dossiê (🧠):** o estudo passa a alimentar a memória do
   tema certo — `dossie.corpus_do_tema` lê `listar_por_tema(slug)`.
4. **Nunca:** o PDF já entregue no WhatsApp.

## Erros

| Caso | Comportamento |
|---|---|
| Área que não é chave do `temas_config` | no-op (o `valida` já falha fechado) + mensagem "não reconheci essa área" |
| Já existe estudo naquele dia na área de destino (colisão de chave) | **recusa**, nomeando o estudo que ocupa o dia — nunca sobrescreve |
| Área igual à atual | no-op silencioso, sem escrita nem mensagem de erro |
| Dia sem digest | não renderiza painel; POST forjado responde que não achou o estudo |
| Banco fora do ar | mensagem na tela; a agenda continua abrindo (o GET já engole falha do `materializar`) |

## Vem junto: a regressão de status

Anotada na fatia 1 e deixada pra esta: `draft_store.aplicar()` grava `APPROVED`/`EDITED`
sem olhar o status atual, então abrir um link velho do `/revisar` de um dia já enviado
volta o status pra aprovado e o `/admin` passa a mostrar **"✅ aprovado" em vez de
"📤 enviado"**. Conserto: `aplicar` preserva `SENT`.

Fica nesta fatia porque é a mesma classe de problema — estado de estudo já enviado sendo
sobrescrito por uma tela que não sabe que ele saiu.

## Testes

Comportamento com banco de verdade, não `assertIn` em código-fonte (a lição das duas
mutações sobreviventes do `tipo='corpus'`: o mesmo trecho aparece duas vezes no arquivo e
o grep passa com uma quebrada).

- **`mover_digest_tema`**: a linha sai do slug velho e aparece no novo com `tema` e
  `tema_slug` coerentes; `listar_por_tema` do slug antigo fica vazio; `listar_temas` para
  de listar o slug esvaziado; colisão no destino não escreve nada.
- **`aplicar_no_digest`**: move; recusa área fora do config; recusa colisão; no-op quando
  a área é a mesma.
- **`semanas_do_mes`**: `semanas_atras=1` inclui a semana anterior na ordem certa; o
  default `0` devolve exatamente o que devolvia antes (proteção dos chamadores atuais).
- **Rota**: POST corrige e a mensagem volta; sem token dá 403; dia sem digest não explode.
- **Tela**: o `<select>` traz a área atual mesmo fora do config (o caso "MEUS ESTUDOS");
  dia passado sem estudo não ganha painel. Âncoras com a **frase inteira**, nunca trecho
  curto — sete asserções falsas por âncora curta na tela de custos.

Provar por mutação, no mínimo:

1. Tirar o `tema` do `UPDATE` (deixando só `tema_slug`) tem que derrubar teste.
2. Remover a guarda de colisão tem que derrubar teste.
3. Trocar o default de `semanas_atras` pra `1` tem que derrubar teste de chamador atual.

## Fora de escopo

- Corrigir área de dia **futuro** pela agenda (fatia 3, via reserva).
- Alcançar estudo de mais de duas semanas atrás. Se aparecer a necessidade, o lugar
  natural é a lista **"Estudos lidos"** que já existe na aba 🧠 (`site_web.py:1549`),
  agrupada por tema e sem limite de data.
- Editar título, resumo ou qualquer outro campo do estudo enviado. Só área.
- Regerar o PDF de um dia passado.
