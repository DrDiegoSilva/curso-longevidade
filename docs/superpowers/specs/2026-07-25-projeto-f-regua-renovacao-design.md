# Projeto F — Régua de renovação — Design

**Data:** 2026-07-25
**Status:** Design aprovado pelo Diego (aguardando revisão do spec)
**Host:** `artigos.drdiegosilva.com.br` (produto assinatura). Não toca no `curso.` (Projetos A/B).
**Depende de:** [Projeto E](2026-07-24-projeto-e-termos-arrependimento-design.md) — o e-mail de
confirmação de renovação e a guarda contra assinante duplicado já existem e são alterados aqui.

## Contexto

Depois do Projeto E, o sistema sabe distinguir quem renova sozinho de quem não renova. O Diego
verificou no painel do Asaas em 2026-07-25:

- **Cartão à vista** ativa a recorrência — renova sozinho.
- **Cartão parcelado** NÃO ativa a recorrência — não renova.
- **Pix** é `DETACHED` (`asaas.py:48`) — nunca renovou.

Como o anual é vendido em até 12×, **a maior parte das vendas do anual não renova**. Essas
pessoas simplesmente param de receber os estudos no fim do período, sem que nada as avise a
tempo de agir.

O que existe hoje é insuficiente: `billing_notices.avisar_pre_renovacao` manda **um** e-mail,
3 dias antes, com texto que hedge ("se for recorrente renova sozinha; se foi Pix à vista, é só
renovar") porque na época não dava pra saber qual era o caso.

E há um bloqueio pior: **não existe caminho de renovação**. O checkout recusa quem ainda tem
acesso (`serve.py`, `_post_assinar`):

```python
ja = subscribers.por_cpf(dados["cpf"]) or subscribers.por_whatsapp(dados["whatsapp"])
if ja and subscribers.tem_acesso(ja):
    return "Já existe uma assinatura ativa com esse CPF ou WhatsApp."
```

Ou seja: um aviso de "renove" mandaria o assinante para uma tela que diz "você já tem
assinatura ativa". Só depois de perder o acesso ele conseguiria voltar.

## Objetivo

1. Criar o caminho de renovação (`/renovar`) para quem já é assinante.
2. Avisar, pelo canal certo e com antecedência configurável, quem precisa agir.
3. Recuperar quem deixou vencer, com um bônus que não corrói o preço.

## Decisões

| # | Questão | Decisão |
|---|---|---|
| 1 | Como o assinante renova | **Rota `/renovar` própria**, logado. Não liberar o `/assinar` |
| 2 | Preço da renovação | **O valor que ele contratou**, não o de tabela. Founder renova como founder |
| 3 | Plano mensal | **Pix sai do mensal.** Mensal passa a ser só cartão, que renova sozinho |
| 4 | Público da régua | **Só o anual sem renovação automática**: Pix e cartão parcelado |
| 5 | Incentivo | **+1 mês de acesso, não desconto.** Só na renovação **depois** do vencimento |
| 6 | Cadência | Configurável pelo Diego na tela — não são períodos fixos no código |
| 7 | Padrão de cadência | **−7, −3, 0, +1, +3, +15** dias relativos ao vencimento |
| 8 | Canal | Escolhido **por automação**; o padrão das seis é WhatsApp |
| 9 | Cupom de afiliado na renovação | **Não vale.** A comissão é só na 1ª venda, o desconto também |
| 10 | Desconto Pix na renovação | **Vale**, como em qualquer compra |

### Por que `/renovar` e não liberar o `/assinar`

O formulário de assinatura pede CPF e WhatsApp digitados. O webhook casa o pagamento com o
assinante existente **por esses dois campos** (guarda do Projeto E). Um dígito errado e o
sistema não reconhece: cria assinante novo, manda boas-vindas de cliente novo, e o cliente fica
com duas contas — o mesmo bug que o Projeto E acabou de fechar, reaberto pela porta da frente.

Na rota própria o assinante já está autenticado: plano, preço e vencimento vêm do cadastro,
não do teclado. E as regras de renovação (sem cupom de afiliado, Pix 5%, bônus de resgate)
ficam num lugar só, em vez de espalhadas por condicionais dentro de um formulário desenhado
para clientes novos.

### Por que o bônus só depois de vencer

Registrado o trade-off, porque a escolha foi consciente: essa regra ensina que deixar vencer
rende mais que renovar em dia. O Diego aceitou porque, se a régua funcionar, poucos chegam ao
resgate — e assim o bônus não é pago a quem renovaria de qualquer jeito.

### Mapa de canais

| Mensagem | Quem recebe | Canal |
|---|---|---|
| Régua (−7, −3, 0) | anual sem renovação automática | WhatsApp |
| Resgate (+1, +3, +15) | venceu e não renovou | WhatsApp |
| Confirmação de renovação **automática** | cartão à vista / mensal | E-mail |
| Confirmação de renovação **manual** | quem renovou pelo `/renovar` | WhatsApp |
| Boas-vindas | primeira compra | WhatsApp + e-mail *(inalterado)* |

Nenhuma mensagem sai nos dois canais: quem precisa **agir** é avisado onde lê (WhatsApp); quem
só precisa ser **informado** de uma cobrança que já aconteceu recebe por e-mail, que serve de
comprovante.

## Arquitetura

### Banco

**`automacoes_renovacao`** — uma linha por disparo configurado:

| coluna | tipo | significado |
|---|---|---|
| `id` | TEXT PK | |
| `dias` | INTEGER | offset relativo ao vencimento: negativo antes, `0` no dia, positivo depois |
| `canal` | TEXT | `whatsapp` ou `email` |
| `texto` | TEXT | template com marcadores |
| `ativo` | INTEGER | liga/desliga sem apagar |
| `criado_em` | TEXT | |

Seed idempotente das seis padrão (−7, −3, 0, +1, +3, +15, todas `whatsapp`), no mesmo estilo do
`_seed_cupons` que já existe em `db.py`.

**`avisos_renovacao_enviados`** — ledger de idempotência:

| coluna | significado |
|---|---|
| `subscriber_id` | |
| `automacao_id` | |
| `vencimento_ref` | a data de vencimento vigente quando o aviso saiu |
| `enviado_em` | |

Chave única em `(subscriber_id, automacao_id, vencimento_ref)`. É o mesmo padrão do `envios_dia`
(`db.py:334`) que resolveu o reenvio duplicado dos estudos: sem ele, um restart do processo no
meio do dia reenviaria a régua inteira. O `vencimento_ref` é o que permite a régua rodar de novo
no ciclo seguinte sem "lembrar" que já avisou no ciclo anterior.

**`subscribers`** ganha `valor_contratado` (REAL). Hoje o valor pago não é gravado em lugar
nenhum — existe só no `pending_signups` e no Asaas. Sem ele não dá para cumprir a Decisão 2.
Preenchido na ativação a partir do valor do pagamento. Para quem já é assinante, fica nulo e o
`/renovar` cai no preço base do plano (founder), que é o que essas pessoas pagaram.

### Módulos

| Arquivo | Responsabilidade | Puro |
|---|---|---|
| `app/regua.py` | **Criar.** `offset_vencimento(vencimento, hoje)`, `na_regua(sub, plano)` (quem entra), `automacoes_do_dia(automacoes, offset)` | sim |

**Convenção de sinal (fonte de bug se ficar implícita):** `offset_vencimento` devolve
`hoje - vencimento` em dias. Faltando 7 dias para vencer o valor é **−7**; no dia do
vencimento é **0**; 15 dias depois de vencido é **+15**. É a mesma convenção do campo `dias`
da automação, então o casamento é igualdade direta, sem inversão de sinal em lugar nenhum.

**Como o código sabe quem "não tem renovação automática":** pela presença de
`subscribers.asaas_subscription_id`. Cartão à vista e mensal criam assinatura recorrente no
Asaas e têm esse campo preenchido; Pix (`DETACHED`) e cartão parcelado não têm. É o mesmo
sinal que o webhook já usa para decidir entre `ATIVAR` e `RENOVAR`, e o mesmo que o Projeto E
usa para gravar `acesso_ate` só em quem não renova sozinho — não inventar um critério novo.
| `app/renovacao.py` | **Criar.** `preco_renovacao(sub, plano)`, `novo_vencimento(acesso_ate, hoje, ciclo, bonus)` | sim |

Lógica pura separada de rede, banco e HTML, como no resto do repositório. O disparo em si
(percorrer assinantes, mandar WhatsApp/e-mail, gravar ledger) fica no orquestrador, testável
com fakes.

### Fluxos

**Disparador diário** — roda na rotina das 08h que já existe no agendador (`serve.py:64`), junto
do `avisar_pre_renovacao`, que passa a cobrir só quem tem renovação automática:

```
para cada assinante do anual, SEM asaas_subscription_id e SEM cancelado_em:
    d = offset_vencimento(vencimento, hoje)     # -7 = faltam 7 dias; +15 = venceu há 15
    para cada automação ativa com dias == d:
        se já está no ledger (assinante, automação, vencimento_ref): pula
        envia pelo canal da automação
        grava no ledger
```

**O público inclui quem já venceu** — é para eles que existem as automações de offset
positivo. Não há janela de corte: quem venceu há 400 dias tem offset `+400`, que não casa com
automação nenhuma, então some da régua naturalmente.

**Quem cancelou a renovação fica de fora, inclusive do resgate.** Ele comunicou a decisão de
sair; insistir no WhatsApp depois disso é o caminho mais curto para o bloqueio. Se um dia o
Diego quiser reativar esse grupo, é uma automação nova com critério próprio, não um efeito
colateral desta.

Cada envio é isolado: falha em um assinante não interrompe os demais, e nunca pode afetar o
envio dos estudos.

**`/renovar`** (GET, exige sessão de assinante):
mostra plano, vencimento, valor contratado, e as opções Pix (com −5%) e cartão. Se o acesso já
expirou, mostra o bônus de +1 mês. **Não** tem campo de cupom.

**`/renovar` (POST):** monta o checkout no Asaas com o valor da Decisão 2, grava um `pending`
marcado como renovação, e redireciona. Na confirmação do pagamento, o webhook já reconhece o
assinante existente (guarda do Projeto E) e estende o período — a partir do **fim atual** quando
ainda há acesso, ou de hoje quando já expirou, somando o bônus nesse segundo caso.

### Alterações no que já existe

- `config.PLANOS`: mensal deixa de oferecer Pix; o checkout esconde o tile de Pix nesse plano.
- `webhook_asaas._confirmar_renovacao` se divide por canal: renovação **automática** segue no
  e-mail; renovação **manual** passa para o WhatsApp.
- `billing_notices.avisar_pre_renovacao` passa a alcançar **só** quem tem renovação automática —
  o resto é da régua.
- Ativação grava `valor_contratado`.

## Erros

Falha de envio (WhatsApp fora do ar, e-mail recusado) é registrada e **não** grava o ledger,
para que a próxima execução tente de novo — mas só enquanto o dia da automação for o de hoje;
passado o dia, aquele disparo é perdido de propósito, em vez de sair atrasado e confuso ("seu
acesso termina em 7 dias" chegando no dia 3).

Falha ao montar o checkout no `/renovar` devolve a página com mensagem clara, sem criar
`pending` órfão.

## Testes

- `dias_ate`: dia do vencimento, véspera, dia seguinte, data ausente, data malformada
- `na_regua`: anual no Pix entra; anual parcelado entra; anual à vista fica fora; mensal fica
  fora; cancelado fica fora
- `automacoes_do_dia`: casa só o offset exato; automação inativa não dispara
- Idempotência: rodar o disparador duas vezes no mesmo dia envia uma vez só
- Ciclo seguinte: o mesmo assinante recebe de novo quando o `vencimento_ref` muda
- `preco_renovacao`: usa `valor_contratado` quando existe; cai no base do plano quando é nulo
- `novo_vencimento`: com acesso vigente estende a partir do fim atual; expirado conta de hoje;
  bônus só no caso expirado
- `/renovar`: sem sessão redireciona; não aceita cupom; Pix aplica 5%
- Falha de envio não grava ledger e não interrompe os outros assinantes

## Fora do escopo

Pix Automático; mudança de plano na renovação; automações que não sejam de vencimento;
recuperação de carrinho abandonado; qualquer mensagem no WhatsApp que não esteja no mapa de
canais.

## Riscos

**1. WhatsApp é canal sensível.** Seis mensagens por ciclo, sendo três depois de a pessoa já ter
escolhido sair, é o limite do aceitável. Bloqueio ou denúncia no WhatsApp não afeta só a régua —
afeta o canal de entrega do produto. O construtor de automações permite ao Diego reduzir, e o
padrão de três resgates deve ser revisto com dados reais.

**2. `valor_contratado` nulo na base atual.** O fallback (preço base do plano) está correto para
os assinantes de hoje, que entraram no preço de lançamento. Se o preço founder mudar antes de
essa base renovar, o fallback passa a mentir. Prazo de validade: até a primeira renovação da
base atual.
