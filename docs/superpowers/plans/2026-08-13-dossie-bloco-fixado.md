# Dossiê: bloco editável e fixado — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O Diego corrige o texto de uma afirmação do dossiê e aquele bloco passa a ser dele — a reconstrução não mexe mais nele.

**Architecture:** Cada bloco ganha um id estável, atribuído ao salvar. A preservação dos blocos fixados mora **dentro do `db.salvar_dossie`** (o gravador), não em quem reconstrói: assim nenhum caminho futuro consegue apagar o texto do Diego escrevendo errado. Editar e soltar escrevem por uma porta própria e explícita, que é a única forma de mexer num bloco fixado.

**Tech Stack:** Python 3 stdlib pura (o container não tem pip), SQLite nos testes e Postgres em produção, HTML por f-string em `site_web.py` sem JS, testes em `unittest`.

**Spec:** `docs/superpowers/specs/2026-08-13-dossie-bloco-fixado-design.md`

## Global Constraints

- **Sem dependências novas** e **sem JavaScript**.
- **Todo SQL roda em SQLite e Postgres** (placeholders `?`).
- **A garantia é do gravador:** `db.salvar_dossie` preserva os blocos fixados seja qual for o conteúdo que o chamador mandar. Quem quiser mexer num fixado usa `dossie_editar_bloco`/`dossie_soltar_bloco`.
- **Editar já fixa** — decisão do Diego; não existe "editar sem fixar".
- **Afirmação vazia (ou só espaços) é recusada** com `ValueError`, não gravada.
- **Nada de filtrar bloco por semelhança de texto.** Se a IA repetir uma afirmação fixada, as duas aparecem e o Diego resolve — filtrar apagaria em silêncio uma afirmação nova legítima.
- **A lista de estudos de um bloco não é editável** (tirar estudo é a parte A, que ataca a causa no corpus).
- Comentários e docstrings em português **com acentos**; a regra de "sem acentos" vale só para a primeira linha da mensagem de commit.
- Commits em português, `feat(escopo): ...` / `fix(escopo): ...`.
- Testes: `cd app && python3 -m unittest discover -s tests`. Um arquivo isolado: `cd app && python3 -m unittest tests.test_dossie_fixar -v`.

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `app/db.py` | id nos blocos; preservação dos fixados no `salvar_dossie`; `blocos_do_dossie`, `dossie_editar_bloco`, `dossie_soltar_bloco`. |
| `app/dossie.py` | `construir(..., fixadas=)` e `reconstruir_todos` passando as afirmações fixadas para a fusão. |
| `app/site_web.py` | Form de editar por bloco, marcador 📌 + data nos fixados, botão soltar. |
| `app/serve.py` | Ações POST `editar_bloco` e `soltar_bloco`. |

Teste novo: `app/tests/test_dossie_fixar.py`.

O formato de um bloco fixado:

```python
{"id": "b3f9...", "afirmacao": "...", "estudos": [{"titulo","fonte","data"}],
 "fixado": True, "editado_em": "2026-08-13T18:22:00"}
```

---

### Task 1: Id estável nos blocos e a preservação dentro do gravador

**Files:**
- Modify: `app/db.py` — `salvar_dossie` (~linha 1666) e funções novas ao lado dela
- Test: `app/tests/test_dossie_fixar.py` (novo)

**Interfaces:**
- Consumes: nada.
- Produces:
  - `db.blocos_do_dossie(tema) -> list[dict]` — os blocos gravados hoje (lista vazia se não há dossiê ou o JSON está quebrado);
  - `db.salvar_dossie(tema, conteudo, n_estudos)` — agora dá id a bloco sem id e **preserva os fixados**;
  - `db._gravar_blocos_cru(tema, blocos)` — grava a lista exatamente como veio, sem preservar nada (é a porta explícita usada pelas Tasks 2).

- [ ] **Step 1: Write the failing test**

Crie `app/tests/test_dossie_fixar.py`:

```python
"""Item 33, parte B — o bloco do dossiê que o Diego corrige vira DELE.

A armadilha que define o desenho: o dossiê é reconstruído do zero, então edição manual
crua seria apagada na reconstrução seguinte, sem aviso. Por isso a preservação mora no
GRAVADOR (`salvar_dossie`), não em quem reconstrói — nenhum caminho futuro consegue perder
o texto dele escrevendo errado. Standalone: python3 app/tests/test_dossie_fixar.py"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _snapshot_env():
    return (os.environ.get("DSCURSO_ARTIGOS_DB"), os.environ.get("DATABASE_URL"))


def _reload_db(tmp):
    os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(tmp, "t.db")
    os.environ.pop("DATABASE_URL", None)
    import importlib, db as _db
    importlib.reload(_db)
    _db.init()
    return _db


def _restore_db(snap):
    import importlib
    a, d = snap
    if a is None:
        os.environ.pop("DSCURSO_ARTIGOS_DB", None)
    else:
        os.environ["DSCURSO_ARTIGOS_DB"] = a
    if d is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = d
    import db as _db
    importlib.reload(_db)


def _bloco(afirmacao, titulo="Estudo A"):
    return {"afirmacao": afirmacao,
            "estudos": [{"titulo": titulo, "fonte": "NEJM", "data": "2026-03"}]}


class _Base(unittest.TestCase):
    def setUp(self):
        self.snap = _snapshot_env()
        self.tmp = tempfile.mkdtemp()
        self.db = _reload_db(self.tmp)

    def tearDown(self):
        _restore_db(self.snap)
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestIdsNosBlocos(_Base):
    def test_bloco_sem_id_ganha_um_ao_salvar(self):
        self.db.salvar_dossie("Obesidade", {"blocos": [_bloco("GLP-1 reduz peso")]}, 10)
        b = self.db.blocos_do_dossie("Obesidade")
        self.assertEqual(len(b), 1)
        self.assertTrue(b[0].get("id"))

    def test_ids_sao_distintos_entre_blocos(self):
        self.db.salvar_dossie("Obesidade",
                              {"blocos": [_bloco("Um"), _bloco("Dois")]}, 10)
        ids = [b["id"] for b in self.db.blocos_do_dossie("Obesidade")]
        self.assertEqual(len(set(ids)), 2)

    def test_tema_sem_dossie_devolve_lista_vazia(self):
        self.assertEqual(self.db.blocos_do_dossie("Longevidade"), [])

    def test_conteudo_quebrado_devolve_lista_vazia_em_vez_de_explodir(self):
        self.db.salvar_dossie("Obesidade", {"blocos": [_bloco("X")]}, 1)
        with self.db._conn() as c:
            c.execute("UPDATE dossies SET conteudo=? WHERE tema=?", ("{quebrado", "Obesidade"))
        self.assertEqual(self.db.blocos_do_dossie("Obesidade"), [])


class TestGravadorPreservaOsFixados(_Base):
    """O teste que dá sentido ao desenho inteiro."""

    def setUp(self):
        super().setUp()
        self.db.salvar_dossie("Obesidade", {"blocos": [_bloco("Texto da IA")]}, 10)
        bid = self.db.blocos_do_dossie("Obesidade")[0]["id"]
        blocos = self.db.blocos_do_dossie("Obesidade")
        blocos[0].update({"afirmacao": "Texto do Diego", "fixado": True,
                          "editado_em": "2026-08-13T10:00:00"})
        self.db._gravar_blocos_cru("Obesidade", blocos)
        self.bid = bid

    def test_salvar_conteudo_novo_NAO_apaga_o_bloco_fixado(self):
        """Uma reconstrução manda blocos completamente diferentes — o do Diego fica."""
        self.db.salvar_dossie("Obesidade", {"blocos": [_bloco("Coisa nova da IA")]}, 20)
        afirmacoes = [b["afirmacao"] for b in self.db.blocos_do_dossie("Obesidade")]
        self.assertIn("Texto do Diego", afirmacoes)
        self.assertIn("Coisa nova da IA", afirmacoes)

    def test_o_id_do_fixado_nao_muda(self):
        self.db.salvar_dossie("Obesidade", {"blocos": [_bloco("Outra")]}, 20)
        fixado = [b for b in self.db.blocos_do_dossie("Obesidade") if b.get("fixado")][0]
        self.assertEqual(fixado["id"], self.bid)

    def test_salvar_dossie_VAZIO_tambem_preserva(self):
        """IA fora do ar devolvendo nada não pode levar o texto dele junto."""
        self.db.salvar_dossie("Obesidade", {"blocos": []}, 0)
        self.assertEqual([b["afirmacao"] for b in self.db.blocos_do_dossie("Obesidade")],
                         ["Texto do Diego"])

    def test_fixado_nao_duplica_quando_o_conteudo_devolvido_ja_o_contem(self):
        """Salvar de volta o que foi lido não pode gerar duas cópias do mesmo bloco."""
        atuais = self.db.blocos_do_dossie("Obesidade")
        self.db.salvar_dossie("Obesidade", {"blocos": atuais}, 10)
        ids = [b["id"] for b in self.db.blocos_do_dossie("Obesidade")]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 1)

    def test_o_fixado_vem_primeiro(self):
        self.db.salvar_dossie("Obesidade", {"blocos": [_bloco("Nova")]}, 20)
        self.assertTrue(self.db.blocos_do_dossie("Obesidade")[0].get("fixado"))

    def test_bloco_NAO_fixado_e_substituido_normalmente(self):
        """A preservação vale só pros fixados — o resto é da máquina."""
        self.db.salvar_dossie("Longevidade", {"blocos": [_bloco("Velha")]}, 5)
        self.db.salvar_dossie("Longevidade", {"blocos": [_bloco("Nova")]}, 5)
        self.assertEqual([b["afirmacao"] for b in self.db.blocos_do_dossie("Longevidade")],
                         ["Nova"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_dossie_fixar -v`
Expected: FAIL — `AttributeError: module 'db' has no attribute 'blocos_do_dossie'`.

- [ ] **Step 3: Write minimal implementation**

Em `app/db.py`, substitua `salvar_dossie` e acrescente as funções ao lado:

```python
def blocos_do_dossie(tema):
    """Os blocos gravados hoje. JSON quebrado devolve lista vazia — isto roda no caminho
    da tela e de todo salvamento; explodir aqui derrubaria a aba inteira."""
    r = obter_dossie(tema)
    if not r:
        return []
    try:
        d = json.loads(r.get("conteudo") or "{}") or {}
    except Exception:
        return []
    return [b for b in (d.get("blocos") or []) if isinstance(b, dict)]


def _com_ids(blocos):
    """Identidade estável por bloco. Sem ela não há como apontar 'este bloco' numa tela, e
    o pino do fixado acabaria apontando pro bloco errado depois de a reconstrução mudar a
    ordem da lista."""
    import secrets
    out = []
    for b in (blocos or []):
        if not isinstance(b, dict):
            continue
        nb = dict(b)                       # não muta o dict do chamador
        if not nb.get("id"):
            nb["id"] = secrets.token_hex(8)
        out.append(nb)
    return out


def _gravar_blocos_cru(tema, blocos):
    """Grava a lista EXATAMENTE como veio, sem preservar nada. É a porta explícita — a
    única forma de mexer num bloco fixado (editar/soltar). Todo o resto passa por
    `salvar_dossie`, que preserva.

    UPDATE puro de propósito: editar e soltar só operam em bloco que já existe, então o
    dossiê já existe. `n_estudos` não é tocado — ele conta o corpus lido, não os blocos.
    """
    from datetime import datetime
    with _conn() as c:
        c.execute("UPDATE dossies SET conteudo=?, atualizado_em=? WHERE tema=?",
                  (json.dumps({"blocos": blocos}, ensure_ascii=False),
                   datetime.now().isoformat(), tema))


def salvar_dossie(tema, conteudo, n_estudos):
    """Upsert do dossiê de um tema (1 por tema). `conteudo` é o dict do `dossie.py`.

    **PRESERVA os blocos fixados.** A garantia mora aqui, no gravador, e não em quem
    reconstrói: assim nenhum caminho futuro — botão novo, cron, script de madrugada —
    consegue apagar o texto que o Diego escreveu. Perder isso seria invisível até a
    afirmação sumir semanas depois. Soltar o bloco é a única porta de saída, e é explícita.
    """
    from datetime import datetime
    fixados = [b for b in blocos_do_dossie(tema) if b.get("fixado")]
    ja = {b.get("id") for b in fixados}
    novos = [b for b in _com_ids((conteudo or {}).get("blocos")) if b.get("id") not in ja]
    with _conn() as c:
        c.execute("""INSERT INTO dossies (tema,conteudo,n_estudos,atualizado_em)
                     VALUES (?,?,?,?)
                     ON CONFLICT(tema) DO UPDATE SET conteudo=excluded.conteudo,
                       n_estudos=excluded.n_estudos, atualizado_em=excluded.atualizado_em""",
                  (tema, json.dumps({"blocos": fixados + novos}, ensure_ascii=False),
                   int(n_estudos or 0), datetime.now().isoformat()))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_dossie_fixar -v`
Expected: PASS (11 testes).

