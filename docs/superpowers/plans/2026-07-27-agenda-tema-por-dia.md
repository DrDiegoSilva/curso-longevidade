# Agenda — tema amarrado ao dia da semana · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trocar a rotação cíclica de temas (que deriva e não amarra nada a dia nenhum) por um mapa dia-da-semana → tema, colocando Obesidade na terça e na quinta e fazendo Longevidade e Performance alternarem na segunda.

**Architecture:** `agenda_plan.py` é o módulo de planejamento puro, sem I/O. A lógica nova entra lá como uma função pura (`tema_do_dia`), e `planejar_agenda` troca seu contador interno (`rot_i`) por uma consulta a essa função. `daily.py` só muda de qual chave da config ele lê. Nenhum estado novo, nenhuma migração de banco.

**Tech Stack:** Python 3 stdlib, `unittest` standalone, config em JSON.

**Spec:** `docs/superpowers/specs/2026-07-27-agenda-tema-por-dia-design.md`

## Global Constraints

- **`agenda_plan.py` é puro** — sem I/O, sem import de `db`/`config`. Todos os valores entram por parâmetro.
- Testes: `unittest` standalone em `app/tests/`, seguindo o cabeçalho dos arquivos existentes (`sys.path.insert` + import do módulo). Suíte completa: `cd app && python3 -m unittest discover -s tests`.
- **Não** mexer na ordem do `_rank` (`agenda_plan.py:52`): variedade → rotação → fresco → camada → nota. A variedade continua acima do mapa, de propósito.
- **Não** mexer nos `CAPS` (`curadoria.py:18`), no piso de nota, nem em `dias_envio`.
- **Não** deixar dia vazio por falta de candidato do tema preferido — `_escolher` já pega o melhor disponível e isso não muda.
- Nomes de dia usam exatamente os de `agenda_plan.DIAS` (`agenda_plan.py:11`): `segunda, terca, quarta, quinta, sexta, sabado, domingo` (sem acento).
- Commits em português, formato `<tipo>: <descrição>`.

---

### Task 1: `tema_do_dia` — a função pura

**Files:**
- Modify: `app/agenda_plan.py` (função nova, logo depois de `DIAS` na linha 11 — antes de `dias_uteis_desde`)
- Test: `app/tests/test_agenda_plan.py`

**Interfaces:**
- Consumes: `agenda_plan.DIAS` (já existe, linha 11) e `datetime` (já importado na linha 9).
- Produces: `agenda_plan.tema_do_dia(data, temas_por_dia) -> str | None`. `data` é `"YYYY-MM-DD"`; `temas_por_dia` é `{nome_do_dia: [tema, ...]}`. Devolve o tema preferido, ou `None` quando o dia não está no mapa.

Esta task é puramente aditiva: a função nasce sem chamador. Nada quebra. A Task 2 a liga.

- [ ] **Step 1: Write the failing test**

Adicionar ao fim de `app/tests/test_agenda_plan.py`, antes do `if __name__`:

```python
class TestTemaDoDia(unittest.TestCase):
    MAPA = {
        "segunda": ["Longevidade", "Performance"],
        "terca":   ["Obesidade"],
        "quarta":  ["Hormonal"],
        "quinta":  ["Obesidade"],
        "sexta":   ["Lipedema"],
    }

    def test_dia_de_tema_unico(self):
        # 2026-07-28 é terça, 2026-07-30 é quinta
        self.assertEqual(ap.tema_do_dia("2026-07-28", self.MAPA), "Obesidade")
        self.assertEqual(ap.tema_do_dia("2026-07-30", self.MAPA), "Obesidade")
        self.assertEqual(ap.tema_do_dia("2026-07-29", self.MAPA), "Hormonal")
        self.assertEqual(ap.tema_do_dia("2026-07-31", self.MAPA), "Lipedema")

    def test_alterna_entre_semanas_consecutivas(self):
        # 2026-07-27 e 2026-08-03 são segundas consecutivas
        a = ap.tema_do_dia("2026-07-27", self.MAPA)
        b = ap.tema_do_dia("2026-08-03", self.MAPA)
        self.assertIn(a, ("Longevidade", "Performance"))
        self.assertIn(b, ("Longevidade", "Performance"))
        self.assertNotEqual(a, b)

    def test_alterna_atravessando_a_virada_de_ano(self):
        # 2026-12-28 (semana ISO 53) e 2027-01-04 (semana ISO 1) são segundas
        # consecutivas com a MESMA paridade de semana ISO — a alternância não pode
        # depender de isocalendar()[1].
        a = ap.tema_do_dia("2026-12-28", self.MAPA)
        b = ap.tema_do_dia("2027-01-04", self.MAPA)
        self.assertNotEqual(a, b)

    def test_estavel_dentro_da_mesma_data(self):
        self.assertEqual(ap.tema_do_dia("2026-07-27", self.MAPA),
                         ap.tema_do_dia("2026-07-27", self.MAPA))

    def test_dia_fora_do_mapa_nao_tem_preferencia(self):
        self.assertIsNone(ap.tema_do_dia("2026-08-01", self.MAPA))   # sábado

    def test_mapa_vazio_ou_none(self):
        self.assertIsNone(ap.tema_do_dia("2026-07-28", {}))
        self.assertIsNone(ap.tema_do_dia("2026-07-28", None))

    def test_lista_vazia_no_dia(self):
        self.assertIsNone(ap.tema_do_dia("2026-07-28", {"terca": []}))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_agenda_plan.TestTemaDoDia -v`
Expected: FAIL com `AttributeError: module 'agenda_plan' has no attribute 'tema_do_dia'`

- [ ] **Step 3: Write minimal implementation**

Em `app/agenda_plan.py`, logo depois da linha `DIAS = [...]`:

```python


def tema_do_dia(data, temas_por_dia):
    """Tema preferido p/ a data (YYYY-MM-DD). Alterna a cada semana quando o dia tem
    mais de um tema. Devolve None quando o dia não está no mapa (aí não há preferência).

    A alternância usa `toordinal() // 7`, não a semana ISO: em anos de 53 semanas a
    paridade ISO repete na virada (semana 53 e semana 1 têm a mesma paridade), o que
    daria o mesmo tema em duas semanas seguidas. O ordinal é monotônico e ignora
    fronteira de ano — consultado sempre no mesmo dia da semana, o balde avança de 1
    a cada semana."""
    dt = datetime.strptime(data, "%Y-%m-%d")
    temas = (temas_por_dia or {}).get(DIAS[dt.weekday()]) or []
    return temas[(dt.toordinal() // 7) % len(temas)] if temas else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_agenda_plan -v`
Expected: PASS — os novos e todos os antigos (a Task 1 não muda comportamento nenhum).

- [ ] **Step 5: Commit**

```bash
git add app/agenda_plan.py app/tests/test_agenda_plan.py
git commit -m "feat(agenda): tema_do_dia — mapa dia-da-semana -> tema, com alternância semanal"
```

---

### Task 2: Trocar a rotação cíclica pelo mapa

**Files:**
- Modify: `app/temas_config.json:41` (troca `rotacao_semana` por `temas_por_dia`)
- Modify: `app/agenda_plan.py:69-88` (`planejar_agenda`)
- Modify: `app/daily.py:97-100` (`_rotacao` → `_temas_por_dia`) e `app/daily.py:192` (a chamada)
- Test: `app/tests/test_agenda_plan.py` (migrar 11 call sites + testes novos)

**Interfaces:**
- Consumes: `agenda_plan.tema_do_dia(data, temas_por_dia)` da Task 1.
- Produces: `agenda_plan.planejar_agenda(dias_ordenados, candidatos, temas_por_dia, tema_anterior)` — o 3º parâmetro passa a ser o dicionário, não mais uma lista. `daily._temas_por_dia() -> dict`.

Esta é a troca atômica: config, planejamento e wiring mudam juntos para a árvore nunca ficar incoerente.

- [ ] **Step 1: Write the failing test**

Em `app/tests/test_agenda_plan.py`, adicionar o helper logo depois dos helpers `_cand`/`_c` que já existem no topo do arquivo:

```python
def _todo_dia(tema):
    """Mapa que prefere o mesmo tema em qualquer dia — preserva a intenção dos testes
    que só queriam dizer 'a preferência do dia é X'."""
    return {d: [tema] for d in ap.DIAS}
```

Depois adicionar a classe nova, antes do `if __name__`:

```python
class TestPlanejarComMapa(unittest.TestCase):
    MAPA = {
        "segunda": ["Longevidade", "Performance"],
        "terca":   ["Obesidade"],
        "quarta":  ["Hormonal"],
        "quinta":  ["Obesidade"],
        "sexta":   ["Lipedema"],
    }

    def test_terca_recebe_obesidade(self):
        # 2026-07-28 é terça
        dias = [("2026-07-28", None, False)]
        cands = [_cand("Hormonal", ref_id="h"), _cand("Obesidade", ref_id="o")]
        plano = ap.planejar_agenda(dias, cands, self.MAPA, None)
        self.assertEqual(plano["2026-07-28"]["ref_id"], "o")

    def test_quinta_tambem_recebe_obesidade(self):
        # 2026-07-30 é quinta — prova que o mapa vale por dia, não por posição na fila
        dias = [("2026-07-30", None, False)]
        cands = [_cand("Lipedema", ref_id="l"), _cand("Obesidade", ref_id="o")]
        plano = ap.planejar_agenda(dias, cands, self.MAPA, None)
        self.assertEqual(plano["2026-07-30"]["ref_id"], "o")

    def test_semana_inteira_segue_o_mapa(self):
        datas = ["2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31"]
        dias = [(d, None, False) for d in datas]
        cands = ([_cand("Longevidade", ref_id="lo"), _cand("Performance", ref_id="pe")]
                 + [_cand("Obesidade", ref_id=f"ob{i}") for i in range(2)]
                 + [_cand("Hormonal", ref_id="ho"), _cand("Lipedema", ref_id="li")])
        plano = ap.planejar_agenda(dias, cands, self.MAPA, None)
        temas = [plano[d]["tema"] for d in datas]
        self.assertIn(temas[0], ("Longevidade", "Performance"))
        self.assertEqual(temas[1], "Obesidade")
        self.assertEqual(temas[2], "Hormonal")
        self.assertEqual(temas[3], "Obesidade")
        self.assertEqual(temas[4], "Lipedema")

    def test_sem_candidato_do_tema_o_dia_nao_fica_vazio(self):
        # terça pede Obesidade, mas só há Hormonal -> preenche mesmo assim
        dias = [("2026-07-28", None, False)]
        cands = [_cand("Hormonal", ref_id="h")]
        plano = ap.planejar_agenda(dias, cands, self.MAPA, None)
        self.assertEqual(plano["2026-07-28"]["ref_id"], "h")

    def test_variedade_ainda_vence_o_mapa(self):
        # terça pede Obesidade, mas o dia anterior foi Obesidade e há alternativa
        dias = [("2026-07-28", None, False)]
        cands = [_cand("Obesidade", ref_id="o"), _cand("Hormonal", ref_id="h")]
        plano = ap.planejar_agenda(dias, cands, self.MAPA, "Obesidade")
        self.assertEqual(plano["2026-07-28"]["ref_id"], "h")

    def test_mapa_vazio_ainda_preenche(self):
        dias = [("2026-07-28", None, False)]
        cands = [_cand("Hormonal", ref_id="h")]
        plano = ap.planejar_agenda(dias, cands, {}, None)
        self.assertEqual(plano["2026-07-28"]["ref_id"], "h")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_agenda_plan.TestPlanejarComMapa -v`
Expected: FAIL com `KeyError: 0`. Motivo: `planejar_agenda` ainda faz `rot[rot_i % len(rot)]`, e um dicionário não é indexável por posição — `len(MAPA)` é 5, `rot_i % 5` é 0, e `MAPA[0]` estoura. A exceção é o sinal certo: prova que o 3º parâmetro ainda é tratado como lista.

(A exceção é o esperado em 5 dos 6 testes novos. `test_mapa_vazio_ainda_preenche` passa `{}`, que é falsy, então cai no `or []` e passa mesmo antes da mudança — ele não é o teste discriminante, está ali para travar a degradação sem preferência.)

- [ ] **Step 3: Write minimal implementation**

Em `app/agenda_plan.py`, **substituir a função `planejar_agenda` inteira** (linhas 69-88) por:

```python
def planejar_agenda(dias_ordenados, candidatos, temas_por_dia, tema_anterior):
    """dias_ordenados: [(data, tema_atual|None, bloqueado)]. Retorna {data: candidato}
    só p/ os dias vazios (tema_atual None e não-bloqueado). O tema preferido de cada dia
    vem do mapa dia-da-semana (tema_do_dia), não de um contador — assim a grade não
    deriva quando um dia está fixado, pulado ou já preenchido."""
    prev = tema_anterior
    usados, plano = set(), {}
    for data, tema_atual, bloqueado in dias_ordenados:
        if bloqueado or tema_atual is not None:
            prev = tema_atual
            continue
        preferido = tema_do_dia(data, temas_por_dia)
        idx, cand = _escolher(candidatos, usados, preferido, prev)
        if cand is None:
            prev = None
            continue
        plano[data] = cand
        usados.add(idx)
        prev = cand["tema"]
    return plano
```

Em `app/agenda_plan.py`, atualizar a docstring do módulo (linhas 3-4) para não mentir sobre o mecanismo — trocar `rotação de tema como guia da vez` por `tema do dia da semana como guia`.

Em `app/temas_config.json`, **substituir a linha 41** (`"rotacao_semana": [...]`) por:

```json
  "temas_por_dia": {
    "segunda": ["Longevidade", "Performance"],
    "terca":   ["Obesidade"],
    "quarta":  ["Hormonal"],
    "quinta":  ["Obesidade"],
    "sexta":   ["Lipedema"]
  },
```

Em `app/daily.py`, **substituir a função `_rotacao`** (linhas 97-100) por:

```python
def _temas_por_dia():
    """Mapa dia-da-semana -> [temas] da config. Vazio => sem preferência de tema
    (a escolha cai para fresco > camada > nota, e nenhum dia fica vazio)."""
    return _cfg().get("temas_por_dia") or {}
```

Em `app/daily.py:192`, trocar a chamada:

```python
    plano = agenda_plan.planejar_agenda(ordenados, cands, _temas_por_dia(), None)
```

- [ ] **Step 4: Migrar os 11 call sites antigos**

Os testes existentes passam o 3º argumento como lista. Trocar, um a um, nas linhas indicadas de `app/tests/test_agenda_plan.py` (confira o número da linha antes de editar — eles andam conforme você insere o helper):

| Linha original | Antes | Depois |
|---|---|---|
| 64 | `["A", "B"]` | `{"segunda": ["A"], "terca": ["B"], "quarta": ["A"]}` |
| 73 | `["A"]` | `_todo_dia("A")` |
| 85 | `["A"]` | `_todo_dia("A")` |
| 91 | `["A"]` | `_todo_dia("A")` |
| 97 | `["A", "B"]` | `{"segunda": ["A"], "terca": ["B"]}` |
| 104 | `["A"]` | `_todo_dia("A")` |
| 111 | `["A"]` | `_todo_dia("A")` |
| 119 | `["Obesidade"]` | `_todo_dia("Obesidade")` |
| 126 | `["Obesidade"]` | `_todo_dia("Obesidade")` |
| 132 | `["Performance"]` | `_todo_dia("Performance")` |
| 146 | `["Obesidade"]` | `_todo_dia("Obesidade")` |

As duas linhas com mapa explícito (64 e 97) são as que usavam duas posições da rotação: as datas ali são 2026-07-27 (segunda), 28 (terça) e 29 (quarta), então o mapa acima preserva o que cada teste queria dizer.

**Não altere as asserções.** Se algum teste passar a falhar depois da migração, isso é sinal de mudança de comportamento — pare e reporte em vez de ajustar a asserção.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -5`
Expected: `OK`, sem falhas.

Depois confirme que a chave velha sumiu de vez:

Run: `cd app && grep -rn "rotacao_semana\|_rotacao" . --include="*.py" --include="*.json"`
Expected: nenhuma saída.

- [ ] **Step 6: Commit**

```bash
git add app/agenda_plan.py app/daily.py app/temas_config.json app/tests/test_agenda_plan.py
git commit -m "feat(agenda): tema por dia da semana no lugar da rotação cíclica (Obesidade ter+qui)"
```

---

### Task 3: Verificação final

**Files:** nenhum (só verificação)

**Interfaces:** nenhuma.

- [ ] **Step 1: Suíte completa**

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -5`
Expected: `OK`. Registre a contagem.

- [ ] **Step 2: Imports**

Run: `cd app && python3 -c "import serve, daily, agenda_plan, site_web; print('IMPORTS OK')"`
Expected: `IMPORTS OK`

- [ ] **Step 3: Simular uma semana de verdade com a config real**

Run:

```bash
cd app && python3 -c "
import json, agenda_plan as ap
mapa = json.load(open('temas_config.json'))['temas_por_dia']
datas = ['2026-07-27','2026-07-28','2026-07-29','2026-07-30','2026-07-31',
         '2026-08-03','2026-08-04','2026-08-05','2026-08-06','2026-08-07']
DIA = ['seg','ter','qua','qui','sex','sab','dom']
from datetime import datetime
for d in datas:
    wd = DIA[datetime.strptime(d,'%Y-%m-%d').weekday()]
    print(d, wd, '->', ap.tema_do_dia(d, mapa))
"
```

Expected: terça e quinta das duas semanas = `Obesidade`; quarta = `Hormonal`; sexta = `Lipedema`; e as duas segundas com temas **diferentes** entre `Longevidade` e `Performance`.

Cole a saída no relatório — é a evidência do critério de aceite 3.

- [ ] **Step 4: Percorrer os critérios de aceite**

Ler a seção "Critérios de aceite" de `docs/superpowers/specs/2026-07-27-agenda-tema-por-dia-design.md` (são 6) e dizer, para cada um, ✅ / ❌ / ⚠️ (só verificável rodando o app), com a evidência (`arquivo:linha` ou nome do teste). Não marcar ✅ o que você só conseguiu inferir.

- [ ] **Step 5: Commit (só se algo mudou)**

Esta task normalmente não altera arquivo. Se não alterou, não commite e diga isso no relatório.

---

## Notas para quem for implementar

- **`tema_do_dia` é consultada por DATA, não por posição na fila.** É isso que mata a deriva: dia fixado, pulado ou já preenchido não desloca mais nada, porque não existe mais contador.
- **A ordem do `_rank` não muda.** Variedade continua acima da rotação — se o dia anterior teve o mesmo tema que o mapa pede, a variedade ganha. É intencional e há teste para isso (`test_variedade_ainda_vence_o_mapa`).
- **Não há migração de banco nem de estado.** A config viaja junto com o código no deploy.
- **Datas de referência usadas nos testes:** 2026-07-27 é segunda, 28 terça, 29 quarta, 30 quinta, 31 sexta, 2026-08-01 sábado. 2026-12-28 e 2027-01-04 são segundas consecutivas que cruzam a virada de ano (2026 tem 53 semanas ISO).
- **Números de linha** conferidos em 2026-07-27 no branch `feat/agenda-tema-por-dia` (base `main` = `6b72d25`). Se o arquivo tiver mudado, localize pelo trecho de código citado.
