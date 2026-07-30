"""Limite de tentativas em MEMÓRIA, por chave (ex.: IP). Sem dependência de db/config.

Existe pra fechar um oráculo real: o campo de cupom do /assinar permitia chutar
códigos sem limite, e um cupom de CORTESIA acertado cria assinante ATIVO sem passar
pelo Asaas (serve.py) — acesso de graça, não desconto.

⚠️ ESCOPO: a contagem vive no processo. O serviço roda com UMA instância
(deploy.replicas=1), então isso basta. Com duas instâncias o limite passa a ser POR
instância e afrouxa proporcionalmente — resolver exigiria store compartilhado
(Redis), que o projeto não tem. Registrado no backlog.
"""
import threading
import time

_LOCK = threading.Lock()
_FALHAS = {}          # chave -> [timestamps das falhas]
_MAX_CHAVES = 5000    # teto de segurança: além disso, poda agressiva


def _podar(agora, janela_s):
    """Remove timestamps vencidos e chaves que ficaram vazias. Chamado sob _LOCK."""
    for k in list(_FALHAS.keys()):
        vivos = [t for t in _FALHAS[k] if agora - t < janela_s]
        if vivos:
            _FALHAS[k] = vivos
        else:
            del _FALHAS[k]


def permitir(chave, limite=5, janela_s=600):
    """True se `chave` ainda pode tentar. Também é o ponto onde a evicção roda."""
    agora = time.time()
    with _LOCK:
        _podar(agora, janela_s)
        return len(_FALHAS.get(chave, [])) < int(limite)


def registrar_falha(chave, janela_s=600):
    """Conta UMA tentativa falha. Sucesso nunca chama isto — quem tem cupom bom
    não gasta cota por conferir."""
    agora = time.time()
    with _LOCK:
        _FALHAS.setdefault(chave, []).append(agora)
        if len(_FALHAS) > _MAX_CHAVES:
            _podar(agora, janela_s)


def zerar():
    """Só pra teste."""
    with _LOCK:
        _FALHAS.clear()


def tamanho():
    """Nº de chaves rastreadas — só pra teste de evicção."""
    with _LOCK:
        return len(_FALHAS)
