# Plano 1 — Máquina de Conteúdo (Digest Científico Diário) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evoluir o app `curso-longevidade` para, todo dia, buscar em vários bancos científicos, escolher o melhor artigo, resumir com rigor, gerar um PDF bonito, mandar o rascunho às 18h para o Dr. Diego revisar por link secreto e, às 08h (se não vetado), enviar o resumo + PDF para uma lista-semente de assinantes no WhatsApp.

**Architecture:** App único em container Python (stdlib no runtime), servido em `curso.drdiegosilva.com.br`, isolado do clinicdspro. Estado em arquivos JSON no volume `/data`. O `serve.py` já é web-server + agendador; estendemos para dois disparos (18h preparar/avisar, 08h enviar) e novas páginas web (`/revisar/<token>`, admin da lista). A cascata de IA e o Z-API já existem em `resumo_diario.py` e são reaproveitados.

**Tech Stack:** Python 3.12 stdlib (`http.server`, `urllib`, `json`, `zoneinfo`), Claude API (chave dedicada), Z-API (WhatsApp), Chromium headless para renderizar HTML→PDF. Testes com `unittest` (stdlib, sem pip).

## Global Constraints

- **Runtime = Python stdlib apenas** (sem `pip install`), EXCETO a **única exceção sancionada**: o binário **Chromium** (via `apt-get`) para renderizar o PDF bonito. Nenhuma lib Python de terceiros.
- **Testes = `unittest` (stdlib)**, rodados com `python -m unittest`. Sem pytest, sem dependências de teste.
- **Isolamento absoluto:** nada de tocar no clinicdspro, seu banco ou dados de paciente. Repo é `DrDiegoSilva/curso-longevidade`.
- **Estado persistente vive em `/data`** (volume). Código em `/app`. Nunca gravar estado em `/app` (efêmero).
- **Fuso = `America/Sao_Paulo`** em todo agendamento e data.
- **Sem segredos no repo.** Credenciais só por env var (`config.py`).
- **Idioma pt-BR** em toda copy destinada ao médico/curador; resumo clínico técnico, **sem seção "para paciente"**, **sem inventar número** fora do abstract.
- **Nunca falhar em silêncio:** toda falha de job avisa o Dr. Diego no WhatsApp (padrão já existente em `resumo_diario.py`).
- Reaproveitar o que existe: `config.py` (env), `buscar_estudos.buscar_epmc`, `resumo_diario.claude`, o wrapper Z-API. Não duplicar.

---

## File Structure

**Novos arquivos (`app/`):**
- `sources.py` — conectores de busca multi-banco + normalização (PubMed, ClinicalTrials.gov, medRxiv) e um `search_all()` unificado. Europe PMC continua em `buscar_estudos.py` e é agregado aqui.
- `selection.py` — funções puras: dedupe, ranking, escolha do artigo do dia.
- `draft_store.py` — persistência + máquina de estado do rascunho do dia em `/data/drafts/`.
- `pdf.py` — monta o HTML do PDF (função pura) e renderiza via Chromium.
- `subscribers.py` — CRUD da lista-semente em `/data/subscribers.json`.
- `deliver.py` — envio WhatsApp texto + PDF à lista, com personalização e throttle (partes puras testáveis).
- `review_web.py` — handlers das páginas `/revisar/<token>` e admin da lista (montagem de HTML pura + integração no `serve.py`).
- `daily.py` — orquestra o job das 18h (preparar rascunho + avisar curador) e o das 08h (enviar se aprovado). Usa `resumo_diario` para o texto e `pdf`/`deliver`/`draft_store`.

**Modificados:**
- `config.py` — novas chaves de env: `DSCURSO_DATA` (default `/data`), `DSCURSO_ADMIN_TOKEN`, `DSCURSO_PUBLIC_URL`, `DSCURSO_SEND_DELAY_SEC`.
- `serve.py` — agendador passa a ter 2 alvos (18h/08h) e o `Handler` roteia as novas páginas.
- `Dockerfile` — instala `chromium`.

**Testes (`tests/`):**
- `tests/test_sources.py`, `tests/test_selection.py`, `tests/test_draft_store.py`, `tests/test_pdf.py`, `tests/test_subscribers.py`, `tests/test_deliver.py`, `tests/fixtures/` (JSONs de resposta gravados das APIs).

---

### Task 1: Config + caminhos de `/data`

**Files:**
- Modify: `app/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `config.DATA` (str, default `/data`), `config.drafts_dir()`→`{DATA}/drafts`, `config.subscribers_path()`→`{DATA}/subscribers.json`, `config.ADMIN_TOKEN` (str|None), `config.PUBLIC_URL` (str, default `https://curso.drdiegosilva.com.br`), `config.SEND_DELAY_SEC` (float, default `4.0`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import os, unittest, importlib

