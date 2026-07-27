# Curadoria — reordenar o fluxo + piso de nota · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganizar a tela `/curadoria` em torno do trabalho real (triar), cortar o entulho da varredura com um piso de nota, e tornar a geração dos resumos priorizados automática.

**Architecture:** O app é um servidor `http.server` sem framework, com HTML montado por f-strings em `site_web.py` e lógica pura em módulos testáveis (`curadoria.py`, `agenda_plan.py`, `daily.py`). O plano segue esse padrão: toda lógica nova nasce como função pura ou com dependência injetável, e o `serve.py` fica só como cola. A página deixa de ser um bloco monolítico e passa a compor helpers pequenos em `site_web.py`.

**Tech Stack:** Python 3 stdlib, `unittest` standalone, SQLite/Supabase via `db.py`, HTML server-rendered (sem JS de framework).

**Spec:** `docs/superpowers/specs/2026-07-26-curadoria-fluxo-design.md`

## Global Constraints

- **Sem JS de framework.** Abas e filtros por querystring; ações por `<form method="post">`. O único JS tolerado é o que já existe no arquivo.
- **Testes:** `unittest` standalone em `app/tests/`, seguindo o cabeçalho dos arquivos existentes (`sys.path.insert` + import do módulo). Rodar tudo com `cd app && python3 -m unittest discover -s tests`.
- **Nada de rede/IA nos testes** — sempre injetar `buscar_fn` / `triar_fn` / `gerar_fn`.
- **Não** aplicar piso de nota em `curadoria.varrer_classicos()` (clássicos ranqueiam por citações).
- **Não** mexer em `daily.preparar_18h`, `daily.enviar_slot`, nem no gate de revisão das 18h.
- **Não** mexer nos `CAPS` de `curadoria.py:18`.
- Variáveis CSS existentes: `--ouro2`/`--gold2` (mesma cor), `--creme`, `--line`, `--ui`, `--muted`. Classes reusáveis já no arquivo: `.tabs`, `.tab`, `.tab.on`, `.cnt`, `.candi`, `.cbody`, `.ctitle`, `.cperg`, `.cmeta`, `.actbtn`, `.slot-btn`, `.badge`, `.badge-fila`, `.hint`, `.infobox`.
- Commits em português, formato `<tipo>: <descrição>`.

---

### Task 1: Piso de nota na varredura

**Files:**
- Modify: `app/config.py` (depois de `DIA_VARREDURA`, linha 74)
- Modify: `app/curadoria.py` (nova função + uso em `varrer`, linhas 47-82)
- Test: `app/tests/test_curadoria.py`

**Interfaces:**
- Consumes: nada de tasks anteriores.
- Produces: `curadoria.aplicar_piso(bons, piso=None, min_por_tema=None) -> list`; `curadoria.varrer(desde, ate, caps=None, buscar_fn=None, triar_fn=None, piso=None, min_por_tema=None)`; `config.SCORE_PISO` (float), `config.MIN_POR_TEMA` (int).

- [ ] **Step 1: Write the failing test**

Adicionar ao fim de `app/tests/test_curadoria.py`, antes do `if __name__`:

```python
class TestPiso(unittest.TestCase):
    def test_corta_abaixo_do_piso_quando_ha_fartura(self):
        bons = [{"score": 9}, {"score": 8}, {"score": 7}, {"score": 3}, {"score": 2}]
        out = curadoria.aplicar_piso(bons, piso=6, min_por_tema=3)
        self.assertEqual([b["score"] for b in out], [9, 8, 7])

    def test_valvula_afrouxa_quando_tema_seco(self):
        # só 1 acima do piso, mas min_por_tema=3 -> entrega os 3 melhores mesmo abaixo
        bons = [{"score": 9}, {"score": 4}, {"score": 3}]
        out = curadoria.aplicar_piso(bons, piso=6, min_por_tema=3)
        self.assertEqual([b["score"] for b in out], [9, 4, 3])

    def test_tema_vazio_continua_vazio(self):
        self.assertEqual(curadoria.aplicar_piso([], piso=6, min_por_tema=3), [])

    def test_score_ausente_conta_como_zero(self):
        out = curadoria.aplicar_piso([{"titulo": "x"}], piso=6, min_por_tema=0)
        self.assertEqual(out, [])

    def test_varrer_aplica_o_piso(self):
        # _fake_triar dá scores 10,9,8,7,6 por tema; piso=8 e min=1 deixa só 10,9,8
        out = curadoria.varrer("2026-01-01", "2026-03-01",
                               caps={"Obesidade": 99}, buscar_fn=_fake_buscar,
                               triar_fn=_fake_triar, piso=8, min_por_tema=1)
        obes = [c for c in out if c["tema"] == "Obesidade"]
        self.assertEqual(len(obes), 3)
        self.assertTrue(all(c["score"] >= 8 for c in obes))

    def test_varrer_classicos_ignora_o_piso(self):
        # clássicos ranqueiam por citações — o piso de nota não pode cortá-los
        out = curadoria.varrer_classicos(caps={"Obesidade": 99}, buscar_fn=_fake_buscar,
                                         triar_fn=_fake_triar)
        self.assertTrue([c for c in out if c["tema"] == "Obesidade"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_curadoria.TestPiso -v`
Expected: FAIL com `AttributeError: module 'curadoria' has no attribute 'aplicar_piso'`

- [ ] **Step 3: Write minimal implementation**

Em `app/config.py`, logo depois da linha `DIA_VARREDURA = ...`:

```python
# Piso de qualidade da varredura: candidato com nota abaixo de SCORE_PISO não entra na
# curadoria. Válvula: tema que não alcançar MIN_POR_TEMA acima do piso afrouxa e entrega
# os melhores que tiver — tema seco não pode zerar.
SCORE_PISO = float(os.environ.get("DSCURSO_SCORE_PISO") or 6)
MIN_POR_TEMA = int(os.environ.get("DSCURSO_MIN_POR_TEMA") or 3)
```

