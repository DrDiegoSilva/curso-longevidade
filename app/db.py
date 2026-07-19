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
            """
        )


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
