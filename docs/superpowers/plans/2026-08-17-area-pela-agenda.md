# Item 36 fatia 2 — corrigir a ÁREA pela /agenda — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ver o estudo já enviado num painel dentro do card do dia na `/agenda` e corrigir a área dele ali mesmo, gravando no `digests`.

**Architecture:** `area_estudo.py` continua o dono único da escrita de área e ganha o irmão retroativo `aplicar_no_digest`, que delega pra uma função nova `db.mover_digest_tema`. Como `tema_slug` faz parte da chave primária de `digests`, corrigir a área **move a linha** — a página do portal muda de endereço e a aba antiga some sozinha. A janela da `/agenda` recua uma semana pra que exista dia passado na tela (numa segunda-feira hoje não existe nenhum).

**Tech Stack:** Python 3 stdlib puro (sem pip no container), `unittest`, SQLite em teste / Postgres em produção, HTML montado por f-string em `site_web.py`.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-08-17-area-pela-agenda-design.md`. Ler antes de começar.
- **Suíte:** `cd app && python3 -m unittest discover -s tests` — tem que ficar verde ao fim de cada task.
- **Sem dependência nova.** O container é stdlib puro.
- **`tema` e `tema_slug` andam sempre juntos.** O portal filtra por `tema_slug`, `db.listar_excluidos` filtra por `tema`. Atualizar só um faz as duas visões discordarem em silêncio.
- **Só dia passado.** Dia futuro continua como está; corrigir área de dia futuro é a fatia 3.
- **Nunca sobrescrever estudo alheio.** Colisão de chave `(data, tema_slug)` recusa e avisa.
- **Âncora de teste em HTML é a frase inteira**, nunca trecho curto — sete asserções falsas por âncora curta na tela de custos (`-webkit-` casando com `"kit"`).
- **Arquivo de teste novo:** `app/tests/test_area_pela_agenda.py` (todas as tasks escrevem nele, salvo indicação).

---

### Task 1: `db.mover_digest_tema` — mover a linha do estudo enviado

**Files:**
- Modify: `app/db.py` (adicionar logo depois de `excluir_digest`, ~linha 2085)
- Test: `app/tests/test_area_pela_agenda.py` (criar)

**Interfaces:**
- Consumes: `db.slug(tema)`, `db._conn()`, `db.registrar_digest(art, conteudo, data=...)` (já existem)
- Produces: `db.mover_digest_tema(data, tema_slug, tema_novo) -> str` devolvendo um de `"movido"`, `"inexistente"`, `"ocupado"`, `"mesmo"`

- [ ] **Step 1: Write the failing test**

```python
"""Item 36 fatia 2 — ver o estudo e corrigir a ÁREA pela /agenda."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestMoverDigestTema(unittest.TestCase):
    """Corrigir a área de um estudo enviado MOVE a linha: `tema_slug` é metade da chave
    primária de `digests`. Banco de verdade, não grep de fonte."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ.pop("DATABASE_URL", None)
        import importlib, db as _db
        importlib.reload(_db)
        self.db = _db
        self.db.init()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _digest(self, data="2026-08-10", tema="Meus estudos", titulo="Tirzepatida"):
        self.db.registrar_digest(
            {"tema": tema, "titulo": titulo, "titulo_original": titulo + " (en)",
             "doi": "10.1/x", "fonte": "JAMA", "url": "https://ex/x"},
            {"titulo_pt": titulo, "resumo": "resumo longo", "gancho": "g", "grafico": ""},
            data=data)

    def test_move_tema_e_slug_juntos(self):
        self._digest()
        self.assertEqual(
            self.db.mover_digest_tema("2026-08-10", "meus-estudos", "Obesidade"), "movido")
        novo = self.db.obter("obesidade", "2026-08-10")
        self.assertIsNotNone(novo)
        self.assertEqual(novo["tema"], "Obesidade")
        self.assertEqual(novo["tema_slug"], "obesidade")

    def test_o_slug_antigo_fica_vazio(self):
        self._digest()
        self.db.mover_digest_tema("2026-08-10", "meus-estudos", "Obesidade")
        self.assertEqual(self.db.listar_por_tema("meus-estudos"), [])

    def test_a_aba_fantasma_some_do_portal(self):
        """As abas do portal saem de um GROUP BY sobre o digests — esvaziado o slug, a
        aba 'MEUS ESTUDOS' sai da lista sem limpeza manual."""
        self._digest()
        self.db.mover_digest_tema("2026-08-10", "meus-estudos", "Obesidade")
        slugs = [t["slug"] for t in self.db.listar_temas()]
        self.assertNotIn("meus-estudos", slugs)
        self.assertIn("obesidade", slugs)

    def test_preserva_o_conteudo_do_estudo(self):
        """Mover não pode perder resumo/doi/fonte: é UPDATE, não reinserção."""
        self._digest()
        self.db.mover_digest_tema("2026-08-10", "meus-estudos", "Obesidade")
        novo = self.db.obter("obesidade", "2026-08-10")
        self.assertEqual(novo["resumo"], "resumo longo")
        self.assertEqual(novo["doi"], "10.1/x")
        self.assertEqual(novo["fonte"], "JAMA")

    def test_destino_ocupado_recusa_e_nao_escreve(self):
        """Nunca sobrescrever o estudo que já está lá."""
        self._digest(tema="Meus estudos", titulo="A")
        self._digest(tema="Obesidade", titulo="B")
        self.assertEqual(
            self.db.mover_digest_tema("2026-08-10", "meus-estudos", "Obesidade"), "ocupado")
        self.assertEqual(self.db.obter("obesidade", "2026-08-10")["titulo_pt"], "B")
        self.assertEqual(self.db.obter("meus-estudos", "2026-08-10")["titulo_pt"], "A")

    def test_estudo_inexistente(self):
        self.assertEqual(
            self.db.mover_digest_tema("2026-08-10", "meus-estudos", "Obesidade"), "inexistente")

    def test_mesma_area_e_no_op(self):
        self._digest(tema="Obesidade")
        self.assertEqual(
            self.db.mover_digest_tema("2026-08-10", "obesidade", "Obesidade"), "mesmo")
        self.assertEqual(self.db.obter("obesidade", "2026-08-10")["tema"], "Obesidade")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_area_pela_agenda -v`
Expected: FAIL — `AttributeError: module 'db' has no attribute 'mover_digest_tema'`

- [ ] **Step 3: Write minimal implementation**

Em `app/db.py`, logo depois de `excluir_digest`:

```python
def mover_digest_tema(data, tema_slug, tema_novo):
    """Muda a ÁREA de um estudo JÁ ENVIADO. Devolve "movido" | "inexistente" | "ocupado"
    | "mesmo".

    `tema` e `tema_slug` andam JUNTOS: o portal filtra por slug (`listar_por_tema`) e
    `listar_excluidos` filtra por `tema`. Atualizar só um faz as duas visões discordarem
    em silêncio — o estudo apareceria na aba nova e continuaria contando como do tema
    velho na memória do dossiê.

    Como `tema_slug` é metade da chave primária, isto MOVE a linha: a página passa a
    viver em /artigos/<slug-novo>/<data>. É seguro porque nenhum link profundo desses é
    enviado por WhatsApp (só a raiz do ARTIGOS_URL e rotas de conta).

    Destino ocupado RECUSA em vez de sobrescrever: dois estudos no mesmo dia é raro, mas
    perder um estudo pra sempre por causa de um clique não é aceitável.
    """
    novo_slug = slug(tema_novo)
    with _conn() as c:
        atual = c.execute("SELECT tema FROM digests WHERE data=? AND tema_slug=?",
                          (data, tema_slug)).fetchone()
        if not atual:
            return "inexistente"
        if novo_slug == tema_slug:
            return "mesmo"
        if c.execute("SELECT 1 FROM digests WHERE data=? AND tema_slug=?",
                     (data, novo_slug)).fetchone():
            return "ocupado"
        c.execute("UPDATE digests SET tema=?, tema_slug=? WHERE data=? AND tema_slug=?",
                  (tema_novo, novo_slug, data, tema_slug))
    return "movido"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_area_pela_agenda -v`
Expected: PASS (7 testes)

- [ ] **Step 5: Commit**

```bash
git add app/db.py app/tests/test_area_pela_agenda.py
git commit -m "feat(agenda): db.mover_digest_tema move o estudo enviado de area"
```

---

### Task 2: `area_estudo.aplicar_no_digest` — o irmão retroativo

**Files:**
- Modify: `app/area_estudo.py` (adicionar depois de `_gravar_na_reserva`, fim do arquivo)
- Test: `app/tests/test_area_pela_agenda.py`

**Interfaces:**
- Consumes: `area_estudo.areas()`, `db.mover_digest_tema(data, tema_slug, tema_novo)` (Task 1)
- Produces: `area_estudo.aplicar_no_digest(data, tema_slug, area) -> str` devolvendo `"movido"`, `"inexistente"`, `"ocupado"`, `"mesmo"` ou `"invalida"`

- [ ] **Step 1: Write the failing test**

Acrescentar em `app/tests/test_area_pela_agenda.py`:

```python
class TestAplicarNoDigest(unittest.TestCase):
    """A camada de domínio: valida a área e delega. Sem banco — o db é dublê."""

    def test_area_valida_delega_pro_db(self):
        import area_estudo
        with mock.patch("area_estudo.areas", return_value=["Obesidade", "Longevidade"]), \
             mock.patch("db.mover_digest_tema", return_value="movido") as m:
            got = area_estudo.aplicar_no_digest("2026-08-10", "meus-estudos", "Obesidade")
        self.assertEqual(got, "movido")
        self.assertEqual(m.call_args.args, ("2026-08-10", "meus-estudos", "Obesidade"))

    def test_area_fora_do_config_nao_chega_no_banco(self):
        """Falha fechada, igual ao `valida`: é assim que 'MEUS ESTUDOS' foi parar num PDF."""
        import area_estudo
        with mock.patch("area_estudo.areas", return_value=["Obesidade"]), \
             mock.patch("db.mover_digest_tema") as m:
            got = area_estudo.aplicar_no_digest("2026-08-10", "meus-estudos", "obesidade")
        self.assertEqual(got, "invalida")
        m.assert_not_called()

    def test_area_vazia_nao_chega_no_banco(self):
        import area_estudo
        with mock.patch("area_estudo.areas", return_value=["Obesidade"]), \
             mock.patch("db.mover_digest_tema") as m:
            self.assertEqual(
                area_estudo.aplicar_no_digest("2026-08-10", "meus-estudos", ""), "invalida")
        m.assert_not_called()

    def test_repassa_o_codigo_do_banco_sem_traduzir(self):
        import area_estudo
        for codigo in ("ocupado", "inexistente", "mesmo"):
            with mock.patch("area_estudo.areas", return_value=["Obesidade"]), \
                 mock.patch("db.mover_digest_tema", return_value=codigo):
                self.assertEqual(
                    area_estudo.aplicar_no_digest("2026-08-10", "x", "Obesidade"), codigo)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_area_pela_agenda.TestAplicarNoDigest -v`
Expected: FAIL — `AttributeError: module 'area_estudo' has no attribute 'aplicar_no_digest'`

- [ ] **Step 3: Write minimal implementation**

No fim de `app/area_estudo.py`:

```python
def aplicar_no_digest(data, tema_slug, area):
    """Corrige a área de um estudo JÁ ENVIADO — o irmão retroativo do
    `aplicar_no_rascunho`. Devolve o vocabulário de `db.mover_digest_tema`, mais
    "invalida" quando a área pedida não é chave do `temas_config`.

    Não usa `valida()` porque aqui não existe "área atual" pra cair de volta: o slug é o
    que se tem. A regra é a mesma — só chave de verdade passa, falha fechada.

    O que esta correção NÃO alcança: o PDF, que já foi entregue no WhatsApp. Alcança a
    página do portal, as abas do portal e, na próxima reconstrução (🧠), a memória do
    dossiê.
    """
    pedida = (area or "").strip()
    if pedida not in areas():
        return "invalida"
    import db
    return db.mover_digest_tema(data, tema_slug, pedida)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_area_pela_agenda -v`
Expected: PASS (11 testes)

- [ ] **Step 5: Commit**

```bash
git add app/area_estudo.py app/tests/test_area_pela_agenda.py
git commit -m "feat(agenda): area_estudo.aplicar_no_digest corrige estudo ja enviado"
```

---

### Task 3: `semanas_do_mes(semanas_atras=...)` — a semana passada na tela

**Files:**
- Modify: `app/agenda_plan.py:41-55`
- Test: `app/tests/test_agenda_plan.py` (arquivo existente — seguir o estilo dele)

**Interfaces:**
- Produces: `agenda_plan.semanas_do_mes(hoje, dias_envio, n_semanas=4, semanas_atras=0)`

- [ ] **Step 1: Write the failing test**

Acrescentar em `app/tests/test_agenda_plan.py`, dentro da classe que já testa `semanas_do_mes`:

```python
    def test_semanas_atras_traz_a_semana_anterior(self):
        """Numa SEGUNDA a janela padrão não tem dia passado nenhum — e era por isso que
        o estudo de 2026-08-10 ficava fora do alcance da tela."""
        envio = {"segunda", "terca", "quarta", "quinta", "sexta"}
        seg = datetime(2026, 8, 17)                     # segunda-feira
        padrao = ap.semanas_do_mes(seg, envio, 4)
        self.assertEqual(padrao[0], "2026-08-17")       # sem passado
        com_recuo = ap.semanas_do_mes(seg, envio, 4, semanas_atras=1)
        self.assertEqual(com_recuo[0], "2026-08-10")
        self.assertIn("2026-08-14", com_recuo)          # sexta da semana passada

    def test_semanas_atras_nao_encurta_o_futuro(self):
        """Recuar o começo não pode comer as 4 semanas pra frente."""
        envio = {"segunda", "terca", "quarta", "quinta", "sexta"}
        seg = datetime(2026, 8, 17)
        padrao = ap.semanas_do_mes(seg, envio, 4)
        com_recuo = ap.semanas_do_mes(seg, envio, 4, semanas_atras=1)
        self.assertEqual(padrao[-1], com_recuo[-1])
        self.assertEqual(len(com_recuo), len(padrao) + 5)

    def test_default_zero_preserva_os_chamadores_atuais(self):
        """`daily.materializar_agenda` usa esta função pra decidir que dias PREENCHER —
        recuar por default criaria slot no passado."""
        envio = {"segunda", "terca", "quarta", "quinta", "sexta"}
        seg = datetime(2026, 8, 17)
        self.assertEqual(ap.semanas_do_mes(seg, envio, 4),
                         ap.semanas_do_mes(seg, envio, 4, semanas_atras=0))
        self.assertEqual(ap.semanas_do_mes(seg, envio, 4)[0], "2026-08-17")

    def test_ordem_cronologica_preservada_com_recuo(self):
        envio = {"segunda", "terca", "quarta", "quinta", "sexta"}
        dias = ap.semanas_do_mes(datetime(2026, 8, 19), envio, 4, semanas_atras=1)
        self.assertEqual(dias, sorted(dias))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_agenda_plan -v`
Expected: FAIL — `TypeError: semanas_do_mes() got an unexpected keyword argument 'semanas_atras'`

- [ ] **Step 3: Write minimal implementation**

Em `app/agenda_plan.py`, substituir a assinatura e as duas linhas de cálculo:

```python
def semanas_do_mes(hoje, dias_envio, n_semanas=4, semanas_atras=0):
    """Dias úteis de `n_semanas` semanas CHEIAS (seg–sex), começando na segunda-feira
    da semana de `hoje`. Ex.: 4 semanas seg–sex = 20 dias. Inclui os dias já passados
    da semana atual (o chamador os marca como histórico). Retorna YYYY-MM-DD em ordem.

    `semanas_atras` recua o COMEÇO em semanas cheias sem encurtar o futuro. A `/agenda`
    usa 1 pra manter a semana passada à vista: numa segunda-feira, sem isso, não há dia
    passado nenhum na tela — e era por aí que o estudo de 2026-08-10 escapava.

    Default 0 de propósito: `daily.materializar_agenda` chama esta função pra decidir que
    dias PREENCHER, e recuar ali criaria slot no passado.
    """
    validos = set(dias_envio) & set(DIAS)
    if not validos:
        raise ValueError("dias_envio não contém nenhum dia útil válido")
    segunda = hoje - timedelta(days=hoje.weekday())   # segunda-feira da semana de hoje
    inicio = segunda - timedelta(days=7 * semanas_atras)
    fim = segunda + timedelta(days=n_semanas * 7)
    out, d = [], inicio
    while d < fim:
        if DIAS[d.weekday()] in validos:
            out.append(d.strftime("%Y-%m-%d"))
        d = d + timedelta(days=1)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_agenda_plan -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/agenda_plan.py app/tests/test_agenda_plan.py