Em `app/curadoria.py`, logo depois de `_normalizar` (antes de `def varrer`):

```python
def aplicar_piso(bons, piso=None, min_por_tema=None):
    """Corta os de nota baixa. Se sobrar menos que `min_por_tema`, afrouxa e devolve os
    melhores que houver (tema seco não pode zerar). `bons` já vem ordenado por score desc."""
    import config
    piso = config.SCORE_PISO if piso is None else piso
    min_por_tema = config.MIN_POR_TEMA if min_por_tema is None else min_por_tema
    acima = [a for a in bons if float(a.get("score", 0) or 0) >= piso]
    return acima if len(acima) >= min_por_tema else bons[:min_por_tema]
```

Na assinatura de `varrer`, trocar por:

```python
def varrer(desde, ate, caps=None, buscar_fn=None, triar_fn=None, piso=None, min_por_tema=None):
```

E dentro do loop de temas, logo depois de `bons.sort(key=lambda x: x.get("score", 0), reverse=True)`:

```python
        bons = aplicar_piso(bons, piso, min_por_tema)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_curadoria -v`
Expected: PASS (todos, incluindo os testes antigos de `varrer`)

- [ ] **Step 5: Commit**

```bash
git add app/config.py app/curadoria.py app/tests/test_curadoria.py
git commit -m "feat(curadoria): piso de nota na varredura com válvula p/ tema seco"
```

---

### Task 2: Estado do estoque (função pura)

**Files:**
- Modify: `app/agenda_plan.py` (nova função, depois de `precisa_reabastecer`)
- Test: `app/tests/test_agenda_plan.py`

**Interfaces:**
- Consumes: `agenda_plan.dias_uteis_desde(inicio, n, dias_envio)` (já existe).
- Produces: `agenda_plan.estado_estoque(reserva_n, cand_n, classico_n, hoje, dias_envio, minimo) -> {"envios": int, "ate": str|None, "baixo": bool}`. `hoje` é `datetime`; `ate` é `YYYY-MM-DD`.

- [ ] **Step 1: Write the failing test**

Adicionar ao fim de `app/tests/test_agenda_plan.py`, antes do `if __name__`:

```python
class TestEstadoEstoque(unittest.TestCase):
    UTEIS = ["segunda", "terca", "quarta", "quinta", "sexta"]

    def test_conta_e_projeta_a_data_do_ultimo_envio(self):
        # 2026-07-27 é segunda; 5 envios cobrem até sexta 31/07
        e = ap.estado_estoque(2, 3, 0, datetime(2026, 7, 27), self.UTEIS, minimo=10)
        self.assertEqual(e["envios"], 5)
        self.assertEqual(e["ate"], "2026-07-31")

    def test_soma_as_tres_fontes(self):
        e = ap.estado_estoque(1, 2, 4, datetime(2026, 7, 27), self.UTEIS, minimo=10)
        self.assertEqual(e["envios"], 7)

    def test_estoque_zero_nao_tem_data(self):
        e = ap.estado_estoque(0, 0, 0, datetime(2026, 7, 27), self.UTEIS, minimo=10)
        self.assertIsNone(e["ate"])
        self.assertTrue(e["baixo"])

    def test_limiar_exato_nao_e_baixo(self):
        e = ap.estado_estoque(10, 0, 0, datetime(2026, 7, 27), self.UTEIS, minimo=10)
        self.assertFalse(e["baixo"])

    def test_abaixo_do_limiar_e_baixo(self):
        e = ap.estado_estoque(9, 0, 0, datetime(2026, 7, 27), self.UTEIS, minimo=10)
        self.assertTrue(e["baixo"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_agenda_plan.TestEstadoEstoque -v`
Expected: FAIL com `AttributeError: module 'agenda_plan' has no attribute 'estado_estoque'`

- [ ] **Step 3: Write minimal implementation**

Em `app/agenda_plan.py`, depois de `precisa_reabastecer`:

```python
def estado_estoque(reserva_n, cand_n, classico_n, hoje, dias_envio, minimo):
    """Quantos envios o estoque cobre e até que dia. Puro (sem I/O).
    `hoje` é datetime (mesmo contrato de dias_uteis_desde); `dias_envio` é iterável de
    nomes de dia; `ate` volta em YYYY-MM-DD, ou None quando não há estoque."""
    envios = reserva_n + cand_n + classico_n
    ate = dias_uteis_desde(hoje, envios, dias_envio)[-1] if envios else None
    return {"envios": envios, "ate": ate, "baixo": envios < minimo}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_agenda_plan -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/agenda_plan.py app/tests/test_agenda_plan.py
git commit -m "feat(agenda): estado_estoque — quantos envios o estoque cobre e até quando"
```

---

### Task 3: Geração noturna automática dos priorizados

**Files:**
- Modify: `app/config.py` (junto das constantes da Task 1)
- Modify: `app/daily.py` (nova função, depois de `varredura_semanal` que começa na linha 483 e termina no `return True`)
- Modify: `app/serve.py` (`agendador`, linhas 39-54)
- Test: `app/tests/test_gerar_noturno.py` (criar)

**Interfaces:**
- Consumes: `curadoria.gerar_selecionados()` (já existe, retorna int).
- Produces: `daily.gerar_selecionados_noturno(gerar_fn=None) -> int`; `config.HORA_CURADORIA` (int).

- [ ] **Step 1: Write the failing test**

Criar `app/tests/test_gerar_noturno.py`:

```python
"""Geração noturna dos candidatos priorizados na curadoria (fn injetável, sem IA).
Standalone: python3 app/tests/test_gerar_noturno.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import daily


class TestGerarNoturno(unittest.TestCase):
    def test_chama_o_gerador_e_devolve_o_total(self):
        chamou = []
        n = daily.gerar_selecionados_noturno(gerar_fn=lambda: chamou.append(1) or 3)
        self.assertEqual(n, 3)
        self.assertEqual(len(chamou), 1)

    def test_falha_no_gerador_nao_propaga(self):
        def explode():
            raise RuntimeError("IA fora do ar")
        self.assertEqual(daily.gerar_selecionados_noturno(gerar_fn=explode), 0)

    def test_nada_selecionado_devolve_zero(self):
        self.assertEqual(daily.gerar_selecionados_noturno(gerar_fn=lambda: 0), 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_gerar_noturno -v`
