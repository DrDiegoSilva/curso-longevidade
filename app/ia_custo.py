"""Tokens -> dinheiro.

O ledger (`db.ia_uso`) guarda só o CRU: modelo e contagem de unidades. O custo é
calculado aqui, na leitura, a partir de `config.PRECOS_IA`. Consequência que vale o
desenho: preço que eu errei hoje, ou preço que a Anthropic mudar amanhã, é **recálculo** —
a história inteira se revaloriza sozinha. Custo congelado na linha contaminaria os
números para sempre.

Por que não pedir o valor pronto para a API: a resposta das mensagens traz `usage` em
tokens e nenhum campo de dinheiro. Existe a Admin API de custo, mas ela vem agregada por
dia e modelo — sabe quanto gastou de Sonnet na terça, não sabe o que é um dossiê.
"""
import config

_SEM_PRECO = set()          # avisa uma vez por modelo, não a cada chamada


def custo_usd(modelo, tokens_in, tokens_out=0):
    """US$ de uma linha do ledger. Modelo sem preço vira 0.0 + aviso no log: a tela de
    custos não pode cair porque entrou um modelo novo."""
    preco = config.PRECOS_IA.get(modelo)
    if not preco:
        if modelo not in _SEM_PRECO:
            _SEM_PRECO.add(modelo)
            print(f"[custo] modelo sem preço em PRECOS_IA: {modelo}", flush=True)
        return 0.0
    p_in, p_out = preco
    return (tokens_in or 0) * p_in / 1e6 + (tokens_out or 0) * p_out / 1e6


def em_brl(usd):
    return (usd or 0.0) * config.USD_BRL
