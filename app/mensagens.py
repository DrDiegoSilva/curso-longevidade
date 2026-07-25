"""Templates EDITÁVEIS das mensagens de boas-vindas (WhatsApp + e-mail) e da
confirmação de renovação/recontratação (só e-mail — ver email_renovacao).
O texto vem de db.settings (chave/valor); se não houver, usa o default.
Marcadores das boas-vindas: {link} (link de criar senha) e {nome} (nome do assinante).
Marcadores da confirmação de renovação: {nome}, {ate} (data até quando o acesso vale)
e {link} (aqui o link é de ENTRAR — a conta já existe, não tem senha pra criar).
Trava de segurança: {link} é sempre garantido nos dois templates — se o admin removê-lo,
ele é re-anexado antes de enviar. Na confirmação de renovação, {ate} tem a mesma trava:
é a informação essencial da mensagem (sem ela vira uma confirmação vazia).
Puro/testável (só depende de db.get_config)."""
import html as _h
import db

# chaves em db.settings
K_WA = "wa_boas_vindas"
K_EMAIL_ASSUNTO = "email_boas_vindas_assunto"
K_EMAIL_CORPO = "email_boas_vindas_corpo"
K_EMAIL_RENOV_ASSUNTO = "email_renovacao_assunto"
K_EMAIL_RENOV_CORPO = "email_renovacao_corpo"

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

# Confirmação de renovação/recontratação — texto único (decisão do Diego): pro
# assinante, renovação automática (cartão à vista) e recontratação (acesso que
# expirou e ele comprou de novo) são a mesma coisa — "paguei e meu acesso segue
# valendo". Só e-mail; WhatsApp fica reservado aos estudos.
EMAIL_RENOV_ASSUNTO_DEFAULT = "Pagamento confirmado — Atualização Científica"
EMAIL_RENOV_CORPO_DEFAULT = (
    "Olá, {nome}!\n\n"
    "Recebemos seu pagamento e sua assinatura da Atualização Científica segue ativa — "
    "seu acesso vale até {ate}.\n\n"
    "Para entrar na sua conta e ver os estudos já enviados, acesse:\n{link}")


def _garante_link(texto):
    """Re-anexa {link} se o admin o removeu (o link é obrigatório)."""
    return texto if "{link}" in (texto or "") else ((texto or "").rstrip() + "\n\n{link}")


def _garante_data(texto):
    """Re-anexa {ate} se o admin o removeu do template de renovação — a data de
    validade é a informação essencial dessa mensagem, então nunca pode faltar."""
    return texto if "{ate}" in (texto or "") else ((texto or "").rstrip() + "\n\n{ate}")


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


def _corpo_email_renov_html(corpo_tpl, nome, ate, link):
    """Renderiza o corpo da confirmação de renovação/recontratação em HTML: escapa o
    texto, {nome} e {ate} viram texto (escapados) e {link} vira um botão de ENTRAR —
    diferente do de criar senha das boas-vindas, porque aqui a conta já existe."""
    esc = _h.escape
    txt = esc(_garante_data(_garante_link(corpo_tpl)))
    txt = txt.replace("{nome}", esc((nome or "").strip())).replace("{ate}", esc((ate or "").strip()))
    botao = (
        f'<a href="{esc(link or "")}" style="display:inline-block;background:#c9a227;color:#1a1300;'
        f'font-family:system-ui,sans-serif;font-weight:700;text-decoration:none;padding:14px 30px;'
        f'border-radius:100px">Acessar minha conta</a>'
        f'<br><br><span style="color:#a9bcb2;font-size:13px">Se o botão não abrir, copie e cole no '
        f'navegador:<br>{esc(link or "")}</span>')
    txt = txt.replace("{link}", botao)
    blocos = "".join(f'<p style="margin:0 0 16px">{b.replace(chr(10), "<br>")}</p>'
                     for b in txt.split("\n\n") if b.strip())
    return (f'<div style="font-family:Georgia,serif;background:#0e211a;color:#e8efe9;padding:32px;'
            f'border-radius:16px;max-width:520px;margin:0 auto">'
            f'<h1 style="color:#e7c766;font-size:26px;margin:0 0 16px">Pagamento confirmado</h1>'
            f'{blocos}</div>')


def email_renovacao(nome, ate, link):
    """(assunto, html) da confirmação de renovação/recontratação por e-mail.

    Um único texto serve tanto pra renovação automática (cartão à vista, ramo RENOVAR)
    quanto pra recontratação (ATIVAR quando o acesso já tinha expirado) — decisão do
    Diego: pro assinante os dois casos são só "paguei e meu acesso segue valendo".
    `ate` já deve chegar formatado em pt-BR (ver site_web._data_br)."""
    assunto = (db.get_config(K_EMAIL_RENOV_ASSUNTO, EMAIL_RENOV_ASSUNTO_DEFAULT) or EMAIL_RENOV_ASSUNTO_DEFAULT)
    assunto = assunto.replace("{nome}", (nome or "").strip())
    corpo = db.get_config(K_EMAIL_RENOV_CORPO, EMAIL_RENOV_CORPO_DEFAULT) or EMAIL_RENOV_CORPO_DEFAULT
    return assunto, _corpo_email_renov_html(corpo, nome, ate, link)
