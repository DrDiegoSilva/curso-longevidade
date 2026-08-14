# Item 33 — tirar um estudo da memória (parte A) + o ledger de custos de IA

**Data:** 2026-08-12
**Base:** `origin/main` = `ba3c17b`
**Branch:** `feat/corpus-excluir`

## O problema

O Diego leu o dossiê da 4ª aba da /curadoria e perguntou: *"no dossiê, como consigo
ajustar alguma informação? ou não posso? tirar algum dado de estudo que não faça
sentido"*. Hoje não dá: o dossiê é **reconstruído do zero** pelo botão 🧠, então qualquer
edição manual seria apagada na reconstrução seguinte, sem aviso.

Ele pediu os dois consertos. Esta spec é o **(A)**: tirar o estudo da memória, para que
**toda reconstrução futura já o ignore**. Ataca a causa (estudo ruim arrastando a
afirmação junto) e por isso é durável. O **(B)** — editar o texto da afirmação e fixar o
bloco contra a reconstrução — vem depois, em spec própria.

## O que o ✕ significa (e o que ele não significa)

Pergunta do Diego no debate: *"como vai ser a avaliação sendo que existem estudos que
refutam outros estudos?"*.

O dossiê **guarda a discordância de propósito** — o `dossie.SYS` manda registrar onde os
estudos divergem e proíbe forçar consenso; a opinião do dia (fatia 2b) aponta o conflito
e não resolve, quem toma partido é o Diego na caixa das 18h.

Logo, o ✕ **não é "discordo deste achado"**. É para estudo que não deveria estar na
memória: fora do tema, duplicado, população que não serve, fraco demais. Usar o ✕ para
apagar o que contraria a própria leitura transforma a memória em eco — e mata justamente
o que dá valor à opinião.

Quando o problema for *a afirmação está errada* (e não *o estudo é ruim*), o conserto é o
(B). A tela diz isso ao lado do ✕:

> tirar da memória — estudo fora do tema, duplicado ou fraco. Não use pra discordar do
> achado: a divergência entre estudos é o que o dossiê existe pra guardar.

## Decisões do Diego (2026-08-12)

1. **Nos dois lugares**: ✕ no estudo dentro do bloco do dossiê *e* uma lista do corpus por
   tema com ✕ exato.
2. **O escopo é perguntado na hora do clique**: dois botões, "Só da memória" e "Da memória
   e da fila". Não há escopo padrão.

## Onde mora a exclusão

O corpus vem de **duas fontes** (`dossie.corpus_do_tema`): `curadoria_candidatos`
(varredura + backfill) e `digests` (estudos **já enviados**, tabela que também alimenta o
portal do assinante).

| Tabela | Coluna nova | Quem lê |
|---|---|---|
| `curadoria_candidatos` | `excluido TEXT DEFAULT ''` | `listar_candidatos` (esconde `'tudo'`) + `corpus_do_tema` (esconde os dois) |
| `digests` | `excluido TEXT DEFAULT ''` | **só** `corpus_do_tema` |

Valores: `''` (na base), `'memoria'` (fora do dossiê, continua na fila), `'tudo'` (fora
dos dois).

Ambas as colunas entram por `db._add_coluna` no `_migrar_colunas` — idempotente e já cobre
Postgres (`ADD COLUMN IF NOT EXISTS`) e SQLite (try/except).

### Por que o filtro entra dentro do `listar_candidatos`

`db.listar_candidatos` passa a esconder `excluido='tudo'` **por padrão**, com
`listar_candidatos(..., incluir_excluidos=True)` para quem precisa ver os excluídos (a
lista de devolver).

Isso cobre de uma vez os cinco consumidores — `materializar_agenda`,
`montar_candidatos_triagem`, `montar_alternativas` (picker do 🔁), `_preparar_de_candidato`
e o `cand_n` do estoque — sem depender de eu lembrar de filtrar em cada um. É exatamente a
classe de erro que vazou o `tipo='corpus'` para o picker do 🔁 (ver a nota do item 33), e
desta vez o filtro fica num lugar só.

