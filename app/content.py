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
            '{"titulo":"Perda de peso (52 sem)","unidade":"%","barras":[{"rotulo":"Tirzepatida","valor":20.9},{"rotulo":"Placebo","valor":3.1}]} '
            "com 2 a 4 barras. Se NÃO houver um número comparável claro, responda apenas: null. "
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
    barras = [b for b in (g.get("barras") or [])
              if isinstance(b.get("valor"), (int, float)) and b.get("rotulo")]
    if not barras:
        return None
    return {"titulo": g.get("titulo", ""), "unidade": g.get("unidade", ""), "barras": barras[:4]}


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
