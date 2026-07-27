# Login por CPF (senha + fallback código no WhatsApp)

**Data:** 2026-07-26
**Status:** aprovado (brainstorming) → aguardando plano de implementação
**Branch:** feat/login-cpf (base e32412d)

## Objetivo

Permitir que o assinante entre no portal usando o **CPF** como identificador, em vez do número de WhatsApp digitado. Resolve de vez o login de assinantes **internacionais**: hoje um número dos EUA digitado sem `+` (ex.: `15555551234`, 11 dígitos) cai em `phone.normalizar` e ganha o prefixo `55` (`5515555551234`), que **não casa** com o valor salvo `+15555551234` — travando os dois logins atuais (senha e OTP), que dependem do número digitado.

Logar por CPF **elimina a digitação do número**, que é a raiz do problema.

### Decisão (do brainstorming)

- **Ambos:** CPF + **senha** (principal) e, como fallback, **código no WhatsApp** (OTP) — espelhando o login por WhatsApp que já existe (`/entrar` + `/entrar-codigo`).

### Ideia-chave do design

Todo o login interno já funciona **por número de WhatsApp** (`login_senha`, `iniciar_login`, `verificar`, sessão keyed por whatsapp). Então as funções de CPF apenas **acham o assinante pelo CPF e delegam** para as funções de WhatsApp já existentes e testadas. O CPF é só uma "porta de entrada" — **não reimplemento autenticação**.

## Não-objetivos (YAGNI)

- Não mexer no login por WhatsApp existente (comportamento inalterado; parâmetros novos têm default).
- Não fazer auto-detecção "número OU CPF no mesmo campo" — telas dedicadas são mais claras.
- Não bloquear por dígito verificador do CPF (mantém resposta neutra/anti-enumeração). A comparação é só por dígitos.
- Não criar recuperação de senha por CPF: quem não tem senha usa o **fallback de código**, ou o admin reenvia o link de 1º acesso (botão novo em Assinantes).

## Componentes

### 1. `auth_web` — 4 funções (só `_ativo_por_cpf` tem lógica nova; o resto delega)

```python
def _ativo_por_cpf(cpf_in):
    """Assinante ATIVO cujos dígitos de CPF batem, ou None. (única lógica nova)"""
    import cpf as cpfmod
    n = cpfmod.so_digitos(cpf_in)
    if not n:
        return None
    return next((a for a in subscribers.ativos()
                 if cpfmod.so_digitos(a.get("cpf", "")) == n), None)

def login_senha_cpf(cpf_in, senha):
    """CPF + senha. Resolve o CPF e delega pro login_senha (por WhatsApp).
    (status, token): 'ok' | 'sem_senha' | 'credenciais' | 'inativo'."""
    a = _ativo_por_cpf(cpf_in)
    if not a:
        return ("inativo", None)
    return login_senha(a.get("whatsapp", ""), senha)

def iniciar_login_cpf(cpf_in, enviar_fn=None):
    """Manda o OTP pro WhatsApp SALVO do assinante achado por CPF. Neutro. True se enviou."""
    a = _ativo_por_cpf(cpf_in)
    if not a:
        return False
    return iniciar_login(a.get("whatsapp", ""), enviar_fn)

def verificar_cpf(cpf_in, codigo):
    """Verifica o OTP p/ o assinante achado por CPF. Token da sessão, ou None."""
    a = _ativo_por_cpf(cpf_in)
    if not a:
        return None
    return verificar(a.get("whatsapp", ""), codigo)
```

Por que delega funciona: para um assinante achado por CPF, `a["whatsapp"]` é o número salvo (já normalizado). `login_senha`/`iniciar_login`/`verificar` fazem `_norm(whatsapp)` (idempotente) e resolvem por `_assinante_ativo` — casam. A sessão é criada com o WhatsApp salvo, consistente com o resto do app (que resolve o assinante logado pela sessão→whatsapp).

### 2. UI — parametrizar as telas existentes com `via` (DRY, sem duplicar página)

`site_web.pagina_login` e `site_web.pagina_entrar` ganham `via="whatsapp"` (default = comportamento atual, zero mudança). Quando `via="cpf"`:
- Label "CPF"; campo `name="cpf"` (`inputmode="numeric"`, placeholder `000.000.000-00`); `action` → `/entrar-cpf` (senha) ou `/entrar-cpf-codigo` (código).
- Cross-links ajustam: na tela CPF+senha, "Sem senha? Entrar com código no WhatsApp" → `/entrar-cpf-codigo`, e "← Entrar com WhatsApp" → `/entrar`. **Não** mostra "Primeiro acesso/Esqueci" no modo CPF (esses são keyed por WhatsApp/e-mail; quem não tem senha usa o código).
- O parâmetro existente `whatsapp=` passa a servir de **valor do identificador a repreencher** (carrega o CPF quando `via="cpf"`) — documentado por comentário. Isso evita mexer nos call-sites atuais.
- Aviso `sem_senha`: no modo CPF, texto = "Você ainda não criou senha. Entre com **código no WhatsApp** abaixo (ou peça seu link de acesso)."

**Descoberta:** em `pagina_login` no modo WhatsApp (padrão), adicionar um link discreto: **"Assinante fora do Brasil / sem WhatsApp brasileiro? Entrar com CPF"** → `/entrar-cpf`.

