# Curadoria — reordenar o fluxo + piso de nota

**Data:** 2026-07-26
**Origem:** brainstorm com o Diego. Queixa inicial: "na tela de curadoria só tem botão salvar seleção" → virou "está tudo meio confuso, melhora o fluxo".

## Contexto: o que já é automático (e por que a tela confunde)

O ciclo de conteúdo **já roda sozinho** de ponta a ponta:

| Quando | O que acontece | Precisa do Diego? |
|---|---|---|
| Domingo ~06h | `daily.varredura_semanal` → `curadoria.rodar_varredura()`: busca Europe PMC, triagem Haiku (ENTRA/LIXO + score 0-10), pergunta clínica. **Não gera resumo.** | não |
| Todo dia 18h | `daily.preparar_18h`: materializa a agenda, escolhe o estudo de amanhã, **gera resumo + PDF + áudio** (`_preparar_de_candidato`), manda o link de revisão no WhatsApp | não |
| 18h, Diego | `/revisar/<token>`: aprovar · editar · não enviar. **Silêncio = envia** | **sim — é o único posto obrigatório** |
| 08h | `daily.enviar_slot` entrega aos assinantes | não |

A tela `/curadoria` **não é um passo desse ciclo**. Ela é um *override opcional*: o que o Diego marca vira resumo "curado" (reserva) e ganha da camada "crua" no `agenda_plan._tier` (curada=2 > crua=1 > clássico=0). Se ninguém abrir a tela, nada quebra.

O problema é que ela **se apresenta como dever de casa**: 6 cartões de estatística no topo, o botão "gerar resumos" *antes* da lista que alimenta ele, um painel grande de upload no meio do caminho, e a triagem — o trabalho de verdade — no rodapé, com o único botão visível sendo "💾 Salvar seleção".

Agrava: os CAPS (`curadoria.py:18`) deixam entrar **50 candidatos por semana** (Obesidade 20, Hormonal 9, Performance 8, Longevidade 7, Lipedema 6) para **5 envios**. O Diego cura um banco 10x maior do que o consumo.

## Objetivo

1. **Piso de nota** na varredura, com válvula pra tema seco — menos entulho chegando na tela.
2. **Reordenar a página** em torno do trabalho real (triar), com o estado do estoque em uma linha.
3. **Matar o "Salvar seleção"**: ações imediatas por item (priorizar / descartar).
4. **A geração dos selecionados vira automática** (cron noturno) — o Diego só marca.
5. **Separar clássicos dos candidatos de varredura** na tela (hoje se misturam — ver Bug 1).

### Bug 1 (corrigido de lambuja)

`serve.py:266` monta a lista com `db.listar_candidatos(status="novo") + db.listar_candidatos(status="selecionado")` — **sem filtrar `tipo`**. Como `curadoria.varrer_classicos()` grava candidatos com `tipo="classico"`, rodar o scan de clássicos hoje despejaria estudos de 10 anos atrás no meio da triagem semanal, indistinguíveis dos frescos. A separação em abas resolve.

## Não-objetivos (YAGNI)

- **Não** mexer nos CAPS — o piso já derruba o volume; um lever de cada vez pra dar pra medir.
- **Não** aplicar piso de nota nos clássicos (`varrer_classicos` ranqueia por **citações**, não por score).
- **Não** implementar "trocar o estudo" na tela de aprovação das 18h — é o **item 23 do backlog**, spec própria.
- **Não** implementar séries (item 8) nem tuning de query por tema (item 16).
- **Não** mexer no gate das 18h nem no envio das 08h.
- **Sem** framework JS: server-rendered com forms, como o resto do admin.
- **Sem** teto de geração por noite — depois do piso a lista é curta; se virar problema, vira follow-up.

## Componentes

### 1. Piso de nota — `config.py` + `curadoria.varrer()`

```python
# config.py
SCORE_PISO   = int(os.environ.get("DSCURSO_SCORE_PISO") or 6)     # nota mínima p/ entrar
MIN_POR_TEMA = int(os.environ.get("DSCURSO_MIN_POR_TEMA") or 3)   # válvula p/ tema seco
```

Em `curadoria.varrer()`, entre a triagem e o cap por tema:

```python
bons.sort(key=lambda x: x.get("score", 0), reverse=True)
acima = [a for a in bons if a.get("score", 0) >= piso]
if len(acima) < min_por_tema:
    acima = bons[:min_por_tema]      # tema seco: melhores mesmo abaixo do piso
# segue o dedup global + top(cap) que já existe
```

`piso`/`min_por_tema` entram como parâmetros com default vindo do `config` — mantém a função testável sem rede e sem monkeypatch de config.

**Semântica:** semana farta corta pesado; tema que não alcança `MIN_POR_TEMA` acima do piso afrouxa sozinho e entrega os melhores que tiver. Nunca zera um tema por causa do piso.

### 2. Geração automática — `serve.agendador`

Tarefa nova, isolada, com hora própria:

```python
# config.py
HORA_CURADORIA = int(os.environ.get("DSCURSO_HORA_CURADORIA") or 21)
```