git commit -m "feat(agenda): semanas_do_mes aceita recuar semanas sem encurtar o futuro"
```

---

### Task 4: o GET da `/agenda` — janela recuada e os campos do estudo

**Files:**
- Modify: `app/serve.py:503` (a janela) e `app/serve.py:507-517` (`_slot_view`)
- Test: `app/tests/test_area_pela_agenda.py`

**Interfaces:**
- Consumes: `agenda_plan.semanas_do_mes(..., semanas_atras=1)` (Task 3), `db.digest_do_dia(data)`
- Produces: o dict de slot passado ganha as chaves `tema_slug`, `resumo`, `fonte`, `doi`, `titulo_original` — consumidas pelo `site_web._slot_card` na Task 5

⚠️ **A tabela `digests` NÃO tem data de publicação.** As colunas são `data` (dia do envio), `titulo_original`, `tema`, `tema_slug`, `titulo_pt`, `resumo`, `gancho`, `grafico`, `doi`, `fonte`, `url`, `criado_em`, `excluido`. O painel mostra revista (`fonte`), DOI e título original — não invente uma data de revista.

- [ ] **Step 1: Write the failing test**

```python
class TestSlotViewCarregaOEstudo(unittest.TestCase):
    """O `digest_do_dia` já faz SELECT * — o `_slot_view` é que jogava fora tudo menos
    tema/título. Sem estes campos o painel não tem o que mostrar."""

    def _slot_view(self, dia, digest):
        """Roda o GET da /agenda com o banco dublado e devolve o slot daquele dia.

        A janela é dublada com uma data FIXA no passado. Usar "ontem" faria o teste pular
        sozinho toda segunda-feira (ontem = domingo, não é dia de envio) — teste que não
        roda é teste que não existe.
        """
        import serve, config
        capturado = {}

        def _fake_pagina(semanas, estoque, token, msg=""):
            capturado["slots"] = [s for sem in semanas for s in sem]
            return "<html></html>"

        with mock.patch("db.init"), \
             mock.patch("db.digest_do_dia", return_value=digest), \
             mock.patch("db.agenda_listar", return_value={}), \
             mock.patch("db.contar_reserva_pronto", return_value=0), \
             mock.patch("daily.materializar_agenda"), \
             mock.patch("daily._dias_envio",
                        return_value={"segunda", "terca", "quarta", "quinta", "sexta"}), \
             mock.patch("agenda_plan.semanas_do_mes", return_value=[dia]), \
             mock.patch("site_web.pagina_agenda", side_effect=_fake_pagina), \
             mock.patch.object(config, "ADMIN_TOKEN", "tok"):
            serve.Handler.do_GET(_RotaStub("/agenda?token=tok"))
        return [s for s in capturado["slots"] if s["data"] == dia]

    def test_dia_passado_carrega_resumo_fonte_doi_e_slug(self):
        digest = {"tema": "Meus estudos", "tema_slug": "meus-estudos",
                  "titulo_pt": "Tirzepatida", "titulo_original": "Tirzepatide",
                  "resumo": "resumo longo", "fonte": "JAMA", "doi": "10.1/x"}
        achados = self._slot_view("2026-08-10", digest)   # data fixa, sempre no passado
        self.assertEqual(len(achados), 1)
        s = achados[0]
        self.assertEqual(s["tema_slug"], "meus-estudos")
        self.assertEqual(s["resumo"], "resumo longo")
        self.assertEqual(s["fonte"], "JAMA")
        self.assertEqual(s["doi"], "10.1/x")
        self.assertEqual(s["titulo_original"], "Tirzepatide")
        self.assertTrue(s["passado"])


