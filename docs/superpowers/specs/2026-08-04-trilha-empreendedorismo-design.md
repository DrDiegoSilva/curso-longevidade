# Trilha de Empreendedorismo Médico — design

**Data:** 2026-08-04
**Status:** spec aprovada no brainstorm, aguardando plano de implementação

## O problema

A assinatura entrega um estudo científico por dia útil (seg–sex). O assinante é médico de
emagrecimento, estética e reposição hormonal — e o que trava o negócio dele **não é
conhecimento clínico**, é gestão: não sabe o custo da própria hora, vende consulta avulsa em vez
de plano, pede desculpa pelo preço e perde o paciente no mês 2.

A trilha ocupa o **sábado** (hoje vazio) com uma peça semanal de empreendedorismo médico.

## Decisões do brainstorm

| Decisão | Escolha | Por quê |
|---|---|---|
| Origem do conteúdo | **Evergreen**, escrito uma vez | Gestão não envelhece como paper. Zero custo de IA por semana e zero risco de a máquina falar besteira de negócio pra público pagante. |
| Cadência | **Drip por assinante** | A semana 12 pressupõe a 11. Broadcast entregaria a trilha pela metade a quem entra no meio. |
| Dia | **Sábado**, no horário que o assinante já escolheu | Fim de semana está livre (`agenda_plan.py:11` — estudo roda seg–sex). Não disputa atenção nem dobra volume no WhatsApp. Reusa a máquina de slots, então quem pediu 18h recebe 18h. |
| Formato | **PDF no WhatsApp** + link clicável para a ferramenta no site | Um anexo só no zap (vários viram bagunça). O PDF já sabe fazer link clicável. Download no site é porta fechada e dá sinal de engajamento. |
| Tamanho | **12 peças — Temporada 1** | Valida o formato com médicos reais antes de escrever 40 peças. |

## Pesquisa de referências

Levantamento de 12 referências do mercado brasileiro (dossiês completos no histórico da sessão).
O que mudou o design:

- **Endogin** (Dr. Caio Saraiva + Dr. Vinicius Carruego, jan/2024) é o espelho quase exato: mesmo
  nicho (emagrecimento + TRH), e um dos três eixos do produto deles **já é mentalidade/negócio**.
  Saíram de 5 para 300+ médicos. Ticket de R$10.997 a R$36.000.
- **Doc4u** (Davison Carvalho + Flávio Augusto) é o modelo da sociedade que o Diego está montando:
  médico com autoridade clínica + sócio com perfil comercial. Bio: "Vendas Curam".
- **Todas as 12 referências têm um framework com nome próprio** — 7 Pilares, FODA, Pentagrama,
  Método Endogin, Destino, Geração de Valor, Estética Ryka. Sem exceção. Por isso a trilha nasce
  com **marca em config, não hardcoded**: o nome vem depois, no brainstorm de naming com o sócio.
- **Todas têm escada de produto.** A assinatura tem um degrau só (R$147/mês). A trilha é o degrau
  de baixo de uma escada que ainda não existe.
- **Todas têm mecanismo de cobrança** (grupo, missão, encontro, ranking). A trilha, sem
  intervenção, só mandaria PDF e torceria.
- A tese de mentalidade do nicho já está escrita, por médicos: *"nunca aceitei que médico bom
  precisava viver pequeno"* (Saraiva), *"riqueza e tempo livre sem corromper a alma"* (Endogin),
  *"menos é mais — menos pacientes, mais certos"* (Gladia Bernardi).

Ressalvas registradas: preços de programas de mentalidade voltaram desatualizados ou não
confirmados — **nenhum serve de referência de precificação**. A formação clínica de Gladia
Bernardi é autodeclarada, sem registro em conselho confirmado nas fontes.

## Anatomia da peça

Três camadas fixas, sempre nesta ordem:

1. **Micro-resultado** — uma ação pequena, executável no fim de semana, **com um número
   verificável**. ("Aquilo que não é medido não é melhorado" — Caio Carneiro.) Não é tarefa vaga.
2. **Insight** — o raciocínio de negócio que sustenta a ação.
3. **Mentalidade** — a camada de cabeça de dono.

Quando o tema pede, a peça leva uma **ferramenta** (planilha, roteiro, modelo) — link clicável no
PDF para `/ferramentas/<slug>`, fechado por sessão de assinante.

Capa mostra **"Semana N de 12"**.

## As 12 semanas

**Bloco 1 · Saber onde você está**
1. O custo real da sua hora — *nº: R$/hora*
2. De médico que atende a dono que decide *(mentalidade)*
3. Escolher **uma** linha de tratamento — *ferramenta: mapa de linha*

**Bloco 2 · Construir a oferta**
4. Do avulso ao plano de acompanhamento — *ferramenta: modelo de plano*
5. Precificação sem culpa — *ferramenta: planilha de precificação*
6. Por que ele te escolhe e não o vizinho *(posicionamento)*

