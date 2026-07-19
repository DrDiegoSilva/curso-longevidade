# Cobrança Asaas — Fase 3 (aviso pré-renovação + landing + deploy) — Plano

> Execução inline. TDD na seleção de quem avisar. Deploy = passo à parte (OK do Diego + envs no EasyPanel + webhook no painel Asaas).

**Goal:** avisar por e-mail ~3 dias antes de renovar/vencer; landing mostra Pix e cartão por plano; preparar deploy sandbox.

## Global Constraints
- Só stdlib. E-mail degrada sem chave.
- Aviso 1× por ciclo (guarda `aviso_renov_em = proximo_vencimento` avisado → reavisa quando o vencimento muda).

### Task 1 — billing_notices.py (TDD)
- `assinantes_a_avisar(subs, dias, hoje)` (puro): ATIVO com `proximo_vencimento` em [hoje, hoje+dias] e `aviso_renov_em != proximo_vencimento`.
- `avisar_pre_renovacao(dias=3)`: itera, envia e-mail, marca `aviso_renov_em`.
- Test `test_billing_notices.py`: dentro da janela avisa; fora não; já avisado (aviso_renov_em==pv) não reavisa; sem e-mail não quebra.
- Commit.

### Task 2 — agendador roda o aviso diário
- `daily.py`: `rotina_08h()` = `billing_notices.avisar_pre_renovacao()` + `enviar_08h()`.
- `serve.py` agendador: task "enviar" → `daily.rotina_08h`.
- Commit.

### Task 3 — landing mostra Pix + cartão por plano
- `site_web.landing()`: cada card de plano ganha "no cartão a partir de {valor_cartao(base,1)}".
- Smoke test.
- Commit.

### Task 4 — validação + checklist de deploy
- Suíte inteira verde. Commit.
- Apresentar checklist de envs/deploy ao Diego (não pushar sem OK).
