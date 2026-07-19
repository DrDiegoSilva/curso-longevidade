# Cobrança Asaas — Fase 1 (núcleo vendável + cupom) — Plano

> Execução inline. TDD nas partes puras (`pricing`, `subscribers.tem_acesso`, `webhook_asaas.decidir`, payload builder). Asaas simulado nos testes; validação real (sandbox) só quando o Diego trouxer a chave.

**Goal:** o médico assina na landing → checkout Asaas → webhook ativa sozinho; **cupom** ativa grátis (Diego testa sem dinheiro). Assinantes migram p/ SQLite.

## Global Constraints
- Só stdlib (Resend/e-mail é Fase 2). Isolado do clinicdspro.
- Valores/planos validados **no servidor** (cliente não define preço).
- Nunca logar CPF/WhatsApp/cartão; cartão nunca passa pelo app (checkout hospedado).
- `subscribers.py` mantém API pública (`ativos/listar/adicionar/remover`) — daily/auth/admin não quebram.

---

### Task 1 — config: Asaas + planos + taxas
**Files:** Modify `app/config.py`
- `ASAAS_BASE_URL` (env, default sandbox `https://api-sandbox.asaas.com/v3`), `ASAAS_API_KEY` (env), `ASAAS_WEBHOOK_TOKEN` (env).
- `TAXA_CARTAO = {"avista":0.0299,"ate6":0.0349,"ate12":0.0399}`, `TAXA_FIXA=0.49` (env-overridável via JSON opcional).
- `PLANOS` ganha por item: `slug` (mensal/trimestral/semestral/anual), `cycle` (MONTHLY/QUARTERLY/SEMIANNUALLY/YEARLY), `base` (float 99/269/499/960), `recorrente_pix` (bool: só mensal). `preco` string vira derivado (`_fmt_brl(base)`).
- `DSCURSO_CUPONS` (csv) p/ seed de cupons.
- Commit.

### Task 2 — pricing.py (TDD)
**Files:** Create `app/pricing.py`, Test `app/tests/test_pricing.py`
- `faixa(parcelas)` → "avista"|"ate6"|"ate12".
- `valor_cartao(base, parcelas)` → gross-up `(base+TAXA_FIXA)/(1-pct)` arredondado 2 casas; `parcelas>=1`.
- `opcoes_parcelas(base, max_parcelas=12)` → `[{parcelas,total,por_parcela}]`.
- `fmt_brl(v)`.
- Testes: à vista de 960 > 960; 12x usa taxa ate12; por_parcela = total/parcelas; monotonicidade da taxa por faixa.
- Commit.

### Task 3 — db.py: novas tabelas + seed cupom (TDD estende test_db)
**Files:** Modify `app/db.py`, `app/tests/test_db.py`
- `init()` cria `subscribers`, `pending_signups`, `webhook_events`, `cupons` (além das atuais).
- Seed de `DSCURSO_CUPONS` em `cupons` (idempotente).
- Funções: `criar_pending(...)→token`, `obter_pending(token)`, `registrar_webhook(payment_id,event)→bool` (False se já visto = idempotência), `cupom_valido(codigo)→bool`.
- Migração `subscribers.json`→tabela `subscribers` se tabela vazia.
- Testes: pending roundtrip; webhook_events idempotente (2ª vez False); cupom seed+valido; migração importa o JSON.
- Commit.

### Task 4 — subscribers.py → SQLite (TDD)
**Files:** Rewrite `app/subscribers.py`, Test `app/tests/test_subscribers.py`; ajustar `app/tests/test_auth_web.py` se preciso
- Mantém `listar()`, `ativos()`, `adicionar(nome,whatsapp)`, `remover(id)`.
- `ativos()` = `[s for s in listar() if tem_acesso(s)]`.
- `tem_acesso(s, agora=None)` (pura): ATIVO True; INADIMPLENTE→`carencia_ate>agora`; CANCELADO→`acesso_ate>agora`; senão False.
- Novas: `por_external_ref(tok)`, `por_subscription(sid)`, `criar_de_pagamento(pending, dados_asaas, status="ATIVO")`, `marcar_status(id,status,**campos)`, `registrar_cancelamento(id,motivo)`.
- `adicionar` cria ATIVO (cortesia/manual).
- Testes: `tem_acesso` nos 4 casos + carência/acesso expirados; adicionar/ativos.
- Rodar test_auth_web (deve seguir verde). Commit.

