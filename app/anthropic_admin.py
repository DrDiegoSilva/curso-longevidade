"""A fatura real da Anthropic, para conferir contra o nosso ledger.

Este é o único ponto da entrega que não foi testado contra o serviço real — a chave de
admin é do Diego. Por isso ele vive isolado, com o contrato copiado da documentação
(conferida em 2026-08-16), e devolve um ESTADO nomeado em vez de levantar: a tela precisa
continuar mostrando o lado que é nosso mesmo quando este lado falha.

⚠️ `amount` vem em CENTAVOS, como string decimal: "123.45" em USD é US$ 1,23. Sem dividir
por 100 a tela mostraria 100x o gasto real — plausível o bastante pra ser acreditado.

⚠️ O relatório é da ORGANIZAÇÃO inteira, não deste app. Diferença contra o nosso ledger
não significa automaticamente preço errado na nossa tabela: pode ser uso de outra origem.

⚠️ `custo_por_dia` também devolve `parcial` (bool), ortogonal ao `estado`: estado 'ok' com
`parcial=True` significa que a API respondeu, mas a leitura ficou sabidamente incompleta
(item com `amount` ilegível descartado, ou fatura maior que o teto de páginas). Sem esse
aviso, a tela mostraria um total truncado como se fosse o total real — e como esta tela
existe pra conferir a NOSSA tabela de preço, um número pra baixo faria parecer que estamos
superestimando o gasto, quando é o oposto.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

import config

URL = "https://api.anthropic.com/v1/organizations/cost_report"
MAX_PAGINAS = 20          # defesa contra laço infinito: a tela não pode travar o servidor


def _headers(chave):
    """A doc exemplifica com `Authorization: Bearer`; chaves de admin históricas usam
    `x-api-key`. Sem a chave do Diego não dá pra saber qual é a dele — escolhe-se pelo
    formato, e o estado 'recusada' na tela cobre o caso de termos escolhido errado."""
    h = {"anthropic-version": "2023-06-01"}
    if str(chave).startswith("sk-ant-"):
        h["x-api-key"] = str(chave)
    else:
        h["Authorization"] = "Bearer " + str(chave)
    return h


def _get(url, chave):
    """O GET isolado — é o ponto que os testes substituem pra rodar sem rede."""
    req = urllib.request.Request(url, method="GET", headers=_headers(chave))
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def _dias_da_pagina(pagina):
    """({'AAAA-MM-DD': US$}, houve_descarte) de uma página. Item com `amount` ilegível é
    pulado — perder um item é melhor que perder o relatório inteiro — mas o descarte fica
    sinalizado pro chamador: a soma que sai daqui é sabidamente incompleta, e a tela não
    pode reportar 'ok' como se fosse a fatura inteira quando isso acontece."""
    out = {}
    descartou = False
    for b in (pagina.get("data") or []):
        dia = str(b.get("starting_at") or "")[:10]
        if not dia:
            continue
        total = 0.0
        for item in (b.get("results") or []):
            try:
                total += float(item.get("amount")) / 100.0     # centavos -> dólar
            except (TypeError, ValueError):
                print(f"[fatura] amount ilegível em {dia}: {item.get('amount')!r}", flush=True)
                descartou = True
        out[dia] = out.get(dia, 0.0) + total
    return out, descartou


def custo_por_dia(desde, ate=None, chave=None):
    """O que a Anthropic cobrou, por dia. Nunca levanta: devolve o estado.

    `parcial` é ortogonal ao `estado`: com estado 'ok' a API respondeu, mas `parcial=True`
    avisa que a leitura ficou sabidamente incompleta (algum item não parseou, ou o teto de
    páginas cortou a fatura antes do fim) — sem esse aviso, uma fatura truncada pareceria
    completa e mentiria pra baixo sobre o quanto a Anthropic cobrou."""
    chave = chave if chave is not None else config.ANTHROPIC_ADMIN_KEY
    if not chave:
        return {"estado": "sem_chave", "dias": {}, "parcial": False}
    params = {"starting_at": f"{desde}T00:00:00Z", "bucket_width": "1d"}
    if ate:
        params["ending_at"] = f"{ate}T00:00:00Z"
    dias, pagina_cursor, parcial = {}, None, False
    try:
        for _ in range(MAX_PAGINAS):
            p = dict(params)
            if pagina_cursor:
                p["page"] = pagina_cursor
            r = _get(URL + "?" + urllib.parse.urlencode(p), chave) or {}
            dias_pagina, descartou = _dias_da_pagina(r)
            for dia, valor in dias_pagina.items():
                dias[dia] = dias.get(dia, 0.0) + valor    # soma entre páginas, nunca sobrescreve
            parcial = parcial or descartou
            if not r.get("has_more"):
                break
            if not r.get("next_page"):
                # anomalia da API: diz que tem mais páginas mas não manda o cursor pra
                # seguir. Parar aqui em silêncio faria a fatura sair curta como se fosse
                # a íntegra -- é o único truncamento que ficava sem avisar.
                parcial = True
                break
            pagina_cursor = r["next_page"]
        else:
            # o for esgotou o teto de páginas sem a API dizer que tinha terminado —
            # a leitura foi cortada, não completada.
            parcial = True
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {"estado": "recusada", "dias": {}, "parcial": False}
        print(f"[fatura] HTTP {e.code} ao ler o custo", flush=True)
        return {"estado": "erro", "dias": {}, "parcial": False}
    except Exception as e:
        print(f"[fatura] falhou ({type(e).__name__}): {e}", flush=True)
        return {"estado": "erro", "dias": {}, "parcial": False}
    return {"estado": "ok", "dias": dias, "parcial": parcial}
