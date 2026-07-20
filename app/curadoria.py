"""Curadoria/Reserva 2026 — banco privado de resumos prontos (NÃO publica no arquivo).

Fluxo:
  1. varrer(): busca real no Europe PMC (5 temas, peso em Obesidade) + triagem por
     IA HAIKU (barata) -> candidatos triados, deduplicados, com score.
  2. gerar_perguntas(): HAIKU escreve, p/ cada candidato, a PERGUNTA clínica que ele
     responde -> o Diego seleciona rápido pela pergunta.
  3. gerar_resumo(): dos SELECIONADOS, escreve o resumo no PADRÃO DE QUALIDADE do app
     (gerador normal — mantém a qualidade), não Haiku.
As chamadas de rede/IA são injetáveis (buscar_fn/triar_fn/llm_fn/geradores) p/ teste.
"""
import os
import json
import re
from datetime import date

# Peso em Obesidade (novas moléculas de emagrecimento = prioridade). ~50 no total.
CAPS = {"Obesidade": 20, "Hormonal": 9, "Performance": 8, "Longevidade": 7, "Lipedema": 6}
_CFG_PATH = os.path.join(os.path.dirname(__file__), "temas_config.json")


def _cfg():
    with open(_CFG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _chave(a):
    return (a.get("doi") or a.get("url") or a.get("titulo") or "").strip().lower()


def _normalizar(a, tema):
    return {
        "tema": tema,
        "titulo": (a.get("titulo") or "").strip(),
        "fonte": a.get("fonte") or "",
        "data": a.get("data") or "",
        "doi": a.get("doi") or "",
        "url": a.get("url") or "",
        "abstract": (a.get("resumo") or "")[:2500],
        "score": float(a.get("score", 5) or 0),
        "chave": _chave(a),
    }


def varrer(desde, ate, caps=None, buscar_fn=None, triar_fn=None):
    """Por tema: busca (Europe PMC etc.) -> triagem IA -> top(cap) por score, dedup global.
    Retorna lista de candidatos normalizados. buscar_fn/triar_fn injetáveis (teste sem rede)."""
    caps = caps or CAPS
    if buscar_fn is None:
        import sources
        buscar_fn = sources.search_all
    if triar_fn is None:
        import triage
        triar_fn = triage.triar
    cfg = _cfg()
    vistos, out = set(), []
    for nome, meta in cfg["temas"].items():
        cap = int(caps.get(nome, 6))
        if cap <= 0:
            continue
        try:
            arts = buscar_fn(meta.get("query", ""), desde, ate)
            bons = []
            for k in range(0, len(arts), 20):        # tria em lotes p/ a resposta não estourar tokens
                bons += triar_fn(arts[k:k + 20], nome)
        except Exception as e:
            print(f"[curadoria] {nome} falhou: {e}", flush=True)
            continue
        bons.sort(key=lambda x: x.get("score", 0), reverse=True)
        n = 0
        for a in bons:
            k = _chave(a)
            if not k or k in vistos:
                continue
            vistos.add(k)
            out.append(_normalizar(a, nome))
            n += 1
            if n >= cap:
                break
    return out


# ── Perguntas (HAIKU barato) ──
def _prompt_perguntas(cands):
    lista = "\n".join(
        f"[{i}] {c.get('titulo','')} | {(c.get('abstract') or c.get('resumo') or '')[:400]}"
        for i, c in enumerate(cands))
    return (
        "Para CADA estudo abaixo, escreva em UMA linha, em português claro, a PERGUNTA "
        "CLÍNICA que ele responde (ex.: \"A tirzepatida mantém a perda de peso a longo prazo?\"). "
        "Seja específico e fiel ao estudo, sem inventar.\n\n"
        f"{lista}\n\n"
        'Responda SÓ JSON: [{"i":0,"pergunta":"..."},{"i":1,"pergunta":"..."}]')


def _parse_perguntas(texto):
    import jsonx
    bruto = jsonx.primeiro_array(texto)
    if not bruto:
        return {}
    try:
        arr = json.loads(bruto)
    except Exception:
        return {}
    out = {}
    for c in arr:
        i = c.get("i")
        if isinstance(i, int):
            out[i] = (c.get("pergunta") or "").strip()
    return out


def gerar_perguntas(cands, llm_fn=None, chunk=15):
    """Anexa 'pergunta' a cada candidato (HAIKU, em lotes). llm_fn(prompt)->texto injetável."""
    if not cands:
        return cands
    if llm_fn is None:
        from resumo_diario import claude, HAIKU
        llm_fn = lambda p: claude(HAIKU, p, max_tokens=1500)
    for ini in range(0, len(cands), chunk):
        lote = cands[ini:ini + chunk]
        mapa = _parse_perguntas(llm_fn(_prompt_perguntas(lote)))
        for j, c in enumerate(lote):
            c["pergunta"] = mapa.get(j, "")
    return cands


# ── Resumo final dos selecionados (PADRÃO de qualidade do app) ──
def gerar_resumo(cand, modelo="sonnet", gerar_resumo=None, gerar_gancho=None,
                 gerar_grafico_json=None, gerar_titulo=None):
    """Gera {titulo_pt, resumo, gancho, grafico}. modelo='sonnet' (padrão da reserva,
    ótimo + barato) ou 'opus' (máximo). Mapeia 'abstract' -> 'resumo' que o gerador espera."""
    import content
    art = dict(cand)
    art["resumo"] = cand.get("abstract") or cand.get("resumo") or ""
    f_resumo = gerar_resumo
    if f_resumo is None:
        from resumo_diario import claude, OPUS, SONNET, SYS_APROF
        mdl = SONNET if (modelo or "").lower() == "sonnet" else OPUS
        def f_resumo(a):
            blob = ("### " + a.get("titulo", "") + "\nData: " + a.get("data", "") +
                    "\nFonte: " + a.get("fonte", "") + " | doi:" + a.get("doi", "") +
                    "\n" + a.get("resumo", ""))
            return claude(mdl, "Aprofunde ESTE estudo para o médico (abra pela data de publicação):\n\n" + blob,
                          system=SYS_APROF, max_tokens=3200)
    return content.gerar_conteudo(art, gerar_resumo=f_resumo, gerar_gancho=gerar_gancho,
                                  gerar_grafico_json=gerar_grafico_json, gerar_titulo=gerar_titulo)


# ── Adicionar MEU estudo (PDF ou colado) -> gera resumo -> fila com PRIORIDADE ──
def extrair_texto_pdf(pdf_bytes):
    """Extrai o texto de um PDF via pdftotext (poppler). Retorna string (pode ser vazia)."""
    import subprocess
    import tempfile
    import os as _os
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_bytes)
        caminho = f.name
    try:
        out = subprocess.run(["pdftotext", "-q", caminho, "-"], capture_output=True, timeout=60)
        return out.stdout.decode("utf-8", "replace")
    finally:
        try:
            _os.unlink(caminho)
        except Exception:
            pass


