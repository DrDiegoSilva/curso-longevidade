"""PDF bonito: HTML+CSS (puro, testável) renderizado por Chromium headless."""
import os
import subprocess
import tempfile
import html as _html


def montar_html(artigo, resumo, nome_medico):
    esc = _html.escape
    corpo = "".join(f"<p>{esc(l)}</p>" for l in (resumo or "").split("\n") if l.strip())
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<style>
  @page {{ size: A4; margin: 22mm 18mm; }}
  body {{ font-family: Georgia, serif; color:#1a2b28; line-height:1.5; }}
  .marca {{ color:#0f4c3a; font-size:12px; letter-spacing:.12em; text-transform:uppercase; }}
  h1 {{ font-size:20px; color:#0f4c3a; margin:.2em 0; }}
  .meta {{ color:#6b7a76; font-size:12px; border-bottom:2px solid #c9a227; padding-bottom:8px; }}
  .corpo p {{ margin:.5em 0; }}
  .rodape {{ margin-top:24px; font-size:10px; color:#6b7a76; border-top:1px solid #ddd; padding-top:8px; }}
  .agua {{ position:fixed; bottom:12mm; right:18mm; font-size:9px; color:#b8c4c0; }}
</style></head><body>
  <div class="marca">Dr. Diego Silva &middot; Atualiza&ccedil;&atilde;o cient&iacute;fica</div>
  <h1>{esc(artigo.get('titulo',''))}</h1>
  <div class="meta">{esc(artigo.get('fonte',''))} &middot; {esc(artigo.get('data',''))} &middot; DOI {esc(artigo.get('doi','') or '—')}</div>
  <div class="corpo">{corpo}</div>
  <div class="rodape">Refer&ecirc;ncia: <a href="{esc(artigo.get('url',''))}">{esc(artigo.get('url',''))}</a></div>
  <div class="agua">Exclusivo &middot; {esc(nome_medico)}</div>
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
