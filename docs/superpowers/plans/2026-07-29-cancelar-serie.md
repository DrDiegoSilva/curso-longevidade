# Cancelar série — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Botão que desfaz a ativação de uma série — libera os dias futuros ainda não preparados (estudo volta ao estoque), mantém os já enviados, e devolve a série pra `rascunho` pronta pra reativar na data certa.

**Architecture:** Uma função de domínio nova em `series.py` (`cancelar_serie`) faz todo o trabalho e devolve `(ok, msg)`, no mesmo formato de `ativar_serie`. A rota `/series` ganha duas ações (confirmação em duas etapas) e `pagina_series` ganha o botão. Um bug pré-existente de `db.agenda_devolver` (não trata `candidato`) entra primeiro, porque cancelar depende dele.

**Tech Stack:** Python 3 stdlib, SQLite + Postgres via `db._Wrap`, `unittest`. Sem framework.

**Spec:** `docs/superpowers/specs/2026-07-29-cancelar-serie-design.md`

## Global Constraints

- **Worktree:** `/Users/diegosilva/dev/curso-longevidade/.claude/worktrees/cancelar-serie`, branch `feat/cancelar-serie`, base main `a45c747`. Testes: `cd app && python3 -m unittest discover -s tests`. **Baseline: 847 testes verdes.**
- **Repo multi-agente:** stagear só os arquivos da task; **nunca** `git add -A`.
- **TDD com prova por mutação:** teste primeiro, RED pelo motivo certo, fix, GREEN, e depois reverter o fix no scratch pra confirmar que o teste fica vermelho. Suíte verde não é evidência.
- **Gate 18h intacto:** cancelar não toca em `daily.preparar_18h`, rotação nem materialização.
- **Fail-safe:** liberação dia-a-dia em `try/except`; falha parcial **avisa** no `msg`, nunca fica silenciosa. Devolve o estudo ao estoque **antes** de limpar o slot (`db.agenda_devolver` já faz nessa ordem).
- **Admin-gated:** as ações novas entram no bloco `/series` do `do_POST` que já checa `token_ok or (sess and auth_web.eh_admin(...))`. Não criar gate novo.
- **Nunca devolver estudo às cegas:** só libera o dia se `agenda_slot(dia)["ref_id"]` ainda for o `ref_id` do item. Senão o estudo voltaria pro estoque estando ainda agendado = duplicado.
- **Dias que NÃO são liberados mantêm a `data` no item** (ela é verdade — o estudo continua lá). Só os liberados têm a `data` limpa. Reativar depois é seguro: `ativar_serie` reatribui todas as datas, e `_indisponiveis` recusa corretamente um ref que ainda esteja agendado.
- Sem push, sem deploy.

## File Structure

- `app/db.py` — **modificar**: `agenda_devolver` passa a tratar `tipo == "candidato"`.
- `app/series.py` — **modificar**: nova `cancelar_serie`.
- `app/serve.py` — **modificar**: ações `cancelar` e `cancelar_confirmar` no POST `/series`; GET passa `confirmar_cancelar` pra página.
- `app/site_web.py` — **modificar**: `pagina_series` ganha o parâmetro `confirmar_cancelar` e o botão 🚫.
- `app/tests/test_series.py` — **modificar**: novas classes de teste.

---

### Task 1: `db.agenda_devolver` trata `candidato`

**Files:**
- Modify: `app/db.py` (`agenda_devolver`, ~linha 1410)
- Test: `app/tests/test_series.py` (nova classe)

**Interfaces:**
- Consumes: `db.marcar_candidato_pronto(cid)` (db.py:1018), `db.agenda_slot`, `db.agenda_upsert`.
- Produces: `db.agenda_devolver(data)` passa a devolver candidato ao estoque. `series.cancelar_serie` (Task 2) depende disso.

**Contexto:** hoje `agenda_devolver` trata `reserva` e `fila` mas ignora `candidato` — o slot é limpo e o candidato **nunca volta** pro estoque. `series._liberar_dia` trata os três, então a inconsistência é do `db`. Efeito colateral atual: `agenda_pular` num dia de candidato vaza o candidato.

- [ ] **Step 1: Write the failing test** — em `app/tests/test_series.py`:

