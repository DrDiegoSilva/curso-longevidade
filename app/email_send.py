"""Envio de e-mail via Resend (stdlib urllib). Sem chave => só loga (degrada).
Usado para confirmação de cancelamento e aviso de pré-renovação.
"""
import json
import urllib.request
import config


def _resend_payload(to, assunto, html, remetente):
    return {"from": remetente, "to": [to], "subject": assunto, "html": html}


def enviar(to, assunto, html):
    if config.EMAIL_BACKEND != "resend" or not config.RESEND_API_KEY:
        print(f"[email] (backend={config.EMAIL_BACKEND}) p/ {to}: {assunto}", flush=True)
        return {"ok": False, "skipped": True}
    payload = _resend_payload(to, assunto, html, config.EMAIL_FROM)
    try:
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {config.RESEND_API_KEY}"})
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()
        return {"ok": True}
    except Exception as e:
        print(f"[email] falha ao enviar p/ {to}: {e}", flush=True)
        return {"ok": False, "erro": str(e)}