```python
tarefas["gerar_curadoria"] = lambda: __import__("curadoria").gerar_selecionados()
horarios.append((config.HORA_CURADORIA, "gerar_curadoria"))
```

**Por que 21h e não dentro do `preparar_18h`:** o preparo das 18h é crítico (gera o estudo de amanhã e dispara o WhatsApp de revisão). Se 12 resumos Sonnet rodassem antes dele, atrasariam o posto do Diego. Tarefa separada, o `try/except` por tarefa do agendador já cobre falha.

**Idempotência:** `gerar_selecionados()` varre `status="selecionado"` e marca `"resumido"` ao fim de cada item — rodar duas vezes não duplica. Não precisa de ledger.

O botão manual "✍️ Gerar resumos dos selecionados" **sai da tela** (a ação POST `acao=gerar` **permanece** no `serve.py` como escape hatch de CLI/emergência, sem UI).

### 3. Ações por item — `serve.py` POST `/curadoria`

Substituem `acao=selecionar` (que some junto com o form de checkbox):

| Ação | Efeito | Função |
|---|---|---|
| `priorizar` | `novo` → `selecionado` | `db.marcar_candidatos([id], "selecionado")` |
| `descartar` | → `descartado` (some da lista pra sempre) | `db.marcar_candidatos([id], "descartado")` |
| `desfazer` | `selecionado` → `novo` | `db.marcar_candidatos([id], "novo")` |

`db.marcar_candidatos(ids, status)` já existe e aceita qualquer status. `descartado` já é respeitado: `listar_candidatos(status="novo")` não o retorna, e `daily.materializar_agenda` só puxa `status="novo"`.

**Redirect com âncora:** o handler devolve `/curadoria?token=…&aba=…&tema=…#cand-<id>` — a página volta no mesmo ponto da rolagem, sem JS.

### 4. Estado do estoque — `agenda_plan.estado_estoque()` (função pura)

```python
def estado_estoque(reserva_n, cand_n, classico_n, hoje, dias_envio, minimo):
    """Quantos envios o estoque cobre e até que dia. Puro (sem I/O).
    `hoje` é datetime (mesmo contrato de dias_uteis_desde); `dias_envio` é
    iterável de nomes de dia; retorna `ate` em YYYY-MM-DD ou None."""
    envios = reserva_n + cand_n + classico_n
    ate = dias_uteis_desde(hoje, envios, dias_envio)[-1] if envios else None
    return {"envios": envios, "ate": ate, "baixo": envios < minimo}
```

Contagens que a rota passa: `db.contar_reserva_pronto()` (só `pronto`),
`len(db.listar_candidatos(status="novo", tipo="varredura"))` e
`len(db.listar_classicos(elegiveis=True))` — as mesmas três que o
`daily.materializar_agenda` já soma, pra a faixa não divergir do que a agenda enxerga.

Mora em `agenda_plan.py` porque o módulo já é "planejamento puro sem I/O". O `minimo` entra por parâmetro (a rota passa `daily.ESTOQUE_MINIMO`, hoje 10) — mantém a pureza e reusa o mesmo limiar do aviso de WhatsApp que já existe (`daily.avisar_estoque_baixo`).

### 5. A página — `site_web.pagina_curadoria()`

Assinatura nova:

```python
def pagina_curadoria(estado, amanha, candidatos, reserva, classicos, token,
                     aba="triagem", tema="", msg=""):
```

- `estado` — dict de `estado_estoque`
- `amanha` — `{"titulo", "status", "review_token"}` ou `None`. Vem de `draft_store.carregar(amanhã)`; `titulo` = `titulo_pt` do rascunho (gravado em `daily.py:358`), caindo pro `artigo["titulo"]` se faltar
- `candidatos` — `tipo="varredura"`, status `novo` + `selecionado`
- `classicos` — `{"candidatos": [...], "banco": [...]}`
- `aba` — `triagem` | `reserva` | `classicos`; `tema` — filtro dentro da triagem

Layout:

```
┌──────────────────────────────────────────────────────┐
│ 👥 Assinantes · 🔬 Curadoria · 📅 Agenda · …          │
│ Curadoria                                             │
├──────────────────────────────────────────────────────┤
│ 📦 Conteúdo garantido até 14/08 · 14 envios          │  faixa (laranja se baixo)
├──────────────────────────────────────────────────────┤
│ 📋 Amanhã sai: "Tirzepatida em 72 semanas…"          │
│    aguardando sua revisão →  [ Revisar ]              │
├──────────────────────────────────────────────────────┤
│ ┌ Triagem 12 ┐ Reserva 8 │ Clássicos 0 │             │  abas de 1º nível
├──────────────────────────────────────────────────────┤
│ Todos 12 · ⚖️ 4 · ⚕️ 3 · 🦵 2 · 🏃 2 · 🧬 1           │  filtro por tema
│                                                       │
│ ★8  Tirzepatida mantém a perda de peso?        ↗     │  título = link p/ DOI/url
│ ❓ A perda ponderal se sustenta após 2 anos?          │
│ Lancet · 12/07/2026 · DOI 10.1016/…                  │
│ [ ⬆️ Priorizar ]              [ 🗑️ Descartar ]        │
├──────────────────────────────────────────────────────┤
│ ⚙️ Ferramentas ▾  (recolhido, <details>)              │
│    ➕ Adicionar meu estudo · 🔎 Varrer agora           │
│    · 🏛️ Varrer clássicos                              │
└──────────────────────────────────────────────────────┘
```

