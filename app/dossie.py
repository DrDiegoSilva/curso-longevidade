"""O DOSSIÊ por tema — a memória destilada que a opinião do dia lê.

Ideia do Diego (2026-08-11), depois do backfill trazer 617 estudos: em vez de reler o
corpus inteiro todo dia, analisar uma vez, indexar num documento, e ir só acrescentando
cada estudo novo.

Por que importa: mandar os ~250 estudos de um tema por dia dá ~100 mil tokens por
chamada, e esse custo **cresce para sempre** conforme a base engorda. Lendo o dossiê são
~6 mil, e fica igual. O argumento não é o preço de hoje — é que um escala e o outro não.

**O dossiê não é prosa.** É `{"blocos": [{afirmacao, estudos:[{titulo,fonte,data}]}]}`.
Texto corrido mataria a guarda de ancoragem da opinião, que é justamente o que separa
"memória" de "modelo opinando bonito": a opinião precisa citar estudo que dê pra conferir.

Bloco sem afirmação ou sem estudo é descartado no parse — afirmação sem lastro é opinião
solta, exatamente o que o dossiê existe pra impedir.
"""
import json
import re
import unicodedata

SYS = ("Você organiza a memória de um médico sobre um tema, a partir de estudos científicos. "
       "Agrupe os achados em AFIRMAÇÕES, e para cada uma liste os estudos que a sustentam. "
       "Registre também onde os estudos DISCORDAM entre si — a divergência é informação, "
       "não defeito; não force consenso. "
       "Nunca afirme nada que não venha dos estudos listados. "
       'Responda SÓ JSON: {"blocos":[{"afirmacao":"...","estudos":'
       '[{"titulo":"...","fonte":"...","data":"AAAA-MM"}]}]}')

LOTE_PADRAO = 25          # ~25 abstracts ≈ 10k tokens de entrada por chamada


def _linha(e):
    return (f"- {e.get('titulo','')} | {e.get('fonte','')} | {e.get('data','')}\n"
            f"  {(e.get('abstract') or e.get('resumo') or '')[:900]}")


def parse(bruto):
    """Normaliza a resposta da IA. Nunca levanta, nunca devolve None — mesma disciplina
    do `content.parse_gancho`, e pelo mesmo motivo: isto roda no caminho do conteúdo."""
    if not bruto:
        return {"blocos": []}
    try:
        import jsonx
        obj = jsonx.primeiro_objeto(str(bruto))     # tira cerca de código e preâmbulo
        d = json.loads(obj) if obj else {}
    except Exception:
        return {"blocos": []}
    if not isinstance(d, dict):
        return {"blocos": []}
    blocos = []
    for b in d.get("blocos") or []:
        if not isinstance(b, dict):
            continue
        afirmacao = str(b.get("afirmacao") or "").strip()
        estudos = [e for e in (b.get("estudos") or [])
                   if isinstance(e, dict) and str(e.get("titulo") or "").strip()]
        if afirmacao and estudos:      # sem lastro não entra
            blocos.append({"afirmacao": afirmacao, "estudos": estudos})
    return {"blocos": blocos}


MIN_PREFIXO = 30      # abaixo disso, "Once" casaria com meio corpus


def normalizar_titulo(t):
    """Minúsculas, sem acento, sem pontuação, espaços colapsados."""
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", t.lower())).strip()


