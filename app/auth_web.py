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
import db
import subscribers

CODIGO_TTL_MIN = 10
SESSAO_TTL_DIAS = 30
MAX_TENTATIVAS = 5


def _norm(whatsapp):
    return "".join(c for c in (whatsapp or "") if c.isdigit())


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
    fn(num, msg)
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
    nome = a.get("nome", "") if a else ""
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


def logout(token):
    if not token:
        return
    with db._conn() as c:
        c.execute("DELETE FROM sessions WHERE token=?", (token,))