```python
class TestAgendaDevolverCandidato(unittest.TestCase):
    def setUp(self):
        self._env = _snapshot_env()
        _restore_db()

    def tearDown(self):
        _restore_db(self._env)

    def test_devolver_dia_de_candidato_volta_ao_estoque(self):
        import db
        db.init()
        cid = db.salvar_candidato({"tema": "Obesidade", "titulo_pt": "C1", "resumo": "r"})
        db.marcar_candidato_agendado(cid)
        db.agenda_upsert("2026-08-10", tipo="candidato", ref_id=cid, titulo="C1")

        db.agenda_devolver("2026-08-10")

        self.assertEqual(db.agenda_slot("2026-08-10")["tipo"], "vazio")
        cand = db.obter_candidato(cid)
        self.assertEqual(cand["status"], "novo",
                         "candidato tem que voltar pro estoque, senão vaza")

    def test_devolver_preserva_fixado(self):
        import db
        db.init()
        cid = db.salvar_candidato({"tema": "Obesidade", "titulo_pt": "C2", "resumo": "r"})
        db.marcar_candidato_agendado(cid)
        db.agenda_upsert("2026-08-11", tipo="candidato", ref_id=cid, titulo="C2", fixado=1)

        db.agenda_devolver("2026-08-11")

        self.assertEqual(db.agenda_slot("2026-08-11")["fixado"], 1)
```

**Antes de escrever:** confirme os nomes reais lendo `db.py` — `salvar_candidato`, `marcar_candidato_agendado`, `obter_candidato` (db.py:965) e o status que `marcar_candidato_pronto` grava (o teste espera `"novo"`; se o código usa outro rótulo, use o do código e diga no report). Confirme também que `_snapshot_env`/`_restore_db` existem no arquivo de teste (foram criados na Fase 2 pra evitar poison de `db._INITED`).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_series.TestAgendaDevolverCandidato -v`
Expected: `test_devolver_dia_de_candidato_volta_ao_estoque` FALHA porque o candidato fica `agendado` (o slot vira `vazio`, mas o estoque não recebe de volta). `test_devolver_preserva_fixado` já deve passar (o `fixado` já é preservado) — é teste de regressão pra não quebrar isso no fix.

- [ ] **Step 3: Write minimal implementation** — em `app/db.py`, dentro de `agenda_devolver`, adicionar o ramo de candidato entre o de `reserva` e o de `fila`:

```python
    if s.get("tipo") == "reserva" and s.get("ref_id"):
        marcar_reserva_pronto(s["ref_id"])
    elif s.get("tipo") == "candidato" and s.get("ref_id"):
        marcar_candidato_pronto(s["ref_id"])
    elif s.get("tipo") == "fila" and s.get("payload"):
```

Atualize o docstring: ele hoje lista os tipos tratados e passa a incluir candidato.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_series.TestAgendaDevolverCandidato -v`
Expected: PASS (2 testes). Depois rode a suíte inteira: `cd app && python3 -m unittest discover -s tests` → 847 + 2 = **849**, OK.

- [ ] **Step 5: Prove by mutation**

Reverta o `elif` do candidato no scratch, rode a classe, confirme RED com o candidato em `agendado`, restaure. Registre no report.

- [ ] **Step 6: Commit**

```bash
git add app/db.py app/tests/test_series.py
git commit -m "fix(agenda): agenda_devolver devolve candidato ao estoque (fecha vazamento do agenda_pular)"
```

---

### Task 2: `series.cancelar_serie`

**Files:**
- Modify: `app/series.py` (função nova)
- Test: `app/tests/test_series.py` (nova classe)

**Interfaces:**
- Consumes: `db.obter_serie(serie_id)` → `{"serie": dict, "itens": [dict]}` (itens têm `id`, `ref_tipo`, `ref_id`, `data`, `titulo`); `db.agenda_slot(dia)` → dict com `tipo`/`ref_id`/`fixado` ou `None`; `db.agenda_devolver(dia)` (Task 1); `db.set_serie_item_data(item_id, data)`; `db.atualizar_serie(serie_id, **campos)` (whitelist: `nome`/`status`/`data_inicio`/`ativada_em`); `draft_store.carregar(dia)`.
- Produces: `series.cancelar_serie(serie_id, db_mod=None, hoje=None, preparado_fn=None) -> (bool, str)`. Task 3 consome no `serve.py`.

