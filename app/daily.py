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
import agenda_plan

DIAS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
REFILL_MINIMO = 2          # reabastece quando a fila cai abaixo disso
JANELA_BUSCA_DIAS = 21     # janela da busca ao reabastecer
ESTOQUE_MINIMO = 10        # avisa o admin quando a reserva de resumos prontos cai abaixo disso


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


def _rotacao():
    cfg = _cfg()
    rot = cfg.get("rotacao_semana")
    return rot if rot else list(cfg["temas"].keys())


def materializar_agenda(dias=15):
    """Preenche os próximos `dias` dias úteis vazios na agenda (rotação + variedade,
    reserva pronta antes de fila fresca). Reabastece se o estoque não cobre o horizonte.
    Retorna quantos slots foram preenchidos. Fail-safe por slot (um slot ruim não aborta
    os outros); erros de configuração propagam."""
    import db
    db.init()
    envio = _dias_envio()
    inicio = datetime.now() + timedelta(days=1)
    datas = agenda_plan.dias_uteis_desde(inicio, dias, envio)
    if not datas:
        return 0

    fila_n = queue_store.tamanho()
    reserva_n = db.contar_reserva_pronto()
    if agenda_plan.precisa_reabastecer(fila_n, reserva_n, dias):
        try:
            print(f"[agenda] estoque {fila_n+reserva_n}<{dias} — reabastecendo", flush=True)
            reabastecer()
        except Exception as e:
            print(f"[agenda] reabastecer falhou (segue): {e}", flush=True)

    slots = db.agenda_listar(datas[0], datas[-1])
    ordenados = []
    for d in datas:
        s = slots.get(d)
        if s and (s.get("fixado") or s.get("tipo") in ("reserva", "fila", "pulado")):
            tema = None if s.get("tipo") == "pulado" else s.get("tema")
            ordenados.append((d, tema, True))
        else:
            ordenados.append((d, None, False))

    cands = []
    for r in db.listar_reserva(status="pronto"):
        cands.append({"tipo": "reserva", "tema": r.get("tema", ""), "titulo": r.get("titulo_pt", ""),
                      "ref_id": r["id"], "payload": None})
    for a in queue_store.listar():
        cands.append({"tipo": "fila", "tema": a.get("tema", ""), "titulo": a.get("titulo", ""),
                      "ref_id": None, "payload": a})

    plano = agenda_plan.planejar_agenda(ordenados, cands, _rotacao(), None)
    feitos = 0
    for data, cand in plano.items():
        try:
            if cand["tipo"] == "reserva":
                db.agenda_upsert(data, tipo="reserva", ref_id=cand["ref_id"], payload=None,
                                 tema=cand["tema"], titulo=cand["titulo"], fixado=0)
                db.marcar_reserva_agendado(cand["ref_id"])   # consome só APÓS gravar o slot
            else:
                payload = json.dumps(cand["payload"], ensure_ascii=False)
                db.agenda_upsert(data, tipo="fila", ref_id=None, payload=payload,
                                 tema=cand["tema"], titulo=cand["titulo"], fixado=0)
                queue_store.remover(cand["payload"])          # consome só APÓS gravar o slot
            feitos += 1
        except Exception as e:
            print(f"[agenda] falha ao materializar {data} (segue): {e}", flush=True)
    return feitos


def avisar_estoque_baixo():
    """Se a reserva (estoque de resumos prontos) cair abaixo de ESTOQUE_MINIMO, avisa
    o admin p/ rodar a curadoria e reabastecer. Fail-safe: nunca derruba o envio."""
    try:
        import db
        n = db.contar_reserva_pronto()
    except Exception as e:
        print(f"[estoque] falha ao contar reserva: {e}", flush=True)
        return
    if n < ESTOQUE_MINIMO:
        deliver.enviar_admin(f"⚠️ Estoque de estudos baixo: *{n}* prontos na reserva "
                             f"(mínimo {ESTOQUE_MINIMO}). Abra a *Curadoria* no painel e rode uma "
                             f"varredura pra reabastecer.")
    print(f"[estoque] reserva com {n} prontos (mínimo {ESTOQUE_MINIMO})", flush=True)


def _conteudo_do_rascunho(r):
    """Reconstrói o dict de conteúdo (titulo_pt/resumo/gancho/grafico) a partir de
    um rascunho salvo — usado pra gerar o áudio no preview e na regeração."""
    art = r.get("artigo", {})
    return {"titulo_pt": r.get("titulo_pt") or art.get("titulo", ""),
            "resumo": r.get("resumo", ""), "gancho": r.get("gancho", ""),
            "grafico": r.get("grafico")}


