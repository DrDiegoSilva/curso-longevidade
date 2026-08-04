"""Conteúdo do dia para um artigo: resumo clínico + gancho de redes + dado do gráfico.

Os geradores de IA são injetáveis para testar a montagem/parse sem rede.
"""
import json
import re

SYS_GANCHO = (
    "Você escreve uma DICA de como o médico pode abordar este tema nas redes sociais "
    "para os pacientes dele. NÃO é um post pronto e NÃO tem chamada para ação "
    "(nada de 'agende sua consulta'). "
    "Dê (1) um ângulo/gancho para o médico falar e (2) a mensagem-chave em linguagem "
    "simples de paciente. Tom educativo, posicionando o médico como autoridade. "
    "ÉTICA (CFM, inegociável): não prometa milagre/cura, não garanta resultado, "
    "NÃO promova remédio de receita para leigo (fale do CONCEITO, não do 'use tal remédio'), "
    "sem sensacionalismo. Máximo 4 linhas, em português.")


def _prompt_titulo(artigo):
    return (f"Título original (em inglês) de um estudo científico: {artigo.get('titulo','')}\n\n"
            "Reescreva em PORTUGUÊS DO BRASIL: curto e claro para um médico (no máximo ~12 palavras), "
            "com a terminologia correta em pt-BR (ex.: 'lipedema' e NÃO 'lipoedema'; 'menopausa'; "
            "'reposição hormonal'). Responda SÓ o título, sem aspas e sem ponto final.")


def _prompt_titulo_do_texto(artigo):
    """Título pt-BR a partir do TEXTO do estudo (uploads sem título em inglês)."""
    corpo = (artigo.get("resumo") or artigo.get("abstract") or "")[:2500]
    return ("Abaixo está o texto de um estudo científico (pode estar em inglês). "
            "Crie um TÍTULO curto e claro em PORTUGUÊS DO BRASIL para um médico "
            "(no máximo ~12 palavras), com a terminologia correta em pt-BR "
            "(ex.: 'lipedema' e NÃO 'lipoedema'; 'menopausa'; 'reposição hormonal'). "
            "Responda SÓ o título, sem aspas e sem ponto final.\n\nTEXTO:\n" + corpo)


def _prompt_gancho(artigo):
    return (f"Estudo: {artigo.get('titulo','')} ({artigo.get('fonte','')}).\n"
            f"Resumo: {(artigo.get('resumo','') or '')[:900]}\n\n"
            "Escreva a dica de como levar ESTE tema para as redes sociais do médico.")


def _prompt_grafico(artigo):
    return (f"Estudo: {artigo.get('titulo','')}.\n"
            f"Resumo: {(artigo.get('resumo','') or '')[:900]}\n\n"
            "Extraia o achado quantitativo PRINCIPAL como um gráfico de comparação simples "
            "(ex.: intervenção vs controle). Responda SÓ JSON no formato "
            '{"titulo":"Perda de peso (52 sem)","unidade":"%",'
            '"barras":[{"rotulo":"Tirzepatida","valor":20.9},{"rotulo":"Placebo","valor":3.1,"comparador":true}],'
            '"chamada":"6x mais eficaz que o placebo",'
            '"bracos":[{"nome":"Tirzepatida","dose":"15 mg/sem","n":"630"},{"nome":"Placebo","dose":"—","n":"643"}]} '
            "com 2 a 4 barras. Regras: marque \"comparador\":true na barra que é o COMPARADOR "
            "(placebo, controle, tratamento padrão); se não houver comparador claro, omita a flag em todas. "
            '"chamada" = UMA frase curta com o efeito RELATIVO citando o comparador pelo nome '
            '(ex.: "6x mais eficaz que a insulina") — só se o resumo permitir calcular; senão omita. '
            '"bracos" = braços/doses do estudo com o n de cada um — só se o resumo trouxer; senão omita. '
            "Se NÃO houver um número comparável claro, responda apenas: null. "
            "NÃO invente números — use só o que está no resumo.")