class TestJanelaRecuada(unittest.TestCase):
    def test_o_get_da_agenda_pede_a_semana_anterior(self):
        """Sem `semanas_atras=1`, numa segunda-feira a tela não tem dia passado nenhum."""
        import serve, config
        with mock.patch("db.init"), \
             mock.patch("db.digest_do_dia", return_value=None), \
             mock.patch("db.agenda_listar", return_value={}), \
             mock.patch("db.contar_reserva_pronto", return_value=0), \
             mock.patch("daily.materializar_agenda"), \
             mock.patch("daily._dias_envio",
                        return_value={"segunda", "terca", "quarta", "quinta", "sexta"}), \
             mock.patch("site_web.pagina_agenda", return_value="<html></html>"), \
             mock.patch("agenda_plan.semanas_do_mes",
                        return_value=["2026-08-10"]) as m_janela, \
             mock.patch.object(config, "ADMIN_TOKEN", "tok"):
            serve.Handler.do_GET(_RotaStub("/agenda?token=tok"))
        self.assertEqual(m_janela.call_args.kwargs.get("semanas_atras"), 1)

    def test_materializar_nao_recua(self):
        """`daily.materializar_agenda` decide que dias PREENCHER — recuar criaria slot no
        passado. Teste de comportamento, não grep de fonte: o mesmo trecho aparece em mais
        de um lugar e o grep passa com uma chamada quebrada."""
        import daily
        with mock.patch("agenda_plan.semanas_do_mes", return_value=[]) as m, \
             mock.patch("daily._dias_envio",
                        return_value={"segunda", "terca", "quarta", "quinta", "sexta"}), \
             mock.patch("db.init"):
            try:
                daily.materializar_agenda()
            except Exception:
                pass                      # a janela vazia pode abortar cedo; o que importa
        self.assertTrue(m.called)         # é COMO ela foi pedida
        self.assertEqual(m.call_args.kwargs.get("semanas_atras", 0), 0)
