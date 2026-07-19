"""PDF bonito (visual C): capa temática + resumo + gráfico do achado + gancho +
marca d'água por assinante. HTML+CSS puro (testável) renderizado por Chromium.
"""
import os
import re
import subprocess
import tempfile
import html as _html

_MOTIF = (
    '<svg viewBox="0 0 760 150" preserveAspectRatio="xMidYMid slice">'
    '<defs><linearGradient id="w" x1="0" x2="1">'
    '<stop offset="0" stop-color="#c9a227" stop-opacity="0"/>'
    '<stop offset=".5" stop-color="#c9a227" stop-opacity=".55"/>'
    '<stop offset="1" stop-color="#c9a227" stop-opacity="0"/></linearGradient></defs>'
    '<path d="M0,104 C90,104 110,60 175,60 C240,60 250,120 320,120 C400,120 405,44 470,44 '
    'C540,44 545,96 620,96 C690,96 700,66 760,66" fill="none" stroke="url(#w)" stroke-width="2.5"/>'
    '<path d="M0,118 C90,118 120,88 190,88 C260,88 270,128 340,128 C420,128 430,72 500,72 '
    'C560,72 580,110 660,110 C710,110 730,92 760,92" fill="none" stroke="#ffffff" stroke-opacity=".28" stroke-width="1.5"/>'
    '<g fill="#c9a227" fill-opacity=".85"><circle cx="175" cy="60" r="3.2"/><circle cx="470" cy="44" r="3.2"/>'
    '<circle cx="620" cy="96" r="2.6"/><circle cx="320" cy="120" r="2.4"/></g></svg>'
)


def _resumo_html(resumo):
    out = []
    for linha in (resumo or "").split("\n"):
        linha = linha.strip()
        if not linha:
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
    titulo = esc(grafico.get("titulo", ""))
    return f'<div class="chart"><div class="ct">{titulo}</div>{"".join(linhas)}</div>'


def _gancho_html(gancho):
    if not gancho:
        return ""
    corpo = _html.escape(gancho.strip()).replace("\n", "<br>")
    return (f'<div class="social"><div class="lab">📣 Para suas redes</div>'
            f'<div class="post">{corpo}</div></div>')


def montar_html(artigo, conteudo, nome_medico, tema_meta):
    esc = _html.escape
    cor = tema_meta.get("cor", "#14332a")
    rotulo = tema_meta.get("rotulo", artigo.get("tema", ""))
    resumo_html = _resumo_html(conteudo.get("resumo", ""))
    grafico_html = _grafico_html(conteudo.get("grafico"))
    gancho_html = _gancho_html(conteudo.get("gancho", ""))
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<style>
  @page {{ size: A4; margin: 0; }}
  *{{box-sizing:border-box}}
  body {{ font-family: Georgia, "Times New Roman", serif; color:#1c2b27; margin:0; line-height:1.5; }}
  .cover {{ position:relative; height:150px; background:linear-gradient(115deg,#0e211a,{cor} 62%,#1c4436); }}
  .cover svg {{ position:absolute; inset:0; width:100%; height:100%; }}
  .brand {{ position:absolute; left:26px; top:22px; z-index:2; }}
  .brand .mark {{ font-family:system-ui,sans-serif; font-size:11px; letter-spacing:.2em; text-transform:uppercase; color:#e9e2c9; font-weight:600; }}
  .brand .sig {{ color:#fbf7ea; font-size:20px; margin-top:3px; }}
  .tag {{ position:absolute; right:26px; top:22px; z-index:2; background:#b8860b; color:#1a1300; font-family:system-ui,sans-serif;
          font-size:11px; letter-spacing:.12em; text-transform:uppercase; font-weight:700; padding:6px 12px; border-radius:100px; }}
  .body {{ padding:26px 40px 30px; }}
  .title {{ font-size:24px; line-height:1.18; color:{cor}; margin:2px 0 10px; }}
  .meta {{ font-family:ui-monospace,Menlo,monospace; font-size:12px; color:#6f7d78; border-bottom:2px solid #b8860b; padding-bottom:10px; margin-bottom:16px; }}
  .corpo p {{ margin:.45em 0; font-size:14.5px; color:#2b3a35; }}
  .corpo strong {{ color:{cor}; }}
  .chart {{ margin:18px 0; background:#f4f1e7; border:1px solid #e7e2d6; border-radius:8px; padding:14px 16px; }}
  .chart .ct {{ font-family:system-ui,sans-serif; font-size:12px; letter-spacing:.08em; text-transform:uppercase; color:#6f7d78; margin-bottom:10px; font-weight:600; }}
  .bar-row {{ display:flex; align-items:center; gap:12px; margin:8px 0; }}
  .bar-lab {{ width:120px; font-family:system-ui,sans-serif; font-size:13px; color:#2b3a35; flex:none; }}
  .bar-track {{ flex:1; background:#e7e2d3; border-radius:100px; height:20px; overflow:hidden; }}
  .bar-fill {{ height:100%; border-radius:100px; }}
  .bar-val {{ font-family:ui-monospace,monospace; font-size:13px; font-weight:700; width:64px; text-align:right; flex:none; }}
  .social {{ margin:20px 0 6px; border:1.5px solid #b8860b; border-radius:10px; padding:15px 17px; background:linear-gradient(180deg,#fff9e9,#fbf3d9); }}
  .social .lab {{ font-family:system-ui,sans-serif; font-size:12px; letter-spacing:.08em; text-transform:uppercase; color:#8a6a06; font-weight:700; margin-bottom:7px; }}
  .social .post {{ font-size:14.5px; color:#3a2f10; font-style:italic; }}
  .foot {{ margin-top:22px; border-top:1px solid #e7e2d6; padding-top:11px; display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap;
           font-family:system-ui,sans-serif; font-size:11px; color:#6f7d78; }}
  .foot .wm {{ font-style:italic; color:#9aa8a0; }}
</style></head><body>
  <div class="cover">{_MOTIF}
    <div class="brand"><div class="mark">Atualiza&ccedil;&atilde;o cient&iacute;fica</div><div class="sig">Dr. Diego Silva</div></div>
    <div class="tag">{esc(rotulo)}</div>
  </div>
  <div class="body">
    <h1 class="title">{esc(artigo.get('titulo',''))}</h1>
    <div class="meta">{esc(artigo.get('fonte',''))} &middot; {esc(artigo.get('data',''))} &middot; DOI {esc(artigo.get('doi','') or '—')}</div>
    <div class="corpo">{resumo_html}</div>
    {grafico_html}
    {gancho_html}
    <div class="foot">
      <span>Refer&ecirc;ncia: {esc(artigo.get('url',''))}</span>
      <span class="wm">Exclusivo &middot; {esc(nome_medico)}</span>
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
             f"--print-to-pdf={out_path}", "--no-pdf-header-footer", f"file://{src}"],
            check=True, timeout=90, capture_output=True)
    finally:
        os.unlink(src)
    return out_path
