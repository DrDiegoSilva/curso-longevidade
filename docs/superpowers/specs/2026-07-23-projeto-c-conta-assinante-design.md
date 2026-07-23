# Projeto C — Conta do assinante & avisos — Design

**Data:** 2026-07-23
**Status:** Design aprovado (aguardando revisão do spec)
**Host:** `artigos.drdiegosilva.com.br` (produto assinatura). Não toca no `curso.` (Projetos A/B).

## Contexto

A `_topbar` (`site_web.py:297`) já é a navegação global de toda página logada: `Arquivo · Minha conta · Sair`. Mas a experiência do assinante tem ruído e uma ação destrutiva mal colocada:

- O corpo do `/minha` (`pagina_minha`, `site_web.py:1028`) **repete** "Ir para o arquivo" e "Sair desta conta" — que o topo já oferece.
- O `_admin_nav` (`site_web.py:528`) repete "← Minha conta".
- **Cancelar assinatura** está solto no rodapé do `/minha`, colado no "Sair".
- Não há página onde o assinante edite os **próprios dados** (celular, e-mail, nome).
- Login é por **OTP no WhatsApp** (`auth_web.iniciar_login`/`verificar`; sessão cookie `sid` 30 dias; tabelas `login_codes`/`sessions` **chaveadas pelo número**). Logo, **trocar o celular = trocar a identidade de login e o canal de entrega** — precisa ser feito com cuidado.
- Quando uma **venda** é ativada (`webhook_asaas._executar`, path `"ativado"`, `webhook_asaas.py:108`), ninguém é avisado. Só há alerta de **falha** (`_alertar_admin` → `deliver.enviar_admin` = WhatsApp).

## Objetivo

Limpar o fluxo de conta do assinante, criar uma página de dados (com troca de celular segura), avisar o Dr. Diego por e-mail a cada venda, e aplicar 3 ajustes visuais já validados. Tudo no tema verde/ouro existente (`site_web.py:33`).

## Escopo

- **C1 — Fluxo/nav:** topbar como navegação única; `/minha` enxuto; remover links repetidos.
- **C2 — Página `/meus-dados`:** editar nome/e-mail; **trocar celular com confirmação por código (OTP) no número novo**; entrada de **Cancelar assinatura** movida pra cá.
- **C3 — Aviso de venda por e-mail:** e-mail instantâneo **a cada venda** (não renovações) ao admin.
- **C-UI:** (a) painel do curador → botões-card (+ atalho 📅 Agenda); (b) números do estoque → cartões; (c) `score` → chip verde/âmbar/cinza com legenda.

**Fora:** migrar o alerta de **falha** de pagamento pra e-mail (fica no WhatsApp, decisão do Diego); e-mail em **renovações**; qualquer coisa dos Projetos A/B.

## Arquitetura

### C1 — Fluxo / navegação

- **Topbar** (`_topbar`): mantém `Arquivo · Minha conta · Sair`. Quando a página atual já é `/minha`, **não** renderizar o link "Minha conta" (evita apontar pra onde já se está). Passar a rota atual pro `_topbar`.
- **`pagina_minha`**: remover do corpo "Ir para o arquivo" e "Sair desta conta" (já no topo). Corpo passa a ser: saudação + status + (painel do curador se admin) + **um** botão **"Meus dados"** (→ `/meus-dados`). Sem "Cancelar" aqui.
- **`_admin_nav`**: remover o "← Minha conta" (o topo já leva). Mantém Assinantes/Curadoria/Agenda/WhatsApp.

### C2 — Página `/meus-dados` (+ OTP de troca de número)

Rota nova `/meus-dados` (GET e POST), **exige sessão** (`auth_web.sessao`). `pagina_meus_dados(sub, msg="", etapa_troca=None)` no `site_web.py`.

Blocos da página:
1. **Nome / e-mail** — form (POST `acao=salvar_contato`). Valida e-mail (formato) e nome (não vazio) → `subscribers.atualizar_contato(id, nome, email)`.
2. **Celular (WhatsApp)** — mostra o número atual + botão **"Trocar número"**:
   - POST `acao=iniciar_troca` com `novo_numero`: valida via `phone.normalizar`; se o número já pertence a **outro** assinante (`subscribers.por_whatsapp`), bloqueia; senão `auth_web.iniciar_troca_numero(sub_id, novo_num)` gera código de 6 dígitos, grava hash em `login_codes` (chaveado pelo **novo** número, reusa a tabela e o TTL do login) e **envia o código via WhatsApp pro número novo**. Página volta mostrando campo "digite o código".
   - POST `acao=confirmar_troca` com `codigo`: `auth_web.confirmar_troca_numero(sub_id, novo_num, codigo)` confere hash/expiry/tentativas; sucesso → `subscribers.atualizar_whatsapp(sub_id, novo_num)` + **migra todas as sessões do número antigo pro novo** (todo `sessions.whatsapp = antigo` vira `novo`, pra o assinante seguir logado e não sobrar sessão órfã) + apaga o `login_codes` do número novo. Erro → mensagem clara, sem trocar nada.
   - **Rate-limit:** reusa o bucket `"otp"` (5/10 min por IP) já existente no `serve.py`.