Consequência desejada no estoque: um candidato `'tudo'` deixa de ser contado por
`cand_n`, então `precisa_reabastecer` volta a buscar estudos novos. É o oposto do bug do
corpus, que inflava o estoque e parava a máquina.

### Por que o portal não pode mudar

`db.listar_por_tema` serve o portal do assinante (`serve.py:653-657`) **e** o
`corpus_do_tema`. Um estudo já enviado não dá pra des-enviar: o filtro de exclusão fica
**no `corpus_do_tema`**, nunca no `listar_por_tema`. Para estudo vindo de `digests` a tela
oferece só **"tirar da memória"** — "da fila" não significa nada para o que já saiu.

### A exclusão sobrevive à varredura

`excluido` é coluna à parte, e o upsert de `salvar_candidatos`
(`ON CONFLICT (chave) DO UPDATE`) não a toca. Se o mesmo paper for varrido de novo — ou
promovido de `corpus` para `varredura` —, os campos dele atualizam e a exclusão continua
de pé.

## As telas (aba 🧠 Dossiê da /curadoria)

Tudo sem JS, como o resto da /curadoria (formulários POST + redirect com `msg`).

**a) ✕ no estudo dentro do bloco.** Cada estudo citado numa afirmação ganha um ✕ que
**não exclui na hora**: abre uma confirmação mostrando qual estudo *de verdade* casou com
aquele título — título completo, fonte, data e origem (candidato ou já enviado). Ali ficam
os dois botões de escopo e o Cancelar. Mesmo padrão da dupla confirmação de Assinantes.

**b) "Estudos lidos (N)"** — acordeão por tema com o corpus real, cada linha com os dois
botões direto (sem confirmação: aqui não há dúvida sobre qual estudo é). É o caminho
garantido quando o casamento de título falhar.

**c) "Fora da memória (N)"** — os excluídos do tema, com **Devolver**. Clique errado tem
volta.

**Feedback depois de excluir:** o bloco continua mostrando o estudo **riscado**, com o
aviso *"fora da memória — refaça o dossiê (🧠) pra ver o efeito nas afirmações"*. Riscar,
e não sumir: o dossiê guardado ainda é o antigo, e esconder a linha faria parecer que a
memória já foi reconstruída sem aquele estudo.

**d) "🧠 Refazer só este tema"** — botão no cartão de cada tema. Observação do Diego:
excluir obriga a reconstruir, e o botão das Ferramentas refaz **os cinco temas** (≈ 10
chamadas Sonnet por tema). Refazer só o tema mexido corta o custo por ~5. É quase de graça
de implementar: `dossie.reconstruir_todos(temas=[t])` já aceita a lista, e a trava
`_LOCK` já impede dois cliques simultâneos. Mesmo desenho assíncrono do botão atual
(thread + aviso no WhatsApp), porque a reconstrução leva minutos.

> Quanto custa, hoje, por estimativa: um tema grande (~250 estudos, 10 lotes + fusão) sai
> por ~US$ 0,7 (≈ R$ 4); os cinco, R$ 10-13. **É estimativa, não medição** — medir de
> verdade é o item 40 do backlog (tela de custos), projeto separado.

## O casamento do título

O dossiê guarda o título **como a IA escreveu** — ela pode ter traduzido ou truncado. A
resolução é função pura, `dossie.casar_titulo(titulo, corpus)`, em três degraus:

1. **Igual depois de normalizar** — minúsculas, sem acento, sem pontuação, espaços
   colapsados;
2. **Truncado** — o menor dos dois títulos normalizados tem ao menos 30 caracteres e é
   **prefixo** do outro (a IA corta o fim, não o começo); vale só se um único estudo do
   corpus casar assim;
3. **Não achou, ou achou mais de um** → devolve `None`, e a tela diz *"não achei este
   estudo na base com esse título — abra **Estudos lidos** e tire de lá"*.

**O que não fazer:** registrar a exclusão pelo título quando o casamento falha. Isso
sumiria com a linha da tela sem tirar o estudo da memória — pareceria resolvido, e a
próxima reconstrução traria o estudo de volta. Falha aberta e verbosa, não silenciosa.

## Interfaces

