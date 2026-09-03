"""
Busca estudos científicos recentes por tema em APIs abertas (Europe PMC).
Prioriza journals de renome. Imprime estruturado para síntese posterior.
Uso: python buscar_estudos.py "obesity OR GLP-1 OR tirzepatide" --dias 14 --max 15
Futuro (VPS): adicionar OpenAlex/Crossref/medRxiv/ClinicalTrials/openFDA.
"""
import sys, json, re, argparse, urllib.request, urllib.parse
import html as _html
from datetime import datetime, timedelta
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

RENOME = [
    "n engl j med", "lancet", "jama", "diabetes care", "obesity",
    "diabetes obes metab", "nature medicine", "nature med", "cell metab",
    "j clin endocrinol metab", "nature", "circulation", "ann intern med",
    "bmj", "endocr", "thyroid", "eur j endocrinol", "obes rev",
]
EPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
EPMC = EPMC_BASE + "/search"

# Só estudo clínico relevante (corta animal/cultura celular/epidemiologia solta)
FILTRO_CLINICO = ('(PUB_TYPE:"Randomized Controlled Trial" OR PUB_TYPE:"Meta-Analysis" '
                  'OR PUB_TYPE:"Systematic Review" OR PUB_TYPE:"Clinical Trial" '
                  'OR PUB_TYPE:"Guideline" OR PUB_TYPE:"Practice Guideline")')