```

Acrescentar o stub de rota no topo do arquivo de teste (mesmo padrão de `test_area_no_revisar.py`):

```python
class _RotaStub:
    """Stub mínimo pro `self` de do_GET/do_POST — a rota /agenda vive INLINE no handler,
    não é método próprio."""

    def __init__(self, path, body=b""):
        import io
        self.path = path
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.headers = {"Content-Length": str(len(body)),
                        "Content-Type": "application/x-www-form-urlencoded"}

    def _html(self, s, code=200):
        return {"code": code, "body": s}

    def _redirect(self, url):
        return {"code": 302, "location": url}

    def _sessao(self):
        return None

    def send_response(self, code):
        self.code = code

    def send_header(self, *a):
        pass

    def end_headers(self):
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_area_pela_agenda.TestJanelaRecuada -v`
Expected: FAIL — `semanas_atras` não é passado (`None != 1`)

- [ ] **Step 3: Write minimal implementation**

Em `app/serve.py:503`:

```python
            # A semana passada fica à vista pra dar onde corrigir a área de um estudo já
            # enviado. Numa SEGUNDA, sem recuar, não há dia passado nenhum na tela.
            janela = agenda_plan.semanas_do_mes(datetime.now(), daily._dias_envio(), 4,
                                                semanas_atras=1)
