"""Orquestra os jobs diários (modelo fila + variedade, seg-sex, 1/dia).

- preparar_18h(): se AMANHÃ for dia útil, reabastece a fila se preciso, tira o
  próximo artigo, gera resumo + gancho + gráfico + PDF de prévia, salva o
  rascunho e avisa o curador com o link de revisão. Silêncio = envia às 08h.
- enviar_08h(): se HOJE for dia útil e houver rascunho não vetado, gera um PDF
  PERSONALIZADO por assinante (nome na marca d'água) e envia.

Sem teste unitário próprio (orquestra rede + IA + WhatsApp); as partes puras
(fila, triagem, conteúdo, pdf) são testadas nos seus módulos. Imports de
resumo_diario são lazy (efeitos de import: log/stdout).
"""
import os
import json
from datetime import datetime, timedelta
import config
import sources
import triage
import content
import queue_store
import draft_store
import subscribers
import deliver
import pdf as pdfmod
import buscar_estudos as be

DIAS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
REFILL_MINIMO = 2          # reabastece quando a fila cai abaixo disso
JANELA_BUSCA_DIAS = 21     # janela da busca ao reabastecer


def _cfg():
    return json.load(open(os.path.join(os.path.dirname(__file__), "temas_config.json"), encoding="utf-8"))


def _dias_envio():
    return set(_cfg().get("dias_envio", ["segunda", "terca", "quarta", "quinta", "sexta"]))


def _e_dia_util(dt):
    return DIAS[dt.weekday()] in _dias_envio()


def _tema_meta(nome):
    return _cfg()["temas"].get(nome, {"rotulo": nome, "cor": "#14332a", "emoji": ""})


def _hoje_iso():
    return datetime.now().strftime("%Y-%m-%d")


def reabastecer():
    """Busca a semana em TODOS os temas, tria por IA e põe os ENTRA na fila.
    Retorna quantos artigos entraram."""
    cfg = _cfg()
    ate = datetime.now()
    desde = ate - timedelta(days=JANELA_BUSCA_DIAS)
    total = 0
    for nome, meta in cfg["temas"].items():
        try:
            arts = sources.search_all(meta.get("query", ""), desde.strftime("%Y-%m-%d"), ate.strftime("%Y-%m-%d"))
            bons = triage.triar(arts, nome)
            total += queue_store.adicionar(bons)
        except Exception as e:
            print(f"[reabastecer] {nome} falhou: {e}", flush=True)
    return total


def preparar_18h():
    amanha = datetime.now() + timedelta(days=1)
    if not _e_dia_util(amanha):
        print("[preparar] amanhã não é dia de envio — pulo", flush=True)
        return None
    if queue_store.tamanho() < REFILL_MINIMO:
        print(f"[reabastecer] +{reabastecer()} na fila", flush=True)
    art = queue_store.proximo()
    if not art:
        deliver.enviar_curador("📭 Sem artigo forte para amanhã (fila vazia). Nada preparado — me chama se quiser forçar.")
        return None
    c = content.gerar_conteudo(art)
    hoje = _hoje_iso()
    os.makedirs(config.drafts_dir(), exist_ok=True)
    preview = os.path.join(config.drafts_dir(), f"{hoje}-preview.pdf")
    pdfmod.gerar_pdf(pdfmod.montar_html(art, c, "Dr. Diego (revisão)", _tema_meta(art.get("tema", ""))), preview)
    r = draft_store.novo_rascunho(hoje, art, c["resumo"], preview)
    r["gancho"] = c["gancho"]
    r["grafico"] = c["grafico"]
    r["titulo_pt"] = c["titulo_pt"]
    draft_store.salvar(r)
    link = f"{config.PUBLIC_URL}/revisar/{r['review_token']}"
    deliver.enviar_curador(f"📋 Amanhã · {art.get('tema','')}:\n*{c['titulo_pt']}*\n{art.get('fonte','')}\n"
                           f"Assinantes: {len(subscribers.ativos())}\n\n👉 Revisar/editar: {link}\n"
                           f"(se não mexer, envio automático às 08h)")
    return r


def rotina_08h():
    """Tarefa das 08h: avisa pré-renovação (todo dia) + envia o digest (dias úteis)."""
    try:
        import billing_notices
        n = billing_notices.avisar_pre_renovacao()
        if n:
            print(f"[pre-renovacao] {n} aviso(s) enviado(s)", flush=True)
    except Exception as e:
        print(f"[pre-renovacao] erro: {e}", flush=True)
    enviar_08h()


def enviar_08h():
    import resumo_diario as rd
    if not _e_dia_util(datetime.now()):
        print("[enviar] hoje não é dia de envio — pulo", flush=True)
        return
    hoje = _hoje_iso()
    r = draft_store.carregar(hoje)
    if not r or not draft_store.pode_enviar(r["status"]):
        deliver.enviar_curador(f"⏭️ Nada enviado hoje ({'sem rascunho' if not r else r['status']}).")
        return
    art = r["artigo"]
    titulo = r.get("titulo_pt") or art.get("titulo", "")
    conteudo = {"titulo_pt": titulo, "resumo": r["resumo"], "gancho": r.get("gancho", ""), "grafico": r.get("grafico")}
    tmeta = _tema_meta(art.get("tema", ""))

    def _envia(whatsapp, nome):
        ppath = os.path.join(config.drafts_dir(), f"{hoje}-{whatsapp}.pdf")
        pdfmod.gerar_pdf(pdfmod.montar_html(art, conteudo, nome or "Assinante", tmeta), ppath)
        link = f"{config.PUBLIC_URL}/entrar"  # portal protegido (login por código)
        msg = deliver.personalizar_rodape(f"🔬 *{titulo}*\n\n{r['resumo']}", nome, link)
        deliver.enviar_texto(whatsapp, msg)
        deliver.enviar_pdf(whatsapp, ppath, caption=titulo)  # PDF local -> base64 (Evolution)

    res = deliver.distribuir(r, subscribers.ativos(), config.SEND_DELAY_SEC, _envia)
    r["status"] = "SENT"
    draft_store.salvar(r)
    queue_store.confirmar_envio(art)
    try:  # grava no arquivo do site (não derruba o envio se falhar)
        import db
        db.registrar_digest(art, conteudo, tmeta, data=hoje)
    except Exception as e:
        print(f"[enviar] falha ao registrar no arquivo: {e}", flush=True)
    rd.registrar([art["doi"]] if art.get("doi") else [])
    deliver.enviar_curador(f"✅ Enviado ({art.get('tema','')}): {res['ok']} assinantes"
                           + (f" · {len(res['falhas'])} falhas" if res["falhas"] else ""))
