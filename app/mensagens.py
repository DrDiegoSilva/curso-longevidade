"""Templates EDITÁVEIS das mensagens de boas-vindas (WhatsApp + e-mail).
O texto vem de db.settings (chave/valor); se não houver, usa o default.
Marcadores: {link} (link de criar senha) e {nome} (nome do assinante).
Trava de segurança: {link} é sempre garantido — se o admin removê-lo do template,
ele é re-anexado antes de enviar (senão o assinante novo não cria senha).
Puro/testável (só depende de db.get_config)."""
import html as _h
import db

# chaves em db.settings
K_WA = "wa_boas_vindas"
K_EMAIL_ASSUNTO = "email_boas_vindas_assunto"
K_EMAIL_CORPO = "email_boas_vindas_corpo"

WA_DEFAULT = (
    "✅ Assinatura confirmada — bem-vindo(a) à *Atualização Científica*!\n\n"
    "📲 *Salve este contato* (Dr. Diego Silva) na sua agenda — assim os estudos chegam "
    "certinho e os *links ficam clicáveis*.\n\n"
    "Para ler os resumos no site, crie sua senha de acesso:\n{link}\n\n"
    "Com seu WhatsApp + senha você entra no site e acessa o *arquivo com todos os estudos "
    "já enviados* — pra reler quando quiser.\n\n"
    "A partir do próximo dia útil você começa a receber os resumos por aqui.")

EMAIL_ASSUNTO_DEFAULT = "Crie sua senha de acesso — Atualização Científica"
EMAIL_CORPO_DEFAULT = (
    "Olá, {nome}!\n\n"
    "Sua assinatura da Atualização Científica está confirmada. Crie sua senha de acesso "
    "para entrar no site e ler os resumos — lá você também tem o arquivo com todos os estudos "
    "já enviados, pra reler quando quiser.\n\n"
    "{link}")


def _garante_link(texto):
    """Re-anexa {link} se o admin o removeu (o link é obrigatório)."""
    return texto if "{link}" in (texto or "") else ((texto or "").rstrip() + "\n\n{link}")


def wa_boas_vindas(link, nome=""):
    """Texto da boas-vindas de WhatsApp (plain text)."""
    tpl = _garante_link(db.get_config(K_WA, WA_DEFAULT) or WA_DEFAULT)
    return tpl.replace("{nome}", (nome or "").strip()).replace("{link}", link or "")


def _corpo_email_html(corpo_tpl, nome, link):
    """Renderiza o corpo (texto do admin) em HTML: escapa o texto, {nome} vira o nome
    (escapado) e {link} vira o botão 'Criar minha senha'. Parágrafos por linha em branco."""
    esc = _h.escape
    txt = esc(_garante_link(corpo_tpl)).replace("{nome}", esc((nome or "").strip()))
    botao = (
        f'<a href="{esc(link or "")}" style="display:inline-block;background:#c9a227;color:#1a1300;'
        f'font-family:system-ui,sans-serif;font-weight:700;text-decoration:none;padding:14px 30px;'
        f'border-radius:100px">Criar minha senha</a>'
        f'<br><br><span style="color:#a9bcb2;font-size:13px">Se o botão não abrir, copie e cole no '
        f'navegador:<br>{esc(link or "")}</span>')
    txt = txt.replace("{link}", botao)
    blocos = "".join(f'<p style="margin:0 0 16px">{b.replace(chr(10), "<br>")}</p>'
                     for b in txt.split("\n\n") if b.strip())
    return (f'<div style="font-family:Georgia,serif;background:#0e211a;color:#e8efe9;padding:32px;'
            f'border-radius:16px;max-width:520px;margin:0 auto">'
            f'<h1 style="color:#e7c766;font-size:26px;margin:0 0 16px">Crie sua senha de acesso</h1>'
            f'{blocos}</div>')


def email_boas_vindas(nome, link):
    """(assunto, html) da boas-vindas por e-mail."""
    assunto = (db.get_config(K_EMAIL_ASSUNTO, EMAIL_ASSUNTO_DEFAULT) or EMAIL_ASSUNTO_DEFAULT)
    assunto = assunto.replace("{nome}", (nome or "").strip())
    corpo = db.get_config(K_EMAIL_CORPO, EMAIL_CORPO_DEFAULT) or EMAIL_CORPO_DEFAULT
    return assunto, _corpo_email_html(corpo, nome, link)
