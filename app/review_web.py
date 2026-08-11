"""HTML das páginas de revisão e admin (montagem pura, testável)."""
import html as _html


def _select_area(tema_atual, areas):
    """<select> da área do estudo — o que vira a capa do PDF, o badge do WhatsApp e a
    seção no portal.

    O tema atual entra como opção mesmo quando NÃO está na lista (upload manual cai em
    "Meus estudos", e estudo antigo pode estar vazio). Sem isso, abrir a tela e apertar
    Aprovar sem tocar em nada trocaria a área silenciosamente pro primeiro item.
    """
    esc = _html.escape
    opcoes = list(areas)
    if tema_atual not in opcoes:
        opcoes.insert(0, tema_atual)
    itens = "".join(
        f'<option value="{esc(o)}"{" selected" if o == tema_atual else ""}>'
        f'{esc(o) if o else "— sem área —"}</option>'
        for o in opcoes)
    return ('<p style="margin:12px 0"><label style="font-size:14px;color:#6b7a76">Área do estudo '
            '<select name="area" style="font-size:15px;padding:6px;margin-left:6px">'
            f'{itens}</select></label></p>')


def pagina_revisao(r, aviso="", audio_on=False, areas=()):
    esc = _html.escape
    a = r.get("artigo", {})
    tok = esc(r.get("review_token", ""))
    sel_area = _select_area(a.get("tema", ""), areas)
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
{sel_area}
  <textarea name="texto" rows="16" style="width:100%;font-size:15px">{esc(r.get('resumo',''))}</textarea>
  <p><a href="/pdf/{esc(r.get('data',''))}" target="_blank">📄 Ver PDF</a></p>
  <button name="acao" value="aprovar">✅ Aprovar</button>
  <button name="acao" value="editar">✏️ Salvar edição</button>
{btn_audio}  <button name="acao" value="nao_enviar">🚫 Não enviar hoje</button>
  <button name="acao" value="trocar">🔁 Trocar por outro estudo</button>
</form></body>"""


_FEITO = {
    "aprovar":    ("✅ Aprovado", "Sai às 08h para os assinantes."),
    "editar":     ("✏️ Edição salva", "É esta versão que sai às 08h."),
    "nao_enviar": ("🚫 Vetado", "Nada será enviado neste dia."),
}


def pagina_feito(acao, data, token):
    """Confirmação do que foi feito, COM saída.

    Antes isto era `<h3>Feito ✅ Pode fechar.</h3>`: não dizia qual das ações tinha
    acontecido e, pior, não tinha link nenhum — pra conferir o PDF da edição que acabou
    de salvar, o curador tinha que voltar no WhatsApp e reabrir o link. O PDF abre em
    aba nova de propósito: mandar a aba atual pro PDF é recriar o beco sem saída.
    """
    esc = _html.escape
    titulo, sub = _FEITO.get(acao, ("✅ Feito", "Pode fechar esta página."))
    d, tok = esc(data or ""), esc(token or "")
    # Vetado não ganha link de PDF: não faz sentido conferir a capa do que não vai sair.
    ver_pdf = (f'<p style="margin:18px 0 8px"><a href="/pdf/{d}" target="_blank" '
               f'style="color:#0f4c3a;font-weight:600">📄 Conferir o PDF</a></p>'
               if acao in ("aprovar", "editar") and d else "")
    voltar = (f'<p style="margin:0"><a href="/revisar/{tok}" style="color:#6b7a76">'
              f'← Voltar para a revisão</a></p>') if tok else ""
    return (f'<!doctype html><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<body style="font-family:system-ui;max-width:680px;margin:40px auto;'
            f'padding:0 16px;color:#1a2b28">'
            f'<h2 style="margin:0 0 4px">{titulo}</h2>'
            f'<p style="color:#6b7a76;margin:0">{sub}</p>'
            f'{ver_pdf}{voltar}</body>')


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


def pagina_trocar_estudo(alternativas, r, token):
    esc = _html.escape
    tok = esc(token)
    atual = esc((r.get("artigo") or {}).get("titulo", ""))
    if not alternativas:
        corpo = "<p>Sem outros estudos disponíveis para trocar agora.</p>"
    else:
        itens = "".join(
            f'<li style="margin:12px 0">'
            f'<form method="post" action="/revisar/{tok}" '
            f'style="display:flex;gap:10px;align-items:center;justify-content:space-between">'
            f'<span><b>{esc(a["titulo"])}</b><br>'
            f'<small style="color:#6b7a76">{esc(a["tema"])} · {esc(a["fonte"])} · '
            f'nota {esc(str(a["score"]))} · {esc(a["tipo"])}</small></span>'
            f'<input type="hidden" name="acao" value="trocar_confirmar">'
            f'<input type="hidden" name="tipo" value="{esc(a["tipo"])}">'
            f'<input type="hidden" name="id" value="{esc(str(a["id"]))}">'
            f'<button type="submit">Usar este amanhã</button>'
            f'</form></li>'
            for a in alternativas
        )
        corpo = f'<ul style="list-style:none;padding:0">{itens}</ul>'
    return f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<body style="font-family:system-ui;max-width:680px;margin:24px auto;padding:0 16px;color:#1a2b28">
<div style="color:#0f4c3a;font-weight:600">Trocar o estudo de amanhã</div>
<p style="color:#6b7a76;font-size:14px">Atual: {atual}. Escolha outro — o resumo novo chega no seu WhatsApp em ~1-2 min, com link de revisão novo.</p>
{corpo}
<p style="margin-top:16px"><a href="/revisar/{tok}">← Voltar para a revisão</a></p>
</body>"""


def pagina_trocando():
    return ('<!doctype html><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<body style="font-family:system-ui;max-width:600px;margin:40px auto;padding:0 16px;color:#1a2b28">'
            '<h3>🔄 Trocando…</h3>'
            '<p>O novo resumo está sendo gerado. Em ~1-2 min você recebe no WhatsApp o estudo novo '
            '(com PDF, áudio e um link de revisão novo). Pode fechar esta página.</p></body>')
