# Projeto E — Termos, Privacidade & Arrependimento — Design

**Data:** 2026-07-24
**Status:** Design aprovado pelo Diego (aguardando revisão do spec)
**Host:** `artigos.drdiegosilva.com.br` (produto assinatura). Não toca no `curso.` (Projetos A/B).

## Contexto

O site vende assinatura recorrente para médicos e **não tem contrato nenhum**. Grep por
`termos|privacidade|lgpd|contrato` em `app/` não retorna uma linha: não existe página de
termos, não existe política de privacidade, e não existe aceite em lugar algum do checkout.

O que já existe hoje no cancelamento (`serve.py:692-747`):

- `/cancelar` exige motivo → oferta de retenção (adia o vencimento 30 dias, 1× por assinante,
  via `asaas.adiar_vencimento`) → confirmação.
- `_executar_cancelamento` (`serve.py:729`) chama `asaas.cancelar_assinatura(sid)`
  (`DELETE /subscriptions/{id}`) — que **só interrompe cobranças futuras** — grava `CANCELADO`
  com `acesso_ate = proximo_vencimento` e manda e-mail de confirmação.
- **Nenhum valor é devolvido, em nenhuma hipótese.**

E o webhook já fecha metade do ciclo de estorno: `PAYMENT_REFUNDED` cai em `SUSPENDER`
(`webhook_asaas.py:22` e `:176`), que marca `CANCELADO` com `acesso_ate` = agora. Ou seja,
**um estorno feito no painel do Asaas já corta o acesso sozinho hoje.**

Origem deste projeto: a pergunta era "dá pra reembolsar automaticamente o restante de um plano
anual cancelado?". A resposta técnica é sim (o Asaas suporta estorno parcial), mas a decisão de
negócio eliminou o caso — ver Decisão 2. O que sobrou é o que faltava de verdade: contrato.

## Objetivo

1. Publicar `/termos` e `/privacidade` versionados, com o controlador identificado de verdade.
2. Capturar aceite: no checkout para novos assinantes, e por re-aceite para a base atual.
3. Automatizar o **único** reembolso que existe: o direito de arrependimento de 7 dias (CDC art. 49),
   sempre integral.
4. Reverter a comissão de afiliado quando a venda for estornada.

## Decisões

| # | Questão | Decisão |
|---|---|---|
| 1 | Escopo do documento | Termos de Uso **e** Política de Privacidade (LGPD), com aceite versionado |
| 2 | Reembolso após os 7 dias | **Nenhum.** Acesso segue até o fim do período pago — que é o que o código já faz |
| 3 | Dentro dos 7 dias | Estorno **integral automático** via API do Asaas, sem intervenção humana |
| 4 | Base atual de assinantes | Re-aceite bloqueando a área de conta (`/minha` e `/meus-dados`) no próximo login. **O envio diário não para** |

Consequência da Decisão 2: **não existe cálculo pro-rata neste projeto.** A calculadora que
originou a conversa deixou de ser necessária. Cancelou depois dos 7 dias → R$ 0,00 e acesso
até o fim.

### Controlador (para a Política de Privacidade)

- **Razão social:** Clínica Diego Silva LTDA
- **CNPJ:** 52.891.914/0001-93 *(dígitos verificadores conferidos)*
- **Endereço:** Av. Adhemar Pereira de Barros, 1500, sala 203 — Londrina/PR, CEP 86047-250
- **Encarregado (DPO) / canal do titular:** `contato@drdiegosilva.com.br` (o `config.ADMIN_EMAIL` já configurado)
- **CNAE:** treinamento — a venda da assinatura está dentro da atividade registrada da PJ

### Redação das cláusulas críticas

**Cláusula 4.2 — reembolso após o arrependimento** (cláusula restritiva: exige destaque
visual, CDC art. 54 §4):

> "O cancelamento do plano Anual após o prazo de arrependimento interrompe as cobranças
> futuras, NÃO gerando reembolso dos valores já pagos. O acesso permanece ativo até o término
> do período contratado."

**Cláusula de foro** — eleição de foro contra consumidor é nula (CDC art. 51, IV c/c art. 101, I),
então a redação preserva o direito do consumidor:

> "Fica eleito o foro da Comarca de Londrina/PR para dirimir controvérsias, ressalvado ao
> CONSUMIDOR o direito de ajuizar ação no foro de seu domicílio, nos termos do art. 101, I, do CDC."

