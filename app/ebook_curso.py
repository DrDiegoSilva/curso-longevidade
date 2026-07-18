"""
ebook_curso.py — Compila as aulas do curso de Longevidade num EBOOK (HTML único, autossuficiente).
Custo ZERO: só junta os arquivos longevidade_XX_*.md já gerados. Regenerável a qualquer momento;
o resumo_diario chama gerar() após cada módulo novo, então o ebook cresce sozinho.

Uso:
  python ebook_curso.py                 # gera o HTML standalone (abre no navegador / OneDrive)
  python ebook_curso.py --artifact P    # grava versão body-only (p/ publicar como Artifact) em P
"""
import sys, io, os, re, html
from datetime import datetime
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import config  # caminhos portáveis (env no VPS, arquivos no Windows)
DIR = os.path.dirname(os.path.abspath(__file__))
BASE = config.BASE
CURRICULO = os.path.join(BASE, "longevidade_CURSO_curriculo.md")
OUT = os.path.join(DIR, "Curso_Longevidade_DrDiego.html")
MESES = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
         "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]

def data_br(iso):
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
        return f"{d.day:02d}/{d.month:02d}/{d.year}"
    except Exception:
        return iso or ""

# ─── Markdown → HTML (subconjunto usado nas aulas) ───────────────
def _inline(t):
    t = html.escape(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)   # **negrito**
    t = re.sub(r"\*(.+?)\*", r"<strong>\1</strong>", t)        # *negrito* (estilo WhatsApp)
    return t

def md_to_html(md):
    out, para, in_ul = [], [], False
    def flush():
        if para:
            out.append("<p>" + _inline(" ".join(para)) + "</p>"); para.clear()
    def close_ul():
        nonlocal in_ul
        if in_ul:
            out.append("</ul>"); in_ul = False
    for raw in md.split("\n"):
        s = raw.strip()
        if not s:
            flush(); close_ul(); continue
        if re.match(r"^-{3,}$", s) or re.match(r"^—{3,}$", s):
            flush(); close_ul(); out.append("<hr>"); continue
        h = re.match(r"^(#{1,4})\s+(.*)$", s)
        if h:
            flush(); close_ul()
            lvl = min(len(h.group(1)) + 1, 4)   # # vira h2 (h1 é o título do capítulo)
            out.append(f"<h{lvl}>{_inline(h.group(2))}</h{lvl}>"); continue
        b = re.match(r"^(?:[-•]|▪️?)\s+(.*)$", s)
        if b:
            flush()
            if not in_ul:
                out.append("<ul>"); in_ul = True
            out.append("<li>" + _inline(b.group(1)) + "</li>"); continue
        para.append(s)
    flush(); close_ul()
    return "\n".join(out)

# ─── Currículo → estrutura (blocos + módulos) ────────────────────
def carregar_estrutura():
    txt = open(CURRICULO, encoding="utf-8").read()
    blocos, atual = [], None
    mod_re = re.compile(r"^- (✅|⬜)\s+(\d+)\.\s+(.*)$")
    for line in txt.split("\n"):
        bh = re.match(r"^##\s+(Bloco\s+\d+)\s*[—-]\s*(.+)$", line.strip())
        if bh:
            atual = {"id": bh.group(1), "nome": bh.group(2).strip(), "mods": []}
            blocos.append(atual); continue
        m = mod_re.match(line.strip())
        if m and atual is not None:
            resto = m.group(3)
            fm = re.search(r"concluído\s+(\d{4}-\d\d-\d\d)\s*→\s*(.+?)\)_", resto)
            titulo = re.sub(r"\s*_\(concluído.*$", "", resto)
            scope = titulo.split(" — ", 1)[1] if " — " in titulo else ""
            titulo = re.sub(r"\*\*", "", titulo.split(" — ")[0]).strip()
            atual["mods"].append({
                "n": int(m.group(2)), "feito": m.group(1) == "✅",
                "titulo": titulo, "escopo": re.sub(r"\*\*", "", scope).strip(),
                "data": fm.group(1) if fm else None,
                "arq": fm.group(2).strip() if fm else None,
            })
    return blocos

