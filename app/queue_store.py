"""Fila persistente de artigos triados (/data/queue.json).

Modelo: fila única ordenada por importância + regra de variedade (não repetir
o tema do último envio quando houver alternativa). Dedupe permanente por chave
(doi/url/título) contra tudo que já entrou na fila ou já foi enviado.

Estado: {"fila": [artigo...], "vistos": [chave...], "ultimo_tema": str|None}
Cada artigo carrega "tema" e "score" (importância dada pela triagem).
"""
import os
import json
import config


def _path():
    return os.path.join(config.DATA, "queue.json")


def _chave(a):
    return a.get("doi") or a.get("url") or a.get("titulo")


def _load():
    try:
        with open(_path(), encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = {}
    d.setdefault("fila", [])
    d.setdefault("vistos", [])
    d.setdefault("ultimo_tema", None)
    return d


def _save(d):
    os.makedirs(config.DATA, exist_ok=True)
    with open(_path(), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


def chaves_vistas():
    return set(_load()["vistos"])


def tamanho():
    return len(_load()["fila"])


def adicionar(artigos):
    """Adiciona artigos ainda não vistos; mantém a fila ordenada por score desc.
    Retorna quantos entraram."""
    d = _load()
    vistos = set(d["vistos"])
    novos = 0
    for a in artigos:
        k = _chave(a)
        if not k or k in vistos:
            continue
        vistos.add(k)
        d["vistos"].append(k)
        d["fila"].append(a)
        novos += 1
    d["fila"].sort(key=lambda x: x.get("score", 0), reverse=True)
    _save(d)
    return novos


def proximo():
    """Remove e retorna o próximo artigo: o melhor cujo tema ≠ último enviado
    (variedade); se todos forem do mesmo tema, retorna o melhor mesmo assim.
    Não altera 'ultimo_tema' (isso é confirmado no envio)."""
    d = _load()
    fila = d["fila"]
    if not fila:
        return None
    idx = 0
    if d.get("ultimo_tema"):
        for i, a in enumerate(fila):
            if a.get("tema") != d["ultimo_tema"]:
                idx = i
                break
    escolhido = fila.pop(idx)
    _save(d)
    return escolhido


def confirmar_envio(artigo):
    """Marca o tema do artigo como o último enviado (para a regra de variedade)."""
    d = _load()
    d["ultimo_tema"] = artigo.get("tema")
    _save(d)


def listar():
    """Cópia da fila atual (leitura; não altera estado)."""
    return list(_load()["fila"])


def remover(artigo):
    """Remove o artigo (por chave) da fila — usado ao materializar na agenda."""
    k = _chave(artigo)
    if k is None:                       # sem chave: não apaga tudo que também é None
        return
    d = _load()
    d["fila"] = [a for a in d["fila"] if _chave(a) != k]
    _save(d)


def devolver(artigo):
    """Recoloca um artigo na fila (ao desagendar/pular). Reordena por score. Não duplica."""
    d = _load()
    if _chave(artigo) in {_chave(a) for a in d["fila"]}:
        return
    d["fila"].append(artigo)
    d["fila"].sort(key=lambda x: x.get("score", 0), reverse=True)
    _save(d)
