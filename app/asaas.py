"""Cliente Asaas (checkout hospedado + assinaturas). stdlib urllib.
`montar_checkout` é puro/testável; as funções de rede logam erro server-side e
nunca vazam o corpo cru do Asaas pro cliente.

No POST /checkouts do Asaas, um cartão é assinatura OU parcelamento — nunca os dois:
  - `chargeTypes: ["RECURRENT"]` + objeto `subscription` -> renova sozinho, mas cobra o
    item CHEIO a cada ciclo (não divide nada);
  - `chargeTypes: ["INSTALLMENT"]` + objeto `installment` -> divide na fatura do cartão,
    e acaba no fim: não recorre.

CORRIGIDO EM 2026-07-30 (custou uma venda real): até aqui o payload mandava um
`installmentCount` de PRIMEIRO NÍVEL junto de `chargeTypes: ["RECURRENT"]`. Esse campo
NÃO EXISTE no POST /checkouts — parcelamento é o objeto `installment` e exige
`INSTALLMENT` em `chargeTypes`. O Asaas descartava o campo desconhecido, honrava o
RECURRENT e cobrava tudo de uma vez: um cliente que escolheu 12x levou R$ 997 numa
tacada. Ninguém nunca parcelou desde o primeiro commit (8b92bb9, 2026-07-19), e a suíte
ficava verde porque o teste afirmava a mesma crença errada.

`maxInstallmentCount` é TETO, não escolha: o nº final de parcelas o cliente marca na
tela do Asaas. Por isso `webhook_asaas._pending_plausivel` aceita qualquer divisor até
o teto — exigir o número exato barraria a venda.

Consequências de que o resto do sistema depende (agora de verdade, não por acidente):
  - a cláusula 2 dos termos está correta ao dizer que só o cartão à vista renova;
  - o assinante de parcelado não fica com `asaas_subscription_id`, então o cancelamento
    não chama DELETE /subscriptions — as parcelas restantes seguem sendo cobradas, que é o
    que a cláusula 3 promete.
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
        p["items"] = [{"name": item_nome, "description": _DESC_ITEM, "quantity": 1, "value": valor}]
        if parcelas > 1:                                  # PARCELADO: divide e acaba
            p["chargeTypes"] = ["INSTALLMENT"]
            p["installment"] = {"maxInstallmentCount": parcelas}
        else:                                             # À VISTA: recorre no ciclo
            p["chargeTypes"] = ["RECURRENT"]
            p["subscription"] = {"cycle": plano["cycle"], "nextDueDate": _hoje()}
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


_DESC_ESTORNO = "Cancelamento no prazo de arrependimento (CDC art. 49)."


def _payload_estorno(valor):
    p = {"description": _DESC_ESTORNO}
    if valor is not None:                 # sem `value` o Asaas estorna o total
        p["value"] = float(valor)
    return p


def estornar_pagamento(pid, valor=None):
    """POST /payments/{id}/refund. valor=None => estorno total.
    O saldo sai da conta Asaas; no cartão leva até 10 dias úteis pra aparecer na fatura."""
    return _req(f"payments/{pid}/refund", "POST", _payload_estorno(valor))


def estornar_parcelamento(iid, valor=None):
    """POST /installments/{id}/refund. valor=None => estorno total do parcelamento.
    Usado quando o pagamento faz parte de um parcelamento no cartão — estornar só a
    parcela devolveria uma fração do valor."""
    return _req(f"installments/{iid}/refund", "POST", _payload_estorno(valor))