def casar_titulo(titulo, corpus):
    """O estudo do corpus que corresponde ao título escrito pela IA no dossiê, ou None.

    Três degraus: igual depois de normalizar; truncado (um é prefixo do outro, com pelo
    menos MIN_PREFIXO caracteres); nada.

    Ambíguo devolve None de propósito. O que NÃO se pode fazer é chutar — excluir o
    estudo errado é invisível até a reconstrução seguinte, quando a afirmação some sem
    explicação.
    """
    alvo = normalizar_titulo(titulo)
    if not alvo or not corpus:
        return None
    iguais = [e for e in corpus if normalizar_titulo(e.get("titulo")) == alvo]
    if len(iguais) == 1:
        # Antes de devolver, confira se existe outro estudo do qual o alvo é prefixo.
        # Se sim, é ambíguo (o alvo pode ser uma truncagem). Com MIN_PREFIXO pra evitar
        # falsos positivos em títulos muito curtos.
        if len(alvo) >= MIN_PREFIXO:
            for e in corpus:
                n = normalizar_titulo(e.get("titulo"))
                if n != alvo and n.startswith(alvo):
                    return None  # ambíguo: alvo é prefixo de outro
        return iguais[0]
    if iguais:
        return None                      # repetido no banco: manda pra lista
    if len(alvo) < MIN_PREFIXO:
        return None
    prefixos = []
    for e in corpus:
        n = normalizar_titulo(e.get("titulo"))
        if len(n) >= MIN_PREFIXO and (n.startswith(alvo) or alvo.startswith(n)):
            prefixos.append(e)
    return prefixos[0] if len(prefixos) == 1 else None


def _chamar(gerar_fn, prompt):
    """Uma falha de lote não pode derrubar o dossiê inteiro."""
    try:
        return parse(gerar_fn(prompt))
    except Exception as e:
        print(f"[dossie] lote falhou (segue): {e}", flush=True)
        return {"blocos": []}


def construir(estudos, lote=LOTE_PADRAO, gerar_fn=None):
    """Dossiê do zero, a partir do corpus do tema.

    Map-reduce: o tema não cabe numa chamada só (~250 estudos = ~100k tokens), então vai
    em lotes e os parciais são fundidos numa passada final, que é onde as afirmações
    repetidas viram uma só e as divergências entre lotes aparecem.

    Reconstruir é a defesa contra o telefone sem fio do `acrescentar`: os abstracts brutos
    ficam no banco, então dá pra refazer do zero e comparar sempre que der desconfiança.
    """
    if gerar_fn is None:
        gerar_fn = _gerador_padrao()
    parciais = []
    for i in range(0, len(estudos), lote):     # corpus vazio: não itera, cai no `if not parciais`
        material = "\n".join(_linha(e) for e in estudos[i:i + lote])
        d = _chamar(gerar_fn, f"Estudos:\n{material}\n\nOrganize a memória deste tema.")
        parciais.extend(d["blocos"])
    if not parciais:
        return {"blocos": []}
    fundido = _chamar(gerar_fn,
                      "Estas são memórias parciais do MESMO tema, feitas em lotes. "
                      "Funda numa só: junte afirmações repetidas somando os estudos de "
                      "cada uma, e mantenha explícitas as divergências.\n\n"
                      + json.dumps({"blocos": parciais}, ensure_ascii=False))
    return fundido if fundido["blocos"] else {"blocos": parciais}


def acrescentar(dossie_atual, estudo, gerar_fn=None):
    """Encaixa UM estudo novo no dossiê, sem reler o corpus.

    Resposta ruim ou falha da IA preserva o dossiê que existia: dossiê velho é melhor que
    dossiê nenhum, e é a mesma regra do kit (`curadoria.regerar_kits`).
    """
    atual = dossie_atual or {"blocos": []}
    if gerar_fn is None:
        gerar_fn = _gerador_padrao()
    novo = _chamar(gerar_fn,
                   "Memória atual do tema:\n"
                   + json.dumps(atual, ensure_ascii=False)
                   + "\n\nEstudo novo:\n" + _linha(estudo)
                   + "\n\nEncaixe o estudo novo: reforce a afirmação que ele sustenta, "
                     "crie afirmação nova se for o caso, e registre se ele CONTRARIA "
                     "alguma das existentes. Devolva a memória inteira atualizada.")
    return novo if novo["blocos"] else atual


def _gerador_padrao():
    from resumo_diario import claude, SONNET
    return lambda p: claude(SONNET, p, system=SYS, max_tokens=4000, acao="dossie")


_LOCK = __import__("threading").Lock()


