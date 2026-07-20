"""HTML das páginas de revisão e admin (montagem pura, testável)."""
import html as _html


def pagina_revisao(r, aviso="", audio_on=False):
    esc = _html.escape
    a = r.get("artigo", {})
    tok = esc(r.get("review_token", ""))
    banner = (f'<div style="background:#e7f5ee;border:1px solid #0f4c3a;color:#0f4c3a;'
              f'padding:10px 12px;border-radius:8px;margin:12px 0">{esc(aviso)}</div>') if aviso else ""
    dica = ('<p style="color:#6b7a76;font-size:13px;margin:4px 0 12px">'
            '🎧 Você recebeu o áudio no seu WhatsApp. Se editar o texto, clique em '
            '<b>Regerar áudio</b> pra ouvir a nova versão. O que você aprovar aqui é o que sai às 08h.'
            '</p>') if audio_on else ""
    btn_audio = ('  <button name="acao" value="regerar_audio" '
                 'style="background:#b8860b;color:#fff;border:0;padding:8px 12px;border-radius:6px">'
                 '🎧 Regerar áudio</button>\n') if audio_on else ""
    return f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<body style="font-family:system-ui;max-width:680px;margin:24px auto;padding:0 16px;color:#1a2b28">
<div style="color:#0f4c3a;font-weight:600">Resumo de {esc(r.get('data',''))}</div>
<h2>{esc(a.get('titulo',''))}</h2>
<div style="color:#6b7a76;font-size:14px">{esc(a.get('fonte',''))}</div>
{banner}
{dica}
<form method="post" action="/revisar/{tok}">
  <textarea name="texto" rows="16" style="width:100%;font-size:15px">{esc(r.get('resumo',''))}</textarea>
  <p><a href="/pdf/{esc(r.get('data',''))}" target="_blank">📄 Ver PDF</a></p>
  <button name="acao" value="aprovar">✅ Aprovar</button>
  <button name="acao" value="editar">✏️ Salvar edição</button>
{btn_audio}  <button name="acao" value="nao_enviar">🚫 Não enviar hoje</button>
</form></body>"""


def pagina_admin(assinantes, token=""):
    esc = _html.escape
    tk = esc(token)
    linhas = "".join(
        f"<li>{esc(s['nome'])} — {esc(s['whatsapp'])} "
        f'<form style="display:inline" method="post" action="/admin">'
        f'<input type="hidden" name="token" value="{tk}">'
        f'<input type="hidden" name="acao" value="remover">'
        f'<input type="hidden" name="id" value="{esc(s["id"])}">'
        f"<button>remover</button></form></li>"
        for s in assinantes
    )
    return f"""<!doctype html><meta charset="utf-8"><body style="font-family:system-ui;max-width:640px;margin:24px auto">
<h2>Assinantes ({len(assinantes)})</h2><ul>{linhas}</ul>
<form method="post" action="/admin">
  <input type="hidden" name="token" value="{tk}">
  <input type="hidden" name="acao" value="adicionar">
  <input name="nome" placeholder="Nome"> <input name="whatsapp" placeholder="55DDDNUMERO">
  <button>adicionar</button>
</form></body>"""
