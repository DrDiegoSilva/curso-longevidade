"""Entrega WhatsApp (backend trocável: Evolution ou Z-API).

- Evolution (self-hosted): PDF vai em base64 (não precisa de URL pública).
- Z-API (legado): mantém envio por URL.
O backend é escolhido por config.WHATSAPP_BACKEND. Partes de montagem de payload
são puras e testáveis; o loop de distribuição injeta a função de envio.
"""
import time
import json
import re
import base64
import urllib.request
import urllib.error
import config


def personalizar_rodape(msg, nome, link):
    return f"{msg}\n\n— {nome}\nMinha assinatura / cancelar: {link}"


# ── Z-API (legado) ──
def _zapi_post(caminho, payload):
    z = config.zapi()
    url = f"https://api.z-api.io/instances/{z['instanceId']}/token/{z['instanceToken']}/{caminho}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json", "Client-Token": z["clientToken"]})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


# ── Evolution API (self-hosted) ──
def _evolution_texto_payload(whatsapp, msg):
    return {"number": whatsapp, "text": msg}


def _evolution_media_payload(whatsapp, pdf_path, caption):
    b64 = base64.b64encode(open(pdf_path, "rb").read()).decode("ascii")
    nome = (re.sub(r"[^\w-]", "_", caption)[:40] or "documento") + ".pdf"
    return {"number": whatsapp, "mediatype": "document", "mimetype": "application/pdf",
            "media": b64, "fileName": nome, "caption": caption}


def _evolution_post(caminho, payload):
    e = config.evolution()
    url = f"{e['url']}/{caminho}/{e['instance']}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json", "apikey": e["apikey"]})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as ex:
        print(f"[evolution] {caminho} HTTP {ex.code}: {ex.read().decode('utf-8', 'replace')[:200]}", flush=True)
        raise


# ── API pública (dispatch por backend) ──
def enviar_texto(whatsapp, msg):
    if config.WHATSAPP_BACKEND == "evolution":
        return _evolution_post("message/sendText", _evolution_texto_payload(whatsapp, msg))
    return _zapi_post("send-text", {"phone": whatsapp, "message": msg})


def enviar_pdf(whatsapp, pdf_path, caption=""):
    """pdf_path = arquivo LOCAL. Evolution manda em base64; Z-API precisaria de URL."""
    if config.WHATSAPP_BACKEND == "evolution":
        return _evolution_post("message/sendMedia", _evolution_media_payload(whatsapp, pdf_path, caption))
    return _zapi_post("send-document/pdf", {"phone": whatsapp, "document": pdf_path, "caption": caption})


def numeros_curadores():
    """Números que recebem a revisão das 18h: o(s) admin(s) (Dr. Diego, sempre) +
    assinantes marcados como 'curador' na tela de Assinantes. Normalizado e sem
    repetição. NÃO usa mais a env WHATSAPP_DESTINO (apontava p/ o nº automático)."""
    import phone
    nums = [phone.normalizar(w) for w in (config.ADMIN_WHATSAPPS or [])]
    try:
        import subscribers
        nums += [phone.normalizar(s.get("whatsapp", "")) for s in subscribers.curadores()]
    except Exception as e:
        print(f"[curador] falha ao carregar curadores: {e}", flush=True)
    vistos, out = set(), []
    for n in nums:
        if n and n not in vistos:
            vistos.add(n)
            out.append(n)
    return out


def enviar_audio(whatsapp, mp3_bytes):
    """Envia o mp3 como mensagem de voz (WhatsApp PTT) via Evolution."""
    if config.WHATSAPP_BACKEND != "evolution":
        return None
    b64 = base64.b64encode(mp3_bytes).decode("ascii")
    return _evolution_post("message/sendWhatsAppAudio", {"number": whatsapp, "audio": b64})


def enviar_curador(msg):
    """Aviso ao curador (Dr. Diego + curadores convidados) — jobs 18h/08h.
    Envia a cada curador; falha de um não derruba os outros."""
    res = None
    for num in numeros_curadores():
        try:
            res = enviar_texto(num, msg)
        except Exception as e:
            print(f"[curador] envio p/ {num} falhou: {e}", flush=True)
    return res


def enviar_admin(msg):
    """Aviso SÓ pro(s) admin(s) (Dr. Diego) — não vai pros curadores convidados.
    Usado p/ alertas operacionais (ex.: estoque de estudos baixo)."""
    import phone
    res, vistos = None, set()
    for w in (config.ADMIN_WHATSAPPS or []):
        n = phone.normalizar(w)
        if not n or n in vistos:
            continue
        vistos.add(n)
        try:
            res = enviar_texto(n, msg)
        except Exception as e:
            print(f"[admin] envio p/ {n} falhou: {e}", flush=True)
    return res


def distribuir(rascunho, assinantes, delay_sec, enviar_fn):
    """Loop com throttle. enviar_fn(whatsapp, nome) injetável (testável sem rede).
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
