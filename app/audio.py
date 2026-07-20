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
    "Você é o NARRADOR do boletim 'Atualização Científica' gravando um áudio curto que comenta um "
    "estudo para médicos. NÃO se passe por nenhum médico específico, NÃO use nome próprio nem 'eu, "
    "doutor' — fale como apresentador do boletim. Tom natural e conversacional, como uma boa análise "
    "falada — NÃO leia dados em lista. Traga o essencial: o que o estudo investigou, o achado mais "
    "importante (com os números que importam, ditos de forma fluida) e o que muda na prática. "
    "ESCREVA PARA SER OUVIDO: evite siglas, escreva por extenso (ex.: 'reposição hormonal' em vez de "
    "TRH; 'acidente vascular cerebral' em vez de AVC). Comece com uma abertura curta (ex.: 'No boletim "
    "de hoje...') e feche rápido, sem se despedir em nome de ninguém. Português do Brasil. No máximo "
    "250 palavras. Responda SÓ o texto do áudio."
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
                                system=_SISTEMA, max_tokens=800).strip()


def narrar(texto):
    """Texto -> mp3 bytes via OpenAI TTS. Requer config.OPENAI_API_KEY."""
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY não configurada")
    body = json.dumps({"model": config.TTS_MODEL, "voice": config.TTS_VOICE,
                       "input": (texto or "")[:4000], "response_format": "mp3"}).encode()
    req = urllib.request.Request("https://api.openai.com/v1/audio/speech", data=body,
                                 headers={"Authorization": "Bearer " + config.OPENAI_API_KEY,
                                          "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def gerar_audio_do_estudo(art, conteudo):
    """Pipeline completo: roteiro (Claude) -> mp3 (OpenAI). Retorna bytes."""
    return narrar(gerar_roteiro(art, conteudo))
