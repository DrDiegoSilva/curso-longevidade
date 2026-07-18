"""
resumo_diario.py — Gera o resumo/aula do dia e envia no WhatsApp via Z-API.
- Lê o calendário de temas_config.json (tema + modo do dia).
- Modo 'atualizacao': busca Europe PMC (7 dias) -> cascata Haiku(tria)->Opus(aprofunda)->Sonnet(menções).
  Se não houver estudo relevante -> fallback para uma AULA do curso de Longevidade.
- Modo 'curso': pega o próximo módulo do currículo -> Opus escreve a aula.
- Envia via Z-API; registra DOIs enviados (dedup) e marca módulo do curso.

Uso: python resumo_diario.py [--dia segunda|...] [--dry-run]
Sem --dia, usa o dia atual. Custo controlado pela chave dedicada (teto $10/mês).
"""
import sys, io, os, json, re, urllib.request, urllib.error
from datetime import datetime
import buscar_estudos as be
import config  # caminhos/credenciais portáveis (env no VPS, arquivos no Windows)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # buscar_estudos já troca o stdout; só reconfigura
except Exception:
    pass
DIR = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(DIR, "temas_config.json"), encoding="utf-8"))
KEY = config.ANTHROPIC_KEY
BASE = config.BASE
CURRICULO = os.path.join(BASE, "longevidade_CURSO_curriculo.md")
CACHE = os.path.join(DIR, "resumos_enviados.jsonl")
DIAS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
HAIKU, SONNET, OPUS = "claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-8"

# ─── Log em arquivo (a tarefa agendada roda sem console visível) ──
os.makedirs(os.path.join(DIR, "logs"), exist_ok=True)
class _Tee:
    def __init__(self, *s): self.s = s
    def write(self, x):
        for st in self.s:
            try: st.write(x)
            except Exception: pass
    def flush(self):
        for st in self.s:
            try: st.flush()
            except Exception: pass
_logf = open(os.path.join(DIR, "logs", "resumo.log"), "a", encoding="utf-8")
sys.stdout = sys.stderr = _Tee(sys.stdout, _logf)
print(f"\n{'#'*70}\n# RUN {datetime.now():%Y-%m-%d %H:%M:%S}")