**Cláusula 2 — renovação automática.** O documento precisa dizer explicitamente que cartão
renova sozinho e Pix não renova (ver "Renovação automática" em Riscos), porque é a maior fonte
potencial de contestação e chargeback.

## Arquitetura

Segue o padrão do repositório: lógica pura e testável separada da rede e do HTML, stdlib apenas,
módulos pequenos.

### Módulos novos

| Arquivo | Responsabilidade | Puro |
|---|---|---|
| `app/legal.py` | Texto dos termos e da privacidade + `VERSAO` (`"2026-07-24"`). Só conteúdo — o layout continua no `site_web` | sim |
| `app/refunds.py` | `dentro_arrependimento(compra, hoje, dias=7)` e `alvo_estorno(pagamento)` | sim |

`alvo_estorno` resolve o problema do cartão parcelado: lê o campo `installment` do pagamento e
devolve `("installment", id)` ou `("payment", id)`. Sem isso, um "estorno integral" de um anual
em 12× devolveria apenas a parcela 1 (R$ 83 em vez de R$ 997).

**Data de referência dos 7 dias:** `subscribers.criado_em`, que é gravado em
`criar_de_pagamento` no momento em que o webhook confirma o pagamento — ou seja, é a data da
contratação efetiva, que é o marco do art. 49 do CDC. Não usar `proximo_vencimento` nem a data
do `pending` (que é anterior ao pagamento e pode nunca ter virado venda).

**Assinante sem pagamento (cortesia por cupom):** `criar_de_pagamento` é chamado com
`dados_asaas={}` no fluxo de cupom (`serve.py:774`), então `asaas_payment_id` fica nulo. Nesse
caso não há o que estornar — o fluxo pula o estorno e segue o cancelamento normal, sem alertar
o admin (não é falha, é ausência de cobrança).

### Funções novas em `asaas.py`

```python
def estornar_pagamento(pid, valor=None)      # POST /payments/{id}/refund
def estornar_parcelamento(iid, valor=None)   # POST /installments/{id}/refund
```

Mesmo padrão das existentes: `_req`, log server-side do corpo do erro, nunca vaza resposta crua
do Asaas para o cliente. `valor=None` = estorno total (é sempre o caso aqui).

### Banco (`db.py`, migração idempotente no `init()`)

- `subscribers` += `termos_versao`, `termos_aceito_em`, `termos_ip`
- `comissoes` += `estornada_em`
- Nova função `db.estornar_comissao(subscriber_id)`

### Fluxos

**Aceite (novo assinante):** checkbox obrigatório no `/assinar` → validado no POST → gravado no
`pending` → copiado para o assinante na ativação (`webhook_asaas._executar`, ramo `ATIVAR`).

**Re-aceite (base atual):** ao abrir `/meus-dados`, se `termos_versao != legal.VERSAO`, exibe a
tela de aceite bloqueando a página. O envio diário de estudos **não** é interrompido — o
assinante continua recebendo o que pagou.

**Cancelamento:**

```
_executar_cancelamento (serve.py:729)
   │
   ├─ refunds.dentro_arrependimento(compra, hoje)?
   │     SIM → GET /payments/{asaas_payment_id}
   │           refunds.alvo_estorno(pagamento)
   │             ├─ ("installment", id) → asaas.estornar_parcelamento(id)
   │             └─ ("payment", id)     → asaas.estornar_pagamento(id)
   │           db.estornar_comissao(sub_id)
   │           e-mail: "reembolso integral de R$ X em até 10 dias úteis"
   │
   └─    NÃO → fluxo atual: acesso até proximo_vencimento, R$ 0,00
```

Os 7 dias só alcançam a **primeira** cobrança, que é exatamente o id guardado em
`asaas_payment_id`. O problema conhecido de esse campo não ser atualizado no `RENOVAR`
(`webhook_asaas.py:164-169`) **não afeta** este fluxo.

### Tratamento de erro

Falha no estorno (sem saldo na conta Asaas, erro de API, timeout) **não bloqueia o
cancelamento**. O assinante nunca fica preso por um problema nosso: o cancelamento conclui,
o sistema registra a pendência e dispara `_alertar_admin` (que já existe, `webhook_asaas.py:56`).
O Diego resolve no painel e o webhook `PAYMENT_REFUNDED` fecha o ciclo cortando o acesso.

