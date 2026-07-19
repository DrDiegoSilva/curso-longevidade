# Site `artigos.drdiegosilva.com.br` — Landing + Arquivo Protegido — Design

**Data:** 2026-07-19
**Produto:** `curso-longevidade` (app isolado do clinicdspro) — assinatura "Atualização Científica" para médicos.

## Objetivo

Transformar o subdomínio `artigos.` num **site** com duas camadas:
1. **Landing pública** (`/`) — página de vendas (SEO, atrai médicos).
2. **Arquivo protegido** — todos os resumos já **enviados**, separados por **tema** e **data**, visíveis só para **assinante logado**.

Hoje `artigos.` e `curso.` abrem o mesmo app (o ebook), e nenhum digest enviado é persistido em lugar nenhum — o rascunho vira `SENT` e some. Este trabalho separa os subdomínios e cria a persistência + o site.

## Decisões (aprovadas no brainstorm 19/07)

- **Acesso ao arquivo:** TUDO PROTEGIDO. Só assinante logado vê qualquer resumo. Landing é o único conteúdo público (indexável).
- **Login:** código de 6 dígitos no WhatsApp (OTP), sem senha. Casa com o canal de entrega. Sessão por cookie server-side (30 dias).
- **CTA da landing:** por ora leva ao WhatsApp do Dr. Diego (checkout Asaas é Fase 2).
- **Stack:** só stdlib — `http.server` + `sqlite3` + `hmac`/`secrets`. Zero dependência nova. Isolado do clinicdspro.

## Arquitetura

### 1. Roteamento por host (`serve.py`)

O app lê o header `Host`:
- Host começa com **`artigos`** → **modo site** (landing + arquivo + login).
- Qualquer outro host (**`curso.`**, IP, health) → **modo ebook** (comportamento atual, intocado).

Rotas operacionais (`/health`, `/revisar/…`, `/pdf/…`, `/admin`, `/robots.txt`) respondem **independente do host**.

### 2. Banco SQLite (`app/db.py`) — `/data/artigos.db`

Módulo novo, stdlib `sqlite3`. `init()` cria as tabelas (idempotente, chamado no boot). Caminho vem de `config` (`ARTIGOS_DB`), sobrescrevível por env → testável em `/tmp`.

**`digests`** — um resumo enviado:
```
id INTEGER PRIMARY KEY
data TEXT            -- "2026-07-19" (dia do envio)
tema TEXT            -- chave do temas_config ("Obesidade","Hormonal"...)
tema_slug TEXT       -- "obesidade","hormonal","lipedema","performance","longevidade"
titulo_pt TEXT
resumo TEXT
gancho TEXT
grafico TEXT         -- JSON serializado (ou "")
doi TEXT
fonte TEXT
url TEXT
criado_em TEXT       -- ISO
UNIQUE(data, tema_slug)   -- upsert: reenvio do mesmo dia/tema não duplica
```

**`login_codes`** — OTP em aberto (1 por número):
```
whatsapp TEXT PRIMARY KEY
codigo_hash TEXT     -- sha256(codigo)
expira TEXT          -- ISO (agora + 10 min)
tentativas INTEGER   -- trava em 5
```

**`sessions`** — sessões logadas:
```
token TEXT PRIMARY KEY   -- secrets.token_hex(16)
whatsapp TEXT
nome TEXT
expira TEXT               -- ISO (agora + 30 dias)
```

**Funções puras/testáveis:**
- `slug(tema)` → slug ASCII minúsculo sem acento.
- `registrar_digest(art, conteudo, tmeta, data=None)` → upsert em `digests`.
- `listar_temas()` → `[{slug, tema, rotulo, emoji, cor, total}]` (contagem por tema, só temas com ≥1 digest).
- `listar_por_tema(slug)` → digests do tema, mais novo→antigo.
- `obter(slug, data)` → um digest ou `None`.

### 3. Persistência no envio (`daily.py::enviar_08h`)

Depois de `distribuir(...)` com sucesso, antes/junto do `queue_store.confirmar_envio`, chamar:
```python
db.registrar_digest(art, conteudo, tmeta)
```
Só o que foi **enviado de verdade** entra no arquivo (rascunho vetado nunca chega aqui). Falha do `registrar_digest` é logada mas **não derruba** o envio (o WhatsApp já saiu).

### 4. Login OTP + sessão (`app/auth_web.py`)

Módulo novo. Usa `db` + `subscribers` + `deliver`.

