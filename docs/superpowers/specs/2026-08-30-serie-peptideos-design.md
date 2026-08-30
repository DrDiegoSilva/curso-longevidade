# Série de Peptídeos — item 44 — design

**Data:** 2026-08-30
**Status:** spec aprovada no brainstorm, aguardando plano de implementação

## O problema

Pacientes perguntam muito sobre peptídeos fora do GLP-1 (esse já é coberto no tema Obesidade da
rotação diária). O levantamento de pesquisa feito em 2026-08-29
(`docs/superpowers/specs/assets/2026-08-29-levantamento-peptideos.md`, 43 fontes) mostra dois
achados que moldam o design:

- Evidência humana é fraca a inexistente pra maioria dos peptídeos pedidos (robusto em
  pré-clínico/animal, RCT humano pequeno, único ou ausente).
- A ANVISA publicou dois alertas oficiais em julho/2026 nomeando explicitamente BPC-157, TB-500,
  GHK-Cu, CJC-1295 e Ipamorelina como **"ilegais para qualquer uso em saúde, inclusive
  estético"** — não é só "sem registro", é postura ativa de fiscalização. O CRM-PR estendeu a
  lista nomeada para Semax, Selank, Tesamorelina e Retatrutida.

Não cabe na rotação diária dos 5 temas — pouca literatura pra sustentar um tema permanente, e o
Diego já cogitou e descartou trocar a vaga de segunda por isso. Vira série separada, nos moldes
da trilha de empreendedorismo: evergreen, escrita uma vez, drip por assinante.

## Decisões do brainstorm

| Decisão | Escolha | Por quê |
|---|---|---|
| Formato do produto | Nova trilha (drip evergreen), fora da rotação diária | Mesmo modelo já provado pela trilha de empreendedorismo; pouca literatura pra tema diário permanente |
| Dia de envio | Sábado — o **mesmo slot** da trilha existente, não um dia novo | Em vez de arranjar domingo, a trilha vira multi-produto: só uma fica ativa por vez, e o Diego escolhe qual no admin |
| Trocar de trilha ativa | Quem está no meio de uma trilha termina ela até o fim antes de começar a próxima | Ninguém perde conteúdo pela metade por causa de uma troca de prioridade do Diego |
| Peças por sábado | 2 (a trilha de empreendedorismo continua com 1) | Tema mais "consumível" e a série é menor (11 peças) — decisão do Diego |
| Nota da ANVISA | Seção própria (`## aviso`) virando bloco de alerta (borda vermelha/âmbar), posicionado depois do corpo e antes da tarefa da semana | Precisa ser clara no texto, mas sem competir visualmente com os blocos de tarefa/mentalidade — validado com mockup no companheiro visual (opção B) |
| Escopo de peças | 11 (10 fixas + Epithalon opcional) | Pesquisa recomendou 8-9 por força de evidência; Diego reincluiu MOTS-c e GHK-Cu por popularidade/uso real entre pacientes — o motivo original do pedido |

## Pesquisa

Resumo de `docs/superpowers/specs/assets/2026-08-29-levantamento-peptideos.md`. Achado central:
alertas oficiais da ANVISA (jul/2026) nomeiam BPC-157, TB-500, GHK-Cu, CJC-1295 e Ipamorelina
como ilegais para qualquer uso; o CRM-PR estendeu a lista nomeada a Semax, Selank, Tesamorelina e
Retatrutida. **Praticamente toda peça da série precisa da nota** — inclusive as com aprovação em
outro país (Tesamorelina/Egrifta, PT-141/Vyleesi, Timosina Alfa-1/Zadaxin), porque nenhuma tem
registro no Brasil.

Duas afirmações do levantamento estão marcadas como **inferidas, não confirmadas** (Sermorelin e
Kisspeptina não aparecem nominalmente em nenhum alerta oficial) — conferir antes de publicar
essas duas peças especificamente.

## As 11 peças

1. Abertura — "nem todo peptídeo é igual" (aprovado / aprovado fora do Brasil / nunca aprovado em
   lugar nenhum)