def enviar_audio_preview(r):
    """Gera o áudio do rascunho e envia aos curadores p/ ESCUTAREM antes de aprovar
    (preview das 18h e botão 'regerar áudio' do review). Fail-safe: nunca derruba o
    preparo. Retorna True se enviou a pelo menos um número."""
    if not config.audio_ligado():
        return False
    try:
        import audio as audiomod
        mp3 = audiomod.gerar_audio_do_estudo(r.get("artigo", {}), _conteudo_do_rascunho(r))
    except Exception as e:
        print(f"[preparar] áudio preview falhou (segue sem): {e}", flush=True)
        return False
    enviou = False
    for num in deliver.numeros_curadores():
        try:
            deliver.enviar_audio(num, mp3)
            enviou = True
        except Exception as e:
            print(f"[preparar] áudio preview p/ {num} falhou: {e}", flush=True)
    return enviou


def _preparar_da_reserva(reserva_id=None):
    """Monta o rascunho de amanhã a partir de um resumo PRONTO da reserva. Se
    `reserva_id` vier (slot da agenda), usa aquele; senão, o próximo da fila."""
    import db
    r_res = db.obter_reserva(reserva_id) if reserva_id else db.proximo_da_reserva()
    if not r_res:
        deliver.enviar_curador("📭 Sem estudo fresco E reserva vazia. Nada preparado p/ amanhã.")
        return None
    art = {"titulo": r_res.get("titulo_pt", ""), "tema": r_res.get("tema", ""),
           "fonte": r_res.get("fonte", ""), "doi": r_res.get("doi", ""),
           "url": r_res.get("url", ""), "data": r_res.get("data", "")}
    try:
        grafico = json.loads(r_res.get("grafico") or "null")
    except Exception:
        grafico = None
    c = {"titulo_pt": r_res.get("titulo_pt", ""), "resumo": r_res.get("resumo", ""),
         "gancho": r_res.get("gancho", ""), "grafico": grafico}
    alvo = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")   # dia do envio (amanhã) — casa com enviar_08h
    os.makedirs(config.drafts_dir(), exist_ok=True)
    preview = os.path.join(config.drafts_dir(), f"{alvo}-preview.pdf")
    pdfmod.gerar_pdf(pdfmod.montar_html(art, c, _tema_meta(art.get("tema", ""))), preview)
    r = draft_store.novo_rascunho(alvo, art, c["resumo"], preview)
    r["gancho"] = c["gancho"]
    r["grafico"] = c["grafico"]
    r["titulo_pt"] = c["titulo_pt"]
    r["reserva_id"] = r_res["id"]                 # p/ marcar 'enviado' após o envio
    draft_store.salvar(r)
    link = f"{config.PUBLIC_URL}/revisar/{r['review_token']}"
    origem = "SEU estudo" if r_res.get("origem") == "manual" else "reserva"
    extra = "\n🎧 O áudio do estudo chega logo abaixo pra você escutar." if config.audio_ligado() else ""
    deliver.enviar_curador(f"📋 Amanhã (da {origem}) · {art.get('tema', '')}:\n*{c['titulo_pt']}*\n{art.get('fonte', '')}\n"
                           f"Assinantes: {len(subscribers.ativos())}\n\n👉 Revisar/editar: {link}\n"
                           f"(se não mexer, envio automático às 08h){extra}")
    enviar_audio_preview(r)
    return r


def _preparar_de_artigo(art):
    """Gera conteúdo de um artigo cru (fila/fresco) e monta o rascunho de amanhã."""
    amanha = datetime.now() + timedelta(days=1)
    c = content.gerar_conteudo(art)
    alvo = amanha.strftime("%Y-%m-%d")
    os.makedirs(config.drafts_dir(), exist_ok=True)
    preview = os.path.join(config.drafts_dir(), f"{alvo}-preview.pdf")
    pdfmod.gerar_pdf(pdfmod.montar_html(art, c, _tema_meta(art.get("tema", ""))), preview)
    r = draft_store.novo_rascunho(alvo, art, c["resumo"], preview)
    r["gancho"] = c["gancho"]
    r["grafico"] = c["grafico"]
    r["titulo_pt"] = c["titulo_pt"]
    draft_store.salvar(r)
    link = f"{config.PUBLIC_URL}/revisar/{r['review_token']}"
    extra = "\n🎧 O áudio do estudo chega logo abaixo pra você escutar." if config.audio_ligado() else ""
    deliver.enviar_curador(f"📋 Amanhã · {art.get('tema','')}:\n*{c['titulo_pt']}*\n{art.get('fonte','')}\n"
                           f"Assinantes: {len(subscribers.ativos())}\n\n👉 Revisar/editar: {link}\n"
                           f"(se não mexer, envio automático às 08h){extra}")
    enviar_audio_preview(r)
    return r


