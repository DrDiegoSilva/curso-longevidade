# Projeto D2 — Founder pricing — Design

**Data:** 2026-07-24 · **Host:** `artigos.` · Parte do [[projeto-d-precos-afiliados]] (depois do D1, já no ar).
**Status:** Design aprovado (decisões via brainstorming) — aguardando revisão do spec.

## Objetivo

Preço de **lançamento** enquanto houver poucas assinaturas; ao atingir **20 assinantes ativos no total** (mensal + anual, incluindo os atuais), os preços sobem automaticamente. Mostrar um **contador de vagas** na landing pra criar urgência.

- **Founder (< 20 ativos):** mensal **R$ 99**, anual **R$ 997** (preços atuais do D1).
- **Pós-founder (≥ 20 ativos):** mensal **R$ 147**, anual **R$ 1.497**.

## Decisões (Diego, 2026-07-23/24)

- Base do limite = **assinantes ATIVOS no total** (mensal + anual), **incluindo os atuais** → `len(subscribers.ativos())`. Ao chegar em 20, troca.
- **Mostrar contador de vagas** na landing (ex.: "Preço de lançamento — restam X de 20 vagas").
- **Lock-in é automático:** os primeiros 20 já assinaram com um valor de assinatura recorrente no Asaas → **renovam nesse valor** sem esforço nosso. Só **novos checkouts** pagam o preço vigente (mais alto) depois dos 20. *(O app não precisa "travar" preço por assinante — o Asaas já faz isso na assinatura recorrente.)*

## Arquitetura

### Config (`config.py`)
- `FOUNDER_LIMITE = int(os.environ.get("DSCURSO_FOUNDER_LIMITE") or 20)`.
- `PLANOS`: adicionar ao **mensal** e **anual** os campos pós-founder — `base_pos` (147.0 / 1497.0), `preco_pos` ("R$ 147" / "R$ 1.497") e, no anual, `nota_pos` ("≈ R$ 125/mês · em até 12x sem juros"). Planos sem `base_pos` não têm founder pricing.

### Pricing (`pricing.py`) — funções puras
- `preco_vigente(plano, n_ativos)` → `float(plano["base_pos"])` se `plano.get("base_pos")` **e** `n_ativos >= config.FOUNDER_LIMITE`; senão `float(plano["base"])`. (Reimportar `config` no `pricing.py` — foi removido no D1; volta só p/ o `FOUNDER_LIMITE`.)
- `vagas_founder(n_ativos)` → `max(0, config.FOUNDER_LIMITE - int(n_ativos))`.
- `preco_str_vigente(plano, n_ativos)` → `plano["preco_pos"]` se pós-founder e existir, senão `plano.get("preco")`. (Pra manter o estilo "R$ 997" sem centavos na landing.)

### Checkout — cobrar o preço vigente
Hoje `serve.py:650` e `asaas.montar_checkout` (`asaas.py:36`) leem `plano["base"]` direto. Passam a usar o vigente:
- `asaas.montar_checkout(plano, metodo, parcelas, dados, token, base_url, base=None)` — novo param **opcional** `base`; internamente `base = float(plano["base"]) if base is None else float(base)`. (Retrocompatível: testes que não passam `base` seguem no founder.)
- `serve.py` `/assinar`: antes do checkout, `n = len(subscribers.ativos())`, `base_vig = pricing.preco_vigente(plano, n)`; usar `base_vig` no `valor` do pending e passar `base=base_vig` ao `montar_checkout`.

### Landing (`site_web.landing`)
- Calcular `n = len(subscribers.ativos())` uma vez.
- Cada card usa `pricing.preco_str_vigente(p, n)` no preço e `nota_pos`/`nota` conforme o caso.
- **Contador de vagas:** se `pricing.vagas_founder(n) > 0`, mostrar um selo/nota perto dos planos: **"Preço de lançamento — restam {vagas} de {FOUNDER_LIMITE} vagas"**. Se 0, não mostrar (preços já são os pós-founder).
- `landing()` passa a depender de `subscribers.ativos()` (DB) — `db.init()` via `_ensure()`. Baixo tráfego; sem cache por ora.

## Fora de escopo
- **D3 — Afiliados** (cupom 10% + comissão 3%). Spec próprio.
- Travar preço por assinante no app (desnecessário — Asaas recorrente já faz).
- Cache da contagem de ativos na landing (só se virar gargalo).

## Testes (unittest stdlib; SQLite tmp p/ os que tocam `subscribers`)
- `pricing.preco_vigente`: n=0 → base (997/99); n=20 → base_pos (1497/147); plano **sem** base_pos (ex.: trimestral) → sempre base, mesmo n≥20.
- `pricing.vagas_founder`: n=0 → 20; n=7 → 13; n=25 → 0.
- `preco_str_vigente`: n<20 → "R$ 997"; n≥20 → "R$ 1.497".
- `asaas.montar_checkout` com `base=1497` → `items[0].value` reflete 1497 (cartão e pix).
- `landing()`: com 0 ativos (tmp DB vazio) → contém "restam 20 de 20 vagas" e "R$ 997"; **mock** de `subscribers.ativos` retornando 20 → contém "R$ 1.497" e **não** contém o selo de vagas.

## Impacto de negócio (registrar)
Enquanto < 20 ativos: entra gente a 997/99 (trava esse preço na renovação via Asaas). No 20º ativo, a landing/checkout viram 1497/147 pra novos. O contador de vagas cria urgência pra fechar os founders.