Detalhes:

- Os **6 cartões de estatística saem**; viram a faixa de uma linha. Os contadores por aba e por tema cobrem o resto.
- Item já **priorizado** mostra badge `⏳ gera hoje à noite` e a ação vira `↩️ Desfazer` — feedback de que o clique fez algo, já que o resumo só nasce às 21h.
- **Título vira link** (`href` = `url` ou `https://doi.org/<doi>`, `target="_blank"`); hoje o DOI é texto morto.
- Aba **Clássicos**: candidatos `tipo="classico"` pendentes (mesmas ações) + o banco já aprovado (`db.listar_classicos(elegiveis=False)`, só leitura). É a tela que faltava (follow-up do item 17 do backlog).
- Aba **Reserva**: o `<details>` de editar/remover que já existe, movido pra cá sem mudança de comportamento. O contador da aba conta só os `pronto` (estoque real); os `enviado` seguem listados abaixo, como histórico.
- **"➕ Adicionar meu estudo"** vai pro `<details>` de Ferramentas — mesmo form, mesmo endpoint multipart, só recolhido.
- **Varrer clássicos** ganha botão (`acao=varrer_classicos` já existe no `serve.py:560` e nunca teve UI).
- Abas e filtro de tema por **querystring** (`?aba=&tema=`), não JS — sobrevive a reload e o redirect das ações preserva o contexto.

## Testes

Padrão da casa: `unittest` standalone em `app/tests/`, dependências de rede injetadas.

**`test_curadoria.py`** (existente, adicionar):
- piso corta candidato abaixo de `SCORE_PISO` quando o tema tem fartura
- válvula: tema com menos de `MIN_POR_TEMA` acima do piso entrega os melhores mesmo abaixo
- tema com 0 resultados da triagem continua vazio (não inventa)
- `varrer_classicos` **não** aplica piso (segue por citações)

**`test_agenda_plan.py`** (existente, adicionar):
- `estado_estoque` conta e projeta a data do último envio coberto
- `envios=0` → `ate=None`, `baixo=True`
- `baixo` liga/desliga no limiar exato

**`test_site_web.py`** (existente, ajustar + adicionar):
- ⚠️ a chamada atual em `test_site_web.py:136` usa a assinatura antiga — **precisa ser atualizada**
- aba triagem renderiza item com link do DOI, pergunta, score e as duas ações
- item `selecionado` mostra `⏳ gera hoje à noite` + `↩️ Desfazer` (e não `⬆️ Priorizar`)
- candidato `tipo="classico"` **não** aparece na aba Triagem (Bug 1)
- faixa de estoque mostra o alerta quando `baixo=True`
- "Amanhã sai" some quando `amanha=None`

**`test_varredura_semanal.py`** (existente, adicionar) ou novo `test_gerar_noturno.py`:
- a tarefa `gerar_curadoria` chama `curadoria.gerar_selecionados` (com a função injetada)
- falha na geração não derruba o agendador

## Critérios de aceite

1. Rodar a varredura com fartura simulada só admite candidatos com score ≥ `SCORE_PISO`.
2. Tema seco continua entregando candidatos (a válvula afrouxa o piso).
3. A tela não tem mais checkbox nem "💾 Salvar seleção".
4. Clicar em "⬆️ Priorizar" marca na hora e a página volta na mesma posição da lista.
5. Nenhum candidato `tipo="classico"` aparece na aba Triagem.
6. O botão "🏛️ Varrer clássicos" existe e funciona.
7. Os resumos dos priorizados são gerados sozinhos às `HORA_CURADORIA` — sem clique.
8. `python3 -m unittest discover -s tests` verde.

## Arquivos

| Arquivo | Mudança |
|---|---|
| `app/config.py` | `SCORE_PISO`, `MIN_POR_TEMA`, `HORA_CURADORIA` |
| `app/curadoria.py` | piso + válvula no `varrer()` |
| `app/agenda_plan.py` | `estado_estoque()` |
| `app/serve.py` | tarefa `gerar_curadoria` no agendador; ações `priorizar`/`descartar`/`desfazer`; remove `acao=selecionar`; monta os dados novos da rota GET (com `tipo`) |
| `app/site_web.py` | `pagina_curadoria` reescrita (abas, faixa, amanhã, ações por item, ferramentas recolhidas) |
| `app/tests/test_curadoria.py` | piso e válvula |
| `app/tests/test_agenda_plan.py` | `estado_estoque` |
| `app/tests/test_site_web.py` | assinatura nova + render das abas/estados |
| `app/tests/test_varredura_semanal.py` | cron noturno de geração |
