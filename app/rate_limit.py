"""Rate-limit simples em memória (instância única do EasyPanel).

Janela deslizante por chave (ex.: "otp:<ip>"). NÃO persiste — reinicia a cada
deploy/restart, o que é aceitável para conter abuso de login/OTP/recuperação.
`limitado` é puro o suficiente p/ testar (injeta `agora`).
"""
import time
import threading

_hits = {}                 # chave -> lista de timestamps (float)
_lock = threading.Lock()
_MAX_CHAVES = 5000         # teto de segurança contra crescimento infinito


def limitado(chave, maximo, janela_seg, agora=None):
    """True se `chave` já atingiu `maximo` tentativas dentro de `janela_seg`.
    Registra a tentativa quando AINDA não estourou (não conta a que foi barrada)."""
    agora = time.time() if agora is None else agora
    corte = agora - janela_seg
    with _lock:
        xs = [t for t in _hits.get(chave, ()) if t > corte]
        estourou = len(xs) >= maximo
        if not estourou:
            xs.append(agora)
        _hits[chave] = xs
        if len(_hits) > _MAX_CHAVES:      # limpeza preguiçosa das chaves já vencidas
            for k in [k for k, v in list(_hits.items()) if not v or v[-1] <= corte]:
                _hits.pop(k, None)
    return estourou


def resetar():
    """Zera o estado (usado em testes)."""
    with _lock:
        _hits.clear()