```

E em `app/serve.py:509-512`, dentro de `_slot_view`:

```python
                if dg:
                    return {"data": d, "tipo": "enviado", "tema": dg.get("tema", ""),
                            "titulo": dg.get("titulo_pt", ""), "fixado": 0, "passado": True,
                            # o painel do card precisa disto; `digest_do_dia` já faz SELECT *
                            "tema_slug": dg.get("tema_slug", ""),
                            "titulo_original": dg.get("titulo_original", ""),
                            "resumo": dg.get("resumo", ""), "fonte": dg.get("fonte", ""),
                            "doi": dg.get("doi", "")}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_area_pela_agenda -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/serve.py app/tests/test_area_pela_agenda.py
git commit -m "feat(agenda): janela recua uma semana e o slot passado carrega o estudo"
```

---

### Task 5: o painel no card do dia passado

**Files:**
- Modify: `app/site_web.py:1894-1934` (`_slot_card`) + função nova `_painel_estudo` logo acima
- Test: `app/tests/test_area_pela_agenda.py`

**Interfaces:**
- Consumes: as chaves do slot da Task 4 (`tema_slug`, `resumo`, `fonte`, `doi`, `titulo_original`), `area_estudo.areas()`
- Produces: HTML com `name="acao" value="corrigir_area_digest"`, `name="slug"`, `name="area"`, `name="data"` — a fiação que a Task 6 lê

- [ ] **Step 1: Write the failing test**

```python
class TestPainelDoDiaPassado(unittest.TestCase):
    """Âncoras com a FRASE INTEIRA — trecho curto casa por acidente (a lição das sete
    asserções falsas da tela de custos)."""

    def _card(self, **extra):
        import site_web
        s = {"data": "2026-08-10", "tipo": "enviado", "tema": "MEUS ESTUDOS",
             "titulo": "Tirzepatida e massa magra", "fixado": 0, "passado": True,
             "tema_slug": "meus-estudos", "titulo_original": "Tirzepatide and lean mass",
             "resumo": "Ensaio randomizado com 342 participantes.",
             "fonte": "JAMA", "doi": "10.1001/jama.2026.123"}
        s.update(extra)
        with mock.patch("area_estudo.areas",
                        return_value=["Obesidade", "Longevidade", "Performance"]):
            return site_web._slot_card(s, "tok", "")

    def test_mostra_o_estudo(self):
        h = self._card()
        self.assertIn("Ensaio randomizado com 342 participantes.", h)
        self.assertIn("JAMA", h)
        self.assertIn("10.1001/jama.2026.123", h)
        self.assertIn("Tirzepatide and lean mass", h)

    def test_a_area_atual_fora_do_config_vem_selecionada(self):
        """'MEUS ESTUDOS' não é chave do temas_config. Sem entrar como opção selecionada,
        o form mandaria uma área diferente sem o curador ter pedido nada."""
        h = self._card()
        self.assertIn('<option value="MEUS ESTUDOS" selected>MEUS ESTUDOS</option>', h)

    def test_traz_as_areas_do_config(self):
        h = self._card()
        for a in ("Obesidade", "Longevidade", "Performance"):
            self.assertIn(f'<option value="{a}">{a}</option>', h)

    def test_area_atual_do_config_nao_duplica(self):
        h = self._card(tema="Obesidade")
        self.assertEqual(h.count('value="Obesidade"'), 1)
        self.assertIn('<option value="Obesidade" selected>Obesidade</option>', h)

    def test_a_fiacao_do_form(self):
        h = self._card()
        self.assertIn('<input type="hidden" name="acao" value="corrigir_area_digest">', h)
        self.assertIn('<input type="hidden" name="slug" value="meus-estudos">', h)
        self.assertIn('<input type="hidden" name="data" value="2026-08-10">', h)
        self.assertIn('name="area"', h)

    def test_avisa_que_o_pdf_entregue_nao_muda(self):
        """Aviso que promete efeito que não acontece foi o erro pego na revisão do bloco
        fixado do dossiê."""
        h = self._card()
        self.assertIn("O PDF que já foi enviado não muda", h)

    def test_dia_passado_sem_estudo_nao_ganha_painel(self):
        h = self._card(titulo="", tema="", tema_slug="", resumo="")
        self.assertNotIn("corrigir_area_digest", h)
        self.assertIn('class="slot passado"', h)

    def test_dia_futuro_continua_sem_painel(self):
        import site_web
        s = {"data": "2026-08-20", "tipo": "reserva", "tema": "Obesidade",
             "titulo": "T", "fixado": 0}
        h = site_web._slot_card(s, "tok", "")
        self.assertNotIn("corrigir_area_digest", h)
        self.assertIn("📌 Fixar", h)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_area_pela_agenda.TestPainelDoDiaPassado -v`
Expected: FAIL — `AssertionError: 'corrigir_area_digest' not found`

- [ ] **Step 3: Write minimal implementation**

Em `app/site_web.py`, logo acima de `_slot_card`:

```python
def _painel_estudo(s, token):
    """O acordeão do dia passado: o que saiu naquele dia + o <select> pra corrigir a área.

    `<details>` nativo, sem JS — mesmo padrão da Reserva por tema. A área atual entra na
    lista mesmo quando não é chave do `temas_config` (o caso "MEUS ESTUDOS"), senão o
    form trocaria a área sozinho no primeiro Salvar.

    O aviso do PDF é literal: o arquivo já foi entregue no WhatsApp e não muda. Prometer
    mais do que a correção alcança é o erro que a revisão do bloco fixado do dossiê pegou.
    """
    import area_estudo
    atual = s.get("tema") or ""
    opcoes = list(area_estudo.areas())
    if atual and atual not in opcoes:
        opcoes.insert(0, atual)
    sel = "".join(f'<option value="{_esc(o)}"{" selected" if o == atual else ""}>'
                  f'{_esc(o)}</option>' for o in opcoes)
    meta = " · ".join(x for x in (_esc(s.get("fonte") or ""), _esc(s.get("doi") or "")) if x)
    orig = (f'<div class="pnl-orig">{_esc(s.get("titulo_original"))}</div>'
            if s.get("titulo_original") else "")
    return (f'<details class="pnl"><summary class="pnl-s">ver o estudo</summary>'
            f'<div class="pnl-b">'
            f'{orig}'
            f'<div class="pnl-meta">{meta}</div>'
            f'<div class="pnl-res">{_esc(s.get("resumo") or "")}</div>'
            f'<form method="post" action="/agenda" class="pnl-f">'
            f'<input type="hidden" name="token" value="{_esc(token)}">'
            f'<input type="hidden" name="acao" value="corrigir_area_digest">'
            f'<input type="hidden" name="data" value="{_esc(s.get("data",""))}">'
            f'<input type="hidden" name="slug" value="{_esc(s.get("tema_slug",""))}">'
            f'<label class="pnl-lbl">Área do estudo</label>'
            f'<select name="area" class="pnl-sel">{sel}</select>'
            f'<button class="slot-btn" type="submit">Salvar</button>'
            f'</form>'
            f'<p class="pnl-av">O PDF que já foi enviado não muda — isto corrige a página '
            f'do portal e a memória do dossiê.</p>'
            f'</div></details>')
