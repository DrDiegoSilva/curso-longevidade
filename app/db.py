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


def _conn():
    c = sqlite3.connect(config.artigos_db())
    c.row_factory = sqlite3.Row
    return c


def init():
    os.makedirs(os.path.dirname(config.artigos_db()) or ".", exist_ok=True)
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS digests (
                id INTEGER PRIMARY KEY,
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
                UNIQUE(data, tema_slug)
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
                criado_em TEXT, cancelado_em TEXT, cancel_motivo TEXT, oferta_retencao_em TEXT
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
            """
        )
    _seed_cupons()


def _seed_cupons():
    from datetime import datetime
    codigos = config.cupons_seed()
    if not codigos:
        return
    with _conn() as c:
        for cod in codigos:
            c.execute("INSERT OR IGNORE INTO cupons (codigo,ativo,descricao,criado_em) VALUES (?,1,'seed',?)",
                      (cod, datetime.now().isoformat()))


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
        cur = c.execute("INSERT OR IGNORE INTO webhook_events (payment_id,event,processed_em) VALUES (?,?,?)",
                        (payment_id or "", event or "", datetime.now().isoformat()))
        return cur.rowcount > 0


def cupom_valido(codigo):
    if not codigo:
        return False
    with _conn() as c:
        r = c.execute("SELECT ativo FROM cupons WHERE codigo=?", ((codigo or "").strip().upper(),)).fetchone()
    return bool(r and r["ativo"])


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
            "SELECT * FROM digests WHERE tema_slug=? ORDER BY data DESC, id DESC", (s,)
        ).fetchall()
    return [dict(r) for r in rows]


def obter(s, data):
    with _conn() as c:
        r = c.execute("SELECT * FROM digests WHERE tema_slug=? AND data=?", (s, data)).fetchone()
    return dict(r) if r else None