def corpus_do_tema(tema, db_mod=None):
    """Os estudos do tema, das 3 fontes que acumulam: candidatos da varredura e do
    backfill (com o abstract inteiro), estudos já enviados e clássicos bancados.

    Cada item carrega `id` e `origem` — é o que permite a tela oferecer um ✕ que aponta
    para uma linha de verdade do banco, em vez de para um título solto.

    Excluídos ficam de fora: `listar_candidatos` já esconde o escopo 'tudo', e o
    'memoria' é filtrado aqui (ele continua na fila, só não alimenta a memória). Nos
    digests o filtro é SÓ aqui: `listar_por_tema` serve o portal do assinante.
    """
    if db_mod is None:
        import db as db_mod
    fonte = []
    for c in db_mod.listar_candidatos(tema=tema):
        if (c.get("excluido") or "").strip():
            continue
        if (c.get("abstract") or "").strip():
            fonte.append({"id": c.get("id", ""), "origem": "candidato",
                          "titulo": c.get("titulo", ""), "fonte": c.get("fonte", ""),
                          "data": c.get("data", ""), "abstract": c.get("abstract", "")})
    for d in db_mod.listar_por_tema(slug_de(tema, db_mod)):
        if (d.get("excluido") or "").strip():
            continue
        fonte.append({"id": f'{d.get("tema_slug","")}|{d.get("data","")}',
                      "origem": "digest", "titulo": d.get("titulo_pt", ""),
                      "fonte": d.get("fonte", ""), "data": d.get("data", ""),
                      "abstract": d.get("resumo", "")})
    return fonte


def slug_de(tema, db_mod=None):
    if db_mod is None:
        import db as db_mod
    return db_mod.slug(tema)


def reconstruir_todos(temas=None, gerar_fn=None, db_mod=None):
    """Refaz o dossiê de cada tema a partir do corpus. Devolve `{tema: n_estudos}`.

    Trava de concorrência: cada tema custa ~10 chamadas Sonnet, então dois cliques
    dobrariam a conta — mesma defesa do backfill e da regeração de kits.
    """
    if not _LOCK.acquire(blocking=False):
        print("[dossie] reconstrução já está rodando — ignorando o disparo novo", flush=True)
        return {"ja_rodando": True}
    try:
        if db_mod is None:
            import db as db_mod
        db_mod.init()
        if temas is None:
            import area_estudo
            temas = area_estudo.areas()
        feitos = {}
        for t in temas:
            estudos = corpus_do_tema(t, db_mod)
            if not estudos:
                continue
            d = construir(estudos, gerar_fn=gerar_fn)
            if not d["blocos"]:          # IA fora do ar: não apaga o dossiê que existia
                print(f"[dossie] {t}: nada gerado, mantendo o anterior", flush=True)
                continue
            db_mod.salvar_dossie(t, d, len(estudos))
            feitos[t] = len(estudos)
        return feitos
    finally:
        _LOCK.release()


def painel(db_mod=None, temas=None):
    """O material da aba 🧠: por tema, o corpus lido (sem os abstracts — a tela só
    precisa de id/origem/titulo/fonte/data pra montar a lista) e o que está fora da
    memória.

    O descarte do abstract é em Python, depois da consulta: o `SELECT *` de
    `corpus_do_tema` continua trazendo abstract/resumo do banco por inteiro. Não
    economiza a consulta — só evita carregar o peso pesado (abstracts de centenas de
    estudos) no HTML da tela.

    Montado só quando a aba do dossiê está aberta: são centenas de linhas por tema.
    """
    if db_mod is None:
        import db as db_mod
    if temas is None:
        import area_estudo
        temas = area_estudo.areas()
    out = {}
    for t in temas:
        corpus = [{k: e.get(k, "") for k in ("id", "origem", "titulo", "fonte", "data")}
                  for e in corpus_do_tema(t, db_mod)]
        out[t] = {"corpus": corpus, "excluidos": db_mod.listar_excluidos(t)}
    return out