## Sequenciamento

O checkbox de aceite vive em `pagina_assinar` (`site_web.py:1428`) e `_post_assinar`
(`serve.py:749`) — os mesmos arquivos que **outro agente** está editando no branch
`feat/landing-copy-pizza` (preços e landing). Por isso:

1. `legal.py`, `refunds.py`, `asaas.py`, migrações do `db.py` e o fluxo de cancelamento — podem
   começar imediatamente, zero sobreposição.
2. Páginas `/termos` e `/privacidade` + re-aceite no `/meus-dados` — sem sobreposição.
3. **Checkbox no checkout — por último**, e só depois de verificar que o outro agente entregou.

## Testes (unittest, padrão dos 215 existentes)

- `dentro_arrependimento`: dia 0, dia 7 (inclusivo), dia 8, data ausente, data malformada
- `alvo_estorno`: pagamento simples → `("payment", id)`; pagamento com `installment` → `("installment", id)`
- Aceite: POST sem checkbox → erro na página; com checkbox → grava versão + timestamp + IP
- Re-aceite: `termos_versao` antiga → bloqueia `/meus-dados`; versão atual → passa
- Cancelamento no dia 3 → chama estorno; no dia 30 → não chama
- Cancelamento no dia 3 de assinante por cupom (sem `asaas_payment_id`) → não chama estorno e não alerta
- Estorno lança exceção → cancelamento conclui mesmo assim + admin alertado
- Comissão de afiliado marcada como estornada quando a venda é estornada

## Fora do escopo

- Cálculo pro-rata e estorno parcial (eliminados pela Decisão 2)
- Tela de estornos no admin
- Desconto de 5% no Pix (outro agente)
- Correção do preço founder no checkout (ver Riscos — território do outro agente)

## Riscos e pendências

**1. Preço founder não chega no checkout (bug pré-existente, não é deste projeto).**
A landing usa `pricing.preco_str_vigente` corretamente (`site_web.py:382`), mas
`_pick_planos` (`site_web.py:1419`) usa `p["preco"]` fixo e `pagina_assinar`
(`site_web.py:1433`) usa `plano["base"]` fixo, enquanto `_post_assinar` (`serve.py:791`)
cobra `pricing.preco_vigente`. No 21º assinante ativo (`FOUNDER_LIMITE = 20`) a página
anuncia R$ 997 e o Asaas cobra R$ 1.497. Repassado ao agente que cuida de preços.

**2. Renovação automática do anual no cartão nunca foi verificada. [EM ABERTO]**
O docstring do `asaas.py:5-6` registra a dúvida: o Asaas aceita `RECURRENT` +
`installmentCount` juntos? A conta é a real, não sandbox. Se o Asaas ignorar silenciosamente
um dos dois, ou cobra R$ 997 à vista no cartão do médico, ou o anual não renova e isso só
aparece daqui a 12 meses.

Isso **não bloqueia o projeto** — afeta uma única frase da cláusula 2 (a que descreve a
renovação). Por isso a cláusula 2 é a **última** coisa a ser redigida, e a publicação de
`/termos` fica condicionada a confirmá-la. Formas de verificar, da mais simples para a mais cara:

1. Painel do Asaas → *Assinaturas*: existe alguma com ciclo Anual? (só funciona se já houver
   venda anual no cartão)
2. `GET /subscriptions` + `GET /payments?subscription=` — read-only, script pronto em
   `scratchpad/verificar_recorrencia.py`
3. `POST /checkouts` com o payload real e leitura da resposta crua — não cobra ninguém, cria
   só um link; script pronto em `scratchpad/testar_checkout_anual.py`
4. Venda de teste real: plano oculto `YEARLY` de R$ 60 em 12× (R$ 5/parcela é o mínimo do
   Asaas), comprar, conferir no painel e estornar

Decisão do Diego em 2026-07-24: adiado, sem bloquear o resto.

**3. Pix não renova, em nenhum plano.** `montar_checkout` (`asaas.py:48-51`) manda Pix como
`DETACHED`. O `config.py:70` menciona `recorrente_pix = Pix Automático` e o campo existe nos
planos, mas `montar_checkout` ignora. Os termos precisam dizer isso com clareza, sobretudo
com o desconto de 5% no Pix empurrando volume para o método que expira.