2. Reparo tecidual — BPC-157 + TB-500
3. GHK-Cu (solo)
4. Secretagogos de GH, mecanismo — Ipamorelin + CJC-1295 + Sermorelin + Tesamorelina
5. Secretagogos de GH, contraste regulatório (mesmo grupo)
6. Nootrópicos russos — Semax + Selank
7. PT-141/Bremelanotide (solo)
8. Timosina Alfa-1 (solo)
9. Melanotan II — alerta (melanoma, priapismo documentados)
10. MOTS-c — alerta/expectativa
11. *(opcional)* Epithalon — só se topar tom cético

Fora: DSIP (evidência fraca demais até pra uma peça honesta). O **texto** de cada peça é trabalho
separado, depois desta spec — mesma ordem que a trilha de empreendedorismo seguiu (conteúdo antes
da infra de envio).

## Anatomia da peça — nova 4ª seção

Reaproveita as 3 camadas da trilha de empreendedorismo (corpo, tarefa da semana, mentalidade) e
ganha uma 4ª, opcional:

4. **Aviso** — nota regulatória clara sobre a substância, quando aplicável. Vira bloco de alerta
   visualmente distinto (não o dourado das outras duas), posicionado logo depois do corpo.

Diferente da trilha de empreendedorismo, a "tarefa da semana" de uma peça de peptídeo
provavelmente não é uma tarefa executável (esta série não ensina "como usar") — pode ficar vazia
ou virar outra coisa (ex.: pergunta pra levar ao médico). Isso é decisão de conteúdo, fora desta
spec.

## Arquitetura — a trilha vira multi-produto

Hoje `trilha.py`/`db.py`/`config.py` só suportam **um** produto (empreendedorismo), com um
interruptor booleano (`trilha.ativa()`). Isso generaliza pra suportar N produtos via um catálogo
e um "qual está ativo agora".

### Catálogo (`config.py`)

```python
TRILHAS = {
    "empreendedorismo": {"nome": <TRILHA_NOME atual>, "total": 12,
                          "dir": <TRILHA_DIR atual>, "pecas_por_envio": 1},
    "peptideos": {"nome": "(placeholder — Diego define)", "total": 11,
                  "dir": "seed/peptideos", "pecas_por_envio": 2},
}
TRILHA_DIA = "sabado"  # continua compartilhado entre todos os produtos
```

### Tabelas

Todas ganham `produto` como parte da chave:

- `trilha_pecas(produto, numero, eixo, titulo, corpo, micro_resultado, mentalidade, aviso,
  ferramenta_slug, ativa, atualizado_em)` — PK `(produto, numero)`. Coluna nova: `aviso`.
- `trilha_progresso(subscriber_id, produto, proxima_peca, ultimo_envio)` — PK
  `(subscriber_id, produto)`.
- `trilha_envios(subscriber_id, produto, numero, enviado_em, feito_em)` — PK
  `(subscriber_id, produto, numero)`.

Migração segue o padrão de `_migrar_colunas`/`_migrar_indices` já usado no repo: adiciona a
coluna `produto` com default `'empreendedorismo'` nas linhas existentes, recria os
índices/chaves. Como a trilha de empreendedorismo nunca foi ligada em produção, as tabelas devem
estar vazias hoje — mas a migração cobre o caso de já existir progresso.

### Motor (`trilha.py`)

Peça central nova: **`produto_do_assinante(sub_id)`**. Resolve, a cada sábado, qual produto
aquele assinante recebe:

1. Olha o progresso do assinante em cada produto do catálogo. Se algum está incompleto
   (`proxima_peca <= total` daquele produto), esse é o produto — não importa qual está "ativo"
   agora. É isso que garante "termina antes de trocar".
2. Se nenhum está incompleto (assinante novo, ou acabou de concluir tudo que já tinha começado),
   usa o produto ativo do momento (`trilha_produto_ativo()`).
3. Se não há produto ativo, `None` — ninguém novo entra, mesma postura de segurança que
   `trilha.ativa()` tem hoje ("nasce desligada").

Invariante que sustenta o passo 1: um assinante nunca tem mais de um produto incompleto ao mesmo
tempo, porque só entra num produto novo quando concluiu (ou nunca começou) todos os outros — não
existe caminho pra "meio de A e meio de B" simultaneamente.

