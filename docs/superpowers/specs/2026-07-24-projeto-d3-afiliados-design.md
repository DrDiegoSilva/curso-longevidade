# Projeto D3 — Afiliados (cupom 10% + comissão 3%) — Design

**Data:** 2026-07-24 · **Host:** `artigos.` · Parte do [[projeto-d-precos-afiliados]] (depois do D1 e D2, já no ar).
**Status:** Design aprovado (decisões via brainstorming) — aguardando revisão do spec.

## Objetivo

Permitir que uma afiliada (a colega médica, e futuros afiliados) divulgue um **código de cupom** que dá **10% de desconto na 1ª venda** ao assinante e gera **3% de comissão** pra ela sobre essa venda. As comissões viram um **relatório no `/admin`**; o pagamento em si é **manual** (fora do sistema).

Escopo fechado com o Diego:
- **Atribuição:** só por **código de cupom** (a afiliada divulga um código; sem link `?ref=`/cookie).
- **Recorrência:** **só aquisição** — 10% off na 1ª cobrança e comissão 3% só na venda inicial; **renovações voltam ao preço cheio/vigente**.
- **Gestão:** painel `/admin` (rota nova `/admin/afiliados`), com tabela de afiliados + ledger de comissões.

## Decisões (Diego, 2026-07-24)

- **Comissão = 3% sobre o valor efetivamente pago** na 1ª venda (`pay.value`, já com o desconto), **não** sobre o valor cheio.
- **Cartão (RECURRENT):** a 1ª cobrança sai com desconto; para a renovação voltar ao cheio, o webhook `ATIVAR` **reseta o `value` da assinatura** no Asaas pro preço vigente cheio. (Descartada a alternativa "desconto recorrente", que seria mais simples de código mas valeria pra sempre.)
- **Pix (DETACHED, não renova):** desconto vira o valor da cobrança única; nada a resetar.
- **Cortesia e afiliado são namespaces separados:** o fluxo de cupom de cortesia (cadastro grátis) continua **intacto**; o código de afiliado é um caminho novo que leva ao **checkout pago com desconto**.
- **Pagamento da comissão é manual;** o sistema só registra e marca "paga".

## Arquitetura

### Dados (`db.py`)

Duas tabelas novas + uma coluna:

- **`afiliados`**: `id` (PK), `nome`, `contato`, `codigo` (UNIQUE, upper), `pct_desconto REAL DEFAULT 10`, `pct_comissao REAL DEFAULT 3`, `ativo INTEGER DEFAULT 1`, `criado_em`.
- **`comissoes`** (ledger, 1 linha por venda atribuída): `id` (PK), `afiliado_id`, `subscriber_id`, `plano`, `valor_venda REAL`, `valor_comissao REAL`, `pago INTEGER DEFAULT 0`, `criado_em`, `pago_em`.
- **`pending_signups`**: nova coluna `afiliado_codigo TEXT` (carrega o código do checkout até a confirmação no webhook).

Ambas as tabelas entram na CREATE TABLE, no `_TABELAS` (RLS) e no `_migrar_colunas` (ALTER idempotente pro Supabase de produção). A coluna `afiliado_codigo` é adicionada via `_add_coluna` no `_migrar_colunas`.

Funções novas em `db.py`:
- `afiliado_por_codigo(codigo)` → dict do afiliado ativo, ou None.
- `criar_afiliado(nome, contato, codigo, pct_desconto=10, pct_comissao=3)` → código; ON CONFLICT(codigo) DO NOTHING.
- `listar_afiliados()` → lista com agregados (nº vendas, comissão total, comissão pendente) via LEFT JOIN/subselect em `comissoes`.
- `toggle_afiliado(id, ativo)`.
- `registrar_comissao(afiliado_id, subscriber_id, plano, valor_venda, valor_comissao)` → insere no ledger.
- `listar_comissoes(afiliado_id=None, pago=None)`.
- `marcar_comissao_paga(id)` → `pago=1`, `pago_em=now`.

### Cálculo (`pricing.py`)

- `valor_com_desconto(base, pct)` → `round(base * (1 - pct/100), 2)`. Puro/testável.
- `comissao(valor_venda, pct)` → `round(valor_venda * pct/100, 2)`.

### Fluxo de compra (`serve.py` `_post_assinar`)

Ordem das checagens do campo `cupom` (após validar dados/CPF/duplicidade):
1. **Cortesia** (`db.cupom_valido`): comportamento atual **intacto** → cadastro grátis, sem Asaas.
2. **Afiliado** (`db.afiliado_por_codigo` ativo): calcula `base_vig = pricing.preco_vigente(plano, n_ativos)` → `base_desc = pricing.valor_com_desconto(base_vig, af["pct_desconto"])` → cria pending com `afiliado_codigo` e segue pro **checkout Asaas pago** com `base=base_desc`.
3. **Sem cupom válido:** fluxo normal (base vigente cheia).

O `valor` gravado no pending e o `base` passado a `asaas.montar_checkout` usam a base descontada (cartão parcela sobre o total descontado; sem juros, D1).

### Desconto no Asaas — "só na 1ª venda"