- [ ] **Step 1: Write the failing test** — em `app/tests/test_series.py`:

```python
def _segunda_futura(dias=14):
    """Uma segunda-feira a pelo menos ~8 dias de hoje. Data COMPUTADA, não fixa:
    data fixa apodrece (o piso de `ativar_serie` recusa data passada, então um
    '2026-08-10' cravado passa a falhar sozinho depois daquela data)."""
    from datetime import date, timedelta
    base = date.today() + timedelta(days=dias)
    return (base - timedelta(days=base.weekday())).isoformat()


class TestCancelarSerie(unittest.TestCase):
    DIAS_UTEIS = ["segunda", "terca", "quarta", "quinta", "sexta"]

    def setUp(self):
        self._env = _snapshot_env()
        _restore_db()
        self.hoje = __import__("datetime").date.today().isoformat()

    def tearDown(self):
        _restore_db(self._env)

    def _serie_ativa(self, n=3, inicio=None):
        """Série ativa com n reservas em n dias úteis seguidos a partir de inicio."""
        import db, series
        inicio = inicio or _segunda_futura()
        db.init()
        sid = db.criar_serie("S")
        for i in range(n):
            rid = db.salvar_reserva({"tema": "Obesidade", "titulo_pt": f"R{i}",
                                     "resumo": "r", "tags": ["glp1"]})
            db.adicionar_serie_item(sid, "reserva", rid, titulo=f"R{i}", tema="Obesidade")
        ok, msg = series.ativar_serie(sid, inicio, db_mod=db, dias_envio=self.DIAS_UTEIS)
        self.assertTrue(ok, f"setup falhou: {msg}")
        return sid

    def test_libera_dias_futuros_e_devolve_estudos(self):
        import db, series
        sid = self._serie_ativa(n=3)
        dias = [it["data"] for it in db.obter_serie(sid)["itens"]]

        ok, msg = series.cancelar_serie(sid, db_mod=db, hoje=self.hoje,
                                        preparado_fn=lambda d: False)

        self.assertTrue(ok, msg)
        for d in dias:
            self.assertEqual(db.agenda_slot(d)["tipo"], "vazio", f"{d} devia estar livre")
        for it in db.obter_serie(sid)["itens"]:
            self.assertEqual(it["data"], "", "item liberado perde a data")
            self.assertEqual(db.obter_reserva(it["ref_id"])["status"], "pronto",
                             "estudo tem que voltar pro estoque")
        self.assertEqual(db.obter_serie(sid)["serie"]["status"], "rascunho")

    def test_mantem_dia_passado_e_de_hoje(self):
        import db, series
        sid = self._serie_ativa(n=3)
        dias = sorted(it["data"] for it in db.obter_serie(sid)["itens"])

        # hoje = o 2º dia: o 1º é passado, o 2º é hoje, só o 3º é futuro
        ok, msg = series.cancelar_serie(sid, db_mod=db, hoje=dias[1],
                                        preparado_fn=lambda d: False)

        self.assertTrue(ok, msg)
        self.assertNotEqual(db.agenda_slot(dias[0])["tipo"], "vazio", "passado fica")
        self.assertNotEqual(db.agenda_slot(dias[1])["tipo"], "vazio", "hoje fica")
        self.assertEqual(db.agenda_slot(dias[2])["tipo"], "vazio", "futuro sai")

    def test_nao_libera_dia_com_rascunho_pronto_e_avisa(self):
        import db, series
        sid = self._serie_ativa(n=2)
        dias = sorted(it["data"] for it in db.obter_serie(sid)["itens"])

        ok, msg = series.cancelar_serie(sid, db_mod=db, hoje=self.hoje,
                                        preparado_fn=lambda d: d == dias[0])

        self.assertTrue(ok, msg)
        self.assertNotEqual(db.agenda_slot(dias[0])["tipo"], "vazio")
        self.assertEqual(db.agenda_slot(dias[1])["tipo"], "vazio")
        self.assertIn("rascunho", msg.lower(), f"o admin tem que ser avisado: {msg}")

    def test_nao_mexe_em_dia_que_ja_e_de_outro_estudo(self):
        import db, series
        sid = self._serie_ativa(n=1)
        it = db.obter_serie(sid)["itens"][0]
        dia = it["data"]
        # alguém trocou o dia (Item 23 / edição manual): o slot não é mais do item
        outra = db.salvar_reserva({"tema": "Obesidade", "titulo_pt": "OUTRA", "resumo": "r"})
        db.agenda_upsert(dia, tipo="reserva", ref_id=outra, titulo="OUTRA")

        ok, msg = series.cancelar_serie(sid, db_mod=db, hoje=self.hoje,
                                        preparado_fn=lambda d: False)

        self.assertTrue(ok, msg)
        self.assertEqual(db.agenda_slot(dia)["ref_id"], outra, "não mexe no dia alheio")
        self.assertEqual(db.obter_reserva(it["ref_id"])["status"], "agendado",
                         "não devolve às cegas — duplicaria o estudo no estoque")

    def test_serie_presa_ativa_sem_datas_volta_a_rascunho(self):
        """O caso grave: hoje esse estado só sai editando o banco."""
        import db, series
        db.init()
        sid = db.criar_serie("Presa")
        db.atualizar_serie(sid, status="ativa")

        ok, msg = series.cancelar_serie(sid, db_mod=db, hoje=self.hoje,
                                        preparado_fn=lambda d: False)

        self.assertTrue(ok, msg)
        self.assertEqual(db.obter_serie(sid)["serie"]["status"], "rascunho")

    def test_recusa_rascunho_e_concluida(self):
        import db, series
        db.init()
        sid = db.criar_serie("R")
        ok, msg = series.cancelar_serie(sid, db_mod=db)
        self.assertFalse(ok)
        self.assertIn("rascunho", msg.lower())

        db.atualizar_serie(sid, status="concluida")
        ok2, msg2 = series.cancelar_serie(sid, db_mod=db)
        self.assertFalse(ok2)

    def test_falha_por_dia_avisa_e_nao_fica_silenciosa(self):
        import db, series
        sid = self._serie_ativa(n=2)
        dias = sorted(it["data"] for it in db.obter_serie(sid)["itens"])
        real = db.agenda_devolver

        def devolver_quebrado(dia):
            if dia == dias[0]:
                raise RuntimeError("boom")
            return real(dia)

        db.agenda_devolver = devolver_quebrado
        try:
            ok, msg = series.cancelar_serie(sid, db_mod=db, hoje=self.hoje,
                                            preparado_fn=lambda d: False)
        finally:
            db.agenda_devolver = real

        self.assertIn(dias[0], msg, f"o dia que falhou tem que aparecer: {msg}")
        self.assertEqual(db.agenda_slot(dias[1])["tipo"], "vazio",
                         "uma falha não impede os outros dias")

    def test_cancelar_libera_a_proxima_ativacao(self):
        """Fecha o ciclo: ativei na data errada -> cancelo -> ativo na certa."""
        import db, series
        sid = self._serie_ativa(n=2)
        ok, _ = series.cancelar_serie(sid, db_mod=db, hoje=self.hoje,
                                      preparado_fn=lambda d: False)
        self.assertTrue(ok)

        nova = _segunda_futura(dias=21)
        ok2, msg2 = series.ativar_serie(sid, nova, db_mod=db, dias_envio=self.DIAS_UTEIS)

        self.assertTrue(ok2, msg2)
        datas = sorted(it["data"] for it in db.obter_serie(sid)["itens"])
        self.assertEqual(datas[0], nova, "reativou na data nova")
```

