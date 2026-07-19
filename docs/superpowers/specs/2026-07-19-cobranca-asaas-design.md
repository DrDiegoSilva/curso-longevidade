# Cobrança Asaas — Assinatura "Atualização Científica" — Design

**Data:** 2026-07-19
**Produto:** `curso-longevidade` (app isolado). Depende do site `artigos.` (landing + arquivo protegido) já construído.

## Objetivo

Vender a assinatura: o médico assina na landing, paga pelo **checkout hospedado do Asaas** (a gente nunca toca em dado de cartão), e é **ativado automaticamente por webhook**. Renovação, inadimplência, cupom e cancelamento self-service resolvidos.

## Decisões (brainstorm 19/07)

- **Formas de pagamento:** cartão + Pix Automático.
- **Cobra na hora** (sem trial).
- **Carência de 3 dias** no atraso (o cartão do Asaas retenta 5× em ~3 dias).
- **Cancelamento com atrito:** motivo obrigatório → oferta de +1 mês grátis → confirmação por **e-mail** (canal discreto).
- **Cupom** libera cadastro grátis (Diego se cadastra com nº real; cortesias).
- **Checkout hospedado** (zero PCI). `externalReference` amarra o pagamento ao cadastro.

### Modelo de cobrança por plano

| Plano | Ciclo Asaas | Valor | Pagamento |
|---|---|---|---|
| Mensal | MONTHLY | R$ 99 | **Recorrente** — Pix Automático (99 flat) **ou** cartão (99 + taxa) |
| Trimestral | QUARTERLY | R$ 269 | **Cartão** recorrente (parcelável, + taxa) **ou** **Pix à vista** (valor cheio, não renova) |
| Semestral | SEMIANNUALLY | R$ 499 | idem |
| Anual | YEARLY | R$ 960 | idem |

- **Cartão** = assinatura Asaas que **renova sozinho** no fim do período; **parcelável até 12×**; valor com **gross-up da taxa exata** (Asaas credita o valor cheio).
- **Pix à vista** (planos maiores) = cobrança avulsa pelo valor cheio, **não renova** → aviso pra recomprar.
- **Aviso discreto por e-mail ~3 dias antes** de cada renovação/vencimento (reduz surpresa/chargeback).

## Arquitetura

### Cliente Asaas — `app/asaas.py`
- Base: `ASAAS_BASE_URL` (sandbox `https://api-sandbox.asaas.com/v3` → prod `https://api.asaas.com/v3`), header `access_token: <ASAAS_API_KEY>`. stdlib `urllib`.
- Funções: `criar_checkout(payload)`, `cancelar_assinatura(sub_id)`, `adiar_vencimento(sub_id, dias)`, `obter_cliente(cid)`, `obter_pagamento(pid)`. Erros logados server-side, nunca vazam cru.
- **Checkout recorrente** (cartão/mensal-pix): POST `/checkouts` com `chargeTypes:["RECURRENT"]`, `billingTypes`, `subscription:{cycle,nextDueDate}`, `installmentCount` (cartão parcelado), `value` (já com gross-up no cartão), `customerData:{name,cpfCnpj,email,phone}`, `externalReference:<token>`, `callback:{successUrl:/obrigado, ...}`. Retorna URL de checkout.
- **Checkout avulso** (Pix à vista dos planos maiores): `chargeTypes:["DETACHED"]`, `billingTypes:["PIX"]`, `value` (valor cheio), mesmo `externalReference`.

### Cálculo da taxa de cartão — `app/pricing.py` (puro, TDD)
- `TAXA_CARTAO` (config): `{"avista":0.0299, "ate6":0.0349, "ate12":0.0399}` + fixo `R$0,49` (defaults do Asaas; **Diego troca pelas taxas reais**).
- `valor_cartao(base, parcelas)` → **gross-up**: `value = (base + fixo) / (1 - pct(parcelas))`, arredondado a 2 casas (Asaas credita ≈ base).
- `faixa(parcelas)` → avista/ate6/ate12.
- `opcoes_parcelas(base)` → lista `[{parcelas, total, por_parcela}]` p/ a página `/assinar` mostrar.

### Banco (novas tabelas em `artigos.db`, via `db.py`)
- **`subscribers`** (MIGRA do `subscribers.json` na 1ª subida): `id, nome, whatsapp, email, cpf, plano, metodo, status (ATIVO|INADIMPLENTE|CANCELADO), asaas_customer_id, asaas_subscription_id, asaas_payment_id, proximo_vencimento, acesso_ate, carencia_ate, aviso_renov_em, criado_em, cancelado_em, cancel_motivo`.
- **`pending_signups`**: `token, nome, email, cpf, whatsapp, plano, metodo, parcelas, valor, criado_em` (criado antes do redirect; `externalReference=token`).
- **`webhook_events`**: `payment_id, event, processed_em` (idempotência: processa cada (payment,event) 1×).
- **`cupons`**: `codigo, ativo, descricao, criado_em`.

### `subscribers.py` — passa a usar SQLite (API pública estável)
- Mantém `ativos()`/`listar()`/`adicionar()`/`remover()` (daily/auth/admin seguem funcionando).
- `ativos()` = quem **tem acesso** (`tem_acesso(sub)`): `ATIVO`, ou `INADIMPLENTE` com `carencia_ate>agora`, ou `CANCELADO` com `acesso_ate>agora`.
- Novas: `por_external_ref`, `por_subscription`, `criar_de_pagamento`, `marcar_status`, `registrar_cancelamento`, `tem_acesso` (pura, TDD).
- Migração idempotente no `db.init` (importa o JSON se a tabela estiver vazia).