3. **Cancelar assinatura** — no fim, visualmente **destrutivo/discreto**, apontando pro fluxo `/cancelar` que **já existe** (`serve.py:448`/`/cancelar/confirmar:450`). Não reimplementar o cancelamento — só mudar de onde se chega.

**DB / módulos novos:**
- `subscribers.atualizar_contato(id, nome, email)` e `subscribers.atualizar_whatsapp(id, novo)` — updates imutáveis (nova linha lógica, sem mutar o dict de entrada).
- `auth_web.iniciar_troca_numero(sub_id, novo_num, enviar_fn=None)` e `auth_web.confirmar_troca_numero(sub_id, novo_num, codigo)` — reusam `_hash`, `login_codes`, TTL e `enviar_fn` do OTP de login. `confirmar_*` também migra as sessões (helper `_migrar_sessoes_whatsapp(antigo, novo)` = `UPDATE sessions SET whatsapp=novo WHERE whatsapp=antigo`).

### C3 — Aviso de venda por e-mail

- Config nova: `ADMIN_EMAIL = os.environ.get("DSCURSO_ADMIN_EMAIL") or "edson-diego@live.com"` (`config.py`).
- Função `_avisar_venda(nome, plano, valor, contato, ativos)` (em `webhook_asaas.py`): monta assunto `🎉 Nova venda — {plano} · R$ {valor}` e um HTML curto (nome, plano, valor, contato, data, "Agora você tem {ativos} assinantes ativos") e chama `email_send.enviar(config.ADMIN_EMAIL, assunto, html)`.
- Chamada no `_executar`, no path **ATIVAR bem-sucedido**, imediatamente antes de `return (200, "ativado")` (`webhook_asaas.py:108`). Usa `subscribers.ativos()` pra a contagem.
- **Nunca pode quebrar a ativação:** envolto em `try/except` com log (padrão de `_boas_vindas`/`_alertar_admin`).
- Reusa o **Resend** já ativo (as boas-vindas já mandam e-mail). Se `EMAIL_BACKEND != "resend"`, `email_send.enviar` já é no-op — degrada sem erro.

### C-UI — 3 componentes (preview aprovado: artifact 264878ad)

Aplicar no `site_web.py`, com CSS novo no bloco de estilo (`site_web.py:33+`):
- **Painel do curador** (`pagina_minha`): 3 links → **botões-card** (ícone + nome + 1 linha), grid, hover, foco visível. Incluir **📅 Agenda** (hoje ausente nesse box).
- **Números do estoque** (`pagina_curadoria`, `stats` em `:699`): frase corrida → dois grupos de **cartões** (Candidatos: novos/selecionados/resumidos; Estoque: prontos/enviados/total), cada um com rótulo + micro-ajuda; barra dourada nos acionáveis (Novos, Prontos).
- **Lista de artigos** (`pagina_curadoria`, item em `:723`): `score` vira **chip** — verde (≥7), âmbar (4–6.9), cinza (<4) — com **legenda** explicando "importância clínica 0–10, só ordena, o assinante não vê"; título em destaque, pergunta/metadados secundários; contagem por tema como badge.

## Segurança (dinheiro + auth)

- **Troca de número:** só efetiva após OTP no **número novo**; bloqueia número já usado por outro assinante; rate-limit `otp`; escapar todas as entradas; migração de sessão feita junto com o update (assinante não perde o acesso). Número inválido → erro, nada muda.
- **Webhook/e-mail:** e-mail de venda em `try/except` (nunca bloqueia ativação); sem segredos no corpo; `ADMIN_EMAIL` via env.
- Todo POST novo carrega token/sessão e valida formato (telefone via `phone`, e-mail por regex simples).

## Tratamento de erros

- Falha ao enviar OTP (WhatsApp) → mensagem "não consegui enviar o código, tente de novo"; nada é trocado.
- Código errado/expirado → erro claro; conta tentativas (reusa lógica do `verificar`).
- E-mail de venda indisponível → loga e segue (ativação não falha).
- e-mail/nome inválidos → erro no form, sem salvar.

## Testes (unittest stdlib; externos mockados; SQLite tmp)

- **C1:** `pagina_minha` não emite "Ir para o arquivo"/"Sair desta conta"; emite botão "Meus dados". `_topbar("/minha")` omite o link "Minha conta". `_admin_nav` não tem "Minha conta".
- **C2:** `subscribers.atualizar_contato`/`atualizar_whatsapp` persistem; `auth_web.iniciar_troca_numero` grava código + chama `enviar_fn` no número novo; `confirmar_troca_numero`: código certo → troca número + migra sessão; errado/expirado → não troca; número de outro assinante → bloqueia. `pagina_meus_dados` renderiza os 3 blocos.
- **C3:** `_avisar_venda` monta assunto/corpo certos (mock `email_send.enviar`); chamado no path "ativado" (mock); exceção no e-mail não quebra `_executar`.
- **C-UI:** `pagina_curadoria` gera cartões e chips (classe `hi/md/lo` conforme o score); `pagina_minha` gera os botões-card incluindo Agenda.

## Fora de escopo / futuro

- Trocar a senha (login por senha) — separado, se um dia existir.
- Painel de métricas de vendas (só o e-mail por ora).
- Projetos A (agenda, feito) e B (curso, pausado) — intocados.
