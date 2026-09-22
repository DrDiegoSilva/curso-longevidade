"""Áudio do estudo: roteiro FALADO (Claude) + narração (OpenAI TTS) -> mp3 bytes.

Não lê o resumo escrito (soa robótico) — a IA primeiro escreve um roteiro
conversacional feito PRA OUVIR (sem siglas, sem listas, sem se passar por
ninguém), e só então vira áudio. Decisão do Diego (2026-07-20).
"""
import re
import json
import urllib.request
import config

_SISTEMA = (
    "Você é o NARRADOR do boletim 'Atualização Científica' gravando um áudio que comenta um "
    "estudo para médicos. NÃO se passe por nenhum médico específico, NÃO use nome próprio nem 'eu, "
    "doutor' — fale como apresentador do boletim. Tom natural e conversacional, como uma boa análise "
    "falada — NÃO leia dados em lista. Este é um público médico: ele quer profundidade técnica, não só "
    "a manchete do achado. Cubra em prosa fluida, nesta ordem: o que o estudo investigou (desenho, "
    "população/n), o achado principal com os números que importam (ditos de forma fluida, não em "
    "lista), os efeitos adversos relevantes quando houver, e o que muda (ou não muda) na prática — "
    "inclusive uma ressalva honesta de limitação/nível de evidência quando for o caso (ex.: "
    "observacional não prova causa). ESCREVA PARA SER OUVIDO: evite siglas, escreva por extenso (ex.: "
    "'reposição hormonal' em vez de TRH; 'acidente vascular cerebral' em vez de AVC). Comece com uma "
    "abertura curta (ex.: 'No boletim de hoje...') e feche rápido, sem se despedir em nome de ninguém. "
    "Português do Brasil. Entre 400 e 480 palavras — mais completo que uma manchete, sem virar leitura "
    "de lista. Responda SÓ o texto do áudio."
)


def _limpar(t):
    t = re.sub(r"[*_]", "", t or "")
    t = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️]", "", t)
    return t.strip()


def gerar_roteiro(art, conteudo, gerar_fn=None):
    """Roteiro falado do estudo (string). gerar_fn injetável (testável sem IA)."""
    material = ("Título: " + (conteudo.get("titulo_pt") or art.get("titulo", "")) +
                "\nFonte: " + art.get("fonte", "") + "\n\n" + _limpar(conteudo.get("resumo", "")))
    if gerar_fn:
        return gerar_fn(material)
    import resumo_diario
    return resumo_diario.claude(resumo_diario.SONNET,
                                "Faça o roteiro de áudio deste estudo:\n\n" + material,
                                system=_SISTEMA, max_tokens=1100, acao="audio_roteiro").strip()


def _post_tts(body):
    """POST isolado — ponto de substituição dos testes, mesmo padrão do
    `resumo_diario._post`."""
    req = urllib.request.Request("https://api.openai.com/v1/audio/speech", data=body,
                                 headers={"Authorization": "Bearer " + config.OPENAI_API_KEY,
                                          "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def narrar(texto):
    """Texto -> mp3 bytes via OpenAI TTS. Requer config.OPENAI_API_KEY.

    O TTS é cobrado por caractere e a resposta não traz contagem nenhuma: o que entra no
    ledger é o tamanho do texto REALMENTE enviado — ou seja, já cortado em 4000. Só
    registra quando o POST volta com sucesso: uma falha de rede (ou um 401) não é
    cobrada pela OpenAI, e gravar mesmo assim infla o número que vira insumo de preço —
    mesma disciplina de `resumo_diario.claude()`, que só grava o que a API já cobrou.
    """
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY não configurada")
    falado = (texto or "")[:4000]
    body = json.dumps({"model": config.TTS_MODEL, "voice": config.TTS_VOICE,
                       "input": falado, "response_format": "mp3"}).encode()
    mp3 = _post_tts(body)
    try:
        import ia_custo
        ia_custo.registrar("audio_tts", config.TTS_MODEL, len(falado), 0, 1)
    except Exception as e:
        # se ia_custo quebrar (import, atributo...), a contabilidade não pode
        # nem estourar narração saudável nem mascarar uma exceção real do POST.
        print(f"[custo] não registrei o uso (audio_tts): {e}", flush=True)
    return mp3


def gerar_audio_do_estudo(art, conteudo):
    """Pipeline completo: roteiro (Claude) -> mp3 (OpenAI). Retorna bytes."""
    return narrar(gerar_roteiro(art, conteudo))


_SISTEMA_TRILHA = (
    "Você é o NARRADOR de uma trilha semanal em áudio para médicos assinantes. NÃO se passe por "
    "nenhum médico específico, NÃO use nome próprio nem 'eu, doutor' — fale como apresentador da "
    "trilha. Tom natural e conversacional, como uma boa aula falada — NÃO leia dados em lista. Traga "
    "o essencial desta peça: o que ela ensina, o achado mais importante (com os números que importam, "
    "ditos de forma fluida) e a virada de conduta ou de mentalidade que ela deixa. ESCREVA PARA SER "
    "OUVIDO: evite siglas, escreva por extenso (ex.: 'hormônio do crescimento' em vez de GH). Comece "
    "com uma abertura curta (ex.: 'Nesta semana da trilha...') e feche rápido, sem se despedir em nome "
    "de ninguém. Português do Brasil. No máximo 250 palavras. Responda SÓ o texto do áudio."
)


def gerar_roteiro_peca(peca, gerar_fn=None):
    """Roteiro falado de UMA peça de trilha (string). gerar_fn injetável (testável sem IA) --
    mesmo padrão de `gerar_roteiro`."""
    material = (f"Título: {peca.get('titulo', '')}\nEixo: {peca.get('eixo', '')}\n\n"
                f"{_limpar(peca.get('corpo', ''))}\n\n"
                f"Mentalidade: {_limpar(peca.get('mentalidade', ''))}")
    if gerar_fn:
        return gerar_fn(material)
    import resumo_diario
    return resumo_diario.claude(resumo_diario.SONNET,
                                "Faça o roteiro de áudio desta aula:\n\n" + material,
                                system=_SISTEMA_TRILHA, max_tokens=800, acao="audio_roteiro_trilha").strip()


def gerar_audio_da_peca(peca):
    """Pipeline completo pra uma peça de trilha: roteiro (Claude) -> mp3 (OpenAI)."""
    return narrar(gerar_roteiro_peca(peca))