```

E trocar o retorno do dia passado em `_slot_card` (linha ~1914):

```python
    if s.get("passado"):        # dia já passado: histórico + painel do estudo enviado
        painel = _painel_estudo(s, token) if s.get("titulo") else ""
        return f'<div class="slot passado" data-data="{de}">{cab}{painel}</div>'
```

Acrescentar ao bloco `css` de `pagina_agenda` (dentro da string `<style>`, antes do `</style>`):

```css
    .slot.passado{opacity:.62}
    .pnl{margin-top:10px}
    .pnl-s{cursor:pointer;font-family:var(--ui);font-size:11.5px;letter-spacing:.04em;
          text-transform:uppercase;color:var(--ouro2);opacity:.9}
    .pnl-b{margin-top:9px;border-top:1px solid var(--line);padding-top:9px}
    .pnl-orig{font-size:12px;color:var(--creme);opacity:.72;font-style:italic;margin-bottom:5px}
    .pnl-meta{font-family:var(--ui);font-size:11px;color:var(--ouro2);margin-bottom:7px}
    .pnl-res{font-size:12.5px;color:var(--creme);opacity:.85;line-height:1.45;
            max-height:190px;overflow:auto;margin-bottom:11px}
    .pnl-lbl{display:block;font-family:var(--ui);font-size:11px;letter-spacing:.05em;
            text-transform:uppercase;color:var(--creme);opacity:.7;margin-bottom:4px}
    .pnl-sel{width:100%;margin-bottom:7px}
    .pnl-av{font-size:11.5px;color:var(--creme);opacity:.6;line-height:1.4;margin:9px 0 0}
```

⚠️ A regra `.slot.passado{opacity:.42}` que já existe deixa o painel quase ilegível. Trocar por `.62` **na regra existente** em vez de acrescentar uma segunda — duas regras com a mesma especificidade e valores diferentes é exatamente o tipo de divergência silenciosa que este projeto já pagou pra aprender.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_area_pela_agenda -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/site_web.py app/tests/test_area_pela_agenda.py
git commit -m "feat(agenda): painel do dia passado com o estudo e o select de area"
```

---

### Task 6: a rota POST `corrigir_area_digest`

**Files:**
- Modify: `app/serve.py:1017` (acrescentar antes do `elif acao == "rematerializar"`)
- Test: `app/tests/test_area_pela_agenda.py`

**Interfaces:**
- Consumes: `area_estudo.aplicar_no_digest` (Task 2), `db.obter(slug, data)`, `db.slug(tema)`, os campos do form da Task 5
- Produces: redirect pra `/agenda` com `msg`

- [ ] **Step 1: Write the failing test**

