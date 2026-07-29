"""Séries temáticas (item 8, Fase 2) — orquestração.

Montar o contexto da página /series e ATIVAR uma série: grava os N estudos nos
próximos N dias úteis livres da agenda, reusando o mecanismo do Item 23
(agenda_upsert + marcar_*_agendado). A série só grava slots; o pipeline das 18h
(preview → gate → envio) já cuida do resto. Conclui por data (reconciliar)."""
from datetime import date, datetime, timedelta

import agenda_plan


def contexto_pagina(db_mod=None, serie_aberta_id=None, termo=""):
    """Dados da /series: lista de séries, a série aberta (ou None) e os resultados
    da busca por tag (ou [])."""
    if db_mod is None:
        import db as db_mod
    db_mod.init()
    series = db_mod.listar_series()
    aberta = db_mod.obter_serie(serie_aberta_id) if serie_aberta_id else None
    resultados = db_mod.buscar_por_tag(termo) if (termo or "").strip() else []
    return {"series": series, "aberta": aberta, "resultados": resultados}


def _tem_dia_util(dias_envio):
    """True se `dias_envio` tem pelo menos um dia da semana reconhecido por
    `agenda_plan.DIAS` — guarda a rodar ANTES de qualquer chamada que dependa
    de `_dias_uteis_validos` (que levanta em conjunto vazio). dias_envio vazio
    é estado real e alcançável: o admin salva /admin/envio sem nenhum dia
    marcado e `daily._dias_envio()` devolve `set()`."""
    return bool(set(dias_envio) & set(agenda_plan.DIAS))


def _dias_uteis_validos(dias_envio):
    validos = set(dias_envio) & set(agenda_plan.DIAS)
    if not validos:
        raise ValueError("dias_envio não contém dia útil válido")
    return validos


def _normalizar_data(valor):
    """'2026-6-29' -> date(2026, 6, 29). None/vazio/formato inválido -> None.

    Toda data que entra em ativar_serie passa por aqui e vira `date` ANTES de
    qualquer comparação. O <input type=date> manda zero-padded, mas um POST
    urlencoded direto não: '2026-6-29' PASSA no strptime e, comparado como TEXTO
    com o piso '2026-07-30', fica MAIOR ('6' > '0'). O piso era burlado — uma
    segunda-feira 30 dias no passado virava slot da agenda com a reserva
    consumida (estudo curado gasto e nunca enviado). TypeError entra no except
    de propósito: `data_inicio=None` é o caso do contrato "não crasha"."""
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _eh_dia_util(d, dias_envio):
    return agenda_plan.DIAS[d.weekday()] in _dias_uteis_validos(dias_envio)


def _dias_livres(db_mod, d, n, dias_envio):
    """Próximos n dias úteis (YYYY-MM-DD) a partir de `d` (date) que NÃO estão
    fixados nem pulados. Pula dias fixados/pulados (usa o próximo livre)."""
    validos = _dias_uteis_validos(dias_envio)
    out = []
    while len(out) < n:
        if agenda_plan.DIAS[d.weekday()] in validos:
            s = db_mod.agenda_slot(d.isoformat())
            if not (s and (s.get("fixado") or s.get("tipo") == "pulado")):
                out.append(d.isoformat())
        d = d + timedelta(days=1)
    return out


def _liberar_dia(db_mod, dia):
    """Se o dia já tem estudo consumível (reserva/candidato/fila), devolve ao
    estoque ANTES de a série sobrescrever o slot — evita órfão e descarte de
    artigo já triado (mesmo cuidado do Item 23 + db.agenda_devolver).
    Clássico não é consumido; vazio/pulado não têm dono no estoque de estudos."""
    s = db_mod.agenda_slot(dia)
    if not s:
        return
    tipo = s.get("tipo")
    if tipo == "reserva" and s.get("ref_id"):
        db_mod.marcar_reserva_pronto(s["ref_id"])
    elif tipo == "candidato" and s.get("ref_id"):
        db_mod.marcar_candidato_pronto(s["ref_id"])
    elif tipo == "fila" and s.get("payload"):
        import json
        import queue_store
        queue_store.devolver(json.loads(s["payload"]))


