"""Triagem por IA: classifica os artigos da semana como ENTRA/LIXO + score.

Reaproveita a voz rigorosa do triador que já existia no app. A chamada à IA é
injetável (`llm`) para testar o parser sem rede.
"""
import json
import re

SYS = ("Você é triador de literatura médica, MUITO rigoroso em cortar ruído. "
       "Prefere falso-negativo a falso-positivo.")


def _prompt(artigos, tema):
    lista = "\n".join(
        f"[{i}] {a.get('titulo','')} | {a.get('fonte','')} | {(a.get('resumo','') or '')[:500]}"
        for i, a in enumerate(artigos))
    return (
        f"Tema do médico: {tema}. Artigos da semana:\n{lista}\n\n"
        "Classifique CADA um para a prática clínica NESTE tema. "
        "ENTRA = o FOCO do estudo é o tema, com dado clínico relevante (muda ou informa conduta) "
        "e desenho forte (ensaio clínico, meta-análise, revisão sistemática ou diretriz). "
        "LIXO = fora da área; animal/cultura celular; pediatria; cirurgia não relacionada; "
        "OU quando o tema aparece só como comorbidade/fator secundário e não é o objeto central. "
        "Na dúvida, LIXO — melhor cortar do que enviar ruído. "
        "Dê um score de importância clínica de 0 a 10 para os que ENTRAM. "
        'Responda SÓ JSON: [{"i":0,"classe":"ENTRA","score":8},{"i":1,"classe":"LIXO","score":0}]')


def _parse(texto, artigos, tema):
    import jsonx
    bruto = jsonx.primeiro_array(texto)
    if not bruto:
        return []
    try:
        cls = json.loads(bruto)
    except Exception:
        return []
    out = []
    for c in cls:
        i = c.get("i")
        if c.get("classe") == "ENTRA" and isinstance(i, int) and 0 <= i < len(artigos):
            a = dict(artigos[i])
            a["tema"] = tema
            try:
                a["score"] = float(c.get("score", 5))
            except (TypeError, ValueError):
                a["score"] = 5.0
            out.append(a)
    return out


def triar(artigos, tema, llm=None):
    """Retorna os artigos ENTRA (com 'tema' e 'score'). llm(prompt)->texto injetável."""
    if not artigos:
        return []
    if llm is None:
        from resumo_diario import claude, HAIKU
        llm = lambda p: claude(HAIKU, p, system=SYS, max_tokens=900)
    return _parse(llm(_prompt(artigos, tema)), artigos, tema)