### 3. Rotas em `serve.py` (espelham as de WhatsApp, mesmos rate limits e redirects)

GET (perto das linhas 296-299):
```python
if path == "/entrar-cpf":
    return self._html(site_web.pagina_login(via="cpf"))
if path == "/entrar-cpf-codigo":
    return self._html(site_web.pagina_entrar("numero", via="cpf"))
```

POST (perto das linhas 577-600):
```python
if path == "/entrar-cpf":
    if not self._rate_ok("login", 15, 300):
        return
    import site_web, auth_web
    doc = g("cpf")
    status, token = auth_web.login_senha_cpf(doc, g("senha"))
    if status == "ok":
        return self._redirect("/artigos", token=token)
    if status == "sem_senha":
        return self._html(site_web.pagina_login(sem_senha=True, whatsapp=doc, via="cpf"))
    return self._html(site_web.pagina_login(erro="CPF ou senha incorretos.", whatsapp=doc, via="cpf"))
if path == "/entrar-cpf-codigo":
    if not self._rate_ok("otp", 5, 600):
        return
    import site_web, auth_web
    doc = g("cpf")
    if g("etapa") == "codigo":
        token = auth_web.verificar_cpf(doc, g("codigo"))
        if token:
            return self._redirect("/artigos", token=token)
        return self._html(site_web.pagina_entrar("codigo", whatsapp=doc, via="cpf",
                          erro="Código inválido ou expirado. Tente novamente."))
    auth_web.iniciar_login_cpf(doc)  # neutro: só envia se achar assinante ativo
    return self._html(site_web.pagina_entrar("codigo", whatsapp=doc, via="cpf"))
```

`robots.txt` (site_web): acrescentar `Disallow: /entrar-cpf` (as páginas já têm `noindex`).

## Segurança

- **Anti-enumeração:** CPF desconhecido cai em `'inativo'` → handler mostra a **mesma** mensagem "CPF ou senha incorretos." (não revela se o CPF existe). O caminho de código é totalmente neutro (sempre mostra a tela de código). O status `'sem_senha'` revela que existe assinatura sem senha — **mesmo comportamento do login por WhatsApp atual** (aceito, consistente).
- **Rate limit:** reusa os buckets `login` (15/5min) e `otp` (5/10min) por IP.
- O CPF não é segredo forte, por isso sempre exige 2º fator (senha ou OTP). O OTP vai pro **número salvo** (não o digitado) — não dá pra desviar o código pra outro número.

## Testes (unittest standalone, padrão `test_mensagens`/`test_webhook`)

`app/tests/test_login_cpf.py`:
- `login_senha_cpf`: ativo com cpf+senha → `('ok', token)`; senha errada → `('credenciais', None)`; sem senha → `('sem_senha', None)`; CPF desconhecido → `('inativo', None)`; CPF com pontuação (`000.000.000-00`) casa pelos dígitos.
- **intl:** assinante `whatsapp="+15555551234"` com cpf+senha → `login_senha_cpf` retorna `('ok', token)` (token truthy) — prova login sem digitar número.
- `iniciar_login_cpf(cpf, enviar_fn=spy)` → `True` e o spy é chamado com o número salvo; CPF desconhecido → `False` e spy não é chamado. Caso intl: spy recebe `+15555551234` (ou sua forma normalizada).
- `verificar_cpf`: dispara `iniciar_login_cpf` capturando o código de 6 dígitos da mensagem do spy (regex `\*(\d{6})\*`); código certo → token; código errado → `None`; CPF desconhecido → `None`.

`app/tests/test_login_cpf_ui.py`:
- `pagina_login(via="cpf")` → contém `action="/entrar-cpf"`, label "CPF", `name="cpf"`.
- `pagina_login()` (default) → **inalterado**: `action="/entrar"`, `name="whatsapp"`, e agora contém o link de descoberta `href="/entrar-cpf"`.
- `pagina_entrar("numero", via="cpf")` → `action="/entrar-cpf-codigo"`, campo CPF.
- `pagina_entrar("codigo", whatsapp="12345678901", via="cpf")` → hidden `name="cpf"` com o valor, `action="/entrar-cpf-codigo"`.

## Critérios de aceite

- [ ] `/entrar-cpf` (CPF+senha) e `/entrar-cpf-codigo` (CPF→código) funcionam e entram no portal.
- [ ] Assinante internacional loga por CPF sem digitar o número; OTP (se usado) chega no número salvo.
- [ ] Login por WhatsApp existente inalterado (call-sites atuais intactos; testes existentes verdes).
- [ ] Link de descoberta "Entrar com CPF" aparece na tela de login principal.
- [ ] Respostas neutras (anti-enumeração) e rate limits aplicados.
- [ ] Testes novos passam; suíte inteira verde.

## Arquivos

- `app/auth_web.py` — 4 funções novas (após `login_senha`/`precisa_criar_senha`).
- `app/site_web.py` — `pagina_login` e `pagina_entrar` parametrizadas (`via`), link de descoberta, `robots.txt`.
- `app/serve.py` — 2 rotas GET + 2 POST.
- `app/tests/test_login_cpf.py`, `app/tests/test_login_cpf_ui.py` — novos.
