"""Hash e validação de senha — só stdlib (PBKDF2-HMAC-SHA256). Puro/testável.

Formato guardado: 'pbkdf2_sha256$<iteracoes>$<salt_b64>$<hash_b64>'. Salt por
usuário; comparação em tempo constante. Nunca guardar a senha crua.
"""
import base64
import hashlib
import hmac
import os

_ALGO = "pbkdf2_sha256"
_ITER = 200_000
MIN_LEN = 6


def hash_senha(senha):
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", (senha or "").encode("utf-8"), salt, _ITER)
    return f"{_ALGO}${_ITER}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def conferir_senha(senha, guardado):
    """True se a senha bate com o hash guardado. Formato inválido => False (sem exceção)."""
    try:
        algo, iteracoes, salt_b64, hash_b64 = (guardado or "").split("$")
        if algo != _ALGO:
            return False
        salt = base64.b64decode(salt_b64)
        esperado = base64.b64decode(hash_b64)
        it = int(iteracoes)
    except (ValueError, AttributeError, TypeError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", (senha or "").encode("utf-8"), salt, it)
    return hmac.compare_digest(dk, esperado)


def validar_forca(senha):
    """Regra leve: >= MIN_LEN caracteres, com pelo menos uma letra e um número."""
    s = senha or ""
    if len(s) < MIN_LEN:
        return False
    return any(c.isalpha() for c in s) and any(c.isdigit() for c in s)
