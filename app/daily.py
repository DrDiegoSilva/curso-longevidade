"""Orquestra os jobs diários: 18h prepara+avisa curador; 08h envia à lista.

Sem teste unitário próprio (orquestra I/O: rede + IA + WhatsApp). Validada por
smoke-test manual no deploy (com a lista-semente só no número do curador).
Imports de resumo_diario/buscar_estudos/pdf são LAZY (dentro das funções) para
não disparar efeitos de import (log/stdout do resumo_diario) na subida do serve.
"""
import os
import json
from datetime import datetime, timedelta
import config
import sources
import selection
import draft_store
import subscribers
import deliver


def _hoje_iso():
    return datetime.now().strftime("%Y-%m-%d")


def _tema_do_dia():
    cfg = json.load(open(os.path.join(os.path.dirname(__file__), "temas_config.json"), encoding="utf-8"))
    dias = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
    plano = cfg["calendario"][dias[datetime.now().weekday()]]
    return plano["tema"]


def preparar_18h():
    import resumo_diario as rd
    import buscar_estudos as be
    import pdf as pdfmod
    tema = _tema_do_dia()
    query, _exc = be.carregar_tema(tema)
    ate = datetime.now()
    desde = ate - timedelta(days=14)
    arts = sources.search_all(query, desde.strftime("%Y-%m-%d"), ate.strftime("%Y-%m-%d"))
    art = selection.escolher_do_dia(arts, rd.dois_enviados())
    if not art:
        rd.enviar_zap(f"📭 Sem artigo forte hoje ({tema}). Nada preparado — me chama se quiser forçar.")
        return None
    resumo = rd.gerar_texto_do_artigo(art)
    hoje = _hoje_iso()
    os.makedirs(config.drafts_dir(), exist_ok=True)
    pdf_path = os.path.join(config.drafts_dir(), f"{hoje}.pdf")
    pdfmod.gerar_pdf(pdfmod.montar_html(art, resumo, "Dr. Diego (revisão)"), pdf_path)
    r = draft_store.novo_rascunho(hoje, art, resumo, pdf_path)
    draft_store.salvar(r)
    link = f"{config.PUBLIC_URL}/revisar/{r['review_token']}"
    rd.enviar_zap(f"📋 Resumo de AMANHÃ pronto:\n*{art['titulo']}*\nFonte: {art.get('fonte','')}\n"
                  f"Assinantes: {len(subscribers.ativos())}\n\n👉 Revisar/editar: {link}\n"
                  f"(se não mexer, envio automático às 08h)")
    return r


def enviar_08h():
    import resumo_diario as rd
    tema_hoje = _hoje_iso()
    r = draft_store.carregar(tema_hoje)
    if not r or not draft_store.pode_enviar(r["status"]):
        rd.enviar_zap(f"⏭️ Nada enviado hoje ({'sem rascunho' if not r else r['status']}).")
        return
    art, resumo = r["artigo"], r["resumo"]
    pdf_url = f"{config.PUBLIC_URL}/pdf/{tema_hoje}"  # servido pela Task 9

    def _envia(whatsapp, nome):
        link = f"{config.PUBLIC_URL}/minha/{whatsapp}"  # placeholder Fase 1 (link real vem na Fase 2)
        msg = deliver.personalizar_rodape(f"🔬 *{art['titulo']}*\n\n{resumo}", nome, link)
        deliver.enviar_texto(whatsapp, msg)
        deliver.enviar_pdf(whatsapp, pdf_url, caption=art["titulo"])

    res = deliver.distribuir(r, subscribers.ativos(), config.SEND_DELAY_SEC, _envia)
    r["status"] = "SENT"
    draft_store.salvar(r)
    rd.registrar([art["doi"]] if art.get("doi") else [])
    rd.enviar_zap(f"✅ Enviado: {res['ok']} assinantes"
                  + (f" · {len(res['falhas'])} falhas" if res["falhas"] else ""))
