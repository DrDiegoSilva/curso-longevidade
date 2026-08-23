# Marcar estudos já enviados no picker de trocar estudo — design

**Data:** 2026-08-23
**Status:** spec aprovada no brainstorm, aguardando plano de implementação

## O problema

Diego, olhando o picker do 🔁 (botão "trocar o estudo de amanhã" na tela `/revisar` das
18h — item 23): *"dentro dos estudos que ficam para serem trocados tem que marcar os que
ja foram enviados."* O picker (`review_web.pagina_trocar_estudo`) lista estudos da reserva
+ candidatos agrupados por tema; hoje não há nenhum jeito de saber, olhando a lista, se um
estudo já apareceu num PDF diário antes — quem escolhe pode repetir sem perceber.

**Achado lateral no brainstorm (não faz parte deste pedido):** Diego notou que a nota
("score") de todos os itens do picker aparece como 0. Investigado: é estoque antigo da
reserva — a coluna `score` de `reserva_resumos` foi adicionada numa migração posterior
(`db.py:346`, `DEFAULT 0`) e não existe backfill que recalcule os registros de antes dela.
Diego confirmou que é isso mesmo e decidiu **não corrigir agora** — fica fora do escopo
desta spec.

## O que muda

- **Cada alternativa do picker (reserva + candidato) passa a saber se já foi enviada** —
  cruzando com a tabela `digests` (histórico real de tudo que já saiu, qualquer data,
  qualquer tema).
- **Dentro de cada card de tema**, os estudos disponíveis (nunca enviados) continuam
  aparecendo primeiro, como hoje. Se houver algum já enviado naquele tema, entra um
  **sub-bloco separado, abaixo**, com cabeçalho "⚠️ Já enviados" — mesma lista, mesmo
  botão "Usar este amanhã" (continua escolhível de propósito, não é bloqueado).
- Cada item já enviado mostra a data: "⚠️ já enviado em `AAAA-MM-DD`" — a data MAIS
  ANTIGA em que aquele estudo apareceu (se saiu mais de uma vez, mostra a primeira). Fica
  em ISO cru de propósito: o picker é tela interna (só o Diego usa), não o PDF nem o
  portal do assinante — não introduz um terceiro formato de data numa superfície que já
  tem inconsistência conhecida em telas voltadas pro assinante (ver
  [[item42-masthead-sem-marca]]).

## Por que casar por DOI primeiro, título como reserva

A reserva guarda o título em **português** (`titulo_pt`); o candidato guarda em
**inglês** (`titulo`, que é o original — `curadoria_candidatos` não tem coluna
`titulo_original` separada, o `titulo` dele já é o original). Comparar só por título
bateria errado boa parte das vezes entre os dois tipos. DOI não tem esse problema —
é o mesmo valor não importa a língua. Por isso: casa por DOI quando os dois lados têm um
(normalizado: `strip().lower()`); sem DOI de um dos lados, cai para título normalizado
(mesma normalização) comparado contra `titulo_original` OU `titulo_pt` do digest — cobre
os dois idiomas em vez de arriscar comparar PT com EN.

## Lógica de casamento

Nova função `daily.marcar_ja_enviados(alts)`, chamada dentro de `montar_alternativas`
depois do corte em `ALTERNATIVAS_MAX`:

```python
def _normalizar_titulo(t):
    return re.sub(r"\s+", " ", (t or "").strip().lower())


def marcar_ja_enviados(alts):
    """Anota cada alternativa com `ja_enviado_em` (data ISO mais antiga em que aquele
    estudo já saiu) ou None. Casa por DOI primeiro (sem risco de traducao); sem DOI dos
    dois lados, cai pro titulo normalizado contra titulo_original OU titulo_pt do digest
    -- a reserva guarda titulo em PT, o candidato em EN, entao um so' dos dois campos
    erraria metade dos casos."""
    import db
    por_doi, por_titulo = {}, {}
    for d in db.listar_digests():
        data = d.get("data", "")
        doi = (d.get("doi") or "").strip().lower()
        if doi and (doi not in por_doi or data < por_doi[doi]):
            por_doi[doi] = data
        for campo in ("titulo_original", "titulo_pt"):
            t = _normalizar_titulo(d.get(campo))
            if t and (t not in por_titulo or data < por_titulo[t]):
                por_titulo[t] = data
    for a in alts:
        doi = (a.get("doi") or "").strip().lower()
        a["ja_enviado_em"] = por_doi.get(doi) if doi else None
        if not a["ja_enviado_em"]:
            a["ja_enviado_em"] = por_titulo.get(_normalizar_titulo(a.get("titulo")))
    return alts
```

`montar_alternativas` precisa passar a incluir `"doi"` em cada dict de alternativa (hoje
não inclui) — pega de `x.get("doi", "")` tanto pro lado da reserva quanto do candidato,
igual aos outros campos (`fonte`, `tema`).

