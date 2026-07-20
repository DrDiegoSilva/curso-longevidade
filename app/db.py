"""Banco do site artigos (SQLite, stdlib) — persiste cada digest ENVIADO e serve
o arquivo protegido (por tema/data) + tabelas de login OTP e sessões.

Caminho vem de config.artigos_db() (env DSCURSO_ARTIGOS_DB sobrescreve → testável).
Partes puras (slug, registrar/listar/obter) sem rede; auth_web usa as tabelas daqui.
"""
import os
import json
import sqlite3
import unicodedata
import re
import config

_TEMAS_JSON = os.path.join(os.path.dirname(__file__), "temas_config.json")


def _temas_cfg():
    try:
        with open(_TEMAS_JSON, encoding="utf-8") as f:
            return json.load(f).get("temas", {})
    except Exception:
        return {}


def slug(texto):
    """Slug ASCII minúsculo sem acento: 'Menopausa & Reposição' -> 'menopausa-reposicao'."""
    n = unicodedata.normalize("NFKD", texto or "")
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"[^a-zA-Z0-9]+", "-", n).strip("-").lower()
    return n or "tema"


def _is_pg():
    return bool(config.DATABASE_URL)


class _Wrap:
    """Interface comum estilo sqlite sobre sqlite3 OU psycopg2 (Postgres/Supabase).
    Traduz placeholders ? -> %s no Postgres; commit/rollback+close no fim do `with`.
    """
    def __init__(self, conn, pg):
        self._c = conn
        self._pg = pg

    def execute(self, sql, params=()):
        if self._pg:
            import psycopg2.extras
            cur = self._c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql.replace("?", "%s"), params)
        else:
            cur = self._c.cursor()
            cur.execute(sql, params)
        return cur

    def executescript(self, sql):
        cur = self._c.cursor()
        cur.execute(sql) if self._pg else cur.executescript(sql)
        return cur

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *a):
        try:
            self._c.commit() if exc_type is None else self._c.rollback()
        finally:
            self._c.close()


def _conn():
    if _is_pg():
        import psycopg2
        return _Wrap(psycopg2.connect(config.DATABASE_URL), True)
    os.makedirs(os.path.dirname(config.artigos_db()) or ".", exist_ok=True)
    c = sqlite3.connect(config.artigos_db())
    c.row_factory = sqlite3.Row
    return _Wrap(c, False)


_INITED = False