Expected: FAIL com `AttributeError: module 'daily' has no attribute 'gerar_selecionados_noturno'`

- [ ] **Step 3: Write minimal implementation**

Em `app/config.py`, junto de `SCORE_PISO`/`MIN_POR_TEMA`:

```python
HORA_CURADORIA = int(os.environ.get("DSCURSO_HORA_CURADORIA") or 21)   # gera os priorizados
```

Em `app/daily.py`, depois de `varredura_semanal`:

```python
def gerar_selecionados_noturno(gerar_fn=None):
    """Gera os resumos dos candidatos que o Diego priorizou na curadoria.
    Roda todo dia às config.HORA_CURADORIA — DEPOIS do preparo das 18h, que tem
    prioridade (ele é quem dispara a revisão do estudo de amanhã).
    Idempotente: gerar_selecionados marca 'resumido' e não repete. gerar_fn injetável."""
    gerar_fn = gerar_fn or (lambda: __import__("curadoria").gerar_selecionados())
    try:
        n = gerar_fn()
        print(f"[curadoria-noturna] {n} resumo(s) gerado(s)", flush=True)
        return n
    except Exception as e:
        print(f"[curadoria-noturna] erro: {e}", flush=True)
        return 0
```

Em `app/serve.py`, na função `agendador`, no dict `tarefas` (linha 39-40), acrescentar a chave:

```python
    tarefas = {"rotina08": daily.rotina_08h, "prep18": _prep_e_18h,
               "varredura_semanal": daily.varredura_semanal,
               "gerar_curadoria": daily.gerar_selecionados_noturno}
```

E depois da linha `horarios.append((config.HORA_VARREDURA, "varredura_semanal"))`:

```python
    horarios.append((config.HORA_CURADORIA, "gerar_curadoria"))   # gera os priorizados
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_gerar_noturno -v && python3 -c "import serve" && echo IMPORT_OK`
Expected: PASS + `IMPORT_OK` (garante que o `agendador` não quebrou no import)

- [ ] **Step 5: Commit**

```bash
git add app/config.py app/daily.py app/serve.py app/tests/test_gerar_noturno.py
git commit -m "feat(curadoria): geração noturna automática dos candidatos priorizados"
```

---

### Task 4: Faixa de estoque, "Amanhã sai" e abas

**Files:**
- Modify: `app/site_web.py` (CSS logo depois da regra `.legend{...}` na linha 183; helpers novos imediatamente antes de `def pagina_curadoria`, linha 1006)
- Test: `app/tests/test_site_web.py`

**Interfaces:**
- Consumes: `agenda_plan.estado_estoque` (Task 2) — o dict `{"envios","ate","baixo"}`.
- Produces: `site_web._curadoria_faixa(estado) -> str`; `site_web._curadoria_amanha(amanha) -> str`; `site_web._curadoria_abas(aba, contagens, token, tema="") -> str`. `amanha` é `{"titulo","status","review_token"}` ou `None`. `contagens` é `{"triagem": int, "reserva": int, "classicos": int}`.

- [ ] **Step 1: Write the failing test**

Adicionar ao fim de `app/tests/test_site_web.py`, antes do `if __name__`:

```python
class TestCuradoriaCabecalho(unittest.TestCase):
    def setUp(self):
        import site_web
        self.s = site_web

    def test_faixa_mostra_envios_e_data(self):
        html = self.s._curadoria_faixa({"envios": 14, "ate": "2026-08-14", "baixo": False})
        self.assertIn("14/08", html)
        self.assertIn("14 envios", html)
        self.assertNotIn("baixo", html)

    def test_faixa_alerta_quando_baixo(self):
        html = self.s._curadoria_faixa({"envios": 3, "ate": "2026-07-29", "baixo": True})
        self.assertIn("baixo", html)

    def test_faixa_sem_estoque(self):
        html = self.s._curadoria_faixa({"envios": 0, "ate": None, "baixo": True})
        self.assertIn("Sem estoque", html)

    def test_amanha_mostra_titulo_e_link_de_revisao(self):
        html = self.s._curadoria_amanha(
            {"titulo": "Tirzepatida 72 semanas", "status": "DRAFT", "review_token": "abc123"})
        self.assertIn("Tirzepatida 72 semanas", html)
        self.assertIn("/revisar/abc123", html)
        self.assertIn("aguardando sua revisão", html)

    def test_amanha_reflete_status_aprovado(self):
        html = self.s._curadoria_amanha(
            {"titulo": "X", "status": "APPROVED", "review_token": "t"})
        self.assertIn("aprovado", html)

    def test_amanha_vazio_nao_renderiza(self):
        self.assertEqual(self.s._curadoria_amanha(None), "")

    def test_abas_marcam_a_ativa_e_mostram_contador(self):
        html = self.s._curadoria_abas(
            "triagem", {"triagem": 12, "reserva": 8, "classicos": 0}, "tok")
        self.assertIn('class="tab on"', html)
        self.assertIn(">12<", html)
        self.assertIn("aba=reserva", html)
        self.assertIn("aba=classicos", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_site_web.TestCuradoriaCabecalho -v`
Expected: FAIL com `AttributeError: module 'site_web' has no attribute '_curadoria_faixa'`

- [ ] **Step 3: Write minimal implementation**

Em `app/site_web.py`, no bloco `<style>`, logo depois da regra `.legend{...}` (linha 183), acrescentar:

