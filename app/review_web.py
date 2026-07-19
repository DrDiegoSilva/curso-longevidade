"""HTML das páginas de revisão e admin (montagem pura, testável)."""
import html as _html


def pagina_revisao(r):
    esc = _html.escape
    a = r.get("artigo", {})
    return f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<body style="font-family:system-ui;max-width:680px;margin:24px auto;padding:0 16px;color:#1a2b28">
<div style="color:#0f4c3a;font-weight:600">Resumo de {esc(r.get('data',''))}</div>
<h2>{esc(a.get('titulo',''))}</h2>
<div style="color:#6b7a76;font-size:14px">{esc(a.get('fonte',''))}</div>
<form method="post" action="/revisar/{esc(r.get('review_token',''))}">
  <textarea name="texto" rows="16" style="width:100%;font-size:15px">{esc(r.get('resumo',''))}</textarea>
  <p><a href="/pdf/{esc(r.get('data',''))}" target="_blank">📄 Ver PDF</a></p>
  <button name="acao" value="aprovar">✅ Aprovar</button>
  <button name="acao" value="editar">✏️ Salvar edição</button>
  <button name="acao" value="nao_enviar">🚫 Não enviar hoje</button>
</form></body>"""


def pagina_admin(assinantes):
    esc = _html.escape
    linhas = "".join(
        f"<li>{esc(s['nome'])} — {esc(s['whatsapp'])} "
        f'<form style="display:inline" method="post" action="/admin">'
        f'<input type="hidden" name="acao" value="remover">'
        f'<input type="hidden" name="id" value="{esc(s["id"])}">'
        f"<button>remover</button></form></li>"
        for s in assinantes
    )
    return f"""<!doctype html><meta charset="utf-8"><body style="font-family:system-ui;max-width:640px;margin:24px auto">
<h2>Assinantes ({len(assinantes)})</h2><ul>{linhas}</ul>
<form method="post" action="/admin">
  <input type="hidden" name="acao" value="adicionar">
  <input name="nome" placeholder="Nome"> <input name="whatsapp" placeholder="55DDDNUMERO">
  <button>adicionar</button>
</form></body>"""