```python
# db.py
listar_candidatos(status=None, tema=None, tipo=None, incluir_excluidos=False)
excluir_candidato(cand_id, escopo)        # escopo: 'memoria' | 'tudo' | '' (devolver)
excluir_digest(tema_slug, data, escopo)   # digests não têm id: PK é (data, tema_slug)
listar_excluidos(tema)                    # candidatos + digests, para a lista (c)

# dossie.py
corpus_do_tema(tema, db_mod=None)   # cada item ganha 'id' e 'origem' ('candidato'|'digest')
casar_titulo(titulo, corpus)        # -> item do corpus ou None
```

`corpus_do_tema` passa a devolver `id` e `origem` em cada item; `construir`/`acrescentar`
não mudam (o `_linha` lê só titulo/fonte/data/abstract, e campo extra não atrapalha).

## Testes

TDD, `unittest`, `cd app && python3 -m unittest discover -s tests`.

- `listar_candidatos` esconde `'tudo'` e **mantém** `'memoria'` — teste de comportamento
  com banco de verdade, não grep no fonte (foi assim que duas mutações sobreviveram na
  fatia anterior do item 33);
- `corpus_do_tema` some com os dois escopos, nas duas fontes;
- **o portal não muda**: `listar_por_tema` continua devolvendo o digest excluído da
  memória — é a regressão perigosa desta fatia;
- a exclusão **sobrevive** a um novo `salvar_candidatos` do mesmo paper (upsert não limpa
  a coluna);
- `casar_titulo`: igual, com acento/caixa, truncado, ambíguo → `None`, inexistente →
  `None`;
- devolver restaura (o estudo volta ao corpus e à fila);
- a tela: ✕ que não casa mostra o aviso e **não exclui nada**.

Fechando: quebrar cada guarda de propósito e conferir que a suíte cai. Suíte verde sozinha
não é prova.

---

# Parte 2 — o ledger de custos (medição, sem tela)

Pedido do Diego no meio desta spec, ao ver que excluir obriga a reconstruir: *"já coloca na
tela tbm os possíveis custos de cada atualização de estudo, áudio, dossiê e tal pra eu ter
uma noção dos custos ou uma tela com custos que já tivemos pra poder saber repassar na
precificação"*. **É insumo de preço.**

Decisão dele (2026-08-12): o **ledger entra junto com a exclusão**; a tela `/admin/custos`
fica para depois (item 40 do backlog). Assim o histórico começa a acumular hoje, sem
atrasar esta entrega — mas não há consulta antes da tela existir.

**Ordem que importa:** medir antes de estimar. Número de custo em botão, antes do ledger,
é chute — inclusive os R$ 4 que eu estimei acima.

## O achado que dimensiona

Só existem **dois** pontos de saída pagos no sistema inteiro:

| Funil | Onde | O que a resposta traz |
|---|---|---|
| Anthropic | `resumo_diario.claude()` (`resumo_diario.py:47`) | `usage.input_tokens` / `output_tokens` — **hoje jogados fora** |
| OpenAI TTS | `audio.narrar()` (`audio.py:44`) | nada; a cobrança é por caractere, e `len(texto)` já basta |

Dossiê, resumo do dia, kit, triagem, perguntas, gancho, título, gráfico e o roteiro do
áudio passam todos pelo primeiro. Instrumentar os dois mede o sistema inteiro.

## Desenho

**Tabela `ia_uso`** — `id, quando, acao, modelo, tokens_in, tokens_out, chamadas`.

**Guarda o cru, calcula o custo na leitura.** A tabela guarda tokens; o preço vive em
`config.PRECOS_IA` (US$ por 1M de unidades, por modelo — para o TTS a unidade é o
caractere). Consequência que vale o desenho: **preço errado ou preço que mudou é
recálculo, não perda** — a história inteira se revaloriza sozinha. Se o custo fosse
congelado na linha, um preço errado hoje contaminaria os números para sempre.