### Task 5 — asaas.py (cliente) + payload builder (TDD do builder)
**Files:** Create `app/asaas.py`, Test `app/tests/test_asaas_payload.py`
- Puro/TDD: `montar_checkout(plano, metodo, parcelas, dados, token, base_url_callback)` → dict do POST `/checkouts` (recorrente p/ mensal e cartão-maior; DETACHED+PIX p/ pix-maior; `value` com gross-up no cartão via pricing; `externalReference=token`; `customerData`).
- Rede (sem teste, try/except, erro logado): `criar_checkout(payload)→{"url":..., "id":...}`, `obter_cliente(cid)`, `obter_pagamento(pid)`, `cancelar_assinatura(sid)`, `adiar_vencimento(sid,dias)`. Header `access_token`.
- Testes do builder: mensal→RECURRENT+MONTHLY; anual cartão 12x→value grossed-up+installmentCount; anual pix→DETACHED+value=base; externalReference presente.
- Commit.

### Task 6 — webhook_asaas.py: decidir() (TDD) + processar()
**Files:** Create `app/webhook_asaas.py`, Test `app/tests/test_webhook.py`
- `decidir(event, pagamento, sub)` (pura) → `{"acao": "ATIVAR"|"RENOVAR"|"INADIMPLENTE"|"SUSPENDER"|"IGNORAR", ...}`:
  - CONFIRMED/RECEIVED + sub None → ATIVAR; + sub existe → RENOVAR.
  - OVERDUE → INADIMPLENTE (carencia_ate=+3d).
  - REFUNDED/DELETED → SUSPENDER.
  - outros → IGNORAR.
- `processar(body, token_header)` → valida token, idempotência (`db.registrar_webhook`), aplica a ação (cria/atualiza subscriber via `subscribers`, envia boas-vindas no ATIVAR via `deliver`). Retorna (status_code, msg).
- Testes de `decidir`: matriz de eventos; carência.
- Commit.

### Task 7 — site: /assinar + /obrigado (render)
**Files:** Modify `app/site_web.py`, Test `app/tests/test_site_web.py`
- `pagina_assinar(plano_sel=None, erro="")`: cards de plano → form (nome,email,cpf,whatsapp) + método (Pix/Cartão) + (cartão+maior) seletor de parcelas com totais (`pricing.opcoes_parcelas`) + cupom. Mesma identidade dark-luxury.
- `pagina_obrigado()`.
- Landing CTA `_cta()` → default `/assinar` (já é `/entrar`? trocar default p/ `/assinar`; env ainda sobrescreve).
- Smoke tests: assinar mostra planos+parcelas; obrigado não-vazio.
- Commit.

### Task 8 — serve.py: rotas de venda + webhook
**Files:** Modify `app/serve.py`
- `_site_get`: `/assinar`→pagina_assinar; `/obrigado`→pagina_obrigado (públicas).
- `do_POST` `/assinar`: valida plano×método×parcelas; se cupom válido→`subscribers.criar_de_pagamento`(cortesia)+boas-vindas→redirect `/obrigado`; senão `db.criar_pending`+`asaas.montar_checkout`+`asaas.criar_checkout`→redirect URL.
- `do_POST` `/webhook/asaas` (host-agnóstico): `webhook_asaas.processar(body, header)`.
- Commit.

### Task 9 — validação local + fecho
- Rodar toda a suíte (todos os `app/tests/*`).
- Subir server local, curl: `/assinar` (Host artigos) 200 com planos; POST `/assinar` com cupom → cria assinante + redirect `/obrigado`; POST `/webhook/asaas` com token errado→401, com evento CONFIRMED simulado→ativa (checar via `/artigos` logado ou DB).
- Commit. Apresentar ao Diego (build/push só com OK dele).