def _indisponiveis(db_mod, itens):
    """Itens da série que NÃO podem ser agendados agora, já com o motivo em texto
    de admin. Lista vazia = pode ativar.

    `db.buscar_por_tag` (db.py:1023) filtra SÓ por tag, nunca por status — então
    um estudo já agendado, ou já ENVIADO, entra na série pelo montador e seria
    re-agendado: o mesmo ref_id em dois slots é o mesmo estudo preparado e
    mandado duas vezes, e um 'enviado' voltava pra 'agendado' e ia de novo.
    `daily.materializar` já guarda as duas coisas (daily.py:165-166 — lê só
    status='pronto' e pula ref_id que já está preso a um slot); ativar_serie
    reusava o mecanismo de escrita mas não as guardas."""
    problemas = []
    na_agenda = {t: db_mod.agenda_ref_ids(t) for t in ("reserva", "candidato", "classico")}
    for it in itens:
        tipo, rid = it.get("ref_tipo"), it.get("ref_id")
        nome = it.get("titulo") or rid or "(sem título)"
        if rid and rid in na_agenda.get(tipo, set()):
            problemas.append(f"'{nome}' já ocupa um dia da agenda")
            continue
        if tipo == "reserva":
            r = db_mod.obter_reserva(rid)
            if not r:
                problemas.append(f"'{nome}' não está mais na reserva")
            elif r.get("status") != "pronto":
                problemas.append(f"'{nome}' está '{r.get('status')}' (só dá pra agendar estudo 'pronto')")
        elif tipo == "candidato":
            c = db_mod.obter_candidato(rid)
            if not c:
                problemas.append(f"'{nome}' não está mais na curadoria")
            elif c.get("status") != "novo":
                problemas.append(f"'{nome}' está '{c.get('status')}' (só dá pra agendar candidato 'novo')")
        elif tipo == "classico":
            if not db_mod.obter_classico(rid):
                problemas.append(f"'{nome}' não está mais no banco de clássicos")
    return problemas


def reconciliar(db_mod=None, hoje=None):
    """Fecha séries ATIVAS cujo último dia atribuído já passou (< hoje). Libera
    ativar outra. Retorna os ids fechados.

    Fecha como 'concluida' quando TODO item foi agendado, e como 'incompleta'
    quando sobrou item sem data — antes o `if i.get("data")` descartava os órfãos
    e a série vencida virava 'concluida' calada, escondendo que um estudo curado
    da sequência nunca foi ao ar.

    Série ativa com ZERO itens datados não é fechada aqui de propósito: esse é
    exatamente o estado de uma ativação NO MEIO do caminho (o claim de
    `reivindicar_serie_ativa` acontece antes do loop que grava os dias), e fechar
    ali seria uma corrida nova. Quem impede o estado permanente é ativar_serie,
    que devolve a série pra 'rascunho' quando nenhum dia é gravado."""
    if db_mod is None:
        import db as db_mod
    hoje = hoje or date.today().isoformat()
    fechados = []
    for s in db_mod.listar_series():
        if s.get("status") != "ativa":
            continue
        det = db_mod.obter_serie(s["id"])
        datas = [i.get("data") for i in det["itens"] if i.get("data")]
        if not datas or max(datas) >= hoje:
            continue
        orfaos = [i for i in det["itens"] if not i.get("data")]
        db_mod.atualizar_serie(s["id"], status="incompleta" if orfaos else "concluida")
        if orfaos:
            titulos = ", ".join(f"'{i.get('titulo') or i.get('ref_id')}'" for i in orfaos)
            print(f"[series] série {s['id']} fechada INCOMPLETA — nunca agendado(s): {titulos}",
                  flush=True)
        fechados.append(s["id"])
    return fechados