```css
.faixa{font-family:var(--ui);font-size:13.5px;color:var(--creme);background:rgba(255,255,255,.04);
       border:1px solid var(--line);border-radius:12px;padding:11px 15px;margin:4px 0 14px}
.faixa.baixo{color:#eaa982;background:rgba(200,120,60,.13);border-color:rgba(200,120,60,.34)}
.amanha{background:linear-gradient(180deg,rgba(201,162,39,.10),rgba(255,255,255,.02));
        border:1px solid rgba(201,162,39,.30);border-radius:14px;padding:13px 16px;margin:0 0 18px}
.am-t{font-family:var(--ui);font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--ouro2)}
.am-tit{font-size:15px;color:var(--creme);line-height:1.35;margin:6px 0 10px}
.am-rod{display:flex;align-items:center;justify-content:space-between;gap:10px;
        font-family:var(--ui);font-size:12.5px;color:var(--muted)}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0 14px}
.chip{font-family:var(--ui);font-size:12.5px;color:var(--muted);background:rgba(255,255,255,.05);
      border:1px solid var(--line);border-radius:100px;padding:6px 13px;text-decoration:none;transition:.15s}
.chip:hover{color:var(--creme);border-color:rgba(201,162,39,.35)}
.chip.on{color:var(--ouro2);background:rgba(201,162,39,.15);border-color:rgba(201,162,39,.38)}
.chip b{font-family:var(--mono);font-weight:700}
.cacts{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px}
```

Em `app/site_web.py`, imediatamente antes de `def pagina_curadoria`:

```python
def _curadoria_faixa(estado):
    """Uma linha respondendo 'vou ficar sem conteúdo?'. Laranja quando o estoque é baixo."""
    n = estado.get("envios", 0)
    ate = estado.get("ate")
    if not n:
        txt = "Sem estoque — nenhum envio coberto"
    else:
        quando = f"{ate[8:10]}/{ate[5:7]}" if ate else "—"
        txt = f"Conteúdo garantido até {quando} · {n} envio{'s' if n != 1 else ''}"
    cls = "faixa baixo" if estado.get("baixo") else "faixa"
    return f'<div class="{cls}">📦 {_esc(txt)}</div>'


_AMANHA_ROT = {"APPROVED": "✅ aprovado", "EDITED": "✏️ editado", "SKIPPED": "🚫 bloqueado",
               "SENT": "📤 enviado"}


def _curadoria_amanha(amanha):
    """Cartão do estudo preparado p/ amanhã, com atalho pra revisão. None => nada."""
    if not amanha:
        return ""
    tok = _esc(amanha.get("review_token") or "")
    rot = _AMANHA_ROT.get(amanha.get("status"), "aguardando sua revisão")
    botao = (f'<a class="actbtn ghost" href="/revisar/{tok}" style="text-decoration:none;'
             f'padding:7px 14px;font-size:12.5px">Revisar</a>') if tok else ""
    return (f'<div class="amanha"><div class="am-t">📋 Amanhã sai</div>'
            f'<div class="am-tit">{_esc(amanha.get("titulo") or "—")}</div>'
            f'<div class="am-rod"><span>{_esc(rot)}</span>{botao}</div></div>')


def _curadoria_abas(aba, contagens, token, tema=""):
    """Abas de 1º nível (triagem/reserva/classicos) por querystring — sem JS."""
    tk = _esc(token)
    out = []
    for chave, rotulo in (("triagem", "Triagem"), ("reserva", "Reserva"), ("classicos", "Clássicos")):
        on = " on" if chave == aba else ""
        q = f"?token={tk}&aba={chave}"
        if chave == "triagem" and tema:
            from urllib.parse import quote
            q += f"&tema={quote(tema)}"
        out.append(f'<a class="tab{on}" href="/curadoria{q}" style="text-decoration:none">'
                   f'{rotulo} <span class="cnt">{contagens.get(chave, 0)}</span></a>')
    return f'<div class="tabs">{"".join(out)}</div>'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_site_web -v`
Expected: PASS nos testes novos. **Os testes antigos seguem passando** — `pagina_curadoria` ainda não mudou nesta task.

- [ ] **Step 5: Commit**

```bash
git add app/site_web.py app/tests/test_site_web.py
git commit -m "feat(curadoria): faixa de estoque, cartão 'amanhã sai' e abas de 1º nível"
```

---

### Task 5: Item da triagem com link e ações imediatas

**Files:**
- Modify: `app/site_web.py` (helper novo, depois de `_curadoria_abas`)
- Modify: `app/serve.py` (POST `/curadoria`: ramo `selecionar` nas linhas 555-558, redirect na linha 580)
- Test: `app/tests/test_site_web.py`

**Interfaces:**
- Consumes: `site_web._chip_score(score)` e `site_web._esc(s)` (já existem).
- Produces: `site_web._curadoria_item(c, token, aba="triagem", tema="") -> str`. `c` é a linha de `curadoria_candidatos` (`id`, `titulo`, `pergunta`, `score`, `fonte`, `data`, `doi`, `url`, `status`). Ações POST novas: `priorizar`, `descartar`, `desfazer` (campos `token`, `acao`, `id`, `aba`, `tema`).

- [ ] **Step 1: Write the failing test**

Adicionar ao fim de `app/tests/test_site_web.py`:

