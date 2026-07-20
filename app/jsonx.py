"""Extração robusta de JSON de respostas de LLM.

Modelos às vezes respondem com ```json ...```, texto antes/depois, ou uma
"Justificativa" com `[0]`/`[3]` que quebra um regex ganancioso `\\[.*\\]`.
Aqui a gente acha o PRIMEIRO array/objeto BALANCEADO (contando profundidade e
ignorando colchetes dentro de strings). Puro/testável.
"""


def _primeiro_balanceado(texto, ab, fe):
    s = texto or ""
    ini = s.find(ab)
    if ini < 0:
        return None
    depth = 0
    em_string = False
    escape = False
    for j in range(ini, len(s)):
        ch = s[j]
        if em_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                em_string = False
            continue
        if ch == '"':
            em_string = True
        elif ch == ab:
            depth += 1
        elif ch == fe:
            depth -= 1
            if depth == 0:
                return s[ini:j + 1]
    return None


def primeiro_array(texto):
    """Substring do primeiro array JSON balanceado, ou None."""
    return _primeiro_balanceado(texto, "[", "]")


def primeiro_objeto(texto):
    """Substring do primeiro objeto JSON balanceado, ou None."""
    return _primeiro_balanceado(texto, "{", "}")