def _preparar_fallback():
    """Comportamento original: fila fresca (gera conteúdo) e, se vazia, reserva."""
    if queue_store.tamanho() < REFILL_MINIMO:
        print(f"[reabastecer] +{reabastecer()} na fila", flush=True)
    art = queue_store.proximo()
    if not art:
        return _preparar_da_reserva()
    return _preparar_de_artigo(art)


def preparar_18h(amanha=None):
    amanha = amanha or (datetime.now() + timedelta(days=1))
    if not _e_dia_util(amanha):
        print("[preparar] amanhã não é dia de envio — pulo", flush=True)
        return None
    try:
        materializar_agenda()
    except Exception as e:
        print(f"[preparar] materializar falhou (segue no fallback): {e}", flush=True)
    import db
    alvo = amanha.strftime("%Y-%m-%d")
    fonte, ref = agenda_plan.classificar_slot(db.agenda_slot(alvo))
    if fonte == "pulado":
        print("[preparar] amanhã marcado como PULADO na agenda — não preparo", flush=True)
        return None
    if fonte == "reserva":
        r = _preparar_da_reserva(reserva_id=ref)
        if r:
            return r
        print("[preparar] item da reserva sumiu — fallback", flush=True)
    elif fonte == "fila":
        try:
            r = _preparar_de_artigo(json.loads(ref))
            if r:
                return r
        except Exception as e:
            print(f"[preparar] slot de fila inválido — fallback: {e}", flush=True)
    return _preparar_fallback()


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

    audio_bytes = None                          # áudio é o MESMO p/ todos: gera 1x
    if config.audio_ligado():
        try:
            import audio as audiomod
            audio_bytes = audiomod.gerar_audio_do_estudo(art, conteudo)
            print(f"[enviar] áudio gerado ({len(audio_bytes)} bytes)", flush=True)
        except Exception as e:
            print(f"[enviar] áudio falhou (segue sem): {e}", flush=True)

    # PDF ÚNICO: gera 1x (marca do curso, sem nome) e manda o MESMO arquivo a todos —
    # menos carga no servidor e menos ponto de falha. Fail-safe: se falhar, envia sem PDF.
    master_pdf = os.path.join(config.drafts_dir(), f"{hoje}-master.pdf")
    try:
        pdfmod.gerar_pdf(pdfmod.montar_html(art, conteudo, tmeta), master_pdf)
    except Exception as e:
        print(f"[enviar] PDF mestre falhou (segue sem PDF): {e}", flush=True)
        master_pdf = None

    def _envia(whatsapp, nome):
        import phone
        whatsapp = phone.normalizar(whatsapp)   # garante o 55 (registros antigos)
        link = f"{config.PUBLIC_URL}/entrar"  # portal protegido (login por código)
        msg = deliver.personalizar_rodape(f"🔬 *{titulo}*\n\n{r['resumo']}", nome, link)
        deliver.enviar_texto(whatsapp, msg)
        if master_pdf:                           # PDF (não derruba o resto se falhar)
            try:
                deliver.enviar_pdf(whatsapp, master_pdf, caption=titulo)  # PDF local -> base64 (Evolution)
            except Exception as e:
                print(f"[enviar] PDF p/ {whatsapp} falhou: {e}", flush=True)
        if audio_bytes:                          # + áudio narrado (não derruba o envio se falhar)
            try:
                deliver.enviar_audio(whatsapp, audio_bytes)
            except Exception as e:
                print(f"[enviar] áudio p/ {whatsapp} falhou: {e}", flush=True)

    res = deliver.distribuir(r, subscribers.ativos(), config.SEND_DELAY_SEC, _envia)
    r["status"] = "SENT"
    draft_store.salvar(r)
    queue_store.confirmar_envio(art)
    try:  # grava no arquivo do site (não derruba o envio se falhar)
        import db
        db.registrar_digest(art, conteudo, tmeta, data=hoje)
    except Exception as e:
        print(f"[enviar] falha ao registrar no arquivo: {e}", flush=True)
    if r.get("reserva_id"):        # veio da reserva/fila -> tira da fila (não reenvia)
        try:
            import db
            db.marcar_reserva_enviado(r["reserva_id"])
        except Exception as e:
            print(f"[enviar] marcar reserva enviado falhou: {e}", flush=True)
    rd.registrar([art["doi"]] if art.get("doi") else [])
    deliver.enviar_curador(f"✅ Enviado ({art.get('tema','')}): {res['ok']} assinantes"
                           + (f" · {len(res['falhas'])} falhas" if res["falhas"] else "")
                           + (" · ⚠️ SEM PDF (erro na geração)" if master_pdf is None else ""))
    avisar_estoque_baixo()      # depois de consumir, avisa se a reserva ficou abaixo do mínimo
