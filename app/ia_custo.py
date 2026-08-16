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

# Vocabulário fixo dos rótulos de `acao`, pra tela futura de custos não nascer com
# sinônimos. Não é guarda de runtime — `registrar` nunca rejeita um rótulo fora daqui
# (o ledger não pode atrapalhar geração); quem confere é `tests/test_ia_custo.py`,
# varrendo os `acao=` REAIS do código-fonte.
ACOES = ("dossie", "resumo_estudo", "boletim", "triagem", "tags", "metadados",
         "perguntas", "kit", "titulo", "grafico", "aula", "audio_roteiro",
         "audio_tts", "desconhecido")

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


def registrar(acao, modelo, unidades_in, unidades_out=0, chamadas=1):
    """Grava uma linha do ledger. NUNCA levanta: perder uma linha de custo é aceitável,
    perder o estudo do dia não é."""
    try:
        import db
        db.init()
        # `acao or "desconhecido"`: claude() já normaliza antes de chamar, mas repetimos
        # aqui como defesa para um futuro chamador direto que esqueça de normalizar.
        db.registrar_ia_uso(acao or "desconhecido", modelo, unidades_in,
                            unidades_out, chamadas)
    except Exception as e:
        print(f"[custo] não registrei o uso ({acao}): {e}", flush=True)


def total_usd(linhas):
    """US$ de um conjunto de linhas agregadas do ledger."""
    return sum(custo_usd(l.get("modelo"), l.get("tokens_in"), l.get("tokens_out"))
               for l in (linhas or []))


def por_acao(linhas):
    """Gasto por ação, do que mais pesa para o que menos pesa.

    A ordem é o conteúdo: é ela que diz ao Diego o que cortar se achar caro. Modelos
    diferentes dentro da mesma ação somam com o preço de cada um.
    """
    acc = {}
    for l in (linhas or []):
        usd = custo_usd(l.get("modelo"), l.get("tokens_in"), l.get("tokens_out"))
        acao = l.get("acao") or "desconhecido"
        acc[acao] = acc.get(acao, 0.0) + usd
    return [{"acao": a, "usd": u, "brl": em_brl(u)}
            for a, u in sorted(acc.items(), key=lambda kv: kv[1], reverse=True)]


def por_dia(linhas):
    """{'AAAA-MM-DD': US$} — é o lado nosso da comparação com a fatura.

    Nota: diferente de `por_acao`, usamos "" como valor ausente em vez de "desconhecido".
    Razão: "desconhecido" é um balde legítimo (ação sem rótulo existe e aparece na tela),
    mas um dia sem data não é um dia — colocá-lo numa tabela de dias reais o contaminaria.
    Na prática não acontece: `dia` vem de SQL com `substr(quando,1,10)` que sempre devolve algo.
    """
    acc = {}
    for l in (linhas or []):
        dia = l.get("dia") or ""
        acc[dia] = acc.get(dia, 0.0) + custo_usd(l.get("modelo"), l.get("tokens_in"),
                                                 l.get("tokens_out"))
    return acc
