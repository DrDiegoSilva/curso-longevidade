"""Conectores multi-banco + normalização. Rede não é testada; parsers sim.

Cada artigo normalizado tem o formato:
  {"titulo","resumo","fonte","doi","url","data","tipo","banco"}
banco ∈ europepmc|pubmed|clinicaltrials
"""
import os
import time
import json
import urllib.request
import urllib.parse
import urllib.error

# OpenAlex pede um contato p/ o "polite pool" (grátis, sem chave).
_MAILTO = os.environ.get("OPENALEX_MAILTO") or "contato@drdiegosilva.com.br"


def _get(url, headers=None, timeout=40):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "DSCurso/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _get_backoff(url, headers=None, tentativas=4, base=1.0, sleep=time.sleep):
    """GET com BACKOFF EXPONENCIAL em 429/5xx (protege a API do parceiro — ex.: Semantic
    Scholar). Espera base, 2·base, 4·base… entre tentativas; relança no fim ou em erro fatal."""
    espera = base
    for i in range(tentativas):
        try:
            return _get(url, headers=headers)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and i < tentativas - 1:
                sleep(espera)
                espera *= 2
                continue
            raise


def parse_pubmed_esummary(data):
    out = []
    res = (data or {}).get("result", {})
    for uid in res.get("uids", []):
        it = res.get(uid, {})
        doi = ""
        for aid in it.get("articleids", []):
            if aid.get("idtype") == "doi":
                doi = aid.get("value", "")
        out.append({
            "titulo": (it.get("title") or "").strip(),
            "resumo": "",  # esummary não traz abstract
            "fonte": it.get("fulljournalname") or it.get("source") or "",
            "doi": doi,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{uid}/",
            "data": it.get("pubdate", ""),
            "tipo": ",".join(it.get("pubtype", []) or []),
            "banco": "pubmed",
        })
    return out


def parse_clinicaltrials(data):
    out = []
    for s in (data or {}).get("studies", []):
        ps = s.get("protocolSection", {})
        ident = ps.get("identificationModule", {})
        nct = ident.get("nctId", "")
        out.append({
            "titulo": (ident.get("briefTitle") or "").strip(),
            "resumo": (ps.get("descriptionModule", {}).get("briefSummary") or "").strip(),
            "fonte": "ClinicalTrials.gov",
            "doi": "",
            "url": f"https://clinicaltrials.gov/study/{nct}",
            "data": ps.get("statusModule", {}).get("lastUpdatePostDateStruct", {}).get("date", ""),
            "tipo": ps.get("designModule", {}).get("studyType", ""),
            "banco": "clinicaltrials",
        })
    return out


def _epmc_normalizado(query, desde, ate):
    from buscar_estudos import buscar_epmc
    out = []
    for r in buscar_epmc(query, desde, ate, 40, clinico=True):
        ab = r.get("abstractText") or ""
        if len(ab) < 120:
            continue
        out.append({
            "titulo": (r.get("title") or "").strip(),
            "resumo": " ".join(ab.split()),
            "fonte": r.get("journalTitle") or "",
            "doi": r.get("doi", ""),
            "url": (f"https://doi.org/{r['doi']}" if r.get("doi") else ""),
            "data": r.get("firstPublicationDate", ""),
            "tipo": ",".join(r.get("pubTypeList", {}).get("pubType", []) or []),
            "banco": "europepmc",
        })
    return out


def reconstruir_abstract(inv):
    """OpenAlex entrega o abstract como índice invertido {palavra:[posições]}.
    Reconstrói o texto na ordem. Puro/testável."""
    if not inv:
        return ""
    pos = {}
    for palavra, idxs in inv.items():
        for i in idxs:
            pos[i] = palavra
    return " ".join(pos[i] for i in sorted(pos))


