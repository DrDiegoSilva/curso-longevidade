# Item 33 — tirar um estudo da memória (dossiê corrigível, parte A)

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

## Fora de escopo

- (B) editar a afirmação e fixar o bloco contra a reconstrução — spec própria, depois
  desta no ar;
- a opinião do dia (2b), o interruptor (2c) e o áudio (3) do item 33;
- apagar o estudo do banco. Exclusão é reversível por desenho: o abstract fica lá, só sai
  do que é lido.
