"""Conteúdo do dia para um artigo: resumo clínico + gancho de redes + dado do gráfico.

Os geradores de IA são injetáveis para testar a montagem/parse sem rede.
"""
import json
import re

SYS_GANCHO = (
    "Você prepara o material de redes sociais de um médico a partir de UM estudo. "
    "Ele produz SÓ REELS (vídeo curto). "
    "Responda SÓ JSON, sem cercas de código, neste formato:\n"
    '{"frase":"...","reels":[{"angulo":"...","apoio":"..."}]}\n'
    "- `frase`: o ACHADO PRINCIPAL em linguagem de paciente, uma frase, sem jargão. "
    "É o texto que vai virar imagem de post: precisa se sustentar sozinho.\n"
    "- `reels`: de 1 a 3 PAUTAS de vídeo. Cada `angulo` é a frase que o médico fala; "
    "cada `apoio` é o dado do estudo que sustenta aquele ângulo (uma linha).\n"
    "REGRAS DAS PAUTAS:\n"
    "1. De 1 a 3. PREFIRA MENOS. Se o estudo só rende uma pauta boa, devolva UMA. "
    "NUNCA invente pauta para fechar número — pauta fraca faz o médico parar de ler o bloco.\n"
    "2. Cada pauta sai de uma PARTE DIFERENTE do estudo (ex.: o grupo comparador, a duração, "
    "o desenho do protocolo). Três jeitos de dizer o mesmo achado é um Reels só, repetido.\n"
    "3. Nada de conselho de produção (formato, horário, hashtag, iluminação) — só ASSUNTO.\n"
    "ÉTICA (CFM, inegociável): não prometa milagre/cura, não garanta resultado, "
    "NÃO promova remédio de receita para leigo (fale do CONCEITO, não do 'use tal remédio'), "
    "sem sensacionalismo, sem chamada para ação ('agende sua consulta'). "
    "Tudo em português do Brasil.")


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
            "Devolva o JSON com a frase e as pautas de Reels deste estudo.")


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
MAX_PASSOS = 6      # passos do roteiro de um Reels
MAX_LIMITES = 6     # itens do bloco "o que nao da pra afirmar"


def _txt(v):
    """String limpa a partir de qualquer coisa que a IA devolva (inclusive None)."""
    return str(v).strip() if v is not None else ""


def _lista(v, limite):
    """Lista de strings limpas a partir do que a IA devolver. Nao levanta se vier
    string, None ou dict no lugar da lista."""
    if not isinstance(v, list):
        return []
    saida = [_txt(x) for x in v]
    return [s for s in saida if s][:limite]


def _kit_vazio():
    return {"frase": "", "paciente": "", "limites": [], "reels": []}


def parse_gancho(bruto):
    """Normaliza o campo `gancho` para
    {"frase", "paciente", "limites", "reels": [{"titulo","gancho","roteiro","apoio"}]}.

    Aceita QUATRO formatos, porque os quatro existem no banco:
      1. JSON novo   -> gancho/roteiro/titulo por pauta + paciente + limites
      2. JSON atual  -> `angulo` vira `gancho`, sem roteiro (o estoque de
         reserva_resumos esta cheio destes; quebrar aqui esvazia o kit de todo
         estudo ja na fila)
      3. texto puro  -> formato legado (classicos/digests antigos); vira uma pauta
      4. lixo/vazio  -> estrutura vazia

    Nunca levanta e nunca devolve None em campo nenhum: isto roda no caminho do PDF
    do assinante, onde uma excecao custa o envio do dia.
    """
    texto = _txt(bruto)
    if not texto:
        return _kit_vazio()
    try:
        dados = json.loads(texto)
    except Exception:
        dados = None
    if not isinstance(dados, dict):
        # JSON que nao fechou (IA estourou o teto de tokens) NAO pode virar pauta:
        # o PDF imprimiria {"frase":... na cara do assinante. Melhor faltar o kit.
        if texto.lstrip()[:1] in ("{", "["):
            return _kit_vazio()
        return {"frase": "", "paciente": "", "limites": [],
                "reels": [{"titulo": "", "gancho": texto, "roteiro": [], "apoio": ""}]}
    reels = []
    for item in (dados.get("reels") or []):
        if not isinstance(item, dict):
            continue
        # `angulo` e o nome antigo de `gancho` -- compatibilidade com o estoque
        gancho = _txt(item.get("gancho")) or _txt(item.get("angulo"))
        if not gancho:
            continue                      # item sem abertura nao rende video nenhum
        reels.append({"titulo": _txt(item.get("titulo")),
                      "gancho": gancho,
                      "roteiro": _lista(item.get("roteiro"), MAX_PASSOS),
                      "apoio": _txt(item.get("apoio"))})
    return {"frase": _txt(dados.get("frase")),
            "paciente": _txt(dados.get("paciente")),
            "limites": _lista(dados.get("limites"), MAX_LIMITES),
            "reels": reels[:MAX_REELS]}


def gerar_conteudo(artigo, gerar_resumo=None, gerar_gancho=None, gerar_grafico_json=None, gerar_titulo=None):
    """Retorna {titulo_pt, resumo, gancho, grafico}. grafico pode ser None."""
    if gerar_resumo is None:
        from resumo_diario import gerar_texto_do_artigo as gerar_resumo
    if gerar_gancho is None:
        from resumo_diario import claude, SONNET
        gerar_gancho = lambda a: claude(SONNET, _prompt_gancho(a), system=SYS_GANCHO, max_tokens=900)
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