- **Pix:** `montar_checkout` já usa DETACHED (não renova) → a cobrança única sai com `base_desc`. Nada a resetar.
- **Cartão:** a 1ª cobrança da assinatura RECURRENT sai com `base_desc`. No webhook `ATIVAR`, após criar o assinante, se o pending tinha `afiliado_codigo`, chamar `asaas.atualizar_valor_assinatura(sid, base_vig_cheio)` para as **próximas** cobranças voltarem ao preço vigente cheio.
  - Novo helper `asaas.atualizar_valor_assinatura(sid, valor)` → `PUT /subscriptions/{sid}` com `{"value": valor, "updatePendingPayments": false}` (não mexe na 1ª cobrança já paga).
  - Envolto em try/except + `_alertar_admin` (padrão existente). Pior caso: uma renovação sai com desconto e o Diego é avisado — **nada quebra a ativação**.
  - ⚠️ **Validar no sandbox:** aceitação do PUT de `value` com `updatePendingPayments=false` numa assinatura recém-criada (mesmo cuidado que o cabeçalho do `asaas.py` já registra pra RECURRENT+installment).

O preço vigente cheio pro reset é recalculado no webhook a partir do plano resolvido (`plano_por_cycle`/`plano_por_base`) e de `preco_vigente(plano, len(subscribers.ativos()))`.

### Comissão (registro único) — `webhook_asaas.py` `_executar` `ATIVAR`

- `ATIVAR` só dispara em **venda nova** (nunca em renovação) → naturalmente "só 1ª venda".
- Se o pending tem `afiliado_codigo` e o afiliado está ativo:
  - captura o `reg` de `subscribers.criar_de_pagamento` pra ter o `subscriber_id`;
  - `valor_venda = pay.value`; `valor_comissao = pricing.comissao(valor_venda, af["pct_comissao"])`;
  - `db.registrar_comissao(...)`.
- Idempotência já garantida por `webhook_events` (não duplica o evento). Wrap em try/except: falha ao registrar comissão **não** derruba a ativação (loga + segue).
- `_avisar_venda` ganha uma linha extra "Afiliado: NOME · comissão R$ X" quando houver atribuição.

### Painel `/admin` — Afiliados (rota nova `/admin/afiliados`)

Página dedicada (`site_web.pagina_admin_afiliados(...)`) pra **não inchar** o `pagina_admin` (já grande):
- **Cadastrar afiliado:** nome, contato, código, % desconto (default 10), % comissão (default 3).
- **Tabela de afiliados:** código, nome, ativo (toggle), nº vendas atribuídas, comissão total, **comissão pendente**.
- **Relatório de comissões:** linhas pendentes com botão **"marcar como paga"** (grava `pago_em`).

Rotas/ações:
- `GET /admin/afiliados` (mesma auth do `/admin`: `ADMIN_TOKEN` ou sessão admin) → renderiza a página.
- `POST /admin/afiliados` com `acao ∈ {criar_afiliado, marcar_comissao_paga, toggle_afiliado}` → aplica e redireciona de volta (mantendo `token` na query, como o `/admin` já faz).
- Link "Afiliados" a partir do `/admin`.

## Erros & bordas

- **Código inexistente/inativo:** cai no fluxo normal (preço cheio), sem desconto — igual "sem cupom".
- **Código de afiliado usado por qualquer pessoa:** é um cupom compartilhado por design (10% pra quem souber o código). Aceito. Comissão atribuída em cada 1ª venda que usar o código.
- **Assinante já ativo (CPF/WhatsApp):** guarda existente barra antes de chegar no cupom — inalterado.
- **Reset da assinatura falha (cartão):** loga + alerta admin; ativação e comissão seguem. Renovação pode sair com desconto até correção manual.
- **Comissão sobre venda de teste (plano `teste`, R$5):** entra no ledger normalmente se um código for usado; irrelevante na prática (plano oculto).
- **Colisão cortesia × afiliado:** cortesia é checada primeiro; se um código existir nas duas tabelas, vale a cortesia (grátis). Na prática não colidem.

## Testes (unittest, `cd app && python3 -m unittest discover -s tests`)

- **`pricing`:** `valor_com_desconto` (10% de 997 = 897.30; arredondamento) e `comissao` (3% de 897.30 = 26.92).
- **`db`:** `criar_afiliado`/`afiliado_por_codigo` (ativo/inativo/inexistente); `registrar_comissao` + `listar_comissoes` (filtro pago); `marcar_comissao_paga`; agregados de `listar_afiliados` (nº vendas, total, pendente).
- **`asaas`/`montar_checkout`:** com `base` descontada, `items[].value` e a assinatura saem com o valor descontado (cartão e pix).
- **`serve` `_post_assinar`:** código de afiliado → pending grava `afiliado_codigo` e `valor` descontado; cortesia continua grátis; código inválido → base cheia.
- **`webhook` `ATIVAR`:** com `afiliado_codigo` grava **1** comissão com `valor_venda=pay.value`; renovação (`RENOVAR`) **não** grava; falha no reset/registro não derruba a ativação.
- **`admin`:** `criar_afiliado`, `toggle_afiliado`, `marcar_comissao_paga` via POST.

## Fora de escopo (YAGNI)

- Link `?ref=` / cookies de atribuição (decidido: só código).
- Desconto/comissão recorrente em renovações (decidido: só 1ª venda).
- Pagamento automático da comissão (é manual).
- Portal do afiliado / login próprio (relatório vive no `/admin`).