### Webhook — `app/webhook_asaas.py` + rota `POST /webhook/asaas`
- Valida header `asaas-access-token == ASAAS_WEBHOOK_TOKEN` (senão 401). Idempotência via `webhook_events`.
- `decidir(evento, pagamento, sub_atual)` → ação (pura, TDD):
  - `PAYMENT_CONFIRMED`/`PAYMENT_RECEIVED`: novo (acha `pending` por `externalReference`) → cria assinante ATIVO + `proximo_vencimento` (=dueDate + ciclo) + **WhatsApp de boas-vindas** ("entre no portal com este número"). Renovação (acha por subscription) → estende vencimento, garante ATIVO.
  - `PAYMENT_OVERDUE`: `INADIMPLENTE`, `carencia_ate=agora+3d`.
  - `PAYMENT_REFUNDED`/`PAYMENT_DELETED`: suspende (`CANCELADO`, `acesso_ate=agora`).
- Boas-vindas usa `deliver.enviar_texto` (WhatsApp já existente).

### Assinar — `app/site_web.py` + rotas
- Landing CTA → `/assinar` (ou `/assinar?plano=anual`).
- `GET /assinar`: escolha de plano → formulário (nome, email, CPF, WhatsApp) + escolha de método; se **cartão + plano maior**, seletor de **parcelas** com totais já com taxa (`pricing.opcoes_parcelas`); campo **cupom** opcional.
- `POST /assinar`:
  - **Cupom válido** → cria assinante ATIVO na hora (cortesia, sem Asaas) + boas-vindas → `/obrigado`.
  - Senão → cria `pending_signups`, monta o payload (recorrente p/ mensal e cartão-maior; avulso p/ Pix-maior; gross-up no cartão), chama `asaas.criar_checkout`, **redireciona** pra URL do checkout.
- `GET /obrigado`: "recebemos, seu acesso chega no WhatsApp assim que o pagamento confirmar".

### Cancelamento (self-service) — rotas protegidas
- `/minha` ganha botão "Cancelar assinatura".
- `GET /cancelar` (🔒): **motivo obrigatório** (textarea).
- `POST /cancelar` (motivo) → `GET /cancelar/oferta`: **+1 mês grátis** ("antes de ir…").
  - Aceita → `asaas.adiar_vencimento(sub,30)` + marca concessão → mantém ATIVO.
  - Recusa → `asaas.cancelar_assinatura(sub)` + `registrar_cancelamento(motivo)` (status CANCELADO, `acesso_ate=proximo_vencimento`) + **e-mail de confirmação**.
- Cortesia/cupom (sem subscription Asaas): cancelar = só marca CANCELADO local.

### E-mail — `app/email_send.py`
- Backend por `EMAIL_BACKEND` (`resend`|`smtp`|`none`). `resend` = POST HTTP (urllib) com `RESEND_API_KEY`+`EMAIL_FROM`; `none` = só loga (degrada). Usos: confirmação de cancelamento + aviso de pré-renovação.

### Aviso de pré-renovação
- No `agendador` (job diário já existe): assinantes com `proximo_vencimento` em ~3 dias e `aviso_renov_em` vazio no ciclo → e-mail discreto + marca enviado.

### Config nova — `app/config.py`
- `ASAAS_BASE_URL`, `ASAAS_API_KEY`, `ASAAS_WEBHOOK_TOKEN`.
- `TAXA_CARTAO` (dict) + `TAXA_FIXA`.
- `EMAIL_BACKEND`, `RESEND_API_KEY`, `EMAIL_FROM`.
- `PLANOS` ganha `cycle` + `slug` do plano (mensal/trimestral/semestral/anual) + `base` numérico.

## Segurança
- Webhook autenticado (token) + idempotente.
- `clinicId` N/A (app single-tenant do Diego).
- CPF/WhatsApp/cartão nunca logados; cartão nunca trafega pelo nosso app (checkout hospedado).
- Valores calculados **no servidor** (o cliente não define preço/parcelas livremente — validamos plano×método×parcelas contra a tabela).
- Chaves em env; começa em **sandbox**.

## Fora de escopo (depois)
- Split/repasse, NF-e, relatórios financeiros, multi-produto, área de gestão de cupons na UI (por ora cupom via `/admin` ou seed).

## Fases (para o plano)
1. **Núcleo vendável:** `asaas.py` + `pricing.py` (TDD) + migração `subscribers`→SQLite + `/assinar` + checkout + `/webhook/asaas` + ativação + gating de acesso + **cupom** (Diego já se cadastra grátis e testa sem dinheiro). 
2. **Cancelamento + retenção:** motivo → oferta +1 mês → cancelar no Asaas + `email_send.py` + confirmação.
3. **Pré-renovação + landing:** aviso por e-mail 3 dias antes + cards da landing com Pix/Cartão + polish + deploy sandbox→prod.

## Testes (unittest)
- `pricing.py`: `valor_cartao` gross-up por faixa; `opcoes_parcelas`; arredondamento.
- `subscribers.py`: `tem_acesso` (ATIVO/INADIMPLENTE+carência/CANCELADO+acesso_ate/expirados); migração JSON→SQLite.
- `webhook_asaas.decidir`: cada evento → ação certa; idempotência.
- `db.py`: pending/cupom/webhook_events roundtrip.

## Dependências do Diego (no deploy)
- Conta Asaas + **API key** (sandbox primeiro).
- **Pix Automático habilitado** na conta (se não, sobe só cartão e liga depois).
- **Taxas reais** de cartão do Asaas dele (pra `TAXA_CARTAO`).
- Credencial de e-mail (**Resend key** ou SMTP Titan) + `EMAIL_FROM`.