- [ ] **Step 5: Rode a suíte inteira** — `salvar_dossie` é usada pela reconstrução

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -5`
Expected: OK, zero falhas.

- [ ] **Step 6: Commit**

```bash
git add app/db.py app/tests/test_dossie_fixar.py
git commit -m "feat(dossie): id por bloco e preservacao dos fixados dentro do gravador"
```

---

### Task 2: Editar (que já fixa) e soltar

**Files:**
- Modify: `app/db.py` — funções novas depois de `salvar_dossie`
- Test: `app/tests/test_dossie_fixar.py` (acrescentar classe)

**Interfaces:**
- Consumes: `db.blocos_do_dossie`, `db._gravar_blocos_cru` (Task 1).
- Produces:
  - `db.dossie_editar_bloco(tema, bloco_id, afirmacao) -> bool` — grava o texto e fixa; `ValueError` se o texto for vazio; `False` se o bloco não existe;
  - `db.dossie_soltar_bloco(tema, bloco_id) -> bool` — tira o `fixado`; `False` se não existe.

- [ ] **Step 1: Write the failing test**

Acrescente a `app/tests/test_dossie_fixar.py`, antes do `if __name__`:

```python
class TestEditarEsoltar(_Base):
    def setUp(self):
        super().setUp()
        self.db.salvar_dossie("Obesidade",
                              {"blocos": [_bloco("Texto da IA"), _bloco("Outro")]}, 10)
        self.bid = self.db.blocos_do_dossie("Obesidade")[0]["id"]

    def _bloco_por_id(self, bid):
        return next(b for b in self.db.blocos_do_dossie("Obesidade") if b["id"] == bid)

    def test_editar_grava_o_texto(self):
        self.db.dossie_editar_bloco("Obesidade", self.bid, "Texto do Diego")
        self.assertEqual(self._bloco_por_id(self.bid)["afirmacao"], "Texto do Diego")

    def test_editar_FIXA_na_mesma_tacada(self):
        """Decisão do Diego: não existe editar sem fixar — senão a reconstrução seguinte
        apaga o que ele escreveu, calada."""
        self.db.dossie_editar_bloco("Obesidade", self.bid, "Texto do Diego")
        self.assertTrue(self._bloco_por_id(self.bid).get("fixado"))

    def test_editar_carimba_a_data(self):
        self.db.dossie_editar_bloco("Obesidade", self.bid, "Texto do Diego")
        self.assertTrue(self._bloco_por_id(self.bid).get("editado_em"))

    def test_editar_nao_mexe_nos_estudos_do_bloco(self):
        antes = self._bloco_por_id(self.bid)["estudos"]
        self.db.dossie_editar_bloco("Obesidade", self.bid, "Texto do Diego")
        self.assertEqual(self._bloco_por_id(self.bid)["estudos"], antes)

    def test_editar_nao_mexe_nos_outros_blocos(self):
        self.db.dossie_editar_bloco("Obesidade", self.bid, "Texto do Diego")
        outros = [b for b in self.db.blocos_do_dossie("Obesidade") if b["id"] != self.bid]
        self.assertEqual([b["afirmacao"] for b in outros], ["Outro"])
        self.assertFalse(outros[0].get("fixado"))

    def test_texto_vazio_levanta_e_nao_grava(self):
        """Afirmação em branco não é edição: é um bloco sem sentido — e como editar fixa,
        salvar vazio congelaria o nada."""
        for ruim in ("", "   ", "\n\t "):
            with self.subTest(ruim=ruim):
                with self.assertRaises(ValueError):
                    self.db.dossie_editar_bloco("Obesidade", self.bid, ruim)
        self.assertEqual(self._bloco_por_id(self.bid)["afirmacao"], "Texto da IA")

    def test_texto_com_espaco_nas_pontas_e_aparado(self):
        self.db.dossie_editar_bloco("Obesidade", self.bid, "  Texto do Diego  ")
        self.assertEqual(self._bloco_por_id(self.bid)["afirmacao"], "Texto do Diego")

    def test_bloco_inexistente_devolve_False_sem_gravar(self):
        self.assertFalse(self.db.dossie_editar_bloco("Obesidade", "nao-existe", "X"))
        self.assertEqual(len(self.db.blocos_do_dossie("Obesidade")), 2)

    def test_soltar_tira_o_fixado(self):
        self.db.dossie_editar_bloco("Obesidade", self.bid, "Texto do Diego")
        self.assertTrue(self.db.dossie_soltar_bloco("Obesidade", self.bid))
        self.assertFalse(self._bloco_por_id(self.bid).get("fixado"))

    def test_soltar_mantem_o_texto_ate_a_proxima_reconstrucao(self):
        self.db.dossie_editar_bloco("Obesidade", self.bid, "Texto do Diego")
        self.db.dossie_soltar_bloco("Obesidade", self.bid)
        self.assertEqual(self._bloco_por_id(self.bid)["afirmacao"], "Texto do Diego")

    def test_depois_de_soltar_a_reconstrucao_substitui(self):
        self.db.dossie_editar_bloco("Obesidade", self.bid, "Texto do Diego")
        self.db.dossie_soltar_bloco("Obesidade", self.bid)
        self.db.salvar_dossie("Obesidade", {"blocos": [_bloco("Só a nova")]}, 10)
        self.assertEqual([b["afirmacao"] for b in self.db.blocos_do_dossie("Obesidade")],
                         ["Só a nova"])

    def test_soltar_bloco_inexistente_devolve_False(self):
        self.assertFalse(self.db.dossie_soltar_bloco("Obesidade", "nao-existe"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_dossie_fixar.TestEditarEsoltar -v`
Expected: FAIL — `AttributeError: module 'db' has no attribute 'dossie_editar_bloco'`.

- [ ] **Step 3: Write minimal implementation**

Em `app/db.py`, depois de `salvar_dossie`:

```python
def dossie_editar_bloco(tema, bloco_id, afirmacao):
    """O texto do Diego entra e o bloco vira dele — editar FIXA na mesma tacada.

    Decisão dele (2026-08-13): não existe editar sem fixar. O estado intermediário — texto
    dele num bloco solto — seria apagado pela reconstrução seguinte sem aviso, que é
    exatamente a armadilha que esta fatia fecha.
    """
    from datetime import datetime
    txt = (afirmacao or "").strip()
    if not txt:
        raise ValueError("afirmação vazia")
    blocos = blocos_do_dossie(tema)
    achou = False
    for b in blocos:
        if b.get("id") == bloco_id:
            b["afirmacao"] = txt
            b["fixado"] = True
            b["editado_em"] = datetime.now().isoformat()
            achou = True
    if not achou:
        return False
    _gravar_blocos_cru(tema, blocos)
    return True


def dossie_soltar_bloco(tema, bloco_id):
    """Devolve o bloco à máquina. O texto atual fica até a próxima reconstrução
    substituí-lo — soltar não é desfazer, é parar de proteger."""
    blocos = blocos_do_dossie(tema)
    achou = False
    for b in blocos:
        if b.get("id") == bloco_id:
            b["fixado"] = False
            achou = True
    if not achou:
        return False
    _gravar_blocos_cru(tema, blocos)
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_dossie_fixar -v`
Expected: PASS (23 testes).

- [ ] **Step 5: Commit**

```bash
git add app/db.py app/tests/test_dossie_fixar.py
git commit -m "feat(dossie): editar a afirmacao fixa o bloco, e soltar devolve pra maquina"
```

---

### Task 3: A reconstrução avisa a IA do que já está fixado

**Files:**
- Modify: `app/dossie.py` — `construir` (~linha 117) e `reconstruir_todos` (~linha 208)
- Test: `app/tests/test_dossie_fixar.py` (acrescentar classe)

**Interfaces:**
- Consumes: `db.blocos_do_dossie` (Task 1).
- Produces: `dossie.construir(estudos, lote=LOTE_PADRAO, gerar_fn=None, fixadas=None)` — `fixadas` é uma lista de strings (as afirmações do Diego).

- [ ] **Step 1: Write the failing test**

Acrescente a `app/tests/test_dossie_fixar.py`, antes do `if __name__`:

```python
class TestReconstrucaoSabeDosFixados(_Base):
    """Sem isso o dossiê passa a dizer a mesma coisa duas vezes: uma com as palavras do
    Diego, outra com as da IA."""

    def setUp(self):
        super().setUp()
        import importlib, dossie
        importlib.reload(dossie)
        self.dossie = dossie

    def _estudos(self, n=3):
        return [{"titulo": f"Estudo {i}", "fonte": "NEJM", "data": "2026-03",
                 "abstract": "abstract " * 30} for i in range(n)]

    def test_a_afirmacao_fixada_vai_no_prompt_da_fusao(self):
        prompts = []

        def gerar_fn(p):
            prompts.append(p)
            return '{"blocos":[{"afirmacao":"a","estudos":[{"titulo":"Estudo 1"}]}]}'

        self.dossie.construir(self._estudos(), lote=2, gerar_fn=gerar_fn,
                              fixadas=["Uma afirmação que o Diego escreveu"])
        self.assertTrue(any("Uma afirmação que o Diego escreveu" in p for p in prompts))

    def test_sem_fixadas_o_prompt_nao_ganha_o_aviso(self):
        prompts = []

        def gerar_fn(p):
            prompts.append(p)
            return '{"blocos":[{"afirmacao":"a","estudos":[{"titulo":"Estudo 1"}]}]}'

        self.dossie.construir(self._estudos(), lote=2, gerar_fn=gerar_fn)
        self.assertFalse(any("FIXADAS" in p for p in prompts))

    def test_reconstruir_passa_as_fixadas_lidas_do_banco(self):
        self.db.salvar_dossie("Obesidade", {"blocos": [_bloco("Texto da IA")]}, 1)
        bid = self.db.blocos_do_dossie("Obesidade")[0]["id"]
        self.db.dossie_editar_bloco("Obesidade", bid, "Texto do Diego")
        self.db.salvar_candidatos([{
            "chave": "k1", "titulo": "Estudo A", "tema": "Obesidade", "tipo": "varredura",
            "fonte": "NEJM", "data": "2026-03-01", "doi": "10.1/k1", "url": "",
            "abstract": "abs " * 40, "pergunta": "", "score": 8, "citacoes": 0, "tags": []}])
        prompts = []

        def gerar_fn(p):
            prompts.append(p)
            return '{"blocos":[{"afirmacao":"nova","estudos":[{"titulo":"Estudo A"}]}]}'

        self.dossie.reconstruir_todos(temas=["Obesidade"], gerar_fn=gerar_fn, db_mod=self.db)
        self.assertTrue(any("Texto do Diego" in p for p in prompts))

    def test_reconstruir_ponta_a_ponta_preserva_o_bloco_do_Diego(self):
        """O caminho real: o botão 🧠 roda inteiro e o texto dele continua lá."""
        self.db.salvar_dossie("Obesidade", {"blocos": [_bloco("Texto da IA")]}, 1)
        bid = self.db.blocos_do_dossie("Obesidade")[0]["id"]
        self.db.dossie_editar_bloco("Obesidade", bid, "Texto do Diego")
        self.db.salvar_candidatos([{
            "chave": "k2", "titulo": "Estudo B", "tema": "Obesidade", "tipo": "varredura",
            "fonte": "NEJM", "data": "2026-03-01", "doi": "10.1/k2", "url": "",
            "abstract": "abs " * 40, "pergunta": "", "score": 8, "citacoes": 0, "tags": []}])
        self.dossie.reconstruir_todos(
            temas=["Obesidade"], db_mod=self.db,
            gerar_fn=lambda p: '{"blocos":[{"afirmacao":"tudo novo",'
                               '"estudos":[{"titulo":"Estudo B"}]}]}')
        afirmacoes = [b["afirmacao"] for b in self.db.blocos_do_dossie("Obesidade")]
        self.assertIn("Texto do Diego", afirmacoes)
        self.assertIn("tudo novo", afirmacoes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_dossie_fixar.TestReconstrucaoSabeDosFixados -v`
Expected: FAIL — `construir() got an unexpected keyword argument 'fixadas'`.

- [ ] **Step 3: Write minimal implementation**

Em `app/dossie.py`, na assinatura e no fim de `construir`:

```python
def construir(estudos, lote=LOTE_PADRAO, gerar_fn=None, fixadas=None):
```

e o trecho da fusão passa a ser:

```python
    aviso = ""
    if fixadas:
        # Sem isto o dossiê passa a dizer a mesma coisa duas vezes — uma com as palavras
        # do Diego, outra com as da IA. Não é garantia (modelo repete às vezes), e por
        # isso a defesa real é a tela: ele vê as duas e resolve. Filtrar por semelhança de
        # texto apagaria em silêncio uma afirmação nova legítima.
        aviso = ("\n\nEstas afirmações já estão FIXADAS pelo médico e vão continuar no "
                 "dossiê exatamente como estão. NÃO as repita nem reescreva com outras "
                 "palavras — cuide do resto:\n- " + "\n- ".join(str(f) for f in fixadas))
    fundido = _chamar(gerar_fn,
                      "Estas são memórias parciais do MESMO tema, feitas em lotes. "
                      "Funda numa só: junte afirmações repetidas somando os estudos de "
                      "cada uma, e mantenha explícitas as divergências.\n\n"
                      + json.dumps({"blocos": parciais}, ensure_ascii=False) + aviso)
    return fundido if fundido["blocos"] else {"blocos": parciais}
```

Em `reconstruir_todos`, dentro do laço dos temas, antes de chamar `construir`:

```python
            fixadas = [b.get("afirmacao", "") for b in db_mod.blocos_do_dossie(t)
                       if b.get("fixado")]
            d = construir(estudos, gerar_fn=gerar_fn, fixadas=fixadas)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_dossie_fixar tests.test_dossie -v`
Expected: PASS (27 no arquivo novo + os de `test_dossie` intactos).

- [ ] **Step 5: Commit**

```bash
git add app/dossie.py app/tests/test_dossie_fixar.py
git commit -m "feat(dossie): a fusao avisa a IA de quais afirmacoes ja estao fixadas"
```

---

### Task 4: A tela — editar, marcador do fixado, soltar

**Files:**
- Modify: `app/site_web.py` — `_dossie_html` (~linha 1453), no trecho que monta `corpo`
- Test: `app/tests/test_dossie_fixar_ui.py` (novo)

**Interfaces:**
- Consumes: `_form_curadoria(token, acao, campos, label, classe, titulo)` e `_esc`, que já existem no arquivo.
- Produces: nada de assinatura nova — `_dossie_html(dossies, painel=None, token="")` continua igual.

- [ ] **Step 1: Write the failing test**

Crie `app/tests/test_dossie_fixar_ui.py`:

```python
"""A tela do bloco editável (item 33, parte B). Standalone:
python3 app/tests/test_dossie_fixar_ui.py"""
import importlib
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _dossie_row(blocos, tema="Obesidade"):
    return {"tema": tema, "atualizado_em": "2026-08-13T10:00:00", "n_estudos": 3,
            "conteudo": json.dumps({"blocos": blocos}, ensure_ascii=False)}


def _bloco(afirmacao="GLP-1 reduz massa magra", bid="b1", fixado=False, editado_em=""):
    b = {"id": bid, "afirmacao": afirmacao,
         "estudos": [{"titulo": "Estudo A", "fonte": "NEJM", "data": "2026-03"}]}
    if fixado:
        b["fixado"] = True
        b["editado_em"] = editado_em or "2026-08-13T18:22:00"
    return b


class TestBlocoEditavel(unittest.TestCase):
    def setUp(self):
        import site_web
        importlib.reload(site_web)
        self.sw = site_web

    def test_bloco_ganha_form_de_editar_com_o_texto_atual(self):
        html = self.sw._dossie_html([_dossie_row([_bloco()])], None, token="tok")
        self.assertIn("editar_bloco", html)
        self.assertIn("GLP-1 reduz massa magra", html)
        self.assertIn("<textarea", html)

    def test_o_id_do_bloco_viaja_no_form(self):
        html = self.sw._dossie_html([_dossie_row([_bloco(bid="abc123")])], None, token="tok")
        self.assertIn("abc123", html)

    def test_bloco_fixado_mostra_o_marcador_e_a_data(self):
        html = self.sw._dossie_html(
            [_dossie_row([_bloco(fixado=True, editado_em="2026-08-13T18:22:00")])],
            None, token="tok")
        self.assertIn("📌", html)
        self.assertIn("2026-08-13", html)

    def test_bloco_fixado_oferece_soltar(self):
        html = self.sw._dossie_html([_dossie_row([_bloco(fixado=True)])], None, token="tok")
        self.assertIn("soltar_bloco", html)

    def test_bloco_solto_NAO_oferece_soltar(self):
        html = self.sw._dossie_html([_dossie_row([_bloco()])], None, token="tok")
        self.assertNotIn("soltar_bloco", html)

    def test_bloco_solto_nao_mostra_o_marcador(self):
        html = self.sw._dossie_html([_dossie_row([_bloco()])], None, token="tok")
        self.assertNotIn("📌", html)

    def test_escapa_a_afirmacao(self):
        html = self.sw._dossie_html(
            [_dossie_row([_bloco(afirmacao="<script>alert(1)</script>")])], None, token="tok")
        self.assertNotIn("<script>alert(1)</script>", html)

    def test_bloco_sem_id_nao_oferece_editar(self):
        """Dossiê antigo, gravado antes desta fatia: sem id não há como apontar o bloco.
        Melhor não oferecer do que oferecer um botão que erra o alvo."""
        b = {"afirmacao": "Sem id", "estudos": [{"titulo": "X", "fonte": "", "data": ""}]}
        html = self.sw._dossie_html([_dossie_row([b])], None, token="tok")
        self.assertIn("Sem id", html)
        self.assertNotIn("editar_bloco", html)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_dossie_fixar_ui -v`
Expected: FAIL — `editar_bloco` não aparece no HTML.

- [ ] **Step 3: Write minimal implementation**

Em `app/site_web.py`, dentro de `_dossie_html`, substitua a montagem de `corpo` (o trecho que hoje é uma comprehension de `blocos`) por uma função e uma junção:

```python
        def _bloco_html(b):
            """Afirmação + lastro + as ações do bloco. O ✏️ abre o texto numa caixa; salvar
            fixa o bloco (editar já fixa — decisão do Diego), e aí ele ganha o 📌 e o
            soltar."""
            bid = b.get("id") or ""
            fixado = bool(b.get("fixado"))
            selo = ""
            if fixado:
                selo = (f'<span class="hint">📌 sua versão, de '
                        f'{_esc((b.get("editado_em") or "")[:10])} — a reconstrução não '
                        f'mexe neste bloco</span> '
                        + _form_curadoria(token, "soltar_bloco",
                                          {"tema": tema, "bloco": bid}, "soltar"))
            editar = ""
            if bid:                     # dossiê antigo, sem id: não dá pra apontar o bloco
                editar = (
                    f'<details style="margin-top:8px">'
                    f'<summary style="cursor:pointer;color:var(--ouro2);'
                    f'font-family:system-ui,sans-serif;font-size:13px">✏️ Editar</summary>'
                    f'<form method="post" action="/curadoria" style="margin-top:10px">'
                    f'<input type="hidden" name="token" value="{_esc(token)}">'
                    f'<input type="hidden" name="acao" value="editar_bloco">'
                    f'<input type="hidden" name="aba" value="dossie">'
                    f'<input type="hidden" name="tema" value="{_esc(tema)}">'
                    f'<input type="hidden" name="bloco" value="{_esc(bid)}">'
                    f'<textarea name="afirmacao" rows="3">{_esc(b.get("afirmacao"))}</textarea>'
                    f'<p class="hint">Salvar deixa este bloco no seu texto — a reconstrução '
                    f'passa a não mexer nele.</p>'
                    f'<button class="actbtn" type="submit">Salvar afirmação</button>'
                    f'</form></details>')
            return (f'<div class="item"><div class="t">{_esc(b.get("afirmacao"))}</div>'
                    f'<div class="d">'
                    + " · ".join(_estudo_linha(e) for e in (b.get("estudos") or []))
                    + f'</div><div class="d">{selo}</div>{editar}</div>')

        corpo = "".join(_bloco_html(b) for b in blocos) or \
            '<p class="hint">Dossiê vazio — a IA não devolveu nada útil.</p>'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_dossie_fixar_ui tests.test_excluir_corpus_ui -v`
Expected: PASS (8 novos + os da parte A intactos).

- [ ] **Step 5: Rode a suíte inteira** — `site_web` é compartilhado

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -5`
Expected: OK.

- [ ] **Step 6: Commit**

```bash
git add app/site_web.py app/tests/test_dossie_fixar_ui.py
git commit -m "feat(dossie): bloco ganha editar, selo de fixado e soltar na aba do dossie"
```

---

### Task 5: As rotas

**Files:**
- Modify: `app/serve.py` — cadeia de `elif acao ==` do POST `/curadoria` (perto de `refazer_dossie_tema`)
- Test: `app/tests/test_dossie_fixar_ui.py` (acrescentar classe)

**Interfaces:**
- Consumes: `db.dossie_editar_bloco`, `db.dossie_soltar_bloco` (Task 2).
- Produces: ações POST `editar_bloco` (tema, bloco, afirmacao) e `soltar_bloco` (tema, bloco).

- [ ] **Step 1: Write the failing test**

Acrescente a `app/tests/test_dossie_fixar_ui.py`, antes do `if __name__`:

```python
import io
import shutil
import tempfile
import urllib.parse as _urlp


class _RouteStub:
    """Mesmo stub dos outros testes de rota — path/headers/rfile + `_html`/`_redirect`,
    sem abrir socket."""

    def __init__(self, path, body=b""):
        self.path = path
        self.rfile = io.BytesIO(body)
        self.headers = {"Content-Length": str(len(body)),
                        "Content-Type": "application/x-www-form-urlencoded"}
        self.client_address = ("127.0.0.1", 0)

    def _html(self, s, code=200):
        return {"code": code, "body": s}

    def _redirect(self, location, token=None, clear=False):
        return {"redirect": location}

    def _sessao(self):
        return None


class TestRotasBloco(unittest.TestCase):
    def setUp(self):
        self.snap = (os.environ.get("DSCURSO_ARTIGOS_DB"), os.environ.get("DATABASE_URL"),
                     os.environ.get("DSCURSO_ADMIN_TOKEN"))
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ.pop("DATABASE_URL", None)
        os.environ["DSCURSO_ADMIN_TOKEN"] = "tok123"
        import db, config, serve
        importlib.reload(db)
        importlib.reload(config)
        importlib.reload(serve)
        self.db, self.serve = db, serve
        self.db.init()
        self.db.salvar_dossie("Obesidade", {"blocos": [
            {"afirmacao": "Texto da IA",
             "estudos": [{"titulo": "Estudo A", "fonte": "NEJM", "data": "2026-03"}]}]}, 5)
        self.bid = self.db.blocos_do_dossie("Obesidade")[0]["id"]

    def tearDown(self):
        a, d, t = self.snap
        for k, v in (("DSCURSO_ARTIGOS_DB", a), ("DATABASE_URL", d),
                     ("DSCURSO_ADMIN_TOKEN", t)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        import db, config
        importlib.reload(db)
        importlib.reload(config)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _post(self, campos):
        body = _urlp.urlencode(campos).encode("utf-8")
        return self.serve.Handler.do_POST(_RouteStub("/curadoria", body))

    def _bloco(self):
        return self.db.blocos_do_dossie("Obesidade")[0]

    def test_sem_token_403_e_nada_muda(self):
        r = self._post({"acao": "editar_bloco", "tema": "Obesidade", "bloco": self.bid,
                        "afirmacao": "invadido"})
        self.assertEqual(r["code"], 403)
        self.assertEqual(self._bloco()["afirmacao"], "Texto da IA")

    def test_editar_persiste_e_fixa(self):
        r = self._post({"token": "tok123", "acao": "editar_bloco", "tema": "Obesidade",
                        "bloco": self.bid, "afirmacao": "Texto do Diego"})
        self.assertIn("redirect", r)
        self.assertEqual(self._bloco()["afirmacao"], "Texto do Diego")
        self.assertTrue(self._bloco().get("fixado"))

    def test_texto_vazio_avisa_e_nao_grava(self):
        """Falha aberta: sem a mensagem ele clica, nada acontece e não sabe por quê."""
        r = self._post({"token": "tok123", "acao": "editar_bloco", "tema": "Obesidade",
                        "bloco": self.bid, "afirmacao": "   "})
        self.assertIn("redirect", r)
        self.assertIn("vazia", r["redirect"].replace("%20", " ").replace("+", " ").lower())
        self.assertEqual(self._bloco()["afirmacao"], "Texto da IA")

    def test_bloco_inexistente_avisa(self):
        r = self._post({"token": "tok123", "acao": "editar_bloco", "tema": "Obesidade",
                        "bloco": "nao-existe", "afirmacao": "X"})
        self.assertIn("redirect", r)
        self.assertEqual(self._bloco()["afirmacao"], "Texto da IA")

    def test_soltar_pela_rota(self):
        self.db.dossie_editar_bloco("Obesidade", self.bid, "Texto do Diego")
        r = self._post({"token": "tok123", "acao": "soltar_bloco", "tema": "Obesidade",
                        "bloco": self.bid})
        self.assertIn("redirect", r)
        self.assertFalse(self._bloco().get("fixado"))

    def test_volta_para_a_aba_do_dossie(self):
        r = self._post({"token": "tok123", "acao": "editar_bloco", "tema": "Obesidade",
                        "bloco": self.bid, "afirmacao": "Texto do Diego"})
        self.assertIn("aba=dossie", r["redirect"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_dossie_fixar_ui.TestRotasBloco -v`
Expected: FAIL — as ações caem fora da cadeia e nada muda.

- [ ] **Step 3: Write minimal implementation**

Em `app/serve.py`, no POST de `/curadoria`, logo depois do ramo `refazer_dossie_tema`:

```python
            elif acao in ("editar_bloco", "soltar_bloco"):
                aba = "dossie"
                tema_b, bloco = g("tema"), g("bloco")
                try:
                    if acao == "soltar_bloco":
                        ok = db.dossie_soltar_bloco(tema_b, bloco)
                        msg = ("Bloco solto — a próxima reconstrução pode reescrevê-lo."
                               if ok else "Não achei esse bloco no dossiê.")
                    else:
                        ok = db.dossie_editar_bloco(tema_b, bloco, g("afirmacao"))
                        msg = ("Afirmação salva e bloco fixado — a reconstrução não mexe "
                               "mais nele." if ok else "Não achei esse bloco no dossiê.")
                except ValueError:
                    # Texto vazio. Falha aberta: sem a mensagem ele clica, nada acontece
                    # e não sabe por quê.
                    msg = "A afirmação não pode ficar vazia — o bloco não foi alterado."
```

Repare que `tema` (a variável da rota, usada no redirect) continua sendo a da querystring; o tema do bloco viaja em `tema_b` para não atropelá-la.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_dossie_fixar_ui -v`
Expected: PASS (14 testes).

- [ ] **Step 5: Rode a suíte inteira**

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -5`
Expected: OK.

- [ ] **Step 6: Commit**

```bash
git add app/serve.py app/tests/test_dossie_fixar_ui.py
git commit -m "feat(dossie): rotas de editar a afirmacao e soltar o bloco"
```

---

### Task 6: Bateria de mutação

Suíte verde prova que os testes que existem passam. A pergunta é outra: desligando cada
guarda, alguém grita? A suíte tem que ficar **vermelha** em todas as linhas abaixo.

**Files:** nenhum arquivo de produção muda ao fim.

- [ ] **Step 1: Prepare**

```bash
cd app && find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null; true
```

Restaure entre mutações com `git checkout -- app/<arquivo>` (**nunca** `git stash` — a
pilha é compartilhada com outras sessões). Confirme com `git diff --stat` antes de rodar
(a mutação atingiu o alvo?) e depois de restaurar (voltou?).

- [ ] **Step 2: Rode as mutações, uma por vez**

| # | Arquivo | Troca | Teste que tem que cair |
|---|---|---|---|
| 1 | `db.py` `salvar_dossie` | não preservar: `fixados = []` | `test_salvar_conteudo_novo_NAO_apaga_o_bloco_fixado` |
| 2 | `db.py` `salvar_dossie` | tirar o dedupe (`novos` sem o filtro por `ja`) | `test_fixado_nao_duplica_quando_o_conteudo_devolvido_ja_o_contem` |
| 3 | `db.py` `salvar_dossie` | preservar TODO bloco, não só os fixados | `test_bloco_NAO_fixado_e_substituido_normalmente` |
| 4 | `db.py` `_com_ids` | não atribuir id (`nb` devolvido como veio) | `test_bloco_sem_id_ganha_um_ao_salvar` |
| 5 | `db.py` `dossie_editar_bloco` | não setar `fixado` | `test_editar_FIXA_na_mesma_tacada` |
| 6 | `db.py` `dossie_editar_bloco` | aceitar vazio (tirar o `raise`) | `test_texto_vazio_levanta_e_nao_grava` |
| 7 | `db.py` `dossie_editar_bloco` | gravar sem `.strip()` | `test_texto_com_espaco_nas_pontas_e_aparado` |
| 8 | `db.py` `dossie_soltar_bloco` | apagar o bloco em vez de soltar | `test_soltar_mantem_o_texto_ate_a_proxima_reconstrucao` |
| 9 | `dossie.py` `construir` | ignorar `fixadas` (nunca montar o aviso) | `test_a_afirmacao_fixada_vai_no_prompt_da_fusao` |
| 10 | `dossie.py` `reconstruir_todos` | passar `fixadas=None` | `test_reconstruir_passa_as_fixadas_lidas_do_banco` |
| 11 | `site_web.py` `_bloco_html` | mostrar o selo 📌 sempre | `test_bloco_solto_nao_mostra_o_marcador` |
| 12 | `site_web.py` `_bloco_html` | oferecer editar mesmo sem id | `test_bloco_sem_id_nao_oferece_editar` |
| 13 | `serve.py` ramo novo | engolir o `ValueError` sem mensagem | `test_texto_vazio_avisa_e_nao_grava` |

- [ ] **Step 3: Conserte o que sobreviver**

Sobrevivente é **hipótese, não veredito**: confira primeiro a âncora (a edição atingiu a
linha certa?) e o `__pycache__`. Confirmada, escreva o teste que faltava.

- [ ] **Step 4: Confirme árvore limpa e suíte verde**

```bash
git status --short
cd app && python3 -m unittest discover -s tests 2>&1 | tail -3
```

- [ ] **Step 5: Commit (só se algum teste novo nasceu)**

```bash
git add app/tests/
git commit -m "test(dossie): fecha os buracos que a bateria de mutacao revelou"
```

---

## Depois do plano

1. Revisão de código do branch inteiro antes do merge.
2. Merge na main, push e deploy pelo EasyPanel — conferir `git ls-remote origin refs/heads/main` == HEAD antes, e **nunca imprimir o corpo do erro** do deploy (vaza todas as credenciais em texto puro).
3. **Ação do Diego depois do deploy:** abrir a aba 🧠, corrigir uma afirmação, apertar **🧠 Refazer só este tema** e confirmar que o texto dele continua lá — é o ciclo inteiro desta fatia numa tacada.