class TestConfig(unittest.TestCase):
    def test_data_paths_from_env(self):
        os.environ["DSCURSO_DATA"] = "/tmp/dscurso-x"
        os.environ["DSCURSO_ADMIN_TOKEN"] = "segredo123"
        import app.config as config
        importlib.reload(config)
        self.assertEqual(config.DATA, "/tmp/dscurso-x")
        self.assertTrue(config.drafts_dir().endswith("/drafts"))
        self.assertTrue(config.subscribers_path().endswith("subscribers.json"))
        self.assertEqual(config.ADMIN_TOKEN, "segredo123")
        self.assertEqual(config.SEND_DELAY_SEC, 4.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/dev/curso-longevidade && python -m unittest tests.test_config -v`
Expected: FAIL — `AttributeError: module 'app.config' has no attribute 'DATA'`

- [ ] **Step 3: Add to `app/config.py` (after the existing `BASE` block)**

```python
# ── Estado persistente (volume /data) ──
DATA = os.environ.get("DSCURSO_DATA") or "/data"
def drafts_dir():
    return os.path.join(DATA, "drafts")
def subscribers_path():
    return os.path.join(DATA, "subscribers.json")

ADMIN_TOKEN = os.environ.get("DSCURSO_ADMIN_TOKEN")
PUBLIC_URL = (os.environ.get("DSCURSO_PUBLIC_URL") or "https://curso.drdiegosilva.com.br").rstrip("/")
SEND_DELAY_SEC = float(os.environ.get("DSCURSO_SEND_DELAY_SEC") or "4.0")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_config -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "feat(config): caminhos de /data, admin token, url pública e delay de envio"
```

---

### Task 2: Conectores multi-banco + normalização

Bancos novos além do Europe PMC (que já existe em `buscar_estudos.buscar_epmc`): **PubMed** (E-utilities esearch+esummary), **ClinicalTrials.gov v2**, **medRxiv**. Cada resposta vira o mesmo dicionário normalizado. As chamadas de rede não são testadas unitariamente; testamos os **parsers** com fixtures gravadas.

**Files:**
- Create: `app/sources.py`
- Create: `tests/test_sources.py`, `tests/fixtures/pubmed_esummary.json`, `tests/fixtures/clinicaltrials_v2.json`
- Test: `tests/test_sources.py`

**Interfaces:**
- Consumes: `buscar_estudos.buscar_epmc` (Europe PMC).
- Produces:
  - Artigo normalizado = `{"titulo": str, "resumo": str, "fonte": str, "doi": str, "url": str, "data": str, "tipo": str, "banco": str}` (`banco` ∈ `europepmc|pubmed|clinicaltrials|medrxiv`).
  - `parse_pubmed_esummary(dict) -> list[dict]`
  - `parse_clinicaltrials(dict) -> list[dict]`
  - `search_all(query: str, desde: str, ate: str) -> list[dict]` (agrega os bancos; captura exceção por banco e segue).

- [ ] **Step 1: Write the failing test (parsers com fixtures)**

```python
# tests/test_sources.py
import json, os, unittest
from app import sources

FX = os.path.join(os.path.dirname(__file__), "fixtures")

class TestParsers(unittest.TestCase):
    def test_parse_pubmed(self):
        data = json.load(open(os.path.join(FX, "pubmed_esummary.json"), encoding="utf-8"))
        arts = sources.parse_pubmed_esummary(data)
        self.assertTrue(len(arts) >= 1)
        a = arts[0]
        self.assertEqual(a["banco"], "pubmed")
        self.assertTrue(a["titulo"])
        self.assertTrue(a["url"].startswith("http"))

    def test_parse_clinicaltrials(self):
        data = json.load(open(os.path.join(FX, "clinicaltrials_v2.json"), encoding="utf-8"))
        arts = sources.parse_clinicaltrials(data)
        self.assertTrue(len(arts) >= 1)
        self.assertEqual(arts[0]["banco"], "clinicaltrials")
        self.assertTrue(arts[0]["url"].startswith("https://clinicaltrials.gov/"))
```

- [ ] **Step 2: Create the fixtures**

Grave 1 amostra real de cada API (poucos itens) — capture com:
```bash
mkdir -p tests/fixtures
curl -s "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&retmode=json&id=38768591" > tests/fixtures/pubmed_esummary.json
curl -s "https://clinicaltrials.gov/api/v2/studies?query.term=tirzepatide&pageSize=2" > tests/fixtures/clinicaltrials_v2.json
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m unittest tests.test_sources -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.sources'`

- [ ] **Step 4: Write `app/sources.py`**

```python
"""Conectores multi-banco + normalização. Rede não é testada; parsers sim."""
import json, urllib.request, urllib.parse

def _get(url, headers=None, timeout=40):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "DSCurso/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

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
            "resumo": "",  # esummary não traz abstract; enriquecido depois se preciso
            "fonte": it.get("fulljournalname") or it.get("source") or "",
            "doi": doi, "url": f"https://pubmed.ncbi.nlm.nih.gov/{uid}/",
            "data": it.get("pubdate", ""), "tipo": ",".join(it.get("pubtype", []) or []),
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
            "fonte": "ClinicalTrials.gov", "doi": "",
            "url": f"https://clinicaltrials.gov/study/{nct}",
            "data": ps.get("statusModule", {}).get("lastUpdatePostDateStruct", {}).get("date", ""),
            "tipo": ps.get("designModule", {}).get("studyType", ""), "banco": "clinicaltrials",
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
            "titulo": (r.get("title") or "").strip(), "resumo": " ".join(ab.split()),
            "fonte": r.get("journalTitle") or "", "doi": r.get("doi", ""),
            "url": (f"https://doi.org/{r['doi']}" if r.get("doi") else ""),
            "data": r.get("firstPublicationDate", ""),
            "tipo": ",".join(r.get("pubTypeList", {}).get("pubType", []) or []), "banco": "europepmc",
        })
    return out

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
    """Agrega todos os bancos. Falha de um banco NÃO derruba os outros."""
    arts = []
    for fn in (_epmc_normalizado, _pubmed, _clinicaltrials):
        try:
            arts += fn(query, desde, ate)
        except Exception as e:
            print(f"[sources] {fn.__name__} falhou: {e}", flush=True)
    return arts
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m unittest tests.test_sources -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/sources.py tests/test_sources.py tests/fixtures/
git commit -m "feat(sources): conectores PubMed/ClinicalTrials + agregador search_all (Europe PMC incluso)"
```

> _medRxiv fica coberto pelo Europe PMC (indexa preprints); um conector dedicado é melhoria futura — não bloquear a Fase 1._

---

### Task 3: Seleção do artigo do dia (puro)

**Files:**
- Create: `app/selection.py`
- Test: `tests/test_selection.py`

**Interfaces:**
- Consumes: artigos normalizados (Task 2).
- Produces:
  - `dedupe(arts, ja_enviados: set[str]) -> list[dict]` (remove por `doi` ou `url` já visto).
  - `rank(arts) -> list[dict]` (ordena: tem-DOI + tipo forte (RCT/meta/guideline) + data desc).
  - `escolher_do_dia(arts, ja_enviados) -> dict | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_selection.py
import unittest
from app import selection

def art(**k):
    base = {"titulo": "x", "resumo": "y", "fonte": "z", "doi": "", "url": "", "data": "2026-07-10", "tipo": "", "banco": "europepmc"}
    base.update(k); return base

class TestSelection(unittest.TestCase):
    def test_dedupe_por_doi_e_url(self):
        arts = [art(doi="10.1/a"), art(doi="10.1/a"), art(url="http://u/1")]
        out = selection.dedupe(arts, {"10.1/a"})
        self.assertEqual(len(out), 1)  # os dois com doi visto saem; sobra o de url novo

    def test_rank_prioriza_estudo_forte_recente(self):
        fraco = art(doi="10/f", tipo="Editorial", data="2026-07-11")
        forte = art(doi="10/s", tipo="Meta-Analysis", data="2026-07-01")
        out = selection.rank([fraco, forte])
        self.assertEqual(out[0]["doi"], "10/s")

    def test_escolher_none_quando_tudo_ja_enviado(self):
        arts = [art(doi="10/a")]
        self.assertIsNone(selection.escolher_do_dia(arts, {"10/a"}))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_selection -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.selection'`

- [ ] **Step 3: Write `app/selection.py`**

```python
"""Escolha do artigo do dia — funções puras, testáveis."""
_FORTE = ("meta-analysis", "randomized", "systematic review", "guideline", "practice guideline")

def _chave(a):
    return a.get("doi") or a.get("url") or a.get("titulo")

def dedupe(arts, ja_enviados):
    vistos, out = set(), []
    for a in arts:
        k = _chave(a)
        if not k or k in ja_enviados or k in vistos:
            continue
        vistos.add(k); out.append(a)
    return out

def _forca(a):
    t = (a.get("tipo") or "").lower()
    return 1 if any(f in t for f in _FORTE) else 0

def rank(arts):
    return sorted(arts, key=lambda a: (bool(a.get("doi")), _forca(a), a.get("data", "")), reverse=True)

def escolher_do_dia(arts, ja_enviados):
    ok = rank(dedupe(arts, ja_enviados))
    return ok[0] if ok else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_selection -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/selection.py tests/test_selection.py
git commit -m "feat(selection): dedupe + ranking + escolha do artigo do dia (puro, TDD)"
```

---

### Task 4: Draft store + máquina de estado (puro)

**Files:**
- Create: `app/draft_store.py`
- Test: `tests/test_draft_store.py`

**Interfaces:**
- Produces:
  - `novo_rascunho(data_iso, artigo, resumo, pdf_path) -> dict` (gera `review_token` aleatório, `status="DRAFT"`).
  - `salvar(rascunho)`, `carregar(data_iso) -> dict|None`, `por_token(token) -> dict|None`.
  - `aplicar(data_iso, acao, texto=None) -> dict` — `acao ∈ {"aprovar","editar","nao_enviar"}`; transições: `DRAFT→APPROVED|EDITED|SKIPPED`.
  - Status válidos: `DRAFT, APPROVED, EDITED, SKIPPED, SENT`. `pode_enviar(status) -> bool` = status ≠ `SKIPPED` e ≠ `SENT`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_draft_store.py
import os, tempfile, unittest, importlib

class TestDraftStore(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.d
        import app.config as config; importlib.reload(config)
        import app.draft_store as ds; importlib.reload(ds); self.ds = ds

    def test_ciclo_criar_salvar_carregar_por_token(self):
        r = self.ds.novo_rascunho("2026-07-18", {"titulo": "T"}, "resumo", "/data/x.pdf")
        self.assertEqual(r["status"], "DRAFT")
        self.assertTrue(len(r["review_token"]) >= 20)
        self.ds.salvar(r)
        self.assertEqual(self.ds.carregar("2026-07-18")["artigo"]["titulo"], "T")
        self.assertEqual(self.ds.por_token(r["review_token"])["data"], "2026-07-18")

    def test_transicoes(self):
        r = self.ds.novo_rascunho("2026-07-18", {"titulo": "T"}, "resumo", "/x.pdf"); self.ds.salvar(r)
        self.assertEqual(self.ds.aplicar("2026-07-18", "editar", "novo texto")["status"], "EDITED")
        self.assertEqual(self.ds.carregar("2026-07-18")["resumo"], "novo texto")
        self.assertEqual(self.ds.aplicar("2026-07-18", "nao_enviar")["status"], "SKIPPED")
        self.assertFalse(self.ds.pode_enviar("SKIPPED"))
        self.assertTrue(self.ds.pode_enviar("DRAFT"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_draft_store -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.draft_store'`

- [ ] **Step 3: Write `app/draft_store.py`**

```python
"""Rascunho do dia: persistência em /data/drafts + máquina de estado."""
import os, json, secrets, glob
from datetime import datetime
import config

VALIDOS = {"DRAFT", "APPROVED", "EDITED", "SKIPPED", "SENT"}

def _path(data_iso):
    return os.path.join(config.drafts_dir(), f"{data_iso}.json")

def novo_rascunho(data_iso, artigo, resumo, pdf_path):
    return {"data": data_iso, "status": "DRAFT", "review_token": secrets.token_urlsafe(24),
            "artigo": artigo, "resumo": resumo, "pdf_path": pdf_path,
            "criado_em": datetime.now().isoformat(), "decidido_em": None}

def salvar(r):
    os.makedirs(config.drafts_dir(), exist_ok=True)
    with open(_path(r["data"]), "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=1)

def carregar(data_iso):
    try:
        return json.load(open(_path(data_iso), encoding="utf-8"))
    except Exception:
        return None

def por_token(token):
    for p in glob.glob(os.path.join(config.drafts_dir(), "*.json")):
        try:
            r = json.load(open(p, encoding="utf-8"))
            if r.get("review_token") == token:
                return r
        except Exception:
            pass
    return None

def pode_enviar(status):
    return status not in ("SKIPPED", "SENT")

def aplicar(data_iso, acao, texto=None):
    r = carregar(data_iso)
    if not r:
        raise ValueError("rascunho não encontrado")
    if acao == "aprovar":
        r["status"] = "APPROVED"
    elif acao == "editar":
        r["status"] = "EDITED"; r["resumo"] = texto or r["resumo"]
    elif acao == "nao_enviar":
        r["status"] = "SKIPPED"
    else:
        raise ValueError(f"ação inválida: {acao}")
    r["decidido_em"] = datetime.now().isoformat()
    salvar(r); return r
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_draft_store -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/draft_store.py tests/test_draft_store.py
git commit -m "feat(draft): store + máquina de estado do rascunho do dia (TDD)"
```

---

### Task 5: PDF bonito (HTML puro + render Chromium)

**Files:**
- Create: `app/pdf.py`, `app/pdf_template.html` (opcional inline)
- Modify: `Dockerfile`
- Test: `tests/test_pdf.py`

**Interfaces:**
- Consumes: `artigo` (dict) + `resumo` (str) + `nome_medico` (str).
- Produces:
  - `montar_html(artigo, resumo, nome_medico) -> str` (puro, testável).
  - `gerar_pdf(html, out_path) -> str` (renderiza via Chromium; integração).

- [ ] **Step 1: Write the failing test (HTML puro)**

```python
# tests/test_pdf.py
import unittest
from app import pdf

class TestPdfHtml(unittest.TestCase):
    def test_html_contem_dados_e_nome(self):
        art = {"titulo": "Tirzepatida X", "fonte": "NEJM", "doi": "10.1/a", "url": "https://doi.org/10.1/a", "data": "2026-07"}
        html = pdf.montar_html(art, "Achado principal: ...", "Dr. Fulano")
        self.assertIn("Tirzepatida X", html)
        self.assertIn("NEJM", html)
        self.assertIn("Dr. Fulano", html)       # marca d'água / personalização
        self.assertIn("10.1/a", html)            # referência/DOI
        self.assertTrue(html.strip().lower().startswith("<!doctype html"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_pdf -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.pdf'`

- [ ] **Step 3: Write `app/pdf.py`**

```python
"""PDF bonito: HTML+CSS (puro) renderizado por Chromium headless."""
import os, subprocess, tempfile, html as _html

def montar_html(artigo, resumo, nome_medico):
    esc = _html.escape
    corpo = "".join(f"<p>{esc(l)}</p>" for l in (resumo or "").split("\n") if l.strip())
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<style>
  @page {{ size: A4; margin: 22mm 18mm; }}
  body {{ font-family: Georgia, serif; color:#1a2b28; line-height:1.5; }}
  .marca {{ color:#0f4c3a; font-size:12px; letter-spacing:.12em; text-transform:uppercase; }}
  h1 {{ font-size:20px; color:#0f4c3a; margin:.2em 0; }}
  .meta {{ color:#6b7a76; font-size:12px; border-bottom:2px solid #c9a227; padding-bottom:8px; }}
  .corpo p {{ margin:.5em 0; }}
  .rodape {{ margin-top:24px; font-size:10px; color:#6b7a76; border-top:1px solid #ddd; padding-top:8px; }}
  .agua {{ position:fixed; bottom:12mm; right:18mm; font-size:9px; color:#b8c4c0; }}
</style></head><body>
  <div class="marca">Dr. Diego Silva · Atualização científica</div>
  <h1>{esc(artigo.get('titulo',''))}</h1>
  <div class="meta">{esc(artigo.get('fonte',''))} · {esc(artigo.get('data',''))} · DOI {esc(artigo.get('doi','—'))}</div>
  <div class="corpo">{corpo}</div>
  <div class="rodape">Referência: <a href="{esc(artigo.get('url',''))}">{esc(artigo.get('url',''))}</a></div>
  <div class="agua">Exclusivo · {esc(nome_medico)}</div>
</body></html>"""

def _chromium_bin():
    for b in ("chromium", "chromium-browser", "google-chrome"):
        if subprocess.run(["which", b], capture_output=True).returncode == 0:
            return b
    raise RuntimeError("Chromium não encontrado na imagem")

def gerar_pdf(html, out_path):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html); src = f.name
    try:
        subprocess.run([_chromium_bin(), "--headless", "--no-sandbox", "--disable-gpu",
                        f"--print-to-pdf={out_path}", "--no-pdf-header-footer", f"file://{src}"],
                       check=True, timeout=90, capture_output=True)
    finally:
        os.unlink(src)
    return out_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_pdf -v`
Expected: PASS

- [ ] **Step 5: Add Chromium to `Dockerfile`** (junto do `apt-get` que já instala `tzdata`)

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends tzdata chromium \
    && rm -rf /var/lib/apt/lists/* \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
```

- [ ] **Step 6: Commit**

```bash
git add app/pdf.py tests/test_pdf.py Dockerfile
git commit -m "feat(pdf): PDF bonito por HTML+CSS renderizado em Chromium headless"
```

---

### Task 6: Lista-semente de assinantes + CRUD

**Files:**
- Create: `app/subscribers.py`
- Test: `tests/test_subscribers.py`

**Interfaces:**
- Produces:
  - `listar() -> list[dict]`, `adicionar(nome, whatsapp) -> dict`, `remover(id) -> bool`, `ativos() -> list[dict]`.
  - Registro = `{"id", "nome", "whatsapp", "status": "ATIVO", "criado_em"}`. (Na Fase 2 o Asaas preenche isso; aqui é manual.)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_subscribers.py
import os, tempfile, unittest, importlib

class TestSubs(unittest.TestCase):
    def setUp(self):
        os.environ["DSCURSO_DATA"] = tempfile.mkdtemp()
        import app.config as config; importlib.reload(config)
        import app.subscribers as s; importlib.reload(s); self.s = s

    def test_add_list_remove(self):
        a = self.s.adicionar("Dra. Ana", "5543999990000")
        self.assertEqual(a["status"], "ATIVO")
        self.assertEqual(len(self.s.listar()), 1)
        self.assertEqual(len(self.s.ativos()), 1)
        self.assertTrue(self.s.remover(a["id"]))
        self.assertEqual(len(self.s.listar()), 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_subscribers -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write `app/subscribers.py`**

```python
"""Lista-semente de assinantes em /data/subscribers.json."""
import os, json, secrets
from datetime import datetime
import config

def _load():
    try:
        return json.load(open(config.subscribers_path(), encoding="utf-8"))
    except Exception:
        return []

def _save(rows):
    os.makedirs(config.DATA, exist_ok=True)
    with open(config.subscribers_path(), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)

def listar():
    return _load()

def ativos():
    return [r for r in _load() if r.get("status") == "ATIVO"]

def adicionar(nome, whatsapp):
    rows = _load()
    reg = {"id": secrets.token_hex(6), "nome": nome.strip(),
           "whatsapp": "".join(c for c in whatsapp if c.isdigit()),
           "status": "ATIVO", "criado_em": datetime.now().isoformat()}
    rows.append(reg); _save(rows); return reg

def remover(id):
    rows = _load(); novo = [r for r in rows if r.get("id") != id]
    _save(novo); return len(novo) != len(rows)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_subscribers -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/subscribers.py tests/test_subscribers.py
git commit -m "feat(subscribers): lista-semente manual de assinantes (TDD)"
```

---

### Task 7: Entrega (personalização + throttle) para a lista

**Files:**
- Create: `app/deliver.py`
- Test: `tests/test_deliver.py`

**Interfaces:**
- Consumes: `subscribers.ativos()`, `pdf.montar_html`/`gerar_pdf`, o wrapper Z-API.
- Produces:
  - `enviar_texto(whatsapp, msg)` e `enviar_pdf(whatsapp, pdf_path, caption)` (Z-API send-text / send-document).
  - `personalizar_rodape(msg, nome, link) -> str` (puro: adiciona "Minha assinatura: <link>" + nome).
  - `distribuir(rascunho, assinantes, delay_sec, enviar_fn) -> dict` (loop com throttle; retorna `{"ok": n, "falhas": [...]}`; injeta `enviar_fn` p/ testar sem rede).

- [ ] **Step 1: Write the failing test (partes puras + loop com fake)**

```python
# tests/test_deliver.py
import unittest
from app import deliver

class TestDeliver(unittest.TestCase):
    def test_personalizar_rodape(self):
        out = deliver.personalizar_rodape("corpo", "Dra. Ana", "https://x/minha/abc")
        self.assertIn("corpo", out); self.assertIn("Dra. Ana", out); self.assertIn("https://x/minha/abc", out)

    def test_distribuir_conta_ok_e_falhas(self):
        assinantes = [{"whatsapp": "111", "nome": "A"}, {"whatsapp": "222", "nome": "B"}]
        chamadas = []
        def fake(w, nome):
            chamadas.append(w)
            if w == "222":
                raise RuntimeError("z-api caiu")
        r = deliver.distribuir({"resumo": "x"}, assinantes, 0, fake)
        self.assertEqual(r["ok"], 1)
        self.assertEqual(len(r["falhas"]), 1)
        self.assertEqual(chamadas, ["111", "222"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_deliver -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write `app/deliver.py`**

```python
"""Entrega WhatsApp texto + PDF à lista, com personalização e throttle."""
import time, json, urllib.request
import config

def personalizar_rodape(msg, nome, link):
    return f"{msg}\n\n— {nome}\nMinha assinatura / cancelar: {link}"

def _zapi_post(caminho, payload):
    z = config.zapi()
    url = f"https://api.z-api.io/instances/{z['instanceId']}/token/{z['instanceToken']}/{caminho}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
        headers={"Content-Type": "application/json", "Client-Token": z["clientToken"]})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")

def enviar_texto(whatsapp, msg):
    return _zapi_post("send-text", {"phone": whatsapp, "message": msg})

def enviar_pdf(whatsapp, pdf_url, caption=""):
    return _zapi_post("send-document/pdf", {"phone": whatsapp, "document": pdf_url, "caption": caption})

def distribuir(rascunho, assinantes, delay_sec, enviar_fn):
    ok, falhas = 0, []
    for a in assinantes:
        try:
            enviar_fn(a["whatsapp"], a.get("nome", ""))
            ok += 1
        except Exception as e:
            falhas.append({"whatsapp": a.get("whatsapp"), "erro": str(e)})
        time.sleep(delay_sec)
    return {"ok": ok, "falhas": falhas}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_deliver -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/deliver.py tests/test_deliver.py
git commit -m "feat(deliver): entrega texto+PDF com personalização e throttle (loop injetável, TDD)"
```

---

### Task 8: Orquestração diária (18h preparar / 08h enviar)

Junta tudo. Usa `resumo_diario` para gerar o texto do resumo (reaproveita a cascata Haiku→Opus→Sonnet já testada em produção). **Não** tem teste unitário próprio (é orquestração de I/O); é validada pelo dry-run e teste manual.

**Files:**
- Create: `app/daily.py`
- Modify: `app/resumo_diario.py` (extrair uma função `gerar_texto_do_artigo(artigo)` reutilizável — mínima refatoração, sem mudar o comportamento do envio diário atual)

**Interfaces:**
- Consumes: `sources.search_all`, `selection.escolher_do_dia`, `resumo_diario.gerar_texto_do_artigo`, `pdf`, `draft_store`, `subscribers.ativos`, `deliver`, o dedup cache já existente (`resumos_enviados.jsonl`).
- Produces:
  - `preparar_18h()` — escolhe artigo, gera resumo+PDF, salva `DRAFT`, avisa o curador no WhatsApp com o link `/revisar/<token>`.
  - `enviar_08h()` — carrega o rascunho do dia; se `pode_enviar`, distribui à lista, marca `SENT`, registra dedup.

- [ ] **Step 1: Extrair função reutilizável em `resumo_diario.py`**

Adicione (sem alterar `main()`), uma função fina que resume UM artigo já escolhido, reusando `claude` + `SYS_APROF`:

```python
def gerar_texto_do_artigo(artigo):
    """Resumo clínico estruturado de UM artigo já escolhido (reusa a voz SYS_APROF)."""
    blob = (f"### {artigo.get('titulo','')}\nData: {artigo.get('data','')}\n"
            f"Fonte: {artigo.get('fonte','')} | doi:{artigo.get('doi','')}\n{artigo.get('resumo','')}")
    return claude(OPUS, f"Aprofunde ESTE estudo para o médico (abra pela data de publicação):\n\n{blob}",
                  system=SYS_APROF, max_tokens=3200)
```

- [ ] **Step 2: Write `app/daily.py`**

```python
"""Orquestra os jobs diários: 18h prepara+avisa curador; 08h envia à lista."""
import os, json
from datetime import datetime, timedelta
import config, sources, selection, draft_store, subscribers, deliver
import resumo_diario as rd
import buscar_estudos as be

def _hoje_iso():
    return datetime.now().strftime("%Y-%m-%d")

def _tema_do_dia():
    cfg = json.load(open(os.path.join(os.path.dirname(__file__), "temas_config.json"), encoding="utf-8"))
    dias = ["segunda","terca","quarta","quinta","sexta","sabado","domingo"]
    plano = cfg["calendario"][dias[datetime.now().weekday()]]
    return plano["tema"]

def _ja_enviados():
    return rd.dois_enviados()

def preparar_18h():
    tema = _tema_do_dia()
    query, _exc = be.carregar_tema(tema)
    ate = datetime.now(); desde = ate - timedelta(days=14)
    arts = sources.search_all(query, desde.strftime("%Y-%m-%d"), ate.strftime("%Y-%m-%d"))
    art = selection.escolher_do_dia(arts, _ja_enviados())
    if not art:
        rd.enviar_zap(f"📭 Sem artigo forte hoje ({tema}). Nada preparado — me chama se quiser forçar.")
        return None
    resumo = rd.gerar_texto_do_artigo(art)
    hoje = _hoje_iso()
    os.makedirs(config.drafts_dir(), exist_ok=True)
    pdf_path = os.path.join(config.drafts_dir(), f"{hoje}.pdf")
    import pdf as pdfmod
    pdfmod.gerar_pdf(pdfmod.montar_html(art, resumo, "Dr. Diego (revisão)"), pdf_path)
    r = draft_store.novo_rascunho(hoje, art, resumo, pdf_path); draft_store.salvar(r)
    link = f"{config.PUBLIC_URL}/revisar/{r['review_token']}"
    rd.enviar_zap(f"📋 Resumo de AMANHÃ pronto:\n*{art['titulo']}*\nFonte: {art.get('fonte','')}\n"
                  f"Assinantes: {len(subscribers.ativos())}\n\n👉 Revisar/editar: {link}\n"
                  f"(se não mexer, envio automático às 08h)")
    return r

def enviar_08h():
    hoje = _hoje_iso()
    r = draft_store.carregar(hoje)
    if not r or not draft_store.pode_enviar(r["status"]):
        rd.enviar_zap(f"⏭️ Nada enviado hoje ({'sem rascunho' if not r else r['status']}).")
        return
    art, resumo = r["artigo"], r["resumo"]
    pdf_url = f"{config.PUBLIC_URL}/pdf/{hoje}"  # servido pela Task 9
    import pdf as pdfmod
    def _envia(whatsapp, nome):
        link = f"{config.PUBLIC_URL}/minha/{whatsapp}"   # placeholder Fase 1 (link real vem na Fase 2)
        msg = deliver.personalizar_rodape(f"🔬 *{art['titulo']}*\n\n{resumo}", nome, link)
        deliver.enviar_texto(whatsapp, msg)
        deliver.enviar_pdf(whatsapp, pdf_url, caption=art["titulo"])
    res = deliver.distribuir(r, subscribers.ativos(), config.SEND_DELAY_SEC, _envia)
    r["status"] = "SENT"; draft_store.salvar(r)
    rd.registrar([art["doi"]] if art.get("doi") else [])
    rd.enviar_zap(f"✅ Enviado: {res['ok']} assinantes"
                  + (f" · {len(res['falhas'])} falhas" if res["falhas"] else ""))
```

- [ ] **Step 3: Smoke-test manual (dry-run seguro)**

Run (com envs de teste apontando o WhatsApp para o número do curador e uma lista-semente só com o seu número):
```bash
cd app && python -c "import daily; daily.preparar_18h()"
```
Expected: chega no seu WhatsApp a mensagem com o link `/revisar/<token>` e um PDF gerado em `/data/drafts/<hoje>.pdf`.

- [ ] **Step 4: Commit**

```bash
git add app/daily.py app/resumo_diario.py
git commit -m "feat(daily): orquestra 18h (preparar+avisar) e 08h (enviar à lista)"
```

---

### Task 9: Páginas web (revisão + PDF + admin) e roteamento

**Files:**
- Create: `app/review_web.py`
- Modify: `app/serve.py`
- Test: `tests/test_review_web.py`

**Interfaces:**
- Consumes: `draft_store`, `subscribers`, `config.ADMIN_TOKEN`.
- Produces (montagem de HTML pura, testável):
  - `pagina_revisao(rascunho) -> str`, `pagina_admin(assinantes) -> str`.
  - Handlers integrados no `serve.py`: `GET /revisar/<token>`, `POST /revisar/<token>` (campos `acao`, `texto`), `GET /pdf/<data>`, `GET /admin?token=` + `POST /admin` (add/remove), `GET /health`.

- [ ] **Step 1: Write the failing test (HTML puro)**

```python
# tests/test_review_web.py
import unittest
from app import review_web

class TestReviewWeb(unittest.TestCase):
    def test_pagina_revisao_tem_texto_e_botoes(self):
        r = {"data": "2026-07-18", "review_token": "tok", "resumo": "meu resumo",
             "artigo": {"titulo": "T", "fonte": "NEJM"}}
        html = review_web.pagina_revisao(r)
        self.assertIn("meu resumo", html)
        self.assertIn("Aprovar", html)
        self.assertIn("Não enviar", html)
        self.assertIn('action="/revisar/tok"', html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_review_web -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write `app/review_web.py`**

```python
"""HTML das páginas de revisão e admin (montagem pura) + helpers de roteamento."""
import html as _html

def pagina_revisao(r):
    esc = _html.escape; a = r.get("artigo", {})
    return f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<body style="font-family:system-ui;max-width:680px;margin:24px auto;padding:0 16px;color:#1a2b28">
<div style="color:#0f4c3a;font-weight:600">Resumo de {esc(r.get('data',''))}</div>
<h2>{esc(a.get('titulo',''))}</h2>
<div style="color:#6b7a76;font-size:14px">{esc(a.get('fonte',''))}</div>
<form method="post" action="/revisar/{esc(r.get('review_token',''))}">
  <textarea name="texto" rows="16" style="width:100%;font-size:15px">{esc(r.get('resumo',''))}</textarea>
  <p><a href="/pdf/{esc(r.get('data',''))}" target="_blank">📄 Ver PDF</a></p>
  <button name="acao" value="aprovar">✅ Aprovar</button>
  <button name="acao" value="editar">✏️ Salvar edição</button>
  <button name="acao" value="nao_enviar">🚫 Não enviar hoje</button>
</form></body>"""

def pagina_admin(assinantes):
    linhas = "".join(f"<li>{_html.escape(s['nome'])} — {_html.escape(s['whatsapp'])} "
                     f'<form style="display:inline" method="post" action="/admin">'
                     f'<input type="hidden" name="acao" value="remover"><input type="hidden" name="id" value="{s["id"]}">'
                     f'<button>remover</button></form></li>' for s in assinantes)
    return f"""<!doctype html><meta charset="utf-8"><body style="font-family:system-ui;max-width:640px;margin:24px auto">
<h2>Assinantes ({len(assinantes)})</h2><ul>{linhas}</ul>
<form method="post" action="/admin">
  <input type="hidden" name="acao" value="adicionar">
  <input name="nome" placeholder="Nome"> <input name="whatsapp" placeholder="55DDDNUMERO">
  <button>adicionar</button>
</form></body>"""
```

- [ ] **Step 4: Wire routes into `app/serve.py`** — no `Handler`, antes do fallback do ebook, tratar as rotas (GET e um novo `do_POST`). Trecho a inserir no `do_GET` (após o bloco `/health`):

```python
        if self.path.startswith("/revisar/"):
            import draft_store, review_web
            tok = self.path.split("/revisar/", 1)[1]
            r = draft_store.por_token(tok)
            return self._html(review_web.pagina_revisao(r) if r else "<h3>Link inválido/expirado</h3>", 200 if r else 404)
        if self.path.startswith("/pdf/"):
            import draft_store
            data = self.path.split("/pdf/", 1)[1]
            r = draft_store.carregar(data)
            if r and os.path.exists(r["pdf_path"]):
                body = open(r["pdf_path"], "rb").read()
                self.send_response(200); self.send_header("Content-Type", "application/pdf"); self.end_headers()
                return self.wfile.write(body)
            return self._html("<h3>PDF não encontrado</h3>", 404)
        if self.path.startswith("/admin"):
            import config, subscribers, review_web, urllib.parse as up
            q = up.parse_qs(up.urlparse(self.path).query)
            if not config.ADMIN_TOKEN or q.get("token", [""])[0] != config.ADMIN_TOKEN:
                return self._html("<h3>Acesso negado</h3>", 403)
            return self._html(review_web.pagina_admin(subscribers.listar()), 200)
```

Adicione o helper e o `do_POST` no `Handler`:

```python
    def _html(self, s, code=200):
        self.send_response(code); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
        self.wfile.write(s.encode("utf-8"))

    def do_POST(self):
        import urllib.parse as up
        length = int(self.headers.get("Content-Length", "0"))
        form = up.parse_qs(self.rfile.read(length).decode("utf-8"))
        g = lambda k: form.get(k, [""])[0]
        if self.path.startswith("/revisar/"):
            import draft_store
            tok = self.path.split("/revisar/", 1)[1]; r = draft_store.por_token(tok)
            if not r:
                return self._html("<h3>Link inválido</h3>", 404)
            draft_store.aplicar(r["data"], g("acao"), g("texto"))
            return self._html("<h3>Feito ✅ Pode fechar.</h3>")
        if self.path == "/admin":
            import config, subscribers
            # token via campo oculto ou query; validação simples
            if g("acao") == "adicionar":
                subscribers.adicionar(g("nome"), g("whatsapp"))
            elif g("acao") == "remover":
                subscribers.remover(g("id"))
            return self._html("<meta http-equiv='refresh' content='0;url=/admin?token=" + (config.ADMIN_TOKEN or "") + "'>")
        return self._html("<h3>rota inválida</h3>", 404)
```

- [ ] **Step 5: Run test + manual check**

Run: `python -m unittest tests.test_review_web -v` → PASS
Manual: `cd app && PORT=3000 DSCURSO_ADMIN_TOKEN=xyz python serve.py` e abrir `http://localhost:3000/health` (→ ok) e `/admin?token=xyz`.

- [ ] **Step 6: Commit**

```bash
git add app/review_web.py app/serve.py tests/test_review_web.py
git commit -m "feat(web): páginas de revisão/PDF/admin + roteamento no serve.py"
```

---

### Task 10: Agendador com dois disparos (18h/08h)

**Files:**
- Modify: `app/serve.py`
- Test: `tests/test_scheduler.py`

**Interfaces:**
- Produces: `serve.proximo_disparo(now, horarios) -> (datetime, str)` (puro: dado agora e a lista de `(hora, tarefa)`, retorna o próximo alvo e qual tarefa).

- [ ] **Step 1: Write the failing test (cálculo puro do próximo alvo)**

```python
# tests/test_scheduler.py
import unittest
from datetime import datetime
from app import serve

class TestScheduler(unittest.TestCase):
    def test_proximo_e_18h_quando_agora_e_meiodia(self):
        now = datetime(2026, 7, 18, 12, 0)
        alvo, tarefa = serve.proximo_disparo(now, [(8, "enviar"), (18, "preparar")])
        self.assertEqual((alvo.hour, tarefa), (18, "preparar"))

    def test_vira_o_dia_quando_passou_das_18(self):
        now = datetime(2026, 7, 18, 19, 0)
        alvo, tarefa = serve.proximo_disparo(now, [(8, "enviar"), (18, "preparar")])
        self.assertEqual((alvo.day, alvo.hour, tarefa), (19, 8, "enviar"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_scheduler -v`
Expected: FAIL — `AttributeError: module 'app.serve' has no attribute 'proximo_disparo'`

- [ ] **Step 3: Refactor `serve.py` scheduler**

Substituir a função `agendador()` por um cálculo testável + loop:

```python
from datetime import datetime, timedelta

def proximo_disparo(now, horarios):
    """horarios: lista de (hora_int, nome_tarefa). Retorna (alvo_datetime, nome) mais próximo."""
    candidatos = []
    for h, nome in horarios:
        alvo = now.replace(hour=h, minute=0, second=0, microsecond=0)
        if now >= alvo:
            alvo += timedelta(days=1)
        candidatos.append((alvo, nome))
    return min(candidatos, key=lambda x: x[0])

def agendador():
    import daily
    tarefas = {"preparar": daily.preparar_18h, "enviar": daily.enviar_08h}
    while True:
        now = _now()
        alvo, nome = proximo_disparo(now.replace(tzinfo=None), [(8, "enviar"), (18, "preparar")])
        espera = max(60, (alvo - now.replace(tzinfo=None)).total_seconds())
        print(f"[agendador] próximo: {nome} {alvo:%Y-%m-%d %H:%M} (em {int(espera)}s)", flush=True)
        time.sleep(espera)
        try:
            tarefas[nome]()
        except Exception as e:
            print(f"[agendador] {nome} erro: {e}", flush=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_scheduler -v`
Expected: PASS

- [ ] **Step 5: Rodar a suíte inteira**

Run: `python -m unittest discover -s tests -v`
Expected: todos PASS.

- [ ] **Step 6: Commit**

```bash
git add app/serve.py tests/test_scheduler.py
git commit -m "feat(scheduler): dois disparos diários (18h preparar / 08h enviar), cálculo testável"
```

---

## Self-Review

**Cobertura da spec (Fase 1 — máquina de conteúdo):**
- Motor multi-banco §7 → Task 2 (PubMed/ClinicalTrials/EPMC; medRxiv via EPMC, anotado).
- Seleção/dedupe §7 → Task 3.
- Resumo rigoroso §7 → Task 8 (reusa cascata + `SYS_APROF`).
- PDF bonito §8 → Task 5 (Chromium).
- Máquina de revisão §9 → Tasks 4 + 9 + 10 (18h/link/08h; "silêncio=aprovado" via `pode_enviar`).
- Entrega WhatsApp+PDF, throttle, personalização §14 → Task 7 + 8.
- Lista (semente na Fase 1) §6/§12 → Task 6 (+ admin na Task 9).
- Agendamento §15 → Task 10.
- Config/segredos §16/§17 → Task 1 (`ADMIN_TOKEN`, `PUBLIC_URL`).
- **Fora de escopo (Plano 2):** landing, Asaas, autocadastro, "Minha assinatura"/cancelamento/save flow, webhooks. O link `/minha/<whatsapp>` na Task 8 é placeholder até o Plano 2.

**Placeholders:** nenhum "TODO/TBD"; medRxiv-via-EPMC é decisão explícita, não pendência.

**Consistência de tipos:** artigo normalizado (`titulo/resumo/fonte/doi/url/data/tipo/banco`) é o mesmo em `sources`→`selection`→`draft_store`→`pdf`→`daily`. `pode_enviar`, `aplicar(acao)` e `review_token` batem entre `draft_store` (Task 4), `daily` (Task 8) e `review_web`/`serve` (Tasks 9-10).

---

## Execution Handoff

Plano salvo em `docs/superpowers/plans/2026-07-18-plano1-maquina-de-conteudo.md`.
