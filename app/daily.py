"""Orquestra os jobs diários (modelo fila + variedade, seg-sex, 1/dia).

- preparar_18h(): se AMANHÃ for dia útil, lê o slot da agenda de amanhã
  (reserva/fila/pulado) e monta o rascunho a partir dele — com fallback pro
  fluxo antigo (fila fresca -> reserva) em caso de slot vazio ou qualquer erro.
  Gera resumo + gancho + gráfico + PDF de prévia, salva o rascunho e avisa o
  curador com o link de revisão. Silêncio = envia às 08h.
- enviar_slot(slot): se HOJE for dia útil e houver rascunho não vetado, envia o
  estudo do dia só pros assinantes daquele slot (idempotente por dia/slot;
  áudio/PDF/finalização do dia rodam 1x, no 1º slot que enviar).

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
    with open(os.path.join(os.path.dirname(__file__), "temas_config.json"), encoding="utf-8") as f:
        return json.load(f)


def _dias_envio():
    # admin escolhe os dias em /admin/envio (db.settings 'dias_envio', CSV). None = nunca setado
    # -> usa o temas_config.json; string vazia = salvou sem nenhum dia -> não envia.
    try:
        import db
        salvo = db.get_config("dias_envio", None)
    except Exception:
        salvo = None
    if salvo is not None:
        return set(d.strip() for d in salvo.split(",") if d.strip())
    return set(_cfg().get("dias_envio", ["segunda", "terca", "quarta", "quinta", "sexta"]))


def _e_dia_util(dt):
    return DIAS[dt.weekday()] in _dias_envio()


def _tema_meta(nome):
    return _cfg()["temas"].get(nome, {"rotulo": nome, "cor": "#14332a", "emoji": ""})


def _hoje_iso():
    return datetime.now().strftime("%Y-%m-%d")


def _e_fresco(data_pub, ref=None):
    """True se o paper foi publicado nos últimos config.FRESCO_DIAS dias (medido em `ref`,
    default hoje). Tolera data vazia/parcial/inválida (retorna False). Publicação futura conta."""
    from datetime import date
    ref = ref or date.today()
    try:
        pub = date.fromisoformat((data_pub or "")[:10])
    except (ValueError, TypeError):
        return False
    idade = (ref - pub).days
    return idade <= config.FRESCO_DIAS       # idade negativa (futuro) também é fresco


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


def _temas_por_dia():
    """Mapa dia-da-semana -> [temas] da config. Vazio => sem preferência de tema
    (a escolha cai para fresco > camada > nota, e nenhum dia fica vazio)."""
    return _cfg().get("temas_por_dia") or {}


def materializar_agenda(n_semanas=4, datas=None):
    """Preenche os dias úteis FUTUROS (>= amanhã) das próximas `n_semanas` semanas
    seg–sex na agenda (tema do dia + variedade, reserva pronta antes de fila fresca).
    `datas` pode ser passado (lista YYYY-MM-DD) p/ testar com uma janela fixa.
    Reabastece se o estoque não cobre o horizonte. Retorna quantos slots preencheu.
    Fail-safe por slot (um slot ruim não aborta os outros); erros de config propagam."""
    import db
    db.init()
    envio = _dias_envio()
    if datas is None:
        amanha_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        datas = [d for d in agenda_plan.semanas_do_mes(datetime.now(), envio, n_semanas)
                 if d >= amanha_str]
    if not datas:
        return 0
    horizonte = len(datas)

    # Reconcilia estoque <-> agenda (self-healing p/ consume meio-falho):
    #  - ref_ids/chaves = itens já presos a algum slot;
    #  - devolve a 'pronto' qualquer reserva 'agendado' que NENHUM slot referencia (órfão);
    #  - mais abaixo, exclui dos candidatos o que já está referenciado (evita double-book).
    ref_ids = db.agenda_ref_ids("reserva")
    for r in db.listar_reserva(status="agendado"):
        if r["id"] not in ref_ids:
            db.marcar_reserva_pronto(r["id"])
    cand_ref_ids = db.agenda_ref_ids("candidato")
    for c in db.listar_candidatos(status="agendado", tipo="varredura"):
        if c["id"] not in cand_ref_ids:
            db.marcar_candidato_pronto(c["id"])
    classico_ref_ids = db.agenda_ref_ids("classico")   # p/ não repetir o mesmo clássico no horizonte
    fila_chaves = set()
    for p in db.agenda_payloads_fila():
        try:
            fila_chaves.add(queue_store._chave(json.loads(p)))
        except Exception:
            pass

    fila_n = queue_store.tamanho()
    reserva_n = db.contar_reserva_pronto()
    # Estoque TOTAL (não só reserva+fila) — senão o reabastecer (rede) dispara mesmo com o
    # pool cheio de candidatos crus/clássicos elegíveis, que também cobrem o horizonte.
    cand_n = len(db.listar_candidatos(status="novo", tipo="varredura"))
    classico_n = len(db.listar_classicos(elegiveis=True))
    estoque_n = reserva_n + cand_n + classico_n
    if agenda_plan.precisa_reabastecer(fila_n, estoque_n, horizonte):
        try:
            print(f"[agenda] estoque {fila_n+estoque_n}<{horizonte} — reabastecendo", flush=True)
            reabastecer()
        except Exception as e:
            print(f"[agenda] reabastecer falhou (segue): {e}", flush=True)

    slots = db.agenda_listar(datas[0], datas[-1])
    ordenados = []
    for d in datas:
        s = slots.get(d)
        if s and (s.get("fixado") or s.get("tipo") in ("reserva", "fila", "pulado", "candidato", "classico")):
            tema = None if s.get("tipo") == "pulado" else s.get("tema")
            ordenados.append((d, tema, True))
        else:
            ordenados.append((d, None, False))

    cands = []
    for r in db.listar_reserva(status="pronto"):
        if r["id"] in ref_ids:          # já preso a um slot (consume meio-falho) -> não re-agenda
            continue
        cands.append({"tipo": "reserva", "tema": r.get("tema", ""), "titulo": r.get("titulo_pt", ""),
                      "ref_id": r["id"], "payload": None,
                      "fresco": _e_fresco(r.get("data", "")), "classico": False,
                      "score": float(r.get("score", 0) or 0)})
    for c in db.listar_candidatos(status="novo", tipo="varredura"):
        if c["id"] in cand_ref_ids:      # já preso a um slot -> não re-agenda
            continue
        cands.append({"tipo": "candidato", "tema": c.get("tema", ""), "titulo": c.get("titulo", ""),
                      "ref_id": c["id"], "payload": None,
                      "fresco": _e_fresco(c.get("data", "")), "classico": False,
                      "score": float(c.get("score", 0) or 0)})
    for cl in db.listar_classicos(elegiveis=True):
        if cl["id"] in classico_ref_ids:
            continue
        cands.append({"tipo": "classico", "tema": cl.get("tema", ""), "titulo": cl.get("titulo_pt", ""),
                      "ref_id": cl["id"], "payload": None,
                      "fresco": False, "classico": True,
                      "score": float(cl.get("citacoes", 0) or 0)})
    for a in queue_store.listar():
        if queue_store._chave(a) in fila_chaves:   # já preso a um slot de fila
            continue
        cands.append({"tipo": "fila", "tema": a.get("tema", ""), "titulo": a.get("titulo", ""),
                      "ref_id": None, "payload": a})

    plano = agenda_plan.planejar_agenda(ordenados, cands, _temas_por_dia(), None)
    feitos = 0
    for data, cand in plano.items():
        try:
            if cand["tipo"] == "reserva":
                db.agenda_upsert(data, tipo="reserva", ref_id=cand["ref_id"], payload=None,
                                 tema=cand["tema"], titulo=cand["titulo"], fixado=0)
                db.marcar_reserva_agendado(cand["ref_id"])   # consome só APÓS gravar o slot
            elif cand["tipo"] == "candidato":
                db.agenda_upsert(data, tipo="candidato", ref_id=cand["ref_id"], payload=None,
                                 tema=cand["tema"], titulo=cand["titulo"], fixado=0)
                db.marcar_candidato_agendado(cand["ref_id"])   # consome só APÓS gravar o slot
            elif cand["tipo"] == "classico":
                db.agenda_upsert(data, tipo="classico", ref_id=cand["ref_id"], payload=None,
                                 tema=cand["tema"], titulo=cand["titulo"], fixado=0)
                # clássico NÃO é consumido (reusável); o ref na agenda já evita repetir no horizonte
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
    alvo = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")   # dia do envio (amanhã) — casa com enviar_slot
    os.makedirs(config.drafts_dir(), exist_ok=True)
    preview = os.path.join(config.drafts_dir(), f"{alvo}-preview.pdf")
    try:                                     # fail-safe: PDF nunca pode derrubar a preparação/revisão
        pdfmod.gerar_pdf(pdfmod.montar_html(art, c, _tema_meta(art.get("tema", ""))), preview)
    except Exception as e:
        print(f"[preparar] PDF preview falhou (segue sem PDF; /pdf regenera sob demanda): {e}", flush=True)
        preview = None
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


def reenviar_pdf_do_dia(data=None):
    """Regenera o PDF do digest ENVIADO em `data` (hoje por padrão) e manda a TODOS
    os assinantes ativos. Uso pontual: recuperar um dia que saiu sem PDF."""
    import db, phone, time
    hoje = data or datetime.now().strftime("%Y-%m-%d")
    dg = db.digest_do_dia(hoje)
    if not dg:
        return {"ok": False, "msg": f"Sem digest registrado em {hoje}."}
    try:
        grafico = json.loads(dg.get("grafico") or "null")
    except Exception:
        grafico = None
    art = {"tema": dg.get("tema", ""), "titulo": dg.get("titulo_pt", ""),
           "fonte": dg.get("fonte", ""), "doi": dg.get("doi", ""),
           "url": dg.get("url", ""), "data": hoje}
    conteudo = {"titulo_pt": dg.get("titulo_pt", ""), "resumo": dg.get("resumo", ""),
                "gancho": dg.get("gancho", ""), "grafico": grafico}
    tmeta = _tema_meta(dg.get("tema", ""))
    os.makedirs(config.drafts_dir(), exist_ok=True)
    master_pdf = os.path.join(config.drafts_dir(), f"{hoje}-master-reenvio.pdf")
    pdfmod.gerar_pdf(pdfmod.montar_html(art, conteudo, tmeta), master_pdf)   # retry cuida do crash
    ativos = subscribers.ativos()
    ok = 0
    for s in ativos:
        w = phone.normalizar(s.get("whatsapp", ""))
        if not w:
            continue
        try:
            deliver.enviar_pdf(w, master_pdf, caption=dg.get("titulo_pt", ""))
            ok += 1
            time.sleep(config.SEND_DELAY_SEC)
        except Exception as e:
            print(f"[reenvio] PDF p/ {w} falhou: {e}", flush=True)
    return {"ok": True, "msg": f"PDF de {hoje} ({dg.get('tema','')}) reenviado a {ok}/{len(ativos)} assinantes."}


def _preparar_de_artigo(art):
    """Gera conteúdo de um artigo cru (fila/fresco) e monta o rascunho de amanhã."""
    amanha = datetime.now() + timedelta(days=1)
    c = content.gerar_conteudo(art)
    alvo = amanha.strftime("%Y-%m-%d")
    os.makedirs(config.drafts_dir(), exist_ok=True)
    preview = os.path.join(config.drafts_dir(), f"{alvo}-preview.pdf")
    try:                                     # fail-safe: PDF nunca pode derrubar a preparação/revisão
        pdfmod.gerar_pdf(pdfmod.montar_html(art, c, _tema_meta(art.get("tema", ""))), preview)
    except Exception as e:
        print(f"[preparar] PDF preview falhou (segue sem PDF; /pdf regenera sob demanda): {e}", flush=True)
        preview = None
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


def _preparar_de_candidato(cand_id):
    """Monta o rascunho de amanhã de um CANDIDATO cru (resumo JIT). Mira _preparar_de_artigo."""
    import db
    c = next((x for x in db.listar_candidatos() if x["id"] == cand_id), None)
    if not c:
        return None
    art = {"titulo": c.get("titulo", ""), "tema": c.get("tema", ""), "fonte": c.get("fonte", ""),
           "doi": c.get("doi", ""), "url": c.get("url", ""), "data": c.get("data", ""),
           "resumo": c.get("abstract", "")}
    r = _preparar_de_artigo(art)          # gera conteúdo, cria draft, manda preview + áudio
    if r:
        r["candidato_id"] = cand_id
        draft_store.salvar(r)
    return r


def _preparar_de_classico(classico_id):
    """Monta o rascunho de amanhã de um CLÁSSICO já bancado (usa o resumo pronto, sem regenerar).
    Mira _preparar_da_reserva."""
    import db
    cl = db.obter_classico(classico_id)
    if not cl:
        return None
    art = {"titulo": cl.get("titulo_pt", ""), "tema": cl.get("tema", ""), "fonte": cl.get("fonte", ""),
           "doi": cl.get("doi", ""), "url": cl.get("url", ""), "data": cl.get("data", "")}
    try:
        grafico = json.loads(cl.get("grafico") or "null")
    except Exception:
        grafico = None
    c = {"titulo_pt": cl.get("titulo_pt", ""), "resumo": cl.get("resumo", ""),
         "gancho": cl.get("gancho", ""), "grafico": grafico}
    alvo = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    os.makedirs(config.drafts_dir(), exist_ok=True)
    preview = os.path.join(config.drafts_dir(), f"{alvo}-preview.pdf")
    try:
        pdfmod.gerar_pdf(pdfmod.montar_html(art, c, _tema_meta(art.get("tema", ""))), preview)
    except Exception as e:
        print(f"[preparar] PDF preview (clássico) falhou (segue sem): {e}", flush=True)
        preview = None
    r = draft_store.novo_rascunho(alvo, art, c["resumo"], preview)
    r["gancho"] = c["gancho"]; r["grafico"] = c["grafico"]; r["titulo_pt"] = c["titulo_pt"]
    r["classico_id"] = classico_id
    draft_store.salvar(r)
    link = f"{config.PUBLIC_URL}/revisar/{r['review_token']}"
    extra = "\n🎧 O áudio do estudo chega logo abaixo pra você escutar." if config.audio_ligado() else ""
    deliver.enviar_curador(f"📋 Amanhã (clássico) · {art.get('tema','')}:\n*{c['titulo_pt']}*\n{art.get('fonte','')}\n"
                           f"Assinantes: {len(subscribers.ativos())}\n\n👉 Revisar/editar: {link}\n"
                           f"(se não mexer, envio automático às 08h){extra}")
    enviar_audio_preview(r)
    return r


ALTERNATIVAS_MAX = 20


def montar_alternativas(r):
    """Lista de estudos p/ trocar o de amanhã: reserva (uploads no topo) + candidatos
    (tema de amanhã primeiro). Exclui o estudo atual. Normalizado e cortado em ALTERNATIVAS_MAX."""
    import db
    atual_res = r.get("reserva_id")
    atual_cand = r.get("candidato_id")
    tema_amanha = (r.get("artigo") or {}).get("tema", "")
    res_rows = [x for x in db.listar_reserva("pronto") if x["id"] != atual_res]
    res_rows.sort(key=lambda x: (x.get("prioridade", 0) or 0, x.get("score", 0) or 0), reverse=True)
    cand_rows = [x for x in db.listar_candidatos("novo") if x["id"] != atual_cand]
    cand_rows.sort(key=lambda x: (1 if x.get("tema") == tema_amanha else 0, x.get("score", 0) or 0), reverse=True)
    alts = (
        [{"tipo": "reserva", "id": x["id"], "titulo": x.get("titulo_pt", ""),
          "fonte": x.get("fonte", ""), "tema": x.get("tema", ""), "score": x.get("score", 0) or 0}
         for x in res_rows]
        + [{"tipo": "candidato", "id": x["id"], "titulo": x.get("titulo", ""),
            "fonte": x.get("fonte", ""), "tema": x.get("tema", ""), "score": x.get("score", 0) or 0}
           for x in cand_rows]
    )
    return alts[:ALTERNATIVAS_MAX]


def alternativa_valida(r, tipo, cid):
    """True se (tipo,cid) está entre as alternativas atuais (não confia no form)."""
    return any(a["tipo"] == tipo and str(a["id"]) == str(cid) for a in montar_alternativas(r))


def trocar_estudo_amanha(token, tipo, cid):
    """Refaz o rascunho de amanhã a partir do estudo escolhido (roda em thread).
    Grava o slot de amanhã no escolhido (consome, igual ao materialize) e devolve o
    estudo atual ao pool. Fail-safe: exceção no preparo -> avisa o curador, o antigo fica."""
    import db
    r = draft_store.por_token(token)
    if not r:
        deliver.enviar_curador("⚠️ Não consegui trocar o estudo (rascunho não encontrado).")
        return None
    try:
        if tipo == "reserva":
            novo = _preparar_da_reserva(reserva_id=cid)
        elif tipo == "candidato":
            novo = _preparar_de_candidato(cid)
        else:
            novo = None
    except Exception as e:
        print(f"[trocar] preparo do escolhido falhou: {e}", flush=True)
        novo = None
    if not novo:
        deliver.enviar_curador("⚠️ Não consegui trocar o estudo; o anterior segue valendo.")
        return None
    try:            # grava o slot de amanhã no escolhido, consome e devolve o atual ao pool (igual ao materialize; guarda p/ observabilidade — roda em thread)
        art = novo.get("artigo", {})
        tema = art.get("tema", "")
        titulo = novo.get("titulo_pt") or art.get("titulo", "")
        data = novo.get("data")
        if tipo == "reserva":
            db.agenda_upsert(data, tipo="reserva", ref_id=cid, payload=None, tema=tema, titulo=titulo, fixado=0)
            db.marcar_reserva_agendado(cid)
        else:
            db.agenda_upsert(data, tipo="candidato", ref_id=cid, payload=None, tema=tema, titulo=titulo, fixado=0)
            db.marcar_candidato_agendado(cid)
        if r.get("candidato_id"):                # devolve o estudo ATUAL ao pool (o slot já aponta pro novo)
            db.marcar_candidato_pronto(r["candidato_id"])
        elif r.get("reserva_id"):
            db.marcar_reserva_pronto(r["reserva_id"])
    except Exception as e:                       # não pode crashar a thread nem falhar em silêncio
        print(f"[trocar] atualizar agenda/pool falhou: {e}", flush=True)
        deliver.enviar_curador("⚠️ Troquei o estudo de amanhã, mas não consegui atualizar a agenda — confira a /agenda pra não repetir o estudo.")
    return novo


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
    try:
        fonte, ref = agenda_plan.classificar_slot(db.agenda_slot(alvo))
        if fonte == "pulado":
            print("[preparar] amanhã marcado como PULADO na agenda — não preparo", flush=True)
            return None
        if fonte == "reserva":
            r = _preparar_da_reserva(reserva_id=ref)
            if r:
                return r
            print("[preparar] item da reserva sumiu — fallback", flush=True)
        elif fonte == "candidato":
            r = _preparar_de_candidato(ref)
            if r:
                return r
            print("[preparar] candidato sumiu — fallback", flush=True)
        elif fonte == "classico":
            r = _preparar_de_classico(ref)
            if r:
                return r
            print("[preparar] clássico sumiu — fallback", flush=True)
        elif fonte == "fila":
            r = _preparar_de_artigo(json.loads(ref))
            if r:
                return r
    except Exception as e:
        print(f"[preparar] erro ao preparar do slot ({e}) — fallback", flush=True)
    return _preparar_fallback()


def rotina_08h():
    """Tarefa das 08h: avisa pré-renovação (todo dia) + dispara a régua + envia o slot das 08h."""
    try:
        import billing_notices
        n = billing_notices.avisar_pre_renovacao()
        if n:
            print(f"[pre-renovacao] {n} aviso(s) enviado(s)", flush=True)
    except Exception as e:
        print(f"[pre-renovacao] erro: {e}", flush=True)
    try:
        import regua
        n = regua.disparar()
        if n:
            print(f"[regua] {n} mensagem(ns) enviada(s)", flush=True)
    except Exception as e:
        print(f"[regua] erro: {e}", flush=True)
    enviar_slot("08h")


def varredura_semanal(hoje=None, rodar_fn=None):
    """Roda a varredura geral 1x por semana ISO, só no DIA_VARREDURA (domingo de manhã).
    Idempotente via db.registrar_envio_slot(chave-semana, 'varredura'). Retorna True se rodou."""
    from datetime import date
    hoje = hoje or date.today()
    if DIAS[hoje.weekday()] != config.DIA_VARREDURA:
        return False
    import db
    ano, semana, _ = hoje.isocalendar()
    chave = f"{ano}-W{semana:02d}"
    if not db.registrar_envio_slot(chave, "varredura"):   # já rodou esta semana
        return False
    rodar_fn = rodar_fn or (lambda: __import__("curadoria").rodar_varredura())
    try:
        n = rodar_fn()
        print(f"[varredura-semanal] {chave}: {n} novos candidatos", flush=True)
    except Exception as e:
        print(f"[varredura-semanal] erro: {e}", flush=True)
    return True


def gerar_selecionados_noturno(gerar_fn=None):
    """Gera os resumos dos candidatos que o Diego priorizou na curadoria.
    Roda todo dia às config.HORA_CURADORIA — DEPOIS do preparo das 18h, que tem
    prioridade (ele é quem dispara a revisão do estudo de amanhã).
    Idempotente: gerar_selecionados marca 'resumido' e não repete. gerar_fn injetável."""
    gerar_fn = gerar_fn or (lambda: __import__("curadoria").gerar_selecionados())
    try:
        n = gerar_fn()
        print(f"[curadoria-noturna] {n} resumo(s) gerado(s)", flush=True)
        return n
    except Exception as e:
        print(f"[curadoria-noturna] erro: {e}", flush=True)
        return 0


def montar_texto_resumo(titulo, resumo, tmeta, fresco=False):
    """Texto do WhatsApp p/ o assinante: selo de recência (se fresco) + badge do tema
    (emoji + rótulo) + título + resumo."""
    rot = (tmeta or {}).get("rotulo", "")
    emoji = (tmeta or {}).get("emoji", "")
    selo = "🆕 *Estudo recente*\n" if fresco else ""
    hdr = f"{emoji} *{rot}*\n".lstrip() if rot else ""
    return f"{selo}{hdr}🔬 *{titulo}*\n\n{resumo}"


def _audio_master(hoje, art, conteudo):
    """Áudio do dia (o MESMO p/ todos). Gera 1x e cacheia em arquivo; regenera se sumir."""
    if not config.audio_ligado():
        return None
    caminho = os.path.join(config.drafts_dir(), f"{hoje}-master.mp3")
    if os.path.exists(caminho):
        try:
            return open(caminho, "rb").read()
        except Exception:
            pass
    try:
        import audio as audiomod
        b = audiomod.gerar_audio_do_estudo(art, conteudo)
        try:
            os.makedirs(config.drafts_dir(), exist_ok=True)
            open(caminho, "wb").write(b)
        except Exception:
            pass
        return b
    except Exception as e:
        print(f"[enviar] áudio falhou (segue sem): {e}", flush=True)
        return None


def _pdf_master(hoje, art, conteudo, tmeta):
    """PDF único do dia (marca do curso, sem nome). Gera 1x em arquivo; reusa se existir."""
    caminho = os.path.join(config.drafts_dir(), f"{hoje}-master.pdf")
    if os.path.exists(caminho):
        return caminho
    try:
        os.makedirs(config.drafts_dir(), exist_ok=True)
        pdfmod.gerar_pdf(pdfmod.montar_html(art, conteudo, tmeta), caminho)
        return caminho
    except Exception as e:
        print(f"[enviar] PDF mestre falhou (segue sem PDF): {e}", flush=True)
        return None


def _finalizar_dia(hoje, r, art, conteudo, tmeta):
    """Fecha o dia UMA vez (1º slot que enviar): status SENT, confirma fila, registra no
    arquivo, tira da reserva, marca DOI. Guardado por marcador em envios_slot."""
    import db
    if not db.registrar_envio_slot(hoje, "_finalizado"):
        return
    import resumo_diario as rd
    r["status"] = "SENT"
    draft_store.salvar(r)
    queue_store.confirmar_envio(art)
    try:
        db.registrar_digest(art, conteudo, tmeta, data=hoje)
    except Exception as e:
        print(f"[enviar] falha ao registrar no arquivo: {e}", flush=True)
    if r.get("reserva_id"):
        try:
            db.marcar_reserva_enviado(r["reserva_id"])
        except Exception as e:
            print(f"[enviar] marcar reserva enviado falhou: {e}", flush=True)
    if r.get("candidato_id"):
        try:
            db.marcar_candidatos([r["candidato_id"]], "resumido")
        except Exception as e:
            print(f"[enviar] marcar candidato falhou: {e}", flush=True)
    if r.get("classico_id"):
        try:
            db.marcar_classico_enviado(r["classico_id"], hoje)
        except Exception as e:
            print(f"[enviar] marcar clássico falhou: {e}", flush=True)
    rd.registrar([art["doi"]] if art.get("doi") else [])
    try:
        avisar_estoque_baixo()   # avisa o curador se a reserva ficou abaixo do mínimo
    except Exception as e:
        print(f"[enviar] avisar_estoque_baixo falhou: {e}", flush=True)


def _montar_ctx(hoje, r):
    """ctx de envio (título/conteúdo/tema + PDF/áudio master cacheados do dia) a partir de um
    rascunho aprovado r. Puro — assume r válido."""
    art = r["artigo"]
    titulo = r.get("titulo_pt") or art.get("titulo", "")
    conteudo = {"titulo_pt": titulo, "resumo": r["resumo"], "gancho": r.get("gancho", ""), "grafico": r.get("grafico")}
    tmeta = _tema_meta(art.get("tema", ""))
    return {"r": r, "art": art, "titulo": titulo, "conteudo": conteudo, "tmeta": tmeta,
            "fresco": _e_fresco(art.get("data", "")),
            "audio_bytes": _audio_master(hoje, art, conteudo),
            "master_pdf": _pdf_master(hoje, art, conteudo, tmeta)}


def _ctx_do_dia(hoje):
    """ctx pronto p/ enviar, ou None se não é dia útil de envio OU não há rascunho aprovado.
    Usado pelo catch-up (que não tem os guards do enviar_slot)."""
    if not _e_dia_util(datetime.now()):
        return None
    r = draft_store.carregar(hoje)
    if not r or r.get("status") == "SKIPPED":
        return None
    return _montar_ctx(hoje, r)


def _enviar_estudo_para(whatsapp, nome, ctx):
    """Envia o estudo do dia (texto + PDF + áudio) a UM assinante. Falha de mídia é logada."""
    import phone
    whatsapp = phone.normalizar(whatsapp)
    link = f"{config.PUBLIC_URL}/entrar"
    msg = deliver.personalizar_rodape(
        montar_texto_resumo(ctx["titulo"], ctx["r"]["resumo"], ctx["tmeta"], fresco=ctx.get("fresco", False)),
        nome, link)
    deliver.enviar_texto(whatsapp, msg)
    if ctx["master_pdf"]:
        try:
            deliver.enviar_pdf(whatsapp, ctx["master_pdf"], caption=ctx["titulo"])
        except Exception as e:
            print(f"[enviar] PDF p/ {whatsapp} falhou: {e}", flush=True)
    if ctx["audio_bytes"]:
        try:
            deliver.enviar_audio(whatsapp, ctx["audio_bytes"])
        except Exception as e:
            print(f"[enviar] áudio p/ {whatsapp} falhou: {e}", flush=True)


def enviar_slot(slot):
    """Envia o estudo do dia SÓ pros assinantes de `slot`. Idempotente por (dia, slot) E por
    (dia, assinante) — o claim `registrar_envio_assinante` garante 1 envio/dia mesmo com troca."""
    import db
    hoje = _hoje_iso()
    if not db.registrar_envio_slot(hoje, slot):     # slot já processado hoje -> não repete
        return
    if not _e_dia_util(datetime.now()):
        return                                       # silencioso (sem spam por slot)
    r = draft_store.carregar(hoje)
    if not r or r.get("status") == "SKIPPED":        # sem rascunho ou vetado
        if db.registrar_envio_slot(hoje, "_skip_aviso"):   # avisa o curador 1x/dia
            deliver.enviar_curador(f"⏭️ Nada enviado hoje ({'sem rascunho' if not r else 'vetado'}).")
        return
    ctx = _montar_ctx(hoje, r)
    # claim por assinante: só quem AINDA não recebeu hoje (mata reenvio na troca de slot)
    destinatarios = [s for s in subscribers.ativos()
                     if subscribers.slot_de(s) == slot and db.registrar_envio_assinante(hoje, s["id"])]
    res = deliver.distribuir(r, destinatarios, config.SEND_DELAY_SEC,
                             lambda w, n: _enviar_estudo_para(w, n, ctx))
    _finalizar_dia(hoje, r, ctx["art"], ctx["conteudo"], ctx["tmeta"])
    if destinatarios:
        deliver.enviar_curador(f"✅ Enviado (slot {slot}, {ctx['art'].get('tema','')}): {res['ok']} assinantes"
                               + (f" · {len(res['falhas'])} falhas" if res["falhas"] else "")
                               + (" · ⚠️ SEM PDF (erro na geração)" if ctx["master_pdf"] is None else ""))


def enviar_catch_up(sub):
    """Envia o estudo de hoje a UM assinante que trocou pra um slot já disparado e ainda não
    recebeu. Idempotente (claim em envios_dia). Retorna True se enviou; False se nada a enviar
    ou já recebeu. NÃO chama _finalizar_dia (já rodou no 1º slot do dia)."""
    import db
    hoje = _hoje_iso()
    ctx = _ctx_do_dia(hoje)
    if ctx is None:
        return False
    if not db.registrar_envio_assinante(hoje, sub["id"]):   # já recebeu hoje -> não repete
        return False
    _enviar_estudo_para(sub["whatsapp"], sub.get("nome", ""), ctx)
    return True
