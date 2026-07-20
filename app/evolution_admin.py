"""Gestão da conexão WhatsApp (Evolution API) para a tela de admin.

Fino cliente HTTP sobre a Evolution: estado da conexão, QR/código de pareamento,
reiniciar e desconectar. Usa a instância/credenciais de config.evolution().
"""
import json
import urllib.request
import urllib.error
import config


def _req(method, path, body=None):
    e = config.evolution()
    if not e.get("url"):
        return {"_error": "sem_config", "_body": "Evolution não configurado"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{e['url']}/{path}", data=data,
        headers={"apikey": e.get("apikey") or "", "Content-Type": "application/json"},
        method=method)
    try:
        raw = urllib.request.urlopen(req, timeout=20).read().decode() or "{}"
        return json.loads(raw)
    except urllib.error.HTTPError as ex:
        return {"_error": ex.code, "_body": ex.read().decode("utf-8", "replace")[:200]}
    except Exception as ex:
        return {"_error": "conn", "_body": str(ex)[:200]}


def _instance():
    return config.evolution().get("instance")


def estado():
    r = _req("GET", f"instance/connectionState/{_instance()}")
    if r.get("_error"):
        return "erro"
    return ((r.get("instance") or {}).get("state")) or r.get("state") or "desconhecido"


def info():
    """{estado, owner, profile} da instância do curso."""
    st = estado()
    owner = profile = None
    r = _req("GET", "instance/fetchInstances")
    arr = r if isinstance(r, list) else (r.get("data") or [])
    for it in arr:
        inst = it.get("instance") or it
        if (inst.get("instanceName") or inst.get("name")) == _instance():
            owner = inst.get("owner") or inst.get("ownerJid")
            profile = inst.get("profileName")
            break
    numero = (owner or "").split("@")[0] if owner else None
    return {"estado": st, "numero": numero, "profile": profile, "instance": _instance()}


def conectar(numero=None):
    """QR + código de pareamento para conectar. Retorna {qr, pairingCode}."""
    path = f"instance/connect/{_instance()}"
    if numero:
        path += f"?number={numero}"
    r = _req("GET", path)
    qr = r.get("qrcode") or r
    b64 = qr.get("base64") or r.get("base64")
    if b64 and not str(b64).startswith("data:"):
        b64 = "data:image/png;base64," + b64
    return {"qr": b64, "pairingCode": qr.get("pairingCode") or r.get("pairingCode"),
            "erro": r.get("_body") if r.get("_error") else None}


def reiniciar():
    return _req("POST", f"instance/restart/{_instance()}")


def desconectar():
    return _req("DELETE", f"instance/logout/{_instance()}")