# ─── Claude API ───────────────────────────────────────────────
def claude(model, prompt, system="", max_tokens=2000, cont=4):
    """Chama a API. Se a resposta bater o teto de tokens (stop_reason='max_tokens'),
    continua automaticamente de onde parou — garante que a aula NUNCA é cortada."""
    msgs = [{"role": "user", "content": prompt}]
    partes = []
    for _ in range(cont + 1):
        body = {"model": model, "max_tokens": max_tokens, "messages": msgs}
        if system:
            body["system"] = system
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=json.dumps(body).encode("utf-8"),
            method="POST", headers={"x-api-key": KEY, "anthropic-version": "2023-06-01",
                                    "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as r:
            d = json.loads(r.read())
        chunk = "".join(b.get("text", "") for b in d.get("content", []))
        partes.append(chunk)
        if d.get("stop_reason") != "max_tokens":
            break  # terminou naturalmente
        # truncou -> pede continuação exata
        msgs.append({"role": "assistant", "content": chunk})
        msgs.append({"role": "user", "content": "Continue EXATAMENTE de onde parou, sem repetir nada nem recomeçar."})
    return "".join(partes).strip()

# ─── Z-API ────────────────────────────────────────────────────
def enviar_zap(msg):
    z = config.zapi()
    url = f"https://api.z-api.io/instances/{z['instanceId']}/token/{z['instanceToken']}/send-text"
    body = json.dumps({"phone": z["destinoNumero"], "message": msg}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json", "Client-Token": z["clientToken"]})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")

# ─── Cache de DOIs enviados (dedup) ───────────────────────────
def dois_enviados():
    if not os.path.exists(CACHE):
        return set()
    out = set()
    for line in open(CACHE, encoding="utf-8"):
        try:
            out.add(json.loads(line).get("doi", ""))
        except Exception:
            pass
    return out

def registrar(dois):
    with open(CACHE, "a", encoding="utf-8") as f:
        for d in dois:
            f.write(json.dumps({"doi": d, "em": datetime.now().isoformat()}) + "\n")

# ─── ATUALIZAÇÃO (Obesidade/Hormônios/Lipedema/Performance) ────
def modo_atualizacao(tema):
    q, exc = be.carregar_tema(tema)
    hoje = datetime.now()
    desde = hoje.fromordinal(hoje.toordinal() - 7).strftime("%Y-%m-%d")
    res = be.buscar_epmc(q, desde, hoje.strftime("%Y-%m-%d"), 40, clinico=True, excluir=exc)
    ja = dois_enviados()
    estudos = []
    for r in res:
        ab = (r.get("abstractText") or "")
        if len(ab) < 120:
            continue
        doi = r.get("doi", "")
        if doi and doi in ja:
            continue
        estudos.append({"titulo": (r.get("title") or "").strip(), "journal": r.get("journalTitle") or "",
                        "data": r.get("firstPublicationDate", ""), "doi": doi, "pmid": r.get("pmid", ""),
                        "abstract": " ".join(ab.split())[:1600]})
    if not estudos:
        return {"msg": None, "commit": lambda: None, "forte": False}  # nada na semana -> só aula
    # 1) Haiku tria
    lista = "\n".join(f"[{i}] {e['titulo']} | {e['journal']} | {e['abstract'][:500]}" for i, e in enumerate(estudos))
    tri = claude(HAIKU, f"Tema do médico: {tema}. Estudos da semana:\n{lista}\n\n"
        "Classifique CADA um p/ a prática clínica do Dr. Diego (emagrecimento/GLP-1, TRT, lipedema, performance): "
        "DESTAQUE (muda conduta, dado clínico forte no tema) / MENCAO (relevante secundário, mas o FOCO é o tema) / "
        "LIXO. É LIXO quando: fora da área; animal/cultura celular; pediatria; cirurgia não relacionada; OU quando o tema "
        "aparece só como comorbidade/fator de risco secundário e NÃO é o objeto central do estudo (ex.: paper de "
        "dermatologia/psoríase/diverticulite que apenas cita obesidade). Só DESTAQUE/MENCAO se o FOCO for o tema. "
        "Na dúvida, LIXO — é melhor cortar do que enviar ruído. "
        'Responda SÓ JSON: [{"i":0,"classe":"DESTAQUE"}, ...]',
        system="Você é triador de literatura médica, MUITO rigoroso em cortar ruído. Prefere falso-negativo a falso-positivo.", max_tokens=800)
    try:
        cls = json.loads(re.search(r"\[.*\]", tri, re.S).group(0))
    except Exception:
        cls = [{"i": i, "classe": "MENCAO"} for i in range(min(4, len(estudos)))]
    dest = [estudos[c["i"]] for c in cls if c.get("classe") == "DESTAQUE" and c["i"] < len(estudos)][:3]
    menc = [estudos[c["i"]] for c in cls if c.get("classe") == "MENCAO" and c["i"] < len(estudos)][:4]
    forte = len(dest) > 0  # semana "forte" = tem ao menos 1 estudo que muda conduta
    if not dest and not menc:
        return {"msg": None, "commit": lambda: None, "forte": False}  # semana vazia -> só aula
    # 2) Opus aprofunda destaques
    partes = []
    if dest:
        blob = "\n\n".join(f"### {e['titulo']}\nData de publicação: {e['data']}\nRevista: {e['journal']} | doi:{e['doi']}\n{e['abstract']}" for e in dest)
        partes.append(claude(OPUS, f"Tema: {tema}. Aprofunde ESTES estudos-destaque (abra cada um pela data de publicação):\n\n{blob}", system=SYS_APROF, max_tokens=3200))
    # 3) Sonnet menções
    if menc:
        blob = "\n\n".join(f"- [{e['data']}] {e['titulo']} ({e['journal']}, doi:{e['doi']}): {e['abstract'][:600]}" for e in menc)
        rotulo = "*📋 Também saiu (menção):*" if dest else "*📋 Nada que mude conduta esta semana; o que saiu de relevante:*"
        partes.append(rotulo + "\n" + claude(SONNET, f"Tema: {tema}. Escreva 1 menção curta (1–2 linhas: achado + relevância clínica) por estudo, com o nome da revista:\n\n{blob}", system=SYS_MENC, max_tokens=700))
    cab = f"🔬 *{tema.upper()} — atualização da semana* (curadoria IA · Europe PMC)\n\n"
    msg = cab + "\n\n".join(partes) + "\n\n_Siglas explicadas no texto · filtro RCT/meta/revisão._"
    dois = [e["doi"] for e in dest + menc if e["doi"]]
    return {"msg": msg, "commit": lambda: registrar(dois), "forte": forte}  # dedup só após envio OK

# ─── CURSO (Longevidade) ──────────────────────────────────────
def proximo_modulo():
    # pega a 1ª linha ⬜ (robusto a parênteses no título e a linhas sem travessão)
    txt = open(CURRICULO, encoding="utf-8").read()
    m = re.search(r"- ⬜ (\d+)\.\s*(.+)", txt)
    if not m:
        return None
    num, resto = m.group(1), m.group(2).strip()
    tb = re.search(r"\*\*(.+?)\*\*", resto)                      # título = 1º trecho em **negrito**
    titulo = tb.group(1) if tb else resto.split("—")[0].strip()
    escopo = resto.split("—", 1)[1].strip() if "—" in resto else resto
    return (num, titulo, re.sub(r"\*\*", "", escopo).split("_(")[0].strip())

def marcar_modulo(num, arquivo):
    # casa a linha ⬜ pelo NÚMERO (qualquer formato de título), não pela estrutura do travessão
    txt = open(CURRICULO, encoding="utf-8").read()
    txt = re.sub(rf"- ⬜ ({re.escape(num)}\..*?)(\n)",
                 rf"- ✅ \1 _(concluído {datetime.now():%Y-%m-%d} → {arquivo})_\2", txt, count=1)
    open(CURRICULO, "w", encoding="utf-8").write(txt)

def _gerar_aula(num, titulo, escopo):
    """Gera o texto da aula (com continuação automática, nunca corta). Usado pelo curso e pelo --regen."""
    termo = re.sub(r"[^a-zA-Z0-9 ]", " ", titulo).split("(")[0]
    try:
        res = be.buscar_epmc(termo, "2022-01-01", datetime.now().strftime("%Y-%m-%d"), 15, clinico=True)
        apoio = "\n".join(f"- {r.get('title','')} ({r.get('journalTitle','')}, doi:{r.get('doi','')})" for r in res[:8] if r.get("abstractText"))
    except Exception:
        apoio = ""
    return claude(OPUS,
        f"Módulo {num} do curso: {titulo}. Escopo: {escopo}.\n"
        f"Estudos de apoio (Europe PMC):\n{apoio}\n\n"
        "Escreva a AULA completa no formato do curso, usando também seu conhecimento consolidado. "
        "IMPORTANTE: sempre feche com a seção de CONDUTA prática — é a parte mais importante, nunca omita.",
        system=SYS_CURSO, max_tokens=4000)

def regenerar_modulo(num):
    """Regenera a aula de um módulo JÁ concluído (conserta cortes) e sobrescreve o .md. NÃO envia, não re-marca."""
    txt = open(CURRICULO, encoding="utf-8").read()
    m = re.search(rf"- ✅ 0*{int(num)}\.\s*(.+)", txt)
    if not m:
        print(f"[regen] módulo {num} não está como concluído — pulei"); return None
    resto = m.group(1)
    fm = re.search(r"→\s*(.+?)\)_", resto)
    tb = re.search(r"\*\*(.+?)\*\*", resto)
    titulo = tb.group(1) if tb else resto.split("—")[0].strip()
    escopo = re.sub(r"\*\*", "", resto.split("—", 1)[1]).split("_(")[0].strip() if "—" in resto else ""
    n2 = f"{int(num):02d}"
    arq = fm.group(1).strip() if fm else f"longevidade_{n2}_" + re.sub(r"[^a-zA-Z]", "", titulo)[:14] + ".md"
    aula = _gerar_aula(n2, titulo, escopo)
    open(os.path.join(BASE, arq), "w", encoding="utf-8").write(f"# Módulo {n2} — {titulo}\n_{datetime.now():%Y-%m-%d}_\n\n" + aula)
    print(f"[regen] módulo {n2} ({titulo}) regenerado -> {arq}")
    return arq

def modo_curso():
    mod = proximo_modulo()
    if not mod:
        return {"msg": "🎓 Curso de Longevidade concluído! Todos os módulos entregues. Podemos revisar ou aprofundar algum.",
                "commit": lambda: None}
    num, titulo, escopo = mod
    aula = _gerar_aula(num, titulo, escopo)
    arq = f"longevidade_{int(num):02d}_" + re.sub(r"[^a-zA-Z]", "", titulo)[:14] + ".md"
    def commit():  # grava o destilado + marca ✅ só após envio OK
        open(os.path.join(BASE, arq), "w", encoding="utf-8").write(f"# Módulo {num} — {titulo}\n_{datetime.now():%Y-%m-%d}_\n\n" + aula)
        marcar_modulo(num, arq)
        try:  # regenera o ebook (não crítico — nunca pode quebrar o envio)
            import ebook_curso
            ebook_curso.gerar()
            print("[ebook] atualizado")
        except Exception as e:
            print("[ebook] falhou (não crítico):", e)
    return {"msg": f"🎓 *CURSO LONGEVIDADE — Aula {num}: {titulo}*\n\n" + aula, "commit": commit}

# ─── Prompts de sistema ───────────────────────────────────────
SYS_APROF = ("Você escreve resumos clínicos para o Dr. Diego (médico). Mantenha TODOS os dados e números, mas em "
    "LINGUAGEM CLARA: frases curtas, uma ideia por frase; explique cada sigla/termo técnico na PRIMEIRA vez em palavras "
    "simples (ex.: 'HR 0,67 — ou seja, ~33% menos risco'); não empilhe várias estatísticas na mesma frase. "
    "Estruture cada estudo-destaque nesta ordem: "
    "(1) cabeçalho ABRINDO pela data → `🗓️ *<mês/ano de publicação>* · *Título curto*`; "
    "(2) linha de metadados (desenho, n, revista + DOI); "
    "(3) 💡 *Em resumo* — 1–2 linhas diretas: o que achou + o que muda na prática; "
    "(4) 📊 *Eficácia* com tempo/velocidade quando houver; "
    "(5) ⚠️ *Efeitos adversos* com números; (6) 🛠️ *Manejo* dos EA; "
    "(7) 🔬 *MBE* — traduza as siglas (MD, HR, IC95%, I²…) em português claro; "
    "(8) 🧠 *Conduta*, separando o consolidado do que é só deste estudo. "
    "Sem seção 'para paciente'. WhatsApp: *negrito* com asteriscos, sem títulos markdown. NÃO invente dados fora do abstract.")
SYS_MENC = ("Menções curtas p/ médico (WhatsApp, *negrito*). Comece CADA uma pela data → `🗓️ mês/ano` + revista; "
    "depois 1–2 linhas em linguagem clara: achado + relevância clínica. Sem inventar.")
SYS_CURSO = ("Você é professor de medicina de longevidade do Dr. Diego. Aula completa e prática, mas em LINGUAGEM CLARA: "
    "frases curtas, explique cada termo técnico/sigla na primeira vez. Abra com um parágrafo '💡 Em resumo' do que ele vai "
    "aprender. Traga níveis de evidência (A) RCT/meta humano (B) mecanismo/animal (C) opinião; SEMPRE cite o ANO dos "
    "estudos-chave (ex.: 'Konopka 2019') para ele situar quão atual é; cubra mecanismo, doses, segurança, interações, "
    "conduta e o debate entre pesquisadores com conflito de interesse. WhatsApp: *negrito*. Honesto sobre hype/evidência fraca.")

# ─── Main ─────────────────────────────────────────────────────
def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dia", choices=DIAS)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true", help="valida o launcher: só escreve no log e sai (sem API/envio)")
    ap.add_argument("--regen", metavar="N", help="regenera aula(s) de módulos JÁ concluídos e reconstrói o ebook; NÃO envia. Ex: 12  ou  1-12  ou  2,5,11")
    args = ap.parse_args()
    if args.selftest:
        print(f"[selftest] launcher OK — python {sys.version.split()[0]} — pid {os.getpid()}")
        return
    if args.regen:
        if "-" in args.regen:
            a, b = args.regen.split("-"); nums = list(range(int(a), int(b) + 1))
        else:
            nums = [int(x) for x in args.regen.split(",")]
        for n in nums:
            try:
                regenerar_modulo(n)
            except Exception as e:
                print(f"[regen] módulo {n} falhou: {e}")
        try:
            import ebook_curso; ebook_curso.gerar(); print("[ebook] reconstruído")
        except Exception as e:
            print("[ebook] falhou:", e)
        return
    dia = args.dia or DIAS[datetime.now().weekday()]
    try:
        plano = CFG["calendario"][dia]
        tema, modo = plano["tema"], plano["modo"]
        print(f"[{dia}] tema={tema} modo={modo}")
        if modo == "curso":
            r = modo_curso()
            msg, commits = r["msg"], [r["commit"]]
        else:
            at = modo_atualizacao(tema) or {"msg": None, "commit": lambda: None, "forte": False}
            if at["forte"]:  # semana forte: só a atualização
                msg, commits = at["msg"], [at["commit"]]
            else:            # semana fraca: menções (se houver) + aula de longevidade
                print(f"[semana fraca] {tema} sem estudo forte -> menções (se houver) + aula")
                curso = modo_curso()
                partes, commits = [], []
                if at["msg"]:
                    partes.append(at["msg"]); commits.append(at["commit"])
                partes.append(curso["msg"]); commits.append(curso["commit"])
                msg = "\n\n━━━━━━━━━━━━━━━\n\n".join(partes)
        print("=" * 60 + f"\n{msg}\n" + "=" * 60)
        if args.dry_run:
            print("\n[dry-run] NÃO enviado (commit adiado).")
        else:
            resp = enviar_zap(msg)
            print("\n[enviado]", resp)
            for c in commits:
                c()  # dedup / módulo ✅ só após envio bem-sucedido
            print("[commit] OK")
    except Exception as e:
        import traceback
        print("[ERRO]\n" + traceback.format_exc())
        # REDE DE SEGURANÇA: nunca falhar em silêncio — avisa o Dr. no WhatsApp
        if not args.dry_run:
            try:
                enviar_zap(f"⚠️ O resumo de {dia} falhou hoje ({type(e).__name__}: {e}). "
                           f"Nada foi enviado. Me chama aqui pra eu corrigir. (detalhe em logs/resumo.log)")
            except Exception:
                pass
        raise

if __name__ == "__main__":
    main()
