"""Cliente Asaas (checkout hospedado + assinaturas). stdlib urllib.
`montar_checkout` é puro/testável; as funções de rede logam erro server-side e
nunca vazam o corpo cru do Asaas pro cliente.

⚠️ Validar no sandbox: aceitação de RECURRENT + installmentCount juntos (cartão
parcelado que renova). Se o Asaas recusar, escolher um dos dois na hora.
"""
import json
import urllib.request
import urllib.error
from datetime import date
import config
import pricing


def _so_digitos(s):
    return "".join(c for c in (s or "") if c.isdigit())


def _hoje():
    return date.today().isoformat()


_DESC_ITEM = "Resumos científicos diários selecionados para médicos."


def montar_checkout(plano, metodo, parcelas, dados, token, base_url, base=None):
    """Corpo do POST /checkouts (puro). Regras REAIS do Asaas:
    - CARTÃO → RECURRENT (renova no ciclo; parcelável) — único método que recorre.
    - PIX → DETACHED (à vista, não renova; exige chave Pix na conta).
    `customerData` é OMITIDO de propósito: o checkout hospedado coleta nome/CPF/
    endereço/cartão; a amarração ao assinante é pelo externalReference.
    """
    metodo = "CARTAO" if (metodo or "").upper() == "CARTAO" else "PIX"
    parcelas = max(1, int(parcelas or 1))
    base = float(plano["base"]) if base is None else float(base)
    item_nome = f"Assinatura {plano['nome']}"[:30]        # Asaas: name <= 30 chars
    p = {"externalReference": token,
         "callback": {"successUrl": f"{base_url}/obrigado", "cancelUrl": f"{base_url}/assinar"}}
    if metodo == "CARTAO":
        valor = pricing.valor_cartao(base, parcelas)
        p["billingTypes"] = ["CREDIT_CARD"]
        p["chargeTypes"] = ["RECURRENT"]
        p["items"] = [{"name": item_nome, "description": _DESC_ITEM, "quantity": 1, "value": valor}]
        p["subscription"] = {"cycle": plano["cycle"], "nextDueDate": _hoje()}
        if parcelas > 1:
            p["installmentCount"] = parcelas
    else:                                                 # PIX à vista (não renova)
        p["billingTypes"] = ["PIX"]
        p["chargeTypes"] = ["DETACHED"]
        p["items"] = [{"name": item_nome, "description": _DESC_ITEM, "quantity": 1, "value": base}]
    return p


# ── Rede ──
def _req(caminho, metodo="GET", payload=None):
    url = f"{config.ASAAS_BASE_URL}/{caminho}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=metodo,
                                 headers={"Content-Type": "application/json",
                                          "access_token": config.ASAAS_API_KEY or ""})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace") or "{}")


def criar_checkout(payload):
    """Cria o checkout e retorna {url, id}. Loga o corpo do erro do Asaas e relança."""
    try:
        d = _req("checkouts", "POST", payload)
    except urllib.error.HTTPError as e:
        corpo = e.read().decode("utf-8", "replace")
        print(f"[asaas] checkout HTTP {e.code}: {corpo[:500]}", flush=True)
        raise
    return {"url": d.get("link") or d.get("url") or d.get("checkoutUrl"), "id": d.get("id")}


def obter_cliente(cid):
    return _req(f"customers/{cid}")


def obter_pagamento(pid):
    return _req(f"payments/{pid}")


def obter_assinatura(sid):
    return _req(f"subscriptions/{sid}")


def cancelar_assinatura(sid):
    return _req(f"subscriptions/{sid}", "DELETE")


def adiar_vencimento(sid, dias=30):
    from datetime import datetime, timedelta
    atual = _req(f"subscriptions/{sid}")
    base = atual.get("nextDueDate") or _hoje()
    novo = (datetime.fromisoformat(base) + timedelta(days=dias)).date().isoformat()
    return _req(f"subscriptions/{sid}", "PUT", {"nextDueDate": novo})