```python
class TestCuradoriaItem(unittest.TestCase):
    def setUp(self):
        import site_web
        self.s = site_web
        self.c = {"id": "c1", "titulo": "Tirzepatida 72 semanas", "pergunta": "Sustenta a perda?",
                  "score": 8, "fonte": "Lancet", "data": "2026-07-12",
                  "doi": "10.1016/x", "url": "", "status": "novo"}

    def test_mostra_titulo_pergunta_e_meta(self):
        html = self.s._curadoria_item(self.c, "tok")
        self.assertIn("Tirzepatida 72 semanas", html)
        self.assertIn("Sustenta a perda?", html)
        self.assertIn("Lancet", html)
        self.assertIn("2026-07-12", html)

    def test_titulo_vira_link_pelo_doi(self):
        html = self.s._curadoria_item(self.c, "tok")
        self.assertIn('href="https://doi.org/10.1016/x"', html)
        self.assertIn('target="_blank"', html)

    def test_titulo_prefere_url_quando_existe(self):
        html = self.s._curadoria_item({**self.c, "url": "https://ex.com/a"}, "tok")
        self.assertIn('href="https://ex.com/a"', html)

    def test_sem_doi_e_sem_url_nao_vira_link(self):
        html = self.s._curadoria_item({**self.c, "doi": "", "url": ""}, "tok")
        self.assertNotIn("<a class=\"ctitle\"", html)
        self.assertIn("Tirzepatida 72 semanas", html)

    def test_novo_oferece_priorizar_e_descartar(self):
        html = self.s._curadoria_item(self.c, "tok")
        self.assertIn('value="priorizar"', html)
        self.assertIn('value="descartar"', html)
        self.assertNotIn('value="desfazer"', html)

    def test_selecionado_mostra_badge_e_desfazer(self):
        html = self.s._curadoria_item({**self.c, "status": "selecionado"}, "tok")
        self.assertIn("gera hoje à noite", html)
        self.assertIn('value="desfazer"', html)
        self.assertNotIn('value="priorizar"', html)

    def test_ancora_do_item(self):
        self.assertIn('id="cand-c1"', self.s._curadoria_item(self.c, "tok"))

    def test_preserva_aba_e_tema_no_form(self):
        html = self.s._curadoria_item(self.c, "tok", aba="triagem", tema="Obesidade")
        self.assertIn('name="tema" value="Obesidade"', html)

    def test_nao_tem_mais_checkbox(self):
        self.assertNotIn("<input type=\"checkbox\"", self.s._curadoria_item(self.c, "tok"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_site_web.TestCuradoriaItem -v`
Expected: FAIL com `AttributeError: module 'site_web' has no attribute '_curadoria_item'`

- [ ] **Step 3: Write minimal implementation**

Em `app/site_web.py`, depois de `_curadoria_abas`:

```python
def _curadoria_item(c, token, aba="triagem", tema=""):
    """Um candidato da triagem: título linkado pro estudo, pergunta, meta e as ações
    imediatas (priorizar/descartar, ou desfazer se já priorizado)."""
    tk, cid = _esc(token), _esc(c.get("id"))
    alvo = c.get("url") or (f"https://doi.org/{c.get('doi')}" if c.get("doi") else "")
    tit = _esc(c.get("titulo"))
    titulo = (f'<a class="ctitle" href="{_esc(alvo)}" target="_blank" rel="noopener">{tit} ↗</a>'
              if alvo else f'<span class="ctitle">{tit}</span>')

    def _acao(acao, label):
        return (f'<form method="post" action="/curadoria" style="display:inline">'
                f'<input type="hidden" name="token" value="{tk}">'
                f'<input type="hidden" name="acao" value="{acao}">'
                f'<input type="hidden" name="id" value="{cid}">'
                f'<input type="hidden" name="aba" value="{_esc(aba)}">'
                f'<input type="hidden" name="tema" value="{_esc(tema)}">'
                f'<button class="slot-btn" type="submit">{label}</button></form>')

    if c.get("status") == "selecionado":
        acoes = ('<span class="badge badge-fila">⏳ gera hoje à noite</span>'
                 + _acao("desfazer", "↩️ Desfazer"))
    else:
        acoes = _acao("priorizar", "⬆️ Priorizar") + _acao("descartar", "🗑️ Descartar")
    return (f'<div class="candi" id="cand-{cid}"><span class="cbody">'
            f'<span style="display:flex;align-items:center;gap:8px;justify-content:space-between">'
            f'{titulo}{_chip_score(c.get("score"))}</span>'
            f'<span class="cperg">❓ {_esc(c.get("pergunta") or "—")}</span>'
            f'<span class="cmeta">{_esc(c.get("fonte", ""))} · {_esc(c.get("data", ""))}'
            f'{" · DOI " + _esc(c.get("doi")) if c.get("doi") else ""}</span>'
            f'<span class="cacts">{acoes}</span></span></div>')
```

Em `app/serve.py`, no POST `/curadoria`, **substituir** o ramo `if acao == "selecionar":` (linhas 555-558 — as quatro linhas do `if` até o `msg = f"Seleção salva…"`) por:

```python
            aba, tema = g("aba") or "triagem", g("tema")
            ancora = ""
            if acao in ("priorizar", "descartar", "desfazer"):
                novo = {"priorizar": "selecionado", "descartar": "descartado",
                        "desfazer": "novo"}[acao]
                cid = g("id")
                db.marcar_candidatos([cid], novo)
                msg = {"priorizar": "Priorizado — o resumo é gerado hoje à noite.",
                       "descartar": "Estudo descartado.",
                       "desfazer": "Prioridade removida."}[acao]
                ancora = f"#cand-{up.quote(cid)}" if acao == "desfazer" else ""
```

E **substituir** a linha final do redirect (linha 580, a que começa com `return self._redirect(f"/curadoria?token=`) por:

```python
            destino = (f"/curadoria?token={config.ADMIN_TOKEN}&aba={up.quote(aba)}"
                       f"&tema={up.quote(tema)}&msg={up.quote(msg)}{ancora}")
            return self._redirect(destino)
```

> A âncora só volta no `desfazer` porque nas outras duas ações o item muda de estado ou some da lista — voltar pra um `id` que não está mais renderizado deixaria a página no topo de qualquer jeito.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_site_web -v && python3 -c "import serve" && echo IMPORT_OK`
Expected: PASS + `IMPORT_OK`

- [ ] **Step 5: Commit**

```bash
git add app/site_web.py app/serve.py app/tests/test_site_web.py
git commit -m "feat(curadoria): ações imediatas por item (priorizar/descartar/desfazer) + título linkado"
```

---

### Task 6: Montar a página nova

**Files:**
- Modify: `app/site_web.py` (`pagina_curadoria` — reescrita; começa na linha 1006 e termina logo antes do comentário `# ── Agenda de envios (admin, token)`)
- Modify: `app/serve.py` (GET `/curadoria` — bloco que começa na linha 258 e termina no `return self._html(site_web.pagina_curadoria(...), 200)`)
- Test: `app/tests/test_site_web.py` (ajustar a chamada antiga da linha ~136 + testes novos)

