"""Login por código no WhatsApp (OTP) + sessão server-side. Só stdlib.

- iniciar_login(whatsapp): só p/ assinante ATIVO; gera código de 6 dígitos, guarda
  sha256 + expiry (10 min), envia via WhatsApp. Retorno neutro (anti-enumeração).
- verificar(whatsapp, codigo): confere hash/expiry/tentativas; acerto cria sessão (30d).
- sessao(cookie_header): resolve o cookie 'sid' -> assinante logado ou None.
Tabelas login_codes/sessions são criadas por db.init().
"""
import hashlib
import secrets
from datetime import datetime, timedelta
import config
import db
import subscribers
import phone

CODIGO_TTL_MIN = 10
SESSAO_TTL_DIAS = 30
MAX_TENTATIVAS = 5
FIRST_ACCESS_TTL_H = 24 * 7   # link de 1º acesso (vem na boas-vindas) vale 7 dias
RESET_TTL_H = 1               # link de "esqueci a senha" vale 1 hora


def _norm(whatsapp):
    return phone.normalizar(whatsapp)


def _hash(codigo):
    return hashlib.sha256(str(codigo).encode("utf-8")).hexdigest()


def _parse_cookie(header):
    out = {}
    for parte in (header or "").split(";"):
        if "=" in parte:
            k, v = parte.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _assinante_ativo(num):
    for a in subscribers.ativos():
        if _norm(a.get("whatsapp", "")) == num:
            return a
    return None


def iniciar_login(whatsapp, enviar_fn=None):
    """Envia o código só se for assinante ATIVO. Retorna True se enviou."""
    num = _norm(whatsapp)
    a = _assinante_ativo(num)
    if not a:
        return False
    codigo = f"{secrets.randbelow(1000000):06d}"
    expira = (datetime.now() + timedelta(minutes=CODIGO_TTL_MIN)).isoformat()
    with db._conn() as c:
        c.execute(
            """INSERT INTO login_codes (whatsapp,codigo_hash,expira,tentativas) VALUES (?,?,?,0)
               ON CONFLICT(whatsapp) DO UPDATE SET codigo_hash=excluded.codigo_hash,
                 expira=excluded.expira, tentativas=0""",
            (num, _hash(codigo), expira),
        )
    msg = (f"🔐 Seu código de acesso ao portal Atualização Científica é *{codigo}*.\n"
           f"Válido por {CODIGO_TTL_MIN} minutos. Se não foi você, ignore.")
    fn = enviar_fn or _enviar_padrao
    try:
        fn(num, msg)                     # falha do WhatsApp NÃO pode derrubar a tela de login
    except Exception as e:
        print(f"[login] envio do código falhou: {e}", flush=True)
    return True


def _enviar_padrao(num, msg):
    import deliver
    return deliver.enviar_texto(num, msg)


def verificar(whatsapp, codigo):
    """Confere o código. Acerto -> cria sessão e retorna o token. Senão None."""
    num = _norm(whatsapp)
    with db._conn() as c:
        row = c.execute("SELECT * FROM login_codes WHERE whatsapp=?", (num,)).fetchone()
        if not row:
            return None
        if row["tentativas"] >= MAX_TENTATIVAS:
            return None
        if datetime.fromisoformat(row["expira"]) < datetime.now():
            c.execute("DELETE FROM login_codes WHERE whatsapp=?", (num,))
            return None
        if _hash(codigo) != row["codigo_hash"]:
            c.execute("UPDATE login_codes SET tentativas=tentativas+1 WHERE whatsapp=?", (num,))
            return None
        c.execute("DELETE FROM login_codes WHERE whatsapp=?", (num,))
    a = _assinante_ativo(num)
    return _criar_sessao(num, a.get("nome", "") if a else "")


def _criar_sessao(num, nome):
    """Cria a sessão (cookie sid, 30 dias) e retorna o token. Usada pelo OTP e pela senha."""
    token = secrets.token_hex(16)
    expira = (datetime.now() + timedelta(days=SESSAO_TTL_DIAS)).isoformat()
    with db._conn() as c:
        c.execute("INSERT INTO sessions (token,whatsapp,nome,expira) VALUES (?,?,?,?)",
                  (token, num, nome, expira))
    return token


def sessao(cookie_header):
    """Assinante logado (dict {whatsapp,nome}) a partir do cookie, ou None."""
    tok = _parse_cookie(cookie_header).get("sid")
    if not tok:
        return None
    with db._conn() as c:
        row = c.execute("SELECT * FROM sessions WHERE token=?", (tok,)).fetchone()
        if not row:
            return None
        if datetime.fromisoformat(row["expira"]) < datetime.now():
            c.execute("DELETE FROM sessions WHERE token=?", (tok,))
            return None
    return {"whatsapp": row["whatsapp"], "nome": row["nome"]}


def eh_admin(whatsapp):
    """True se o WhatsApp é de um admin (Diego) — vê os atalhos de admin sem token."""
    alvo = _norm(whatsapp)
    return bool(alvo) and alvo in {_norm(w) for w in config.ADMIN_WHATSAPPS}


def logout(token):
    if not token:
        return
    with db._conn() as c:
        c.execute("DELETE FROM sessions WHERE token=?", (token,))


# ── Login por SENHA (não depende do WhatsApp) ──
def login_senha(whatsapp, senha):
    """Login por WhatsApp + senha. Retorna (status, token_sessao).
    status: 'ok' (token setado) | 'sem_senha' | 'credenciais' | 'inativo'."""
    import passwords
    num = _norm(whatsapp)
    a = _assinante_ativo(num)
    if not a:
        return ("inativo", None)
    h = a.get("senha_hash")
    if not h:
        return ("sem_senha", None)
    if not passwords.conferir_senha(senha or "", h):
        return ("credenciais", None)
    return ("ok", _criar_sessao(num, a.get("nome", "")))


