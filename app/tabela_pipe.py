"""Tabela de cano (`| a | b |` com 2ª linha separadora) -> `<table>`.

Mora fora do `pdf.py` e do `pdf_trilha.py` porque os DOIS precisam dela e por
motivos diferentes: a trilha recebe markdown escrito à mão, e o resumo do estudo
diário recebe o que o modelo resolver emitir -- e ele resolve usar tabela mesmo
quando o prompt pede formato de WhatsApp. Enquanto só a trilha sabia ler tabela,
o assinante recebeu `| População | Proteína/dia |` impresso literal no PDF.

O que muda entre os dois é apenas a marcação inline dentro da célula
(`**negrito**` na trilha, `*negrito*` do WhatsApp no resumo), então ela entra por
parâmetro: `inline(texto_cru) -> html`. Esse callable é quem faz o escape, e é
por isso que a segurança não depende deste módulo -- aqui só se decide onde ficam
as tags de tabela; o CONTEÚDO de toda célula passa por `inline` antes de sair.
"""
import re

_SEPARADOR_RE = re.compile(r"^:?-{1,}:?$")


def eh_linha(linha):
    """Linha entre canos. Marcadores como `|` não são especiais em HTML, então
    olhar o texto cru aqui não abre brecha nenhuma."""
    l = (linha or "").strip()
    return len(l) >= 2 and l.startswith("|") and l.endswith("|")


def celulas(linha):
    return [c.strip() for c in linha.strip()[1:-1].split("|")]


def eh_separadora(linha):
    if not eh_linha(linha):
        return False
    cels = celulas(linha)
    return bool(cels) and all(_SEPARADOR_RE.match(c) for c in cels)


def eh_tabela(linhas):
    """Exige a linha separadora na 2ª posição. Sem ela, uma frase solta entre
    canos viraria uma tabela de uma célula só e o texto sumiria da página."""
    return (len(linhas) >= 2 and all(eh_linha(l) for l in linhas)
            and eh_separadora(linhas[1]))


def html(linhas, inline, num=None):
    """`linhas` já validadas por `eh_tabela`. `inline(texto)` escapa e marca cada
    célula. `num(texto_cru)` é opcional e só decide a classe CSS de alinhamento à
    direita -- recebe o texto ANTES do escape, para poder olhar a marcação."""
    cab = "".join(f"<th>{inline(c)}</th>" for c in celulas(linhas[0]))
    corpo = []
    for linha in linhas[2:]:
        tds = []
        for c in celulas(linha):
            classe = ' class="num"' if (num and num(c)) else ""
            tds.append(f"<td{classe}>{inline(c)}</td>")
        corpo.append("<tr>" + "".join(tds) + "</tr>")
    return (f"<table><thead><tr>{cab}</tr></thead>"
            f"<tbody>{''.join(corpo)}</tbody></table>")