**Interfaces:**
- Consumes: `_curadoria_faixa`, `_curadoria_amanha`, `_curadoria_abas` (Task 4), `_curadoria_item` (Task 5), `agenda_plan.estado_estoque` (Task 2).
- Produces: `site_web.pagina_curadoria(estado, amanha, candidatos, reserva, classicos, token, aba="triagem", tema="", msg="") -> str`. `classicos` é `{"candidatos": [...], "banco": [...]}`.

- [ ] **Step 1: Write the failing test**

Em `app/tests/test_site_web.py`, **substituir** o teste existente que chama `pagina_curadoria` (~linha 136) e acrescentar a classe nova:

```python
class TestPaginaCuradoria(unittest.TestCase):
    def setUp(self):
        import site_web
        self.s = site_web
        self.estado = {"envios": 12, "ate": "2026-08-12", "baixo": False}
        self.cand = {"id": "c1", "titulo": "Estudo A", "pergunta": "P?", "score": 8,
                     "fonte": "Lancet", "data": "2026-07-12", "doi": "10.1/a",
                     "url": "", "status": "novo", "tema": "Obesidade", "tipo": "varredura"}
        self.classicos = {"candidatos": [], "banco": []}

    def _render(self, **kw):
        base = dict(estado=self.estado, amanha=None, candidatos=[self.cand], reserva=[],
                    classicos=self.classicos, token="tok")
        base.update(kw)
        return self.s.pagina_curadoria(**base)

    def test_renderiza_triagem_por_padrao(self):
        html = self._render()
        self.assertIn("Estudo A", html)
        self.assertIn('class="tab on"', html)

    def test_nao_tem_mais_salvar_selecao(self):
        html = self._render()
        self.assertNotIn("Salvar seleção", html)
        self.assertNotIn('type="checkbox"', html)

    def test_filtro_por_tema_esconde_os_outros(self):
        outro = {**self.cand, "id": "c2", "titulo": "Estudo B", "tema": "Hormonal"}
        html = self._render(candidatos=[self.cand, outro], tema="Obesidade")
        self.assertIn("Estudo A", html)
        self.assertNotIn("Estudo B", html)

    def test_aba_reserva_lista_os_prontos(self):
        reserva = [{"id": "r1", "tema": "Obesidade", "status": "pronto",
                    "titulo_pt": "Resumo pronto", "resumo": "txt", "prioridade": 0}]
        html = self._render(reserva=reserva, aba="reserva")
        self.assertIn("Resumo pronto", html)

    def test_aba_classicos_lista_candidatos_classicos(self):
        cl = {**self.cand, "id": "k1", "titulo": "Clássico X", "tipo": "classico"}
        html = self._render(classicos={"candidatos": [cl], "banco": []}, aba="classicos")
        self.assertIn("Clássico X", html)

    def test_classico_nao_vaza_pra_triagem(self):
        cl = {**self.cand, "id": "k1", "titulo": "Clássico X", "tipo": "classico"}
        html = self._render(classicos={"candidatos": [cl], "banco": []})
        self.assertNotIn("Clássico X", html)

    def test_ferramentas_tem_meu_estudo_e_varreduras(self):
        html = self._render()
        self.assertIn("Adicionar meu estudo", html)
        self.assertIn('value="varrer"', html)
        self.assertIn('value="varrer_classicos"', html)

    def test_faixa_e_amanha_aparecem(self):
        html = self._render(amanha={"titulo": "Amanhã X", "status": "DRAFT",
                                    "review_token": "tk9"})
        self.assertIn("Conteúdo garantido até", html)
        self.assertIn("Amanhã X", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_site_web.TestPaginaCuradoria -v`
Expected: FAIL com `TypeError: pagina_curadoria() got an unexpected keyword argument 'estado'`

- [ ] **Step 3: Write minimal implementation**

Em `app/site_web.py`, **substituir a função `pagina_curadoria` inteira** (linhas 974-1093) por:

```python
_CUR_EMOJI = {"Obesidade": "⚖️", "Hormonal": "⚕️", "Lipedema": "🦵",
              "Performance": "🏃", "Longevidade": "🧬"}
_CUR_ORDEM = ["Obesidade", "Hormonal", "Lipedema", "Performance", "Longevidade"]


def _curadoria_chips(candidatos, token, tema=""):
    """Filtro por tema dentro da triagem. Mostra as 5 frentes sempre (inclusive com 0)."""
    from urllib.parse import quote
    tk = _esc(token)
    n = {}
    for c in candidatos:
        k = c.get("tema", "—")
        n[k] = n.get(k, 0) + 1
    temas = _CUR_ORDEM + [t for t in n if t not in _CUR_ORDEM]
    chips = [f'<a class="chip{"" if tema else " on"}" href="/curadoria?token={tk}&aba=triagem">'
             f'Todos <b>{len(candidatos)}</b></a>']
    for t in temas:
        on = " on" if t == tema else ""
        chips.append(f'<a class="chip{on}" href="/curadoria?token={tk}&aba=triagem&tema={quote(t)}">'
                     f'{_CUR_EMOJI.get(t, "•")} {_esc(t)} <b>{n.get(t, 0)}</b></a>')
    return f'<div class="chips">{"".join(chips)}</div>'


def _curadoria_reserva_item(r, token):
    """Item da Reserva: título + <details> pra editar/remover (comportamento original)."""
    tok, rid = _esc(token), _esc(r.get("id"))
    prio = ' · <span style="color:var(--ouro2)">★ prioridade</span>' if r.get("prioridade") else ""
    return (
        f'<div class="item">'
        f'<div class="d">{_esc(r.get("tema"))} · {_esc(r.get("status"))}{prio}</div>'
        f'<div class="t">{_esc(r.get("titulo_pt"))}</div>'
        f'<details style="margin-top:8px">'
        f'<summary style="cursor:pointer;color:var(--ouro2);font-family:system-ui,sans-serif;'
        f'font-size:13px">✏️ editar / remover</summary>'
        f'<form method="post" action="/curadoria" style="margin-top:12px">'
        f'<input type="hidden" name="token" value="{tok}">'
        f'<input type="hidden" name="acao" value="editar_reserva">'
        f'<input type="hidden" name="id" value="{rid}">'
        f'<input type="hidden" name="aba" value="reserva">'
        f'<label>Título</label>'
        f'<input type="text" name="titulo_pt" value="{_esc(r.get("titulo_pt"))}" style="width:100%">'
        f'<label style="margin-top:10px">Resumo (pode ajustar o texto que a IA gerou)</label>'
        f'<textarea name="resumo" rows="10">{_esc(r.get("resumo"))}</textarea>'
        f'<button class="actbtn" type="submit">Salvar alterações</button>'
        f'</form>'
        f'<form method="post" action="/curadoria" '
        f'onsubmit="return confirm(\'Remover este item da reserva?\')" style="margin-top:10px">'
        f'<input type="hidden" name="token" value="{tok}">'
        f'<input type="hidden" name="acao" value="remover_reserva">'
        f'<input type="hidden" name="id" value="{rid}">'
        f'<input type="hidden" name="aba" value="reserva">'
        f'<button class="actbtn ghost" type="submit">🗑️ Remover da reserva</button>'
        f'</form></details></div>')


def _curadoria_ferramentas(token):
    """Ações raras, recolhidas: adicionar meu estudo (PDF) e as duas varreduras."""
    tok = _esc(token)
    def _varredura(acao, label, pergunta):
        return (f'<form method="post" action="/curadoria" style="display:inline" '
                f'onsubmit="return confirm(\'{pergunta}\')">'
                f'<input type="hidden" name="token" value="{tok}">'
                f'<input type="hidden" name="acao" value="{acao}">'
                f'<button class="actbtn ghost" type="submit">{label}</button></form>')
    return f"""
      <details style="margin-top:26px">
        <summary style="cursor:pointer;color:var(--ouro2);font-family:var(--ui);font-size:13px">
          ⚙️ Ferramentas</summary>
        <div style="display:flex;gap:10px;flex-wrap:wrap;margin:14px 0 18px">
          {_varredura("varrer", "🔎 Varrer agora",
                      "Rodar a varredura no Europe PMC (Haiku)? Pode levar 1–2 min.")}
          {_varredura("varrer_classicos", "🏛️ Varrer clássicos",
                      "Buscar estudos-marco por citações? Pode levar 1–2 min.")}
        </div>
        <div class="panel" style="max-width:none;margin:0">
          <h3 style="font-family:'Cormorant Garamond',Georgia,serif;font-size:23px;
                     color:var(--ouro2);margin-bottom:6px">➕ Adicionar meu estudo</h3>
          <p class="hint" style="margin-bottom:14px">Sobe o PDF (ou cola o texto). Gero o resumo
            e ele entra na <strong>fila, na frente</strong>.</p>
          <form method="post" action="/curadoria" enctype="multipart/form-data">
            <input type="hidden" name="token" value="{tok}">
            <label>PDF do estudo</label>
            <input type="file" name="pdf" accept="application/pdf"
                   style="color:var(--suave);font-family:system-ui,sans-serif;margin-bottom:14px">
            <label>…ou cole o texto/resumo (se não tiver PDF)</label>
            <textarea name="texto" rows="3" placeholder="Cole aqui o abstract do estudo…"></textarea>
            <input type="text" name="titulo" placeholder="Título (opcional)" style="width:100%;margin-bottom:10px">
            <div style="display:flex;gap:10px;flex-wrap:wrap">
              <input type="text" name="fonte" placeholder="Revista (opcional)" style="flex:1">
              <input type="text" name="doi" placeholder="DOI (opcional)" style="flex:1">
            </div>
            <button class="actbtn" type="submit" style="margin-top:14px">
              Gerar resumo e adicionar à fila</button>
          </form>
        </div>
      </details>"""


def pagina_curadoria(estado, amanha, candidatos, reserva, classicos, token,
                     aba="triagem", tema="", msg=""):
    """Bancada de triagem: faixa de estoque + o que sai amanhã + abas
    (Triagem · Reserva · Clássicos) + ferramentas recolhidas."""
    prontos = [r for r in reserva if r.get("status") == "pronto"]
    cl_cands = (classicos or {}).get("candidatos", [])
    cl_banco = (classicos or {}).get("banco", [])
    contagens = {"triagem": len(candidatos), "reserva": len(prontos), "classicos": len(cl_cands)}
    msg_html = f'<div class="infobox">{_esc(msg)}</div>' if msg else ""

    if aba == "reserva":
        corpo_aba = ("".join(_curadoria_reserva_item(r, token) for r in reserva)
                     or '<p class="hint">Reserva vazia. Priorize candidatos na Triagem — '
                        'os resumos são gerados automaticamente à noite.</p>')
    elif aba == "classicos":
        lista = "".join(_curadoria_item(c, token, "classicos", "") for c in cl_cands)
        banco = "".join(
            f'<div class="item"><div class="d">{_esc(c.get("tema"))} · '
            f'{_esc(str(c.get("citacoes", 0)))} citações</div>'
            f'<div class="t">{_esc(c.get("titulo_pt"))}</div></div>' for c in cl_banco)
        corpo_aba = (
            '<p class="hint">Estudos-marco (evergreen), ranqueados por citações. '
            'Servem de piso quando falta conteúdo fresco.</p>'
            + (lista or '<p class="hint">Nenhum clássico aguardando aprovação. '
                        'Rode <strong>🏛️ Varrer clássicos</strong> em Ferramentas.</p>')
            + (f'<div class="sectag" style="margin-top:24px">🏛️ No banco · {len(cl_banco)}</div>{banco}'
               if cl_banco else ""))
    else:
        vis = [c for c in candidatos if not tema or c.get("tema") == tema]
        corpo_aba = (_curadoria_chips(candidatos, token, tema)
                     + ("".join(_curadoria_item(c, token, "triagem", tema) for c in vis)
                        or '<p class="hint">Nada aguardando triagem aqui. A máquina segue '
                           'escolhendo e enviando sozinha — você decide às 18h.</p>'))

    corpo = f"""
    <div class="wrap">
      {_admin_nav(token, "curadoria")}
      <h2 class="disp" style="font-size:40px;color:var(--creme);margin:6px 0 10px">Curadoria</h2>
      {_curadoria_faixa(estado)}
      {_curadoria_amanha(amanha)}
      {msg_html}
      {_curadoria_abas(aba, contagens, token, tema)}
      {corpo_aba}
      {_curadoria_ferramentas(token)}
    </div>"""
    return _pagina("Curadoria", corpo, logado=True,
                   meta_extra='<meta name="robots" content="noindex">')
```