def _openalex_normalizado(query, desde, ate):
    """OpenAlex: 250M+ trabalhos, abstract + citações, sem chave. Só artigos COM abstract."""
    filtro = f"from_publication_date:{desde},to_publication_date:{ate},type:article,has_abstract:true"
    url = ("https://api.openalex.org/works?search=" + urllib.parse.quote(query)
           + "&filter=" + urllib.parse.quote(filtro)
           + "&per-page=40&sort=relevance_score:desc&mailto=" + urllib.parse.quote(_MAILTO))
    out = []
    for w in _get(url).get("results", []):
        ab = reconstruir_abstract(w.get("abstract_inverted_index"))
        if len(ab) < 120:
            continue
        src = (w.get("primary_location") or {}).get("source") or {}
        doi = (w.get("doi") or "").replace("https://doi.org/", "")
        out.append({
            "titulo": (w.get("title") or "").strip(),
            "resumo": " ".join(ab.split()),
            "fonte": src.get("display_name") or "",
            "doi": doi,
            "url": w.get("doi") or w.get("id") or "",
            "data": w.get("publication_date", ""),
            "tipo": w.get("type", ""),
            "banco": "openalex",
        })
    return out


def parse_semanticscholar(data):
    """Normaliza a resposta do Semantic Scholar. Só artigos COM abstract. Puro/testável."""
    out = []
    for p in (data or {}).get("data", []) or []:
        ab = (p.get("abstract") or "").strip()
        if len(ab) < 120:
            continue
        doi = (p.get("externalIds") or {}).get("DOI") or ""
        out.append({
            "titulo": (p.get("title") or "").strip(),
            "resumo": " ".join(ab.split()),
            "fonte": p.get("venue") or "",
            "doi": doi,
            "url": (f"https://doi.org/{doi}" if doi else (p.get("url") or "")),
            "data": p.get("publicationDate") or (str(p.get("year")) if p.get("year") else ""),
            "tipo": "",
            "banco": "semanticscholar",
        })
    return out


def _semanticscholar_normalizado(query, desde, ate):
    """Semantic Scholar (200M+ papers, abstract + TLDR). EXIGE chave grátis
    (SEMANTIC_SCHOLAR_KEY); sem chave, devolve [] (evita o 429 do pool público)."""
    key = os.environ.get("SEMANTIC_SCHOLAR_KEY")
    if not key:
        return []
    anos = f"{(desde or '')[:4]}-{(ate or '')[:4]}"
    url = ("https://api.semanticscholar.org/graph/v1/paper/search?query=" + urllib.parse.quote(query)
           + "&fields=title,abstract,venue,year,publicationDate,externalIds&limit=40&year=" + urllib.parse.quote(anos))
    return parse_semanticscholar(_get_backoff(url, headers={"User-Agent": "DSCurso/1.0", "x-api-key": key}))


def _pubmed(query, desde, ate):
    q = urllib.parse.quote(f"{query} AND ({desde}[dp] : {ate}[dp])")
    ids = _get(f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&retmode=json&retmax=30&term={q}")
    uids = ids.get("esearchresult", {}).get("idlist", [])
    if not uids:
        return []
    data = _get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&retmode=json&id=" + ",".join(uids))
    return parse_pubmed_esummary(data)


def _clinicaltrials(query, desde, ate):
    q = urllib.parse.quote(query)
    data = _get(f"https://clinicaltrials.gov/api/v2/studies?query.term={q}&pageSize=20&sort=LastUpdatePostDate:desc")
    return parse_clinicaltrials(data)


def search_all(query, desde, ate):
    """Agrega os bancos que ENTREGAM abstract. Falha de um NÃO derruba os outros.
    PubMed (esummary) foi aposentado: vem SEM abstract e o Europe PMC já indexa o MEDLINE.
    Semantic Scholar entra só se SEMANTIC_SCHOLAR_KEY estiver setada (sem chave → [], sem 429)."""
    arts = []
    for fn in (_epmc_normalizado, _openalex_normalizado, _semanticscholar_normalizado, _clinicaltrials):
        try:
            arts += fn(query, desde, ate)
        except Exception as e:
            print(f"[sources] {fn.__name__} falhou: {e}", flush=True)
    return arts
