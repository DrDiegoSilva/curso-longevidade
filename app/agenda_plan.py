"""Planejamento puro da agenda de envios — sem I/O (testável em memória).

Regras: preencher só os dias VAZIOS; variedade (não repetir o tema do dia
anterior quando houver alternativa) > rotação de tema como guia da vez >
fresh-first (candidato fresco, ≤30d) > TIER de curadoria (curada/reserva >
crua/candidato-fila > clássico como PISO, só entra quando não há melhor) >
nota (score, só desempata dentro do mesmo tier). Não consome candidato duas vezes.
"""
from datetime import datetime, timedelta

DIAS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]


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


def planejar_agenda(dias_ordenados, candidatos, rotacao, tema_anterior):
    """dias_ordenados: [(data, tema_atual|None, bloqueado)]. Retorna {data: candidato}
    só p/ os dias vazios (tema_atual None e não-bloqueado)."""
    prev = tema_anterior
    usados, plano = set(), {}
    rot = rotacao or []
    rot_i = 0
    for data, tema_atual, bloqueado in dias_ordenados:
        if bloqueado or tema_atual is not None:
            prev = tema_atual
            continue
        preferido = rot[rot_i % len(rot)] if rot else None
        idx, cand = _escolher(candidatos, usados, preferido, prev)
        if cand is None:
            prev = None
            continue
        plano[data] = cand
        usados.add(idx)
        prev = cand["tema"]
        rot_i += 1
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