def dia_minimo_inicio(db_mod=None, hoje=None, dias_envio=None, preparado_fn=None):
    """Primeiro dia útil a partir de AMANHÃ cujo preview das 18h ainda NÃO foi
    montado. Ativar num dia já preparado não trocaria o rascunho pronto (limitação
    do Item 23) — esse é o piso da data de início.

    Nunca levanta: sem nenhum dia de envio configurado, devolve "" (sentinel
    falsy) em vez do ValueError de _dias_uteis_validos. As duas rotas (GET
    /series e POST acao=ativar) avaliam esta função como ARGUMENTO — antes de
    qualquer guard rodar —, então um raise aqui derruba a tela inteira com 500
    mesmo com o guard equivalente já em ativar_serie."""
    if db_mod is None:
        import db as db_mod
    if dias_envio is None:
        import daily
        dias_envio = daily._dias_envio()
    if not _tem_dia_util(dias_envio):
        return ""
    if preparado_fn is None:
        import draft_store
        preparado_fn = lambda d: draft_store.carregar(d) is not None
    validos = _dias_uteis_validos(dias_envio)
    d = (datetime.strptime(hoje, "%Y-%m-%d").date() if hoje else date.today()) + timedelta(days=1)
    while True:
        iso = d.isoformat()
        if agenda_plan.DIAS[d.weekday()] in validos and not preparado_fn(iso):
            return iso
        d = d + timedelta(days=1)


_MSG_JA_ATIVA = "Já existe uma série ativa. Espere ela terminar antes de ativar outra."


def _devolver_claim(db_mod, serie_id):
    """Solta o claim de 'ativa' e devolve a série pra 'rascunho'. Retorna "" se
    deu certo, ou um aviso pro admin se NEM isso deu.

    Chamada em todo caminho que sai da ativação sem ter gravado dia nenhum. Sem
    ela a série fica 'ativa' com zero itens datados — e esse estado hoje NÃO TEM
    SAÍDA: `reconciliar` se recusa a fechar série sem data (de propósito, pra
    não correr com o claim) e a rota não tem ação de cancelar. Não levanta: quem
    chama já está tratando outra falha e não pode perder a mensagem original."""
    try:
        db_mod.atualizar_serie(serie_id, status="rascunho", data_inicio="", ativada_em="")
        return ""
    except Exception as e:
        print(f"[series] NÃO consegui devolver a série {serie_id} pra rascunho: {e}", flush=True)
        return (" ATENÇÃO: a série ficou ATIVA e vai bloquear a próxima ativação — "
                f"confira a /series ({e}).")