**Antes de escrever:** confirme nos fontes os nomes `db.obter_reserva`, `db.salvar_candidato`, e o status que `marcar_reserva_pronto` grava (o teste espera `"pronto"`). Confirme a assinatura de `db.agenda_upsert` (db.py:1386) pros kwargs usados. Se algum nome divergir, use o do código e registre no report.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_series.TestCancelarSerie -v`
Expected: todos FALHAM com `AttributeError: module 'series' has no attribute 'cancelar_serie'`.

- [ ] **Step 3: Write minimal implementation** — em `app/series.py`:

```python
def cancelar_serie(serie_id, db_mod=None, hoje=None, preparado_fn=None):
    """Desfaz a ativação: libera os dias FUTUROS ainda não preparados (o estudo volta
    ao estoque e o slot vira 'vazio') e devolve a série pra 'rascunho', pronta pra ser
    reativada com outra data. Retorna (ok, msg).

    NÃO libera: dia de hoje ou passado (o envio das 08h já passou — não existe
    des-enviar) nem dia cujo rascunho das 18h já foi montado (ele seria enviado de
    qualquer forma, então limpar o slot daria impressão falsa — mesma limitação que
    justifica `dia_minimo_inicio`). Nem dia cujo slot já é de OUTRO estudo: devolver
    às cegas duplicaria o estudo no estoque.

    Não crasha: falha por dia é contada e avisada no msg, nunca engolida.
    """
    if db_mod is None:
        import db as db_mod
    if preparado_fn is None:
        import draft_store
        preparado_fn = lambda d: draft_store.carregar(d) is not None
    hoje = hoje or date.today().isoformat()

    det = db_mod.obter_serie(serie_id)
    if not det:
        return (False, "Série não encontrada.")
    st = (det["serie"].get("status") or "")
    if st not in ("ativa", "incompleta"):
        return (False, f"Só dá pra cancelar série ativa ou incompleta (esta está '{st}').")

    liberados = passados = preparados = alheios = 0
    falhas = []
    for it in det["itens"]:
        dia = it.get("data") or ""
        if not dia:
            continue
        if dia <= hoje:
            passados += 1
            continue
        if preparado_fn(dia):
            preparados += 1
            continue
        try:
            slot = db_mod.agenda_slot(dia)
            if not slot or (slot.get("ref_id") or "") != (it.get("ref_id") or ""):
                alheios += 1
                continue
            db_mod.agenda_devolver(dia)          # devolve ao estoque ANTES de limpar
            db_mod.set_serie_item_data(it["id"], "")
            liberados += 1
        except Exception as e:
            print(f"[series] cancelar: falhou liberar {dia}: {e}", flush=True)
            falhas.append(dia)

    try:
        db_mod.atualizar_serie(serie_id, status="rascunho", data_inicio="", ativada_em="")
    except Exception as e:
        print(f"[series] cancelar: não devolvi a série {serie_id} pra rascunho: {e}", flush=True)
        return (False, f"Os {liberados} dia(s) foram liberados, mas a série NÃO voltou pra "
                       f"rascunho ({e}) — ela vai continuar bloqueando a próxima ativação. "
                       f"Confira a /series.")

    mantidos = []
    if passados:
        mantidos.append(f"{passados} já enviado(s)")
    if preparados:
        mantidos.append(f"{preparados} com rascunho das 18h pronto")
    if alheios:
        mantidos.append(f"{alheios} já ocupado(s) por outro estudo")
    msg = f"Série cancelada: {liberados} dia(s) liberado(s)"
    if mantidos:
        msg += f", mantido(s) {' + '.join(mantidos)}"
    msg += "."
    if liberados:
        msg += " Os estudos voltaram pro estoque."
    if falhas:
        msg += (f" ATENÇÃO: falhou liberar {', '.join(falhas)} — confira a /agenda "
                f"(detalhe nos logs).")
    return (True, msg)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_series.TestCancelarSerie -v`
Expected: PASS (8 testes). Suíte inteira: **849 + 8 = 857**, OK.

- [ ] **Step 5: Prove by mutation**

Um por um, no scratch: (a) trocar `dia <= hoje` por `dia < hoje` → o teste de "hoje fica" fica vermelho; (b) remover a checagem do `preparado_fn` → o teste do rascunho pronto fica vermelho; (c) remover a comparação de `ref_id` → o teste do dia alheio fica vermelho; (d) tirar o `try/except` do loop → o teste de falha parcial fica vermelho. Restaure cada um. Registre no report.

- [ ] **Step 6: Commit**

```bash
git add app/series.py app/tests/test_series.py
git commit -m "feat(series): cancelar_serie (libera dias futuros, devolve estudos, volta pra rascunho)"
```

---

### Task 3: rota + botão com confirmação em duas etapas

**Files:**
- Modify: `app/serve.py` (POST `/series`: `cancelar` e `cancelar_confirmar`; GET `/series`: passa `confirmar_cancelar`)
- Modify: `app/site_web.py` (`pagina_series`: parâmetro novo + botão)
- Test: `app/tests/test_series.py` (adicionar à classe `TestRotaSeries` existente e à `TestPaginaSeries`)

**Interfaces:**
- Consumes: `series.cancelar_serie` (Task 2); `site_web.pagina_series(ctx, token, serie_aberta_id="", dia_min="", msg="")` — ganha o kwarg `confirmar_cancelar=""`.
- Produces: nada que outra task consuma (é a última).

**Padrão a seguir:** o `/admin` já faz confirmação em duas etapas pra remover assinante — `acao=remover` renderiza a confirmação via query param, `acao=remover_confirmar` executa (ver `site_web.pagina_admin(..., confirmar_id=...)` em site_web.py:973 e `serve.py` no bloco `/admin`). Espelhe isso.

- [ ] **Step 1: Write the failing test** — adicione em `app/tests/test_series.py`:

```python
    def test_pagina_mostra_botao_cancelar_na_serie_ativa(self):
        import site_web
        ctx = {"series": [{"id": "s1", "nome": "S", "status": "ativa"}],
               "aberta": {"serie": {"id": "s1", "nome": "S", "status": "ativa"},
                          "itens": [{"id": "i1", "ref_tipo": "reserva", "ref_id": "r1",
                                     "titulo": "R1", "data": "2026-08-10"}]},
               "resultados": []}
        html = site_web.pagina_series(ctx, "TK")
        self.assertIn("cancelar", html)
        self.assertIn("🚫", html)

    def test_pagina_nao_mostra_cancelar_em_rascunho(self):
        import site_web
        ctx = {"series": [{"id": "s1", "nome": "S", "status": "rascunho"}],
               "aberta": {"serie": {"id": "s1", "nome": "S", "status": "rascunho"},
                          "itens": []},
               "resultados": []}
        html = site_web.pagina_series(ctx, "TK")
        self.assertNotIn("🚫", html)

    def test_pagina_confirmacao_pede_confirmar_e_diz_o_efeito(self):
        import site_web
        ctx = {"series": [{"id": "s1", "nome": "S", "status": "ativa"}],
               "aberta": {"serie": {"id": "s1", "nome": "S", "status": "ativa"},
                          "itens": [{"id": "i1", "ref_tipo": "reserva", "ref_id": "r1",
                                     "titulo": "R1", "data": "2026-08-10"}]},
               "resultados": []}
        html = site_web.pagina_series(ctx, "TK", confirmar_cancelar="s1")
        self.assertIn("cancelar_confirmar", html)
