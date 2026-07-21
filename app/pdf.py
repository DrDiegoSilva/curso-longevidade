"""PDF bonito (visual C): capa ilustrada + resumo + gráfico do achado + gancho +
marca d'água por assinante. HTML+CSS puro (testável) renderizado por Chromium.
Título em português (conteudo['titulo_pt']).
"""
import os
import re
import subprocess
import tempfile
import html as _html

# Capa ilustrada: rede molecular (nós + conexões) + arco dourado sobre o gradiente.
_MOTIF = (
    '<svg viewBox="0 0 760 185" preserveAspectRatio="xMidYMid slice">'
    '<defs>'
    '<radialGradient id="glow" cx="78%" cy="30%" r="60%">'
    '<stop offset="0" stop-color="#ffffff" stop-opacity=".16"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/></radialGradient>'
    '<linearGradient id="arc" x1="0" x2="1"><stop offset="0" stop-color="#c9a227" stop-opacity="0"/>'
    '<stop offset=".5" stop-color="#e7c766" stop-opacity=".7"/><stop offset="1" stop-color="#c9a227" stop-opacity="0"/></linearGradient>'
    '</defs>'
    '<rect width="760" height="185" fill="url(#glow)"/>'
    '<path d="M-10,150 C160,120 250,60 400,66 C560,72 620,120 780,96" fill="none" stroke="url(#arc)" stroke-width="3"/>'
    '<g stroke="#dfe8e2" stroke-opacity=".28" stroke-width="1.1">'
    '<line x1="120" y1="52" x2="210" y2="96"/><line x1="210" y1="96" x2="150" y2="140"/>'
    '<line x1="210" y1="96" x2="330" y2="70"/><line x1="330" y1="70" x2="430" y2="118"/>'
    '<line x1="430" y1="118" x2="540" y2="70"/><line x1="540" y1="70" x2="640" y2="112"/>'
    '<line x1="330" y1="70" x2="300" y2="150"/><line x1="540" y1="70" x2="600" y2="44"/>'
    '</g>'
    '<g fill="#f2ead0">'
    '<circle cx="120" cy="52" r="4"/><circle cx="210" cy="96" r="5.5"/><circle cx="150" cy="140" r="3.5"/>'
    '<circle cx="330" cy="70" r="6"/><circle cx="430" cy="118" r="5"/><circle cx="540" cy="70" r="6.5"/>'
    '<circle cx="640" cy="112" r="4"/><circle cx="300" cy="150" r="3"/><circle cx="600" cy="44" r="4.5"/></g>'
    '<g fill="#c9a227">'
    '<circle cx="210" cy="96" r="2.4"/><circle cx="330" cy="70" r="2.6"/><circle cx="540" cy="70" r="2.8"/></g>'
    '</svg>'
)


_SEP_RE = re.compile(r"^[\-_*—–=·•\s]{3,}$")               # linha só de traços/separadores
_HEADER_RE = re.compile(r"\s*(\S{1,3}\s+)?\*([^*]+)\*\s*")   # linha TODA em negrito (emoji opcional) = título de seção


def _resumo_html(resumo):
    """Converte o resumo (estilo WhatsApp: *negrito*, --- separadores, emojis de
    seção) em HTML. Título de seção não quebra do texto seguinte (break-after:avoid);
    linhas só de '---' viram uma divisória sutil (não ficam soltas)."""
    out = []
    for linha in (resumo or "").split("\n"):
        linha = linha.strip()
        if not linha:
            continue
        if _SEP_RE.fullmatch(linha):
            out.append('<hr class="rule">')
            continue
        if _HEADER_RE.fullmatch(linha):                     # ex.: "💡 *Em resumo*"
            inner = _html.escape(re.sub(r"\*([^*]+)\*", r"\1", linha))
            out.append(f'<p class="h">{inner}</p>')
            continue
        e = _html.escape(linha)
        e = re.sub(r"\*([^*]+)\*", r"<strong>\1</strong>", e)
        out.append(f"<p>{e}</p>")
    return "".join(out)


