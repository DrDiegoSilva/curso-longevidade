"""Escolha do artigo do dia — funções puras, testáveis."""
_FORTE = ("meta-analysis", "randomized", "systematic review", "guideline", "practice guideline")


def _chave(a):
    return a.get("doi") or a.get("url") or a.get("titulo")


def dedupe(arts, ja_enviados):
    vistos, out = set(), []
    for a in arts:
        k = _chave(a)
        if not k or k in ja_enviados or k in vistos:
            continue
        vistos.add(k)
        out.append(a)
    return out


def _forca(a):
    t = (a.get("tipo") or "").lower()
    return 1 if any(f in t for f in _FORTE) else 0


def rank(arts):
    return sorted(arts, key=lambda a: (bool(a.get("doi")), _forca(a), a.get("data", "")), reverse=True)


def escolher_do_dia(arts, ja_enviados):
    ok = rank(dedupe(arts, ja_enviados))
    return ok[0] if ok else None