**Por que não pedir o valor pronto para a API** (pergunta do Diego, 2026-08-12): a resposta
das mensagens traz `usage` em tokens e **nenhum campo de dinheiro** — custo é sempre
tokens × preço. Existe a Admin API de uso/custo da Anthropic (e equivalente na OpenAI),
que devolve o valor **realmente faturado**, mas ela (1) exige chave de *admin da
organização*, diferente da que o app usa, e (2) vem agregada por dia e modelo: sabe que
gastou US$ 12 de Sonnet na terça, não sabe o que é um dossiê. A quebra por ação — que é o
que serve para precificar — só o ledger dá. Conferir um contra o outro (ledger × fatura)
é bom, e fica para o item 40, junto da tela.

**Cotação do dólar fixa**: `config.USD_BRL` (padrão 5,50, override por
`DSCURSO_USD_BRL`), e a tela futura sempre mostra qual cotação usou. Média basta: a
decisão que esse número sustenta não muda com 3% de câmbio.

⚠️ `PRECOS_IA` e `USD_BRL` nascem como minha melhor leitura e **precisam ser conferidos
pelo Diego**. Ambos com override por variável de ambiente, para corrigir sem deploy.

⚠️ **Se um dia entrar prompt caching**, `usage` ganha `cache_creation_input_tokens` e
`cache_read_input_tokens`, que têm preço próprio; sem registrá-los o custo medido passa a
mentir. Hoje o corpo da requisição não usa cache, então ficam de fora — mas quem ligar
cache tem que voltar aqui.

**A ação viaja explícita**: `claude(..., acao="dossie")`, um parâmetro novo com padrão
`""`. São ~15 pontos de chamada, uma palavra em cada. Preferi explícito a inferir pela
pilha de chamadas: se eu esquecer um ponto, ele cai num balde `"desconhecido"` que
**aparece na conta** — inferência mágica erraria calada.

Os rótulos, fixados agora para a tela futura não nascer com sinônimos: `dossie`,
`resumo_estudo`, `boletim`, `triagem`, `tags`, `metadados`, `perguntas`, `kit`, `titulo`,
`grafico`, `aula`, `audio_roteiro`, `audio_tts` — mais `desconhecido` para quem esquecer.

> Corrigido durante a implementação (2026-08-13): o levantamento original contava **15**
> pontos de chamada e existem **17**. `triage.py` tem três, não uma. Triar a varredura,
> etiquetar o estoque e extrair metadados de um PDF recém-subido são atividades diferentes,
> com gatilho e frequência diferentes — juntá-las num rótulo só esconderia justamente o que
> a tela vai existir pra mostrar. Daí `tags` e `metadados` separados de `triagem`.

**Uma linha por chamada de `claude()`**, somando o laço de continuação (o `cont=4` pode
render 5 idas à API numa chamada só; `chamadas` guarda quantas foram).

**Falha de contabilidade nunca derruba geração.** Todo o registro vai em `try/except` com
`print` no log: perder uma linha de custo é aceitável, perder o estudo do dia não é.

## Testes da parte 2

- `custo_usd(modelo, tin, tout)` — cálculo por modelo, modelo desconhecido não explode;
- `claude()` **grava** o uso: o POST vira uma função pequena (`_post`) que o teste
  substitui, e aí dá pra provar o registro sem rede — inclusive que o laço de continuação
  vira **uma linha com `chamadas=2`**, não duas linhas;
- `narrar()` grava **o que foi mandado de verdade**: o código corta em 4000 caracteres
  antes de enviar (`audio.py:47`), então o cobrado é o texto cortado, não o original —
  teste com texto de 5000 caracteres tem que registrar 4000;
- banco fora do ar não derruba a geração: `registrar_uso` levanta, `claude()` devolve o
  texto assim mesmo.

## Fora de escopo

- (B) editar a afirmação e fixar o bloco contra a reconstrução — spec própria, depois
  desta no ar;
- a opinião do dia (2b), o interruptor (2c) e o áudio (3) do item 33;
- apagar o estudo do banco. Exclusão é reversível por desenho: o abstract fica lá, só sai
  do que é lido;
- **a tela `/admin/custos`** e a estimativa de custo nos botões — item 40 do backlog. Aqui
  entra só a medição, por decisão do Diego. Enquanto a tela não existe, o gasto se lê por
  consulta ao banco.
