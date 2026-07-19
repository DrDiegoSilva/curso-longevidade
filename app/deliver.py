"""Entrega WhatsApp texto + PDF à lista, com personalização e throttle."""
import time
import json
import urllib.request
import config


def personalizar_rodape(msg, nome, link):
    return f"{msg}\n\n— {nome}\nMinha assinatura / cancelar: {link}"


def _zapi_post(caminho, payload):
    z = config.zapi()
    url = f"https://api.z-api.io/instances/{z['instanceId']}/token/{z['instanceToken']}/{caminho}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json", "Client-Token": z["clientToken"]})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def enviar_texto(whatsapp, msg):
    return _zapi_post("send-text", {"phone": whatsapp, "message": msg})


def enviar_pdf(whatsapp, pdf_url, caption=""):
    return _zapi_post("send-document/pdf", {"phone": whatsapp, "document": pdf_url, "caption": caption})


def distribuir(rascunho, assinantes, delay_sec, enviar_fn):
    """Loop com throttle. enviar_fn(whatsapp, nome) é injetado (testável sem rede).
    Falha em um assinante não derruba o lote."""
    ok, falhas = 0, []
    for a in assinantes:
        try:
            enviar_fn(a["whatsapp"], a.get("nome", ""))
            ok += 1
        except Exception as e:
            falhas.append({"whatsapp": a.get("whatsapp"), "erro": str(e)})
        time.sleep(delay_sec)
    return {"ok": ok, "falhas": falhas}