def init():
    global _INITED
    if _INITED:
        return
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS digests (
                data TEXT NOT NULL,
                tema TEXT NOT NULL,
                tema_slug TEXT NOT NULL,
                titulo_pt TEXT NOT NULL,
                resumo TEXT NOT NULL,
                gancho TEXT,
                grafico TEXT,
                doi TEXT,
                fonte TEXT,
                url TEXT,
                criado_em TEXT,
                PRIMARY KEY (data, tema_slug)
            );
            CREATE TABLE IF NOT EXISTS login_codes (
                whatsapp TEXT PRIMARY KEY,
                codigo_hash TEXT NOT NULL,
                expira TEXT NOT NULL,
                tentativas INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                whatsapp TEXT NOT NULL,
                nome TEXT,
                expira TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS subscribers (
                id TEXT PRIMARY KEY,
                nome TEXT, whatsapp TEXT, email TEXT, cpf TEXT,
                plano TEXT, metodo TEXT,
                status TEXT DEFAULT 'ATIVO',
                asaas_customer_id TEXT, asaas_subscription_id TEXT, asaas_payment_id TEXT,
                proximo_vencimento TEXT, acesso_ate TEXT, carencia_ate TEXT, aviso_renov_em TEXT,
                criado_em TEXT, cancelado_em TEXT, cancel_motivo TEXT, oferta_retencao_em TEXT,
                senha_hash TEXT, curador INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS pending_signups (
                token TEXT PRIMARY KEY,
                nome TEXT, email TEXT, cpf TEXT, whatsapp TEXT,
                plano TEXT, metodo TEXT, parcelas INTEGER, valor REAL,
                criado_em TEXT
            );
            CREATE TABLE IF NOT EXISTS webhook_events (
                payment_id TEXT, event TEXT, processed_em TEXT,
                PRIMARY KEY (payment_id, event)
            );
            CREATE TABLE IF NOT EXISTS cupons (
                codigo TEXT PRIMARY KEY, ativo INTEGER DEFAULT 1, descricao TEXT, criado_em TEXT
            );
            CREATE TABLE IF NOT EXISTS senha_tokens (
                token TEXT PRIMARY KEY,
                whatsapp TEXT NOT NULL,
                expira TEXT NOT NULL,
                usado INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS curadoria_candidatos (
                id TEXT PRIMARY KEY,
                tema TEXT, titulo TEXT, fonte TEXT, data TEXT, doi TEXT, url TEXT,
                abstract TEXT, pergunta TEXT, score REAL, chave TEXT UNIQUE,
                status TEXT DEFAULT 'novo', criado_em TEXT
            );
            CREATE TABLE IF NOT EXISTS reserva_resumos (
                id TEXT PRIMARY KEY, candidato_id TEXT,
                tema TEXT, titulo_pt TEXT, resumo TEXT, gancho TEXT, grafico TEXT,
                doi TEXT, fonte TEXT, url TEXT, data TEXT,
                status TEXT DEFAULT 'pronto', prioridade INTEGER DEFAULT 0,
                origem TEXT DEFAULT 'varredura', enviado_em TEXT, criado_em TEXT
            );
            CREATE TABLE IF NOT EXISTS daily_drafts (
                data TEXT PRIMARY KEY,
                review_token TEXT,
                status TEXT DEFAULT 'DRAFT',
                payload TEXT,
                criado_em TEXT,
                atualizado_em TEXT
            );
            """
        )
    _migrar_colunas()
    _seed_cupons()
    if _is_pg():
        _habilitar_rls()        # trava a Data API pública do Supabase (app conecta direto e ignora RLS)
    _INITED = True


_TABELAS = ["digests", "login_codes", "sessions", "subscribers",
            "pending_signups", "webhook_events", "cupons", "senha_tokens",
            "curadoria_candidatos", "reserva_resumos", "daily_drafts"]


def _add_coluna(c, tabela, coluna, tipo):
    """ADD COLUMN idempotente (pg: IF NOT EXISTS; sqlite: try/except duplicata)."""
    if _is_pg():
        c.execute(f"ALTER TABLE {tabela} ADD COLUMN IF NOT EXISTS {coluna} {tipo}")
    else:
        try:
            c.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
        except Exception:
            pass  # coluna já existe (banco recém-criado pela CREATE TABLE)


def _migrar_colunas():
    """Adiciona colunas novas a bancos JÁ existentes (idempotente).
    Banco novo/testes já nasce com a coluna via CREATE TABLE — aqui o ALTER é
    p/ o Supabase de produção que foi criado antes desta coluna existir."""
    with _conn() as c:
        _add_coluna(c, "subscribers", "senha_hash", "TEXT")
        _add_coluna(c, "subscribers", "curador", "INTEGER DEFAULT 0")
        _add_coluna(c, "cupons", "usos", "INTEGER DEFAULT 0")
        _add_coluna(c, "cupons", "uso_unico", "INTEGER DEFAULT 1")
        _add_coluna(c, "cupons", "dias_acesso", "INTEGER DEFAULT 0")
        _add_coluna(c, "reserva_resumos", "prioridade", "INTEGER DEFAULT 0")
        _add_coluna(c, "reserva_resumos", "origem", "TEXT DEFAULT 'varredura'")
        _add_coluna(c, "reserva_resumos", "enviado_em", "TEXT")


def _habilitar_rls():
    """ENABLE RLS em toda tabela (sem policy = Data API pública bloqueada). Idempotente."""
    with _conn() as c:
        for t in _TABELAS:
            c.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")


def _seed_cupons():
    from datetime import datetime
    codigos = config.cupons_seed()
    if not codigos:
        return
    with _conn() as c:
        for cod in codigos:
            # cupons do env = multi-uso (o Diego compartilha o mesmo código)
            c.execute("INSERT INTO cupons (codigo,ativo,descricao,uso_unico,criado_em) VALUES (?,1,'seed',0,?) "
                      "ON CONFLICT (codigo) DO UPDATE SET uso_unico=0", (cod, datetime.now().isoformat()))


def criar_pending(dados):
    """Cadastro em aberto (antes do redirect ao checkout). Retorna o token (externalReference)."""
    import secrets
    from datetime import datetime
    token = secrets.token_hex(16)
    with _conn() as c:
        c.execute(
            """INSERT INTO pending_signups (token,nome,email,cpf,whatsapp,plano,metodo,parcelas,valor,criado_em)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (token, dados.get("nome", ""), dados.get("email", ""), dados.get("cpf", ""),
             dados.get("whatsapp", ""), dados.get("plano", ""), dados.get("metodo", ""),
             int(dados.get("parcelas", 1)), float(dados.get("valor", 0)), datetime.now().isoformat()),
        )
    return token


def obter_pending(token):
    with _conn() as c:
        r = c.execute("SELECT * FROM pending_signups WHERE token=?", (token,)).fetchone()
    return dict(r) if r else None


def registrar_webhook(payment_id, event):
    """True se é a 1ª vez (processar); False se já visto (idempotência)."""
    from datetime import datetime
    with _conn() as c:
        cur = c.execute("INSERT INTO webhook_events (payment_id,event,processed_em) VALUES (?,?,?) "
                        "ON CONFLICT (payment_id,event) DO NOTHING",
                        (payment_id or "", event or "", datetime.now().isoformat()))
        return cur.rowcount > 0


def cupom_valido(codigo):
    if not codigo:
        return False
    with _conn() as c:
        r = c.execute("SELECT ativo FROM cupons WHERE codigo=?", ((codigo or "").strip().upper(),)).fetchone()
    return bool(r and r["ativo"])


def criar_cupom(descricao="", uso_unico=True, dias_acesso=0, codigo=None):
    """Gera um cupom de cortesia. dias_acesso=0 => acesso permanente; N => N dias.
    Sem código informado, cria um aleatório. Retorna o código."""
    import secrets
    from datetime import datetime
    cod = (codigo or secrets.token_hex(4)).strip().upper()
    with _conn() as c:
        c.execute("INSERT INTO cupons (codigo,ativo,descricao,usos,uso_unico,dias_acesso,criado_em) VALUES (?,1,?,0,?,?,?) "
                  "ON CONFLICT (codigo) DO NOTHING",
                  (cod, descricao or "", 1 if uso_unico else 0, int(dias_acesso or 0), datetime.now().isoformat()))
    return cod


def obter_cupom(codigo):
    with _conn() as c:
        r = c.execute("SELECT * FROM cupons WHERE codigo=?", ((codigo or "").strip().upper(),)).fetchone()
    return dict(r) if r else None


def listar_cupons():
    with _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM cupons ORDER BY criado_em DESC").fetchall()]


def consumir_cupom(codigo):
    """Marca 1 uso do cupom. Se for de uso único, desativa (ativo=0)."""
    cod = (codigo or "").strip().upper()
    with _conn() as c:
        r = c.execute("SELECT uso_unico,usos FROM cupons WHERE codigo=?", (cod,)).fetchone()
        if not r:
            return
        novos = (r["usos"] or 0) + 1
        ativo = 0 if r["uso_unico"] else 1
        c.execute("UPDATE cupons SET usos=?, ativo=? WHERE codigo=?", (novos, ativo, cod))


# ── Tokens de definição/redefinição de senha ──
def criar_token_senha(whatsapp, validade_horas=1):
    """Cria um token de uso único p/ criar/redefinir senha. Retorna o token."""
    import secrets
    from datetime import datetime, timedelta
    token = secrets.token_hex(24)
    expira = (datetime.now() + timedelta(hours=validade_horas)).isoformat()
    with _conn() as c:
        c.execute("INSERT INTO senha_tokens (token,whatsapp,expira,usado) VALUES (?,?,?,0)",
                  (token, whatsapp or "", expira))
    return token


def obter_token_senha(token):
    """Dados do token {whatsapp,expira} se existe, NÃO usado e NÃO expirado; senão None."""
    from datetime import datetime
    if not token:
        return None
    with _conn() as c:
        r = c.execute("SELECT * FROM senha_tokens WHERE token=?", (token,)).fetchone()
    if not r:
        return None
    d = dict(r)
    if d.get("usado"):
        return None
    try:
        if datetime.fromisoformat(d["expira"]) < datetime.now():
            return None
    except Exception:
        return None
    return d


def consumir_token_senha(token):
    """Marca o token como usado (uso único)."""
    with _conn() as c:
        c.execute("UPDATE senha_tokens SET usado=1 WHERE token=?", (token,))


# ── Curadoria (candidatos) + Reserva (resumos prontos) — banco privado, NÃO publica ──
def salvar_candidatos(cands):
    """Insere candidatos novos (dedup por chave). Retorna quantos entraram."""
    import secrets
    from datetime import datetime
    novos = 0
    with _conn() as c:
        for x in cands:
            if not x.get("chave"):
                continue
            cur = c.execute(
                """INSERT INTO curadoria_candidatos
                   (id,tema,titulo,fonte,data,doi,url,abstract,pergunta,score,chave,status,criado_em)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?, 'novo', ?)
                   ON CONFLICT (chave) DO NOTHING""",
                (secrets.token_hex(8), x.get("tema", ""), x.get("titulo", ""), x.get("fonte", ""),
                 x.get("data", ""), x.get("doi", ""), x.get("url", ""), x.get("abstract", ""),
                 x.get("pergunta", ""), float(x.get("score", 0) or 0), x.get("chave"),
                 datetime.now().isoformat()))
            if cur.rowcount and cur.rowcount > 0:
                novos += 1
    return novos


def listar_candidatos(status=None, tema=None):
    q = "SELECT * FROM curadoria_candidatos"
    conds, params = [], []
    if status:
        conds.append("status=?"); params.append(status)
    if tema:
        conds.append("tema=?"); params.append(tema)
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY tema, score DESC, criado_em DESC"
    with _conn() as c:
        return [dict(r) for r in c.execute(q, params).fetchall()]


def definir_selecao(ids):
    """Marca 'selecionado' os ids dados e volta p/ 'novo' os que saíram da seleção.
    Não toca em 'resumido'/'descartado'."""
    alvo = set(ids or [])
    with _conn() as c:
        atuais = [r["id"] for r in c.execute(
            "SELECT id FROM curadoria_candidatos WHERE status IN ('novo','selecionado')").fetchall()]
        for i in atuais:
            c.execute("UPDATE curadoria_candidatos SET status=? WHERE id=?",
                      ("selecionado" if i in alvo else "novo", i))


def marcar_candidatos(ids, status):
    with _conn() as c:
        for i in (ids or []):
            c.execute("UPDATE curadoria_candidatos SET status=? WHERE id=?", (status, i))


def contar_candidatos():
    with _conn() as c:
        rows = c.execute("SELECT status, COUNT(*) n FROM curadoria_candidatos GROUP BY status").fetchall()
    return {r["status"]: r["n"] for r in rows}


def salvar_reserva(reg):
    """Salva um resumo pronto na reserva/fila. prioridade>0 = fura fila (artigo do Diego).
    Retorna o id."""
    import secrets
    from datetime import datetime
    rid = secrets.token_hex(8)
    with _conn() as c:
        c.execute(
            """INSERT INTO reserva_resumos
               (id,candidato_id,tema,titulo_pt,resumo,gancho,grafico,doi,fonte,url,data,status,prioridade,origem,criado_em)
               VALUES (?,?,?,?,?,?,?,?,?,?,?, 'pronto', ?,?,?)""",
            (rid, reg.get("candidato_id"), reg.get("tema", ""), reg.get("titulo_pt", ""),
             reg.get("resumo", ""), reg.get("gancho", ""), reg.get("grafico", ""), reg.get("doi", ""),
             reg.get("fonte", ""), reg.get("url", ""), reg.get("data", ""),
             int(reg.get("prioridade", 0) or 0), reg.get("origem", "varredura"), datetime.now().isoformat()))
    return rid


def listar_reserva(status=None):
    q = "SELECT * FROM reserva_resumos"
    params = []
    if status:
        q += " WHERE status=?"; params.append(status)
    q += " ORDER BY prioridade DESC, criado_em DESC"
    with _conn() as c:
        return [dict(r) for r in c.execute(q, params).fetchall()]


def contar_reserva_pronto():
    """Quantos resumos 'pronto' (estoque disponível p/ enviar) há na reserva."""
    with _conn() as c:
        r = c.execute("SELECT COUNT(*) n FROM reserva_resumos WHERE status='pronto'").fetchone()
    return r["n"] if r else 0


def proximo_da_reserva():
    """Próximo resumo a enviar da fila: prioridade (artigos do Diego) primeiro, depois
    os mais antigos. Só 'pronto'. Retorna dict ou None (não marca — o envio confirma)."""
    with _conn() as c:
        r = c.execute("SELECT * FROM reserva_resumos WHERE status='pronto' "
                      "ORDER BY prioridade DESC, criado_em ASC LIMIT 1").fetchone()
    return dict(r) if r else None


def marcar_reserva_enviado(rid):
    from datetime import datetime
    with _conn() as c:
        c.execute("UPDATE reserva_resumos SET status='enviado', enviado_em=? WHERE id=?",
                  (datetime.now().isoformat(), rid))


def atualizar_reserva(rid, titulo_pt=None, resumo=None):
    """Edita título e/ou resumo de um item da reserva (curador ajusta o que a IA gerou)."""
    sets, params = [], []
    if titulo_pt is not None:
        sets.append("titulo_pt=?"); params.append(titulo_pt)
    if resumo is not None:
        sets.append("resumo=?"); params.append(resumo)
    if not sets:
        return
    params.append(rid)
    with _conn() as c:
        c.execute(f"UPDATE reserva_resumos SET {','.join(sets)} WHERE id=?", params)


def remover_reserva(rid):
    with _conn() as c:
        c.execute("DELETE FROM reserva_resumos WHERE id=?", (rid,))


# ── Rascunho do dia (persistido no banco — sobrevive a deploy/restart) ──
def salvar_draft(data, review_token, status, payload):
    from datetime import datetime
    agora = datetime.now().isoformat()
    with _conn() as c:
        c.execute(
            """INSERT INTO daily_drafts (data,review_token,status,payload,criado_em,atualizado_em)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(data) DO UPDATE SET review_token=excluded.review_token,
                 status=excluded.status, payload=excluded.payload, atualizado_em=excluded.atualizado_em""",
            (data, review_token or "", status or "DRAFT",
             json.dumps(payload, ensure_ascii=False), agora, agora))


def obter_draft(data):
    with _conn() as c:
        r = c.execute("SELECT payload FROM daily_drafts WHERE data=?", (data,)).fetchone()
    return json.loads(r["payload"]) if r and r["payload"] else None


def obter_draft_por_token(token):
    if not token:
        return None
    with _conn() as c:
        r = c.execute("SELECT payload FROM daily_drafts WHERE review_token=?", (token,)).fetchone()
    return json.loads(r["payload"]) if r and r["payload"] else None


def registrar_digest(art, conteudo, tmeta=None, data=None):
    """Upsert de um digest enviado (chave = data + tema_slug)."""
    from datetime import datetime
    tema = art.get("tema", "") or "Geral"
    s = slug(tema)
    d = data or datetime.now().strftime("%Y-%m-%d")
    grafico = conteudo.get("grafico")
    grafico_txt = json.dumps(grafico, ensure_ascii=False) if grafico else ""
    with _conn() as c:
        c.execute(
            """INSERT INTO digests (data,tema,tema_slug,titulo_pt,resumo,gancho,grafico,doi,fonte,url,criado_em)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(data,tema_slug) DO UPDATE SET
                 tema=excluded.tema, titulo_pt=excluded.titulo_pt, resumo=excluded.resumo,
                 gancho=excluded.gancho, grafico=excluded.grafico, doi=excluded.doi,
                 fonte=excluded.fonte, url=excluded.url, criado_em=excluded.criado_em""",
            (d, tema, s, conteudo.get("titulo_pt", "") or art.get("titulo", ""),
             conteudo.get("resumo", ""), conteudo.get("gancho", ""), grafico_txt,
             art.get("doi", ""), art.get("fonte", ""), art.get("url", ""),
             datetime.now().isoformat()),
        )


def listar_temas():
    """Temas COM digest, ordenados como no temas_config, com contagem + rotulo/emoji/cor."""
    with _conn() as c:
        rows = c.execute("SELECT tema_slug, COUNT(*) n FROM digests GROUP BY tema_slug").fetchall()
    counts = {r["tema_slug"]: r["n"] for r in rows}
    stored_tema = {}
    with _conn() as c:
        for r in c.execute("SELECT tema_slug, tema FROM digests"):
            stored_tema.setdefault(r["tema_slug"], r["tema"])
    out = []
    seen = set()
    for nome, meta in _temas_cfg().items():
        s = slug(nome)
        if s in counts:
            out.append({"slug": s, "tema": nome, "rotulo": meta.get("rotulo", nome),
                        "emoji": meta.get("emoji", ""), "cor": meta.get("cor", "#14332a"),
                        "total": counts[s]})
            seen.add(s)
    # temas que existem no banco mas não no config (renomeados/removidos)
    for s, n in counts.items():
        if s not in seen:
            nome = stored_tema.get(s, s)
            out.append({"slug": s, "tema": nome, "rotulo": nome, "emoji": "", "cor": "#14332a", "total": n})
    return out


def _meta_por_slug(s):
    for nome, meta in _temas_cfg().items():
        if slug(nome) == s:
            return {"slug": s, "tema": nome, "rotulo": meta.get("rotulo", nome),
                    "emoji": meta.get("emoji", ""), "cor": meta.get("cor", "#14332a")}
    return {"slug": s, "tema": s, "rotulo": s, "emoji": "", "cor": "#14332a"}


def meta_tema(s):
    """Metadados do tema pelo slug (para o cabeçalho da lista/digest)."""
    return _meta_por_slug(s)


def listar_por_tema(s):
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM digests WHERE tema_slug=? ORDER BY data DESC, criado_em DESC", (s,)
        ).fetchall()
    return [dict(r) for r in rows]


def obter(s, data):
    with _conn() as c:
        r = c.execute("SELECT * FROM digests WHERE tema_slug=? AND data=?", (s, data)).fetchone()
    return dict(r) if r else None
