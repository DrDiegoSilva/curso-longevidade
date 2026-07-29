# Admin de preços editáveis — Design

**Data:** 2026-07-28
**Status:** aprovado (brainstorming) → aguardando plano
**Branch:** `precos-lancamento` (mesma do preço de lançamento; a tela gerencia esses preços)

## Objetivo

Dar ao Diego uma tela de admin (`/admin/precos`) pra **mudar o preço do Mensal e do Anual de forma autônoma**, sem mexer no código nem redeployar. O preço editado passa a valer **imediatamente** nas vendas novas.

## Decisões (brainstorming 2026-07-28)

- **Edita só o número** (o `base` cobrado). O texto de exibição (`"R$ 1.497"`, a nota `"≈ R$ 125/mês…"`) **deriva** do número — uma fonte de verdade.
- **Só Mensal e Anual** na tela (os visíveis). Trimestral/Semestral/Teste seguem fixos no código.
- **"Voltar ao padrão"** por plano (limpa o override → volta ao default do código).
- **Cupom LANCAMENTO fica −R$500 fixo** sobre o valor vigente (não "preço-alvo 997"). Se o Diego subir o anual pra 1600, com cupom sai 1100.
- **Assinantes atuais não mudam** — renovação lê `valor_contratado`; o preço só afeta vendas novas.

## Arquitetura — resolução do preço vigente (Approach A: resolver no `config`)

O preço é lido em vários pontos (cards da landing, tela `/assinar`, cálculo do que cobra, e `plano_por_base` no webhook). O override precisa valer em todos → um único ponto de resolução no `config`.

- **Storage:** `settings` (via `db.get_config`/`set_config`), chaves `preco_base_mensal` e `preco_base_anual` (string do número; ausente/"" = default do código).
- **Resolver:** `config.plano_por_slug(slug)` e o novo `config.planos_venda()` (lista dos visíveis, p/ a landing) devolvem uma **CÓPIA** do dict do plano com:
  - `base` e `base_pos` = override (se houver), senão o valor do código.
  - `preco`/`preco_pos` re-derivados: `_preco_str(base)` no estilo atual **sem centavos** (`"R$ 1.497"`).
  - `nota`/`nota_pos` re-derivados por plano: anual = `f"≈ R$ {round(base/12)}/mês · em até 12x sem juros"`; mensal = `""`. Campos não-preço (`cycle`, `pix_desconto_pct`, `aceita_pix`, `recorrente_pix`, `oculto`, `slug`, `nome`, `periodo`) são preservados da definição do código.
- `config.plano_por_base(valor)` passa a casar contra o `base` **vigente** (resolvido), não só o do código.
- **Import lazy de `db`** dentro do resolver (evita ciclo `config`↔`db`); defensivo — se `settings`/tabela faltar, cai no default (é o contrato do `get_config`).
- **Imutabilidade:** o resolver nunca muta `config.PLANOS`; sempre devolve cópia nova.

## Página `/admin/precos`

- **Rota** GET+POST, admin-gated pelo `config.ADMIN_TOKEN` (mesmo check das outras telas admin). Link **💰 Preços** no `_admin_nav`.
- **GET (`site_web.pagina_precos`):** lista Mensal e Anual; por plano: input com o `base` vigente + um **preview** derivado ("R$ 1.497", "≈ R$ 125/mês", e no anual "12x de R$ 124,75" via `pricing.opcoes_parcelas`). Escape via `_esc`. Botão **Salvar** e **Voltar ao padrão** por plano.
- **POST:** ação `salvar_preco` (valida número **positivo**; recusa vazio/0/negativo/texto com mensagem clara; grava `set_config("preco_base_<slug>", str(valor))`); ação `resetar_preco` (`set_config("preco_base_<slug>", "")` — string vazia, que o resolver trata como "sem override" → volta ao default do código). Redirect com msg ("✅ Preço do Anual: R$ 1.600" / "Anual voltou ao padrão (R$ 1.497)").

## Guarda-corpos (dinheiro real)

- Validação de entrada: só número > 0 (com no máx. 2 casas); senão rejeita sem gravar.
- Efeito imediato só em **vendas novas**; **nenhum** assinante atual é tocado (renovação = `valor_contratado`).
- Sem override salvo, o comportamento é **idêntico** ao de hoje (default do código) — a suíte existente segue verde.
- O resolver é defensivo: qualquer falha ao ler `settings` → default do código (nunca derruba a landing/checkout).

## Dados

- Sem tabela nova. Duas chaves em `settings`: `preco_base_mensal`, `preco_base_anual`.

## Testes (TDD)

- **Resolver (`config`):** override aplicado quando há `settings`; default quando não há; devolve **cópia** (não muta `PLANOS`); `preco`/`nota` derivados corretos (anual "≈ R$ X/mês", mensal ""); `plano_por_base` enxerga o override; import lazy não quebra.
- **`pricing`/checkout:** `preco_vigente` reflete o override (via o dict resolvido); nenhuma regressão no cálculo (997 cupom etc. seguem, agora sobre o valor vigente).
- **`pagina_precos`:** renderiza os 2 planos + preview + botões; escapa; mostra o valor vigente.
- **`/admin/precos`:** GET renderiza (admin-gated, 403 sem token); POST `salvar_preco` valida positivo e grava; entrada inválida não grava; `resetar_preco` limpa.
- **Regressão:** suíte 741 verde sem nenhum override setado.

## Arquivos

- `app/config.py` — resolver (`plano_por_slug`/`planos_venda`/`plano_por_base` override-aware; `_preco_str`/derivação de nota).
- `app/site_web.py` — `pagina_precos` + link no `_admin_nav`; a landing passa a usar `planos_venda()`.
- `app/serve.py` — rotas GET/POST `/admin/precos`.
- `app/tests/test_admin_precos.py` — novo.

## Fora de escopo (backlog)

- Editar preço dos planos ocultos; editar o cupom/Pix % pela tela; histórico/auditoria de mudanças de preço; agendar mudança de preço; cupom "preço-alvo" (hoje é −R$ fixo). Renovação do 1x-cartão no valor de tabela (decisão já tomada: manter o valor contratado).
