"""Triagem por IA: classifica os artigos da semana como ENTRA/LIXO + score.

Reaproveita a voz rigorosa do triador que já existia no app. A chamada à IA é
injetável (`llm`) para testar o parser sem rede.
"""
import json
import re

SYS = ("Você é triador de literatura médica, MUITO rigoroso em cortar ruído. "
       "Prefere falso-negativo a falso-positivo.")


def _norm_tags(tags):
    """Lista de string minúscula, deduplicada; qualquer coisa fora disso -> []."""
    if not isinstance(tags, list):
        return []
    out, seen = [], set()
    for t in tags:
        if isinstance(t, str):
            t = t.strip().lower()
            if t and t not in seen:
                seen.add(t)
                out.append(t)
    return out


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
        "Para cada ENTRA, em 'tags' liste 3-6 palavras-chave (moléculas/intervenções + o tópico central), "
        "minúsculas, em português, usando o NOME COMUM da molécula (ex.: 'retatrutida', não 'ly3437943'). "
        'Responda SÓ JSON: [{"i":0,"classe":"ENTRA","score":8,"tags":["retatrutida","glp1","perda de peso"]},'
        '{"i":1,"classe":"LIXO","score":0}]')


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
            a["tags"] = _norm_tags(c.get("tags"))
            out.append(a)
    return out


def triar(artigos, tema, llm=None):
    """Retorna os artigos ENTRA (com 'tema' e 'score'). llm(prompt)->texto injetável."""
    if not artigos:
        return []
    if llm is None:
        from resumo_diario import claude, HAIKU
        llm = lambda p: claude(HAIKU, p, system=SYS, max_tokens=900, acao="triagem")
    return _parse(llm(_prompt(artigos, tema)), artigos, tema)


def _prompt_tags(artigos):
    lista = "\n".join(
        f"[{i}] {a.get('titulo','')} | {(a.get('resumo','') or a.get('abstract','') or '')[:500]}"
        for i, a in enumerate(artigos))
    return (
        "Para CADA estudo abaixo, liste 3-6 palavras-chave (moléculas/intervenções + o tópico central), "
        "minúsculas, em português, usando o nome comum da molécula.\n"
        f"{lista}\n\n"
        'Responda SÓ JSON: [{"i":0,"tags":["retatrutida","glp1"]},{"i":1,"tags":["menopausa"]}]')


def taggear(artigos, llm=None):
    """Só tags (sem ENTRA/LIXO) — p/ backfill do estoque. Retorna {i: [tags]}."""
    if not artigos:
        return {}
    if llm is None:
        from resumo_diario import claude, HAIKU
        llm = lambda p: claude(HAIKU, p, system=SYS, max_tokens=700, acao="tags")
    import jsonx
    bruto = jsonx.primeiro_array(llm(_prompt_tags(artigos)))
    try:
        cls = json.loads(bruto) if bruto else []
    except Exception:
        cls = []
    return {c["i"]: _norm_tags(c.get("tags")) for c in cls
            if isinstance(c, dict) and isinstance(c.get("i"), int)}


def _prompt_metadados(titulo, texto, temas):
    return ("Extraia os metadados do estudo abaixo.\n"
            f"Áreas possíveis: {', '.join(temas)}\n\n"
            f"Título: {titulo}\n"
            f"Texto: {(texto or '')[:3000]}\n\n"
            'Responda SÓ JSON: {"area":"<uma das áreas, ou vazio se nenhuma couber>",'
            '"fonte":"<nome da revista>","data":"<AAAA-MM ou AAAA>"}\n'
            "Deixe vazio o campo que o texto não disser. Não invente.")


def extrair_metadados(titulo, texto, temas, llm=None):
    """Área + revista + data numa chamada só (antes a área ia numa chamada e o
    resto em outra, sobre o MESMO texto).

    O DOI NÃO vem daqui de propósito: ele tem formato fixo e sai por regex em
    `curadoria.doi_do_texto` -- identificador é justamente o campo onde uma
    alucinação passa despercebida e vira link quebrado no PDF do assinante.

    Nunca levanta e nunca inventa área: só devolve chave que estava na lista. O
    upload do estudo não pode morrer porque a IA teve um soluço."""
    vazio = {"area": "", "fonte": "", "data": ""}
    if llm is None:
        from resumo_diario import claude, HAIKU
        llm = lambda p: claude(HAIKU, p, system=SYS, max_tokens=200, acao="metadados")
    try:
        import jsonx
        bruto = jsonx.primeiro_objeto(llm(_prompt_metadados(titulo, texto, temas)) or "")
        d = json.loads(bruto) if bruto else {}
    except Exception as e:
        print(f"[triage] extrair metadados falhou: {e}", flush=True)
        return vazio
    if not isinstance(d, dict):
        return vazio
    area = str(d.get("area") or "").strip().lower()
    # Casa a chave mais longa primeiro: evita que "Hormonal" ganhe de uma area
    # futura "Hormonal feminino" so por vir antes na lista.
    escolhida = next((t for t in sorted(temas, key=len, reverse=True) if t.lower() in area), "")
    return {"area": escolhida,
            "fonte": str(d.get("fonte") or "").strip(),
            "data": str(d.get("data") or "").strip()}
