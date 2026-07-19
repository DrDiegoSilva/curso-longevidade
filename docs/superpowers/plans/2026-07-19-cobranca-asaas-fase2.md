# Cobrança Asaas — Fase 2 (cancelamento + retenção + e-mail) — Plano

> Execução inline. Reusa `asaas.cancelar_assinatura`/`adiar_vencimento` (já existem). E-mail via Resend (Diego já usa no sistema deles). TDD no payload de e-mail.

**Goal:** assinante cancela sozinho em `/minha` → motivo obrigatório → oferta de +1 mês grátis → se recusar, cancela no Asaas mantendo acesso até o fim do período pago + **e-mail** de confirmação.

## Global Constraints
- Só stdlib. E-mail degrada (sem chave → só loga).
- Cortesia/cupom (sem `asaas_subscription_id`): cancelar = só marca CANCELADO local (não chama Asaas).
- Oferta de retenção só 1× por assinante (`oferta_retencao_em`).

### Task 1 — config + coluna
- `config.py`: `EMAIL_BACKEND` (default "resend" se `RESEND_API_KEY`, senão "none"), `RESEND_API_KEY`, `EMAIL_FROM`.
- `db.py`: coluna `oferta_retencao_em TEXT` em `subscribers`; `subscribers._COLS` inclui.
- Commit.

### Task 2 — email_send.py (TDD payload)
- `_resend_payload(to, assunto, html, remetente)` puro → dict {from,to,subject,html}.
- `enviar(to, assunto, html)` → resend via urllib POST `https://api.resend.com/emails` (Bearer); "none" → loga e retorna. try/except (não derruba fluxo).
- Test `test_email_send.py`: payload correto; backend none não explode.
- Commit.

### Task 3 — site_web: páginas de cancelamento
- `pagina_cancelar(erro="")`: aviso + textarea `motivo` (required) → POST `/cancelar`.
- `pagina_cancelar_oferta(motivo)`: "mais um mês por nossa conta" + form POST `/cancelar/confirmar` com `motivo` hidden e 2 botões (`acao=aceitar` / `acao=cancelar`).
- `pagina_cancelado(acesso_ate)`: confirmação + data.
- `pagina_minha` ganha botão "Cancelar assinatura" → `/cancelar`.
- Smoke tests.
- Commit.

### Task 4 — serve.py: rotas de cancelamento (🔒)
- GET `/cancelar` → pagina_cancelar (exige sessão).
- POST `/cancelar` (motivo): vazio→erro; se `oferta_retencao_em` vazio→oferta; senão→cancela direto.
- POST `/cancelar/confirmar` (acao,motivo):
  - `aceitar`→`asaas.adiar_vencimento(sid,30)`(se sub Asaas)+`marcar_status(ATIVO, oferta_retencao_em=now, proximo_vencimento=+30d)`→/minha.
  - `cancelar`→`asaas.cancelar_assinatura(sid)`(se sub)+`registrar_cancelamento(id,motivo,acesso_ate=proximo_vencimento)`+e-mail→pagina_cancelado.
- Commit.

### Task 5 — validação local + fecho
- Suíte inteira verde; curl do fluxo (motivo→oferta→aceitar / →cancelar). Commit. Apresentar ao Diego.