`ativa()`/`definir_ativa()` (booleano) viram `produto_ativo()`/`definir_produto_ativo(id_ou_vazio)`
(`db.get_config("trilha_produto_ativo", "")`).

`enviar_para(sub, ...)` passa a mandar `pecas_por_envio(produto)` peças em sequência — mesmo ciclo
claim→render→envia→avança de hoje, repetido N vezes, com o mesmo delay de pacing já usado entre
assinantes diferentes aplicado também entre a 1ª e a 2ª peça da **mesma** pessoa. Se a trilha
acabar no meio do lote (ex.: só falta 1 peça quando `pecas_por_envio=2`), manda a que resta e
para — nunca emenda no próximo produto no mesmo sábado.

`semear()` passa a rodar por produto (lê `dir` de cada entrada do catálogo) e, ao terminar de
semear o produto "peptideos", imprime no log quantas peças ficaram sem o campo `aviso` — sinal
visível em deploy, não bloqueio duro (a peça de abertura pode legitimamente não precisar).

### Admin (`/admin/trilha`)

O botão único ligar/desligar vira um seletor de produto (Nenhuma / Empreendedorismo /
Peptídeos). Prévia de peças (`/admin/trilha/peca/<n>`) e o painel "quem está em qual semana"
passam a ser por produto (querystring `?produto=`). Trocar o produto ativo não mexe em quem já
está em progresso em outro.

### Página do assinante (`/trilha`)

Mostra a trilha do produto em que a pessoa está agora (mesma função `produto_do_assinante`),
nome/total lidos do catálogo em vez de constante fixa. Sem mudança visual.

### Bloco da ANVISA (`pdf_trilha.py`)

Novo bloco `.bloco.alerta` — mesma estrutura visual do `.bloco` existente (borda esquerda,
rótulo, texto), mas com cor de alerta (borda vermelho/âmbar `#b3402a`) em vez do dourado
`#c9a227` das outras duas. Renderiza só quando `peca.aviso` não é vazio (mesma regra de hoje pra
`micro_resultado`/`mentalidade`), posicionado depois do `<div class="corpo">` e antes do bloco
"Sua tarefa desta semana".

## Estados e falhas

| Situação | Comportamento |
|---|---|
| Assinante no meio de A quando B vira produto ativo | Continua recebendo A até concluir; só depois entra em B |
| Assinante novo, nenhum produto ativo | Não recebe nada (mesma postura "nasce desligada" de hoje) |
| Envio de uma das 2 peças do sábado falha | Só a que falhou fica pendente pro sábado seguinte (claim por peça, sem mudança na lógica existente) — a outra já enviada não repete |
| Trilha acaba no meio do lote de 2 | Manda a última peça que resta e para; não começa o próximo produto no mesmo sábado |
| Peça de peptídeos sem campo `aviso` | Não quebra nada — só aparece no log de `semear()` como aviso |

## Testes

- Migração das 3 tabelas é idempotente.
- `produto_do_assinante`: meio de A + B ativo → continua A; concluiu tudo + B ativo → cai em B;
  nenhum produto ativo + nunca começou nada → `None`.
- `enviar_para` manda 2 peças pra peptídeos e 1 pra empreendedorismo, respeitando fim de trilha no
  meio do lote.
- Trocar produto ativo no admin não altera `trilha_progresso` de quem já está em outro produto.
- Bloco `.alerta` aparece só quando `aviso` não é vazio; nunca aparece na trilha de
  empreendedorismo (peças de lá não têm o campo preenchido).
- `semear()` reporta contagem de peças de "peptideos" sem `aviso`.

## Fora de escopo

- **O texto das 11 peças.** Esta spec define formato, catálogo e motor; escrever o conteúdo é
  trabalho separado (como foi com a trilha de empreendedorismo).
- **O nome da trilha de peptídeos** — placeholder no catálogo até o Diego decidir.
- **Confirmar o status ANVISA inferido** de Sermorelin e Kisspeptina (não nomeados em nenhum
  alerta oficial) — checar antes de publicar essas duas peças especificamente.
- Qualquer trilha além dessas duas (o catálogo já suporta, mas não há uma terceira desenhada).
