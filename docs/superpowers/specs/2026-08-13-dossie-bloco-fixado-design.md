# Item 33 — o dossiê corrigível, parte B: editar a afirmação e fixar o bloco

**Data:** 2026-08-13
**Base:** `origin/main` = `f5c8b97`
**Branch:** `feat/dossie-fixar`

## O problema

A parte A (no ar desde 2026-08-13, ver `2026-08-12-excluir-estudo-do-corpus-design.md`)
resolveu o caso "este estudo não deveria estar na memória" — o estudo sai do corpus e toda
reconstrução futura já o ignora.

Falta o outro caso, que o Diego pediu junto: **a afirmação está errada**. O estudo é bom,
o lastro existe, mas a frase que a IA escreveu não diz o que ele diria. Hoje não há onde
mexer: o dossiê é reconstruído do zero pelo botão 🧠, e qualquer edição manual seria
apagada na reconstrução seguinte, **sem aviso**.

## Decisões do Diego (2026-08-13)

1. **Editar já fixa.** Não há "editar sem fixar". Todo bloco que ele reescreve vira dele e
   a máquina para de mexer. Sem isso existiria um estado perigoso — texto dele num bloco
   solto, que some na reconstrução seguinte, que é exatamente a armadilha que esta fatia
   fecha.
2. **Sem afirmação nova do zero.** Só correção do que a IA produziu. Se falta algo na
   memória, o sinal provável é falta de estudo na base, não de texto na tela.

## Onde mora a garantia

Os blocos hoje são uma lista JSON sem identidade (`dossies.conteudo`), então não há como
apontar "este bloco". Cada bloco passa a ter um **id estável**, atribuído no momento de
salvar; os que são do Diego ganham `fixado` e `editado_em`.

**A preservação vive no gravador, não no reconstrutor.** `db.salvar_dossie` passa a
sempre reler os blocos fixados do que já está gravado e mantê-los, **seja qual for o
conteúdo que o chamador mandar**.

Por que não ensinar `reconstruir_todos` a poupar os fixados, que seria o caminho óbvio:
qualquer caminho futuro que grave um dossiê — um botão novo, um cron, um script de
madrugada — apagaria o texto do Diego, e o erro só apareceria semanas depois, quando a
afirmação sumisse. Com a regra no gravador **não existe forma de perder o texto dele
escrevendo errado**. Soltar o bloco vira a única porta de saída, explícita e nomeada.

Um bloco fixado guarda **o texto que o Diego escreveu** e a lista de estudos que estava
embaixo dele no momento em que fixou. A exclusão da parte A continua valendo por cima:
estudo tirado da memória aparece riscado também dentro de um bloco fixado.

## Formato

```python
# um bloco dentro de dossies.conteudo
{"id": "b3f9...", "afirmacao": "...", "estudos": [{"titulo","fonte","data"}],
 "fixado": True, "editado_em": "2026-08-13T18:22:00"}   # os 2 últimos só nos fixados
```

`dossie.parse` e `dossie.construir` continuam sem saber de id — quem atribui é
`salvar_dossie`, para qualquer bloco que chegue sem um.

## Interfaces

```python
# db.py
salvar_dossie(tema, conteudo, n_estudos)        # agora PRESERVA os fixados e dá id aos novos
dossie_editar_bloco(tema, bloco_id, afirmacao)  # grava o texto e fixa; ValueError se vazio
dossie_soltar_bloco(tema, bloco_id)             # tira o fixado (o texto atual fica até a
                                                # próxima reconstrução substituir)

# dossie.py
construir(estudos, lote=LOTE_PADRAO, gerar_fn=None, fixadas=None)
```

## A tela (aba 🧠 Dossiê)

- Cada bloco ganha **✏️ Editar**: um `<details>` com a afirmação numa `<textarea>` e um
  botão de salvar. Sem JS, mesmo padrão do editar da Reserva.
- Bloco fixado aparece com **📌 e a data** ("sua versão — a reconstrução não mexe") e um
  **soltar** ao lado.
- **Texto vazio é recusado com aviso**, não salvo: afirmação em branco não é edição, é um
  bloco sem sentido — e como editar fixa, salvar vazio congelaria o nada.

## A reconstrução

As afirmações fixadas viajam no prompt da **fusão** (`construir(..., fixadas=[...])`), com
a instrução de não repeti-las. Evita o dossiê dizer a mesma coisa duas vezes, uma com as
palavras do Diego e outra com as da IA.

Não é garantia — modelo repete às vezes. A defesa real é a que o desenho já tem: se
repetir, ele vê as duas na tela e solta ou edita a que sobrou. **O que não se deve fazer é
filtrar por semelhança de texto**: isso apagaria em silêncio uma afirmação nova legítima só
por parecer com a dele.

## Fora de escopo

- **Editar a lista de estudos de um bloco.** Tirar estudo é a parte A, que ataca a causa no
  corpus. Permitir editar o lastro aqui criaria uma lista que não corresponde a nada no
  banco — exatamente o que o formato do dossiê existe pra impedir.
- Escrever afirmação do zero (decisão 2).
- A opinião do dia (fatia 2b), o interruptor (2c) e o áudio (3) do item 33.
- A tela de custos (item 40 do backlog).

## Testes

TDD, `unittest`, `cd app && python3 -m unittest discover -s tests`.

- **A garantia**: `salvar_dossie` chamado com um conteúdo que NÃO contém o bloco fixado
  ainda assim o preserva — é o teste que dá sentido a todo o desenho;
- id é atribuído a bloco que chega sem um, e o id de um bloco fixado **não muda** entre
  salvamentos;
- `dossie_editar_bloco` grava o texto e fixa numa tacada; texto vazio (ou só espaços)
  levanta `ValueError` e não grava;
- `dossie_soltar_bloco` tira o fixado, e aí a reconstrução seguinte substitui o bloco;
- `reconstruir_todos` ponta a ponta: bloco fixado sobrevive a uma reconstrução que devolve
  blocos completamente diferentes;
- o prompt da fusão carrega as afirmações fixadas (teste de comportamento capturando o
  prompt, não grep no fonte);
- tela: form de editar presente, marcador 📌 nos fixados, soltar presente, tudo escapado;
- rotas: sem token 403 e nada muda; editar persiste; vazio devolve aviso; soltar funciona.

Fechando: quebrar cada guarda de propósito e conferir que a suíte cai.