```python
class TestRotaCorrigirArea(unittest.TestCase):
    """A fiação: sem isto, um campo com nome errado passaria em todo teste de unidade e
    a correção simplesmente não chegaria no banco."""

    def _post(self, campos):
        """Manda o POST. Os dublês do domínio ficam no `with` de cada teste."""
        import urllib.parse as up, serve, config
        with mock.patch("db.init"), mock.patch.object(config, "ADMIN_TOKEN", "tok"), \
             mock.patch("daily._dias_envio",
                        return_value={"segunda", "terca", "quarta", "quinta", "sexta"}):
            return serve.Handler.do_POST(
                _RotaStub("/agenda", up.urlencode(campos).encode("utf-8")))

    def test_leva_data_slug_e_area_ate_o_dominio(self):
        with mock.patch("area_estudo.aplicar_no_digest", return_value="movido") as m:
            out = self._post({"token": "tok", "acao": "corrigir_area_digest",
                              "data": "2026-08-10", "slug": "meus-estudos",
                              "area": "Obesidade"})
        self.assertEqual(m.call_args.args, ("2026-08-10", "meus-estudos", "Obesidade"))
        self.assertIn("rea%20corrigida", out["location"])

    def test_destino_ocupado_nomeia_o_estudo_que_esta_la(self):
        with mock.patch("area_estudo.aplicar_no_digest", return_value="ocupado"), \
             mock.patch("db.slug", return_value="obesidade"), \
             mock.patch("db.obter", return_value={"titulo_pt": "Semaglutida e sono"}):
            out = self._post({"token": "tok", "acao": "corrigir_area_digest",
                              "data": "2026-08-10", "slug": "meus-estudos",
                              "area": "Obesidade"})
        self.assertIn("Semaglutida", up.unquote(out["location"]))

    def test_area_invalida_avisa(self):
        with mock.patch("area_estudo.aplicar_no_digest", return_value="invalida"):
            out = self._post({"token": "tok", "acao": "corrigir_area_digest",
                              "data": "2026-08-10", "slug": "x", "area": "lixo"})
        self.assertIn("reconheci", up.unquote(out["location"]))

    def test_dia_sem_estudo_nao_explode(self):
        with mock.patch("area_estudo.aplicar_no_digest", return_value="inexistente"):
            out = self._post({"token": "tok", "acao": "corrigir_area_digest",
                              "data": "2026-08-10", "slug": "x", "area": "Obesidade"})
        self.assertEqual(out["code"], 302)
        self.assertIn("achei", up.unquote(out["location"]))

    def test_sem_token_da_403(self):
        import urllib.parse as up_, serve, config
        with mock.patch("db.init"), mock.patch.object(config, "ADMIN_TOKEN", "tok"), \
             mock.patch("area_estudo.aplicar_no_digest") as m:
            out = serve.Handler.do_POST(_RotaStub(
                "/agenda", up_.urlencode({"token": "errado", "acao": "corrigir_area_digest",
                                          "data": "2026-08-10", "slug": "x",
                                          "area": "Obesidade"}).encode("utf-8")))
        self.assertEqual(out["code"], 403)
        m.assert_not_called()

    def test_banco_fora_do_ar_avisa_em_vez_de_derrubar(self):
        with mock.patch("area_estudo.aplicar_no_digest",
                        side_effect=RuntimeError("sem conexão")):
            out = self._post({"token": "tok", "acao": "corrigir_area_digest",
                              "data": "2026-08-10", "slug": "x", "area": "Obesidade"})
        self.assertEqual(out["code"], 302)
        self.assertIn("guardar", up.unquote(out["location"]))

    def test_mover_continua_recusando_dia_passado(self):
        """A guarda do `mover` (só dia futuro) não pode ter afrouxado junto com a janela
        recuada. Comportamento, não grep: mandar um `mover` com data de ontem."""
        from datetime import datetime, timedelta
        ontem = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        amanha = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        with mock.patch("db.agenda_mover") as m:
            out = self._post({"token": "tok", "acao": "mover",
                              "data": ontem, "dest": amanha})
        m.assert_not_called()
        self.assertIn("inv", up.unquote(out["location"]).lower())
```