def _grafico_html(grafico):
    if not grafico or not grafico.get("barras"):
        return ""
    esc = _html.escape
    barras = grafico["barras"]
    mx = max((abs(float(b["valor"])) for b in barras), default=0) or 1
    linhas = []
    for i, b in enumerate(barras):
        val = float(b["valor"])
        w = max(6, round(abs(val) / mx * 100))
        fill = ("linear-gradient(90deg,#14332a,#2f7a5f)" if i == 0 else "#b9c2ba")
        cor_val = "#14332a" if i == 0 else "#6f7d78"
        txt = f"{val:g}{esc(grafico.get('unidade',''))}"
        linhas.append(
            f'<div class="bar-row"><div class="bar-lab">{esc(str(b["rotulo"]))}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{w}%;background:{fill}"></div></div>'
            f'<div class="bar-val" style="color:{cor_val}">{txt}</div></div>')
    return f'<div class="chart"><div class="ct">{esc(grafico.get("titulo",""))}</div>{"".join(linhas)}</div>'


def _gancho_html(gancho):
    if not gancho:
        return ""
    corpo = _html.escape(gancho.strip()).replace("\n", "<br>")
    return (f'<div class="social"><div class="lab">📣 Para suas redes</div>'
            f'<div class="post">{corpo}</div></div>')


def _rodape_direitos():
    """Nota de direitos fixa no rodapé — o PDF é único (mesmo arquivo p/ todos os
    assinantes), com a marca do curso no lugar do nome individual."""
    from datetime import datetime
    return (f"© {datetime.now().year} Atualização Científica · Dr. Diego Silva · "
            f"CRM-PR 54310 — conteúdo exclusivo para assinantes")


