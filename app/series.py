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


def _dias_uteis_validos(dias_envio):
    validos = set(dias_envio) & set(agenda_plan.DIAS)
    if not validos:
        raise ValueError("dias_envio não contém dia útil válido")
    return validos


def _eh_dia_util(data_inicio, dias_envio):
    d = datetime.strptime(data_inicio, "%Y-%m-%d").date()
    return agenda_plan.DIAS[d.weekday()] in _dias_uteis_validos(dias_envio)


def _dias_livres(db_mod, data_inicio, n, dias_envio):
    """Próximos n dias úteis (YYYY-MM-DD) a partir de data_inicio que NÃO estão
    fixados nem pulados. Pula dias fixados/pulados (usa o próximo livre)."""
    validos = _dias_uteis_validos(dias_envio)
    d = datetime.strptime(data_inicio, "%Y-%m-%d").date()
    out = []
    while len(out) < n:
        if agenda_plan.DIAS[d.weekday()] in validos:
            s = db_mod.agenda_slot(d.isoformat())
            if not (s and (s.get("fixado") or s.get("tipo") == "pulado")):
                out.append(d.isoformat())
        d = d + timedelta(days=1)
    return out


def _liberar_dia(db_mod, dia):
    """Se o dia já tem estudo consumível (reserva/candidato), devolve ao estoque
    ANTES de a série sobrescrever o slot — evita órfão (mesmo cuidado do Item 23).
    Clássico não é consumido; vazio/fila não têm dono no estoque de estudos."""
    s = db_mod.agenda_slot(dia)
    if not s or not s.get("ref_id"):
        return
    if s.get("tipo") == "reserva":
        db_mod.marcar_reserva_pronto(s["ref_id"])
    elif s.get("tipo") == "candidato":
        db_mod.marcar_candidato_pronto(s["ref_id"])


def reconciliar(db_mod=None, hoje=None):
    """Fecha séries ATIVAS cujo último dia atribuído já passou (< hoje). Libera
    ativar outra. Retorna os ids concluídos."""
    if db_mod is None:
        import db as db_mod
    hoje = hoje or date.today().isoformat()
    fechados = []
    for s in db_mod.listar_series():
        if s.get("status") != "ativa":
            continue
        det = db_mod.obter_serie(s["id"])
        datas = [i.get("data") for i in det["itens"] if i.get("data")]
        if datas and max(datas) < hoje:
            db_mod.atualizar_serie(s["id"], status="concluida")
            fechados.append(s["id"])
    return fechados


def dia_minimo_inicio(db_mod=None, hoje=None, dias_envio=None, preparado_fn=None):
    """Primeiro dia útil a partir de AMANHÃ cujo preview das 18h ainda NÃO foi
    montado. Ativar num dia já preparado não trocaria o rascunho pronto (limitação
    do Item 23) — esse é o piso da data de início."""
    if db_mod is None:
        import db as db_mod
    if dias_envio is None:
        import daily
        dias_envio = daily._dias_envio()
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


def ativar_serie(serie_id, data_inicio, dia_min=None, db_mod=None, dias_envio=None):
    """Grava os itens da série nos próximos N dias úteis livres a partir de
    data_inicio. Retorna (ok, msg). Não crasha: falha parcial → (False, aviso)."""
    if db_mod is None:
        import db as db_mod
    if dias_envio is None:
        import daily
        dias_envio = daily._dias_envio()
    db_mod.init()
    reconciliar(db_mod=db_mod)                        # fecha vencidas antes da trava
    det = db_mod.obter_serie(serie_id)
    if not det:
        return (False, "Série não encontrada.")
    if det["serie"].get("status") != "rascunho":
        return (False, "Só dá pra ativar uma série em rascunho.")
    itens = det["itens"]
    if not itens:
        return (False, "A série está vazia — adicione estudos antes de ativar.")
    if any(s.get("status") == "ativa" for s in db_mod.listar_series()):
        return (False, "Já existe uma série ativa. Espere ela terminar antes de ativar outra.")
    if not _eh_dia_util(data_inicio, dias_envio):
        return (False, "A data de início precisa cair num dia de envio (dia útil configurado).")
    if dia_min and data_inicio < dia_min:
        return (False, f"Escolha uma data a partir de {dia_min} — dias anteriores já podem ter o "
                       f"preview pronto. Pro 1º dia já preparado, use o 🔁 Trocar na revisão.")
    dias = _dias_livres(db_mod, data_inicio, len(itens), dias_envio)
    falhou = False
    for dia, item in zip(dias, itens):
        try:
            _liberar_dia(db_mod, dia)
            tipo, ref_id = item["ref_tipo"], item["ref_id"]
            db_mod.agenda_upsert(dia, tipo=tipo, ref_id=ref_id, payload=None,
                                 tema=item.get("tema", ""), titulo=item.get("titulo", ""), fixado=0)
            if tipo == "reserva":
                db_mod.marcar_reserva_agendado(ref_id)       # consome só APÓS gravar o slot
            elif tipo == "candidato":
                db_mod.marcar_candidato_agendado(ref_id)
            # clássico: agenda_upsert basta (reusável, não consome)
            db_mod.set_serie_item_data(item["id"], dia)
        except Exception as e:
            print(f"[series] falha ao gravar '{item.get('titulo','')}' em {dia}: {e}", flush=True)
            falhou = True
    db_mod.atualizar_serie(serie_id, status="ativa", data_inicio=data_inicio,
                           ativada_em=datetime.now().isoformat())
    if falhou:
        return (False, "Série ativada com falhas em alguns dias — confira a /agenda pra não faltar/repetir estudo.")
    return (True, f"Série ativada: {len(dias)} estudos a partir de {data_inicio}. Revise cada dia às 18h.")