No topo do arquivo de teste, acrescentar `import urllib.parse as up`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_area_pela_agenda.TestRotaCorrigirArea -v`
Expected: FAIL — `aplicar_no_digest` nunca é chamado (a ação cai no `else` e o redirect vem com msg vazia)

- [ ] **Step 3: Write minimal implementation**

Em `app/serve.py`, antes do `elif acao == "rematerializar":`:

```python
            elif acao == "corrigir_area_digest":
                # Estudo JÁ ENVIADO: a área é gravada no `digests`, não no rascunho. Não
                # passa pela lista `validos` do `mover` — aquela guarda existe pra manter
                # o passado imexível, e aqui o passado é justamente o alvo.
                import area_estudo
                area = g("area")
                try:
                    r = area_estudo.aplicar_no_digest(data, g("slug"), area)
                    if r == "movido":
                        msg = f"Área corrigida para {area}."
                    elif r == "ocupado":
                        outro = db.obter(db.slug(area), data) or {}
                        msg = (f"Já existe estudo nesse dia em {area}: "
                               f"{outro.get('titulo_pt') or 'sem título'}. Não mexi em nada.")
                    elif r == "invalida":
                        msg = "Não reconheci essa área."
                    elif r == "inexistente":
                        msg = "Não achei o estudo desse dia."
                    else:
                        msg = "A área já era essa."
                except Exception as e:
                    # Banco fora do ar não pode devolver 500 numa tela que ele abre todo
                    # dia — a agenda continua servindo pro resto.
                    print(f"[agenda] corrigir área de {data} falhou: {e}", flush=True)
                    msg = "Não consegui guardar a área agora — tente de novo."
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_area_pela_agenda -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/serve.py app/tests/test_area_pela_agenda.py
git commit -m "feat(agenda): rota que grava a area corrigida no estudo enviado"
```

---

### Task 7: `draft_store.aplicar` para de "desenviar" estudo

**Files:**
- Modify: `app/draft_store.py:93-102`
- Test: `app/tests/test_area_pela_agenda.py`

**Interfaces:**
- Produces: nenhuma assinatura nova — `aplicar` passa a preservar `status == "SENT"` em `aprovar`/`editar`

Regressão pré-existente anotada na fatia 1: abrir um link velho do `/revisar` de um dia já enviado volta o status pra aprovado, e o `/admin` mostra "✅ aprovado" em vez de "📤 enviado".

⚠️ **`nao_enviar` continua escrevendo `SKIPPED` mesmo em rascunho `SENT`** — é freio de emergência legítimo: `enviar_slot` só respeita `SKIPPED`, então travar isso tiraria a chance de cortar os slots seguintes depois do primeiro ter saído.

- [ ] **Step 1: Write the failing test**

```python
class TestStatusEnviadoNaoRegride(unittest.TestCase):
    def _rascunho(self):
        return {"data": "2026-08-10", "status": "SENT", "artigo": {"tema": "Obesidade"},
                "titulo_pt": "T", "texto": "t"}

    def _aplicar(self, acao):
        import draft_store
        r = self._rascunho()
        with mock.patch("draft_store.carregar", return_value=r), \
             mock.patch("draft_store.salvar"), \
             mock.patch("area_estudo.aplicar_no_rascunho", return_value=False):
            return draft_store.aplicar("2026-08-10", acao, texto="t")

    def test_aprovar_nao_desenvia(self):
        self.assertEqual(self._aplicar("aprovar")["status"], "SENT")

    def test_editar_nao_desenvia(self):
        self.assertEqual(self._aplicar("editar")["status"], "SENT")

    def test_nao_enviar_ainda_freia_o_dia(self):
        """Freio de emergência: `enviar_slot` só respeita SKIPPED, e cortar os slots
        seguintes depois do primeiro ter saído tem que continuar possível."""
        self.assertEqual(self._aplicar("nao_enviar")["status"], "SKIPPED")

    def test_rascunho_nao_enviado_segue_virando_aprovado(self):
        import draft_store
        r = self._rascunho()
        r["status"] = "DRAFT"
        with mock.patch("draft_store.carregar", return_value=r), \
             mock.patch("draft_store.salvar"), \
             mock.patch("area_estudo.aplicar_no_rascunho", return_value=False):
            self.assertEqual(
                draft_store.aplicar("2026-08-10", "aprovar", texto="t")["status"], "APPROVED")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_area_pela_agenda.TestStatusEnviadoNaoRegride -v`
Expected: FAIL — `'APPROVED' != 'SENT'` nos dois primeiros

- [ ] **Step 3: Write minimal implementation**

Em `app/draft_store.py`:

```python
    if acao == "aprovar":
        area_estudo.aplicar_no_rascunho(r, area)
        _guardar_texto(r, texto)
        _guardar_kit(r, kit)
        if r.get("status") != "SENT":     # link velho de dia já enviado não "desenvia"
            r["status"] = "APPROVED"
    elif acao == "editar":
        area_estudo.aplicar_no_rascunho(r, area)
        _guardar_texto(r, texto)
        _guardar_kit(r, kit)
        if r.get("status") != "SENT":
            r["status"] = "EDITED"
    elif acao == "nao_enviar":
        # SEM guarda de propósito: freio de emergência. `enviar_slot` só respeita SKIPPED,
        # e cortar os slots seguintes depois do primeiro ter saído tem que continuar valendo.
        r["status"] = "SKIPPED"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest discover -s tests`
Expected: PASS — a suíte inteira. Se algum teste da fatia 1 esperava `APPROVED` num rascunho `SENT`, ele documentava a regressão: corrigir a expectativa e anotar no commit.

- [ ] **Step 5: Commit**

```bash
git add app/draft_store.py app/tests/test_area_pela_agenda.py
git commit -m "fix(revisar): aprovar link velho nao volta estudo enviado para aprovado"
```

---

### Task 8: bateria de mutação e suíte completa

**Files:**
- Test: `app/tests/test_area_pela_agenda.py` (acrescentar teste se alguma mutação sobreviver)

Mutação que sobrevive é **hipótese, não veredito** — antes de concluir que falta teste, conferir se a âncora do `replace` acertou a linha certa e se não há `.pyc` velho (`find app -name '__pycache__' -exec rm -rf {} +`).

- [ ] **Step 1: Rodar a suíte inteira, limpa**

```bash
find app -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
cd app && python3 -m unittest discover -s tests 2>&1 | tail -5
```
Expected: OK, sem falha. Anotar o total de testes.

- [ ] **Step 2: Mutação 1 — o `UPDATE` esquece o `tema`**

Aplicar no scratchpad (não commitar): em `db.mover_digest_tema`, trocar
`"UPDATE digests SET tema=?, tema_slug=? WHERE data=? AND tema_slug=?"` por
`"UPDATE digests SET tema_slug=? WHERE data=? AND tema_slug=?"` (e tirar `tema_novo` dos parâmetros).

Run: `cd app && python3 -m unittest tests.test_area_pela_agenda -v`
Expected: FAIL em `test_move_tema_e_slug_juntos`. Se passar, o teste não prova nada — acrescentar asserção sobre `novo["tema"]`. Reverter a mutação.

- [ ] **Step 3: Mutação 2 — a guarda de colisão some**

Remover o bloco `if c.execute("SELECT 1 FROM digests WHERE data=? AND tema_slug=?", ...)` inteiro.

Run: `cd app && python3 -m unittest tests.test_area_pela_agenda -v`
Expected: FAIL em `test_destino_ocupado_recusa_e_nao_escreve`. Reverter.

- [ ] **Step 4: Mutação 3 — o default de `semanas_atras` vira 1**

Trocar `semanas_atras=0` por `semanas_atras=1` na assinatura de `semanas_do_mes`.

Run: `cd app && python3 -m unittest tests.test_agenda_plan -v`
Expected: FAIL em `test_default_zero_preserva_os_chamadores_atuais`. Reverter.

- [ ] **Step 5: Mutação 4 — a área atual fora do config não entra no `<select>`**

Em `_painel_estudo`, remover as duas linhas `if atual and atual not in opcoes: opcoes.insert(0, atual)`.

Run: `cd app && python3 -m unittest tests.test_area_pela_agenda -v`
Expected: FAIL em `test_a_area_atual_fora_do_config_vem_selecionada`. Reverter.

- [ ] **Step 6: Mutação 5 — a guarda do SENT some**

Em `draft_store.aplicar`, voltar `r["status"] = "APPROVED"` sem o `if`.

Run: `cd app && python3 -m unittest tests.test_area_pela_agenda -v`
Expected: FAIL em `test_aprovar_nao_desenvia`. Reverter.

- [ ] **Step 7: Suíte limpa e commit final**

```bash
find app -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
cd app && python3 -m unittest discover -s tests 2>&1 | tail -5
```

```bash
git add -u && git commit -m "test(agenda): bateria de mutacao da correcao de area retroativa"
```

(Se nenhuma mutação exigiu teste novo, não há o que commitar — seguir sem commit vazio.)

---

## Conferência ao vivo (depois do deploy)

O item nasceu de um estudo específico. A prova é ele:

1. Abrir `/agenda` no host **artigos.** com `?token=` — a semana passada tem que aparecer antes da semana atual.
2. No card de **10/08**, abrir "ver o estudo": tem que mostrar o resumo, JAMA/DOI e o `<select>` com **MEUS ESTUDOS** selecionado.
3. Escolher a área certa e Salvar.
4. Conferir no portal: o estudo aparece na aba certa e a aba **MEUS ESTUDOS some**.
5. Na próxima reconstrução do dossiê (🧠), o estudo passa a contar no tema certo.