def ativar_serie(serie_id, data_inicio, dia_min=None, db_mod=None, dias_envio=None, hoje=None):
    """Grava os itens da série nos próximos N dias úteis livres a partir de
    data_inicio. Retorna (ok, msg). Não crasha: falha parcial → (False, aviso
    com o erro real de cada dia). `hoje` só existe pra teste (default: hoje).

    Ordem que importa: TODA validação e a guarda de disponibilidade rodam antes
    de `reivindicar_serie_ativa`, e o claim roda antes da primeira escrita na
    agenda — quem perde a corrida para sem ter tocado em slot nenhum."""
    if db_mod is None:
        import db as db_mod
    if dias_envio is None:
        import daily
        dias_envio = daily._dias_envio()
    if not _tem_dia_util(dias_envio):
        # daily._dias_envio() retorna vazio no modo "não envia" — sem isso,
        # _eh_dia_util (via _dias_uteis_validos) levantaria ValueError e
        # violaria o contrato de "nunca crasha" antes de qualquer escrita.
        return (False, "Configure os dias de envio (nenhum dia útil ativo).")
    db_mod.init()
    reconciliar(db_mod=db_mod, hoje=hoje)             # fecha vencidas antes da trava
    det = db_mod.obter_serie(serie_id)
    if not det:
        return (False, "Série não encontrada.")
    if det["serie"].get("status") != "rascunho":
        return (False, "Só dá pra ativar uma série em rascunho.")
    itens = det["itens"]
    if not itens:
        return (False, "A série está vazia — adicione estudos antes de ativar.")
    if any(s.get("status") == "ativa" for s in db_mod.listar_series()):
        return (False, _MSG_JA_ATIVA)                 # atalho amigável; a trava é o claim
    inicio = _normalizar_data(data_inicio)
    if inicio is None:
        # data_inicio malformada/vazia/None chega direto num POST urlencoded (o
        # <input type=date> do navegador não é a única porta) — sem isso,
        # datetime.strptime derrubava a rota com 500 (Fail-safe do plano:
        # "falha parcial -> avisa, não fica silenciosa").
        return (False, "Data de início inválida — escolha uma data no formato AAAA-MM-DD.")
    if not _eh_dia_util(inicio, dias_envio):
        return (False, "A data de início precisa cair num dia de envio (dia útil configurado).")
    # Regra PRÓPRIA de "não no passado": antes ela só existia de carona no
    # `dia_min` que o único chamador de produção passa — uma chamada direta com
    # data passada escrevia um slot histórico na agenda e queimava o estudo.
    if inicio < (_normalizar_data(hoje) or date.today()):
        return (False, "A data de início não pode estar no passado — escolha hoje ou um dia à frente.")
    piso = _normalizar_data(dia_min)
    if piso and inicio < piso:
        return (False, f"Escolha uma data a partir de {piso.isoformat()} — dias anteriores já podem "
                       f"ter o preview pronto. Pro 1º dia já preparado, use o 🔁 Trocar na revisão.")
    problemas = _indisponiveis(db_mod, itens)
    if problemas:
        return (False, "Não dá pra ativar: " + "; ".join(problemas) +
                       ". Tire esses estudos da série (🗑️) e ative de novo.")
    inicio_iso = inicio.isoformat()
    if not db_mod.reivindicar_serie_ativa(serie_id, inicio_iso, datetime.now().isoformat()):
        return (False, _MSG_JA_ATIVA)
    # Daqui pra baixo a série JÁ está 'ativa' no banco. QUALQUER escape sem dia
    # gravado (não só a falha por dia lá dentro: _dias_livres chama db.agenda_slot
    # e pode levantar com o banco travado) precisa devolver o claim — senão sobra
    # uma série 'ativa' sem item datado, que reconciliar não fecha e a rota não
    # cancela. Era a trava permanente do Finding 1 voltando por uma porta estreita.
    gravados, falhas = 0, []
    try:
        dias = _dias_livres(db_mod, inicio, len(itens), dias_envio)
        for dia, item in zip(dias, itens):
            try:
                _liberar_dia(db_mod, dia)
                tipo, ref_id = item["ref_tipo"], item["ref_id"]
                db_mod.agenda_upsert(dia, tipo=tipo, ref_id=ref_id, payload=None,
                                     tema=item.get("tema", ""), titulo=item.get("titulo", ""),
                                     fixado=0)
                if tipo == "reserva":
                    db_mod.marcar_reserva_agendado(ref_id)   # consome só APÓS gravar o slot
                elif tipo == "candidato":
                    db_mod.marcar_candidato_agendado(ref_id)
                # clássico: agenda_upsert basta (reusável, não consome)
                db_mod.set_serie_item_data(item["id"], dia)
                gravados += 1
            except Exception as e:
                print(f"[series] falha ao gravar '{item.get('titulo','')}' em {dia}: {e}", flush=True)
                falhas.append(f"{dia} '{item.get('titulo','')}': {e}")
    except Exception as e:
        print(f"[series] ativação de {serie_id} abortada antes de concluir: {e}", flush=True)
        aviso = _devolver_claim(db_mod, serie_id) if not gravados else ""
        if gravados:
            return (False, f"Série ativada só em parte ({gravados} dia(s)) e a montagem abortou: "
                           f"{e} — confira a /agenda pra não faltar/repetir estudo.")
        return (False, f"Não consegui montar os dias da série — ela continua em rascunho. "
                       f"Erro: {e}" + aviso)
    if not gravados:
        # Nada foi agendado: DEVOLVE o claim. Marcar 'ativa' aqui trancava a
        # feature pra sempre — sem item datado, reconciliar nunca fecha, e a rota
        # não tem ação de cancelar/concluir: só editando o banco na mão.
        return (False, "Não consegui agendar nenhum dia — a série continua em rascunho. "
                       + " | ".join(falhas) + _devolver_claim(db_mod, serie_id))
    if falhas:
        return (False, f"Série ativada com {len(falhas)} dia(s) com falha — confira a /agenda pra "
                       f"não faltar/repetir estudo. " + " | ".join(falhas))
    return (True, f"Série ativada: {len(dias)} estudos a partir de {inicio_iso}. "
                  f"Revise cada dia às 18h.")
