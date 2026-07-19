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


def montar_checkout(plano, metodo, parcelas, dados, token, base_url):
    """Monta o corpo do POST /checkouts conforme plano×método (puro)."""
    metodo = (metodo or "PIX").upper()
    parcelas = max(1, int(parcelas or 1))
    base = float(plano["base"])
    customer = {"name": dados.get("nome", ""), "cpfCnpj": _so_digitos(dados.get("cpf", "")),
                "email": dados.get("email", ""), "phone": _so_digitos(dados.get("whatsapp", ""))}
    p = {"customerData": customer, "externalReference": token,
         "callback": {"successUrl": f"{base_url}/obrigado", "cancelUrl": f"{base_url}/assinar"}}
    if metodo == "CARTAO":                       # cartão: sempre recorrente (renova no ciclo do plano)
        p["billingTypes"] = ["CREDIT_CARD"]
        p["chargeTypes"] = ["RECURRENT"]
        p["value"] = pricing.valor_cartao(base, parcelas)
        p["subscription"] = {"cycle": plano["cycle"], "nextDueDate": _hoje()}
        if parcelas > 1:
            p["installmentCount"] = parcelas
    elif plano.get("recorrente_pix"):            # mensal via Pix Automático
        p["billingTypes"] = ["PIX"]
        p["chargeTypes"] = ["RECURRENT"]
        p["value"] = base
        p["subscription"] = {"cycle": plano["cycle"], "nextDueDate": _hoje()}
    else:                                        # planos maiores via Pix à vista (não renova)
        p["billingTypes"] = ["PIX"]
        p["chargeTypes"] = ["DETACHED"]
        p["value"] = base
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
    """Cria o checkout e retorna {url, id}. Erro logado; lança pro caller tratar."""
    d = _req("checkouts", "POST", payload)
    return {"url": d.get("link") or d.get("url") or d.get("checkoutUrl"), "id": d.get("id")}


def obter_cliente(cid):
    return _req(f"customers/{cid}")


def obter_pagamento(pid):
    return _req(f"payments/{pid}")


def cancelar_assinatura(sid):
    return _req(f"subscriptions/{sid}", "DELETE")


def adiar_vencimento(sid, dias=30):
    from datetime import datetime, timedelta
    atual = _req(f"subscriptions/{sid}")
    base = atual.get("nextDueDate") or _hoje()
    novo = (datetime.fromisoformat(base) + timedelta(days=dias)).date().isoformat()
    return _req(f"subscriptions/{sid}", "PUT", {"nextDueDate": novo})
