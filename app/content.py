"""Conteúdo do dia para um artigo: resumo clínico + gancho de redes + dado do gráfico.

Os geradores de IA são injetáveis para testar a montagem/parse sem rede.
"""
import json
import re

SYS_GANCHO = (
    "Você prepara o material de redes sociais de um médico a partir de UM estudo. "
    "Ele trata obesidade, menopausa e reposição hormonal, e produz SÓ REELS (vídeo curto). "
    "Responda SÓ JSON, sem cercas de código, neste formato:\n"
    '{"frase":"...","paciente":"...","limites":["..."],'
    '"reels":[{"titulo":"...","gancho":"...","roteiro":["...","..."],"apoio":"..."}]}\n'
    "\n"
    "REGRA CENTRAL DAS PAUTAS — o público é o PACIENTE do médico, não o médico. O paciente "
    "não lê estudo e não se interessa por desenho de pesquisa. Cada pauta ABRE numa dor que "
    "ele reconhece em si mesmo e TERMINA apontando para algo que se resolve com acompanhamento "
    "médico. O estudo é a prova que sustenta, nunca a manchete. É PROIBIDO fazer pauta sobre "
    "metodologia, grupo comparador, tamanho de amostra ou tempo de seguimento — isso é conversa "
    "de médico para médico e faz o paciente rolar o feed.\n"
    "\n"
    "- `frase`: o achado em linguagem de paciente, UMA frase que se sustenta sozinha como "
    "imagem de post.\n"
    "- `paciente`: como o MÉDICO explica esse achado ao paciente no consultório — 2 a 4 frases, "
    "linguagem de conversa, incluindo a ressalva honesta que mantém a confiança. É para o médico "
    "ler antes da consulta, não para postar.\n"
    "- `limites`: 3 a 5 itens do que NÃO pode ser dito sobre ESTE estudo — específicos dele, "
    "nunca regras genéricas. Puxe do próprio texto: amostra pequena, uso fora de bula, desfecho "
    "que é questionário e não exame, limitação que os autores declararam. Somado ao que o CFM "
    "veda: promessa de resultado, antes/depois, promoção de medicamento de receita a leigo, "
    "convocação para consulta.\n"
    "- `reels`: de 1 a 3 pautas. PREFIRA MENOS — se o estudo só sustenta uma dor de verdade, "
    "devolva UMA. Pauta inventada para fechar número faz o médico parar de ler o bloco. Cada "
    "pauta sai de uma DOR DIFERENTE, nunca do mesmo assunto com outras palavras.\n"
    "  - `titulo`: 3 a 6 palavras nomeando o assunto da pauta, para o médico achar de relance.\n"
    "  - `gancho`: a frase EXATA dos 3 primeiros segundos do vídeo. Fala com o paciente na "
    "segunda pessoa, nomeia a dor dele, e NÃO cita o estudo.\n"
    "  - `roteiro`: 3 a 5 passos NA ORDEM DE GRAVAÇÃO, cada um uma linha do que o médico diz. "
    "Um dos passos, sempre, é a ressalva honesta. O último fecha na dor ou aponta o caminho. "
    "Quem lê tem que conseguir gravar sem saber nada de medicina. "
    "ESCREVA CADA PASSO EM PORTUGUÊS SIMPLES, como quem instrui uma pessoa: 'Comece contando "
    "que...', 'Explique que...', 'Diga a ressalva:...', 'Termine assim:...'. É PROIBIDO jargão "
    "de marketing — não escreva 'nomeia a cena', 'vira a chave', 'prova por baixo', 'quebra de "
    "padrão' nem 'CTA'; quem lê é médico ou social media, não publicitário.\n"
    "  - `apoio`: o dado do estudo que sustenta aquela pauta, em uma linha. É para o médico "
    "conferir, não para ser dito no vídeo.\n"
    "\n"
    "ÉTICA (CFM, inegociável): não prometa milagre/cura, não garanta resultado, "
    "NÃO promova remédio de receita para leigo (fale do CONCEITO, não do 'use tal remédio'), "
    "sem sensacionalismo, sem chamada para ação ('agende sua consulta'). "
    "Nunca invente número que não esteja na fonte. Tudo em português do Brasil.")


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
    string, None ou dict no lugar da lista. Item que nao e string (dict, numero...)
    e descartado -- senao o repr do Python (ex.: {'item': 'x'}) vaza pro PDF."""
    if not isinstance(v, list):
        return []
    saida = [_txt(x) for x in v if isinstance(x, str)]
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
    if texto.strip().lower().startswith("null"):
        return _kit_vazio()
    # A IA as vezes responde com cerca de codigo (```json ... ```) ou preambulo
    # ("Segue o JSON pedido:") antes do objeto -- o mesmo problema que _parse_grafico
    # ja resolve com jsonx.primeiro_objeto. Sem isto, json.loads(texto) falhava e o
    # JSON inteiro (cerca incluida) virava UMA pauta impressa cru no PDF.
    import jsonx
    bruto_json = jsonx.primeiro_objeto(texto)
    dados = None
    if bruto_json:
        try:
            dados = json.loads(bruto_json)
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
    reels_bruto = dados.get("reels")
    for item in (reels_bruto if isinstance(reels_bruto, list) else []):
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
        # 2500, nao 900: a saida real medida (frase + paciente + limites + 2 pautas com
        # roteiro) deu 934 tokens. Com o teto antigo o JSON chega cortado e o kit some.
        gerar_gancho = lambda a: claude(SONNET, _prompt_gancho(a), system=SYS_GANCHO, max_tokens=2500)
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


# ── Kit editável na tela das 18h ─────────────────────────────────────────────
_CAMPOS_KIT = ("kit_frase", "kit_paciente", "kit_limites", "kit_reel_titulo",
               "kit_reel_gancho", "kit_reel_roteiro", "kit_reel_apoio")


def kit_do_form(form):
    """Remonta o kit a partir do formulário do `/revisar`. `form` é o dict de LISTAS do
    `parse_qs` — as pautas usam nomes repetidos e voltam na ordem.

    Devolve **None** quando o formulário não traz campo de kit nenhum: POST antigo ou
    forjado não pode APAGAR o kit por omissão. Campos presentes e vazios, sim, são uma
    decisão dele de apagar.

    Pauta sem título é descartada — é assim que ele tira uma pauta que não presta.
    """
    if not any(c in form for c in _CAMPOS_KIT):
        return None
    um = lambda k: (form.get(k) or [""])[0]
    linhas = lambda t: [l.strip() for l in (t or "").splitlines() if l.strip()]
    tits = form.get("kit_reel_titulo") or []
    gans = form.get("kit_reel_gancho") or []
    rots = form.get("kit_reel_roteiro") or []
    aps = form.get("kit_reel_apoio") or []
    pega = lambda lst, i: lst[i].strip() if i < len(lst) else ""
    reels = []
    for i, t in enumerate(tits):
        if not (t or "").strip():
            continue
        reels.append({"titulo": t.strip(), "gancho": pega(gans, i),
                      "roteiro": linhas(rots[i] if i < len(rots) else ""),
                      "apoio": pega(aps, i)})
    return {"frase": um("kit_frase").strip(), "paciente": um("kit_paciente").strip(),
            "limites": linhas(um("kit_limites")), "reels": reels}