- `iniciar_login(whatsapp)`: normaliza o número; **só** prossegue se for assinante **ATIVO**; gera código de 6 dígitos, guarda `sha256` + expiry (10 min), envia via `deliver.enviar_texto`. Resposta **sempre neutra** ("se for assinante, enviamos o código") — anti-enumeração.
- `verificar(whatsapp, codigo)`: confere hash + não expirado + `tentativas<5`; incrementa tentativas em erro; em acerto apaga o code, cria sessão (`sessions`), retorna `token`. `None` se falha.
- `sessao(headers)`: lê cookie `sid`, busca sessão não expirada, retorna `{whatsapp,nome}` ou `None`.
- `logout(token)`: apaga a sessão.
- `_parse_cookie(header)` puro/testável.

Cookie: `sid=<token>; HttpOnly; Path=/; Max-Age=2592000; SameSite=Lax; Secure`.

### 5. Site (`app/site_web.py`) — render HTML (stdlib, inline CSS)

Visual **dark-luxury verde+dourado**, serif, mesma identidade do PDF; marca **Dr. Diego Silva · CRM-PR 54310**. Páginas:
- `landing()` — herói + o que é + 5 temas + resumo de exemplo "espiado" + planos (mensal/trimestral/semestral/anual) + CTA WhatsApp. **Pública**, indexável.
- `pagina_entrar(etapa, whatsapp="", erro="")` — passo 1 (número) / passo 2 (código).
- `hub_temas(temas)` — grade dos temas com contagem.
- `lista_tema(meta, digests)` — resumos do tema por data.
- `pagina_digest(meta, d)` — resumo completo: título, meta (fonte/data/DOI), texto, gráfico (reusa `pdf._grafico_html`), gancho (reusa `pdf._gancho_html`), botão do PDF.
- `pagina_minha(sub)` — página do assinante (status, link cancelar Fase 2, logout).

### 6. Rotas novas (`serve.py`, só no modo site)

| Rota | Método | Proteção | Ação |
|---|---|---|---|
| `/` | GET | pública | landing |
| `/entrar` | GET/POST | pública | login OTP (2 passos) |
| `/sair` | GET | — | logout → `/` |
| `/artigos` | GET | 🔒 sessão | hub dos temas |
| `/artigos/<slug>` | GET | 🔒 sessão | lista do tema |
| `/artigos/<slug>/<data>` | GET | 🔒 sessão | resumo completo |
| `/minha` | GET | 🔒 sessão | página do assinante |
| `/robots.txt` | GET | pública | `Allow: /`, `Disallow` no resto |

Sem sessão nas rotas 🔒 → `302 /entrar`.

## Configuração nova (`config.py`)
- `ARTIGOS_DB` = `os.path.join(DATA, "artigos.db")` (env `DSCURSO_ARTIGOS_DB` sobrescreve).
- `CONTATO_WHATSAPP` = env `DSCURSO_CONTATO_WHATSAPP` (fallback `whatsapp_destino()`) — número do CTA (`wa.me/<num>`).
- `PLANOS` = lista `[{nome, periodo, preco}]` com `preco` default `""` → landing mostra "sob consulta" até o Diego preencher (env/edição).

## Segurança
- Sessão server-side (cookie só carrega token aleatório; nada assinado no cliente).
- OTP: código hasheado (sha256), expira em 10 min, single-use, trava em 5 tentativas.
- Anti-enumeração no `/entrar` (resposta neutra; só envia a assinante ATIVO).
- `robots.txt` bloqueia indexação do arquivo/login.
- Nunca logar `accessCode`/código/telefone completo.
- HTML sempre com `html.escape` no conteúdo dinâmico.

## Fora de escopo (Fase 2)
- Checkout real (Asaas + Pix Automático), cadastro com cupom, cancelamento self-service + save flow.
- Busca no arquivo, paginação (audiência pequena; YAGNI).
- White-label / outros médicos.

## Testes (unittest)
- `db.py`: `slug()`; `registrar_digest` + `listar_temas`/`listar_por_tema`/`obter` roundtrip; upsert não duplica (mesmo dia/tema).
- `auth_web.py`: `iniciar_login` só p/ ATIVO (envio injetável); `verificar` acerto/erro/expiração/trava-5; `sessao`/`logout`; `_parse_cookie`.
- Render (`site_web`): smoke — cada página retorna HTML não-vazio com o conteúdo esperado escapado.
