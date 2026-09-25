"""Rastreio de leitura das mensagens de WhatsApp (Z-API ou Evolution, conforme
`config.WHATSAPP_BACKEND`) -- é o que alimenta a tela de engajamento (achado do Diego,
2026-09-25: o app não media NADA de uso além do "marcar feito" da trilha).

Duas pontas:
1. No ENVIO (`deliver.enviar_texto`/`enviar_pdf`/`enviar_audio` já devolvem a resposta
   crua do provedor) -- `extrair_id_*` pega o id da mensagem dessa resposta, pra
   `db.registrar_mensagem_enviada` guardar contra quem/o quê foi mandado.
2. No WEBHOOK de status que o provedor chama depois (entregue/lida/reproduzida) --
   `decidir_status_*` traduz o payload pro nosso vocabulário fixo
   (enviado/entregue/lida/reproduzida) e casa pelo id.

Formato dos payloads conforme documentação pública da Z-API e da Evolution API --
NÃO testado contra um webhook real (esta sessão não tem rede pra isso). Se o formato
divergir, `processar()` não quebra (nunca levanta), só não atualiza nada -- o primeiro
webhook real que chegar em produção deve ser conferido nos logs do container.
"""
import json

import config

_ORDEM_ZAPI = {"SENT": "enviado", "RECEIVED": "entregue", "READ": "lida", "PLAYED": "reproduzida"}
_ORDEM_EVOLUTION_ACK = {2: "entregue", 3: "entregue", 4: "lida", 5: "reproduzida"}


def extrair_id_zapi(resposta_texto):
    """Id da mensagem a partir da resposta do POST de envio (`send-text`/`send-document`).
    Z-API devolve `messageId` (e também `zaapId`, que NÃO é o id usado no webhook de
    status) -- puro/testável com a string crua que `deliver._zapi_post` devolve."""
    try:
        d = json.loads(resposta_texto or "")
    except Exception:
        return None
    return d.get("messageId") or d.get("id") or None


def extrair_id_evolution(resposta_texto):
    """Id da mensagem a partir da resposta do POST de envio da Evolution -- vem em
    `key.id` (convenção Baileys)."""
    try:
        d = json.loads(resposta_texto or "")
    except Exception:
        return None
    return (d.get("key") or {}).get("id") or None


def decidir_status_zapi(payload):
    """Payload do webhook de status da Z-API -> lista de (msg_id, status) no nosso
    vocabulário. Z-API pode mandar um `messageId` só ou uma lista `ids` (status em lote).
    Status fora do vocabulário conhecido (`_ORDEM_ZAPI`) é ignorado, não quebra."""
    status = _ORDEM_ZAPI.get((payload or {}).get("status", "").upper())
    if not status:
        return []
    ids = payload.get("ids") or ([payload["messageId"]] if payload.get("messageId") else [])
    return [(i, status) for i in ids if i]


def decidir_status_evolution(payload):
    """Payload do webhook `messages.update` da Evolution -> lista de (msg_id, status).
    O ack code vem em `data.update.status` (Baileys: 2=servidor/entregue, 3=entregue,
    4=lida, 5=reproduzida -- 0/1 são erro/pendente, sem status nosso pra eles)."""
    data = (payload or {}).get("data") or {}
    ack = (data.get("update") or {}).get("status")
    msg_id = (data.get("key") or {}).get("id")
    status = _ORDEM_EVOLUTION_ACK.get(ack)
    if not msg_id or not status:
        return []
    return [(msg_id, status)]


def registrar_envio(resposta, subscriber_id, tipo, db_mod=None):
    """Ponto único usado por `daily.py` e `trilha.py` depois de um envio real: extrai o id
    da resposta crua do provedor (conforme `config.WHATSAPP_BACKEND`) e grava contra quem
    recebeu o quê. NUNCA levanta -- rastreio é bônus, não pode derrubar um envio que já
    saiu (achado do Diego, 2026-09-25)."""
    if not subscriber_id:
        return
    if db_mod is None:
        import db as db_mod
    try:
        extrair = extrair_id_evolution if config.WHATSAPP_BACKEND == "evolution" else extrair_id_zapi
        msg_id = extrair(resposta if isinstance(resposta, str) else "")
        db_mod.registrar_mensagem_enviada(msg_id, subscriber_id, tipo)
    except Exception as e:
        print(f"[engajamento] não rastreei o envio ({tipo}): {e}", flush=True)


def processar(payload, db_mod=None):
    """Orquestra: escolhe o parser pelo backend configurado, aplica cada (id, status)
    encontrado. NUNCA levanta -- um webhook de status mal formado não pode derrubar a
    rota nem afetar o envio de verdade."""
    if db_mod is None:
        import db as db_mod
    try:
        decidir = decidir_status_evolution if config.WHATSAPP_BACKEND == "evolution" else decidir_status_zapi
        for msg_id, status in decidir(payload):
            db_mod.atualizar_status_mensagem(msg_id, status)
    except Exception as e:
        print(f"[engajamento] webhook de status não processado: {e}", flush=True)