```

E na `TestRotaSeries` existente (ela já tem o stub MRO via `self.Stub = _make_stub_cls()`, `ADMIN_TOKEN = "segredo-teste"` e `self.db` recarregado num tmp — **reuse tudo, não crie outro stub**):

```python
    def test_post_cancelar_confirmar_sem_token_nem_sessao_403(self):
        stub = self.Stub("/series", body=b"acao=cancelar_confirmar&serie=s1")
        code, _ = stub.do_POST()
        self.assertEqual(code, 403)

    def test_post_cancelar_mostra_confirmacao_sem_cancelar_nada(self):
        """`acao=cancelar` é só a etapa 1: redireciona pedindo confirmação e
        NÃO pode mexer na série (senão a confirmação seria decorativa)."""
        import series
        sid = self._ativa_uma()
        body = f"acao=cancelar&serie={sid}&token=segredo-teste".encode()
        stub = self.Stub("/series", body=body)

        tag, location = stub.do_POST()

        self.assertEqual(tag, "REDIRECT")
        self.assertIn("confirmar_cancelar=", location)
        self.assertEqual(self.db.obter_serie(sid)["serie"]["status"], "ativa",
                         "etapa 1 não cancela")

    def test_post_cancelar_confirmar_devolve_serie_pra_rascunho(self):
        sid = self._ativa_uma()
        body = f"acao=cancelar_confirmar&serie={sid}&token=segredo-teste".encode()
        stub = self.Stub("/series", body=body)

        tag, location = stub.do_POST()

        self.assertEqual(tag, "REDIRECT")
        self.assertTrue(location.startswith("/series?"))
        self.assertIn("msg=", location, "o resultado tem que chegar ao admin")
        self.assertEqual(self.db.obter_serie(sid)["serie"]["status"], "rascunho")

    def _ativa_uma(self):
        """Série ativa com 1 reserva, começando numa segunda futura."""
        import series
        from datetime import date, timedelta
        base = date.today() + timedelta(days=14)
        inicio = (base - timedelta(days=base.weekday())).isoformat()
        sid = self.db.criar_serie("S")
        rid = self.db.salvar_reserva({"tema": "Obesidade", "titulo_pt": "R0",
                                      "resumo": "r", "tags": ["glp1"]})
        self.db.adicionar_serie_item(sid, "reserva", rid, titulo="R0", tema="Obesidade")
        ok, msg = series.ativar_serie(sid, inicio, db_mod=self.db,
                                      dias_envio=["segunda", "terca", "quarta",
                                                  "quinta", "sexta"])
        self.assertTrue(ok, f"setup falhou: {msg}")
        return sid