Em `app/serve.py`, **substituir** o corpo da rota GET `/curadoria` (linhas 258-268) por:

```python
        if path.startswith("/curadoria"):
            import config, db, site_web, auth_web, agenda_plan, daily, draft_store
            from datetime import datetime, timedelta
            q = up.parse_qs(up.urlparse(self.path).query)
            sess = self._sessao()
            token_ok = config.ADMIN_TOKEN and q.get("token", [""])[0] == config.ADMIN_TOKEN
            if not (token_ok or (sess and auth_web.eh_admin(sess["whatsapp"]))):
                return self._html("<h3>Acesso negado</h3>", 403)
            db.init()
            novos = db.listar_candidatos(status="novo", tipo="varredura")
            cands = novos + db.listar_candidatos(status="selecionado", tipo="varredura")
            classicos = {
                "candidatos": (db.listar_candidatos(status="novo", tipo="classico")
                               + db.listar_candidatos(status="selecionado", tipo="classico")),
                "banco": db.listar_classicos(elegiveis=False)}
            estado = agenda_plan.estado_estoque(
                db.contar_reserva_pronto(), len(novos), len(db.listar_classicos(elegiveis=True)),
                datetime.now(), daily._dias_envio(), daily.ESTOQUE_MINIMO)
            amanha = None
            try:
                d = draft_store.carregar((datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"))
                if d:
                    amanha = {"titulo": d.get("titulo_pt") or (d.get("artigo") or {}).get("titulo", ""),
                              "status": d.get("status", ""), "review_token": d.get("review_token", "")}
            except Exception as e:
                print(f"[curadoria] rascunho de amanhã falhou: {e}", flush=True)
            return self._html(site_web.pagina_curadoria(
                estado, amanha, cands, db.listar_reserva(), classicos, config.ADMIN_TOKEN,
                aba=q.get("aba", ["triagem"])[0], tema=q.get("tema", [""])[0],
                msg=q.get("msg", [""])[0]), 200)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -5`
Expected: OK, sem falhas. Se algum teste antigo de `pagina_curadoria` sobrou com a assinatura velha, atualizar para o novo `_render`.

- [ ] **Step 5: Commit**

```bash
git add app/site_web.py app/serve.py app/tests/test_site_web.py
git commit -m "feat(curadoria): página nova (abas Triagem/Reserva/Clássicos + ferramentas recolhidas)"
```

---

### Task 7: Verificação final

**Files:** nenhum (só verificação)

**Interfaces:** nenhuma.

- [ ] **Step 1: Rodar a suíte inteira**

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -5`
Expected: `OK` — nenhuma falha, nenhum erro.

- [ ] **Step 2: Conferir que o servidor sobe**

Run: `cd app && python3 -c "import serve, site_web, curadoria, daily, agenda_plan; print('IMPORTS OK')"`
Expected: `IMPORTS OK`

- [ ] **Step 3: Conferir os critérios de aceite da spec**

Percorrer a lista de "Critérios de aceite" em `docs/superpowers/specs/2026-07-26-curadoria-fluxo-design.md` e confirmar um a um. Os que não dá pra verificar sem rodar o app (4, 6, 7) ficam pro teste manual do Diego depois do deploy — anotar quais.

- [ ] **Step 4: Commit (se houve ajuste)**

```bash
git add -u app
git commit -m "test: verificação final do fluxo da curadoria"
```

---

## Notas para quem for implementar

- **Ordem importa:** Tasks 1-3 são independentes entre si e podem ir em paralelo; Task 4 e 5 criam os helpers que a Task 6 compõe, então 6 vem por último.
- **`db.marcar_candidatos(ids, status)` já existe** (`app/db.py:604`) e aceita qualquer status — não precisa de função nova pro `descartado`.
- **`descartado` já é respeitado** pelo resto do sistema: `db.listar_candidatos(status="novo")` não o retorna e `daily.materializar_agenda` só puxa `status="novo"`. Não há migração de schema nesta feature.
- **A ação POST `acao=gerar`** (gerar resumos na mão) **fica no `serve.py`** como escape hatch, só perde o botão na UI. Não remover.
- **`db.definir_selecao` fica órfã** depois da Task 5 (o único chamador era o ramo `selecionar`). **Deixar como está** — ela tem teste próprio em `app/tests/test_db.py:106` e remover só criaria churn. Isto é intencional, não é descuido: um revisor que apontar "função morta" pode ser respondido com esta nota.
- **Números de linha** foram conferidos no branch `feat/login-cpf` em 2026-07-26. Se o arquivo tiver mudado, localize pelo trecho de código citado em vez de confiar no número.
- **Não há teste de rota HTTP** neste projeto — `serve.py` é cola fina e se verifica por `import serve` + testes dos módulos que ele chama. Siga esse padrão em vez de inventar um harness de HTTP.