def _http_get_json(url, timeout=40):
    """O GET isolado — ponto que os testes substituem pra provar o parsing sem rede."""
    req = urllib.request.Request(url, headers={"User-Agent": "HealthBot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _http_get_text(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "HealthBot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def buscar_epmc(query, desde, ate, n=40, clinico=True, excluir=""):
    q = f"({query})"
    if excluir:
        q += f" NOT {excluir}"
    if clinico:
        q += f" AND {FILTRO_CLINICO}"
    q += f" AND (FIRST_PDATE:[{desde} TO {ate}]) AND (LANG:eng)"
    params = {
        "query": q,
        "format": "json", "pageSize": n, "sort": "P_PDATE_D desc",
        "resultType": "core",
    }
    url = EPMC + "?" + urllib.parse.urlencode(params)
    data = _http_get_json(url)
    return data.get("resultList", {}).get("result", [])


# ─── Texto completo (Open Access, Europe PMC) ──────────────────────────────
# Único jeito deste app conseguir o ESTUDO INTEIRO (não só o abstract) usando stdlib
# puro (sem lib de PDF): a Europe PMC serve o JATS full text em XML pra artigo Open
# Access com PMCID. Decisão de 2026-09-03: sem texto completo, o estudo NÃO entra —
# nunca cai pro abstract como substituto (ver sources._so_com_texto_completo).
_TAG = re.compile(r"<[^>]+>")

def _xml_para_texto(xml, max_chars=20000):
    """Extrai o texto corrido de um XML JATS (fullTextXML da Europe PMC). Puro/testável.
    Tira a bibliografia (<back>...) — infla token à toa e não ajuda o resumo. Corta em
    max_chars: um texto completo passa fácil de 60KB, e isso é custo de token de verdade
    (ver ia_custo) sem ganho proporcional pro resumo."""
    if not xml:
        return ""
    corpo = re.split(r"<back[ >]", xml, maxsplit=1)[0]
    texto = _TAG.sub(" ", corpo)
    texto = _html.unescape(texto)
    return " ".join(texto.split())[:max_chars]


def texto_completo_pmc(pmcid):
    """Baixa e extrai o texto corrido do full text XML (Europe PMC) de um PMCID Open
    Access. None se falhar — sem fallback pro abstract; quem chama decide (descarta)."""
    if not pmcid:
        return None
    url = f"{EPMC_BASE}/PMC/{pmcid}/fullTextXML"
    try:
        xml = _http_get_text(url)
    except Exception as e:
        print(f"[fulltext] falhou pmcid={pmcid}: {e}", flush=True)
        return None
    return _xml_para_texto(xml) or None


def _pmcid_por_doi(doi):
    """Consulta a Europe PMC pelo DOI p/ achar pmcid/isOpenAccess — usado quando o
    artigo veio de OUTRA base (OpenAlex, Semantic Scholar) que não traz esse dado
    embutido no próprio resultado da busca."""
    if not doi:
        return "", ""
    params = {"query": f'DOI:"{doi}"', "format": "json", "pageSize": 1, "resultType": "core"}
    url = EPMC + "?" + urllib.parse.urlencode(params)
    try:
        data = _http_get_json(url)
    except Exception as e:
        print(f"[fulltext] lookup por doi falhou ({doi}): {e}", flush=True)
        return "", ""
    res = data.get("resultList", {}).get("result", [])
    if not res:
        return "", ""
    r0 = res[0]
    return r0.get("pmcid") or "", r0.get("isOpenAccess") or ""


def texto_completo(doi="", pmcid="", is_open_access=""):
    """Texto completo de um artigo — só quando ele é Open Access com PMCID na Europe
    PMC (é a única fonte de full text que este app consegue buscar E ler com stdlib
    puro). Aceita pmcid/isOpenAccess já conhecidos (artigo veio da própria Europe PMC,
    evita 2ª chamada) ou resolve pelo DOI (artigo veio de outra base). None = sem
    texto completo — o chamador NUNCA deve cair pro abstract como substituto."""
    if not (pmcid and is_open_access == "Y"):
        pmcid, is_open_access = _pmcid_por_doi(doi)
    if not (pmcid and is_open_access == "Y"):
        return None
    return texto_completo_pmc(pmcid)


def carregar_tema(nome):
    import os
    cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temas_config.json")
    temas = json.load(open(cfg, encoding="utf-8"))["temas"]
    for k, v in temas.items():
        if k.lower() == nome.lower():
            return v["query"], v.get("excluir", "")
    raise SystemExit(f"Tema '{nome}' nao encontrado. Disponiveis: {list(temas)}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?", default=None, help="query direta (ou use --tema)")
    ap.add_argument("--tema", help="nome do tema em temas_config.json (Obesidade/Hormonios/Lipedema/Longevidade)")
    ap.add_argument("--dias", type=int, default=14)
    ap.add_argument("--max", type=int, default=15)
    ap.add_argument("--tudo", action="store_true", help="desliga o filtro de estudo clinico")
    args = ap.parse_args()
    excluir = ""
    if args.tema:
        query, excluir = carregar_tema(args.tema)
    elif args.query:
        query = args.query
    else:
        raise SystemExit("informe uma query ou --tema")
    ate = datetime.now()
    desde = ate - timedelta(days=args.dias)
    res = buscar_epmc(query, desde.strftime("%Y-%m-%d"), ate.strftime("%Y-%m-%d"), 40, clinico=not args.tudo, excluir=excluir)
    itens = []
    for r in res:
        ab = r.get("abstractText", "") or ""
        if len(ab) < 120:
            continue
        j = r.get("journalTitle") or ""
        itens.append({
            "titulo": r.get("title", "").strip(),
            "journal": j, "data": r.get("firstPublicationDate", ""),
            "doi": r.get("doi", ""), "pmid": r.get("pmid", ""),
            "tipo": r.get("pubTypeList", {}).get("pubType", []),
            "renome": any(k in j.lower() for k in RENOME),
            "abstract": " ".join(ab.split()),
        })
    itens.sort(key=lambda x: (x["renome"], x["data"]), reverse=True)
    print(f"[busca] {len(itens)} estudos com abstract (ult. {args.dias} dias)\n")
    for i, s in enumerate(itens[:args.max], 1):
        print("=" * 70)
        print(f"{i}. {'[RENOME] ' if s['renome'] else ''}{s['titulo']}")
        print(f"   {s['journal']} | {s['data']} | doi:{s['doi']} | PMID:{s['pmid']}")
        tipos = ", ".join(t for t in s["tipo"] if t) if s["tipo"] else ""
        if tipos:
            print(f"   tipo: {tipos}")
        print(f"   ABSTRACT: {s['abstract'][:1400]}")
        print()

if __name__ == "__main__":
    main()
