# Projeto D1 — Ajustes de preço — Design

**Data:** 2026-07-23 · **Host:** `artigos.` (assinatura) · Parte do [[projeto-d-precos-afiliados]].
**Status:** Design aprovado (decisões via brainstorming) — aguardando revisão do spec.

## Contexto

Planos em `config.PLANOS` (`config.py:62`). Preço de cartão em `pricing.py` (`valor_cartao`/`opcoes_parcelas`), que hoje faz **gross-up** (`(base + TAXA_FIXA) / (1 - TAXA_CARTAO[faixa])`) — o **cliente paga a taxa embutida**. Fluxo de cobrança: `serve.py:650` e `asaas.py:41` chamam `valor_cartao`; a landing exibe via `site_web.py:1243/1248`. `TAXA_CARTAO`/`TAXA_FIXA` só são usados em `pricing.py`.

Badge "20% OFF" do anual em `site_web.py:378`.

## Decisões (Diego, 2026-07-23)

- **Anual: R$ 960 → R$ 997.** (Mensal continua **R$ 99** por ora — o R$ 147 é founder pricing = D2.)
- **Badge "20% OFF" → "melhor preço".**
- **Cartão sem juros até 12x, sem gross-up:** o cliente paga o valor do plano parcelado em até 12x; o Diego **absorve a taxa de transação (~3,5–4% + R$ 0,49)** recebendo **mês a mês**.
  - **Taxa real do Asaas** (fonte: [asaas.com/precos-e-taxas](https://www.asaas.com/precos-e-taxas)): cartão à vista R$ 0,49 + 2,99%; 2–6x + 3,49%; 7–12x + 3,99%. O "12%" antigo era **antecipação** (~1,25%/mês para receber tudo à vista). Sem antecipar, 12x custa ~4%.
  - ⚠️ **Ação operacional do Diego (fora do app):** deixar a **antecipação automática DESLIGADA** no painel Asaas.
- Bônus: com o cartão pagando o valor **base** (997), o `plano_por_base` do webhook casa o plano de forma mais limpa (hoje o valor grossed-up não bate com `base`).

## Escopo (D1)

1. **`config.PLANOS`** (slug `anual`): `base` 960 → **997**; `preco` "R$ 960" → **"R$ 997"**; `nota` → algo como **"≈ R$ 83/mês · em até 12x sem juros"**. Não mexer no mensal.
2. **`site_web.py:378`**: badge do anual "20% OFF" → **"melhor preço"** (o CSS já faz `text-transform:uppercase`).
3. **`pricing.valor_cartao(base, parcelas)`**: passa a devolver **`round(float(base), 2)`** (sem gross-up). `opcoes_parcelas` fica igual (agora `total=base`, `por_parcela=base/n`). Remover o helper `faixa()` (fica sem uso). Em `config.py`, `TAXA_CARTAO`/`TAXA_FIXA` deixam de ser aplicadas — atualizar o comentário para "não aplicadas (cartão sem juros, D1 2026-07-23); mantidas p/ referência".

## Fora de escopo

- **D2 — Founder pricing:** mensal 99→**147** e anual 997→**1497** ao passar de **20 assinantes no total** (somando mensal + anual). Spec próprio.
- **D3 — Afiliados** (cupom 10% + comissão 3%). Spec próprio.

## Testes (unittest stdlib)

- `pricing.valor_cartao(997, n) == 997.0` para n = 1..12 (sem juros, sem gross-up).
- `pricing.opcoes_parcelas(997)`: cada opção tem `total == 997.0` e `por_parcela == round(997/n, 2)`; 12 opções.
- `config.plano_por_slug("anual")`: `base == 997`, `preco == "R$ 997"`.
- Landing (`pagina_home`/onde o card do anual é montado): contém "melhor preço" (case-insensitivo) e **não** contém "20% OFF".

## Impacto de negócio (registrar, não é código)

Por venda no cartão você passa a absorver ~3,5–4% + R$ 0,49 (ex.: anual 997 em 12x → você recebe ~957–962, mês a mês). O aumento 960→997 já cobre boa parte disso. Mantendo a antecipação desligada, o custo fica em ~4% (não ~12%).