def montar_html(artigo, conteudo, tema_meta):
    esc = _html.escape
    cor = tema_meta.get("cor", "#14332a")
    rotulo = tema_meta.get("rotulo", artigo.get("tema", ""))
    emoji = tema_meta.get("emoji", "")
    titulo = conteudo.get("titulo_pt") or artigo.get("titulo", "")
    resumo_html = _resumo_html(conteudo.get("resumo", ""))
    grafico_html = _grafico_html(conteudo.get("grafico"))
    gancho_html = _gancho_html(conteudo.get("gancho", ""))
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<style>
  @page {{ size: A4; margin: 0; }}
  *{{box-sizing:border-box}}
  body {{ font-family: Georgia, "Times New Roman", serif; color:#20302b; margin:0; font-size:20px; line-height:1.7; }}
  h1, h2 {{ break-after:avoid; }}
  .cover {{ position:relative; height:185px; background:linear-gradient(120deg,#0e211a,{cor} 60%,#20543f); }}
  .cover svg {{ position:absolute; inset:0; width:100%; height:100%; }}
  .brand {{ position:absolute; left:34px; top:28px; z-index:2; }}
  .brand .mark {{ font-family:system-ui,sans-serif; font-size:12px; letter-spacing:.22em; text-transform:uppercase; color:#ece4c6; font-weight:600; }}
  .brand .sig {{ color:#fbf7ea; font-size:26px; margin-top:5px; }}
  .brand .crm {{ font-family:system-ui,sans-serif; font-size:11px; letter-spacing:.1em; color:#cbd8cf; margin-top:3px; }}
  .tag {{ position:absolute; right:34px; top:28px; z-index:2; background:#c9a227; color:#1a1300; font-family:system-ui,sans-serif;
          font-size:12px; letter-spacing:.12em; text-transform:uppercase; font-weight:700; padding:7px 15px; border-radius:100px; }}
  .body {{ padding:34px 48px 40px; }}
  .title {{ font-size:34px; line-height:1.22; color:{cor}; margin:0 0 14px; }}
  .meta {{ font-family:ui-monospace,Menlo,monospace; font-size:15px; color:#6f7d78; border-bottom:2px solid #c9a227; padding-bottom:13px; margin-bottom:22px; }}
  .corpo p {{ margin:.75em 0; font-size:20px; color:#2b3a35; orphans:2; widows:2; }}
  .corpo strong {{ color:{cor}; }}
  .corpo .h {{ font-size:21px; font-weight:700; color:{cor}; margin:22px 0 4px; line-height:1.3; break-after:avoid; break-inside:avoid; }}
  .corpo hr.rule {{ border:none; border-top:1px solid #e2ddcb; margin:16px 0 14px; break-after:avoid; }}
  .chart {{ margin:26px 0; background:#f4f1e7; border:1px solid #e7e2d6; border-radius:10px; padding:20px 22px; break-inside:avoid; }}
  .chart .ct {{ font-family:system-ui,sans-serif; font-size:14px; letter-spacing:.08em; text-transform:uppercase; color:#6f7d78; margin-bottom:14px; font-weight:600; }}
  .bar-row {{ display:flex; align-items:center; gap:14px; margin:12px 0; }}
  .bar-lab {{ width:140px; font-family:system-ui,sans-serif; font-size:17px; color:#2b3a35; flex:none; }}
  .bar-track {{ flex:1; background:#e7e2d3; border-radius:100px; height:26px; overflow:hidden; }}
  .bar-fill {{ height:100%; border-radius:100px; }}
  .bar-val {{ font-family:ui-monospace,monospace; font-size:17px; font-weight:700; width:78px; text-align:right; flex:none; }}
  .social {{ margin:28px 0 8px; border:2px solid #c9a227; border-radius:12px; padding:20px 22px; background:linear-gradient(180deg,#fff9e9,#fbf3d9); break-inside:avoid; }}
  .social .lab {{ font-family:system-ui,sans-serif; font-size:14.5px; letter-spacing:.08em; text-transform:uppercase; color:#8a6a06; font-weight:700; margin-bottom:9px; }}
  .social .post {{ font-size:20px; color:#3a2f10; font-style:italic; line-height:1.6; }}
  .foot {{ margin-top:30px; border-top:1px solid #e7e2d6; padding-top:14px; display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap;
           break-inside:avoid; font-family:system-ui,sans-serif; font-size:13px; color:#6f7d78; }}
  .foot .wm {{ font-style:italic; color:#9aa8a0; }}
</style></head><body>
  <div class="cover">{_MOTIF}
    <div class="brand"><div class="mark">Atualiza&ccedil;&atilde;o cient&iacute;fica</div><div class="sig">Dr. Diego Silva</div><div class="crm">CRM-PR 54310</div></div>
    <div class="tag">{esc(emoji)} {esc(rotulo)}</div>
  </div>
  <div class="body">
    <h1 class="title">{esc(titulo)}</h1>
    <div class="meta">{esc(artigo.get('fonte',''))} &middot; {esc(artigo.get('data',''))} &middot; DOI {esc(artigo.get('doi','') or '—')}</div>
    <div class="corpo">{resumo_html}</div>
    {grafico_html}
    {gancho_html}
    <div class="foot">
      <span>Refer&ecirc;ncia: {esc(artigo.get('url',''))}</span>
      <span class="wm">{_rodape_direitos()}</span>
    </div>
  </div>
</body></html>"""


def _chromium_bin():
    for b in ("chromium", "chromium-browser", "google-chrome"):
        if subprocess.run(["which", b], capture_output=True).returncode == 0:
            return b
    raise RuntimeError("Chromium não encontrado na imagem")


def gerar_pdf(html, out_path):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        src = f.name
    try:
        subprocess.run(
            [_chromium_bin(), "--headless", "--no-sandbox", "--disable-gpu",
             "--disable-dev-shm-usage", "--disable-software-rasterizer",
             f"--print-to-pdf={out_path}", "--no-pdf-header-footer", f"file://{src}"],
            check=True, timeout=90, capture_output=True)
    finally:
        os.unlink(src)
    # Chromium às vezes crasha e ainda retorna 0 (sem gerar o arquivo). Confere de verdade:
    if not (os.path.exists(out_path) and os.path.getsize(out_path) > 1000):
        raise RuntimeError("Chromium não gerou o PDF (crash silencioso ou saída vazia)")
    return out_path
