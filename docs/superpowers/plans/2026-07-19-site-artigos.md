# Site artigos — landing + arquivo protegido — Plano de Implementação

> Execução: inline nesta sessão (audiência pequena, feature coesa). TDD nas partes puras (`db`, `auth_web`).

**Goal:** `artigos.drdiegosilva.com.br` = landing pública + arquivo dos resumos enviados por tema/data, protegido por login OTP no WhatsApp; digests persistidos em SQLite no envio das 08h.

**Tech:** stdlib (`http.server`, `sqlite3`, `hmac`/`secrets`, `hashlib`). Sem dependência nova.

## Global Constraints
- Só stdlib. Isolado do clinicdspro.
- Curador/ebook intocados: host ≠ `artigos*` mantém comportamento atual.
- HTML dinâmico sempre `html.escape`. Nunca logar telefone/código.
- Reusar `pdf._grafico_html` / `pdf._gancho_html` no render do digest (DRY).

---

### Task 1 — config: DB, contato, planos
**Files:** Modify `app/config.py`
- `ARTIGOS_DB = os.environ.get("DSCURSO_ARTIGOS_DB") or os.path.join(DATA, "artigos.db")`
- `CONTATO_WHATSAPP = os.environ.get("DSCURSO_CONTATO_WHATSAPP") or whatsapp_destino()` (função, pois whatsapp_destino é função) → definir como função `contato_whatsapp()`.
- `PLANOS` = `[{"nome":"Mensal","periodo":"/mês",...preco:""}, Trimestral, Semestral, Anual]`.
- Commit.

### Task 2 — db.py (TDD)
**Files:** Create `app/db.py`, Test `tests/test_db.py`
- Teste primeiro: `slug("Menopausa & Reposição Hormonal")=="menopausa-reposicao-hormonal"` etc; `registrar_digest`→`listar_temas`/`listar_por_tema`/`obter` roundtrip; upsert mesmo (data,slug) não duplica. Usa `DSCURSO_ARTIGOS_DB` num tmp.
- Implementar `init(conn=None)`, `_conn()`, `slug`, `registrar_digest(art,conteudo,tmeta,data=None)`, `listar_temas()`, `listar_por_tema(slug)`, `obter(slug,data)`.
- `listar_temas` cruza contagem do banco com `temas_config` (rotulo/emoji/cor); só temas com total>0.
- Rodar testes verde. Commit.

### Task 3 — auth_web.py (TDD)
**Files:** Create `app/auth_web.py`, Test `tests/test_auth_web.py`
- Teste primeiro: `_parse_cookie("a=1; sid=xyz")["sid"]=="xyz"`; `iniciar_login` chama envio só p/ ATIVO (fake subscribers+fake send), grava code; `verificar` acerto cria sessão, código errado incrementa tentativa, >5 trava, expirado falha; `sessao` acha por cookie, expirada→None; `logout`.
- Implementar usando `db` (tabelas `login_codes`,`sessions` criadas no `db.init`) + `subscribers.ativos()` + injeção do `enviar_fn` (default `deliver.enviar_texto`).
- Rodar testes verde. Commit.

### Task 4 — persistir no envio
**Files:** Modify `app/daily.py::enviar_08h`
- Após `distribuir`, `try: db.registrar_digest(art, conteudo, tmeta) except Exception as e: print(...)` (não derruba envio).
- `import db`. Commit.

### Task 5 — site_web.py (render)
**Files:** Create `app/site_web.py`
- `_base(titulo, corpo, publica=False)` layout dark-luxury verde/dourado, marca+CRM.
- `landing()`, `pagina_entrar(etapa,whatsapp,erro)`, `hub_temas(temas)`, `lista_tema(meta,digests)`, `pagina_digest(meta,d)`, `pagina_minha(sub)`, `robots_txt()`.
- `pagina_digest` reusa `pdf._grafico_html`/`_gancho_html` (parse `d["grafico"]` JSON).
- Smoke test opcional `tests/test_site_web.py` (cada página não-vazia, escapa conteúdo).
- Commit.

### Task 6 — serve.py (roteamento por host + rotas)
**Files:** Modify `app/serve.py`
- No boot: `import db; db.init()`.
- Helper `_host_artigos(self)` = `self.headers.get("Host","").lower().startswith("artigos")`.
- `do_GET`: manter `/health /revisar /pdf /admin` host-agnósticos; adicionar `/robots.txt`; se `_host_artigos`: `/`→landing, `/entrar`→login GET, `/sair`→logout, `/artigos*`→(checa sessão, senão 302 /entrar), `/minha`→sessão; senão cai no ebook atual.
- `do_POST`: `/entrar` (passo número → `auth_web.iniciar_login`; passo código → `auth_web.verificar` seta cookie e 302 /artigos).
- Helpers `_redirect(loc, cookie=None)`, `_set_cookie`.
- Commit.

### Task 7 — deploy
- Trocar env `DSCURSO_PUBLIC_URL`→`https://artigos.drdiegosilva.com.br`, add `DSCURSO_CONTATO_WHATSAPP`.
- `git push` (após OK do Diego) → auto-deploy Campinas. Validar landing pública + fluxo login.
