"""
Busca estudos científicos recentes por tema em APIs abertas (Europe PMC).
Prioriza journals de renome. Imprime estruturado para síntese posterior.
Uso: python buscar_estudos.py "obesity OR GLP-1 OR tirzepatide" --dias 14 --max 15
Futuro (VPS): adicionar OpenAlex/Crossref/medRxiv/ClinicalTrials/openFDA.
"""
import sys, json, argparse, urllib.request, urllib.parse
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
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

# Só estudo clínico relevante (corta animal/cultura celular/epidemiologia solta)
FILTRO_CLINICO = ('(PUB_TYPE:"Randomized Controlled Trial" OR PUB_TYPE:"Meta-Analysis" '
                  'OR PUB_TYPE:"Systematic Review" OR PUB_TYPE:"Clinical Trial" '
                  'OR PUB_TYPE:"Guideline" OR PUB_TYPE:"Practice Guideline")')

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
    req = urllib.request.Request(url, headers={"User-Agent": "HealthBot/1.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        data = json.loads(r.read())
    return data.get("resultList", {}).get("result", [])

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
