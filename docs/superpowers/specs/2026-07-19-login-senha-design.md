# Login com senha — site `artigos.` (Atualização Científica)

**Data:** 2026-07-19
**Contexto:** Hoje o login do portal depende do WhatsApp TODA vez (OTP de 6 dígitos por WhatsApp). Quando a instância Evolution caiu, ninguém conseguiu entrar. Esta feature desacopla o login do WhatsApp.

## Decisão de produto (travada com o Diego)
- **Usuário = WhatsApp (com DDD) + senha.** O número que o médico decora vira o login; digitar o número NÃO dispara nada no WhatsApp → entra mesmo com o WhatsApp fora do ar.
- **Entrega do link de criar/redefinir senha = E-MAIL** (Resend, já integrado). WhatsApp segue SÓ entregando os artigos.
- **1º acesso:** na ativação (webhook Asaas), a boas-vindas nos **dois canais** (WhatsApp E e-mail) traz o **mesmo link tokenizado** "crie sua senha pra acessar os resumos no site" (redundância proposital: e-mail cobre se o WhatsApp cair).
- **Esqueci a senha:** informa o WhatsApp → link de redefinir por e-mail.
- **Fallback p/ quem não tem e-mail na ficha** (ex.: cortesia manual): recebe o link por **WhatsApp**; e o login por **código (OTP antigo)** fica como emergência escondida na tela de login.
- **Regra de senha:** ≥6 caracteres, com **letra e número**.
- **Hash:** PBKDF2-HMAC-SHA256 (stdlib), salt por usuário, ~200k iterações. Nunca senha crua.

## Fluxos
1. **Login** (`/entrar`): campos WhatsApp + senha → confere hash → cria sessão (reusa `sessions` + cookie `sid`, 30 dias). Sem senha ainda → mensagem "crie sua senha" (botão → 1º acesso). Credencial errada / inativo → erro genérico.
2. **1º acesso / esqueci** (`/primeiro-acesso`, `/esqueci`): informa WhatsApp → cria token (`senha_tokens`) → envia link por e-mail (fallback WhatsApp) → resposta **neutra** (anti-enumeração).
3. **Criar senha** (`/criar-senha?token=`): valida token (existe, não usado, não expirado) → form (senha + repetir) → valida força → grava `senha_hash`, consome token, cria sessão → `/artigos`.
4. **Emergência**: link "entrar sem senha (código no WhatsApp)" mantém o OTP antigo (`/entrar-codigo`).

## Componentes / arquivos
- **`passwords.py`** (NOVO, puro, TDD): `hash_senha`, `conferir_senha`, `validar_forca`.
- **`db.py`**: coluna `senha_hash` em subscribers (na CREATE + ALTER idempotente p/ banco existente) · tabela `senha_tokens(token PK, whatsapp, expira, usado)` + RLS · helpers `criar_token_senha/obter_token_senha/consumir_token_senha`.
- **`subscribers.py`**: `senha_hash` em `_COLS` · `definir_senha(id, hash)`.
- **`auth_web.py`**: `login_senha(wpp,senha)->(status,token)` · `iniciar_definir_senha(wpp,motivo)` · `definir_senha(token,s,s2)->(status,sessao)` · `preparar_primeiro_acesso(wpp)->link` · `_criar_sessao` (refatorado de `verificar`) · builders de link/e-mail. OTP (`iniciar_login`/`verificar`) intacto = fallback.
- **`webhook_asaas.py`**: no ATIVAR, boas-vindas com o link de criar senha nos 2 canais (WhatsApp via `enviar_fn`, e-mail via `email_send`).
- **`serve.py`**: rotas `/entrar` (GET login, POST senha), `/primeiro-acesso`, `/esqueci`, `/criar-senha`, `/entrar-codigo` (fallback OTP).
- **`site_web.py`**: `pagina_login`, `pagina_recuperar` (1º acesso/esqueci), `pagina_criar_senha`, `pagina_msg` (neutra).
- **`config.py`**: `ARTIGOS_URL` (env `DSCURSO_ARTIGOS_URL`, default `https://artigos.drdiegosilva.com.br`) — corrige de brinde o link que apontava pra `curso.` · `PRODUTO`.

## Testes
- `test_passwords.py` (puro): roundtrip, senha errada, formato inválido, regras de força.
- `test_auth_web.py` (+): `login_senha` (ok/sem_senha/credenciais/inativo), `definir_senha` (token→sessão), token expirado/usado, `iniciar_definir_senha` neutro.
- `test_db.py` (+): helpers de token, `senha_hash`/`definir_senha`.

## Fora de escopo
- Trocar senha logado (já existe padrão no clinicdspro; aqui não pediram). 2FA. Bloqueio por tentativas no login por senha (rate-limit fica p/ depois; OTP já trava em 5).

## Deploy
- ALTER da coluna roda no `db.init` (idempotente). Sem migração manual.
- ⚠️ Pôr o e-mail do cliente Asaas `cus_000008436114` na ficha manual do Diego p/ ele testar o fluxo por e-mail.
- Env nova opcional: `DSCURSO_ARTIGOS_URL` (senão usa o default correto).