def precisa_criar_senha(whatsapp):
    """True se é assinante ativo e ainda NÃO tem senha (guia o 1º acesso)."""
    a = _assinante_ativo(_norm(whatsapp))
    return bool(a and not a.get("senha_hash"))


# ── Criação / redefinição de senha por token (link enviado por e-mail + WhatsApp) ──
def _link_senha(token):
    return f"{config.ARTIGOS_URL}/criar-senha?token={token}"


def preparar_primeiro_acesso(whatsapp):
    """Cria o token de 1º acesso (7 dias) e devolve o LINK — usado na boas-vindas do webhook."""
    num = _norm(whatsapp)
    return _link_senha(db.criar_token_senha(num, validade_horas=FIRST_ACCESS_TTL_H))


def iniciar_definir_senha(whatsapp, motivo="reset", enviar_fn=None):
    """Cria token e envia o link (e-mail + WhatsApp). SEMPRE neutro p/ o usuário
    (anti-enumeração). Retorna True se havia assinante ativo (uso em teste)."""
    num = _norm(whatsapp)
    a = _assinante_ativo(num)
    if not a:
        return False
    primeiro = (motivo == "primeiro")
    ttl = FIRST_ACCESS_TTL_H if primeiro else RESET_TTL_H
    link = _link_senha(db.criar_token_senha(num, validade_horas=ttl))
    _enviar_link_senha(a, link, primeiro, enviar_fn)
    return True


def definir_senha(token, senha, senha2):
    """Grava a senha a partir do token de uso único. Retorna (status, token_sessao).
    status: 'ok' | 'token_invalido' | 'nao_confere' | 'fraca'."""
    import passwords
    reg = db.obter_token_senha(token)
    if not reg:
        return ("token_invalido", None)
    if (senha or "") != (senha2 or ""):
        return ("nao_confere", None)
    if not passwords.validar_forca(senha):
        return ("fraca", None)
    a = subscribers.por_whatsapp(reg["whatsapp"])
    if not a:
        return ("token_invalido", None)
    subscribers.definir_senha(a["id"], passwords.hash_senha(senha))
    db.consumir_token_senha(token)
    return ("ok", _criar_sessao(reg["whatsapp"], a.get("nome", "")))


def _enviar_link_senha(a, link, primeiro, enviar_fn=None):
    """Manda o link por e-mail (se houver) e por WhatsApp (fallback/redundância)."""
    email = (a.get("email") or "").strip()
    nome = a.get("nome", "")
    assunto = ("Crie sua senha de acesso" if primeiro else "Redefinir sua senha") + f" — {config.PRODUTO}"
    if email:
        try:
            import email_send
            email_send.enviar(email, assunto, email_html_senha(nome, link, primeiro))
        except Exception as e:
            print(f"[senha] e-mail falhou: {e}", flush=True)
    wpp = a.get("whatsapp", "")
    if wpp:
        fn = enviar_fn or _enviar_padrao
        try:
            fn(wpp, wa_msg_senha(link, primeiro))
        except Exception as e:
            print(f"[senha] WhatsApp falhou: {e}", flush=True)


def wa_msg_senha(link, primeiro):
    if primeiro:
        return (f"✅ Assinatura confirmada — bem-vindo(a) à *{config.PRODUTO}*!\n\n"
                f"📲 *Salve este contato* (Dr. Diego Silva) na sua agenda — assim os estudos "
                f"chegam certinho e os *links ficam clicáveis*.\n\n"
                f"Para ler os resumos no site, crie sua senha de acesso:\n{link}\n\n"
                f"Com seu WhatsApp + senha você entra em {config.ARTIGOS_URL} e tem acesso ao "
                f"*arquivo com todos os estudos já enviados* — pra reler quando quiser.")
    return (f"🔐 Para redefinir sua senha da *{config.PRODUTO}*, use este link "
            f"(vale 1 hora):\n{link}\n\nSe não foi você, ignore.")


def email_html_senha(nome, link, primeiro):
    import html as _h
    saud = f"Olá, {_h.escape(nome)}!" if nome else "Olá!"
    if primeiro:
        titulo = "Crie sua senha de acesso"
        texto = (f"Sua assinatura da <strong>{config.PRODUTO}</strong> está confirmada. "
                 f"Crie sua senha de acesso para entrar no site e ler os resumos — lá você também "
                 f"tem o <strong>arquivo com todos os estudos já enviados</strong>, pra reler quando quiser:")
        botao = "Criar minha senha"
    else:
        titulo = "Redefinir sua senha"
        texto = "Recebemos um pedido para redefinir a senha da sua conta. Clique abaixo para criar uma nova senha:"
        botao = "Redefinir senha"
    return (
        f'<div style="font-family:Georgia,serif;background:#0e211a;color:#e8efe9;padding:32px;border-radius:16px;max-width:520px;margin:0 auto">'
        f'<h1 style="font-family:Georgia,serif;color:#e7c766;font-size:26px;margin:0 0 16px">{titulo}</h1>'
        f'<p style="margin:0 0 12px">{saud}</p>'
        f'<p style="color:#a9bcb2;margin:0 0 24px">{texto}</p>'
        f'<p style="margin:0 0 24px"><a href="{link}" '
        f'style="display:inline-block;background:#c9a227;color:#1a1300;font-family:system-ui,sans-serif;'
        f'font-weight:700;text-decoration:none;padding:14px 30px;border-radius:100px">{botao}</a></p>'
        f'<p style="color:#a9bcb2;font-size:13px;margin:0">Se o botão não abrir, copie e cole no navegador:<br>{link}</p>'
        f'</div>')