def corpo_modulo(arq):
    """Lê o .md do módulo e remove o cabeçalho redundante (# Título, _data_, ---)."""
    p = os.path.join(BASE, arq)
    if not os.path.exists(p):
        return ""
    linhas = open(p, encoding="utf-8").read().split("\n")
    i = 0
    while i < len(linhas):
        s = linhas[i].strip()
        if s == "" or re.match(r"^#\s", s) or re.match(r"^_.*_$", s) or re.match(r"^-{3,}$", s):
            i += 1
        else:
            break
    return md_to_html("\n".join(linhas[i:]))

# ─── CSS (paleta botânica-clínica; claro + escuro) ───────────────
CSS = """
:root{
  --paper:#f4f6f2; --ink:#1a201c; --soft:#586159; --faint:#8a938a; --line:#dde3db;
  --accent:#1f6b52; --accent-2:#2b8a68; --wash:#e7efe9; --gold:#96742a; --danger:#a1382a;
  --serif:'Iowan Old Style','Palatino Linotype',Palatino,'Book Antiqua',Georgia,serif;
  --sans:system-ui,'Segoe UI',Roboto,sans-serif;
  --mono:ui-monospace,'Cascadia Code',Consolas,'Courier New',monospace;
}
@media (prefers-color-scheme:dark){:root{
  --paper:#141712;--ink:#e7ebe3;--soft:#9aa399;--faint:#69726a;--line:#282d26;
  --accent:#63bd97;--accent-2:#79caa6;--wash:#1a241d;--gold:#c6a256;--danger:#d6796a;
}}
:root[data-theme="light"]{
  --paper:#f4f6f2;--ink:#1a201c;--soft:#586159;--faint:#8a938a;--line:#dde3db;
  --accent:#1f6b52;--accent-2:#2b8a68;--wash:#e7efe9;--gold:#96742a;--danger:#a1382a;
}
:root[data-theme="dark"]{
  --paper:#141712;--ink:#e7ebe3;--soft:#9aa399;--faint:#69726a;--line:#282d26;
  --accent:#63bd97;--accent-2:#79caa6;--wash:#1a241d;--gold:#c6a256;--danger:#d6796a;
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--serif);
  font-size:1.06rem;line-height:1.72;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
.wrap{max-width:43rem;margin:0 auto;padding:0 1.5rem 6rem}
.eyebrow{font-family:var(--mono);font-size:.72rem;letter-spacing:.22em;text-transform:uppercase;color:var(--accent);font-weight:600}
a{color:var(--accent);text-decoration:none}
strong{font-weight:650;color:var(--ink)}

/* Capa */
.cover{min-height:100vh;display:flex;flex-direction:column;justify-content:center;
  max-width:43rem;margin:0 auto;padding:2rem 1.5rem;border-bottom:1px solid var(--line)}
.cover .kick{font-family:var(--mono);font-size:.78rem;letter-spacing:.26em;text-transform:uppercase;color:var(--accent);margin-bottom:1.4rem}
.cover h1{font-size:clamp(2.4rem,7vw,3.6rem);line-height:1.05;margin:0;font-weight:700;letter-spacing:-.01em;text-wrap:balance}
.cover h1 em{font-style:normal;color:var(--accent)}
.cover .sub{font-size:1.15rem;color:var(--soft);margin:1.1rem 0 0;max-width:32rem}
.rule{height:2px;width:3.2rem;background:var(--accent);border:0;margin:2rem 0}
.cover .meta{font-family:var(--mono);font-size:.8rem;color:var(--soft);line-height:1.9;letter-spacing:.02em}
.cover .meta b{color:var(--ink);font-weight:600}
.prog{margin-top:1.6rem;max-width:22rem}
.prog .bar{height:6px;background:var(--wash);border-radius:99px;overflow:hidden}
.prog .fill{height:100%;background:var(--accent);border-radius:99px}
.prog .lab{font-family:var(--mono);font-size:.74rem;color:var(--soft);margin-top:.5rem;letter-spacing:.04em}

/* Sumário */
.toc{padding-top:3.5rem}
.toc h2{font-size:1.5rem;margin:0 0 1.4rem}
.toc .blk{font-family:var(--mono);font-size:.72rem;letter-spacing:.18em;text-transform:uppercase;
  color:var(--accent);margin:1.8rem 0 .5rem;padding-bottom:.4rem;border-bottom:1px solid var(--line)}
.toc ol{list-style:none;margin:0;padding:0}
.toc li{display:grid;grid-template-columns:2.2rem 1fr auto;gap:.7rem;align-items:baseline;padding:.32rem 0}
.toc .nn{font-family:var(--mono);font-size:.85rem;color:var(--faint);font-variant-numeric:tabular-nums}
.toc .tt{color:var(--ink)}
.toc li.pend .tt{color:var(--faint)}
.toc .st{font-family:var(--mono);font-size:.7rem;color:var(--soft);letter-spacing:.03em;white-space:nowrap}
.toc li.pend .st{color:var(--faint)}

/* Divisor de bloco */
.bloco{margin:5rem 0 0;padding-top:2.5rem;border-top:2px solid var(--accent)}
.bloco .n{font-family:var(--mono);font-size:.78rem;letter-spacing:.22em;text-transform:uppercase;color:var(--accent)}
.bloco h2{font-size:2rem;margin:.4rem 0 0;line-height:1.1;text-wrap:balance}

/* Capítulo / módulo */
.cap{margin:3.2rem 0 0;padding-top:2.4rem;border-top:1px solid var(--line)}
.cap .hd{display:flex;align-items:baseline;gap:1rem;margin-bottom:.2rem}
.cap .num{font-family:var(--mono);font-size:2.6rem;font-weight:600;color:var(--wash);line-height:1;
  -webkit-text-stroke:1px var(--accent);color:transparent}
.cap h1{font-size:1.9rem;line-height:1.12;margin:0;font-weight:700;text-wrap:balance}
.cap .info{font-family:var(--mono);font-size:.74rem;color:var(--soft);letter-spacing:.03em;margin:.7rem 0 1.4rem;
  padding:.5rem .8rem;background:var(--wash);border-radius:6px;display:inline-block}
.cap h2{font-size:1.28rem;color:var(--accent);margin:1.9rem 0 .5rem;font-weight:700;line-height:1.25}
.cap h3{font-size:1.06rem;margin:1.3rem 0 .4rem;font-weight:700;color:var(--ink)}
.cap h4{font-size:.96rem;margin:1.1rem 0 .3rem;font-weight:700;color:var(--soft)}
.cap p{margin:.7rem 0}
.cap ul{margin:.6rem 0;padding-left:1.2rem}
.cap li{margin:.35rem 0}
.cap li::marker{color:var(--accent)}
.cap hr{border:0;border-top:1px solid var(--line);margin:1.6rem 0}

/* Rodapé */
.foot{margin-top:5rem;padding-top:1.5rem;border-top:1px solid var(--line);
  font-family:var(--mono);font-size:.74rem;color:var(--faint);line-height:1.8}

/* Impressão → PDF limpo */
@media print{
  :root{--paper:#fff;--ink:#111;--soft:#444;--wash:#eef3ef;--line:#ccc}
  body{font-size:11pt}
  .cover{min-height:auto;page-break-after:always;border:0}
  .bloco,.cap{page-break-before:page;border-top:0}
  .toc{page-break-after:always}
  a{color:inherit}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""

# ─── Montagem ────────────────────────────────────────────────────
def build(standalone=True):
    blocos = carregar_estrutura()
    mods = [m for b in blocos for m in b["mods"]]
    total = len(mods)
    feitos = [m for m in mods if m["feito"]]
    nfeitos = len(feitos)
    pct = round(100 * nfeitos / total) if total else 0
    hoje = datetime.now()
    edicao = f"{hoje.day} de {MESES[hoje.month]} de {hoje.year}"

    # Capa
    P = []
    P.append('<div class="cover">')
    P.append('<div class="kick">Curso destilado · medicina para médico</div>')
    P.append('<h1>Longevidade &amp;<br><em>Medicina de Precisão</em></h1>')
    P.append('<p class="sub">Aulas destiladas de literatura consolidada — mecanismo, evidência graduada (A/B/C), doses, segurança e conduta. Compilado para o Dr. Diego Silva.</p>')
    P.append('<hr class="rule">')
    P.append(f'<div class="prog"><div class="bar"><div class="fill" style="width:{pct}%"></div></div>'
             f'<div class="lab">{nfeitos} de {total} módulos concluídos · {pct}%</div></div>')
    P.append(f'<div class="meta" style="margin-top:1.6rem">Edição atualizada em <b>{edicao}</b><br>'
             f'Fonte: destilados do acervo + Europe PMC · entrega diária via WhatsApp</div>')
    P.append('</div>')

    # Corpo com wrap
    P.append('<div class="wrap">')

    # Sumário
    P.append('<nav class="toc"><h2>Sumário</h2>')
    for b in blocos:
        if not b["mods"]:
            continue
        P.append(f'<div class="blk">{html.escape(b["id"])} — {html.escape(b["nome"])}</div><ol>')
        for m in b["mods"]:
            cls = "" if m["feito"] else " pend"
            nn = f'{m["n"]:02d}'
            tt = html.escape(m["titulo"])
            if m["feito"]:
                st = f'concluído {data_br(m["data"])}'
                tt = f'<a href="#mod-{nn}">{tt}</a>'
            else:
                st = "em breve"
            P.append(f'<li class="{cls.strip()}"><span class="nn">{nn}</span>'
                     f'<span class="tt">{tt}</span><span class="st">{st}</span></li>')
        P.append('</ol>')
    P.append('</nav>')

    # Blocos + capítulos
    for b in blocos:
        done = [m for m in b["mods"] if m["feito"]]
        if not done:
            continue
        P.append(f'<section class="bloco"><div class="n">{html.escape(b["id"])}</div>'
                 f'<h2>{html.escape(b["nome"])}</h2></section>')
        for m in done:
            nn = f'{m["n"]:02d}'
            corpo = corpo_modulo(m["arq"])
            info = f'Módulo {nn} · concluído em {data_br(m["data"])}'
            if m["escopo"]:
                info += f' · {html.escape(m["escopo"])}'
            P.append(f'<article class="cap" id="mod-{nn}"><div class="hd">'
                     f'<span class="num">{nn}</span><h1>{html.escape(m["titulo"])}</h1></div>'
                     f'<div class="info">{info}</div>{corpo}</article>')

    P.append(f'<div class="foot">Curso de Longevidade &amp; Medicina de Precisão · Dr. Diego Silva<br>'
             f'Gerado automaticamente a partir das aulas diárias · {edicao}<br>'
             f'Uso pessoal/educacional — não substitui julgamento clínico individualizado.</div>')
    P.append('</div>')  # /wrap

    body = f'<style>{CSS}</style>\n' + "\n".join(P)
    if not standalone:
        return '<title>Curso de Longevidade — Dr. Diego</title>\n' + body
    return ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Curso de Longevidade — Dr. Diego</title></head><body>'
            + body + '</body></html>')

def gerar():
    """Grava o ebook standalone e devolve o caminho. Chamado pelo resumo_diario após cada módulo."""
    htmlstr = build(standalone=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(htmlstr)
    return OUT

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", metavar="PATH", help="grava versão body-only p/ publicar como Artifact")
    args = ap.parse_args()
    if args.artifact:
        with open(args.artifact, "w", encoding="utf-8") as f:
            f.write(build(standalone=False))
        print("[artifact] gravado em", args.artifact)
    caminho = gerar()
    blocos = carregar_estrutura()
    nf = sum(1 for b in blocos for m in b["mods"] if m["feito"])
    print(f"[ebook] {nf} módulos compilados -> {caminho}")

if __name__ == "__main__":
    main()