def adicionar_meu_estudo(texto, titulo="", fonte="", doi="", url="", data="", modelo="sonnet", **geradores):
    """Gera o resumo de um estudo do Diego (texto do PDF ou colado) e coloca na fila
    COM PRIORIDADE (fura a fila). Retorna (id_reserva, titulo_pt)."""
    import json
    import db
    db.init()
    cand = {"titulo": titulo, "fonte": fonte, "doi": doi, "url": url, "data": data,
            "abstract": (texto or "")[:14000]}      # corta p/ caber no prompt
    r = gerar_resumo(cand, modelo=modelo, **geradores)
    rid = db.salvar_reserva({
        "tema": "Meus estudos", "titulo_pt": r["titulo_pt"], "resumo": r["resumo"],
        "gancho": r.get("gancho", ""),
        "grafico": json.dumps(r["grafico"], ensure_ascii=False) if r.get("grafico") else "",
        "doi": doi, "fonte": fonte, "url": url, "data": data,
        "prioridade": 1, "origem": "manual"})
    return rid, r["titulo_pt"]


# ── Orquestração com banco (servidor/CLI) ──
def rodar_varredura(desde=None, ate=None, caps=None):
    """Varre + gera perguntas (Haiku) + salva candidatos no Supabase. Retorna quantos entraram."""
    import db
    db.init()                       # garante as tabelas (deploy novo / CLI)
    desde = desde or "2026-01-01"
    ate = ate or date.today().isoformat()
    cands = varrer(desde, ate, caps=caps)
    gerar_perguntas(cands)
    n = db.salvar_candidatos(cands)
    print(f"[curadoria] varredura: {len(cands)} candidatos, {n} novos salvos", flush=True)
    return n


def gerar_selecionados():
    """Gera o resumo (padrão) de cada candidato 'selecionado' -> reserva. Retorna quantos."""
    import db
    db.init()                       # garante as tabelas (deploy novo / CLI)
    feitos = 0
    for c in db.listar_candidatos(status="selecionado"):
        try:
            r = gerar_resumo(c)
            db.salvar_reserva({
                "candidato_id": c["id"], "tema": c["tema"], "titulo_pt": r["titulo_pt"],
                "resumo": r["resumo"], "gancho": r.get("gancho", ""),
                "grafico": json.dumps(r["grafico"], ensure_ascii=False) if r.get("grafico") else "",
                "doi": c.get("doi", ""), "fonte": c.get("fonte", ""), "url": c.get("url", ""),
                "data": c.get("data", "")})
            db.marcar_candidatos([c["id"]], "resumido")
            feitos += 1
        except Exception as e:
            print(f"[curadoria] gerar resumo falhou ({c.get('titulo','')[:40]}): {e}", flush=True)
    print(f"[curadoria] {feitos} resumo(s) gerado(s) para a reserva", flush=True)
    return feitos


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "varrer"
    if cmd == "varrer":
        rodar_varredura()
    elif cmd == "gerar":
        gerar_selecionados()
    else:
        print("uso: python curadoria.py [varrer|gerar]")