`db.listar_digests()` já existe (`SELECT * FROM digests`, sem filtro) — não precisa de
função nova no `db.py`. A tabela é pequena (~1 linha por tema por dia útil, ~260/ano) —
uma leitura completa por carregamento do picker é barata, sem N+1.

## HTML do picker (`app/review_web.py`)

`_item_troca` ganha o aviso condicional:

```python
def _item_troca(a, tok):
    esc = _html.escape
    aviso = (f'<br><small style="color:#9c3226">⚠️ já enviado em {esc(a["ja_enviado_em"])}</small>'
              if a.get("ja_enviado_em") else "")
    return (f'<li style="margin:12px 0">'
            f'<form method="post" action="/revisar/{tok}" '
            f'style="display:flex;gap:10px;align-items:center;justify-content:space-between">'
            f'<span><b>{esc(a["titulo"])}</b><br>'
            f'<small style="color:#6b7a76">{esc(a["fonte"])} · '
            f'nota {esc(str(a["score"]))} · {esc(a["tipo"])}</small>{aviso}</span>'
            f'<input type="hidden" name="acao" value="trocar_confirmar">'
            f'<input type="hidden" name="tipo" value="{esc(a["tipo"])}">'
            f'<input type="hidden" name="id" value="{esc(str(a["id"]))}">'
            f'<button type="submit">Usar este amanhã</button>'
            f'</form></li>')
```

`pagina_trocar_estudo` separa `itens` de cada tema em `disponiveis`/`enviados` antes de
montar o card:

```python
        for t in temas:
            itens = por_tema.get(t, [])
            if not itens:
                corpo_card = '<p style="color:#6b7a76">Nada neste tema.</p>'
            else:
                disponiveis = [a for a in itens if not a.get("ja_enviado_em")]
                enviados = [a for a in itens if a.get("ja_enviado_em")]
                corpo_card = (f'<ul style="list-style:none;padding:0">'
                              + "".join(_item_troca(a, tok) for a in disponiveis) + "</ul>"
                              ) if disponiveis else '<p style="color:#6b7a76">Nada disponível neste tema.</p>'
                if enviados:
                    corpo_card += (
                        '<p style="color:#9c3226;font-weight:600;margin:14px 0 4px">'
                        '⚠️ Já enviados</p>'
                        '<ul style="list-style:none;padding:0">'
                        + "".join(_item_troca(a, tok) for a in enviados) + "</ul>")
```

O resto de `pagina_trocar_estudo` (agrupamento por tema, `<details>`, contagem no
`<summary>`) não muda — a contagem `({len(itens)})` continua sendo o TOTAL do tema
(disponíveis + já enviados), não só os disponíveis. Decisão explícita: é o mesmo número
que já existe hoje, menos uma mudança para não confundir quem já está acostumado com ele.

## Onde mexe

| Arquivo | O quê |
|---|---|
| `app/daily.py` | `montar_alternativas` (inclui `doi` nas alternativas, chama `marcar_ja_enviados`), `marcar_ja_enviados` e `_normalizar_titulo` novas |
| `app/review_web.py` | `_item_troca` (aviso condicional), `pagina_trocar_estudo` (separa disponíveis/enviados dentro de cada card de tema) |

`app/db.py`, `app/curadoria.py`, `app/content.py` não são tocados — só leitura do que já
existe.

## Testes

- `marcar_ja_enviados`: casa por DOI (case-insensitive, com espaço a mais); casa por
  título quando falta DOI de um dos lados, testando os dois campos do digest
  (`titulo_original` e `titulo_pt`); quando o mesmo DOI/título aparece em mais de um
  digest, guarda a data MAIS ANTIGA; item sem casamento nenhum recebe `None`; DOI/título
  vazios não estouram exceção nem casam à toa (string vazia não é chave).
- `montar_alternativas`: alternativa da reserva e do candidato carregam `doi` no dict.
- `_item_troca`: renderiza o aviso quando `ja_enviado_em` está presente; não renderiza
  nada quando ausente (sem `<br>` órfão).
- `pagina_trocar_estudo`: tema com só disponíveis não mostra o cabeçalho "Já enviados";
  tema com só já-enviados mostra "Nada disponível" + o sub-bloco; tema misto mostra as
  duas partes, disponíveis antes; o botão "Usar este amanhã" continua presente nos itens
  já enviados (não fica só-leitura).

## Fora de escopo

- Recalcular a nota (`score`) zerada do estoque antigo — decisão do Diego, fica pra depois.
- Qualquer mudança na lógica de troca em si (`trocar_estudo_amanha`) — só a marcação
  visual no picker.
- Impedir a escolha de um estudo já enviado — continua permitido, de propósito.
