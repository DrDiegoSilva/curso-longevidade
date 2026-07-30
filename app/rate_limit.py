"""Rate-limit simples em memória (instância única do EasyPanel).

Janela deslizante por chave (ex.: "otp:<ip>"). NÃO persiste — reinicia a cada
deploy/restart, o que é aceitável para conter abuso de login/OTP/recuperação.
`limitado` é puro o suficiente p/ testar (injeta `agora`).

CONTAR-E-PERDOAR (fix do CRITICAL da revisão final, 2026-07-29): quando "checar" e
"contar" precisam ser separáveis — um cupom VÁLIDO não pode gastar cota de quem
acertou — a resposta certa NÃO é espiar agora e contar depois. Peek-then-count perde
a atomicidade que este módulo tinha: sob `ThreadingHTTPServer`, toda thread de uma
rajada espia a contagem 0 (o registro só sairia uma ida ao banco depois) e TODAS
passam — 50 de 50 chutes avaliados com teto de 5, medido. O certo é chamar
`limitado(...)` normal (checa e grava na MESMA seção crítica) e, se a tentativa se
revelar legítima, devolver a cota com `perdoar_tentativa`. As duas propriedades
valem juntas: sem corrida, e cupom válido de graça.

`limitado(..., registrar=False)` (PEEK, sem gravar nada) e `registrar_tentativa`
(conta 1 sem checar) continuam aqui como primitivas — hoje SEM nenhum uso na app (as
duas rotas de cupom passaram pro contar-e-perdoar) e mantidas só com testes próprios,
justamente pra documentar a armadilha: NÃO servem pra montar check-then-act sob
concorrência, ver o aviso na docstring de cada uma. Nenhuma das três muda o
comportamento de `limitado(..., registrar=True)`: o default, o único modo que
login/OTP/recuperação usam.
"""
import time
import threading

_hits = {}                 # chave -> lista de timestamps (float)
_janelas = {}              # chave -> janela_seg da última escrita nessa chave
_lock = threading.Lock()
_MAX_CHAVES = 5000         # teto de segurança contra crescimento infinito


def _podar_vencidas(agora):
    """Limpeza preguiçosa das chaves já vencidas. Chamada sob `_lock`, só quando o
    dicionário passa do teto — mesma condição/lógica de antes da extensão.

    Cada chave é avaliada com A PRÓPRIA janela (`_janelas`), não com a de quem
    disparou a poda (Minor da revisão final): chaves de janelas diferentes convivem
    aqui (`login:` 300 s, `otp:`/`recover:`/`cupom:` 600 s), e podar todas com a
    janela do chamador fazia uma chamada de login evictar chaves `cupom:` ainda
    vigentes — reset de cota silencioso, exatamente o que o limite existe pra
    impedir. Chave sem janela conhecida nunca é evictada (nunca some cota alheia)."""
    if len(_hits) <= _MAX_CHAVES:
        return
    for k, v in list(_hits.items()):
        janela = _janelas.get(k)
        if janela is None:
            continue
        if not v or v[-1] <= agora - janela:
            _hits.pop(k, None)
            _janelas.pop(k, None)


def limitado(chave, maximo, janela_seg, agora=None, registrar=True):
    """True se `chave` já atingiu `maximo` tentativas dentro de `janela_seg`.
    Com `registrar=True` (o default, comportamento idêntico ao de sempre): registra
    a tentativa quando AINDA não estourou (não conta a que foi barrada).
    Com `registrar=False`: PEEK puro — responde sem gravar nada em `chave`.

    CUIDADO: `registrar=False` NÃO serve pra decidir e contar depois (peek-then-count
    é uma corrida — ver o cabeçalho do módulo). Pra "não gastar cota quando a
    tentativa era legítima", use este default e depois `perdoar_tentativa`."""
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
        _janelas[chave] = janela_seg
        _podar_vencidas(agora)
    return estourou


def registrar_tentativa(chave, janela_seg, agora=None):
    """Conta UMA tentativa em `chave`, sem checar limite nenhum. `janela_seg` só
    orienta a poda preguiçosa das chaves vencidas (mesmo teto `_MAX_CHAVES`).

    CUIDADO: usar isto DEPOIS de um peek (`limitado(..., registrar=False)`) é o
    peek-then-count que o CRITICAL da revisão final desmontou — entre o peek e o
    registro cabe a rajada inteira. Existe pra contar uma tentativa cuja decisão não
    depende de ler a contagem."""
    agora = time.time() if agora is None else agora
    with _lock:
        _hits.setdefault(chave, []).append(agora)
        _janelas[chave] = janela_seg
        _podar_vencidas(agora)


def perdoar_tentativa(chave):
    """Devolve UMA tentativa a `chave` (o oposto de contar): remove o registro mais
    recente. No-op se a chave não existe ou já está vazia.

    É a metade "perdoa" do contar-e-perdoar: quem chama conta a tentativa
    atomicamente (`limitado`), avalia, e chama isto quando a tentativa se revelou
    legítima (cupom promocional/afiliado/cortesia válido) — a cota fica exatamente
    como estava, sem que nunca tenha existido uma janela entre checar e contar.

    Remove o timestamp mais recente e não "o meu": a lista é um multiconjunto de
    marcas dentro da janela, então a contagem cai de exatamente 1 de qualquer forma.
    Se outra thread gravou uma falha no meio, perdoa a marca dela e mantém a minha —
    o total (n−1) é o mesmo, e nenhuma tentativa falha deixa de ser cobrada."""
    with _lock:
        xs = _hits.get(chave)
        if xs:
            xs.pop()


def resetar():
    """Zera o estado (usado em testes)."""
    with _lock:
        _hits.clear()
        _janelas.clear()


def tamanho():
    """Nº de chaves rastreadas — só pra teste de evicção (migrado de
    ratelimit.py::tamanho() na consolidação dos dois módulos)."""
    with _lock:
        return len(_hits)
