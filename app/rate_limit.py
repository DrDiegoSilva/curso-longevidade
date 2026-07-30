"""Rate-limit simples em memória (instância única do EasyPanel).

Janela deslizante por chave (ex.: "otp:<ip>"). NÃO persiste — reinicia a cada
deploy/restart, o que é aceitável para conter abuso de login/OTP/recuperação.
`limitado` é puro o suficiente p/ testar (injeta `agora`).

`limitado(..., registrar=False)` é um PEEK: só responde se `chave` já estourou,
sem gravar nada — necessário quando checar e contar precisam ser separáveis (ex.:
um cupom válido não pode gastar cota de quem acertou, mas um IP já bloqueado tem
que ser recusado ANTES de o cupom ser avaliado). `registrar_tentativa` é o par:
conta UMA tentativa sem checar limite nenhum, chamado só depois que quem chama já
sabe que a tentativa falhou. Nenhuma das duas mudam o comportamento de
`limitado(..., registrar=True)` — o default, o único modo que login/OTP/
recuperação usam.
"""
import time
import threading

_hits = {}                 # chave -> lista de timestamps (float)
_lock = threading.Lock()
_MAX_CHAVES = 5000         # teto de segurança contra crescimento infinito


def _podar_vencidas(agora, janela_seg):
    """Limpeza preguiçosa das chaves já vencidas. Chamada sob `_lock`, só quando o
    dicionário passa do teto — mesma condição/lógica de antes da extensão."""
    if len(_hits) > _MAX_CHAVES:
        corte = agora - janela_seg
        for k in [k for k, v in list(_hits.items()) if not v or v[-1] <= corte]:
            _hits.pop(k, None)


def limitado(chave, maximo, janela_seg, agora=None, registrar=True):
    """True se `chave` já atingiu `maximo` tentativas dentro de `janela_seg`.
    Com `registrar=True` (o default, comportamento idêntico ao de sempre): registra
    a tentativa quando AINDA não estourou (não conta a que foi barrada).
    Com `registrar=False`: PEEK puro — responde sem gravar nada em `chave`."""
    agora = time.time() if agora is None else agora
    corte = agora - janela_seg
    with _lock:
        xs = [t for t in _hits.get(chave, ()) if t > corte]
        estourou = len(xs) >= maximo
        if not registrar:
            return estourou
        if not estourou:
            xs.append(agora)
        _hits[chave] = xs
        _podar_vencidas(agora, janela_seg)
    return estourou


def registrar_tentativa(chave, janela_seg, agora=None):
    """Conta UMA tentativa em `chave`, sem checar limite nenhum — o par do peek
    (`limitado(..., registrar=False)`): primeiro checa, decide (ex.: cupom
    inválido) e só ENTÃO chama isto. `janela_seg` só orienta a poda preguiçosa das
    chaves vencidas (mesmo teto `_MAX_CHAVES` de sempre)."""
    agora = time.time() if agora is None else agora
    with _lock:
        _hits.setdefault(chave, []).append(agora)
        _podar_vencidas(agora, janela_seg)


def resetar():
    """Zera o estado (usado em testes)."""
    with _lock:
        _hits.clear()