```

**Nota de integração:** `serve.py` chama `series.cancelar_serie(sid)` **sem** `db_mod`, então a função faz `import db as db_mod` — e pega o módulo recarregado que `_reload_db(self.tmp)` pôs em `sys.modules`. É o mesmo mecanismo que faz `test_post_criar_cria_serie_e_redireciona` poder checar `self.db.listar_series()`. Se ao rodar isso o banco parecer vazio, é sinal de que o reload não está pegando — investigue em vez de contornar com mock.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_series.TestPaginaSeries tests.test_series.TestRotaSeries -v`
Expected: os novos FALHAM — `pagina_series` não aceita `confirmar_cancelar` (TypeError) e não emite `🚫`; a rota ignora `acao=cancelar_confirmar` e não muda o status.

- [ ] **Step 3: Write minimal implementation**

**3a. `site_web.pagina_series`** — adicione `confirmar_cancelar=""` na assinatura (último kwarg, pra não quebrar chamador posicional). No bloco do montador, onde `st` é o status da série aberta, depois da lista de itens:

```python
        cancelar_html = ""
        if st in ("ativa", "incompleta"):
            if str(confirmar_cancelar) == str(aberta["serie"]["id"]):
                n_dias = sum(1 for i in aberta.get("itens", []) if i.get("data"))
                cancelar_html = (
                    f'<div style="margin:12px 0;padding:10px;border:1px solid var(--ouro2)">'
                    f'<p>Cancelar libera os dias <b>futuros</b> ({n_dias} dia(s) marcado(s)) e '
                    f'devolve os estudos pro estoque. Dias já enviados ficam como estão. '
                    f'A série volta pra rascunho.</p>'
                    f'<form method="post" action="/series" style="display:inline">'
                    f'<input type="hidden" name="acao" value="cancelar_confirmar">'
                    f'<input type="hidden" name="token" value="{tk}">'
                    f'<input type="hidden" name="serie" value="{sid}">'
                    f'<button type="submit">🚫 Confirmar cancelamento</button></form>'
                    f'&nbsp;<a href="/series?serie={sid}&token={tk}">Voltar</a></div>')
            else:
                cancelar_html = (
                    f'<form method="post" action="/series" style="display:inline">'
                    f'<input type="hidden" name="acao" value="cancelar">'
                    f'<input type="hidden" name="token" value="{tk}">'
                    f'<input type="hidden" name="serie" value="{sid}">'
                    f'<button type="submit">🚫 Cancelar série</button></form>')
```