def _parse_grafico(texto):
    if not texto:
        return None
    if texto.strip().lower().startswith("null"):
        return None
    import jsonx
    bruto = jsonx.primeiro_objeto(texto)
    if not bruto:
        return None
    try:
        g = json.loads(bruto)
    except Exception:
        return None
    barras = [_barra(b) for b in (g.get("barras") or [])
              if isinstance(b, dict) and isinstance(b.get("valor"), (int, float)) and b.get("rotulo")]
    if not barras:
        return None
    out = {"titulo": g.get("titulo", ""), "unidade": g.get("unidade", ""), "barras": barras[:4]}
    chamada = str(g.get("chamada") or "").strip()
    if chamada:
        out["chamada"] = chamada
    bracos = [_braco(b) for b in (g.get("bracos") or [])
              if isinstance(b, dict) and str(b.get("nome") or "").strip()]
    if bracos:
        out["bracos"] = bracos[:8]
    return out


def _verdadeiro(v):
    return v is True or str(v).strip().lower() in ("true", "1", "sim", "yes")


def _barra(b):
    """Barra normalizada. A flag `comparador` é OPCIONAL — conteúdo antigo (sem
    ela) segue válido e o PDF cai no visual de antes."""
    nova = {"rotulo": b["rotulo"], "valor": b["valor"]}
    if _verdadeiro(b.get("comparador")):
        nova["comparador"] = True
    return nova


def _braco(b):
    """Braço/dose do estudo: nome + dose + n (strings; n pode vir número)."""
    nova = {"nome": str(b["nome"]).strip()}
    for k in ("dose", "n"):
        v = str(b.get(k) or "").strip()
        if v:
            nova[k] = v
    return nova


MAX_REELS = 3


def _txt(v):
    """String limpa a partir de qualquer coisa que a IA devolva (inclusive None)."""
    return str(v).strip() if v is not None else ""


def parse_gancho(bruto):
    """Normaliza o campo `gancho` para {"frase": str, "reels": [{"angulo","apoio"}]}.

    Aceita tres formatos, porque os tres existem no banco:
      1. JSON novo  -> {"frase": ..., "reels": [...]}
      2. texto puro -> formato LEGADO (reserva/classicos/digests antigos); vira um reel
      3. lixo/vazio -> estrutura vazia, sem levantar

    Nunca levanta e nunca devolve None em campo nenhum: isto roda no caminho do PDF
    do assinante, onde uma excecao custa o envio do dia.
    """
    texto = _txt(bruto)
    if not texto:
        return {"frase": "", "reels": []}
    try:
        dados = json.loads(texto)
    except Exception:
        dados = None
    if not isinstance(dados, dict):
        return {"frase": "", "reels": [{"angulo": texto, "apoio": ""}]}
    reels = []
    for item in (dados.get("reels") or []):
        if not isinstance(item, dict):
            continue
        angulo = _txt(item.get("angulo"))
        if not angulo:
            continue                      # item sem angulo nao rende video nenhum
        reels.append({"angulo": angulo, "apoio": _txt(item.get("apoio"))})
    return {"frase": _txt(dados.get("frase")), "reels": reels[:MAX_REELS]}


def gerar_conteudo(artigo, gerar_resumo=None, gerar_gancho=None, gerar_grafico_json=None, gerar_titulo=None):
    """Retorna {titulo_pt, resumo, gancho, grafico}. grafico pode ser None."""
    if gerar_resumo is None:
        from resumo_diario import gerar_texto_do_artigo as gerar_resumo
    if gerar_gancho is None:
        from resumo_diario import claude, SONNET
        gerar_gancho = lambda a: claude(SONNET, _prompt_gancho(a), system=SYS_GANCHO, max_tokens=500)
    if gerar_grafico_json is None:
        from resumo_diario import claude, HAIKU
        gerar_grafico_json = lambda a: claude(HAIKU, _prompt_grafico(a), max_tokens=300)
    if gerar_titulo is None:
        from resumo_diario import claude, HAIKU
        gerar_titulo = lambda a: claude(HAIKU, _prompt_titulo(a), max_tokens=80)
    titulo_pt = (gerar_titulo(artigo) or "").strip().strip('"').strip() or artigo.get("titulo", "")
    return {
        "titulo_pt": titulo_pt,
        "resumo": gerar_resumo(artigo),
        "gancho": gerar_gancho(artigo),
        "grafico": _parse_grafico(gerar_grafico_json(artigo)),
    }
