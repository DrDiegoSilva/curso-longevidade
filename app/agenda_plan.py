"""Planejamento puro da agenda de envios — sem I/O (testável em memória).

Regras: preencher só os dias VAZIOS; variedade (não repetir o tema do dia
anterior quando houver alternativa) > tema do dia da semana como guia da vez >
fresh-first (candidato fresco, ≤30d) > TIER de curadoria (curada/reserva >
crua/candidato-fila > clássico como PISO, só entra quando não há melhor) >
nota (score, só desempata dentro do mesmo tier). Não consome candidato duas vezes.
"""
from datetime import datetime, timedelta

DIAS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]


def tema_do_dia(data, temas_por_dia):
    """Tema preferido p/ a data (YYYY-MM-DD). Alterna a cada semana quando o dia tem
    mais de um tema. Devolve None quando o dia não está no mapa (aí não há preferência).

    A alternância usa `toordinal() // 7`, não a semana ISO: em anos de 53 semanas a
    paridade ISO repete na virada (semana 53 e semana 1 têm a mesma paridade), o que
    daria o mesmo tema em duas semanas seguidas. O ordinal é monotônico e ignora
    fronteira de ano — consultado sempre no mesmo dia da semana, o balde avança de 1
    a cada semana."""
    dt = datetime.strptime(data, "%Y-%m-%d")
    temas = (temas_por_dia or {}).get(DIAS[dt.weekday()]) or []
    return temas[(dt.toordinal() // 7) % len(temas)] if temas else None


def dias_uteis_desde(inicio, n, dias_envio):
    """Próximos n dias úteis (YYYY-MM-DD) a partir de `inicio` (datetime), inclusive."""
    validos = set(dias_envio) & set(DIAS)
    if not validos:
        raise ValueError("dias_envio não contém nenhum dia útil válido")
    out, d = [], inicio
    while len(out) < n:
        if DIAS[d.weekday()] in validos:
            out.append(d.strftime("%Y-%m-%d"))
        d = d + timedelta(days=1)
    return out


def semanas_do_mes(hoje, dias_envio, n_semanas=4):
    """Dias úteis de `n_semanas` semanas CHEIAS (seg–sex), começando na segunda-feira
    da semana de `hoje`. Ex.: 4 semanas seg–sex = 20 dias. Inclui os dias já passados
    da semana atual (o chamador os marca como histórico). Retorna YYYY-MM-DD em ordem."""
    validos = set(dias_envio) & set(DIAS)
    if not validos:
        raise ValueError("dias_envio não contém nenhum dia útil válido")
    segunda = hoje - timedelta(days=hoje.weekday())   # segunda-feira da semana de hoje
    fim = segunda + timedelta(days=n_semanas * 7)
    out, d = [], segunda
    while d < fim:
        if DIAS[d.weekday()] in validos:
            out.append(d.strftime("%Y-%m-%d"))
        d = d + timedelta(days=1)
    return out


def _tier(cand):
    """Camada de curadoria: clássico é o piso; entre o resto, curada (reserva, revisada por
    humano) bate crua (candidato/fila, direto da varredura, sem revisão)."""
    if cand.get("classico"):
        return 0                       # clássico é o piso
    return 2 if cand.get("tipo") == "reserva" else 1   # curada(reserva)=2 > crua(candidato/fila)=1


def _rank(cand, preferido, prev):
    return (
        1 if cand["tema"] != prev else 0,            # variedade (regra forte)
        1 if cand["tema"] == preferido else 0,       # rotação = tema do dia (guia da vez)
        1 if cand.get("fresco") else 0,              # fresh-first (≤30d)
        _tier(cand),                                 # curada(2) > crua(1) > clássico(0)
        cand.get("score", 0),                        # nota (score) só desempata dentro da mesma camada
    )


def _escolher(candidatos, usados, preferido, prev):
    disp = [(i, c) for i, c in enumerate(candidatos) if i not in usados]
    if not disp:
        return None, None
    return max(disp, key=lambda ic: _rank(ic[1], preferido, prev))


def planejar_agenda(dias_ordenados, candidatos, temas_por_dia, tema_anterior):
    """dias_ordenados: [(data, tema_atual|None, bloqueado)]. Retorna {data: candidato}
    só p/ os dias vazios (tema_atual None e não-bloqueado). O tema preferido de cada dia
    vem do mapa dia-da-semana (tema_do_dia), não de um contador — assim a grade não
    deriva quando um dia está fixado, pulado ou já preenchido."""
    prev = tema_anterior
    usados, plano = set(), {}
    for data, tema_atual, bloqueado in dias_ordenados:
        if bloqueado or tema_atual is not None:
            prev = tema_atual
            continue
        preferido = tema_do_dia(data, temas_por_dia)
        idx, cand = _escolher(candidatos, usados, preferido, prev)
        if cand is None:
            prev = None
            continue
        plano[data] = cand
        usados.add(idx)
        prev = cand["tema"]
    return plano


def classificar_slot(slot):
    """Decide a fonte do preparo das 18h a partir do slot (função pura)."""
    if not slot:
        return ("fallback", None)
    t = slot.get("tipo")
    if t == "pulado":
        return ("pulado", None)
    if t == "reserva" and slot.get("ref_id"):
        return ("reserva", slot["ref_id"])
    if t == "candidato" and slot.get("ref_id"):
        return ("candidato", slot["ref_id"])
    if t == "classico" and slot.get("ref_id"):
        return ("classico", slot["ref_id"])
    if t == "fila" and slot.get("payload"):
        return ("fila", slot["payload"])
    return ("fallback", None)


def precisa_reabastecer(fila_n, reserva_n, horizonte):
    """Reabastece enquanto o estoque total não cobre o horizonte (acumula os frescos
    da semana em vez de só reabastecer quando a fila esvazia)."""
    return (fila_n + reserva_n) < horizonte


def estado_estoque(reserva_n, cand_n, classico_n, hoje, dias_envio, minimo):
    """Quantos envios o estoque cobre e até que dia. Puro (sem I/O).
    `hoje` é datetime (mesmo contrato de dias_uteis_desde); `dias_envio` é iterável de
    nomes de dia; `ate` volta em YYYY-MM-DD, ou None quando não há estoque OU quando
    `dias_envio` não tem nenhum dia útil válido (config incompleta/em edição —
    degrada pra "não sei até quando" em vez de propagar o ValueError)."""
    envios = reserva_n + cand_n + classico_n
    ate = None
    if envios:
        try:
            ate = dias_uteis_desde(hoje, envios, dias_envio)[-1]
        except ValueError:
            ate = None
    return {"envios": envios, "ate": ate, "baixo": envios < minimo}


def agrupar_por_semana(slots_ordenados):
    """Quebra a lista de slots (ordenada por data) em blocos por semana ISO."""
    semanas, atual, chave = [], [], None
    for s in slots_ordenados:
        wk = datetime.strptime(s["data"], "%Y-%m-%d").isocalendar()[:2]
        if chave is not None and wk != chave:
            semanas.append(atual)
            atual = []
        atual.append(s)
        chave = wk
    if atual:
        semanas.append(atual)
    return semanas