Depois inclua `cancelar_html` no HTML montado (junto de onde os outros forms da série aberta entram). **Confirme lendo a função** onde `montador` é composto e insira lá; todo valor interpolado tem que passar por `_esc` (note que `sid` e `tk` já vêm escapados no código existente).

**3b. `serve.py`, POST `/series`** — adicione ao dispatch de `acao`, junto das outras:

```python
            elif acao == "cancelar":
                import urllib.parse as _up
                return self._redirect(
                    f"/series?serie={_up.quote(sid)}&token={config.ADMIN_TOKEN}"
                    f"&confirmar_cancelar={_up.quote(sid)}")
            elif acao == "cancelar_confirmar":
                ok, msg = series.cancelar_serie(sid)
```

**3c. `serve.py`, GET `/series`** — passe o novo param pra página:

```python
            return self._html(site_web.pagina_series(
                ctx, config.ADMIN_TOKEN or "", serie_aberta_id=sid or "",
                dia_min=dia_min, msg=q.get("msg", [""])[0],
                confirmar_cancelar=q.get("confirmar_cancelar", [""])[0]))
```

**Leia o GET atual antes de editar** — a chamada existente pode ter mudado; preserve os argumentos que já estão lá e só acrescente o novo.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_series -v`
Expected: PASS. Suíte inteira: `cd app && python3 -m unittest discover -s tests` → **857 + 5 = 862**, OK, saída limpa.

- [ ] **Step 5: Prove by mutation**

No scratch: remova o ramo `cancelar_confirmar` do `serve.py` → o teste de rota fica vermelho; troque a condição `st in ("ativa","incompleta")` por `st == "rascunho"` → o teste do botão fica vermelho. Restaure. Registre no report.

- [ ] **Step 6: Commit**

```bash
git add app/serve.py app/site_web.py app/tests/test_series.py
git commit -m "feat(series): botao 🚫 Cancelar serie (confirmacao em 2 etapas) + rota"
```

---

## Notas de execução

- **Contagem de testes:** baseline 847 → Task 1: 849 → Task 2: 857 → Task 3: 863 (3 de página + 3 de rota). Se der outro número, investigue antes de commitar em vez de ajustar a expectativa.
- **Nomes a confirmar contra o código** (não são lacunas de design, são checagens de integração): `db.salvar_candidato` / `marcar_candidato_agendado` / `obter_candidato` / `obter_reserva`; o status que `marcar_reserva_pronto` e `marcar_candidato_pronto` gravam; os kwargs de `db.agenda_upsert`; os helpers `_snapshot_env`/`_restore_db` do arquivo de teste; e o stub `_SeriesRotaStub` da `TestRotaSeries`.
- **Fora de escopo:** cancelar dia individual, desfazer envio, rodar `reconciliar` de noite, reordenar série ativada.

## Self-Review (checklist do autor)

- **Cobertura do spec:** dias futuros liberados + estudo ao estoque (Task 2) ✓; passado/hoje mantidos (Task 2) ✓; rascunho das 18h mantido **e avisado** (Task 2) ✓; dia alheio não mexido nem devolvido (Task 2) ✓; `fixado` preservado (Task 1, via `agenda_devolver`) ✓; candidato devolvido (Task 1) ✓; série presa cancelável (Task 2) ✓; `incompleta` cancelável / `concluida`+`rascunho` recusadas (Task 2) ✓; fail-safe por dia com aviso (Task 2) ✓; rota gateada + confirmação em 2 etapas (Task 3) ✓; regressão do ciclo completo ativar-errado → cancelar → reativar (Task 2, `test_cancelar_libera_a_proxima_ativacao`) ✓.
- **Consistência de tipos:** `cancelar_serie` devolve `(bool, str)` — igual `ativar_serie`, consumido como `ok, msg` no `serve.py`. `obter_serie` devolve `{"serie","itens"}` em todos os consumidores. `agenda_slot` devolve dict ou `None` — o código checa `if not slot`.
- **Sem placeholders:** varri o plano — nenhum `...`, TBD ou "igual à Task N". Os 3 testes de rota da Task 3 estão escritos por extenso (a primeira versão deste plano os deixou como `...` com uma justificativa; era placeholder disfarçado e foi corrigido).
- **Datas computadas, não cravadas:** as datas de ativação vêm de `_segunda_futura()` / do helper `_ativa_uma`, porque `ativar_serie` recusa data passada — uma data fixa faria o teste falhar sozinho no futuro. As datas cravadas que sobraram são chaves de dia em chamadas diretas à agenda (sem validação) e um campo de string num ctx de render: não apodrecem.
- **Ordem das tasks:** Task 1 antes de Task 2 não é arbitrário — `cancelar_serie` usa `agenda_devolver` e precisa que ela devolva candidato, senão cancelar um dia de candidato vaza o estudo.
