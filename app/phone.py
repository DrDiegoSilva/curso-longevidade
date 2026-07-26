"""Normalização de número de WhatsApp (E.164 canônico).
- BR: dígitos '55'+DDD+número (sem '+', igual ao legado). Números de 10-11 dígitos
  sem país ganham o 55.
- Internacional: entrada com '+' mantém o '+CC…' (idempotente). Só o Brasil é +55,
  então '+55…' é canonizado de volta pra '55…' (consistente com o legado BR).
O WhatsApp recebe só dígitos (ver para_api)."""


def normalizar(w):
    w = (w or "").strip()
    intl = w.startswith("+")
    d = "".join(c for c in w if c.isdigit())
    if intl:
        return d if d.startswith("55") else "+" + d
    if len(d) in (10, 11):
        return "55" + d
    return d


def para_api(w):
    """Formato que o WhatsApp aceita: só dígitos com código do país (sem '+')."""
    return normalizar(w).lstrip("+")


def montar_e164(dial, local):
    """Junta o código do país (do seletor) + número local -> '+<dial><digitos>'."""
    d = "".join(c for c in (local or "") if c.isdigit())
    dd = "".join(c for c in (dial or "") if c.isdigit())
    return "+" + dd + d