**Bloco 3 · Vender e reter**
7. A consulta que vende sozinha — *ferramenta: roteiro de 5 perguntas*
8. "Você não está fazendo uma venda, está sofrendo uma compra" *(mentalidade)*
9. O paciente que some no mês 2 — *régua D+7/D+30/D+90; nº: % que chega ao mês 3*

**Bloco 4 · Escalar sem se destruir**
10. Quantos planos cabem em você — *nº: teto de pacientes*
11. De onde vem o próximo paciente *(aquisição)*
12. O painel do dono — *ferramenta: painel de 5 números*

Emagrecimento puxa o exemplo do começo ao fim. Estética e hormonal entram como segunda linha na
Temporada 2, junto com delegação/primeira contratação — aquisição e posicionamento são mais
urgentes que delegar.

As peças **7 e 8 são do sócio comercial**: são as de venda e ele tem mais autoridade nelas.

## Arquitetura

Módulo **`trilha.py`** próprio. **Não encosta em `daily.py`** — se quebrar, quebra sozinho.

Descartado: encaixar na tabela `agenda` (é global por dia, não comporta drip por assinante) e
reusar `series.py` (séries ocupam dias úteis globais e carregam estudos, não peças evergreen).

### Tabelas

- **`trilha_pecas`** — `numero`, `eixo`, `titulo`, `corpo`, `micro_resultado`, `mentalidade`,
  `ferramenta_slug`, `ativa`. As peças vivem em `seed/trilha/` e são semeadas no banco, mesmo
  padrão de `seed/base`.
- **`trilha_progresso`** — `subscriber_id`, `proxima_peca`, `ultimo_envio`. A posição de cada
  médico na trilha.
- **`trilha_envios`** — ledger com unicidade em `(subscriber_id, numero)`, mais `feito_em`
  (nulo até o assinante clicar "✅ fiz"). Mesma defesa que `envios_dia` deu contra o 2x/0x.

### Entrega

Sábado, com função de envio **própria** em `trilha.py`, que percorre os mesmos slots de horário
que o assinante já escolheu (o horário mora em `subscribers`, não em `daily.py`). Reusa `pdf.py`
e `deliver.enviar_pdf`. Não chama `daily.enviar_slot` — o motor diário fica intocado; o que se
reaproveita é o **conceito** de slot e as tabelas de assinante, não o código de estudo.

### Rotas

- `/trilha` — área do assinante: peça da semana, histórico, botão **"✅ fiz"**, download da
  ferramenta. Reusa a sessão de `/minha` (`serve.py:490`).
- `/ferramentas/<slug>` — download fechado por sessão.
- `/admin/trilha` — quem está em qual semana, quantos marcaram "fiz", quem concluiu.

### Accountability

**Não haverá canal de entrada no WhatsApp.** O único webhook de entrada hoje é o do Asaas
(`serve.py:578`); receber mensagem exigiria canal novo, telefone virando identidade e texto livre
pra interpretar. Fora de escopo nesta temporada.

A cobrança é o botão **"✅ fiz"** no site (um clique, sem formulário) e a **peça seguinte abre
reconhecendo ou retomando**, conforme ele tenha marcado ou não.

## Estados e falhas

| Situação | Comportamento |
|---|---|
| Envio falha | `trilha_envios` só grava no sucesso e `proxima_peca` só avança junto. Ele recebe a **mesma** peça no sábado seguinte. Nunca pula conteúdo. |
| Assinante novo | `trilha_progresso` nasce em `proxima_peca = 1`. Assinante antigo na estreia idem. |
| Cancelado ou vencido | Não recebe. Mesma checagem do estudo diário, sem regra nova. |
| Concluiu as 12 | Para de receber; aparece no admin como concluído. É a melhor lista para uma oferta de tíquete alto — o sistema apenas mostra quem chegou lá, não vende nada sozinho. |
| Peça 13 | Não existe e não quebra. |

## Testes

TDD, seguindo o padrão do repo:

- não envia duas vezes no mesmo sábado
- não avança a posição se o envio falhar
- assinante novo entra na peça 1
- cancelado não recebe
- concluído para de receber
- peça 13 não existe e não quebra
- download da ferramenta barra quem não tem sessão
- "✅ fiz" é idempotente (clicar duas vezes não duplica registro)

## Fora de escopo

- **O texto das 12 peças.** Esta spec define formato e esqueleto; escrever é trabalho separado.
- **O nome e o framework** da trilha — brainstorm de naming com o sócio, depois.
- **A oferta de tíquete alto** que a trilha alimenta. Decisão de negócio, não de software.
- **Canal de entrada no WhatsApp.**
- Delegação e segunda linha de tratamento (Temporada 2).
