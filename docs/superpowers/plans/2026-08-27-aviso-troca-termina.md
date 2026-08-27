# Aviso quando a troca do estudo de amanhã termina — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A tela "🔄 Trocando…" (depois de escolher um estudo novo no picker do 🔁) passa a avisar sozinha, ao vivo, quando a troca terminou — sucesso (com o link novo de revisão) ou erro — sem precisar checar o WhatsApp.

**Architecture:** O estado da troca fica gravado no MESMO rascunho já persistido em `daily_drafts` (campo novo `erro_troca`, sem tabela nova). Um endpoint só-leitura (`GET /revisar-status`) resolve esse estado a partir de duas funções puras e testáveis em `draft_store.py`. A página `pagina_trocando()` ganha um `<script>` que consulta esse endpoint a cada ~3s (polling), no mesmo estilo honesto/testável (JS extraído, shim de DOM em `node`) já usado no painel de progresso de upload (item 34).

**Tech Stack:** Python stdlib puro (`http.server`), sem dependências novas. `node` só é usado para RODAR os testes do JS extraído (já é assim pros outros componentes com `<script>`) — não é dependência de runtime da aplicação.

## Global Constraints

- Sem dependências novas — projeto é stdlib puro; `node` é só ferramenta de teste, não roda em produção.
- Endpoint novo é **`/revisar-status`** (com hífen, não `/revisar/status`) — não pode colidir com o prefixo `path.startswith("/revisar/")` já existente em `serve.py`.
- **Nenhuma tabela nova no banco.** `erro_troca` é só mais um campo dentro do payload JSON já existente em `daily_drafts` (via `draft_store`).
- Mensagem de erro exata (mesma que já vai pro WhatsApp hoje): `"Não consegui trocar o estudo; o anterior segue valendo."`
- Texto de demora exato: `"Ainda trabalhando nisso — mais que o esperado. O aviso também chega no seu WhatsApp assim que terminar."`
- Limiar de demora: **75000ms (75s)** — mesmo valor do item 34 (`ui._DEMORA_LONGA`), redefinido localmente (não importa o atributo privado de outro módulo).
- Intervalo de polling: **3000ms (3s)**.
- O aviso que já vai pro WhatsApp (`deliver.enviar_curador`) **não muda** — nem o texto, nem quando é chamado.
- Sem JS / `fetch` indisponível: a página cai pro texto estático de hoje. Nunca quebra.

---

## Task 1: `draft_store` — estado da troca (status_troca / iniciar_troca / falhar_troca)

**Files:**
- Modify: `app/draft_store.py` (adiciona 3 funções no fim do arquivo)
- Test: Create `app/tests/test_aviso_troca_termina.py`

**Interfaces:**
- Produces:
  - `draft_store.status_troca(token_antigo: str, data: str) -> dict` — `{"status": "andamento"}` | `{"status": "erro", "msg": str, "voltar": str}` | `{"status": "pronto", "link": str}`.
  - `draft_store.iniciar_troca(r: dict) -> None` — limpa `r["erro_troca"]` e salva.
  - `draft_store.falhar_troca(r: dict, msg: str) -> None` — grava `r["erro_troca"] = msg` e salva.
- Consumes: `draft_store.por_token`, `draft_store.carregar`, `draft_store.salvar` (já existem, mesmo arquivo).

- [ ] **Step 1: Escrever os testes (falham — as funções ainda não existem)**

Criar `app/tests/test_aviso_troca_termina.py`:

```python
"""Item 43 (parte A) — a tela "Trocando..." avisa sozinha quando a troca do estudo de
amanhã termina (sucesso com link novo, ou erro), sem precisar checar o WhatsApp.

O estado mora no MESMO rascunho já persistido em `daily_drafts` (`erro_troca`), sem
tabela nova: o token antigo SUMIR (sobrescrito pelo novo, upsert por `data`) é o sinal
de sucesso — mesmo mecanismo que já causa "Link inválido/expirado" hoje.
"""
import importlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DSCURSO_DATA", tempfile.mkdtemp())

_NODE = shutil.which("node")


class TestStatusTroca(unittest.TestCase):
    def setUp(self):
        import draft_store
        importlib.reload(draft_store)
        self.ds = draft_store

    def test_andamento_quando_rascunho_antigo_existe_sem_erro(self):
        with mock.patch.object(self.ds, "por_token", return_value={"data": "2026-08-27"}):
            r = self.ds.status_troca("tok-velho", "2026-08-27")
        self.assertEqual(r, {"status": "andamento"})

    def test_erro_quando_rascunho_antigo_tem_erro_troca(self):
        rascunho = {"data": "2026-08-27",
                    "erro_troca": "Não consegui trocar o estudo; o anterior segue valendo."}
        with mock.patch.object(self.ds, "por_token", return_value=rascunho):
            r = self.ds.status_troca("tok-velho", "2026-08-27")
        self.assertEqual(r, {"status": "erro",
                             "msg": "Não consegui trocar o estudo; o anterior segue valendo.",
                             "voltar": "/revisar/tok-velho"})

    def test_pronto_quando_rascunho_antigo_sumiu_e_ha_um_novo_na_data(self):
        atual = {"review_token": "tok-novo", "data": "2026-08-27"}
        with mock.patch.object(self.ds, "por_token", return_value=None), \
             mock.patch.object(self.ds, "carregar", return_value=atual):
            r = self.ds.status_troca("tok-velho", "2026-08-27")
        self.assertEqual(r, {"status": "pronto", "link": "/revisar/tok-novo"})

    def test_andamento_quando_nao_ha_rascunho_nenhum_ainda(self):
        """Caso extremo, praticamente inatingível pelo fluxo real (serve.py só chega
        aqui depois de confirmar que o rascunho existe) — nunca finge sucesso ou erro
        sem ter certeza."""
        with mock.patch.object(self.ds, "por_token", return_value=None), \
             mock.patch.object(self.ds, "carregar", return_value=None):
            r = self.ds.status_troca("tok-velho", "2026-08-27")
        self.assertEqual(r, {"status": "andamento"})

    def test_token_ou_data_vazios_nao_estouram(self):
        with mock.patch.object(self.ds, "por_token", return_value=None), \
             mock.patch.object(self.ds, "carregar", return_value=None):
            r = self.ds.status_troca("", "")
        self.assertEqual(r, {"status": "andamento"})


class TestIniciarTroca(unittest.TestCase):
    def setUp(self):
        import draft_store
        importlib.reload(draft_store)
        self.ds = draft_store

    def test_limpa_erro_anterior_e_salva(self):
        r = {"data": "2026-08-27", "erro_troca": "erro de uma tentativa anterior"}
        with mock.patch.object(self.ds, "salvar") as m_salvar:
            self.ds.iniciar_troca(r)
        self.assertEqual(r["erro_troca"], "")
        m_salvar.assert_called_once_with(r)

    def test_funciona_sem_erro_anterior(self):
        r = {"data": "2026-08-27"}
        with mock.patch.object(self.ds, "salvar") as m_salvar:
            self.ds.iniciar_troca(r)
        self.assertEqual(r["erro_troca"], "")
        m_salvar.assert_called_once_with(r)


class TestFalharTroca(unittest.TestCase):
    def setUp(self):
        import draft_store
        importlib.reload(draft_store)
        self.ds = draft_store

    def test_grava_mensagem_e_salva(self):
        r = {"data": "2026-08-27"}
        with mock.patch.object(self.ds, "salvar") as m_salvar:
            self.ds.falhar_troca(r, "deu ruim")
        self.assertEqual(r["erro_troca"], "deu ruim")
        m_salvar.assert_called_once_with(r)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `cd app && python3 -m pytest tests/test_aviso_troca_termina.py -v`
Expected: FAIL — `AttributeError: module 'draft_store' has no attribute 'status_troca'` (e outros dois, `iniciar_troca`/`falhar_troca`).

- [ ] **Step 3: Implementar as três funções em `app/draft_store.py`**

Adicionar no FIM do arquivo (depois de `aplicar`):

```python
def status_troca(token_antigo, data):
    """Estado de uma troca de estudo em andamento (ver `daily.trocar_estudo_amanha`).

    O rascunho antigo (`token_antigo`) SUMIR é o sinal de sucesso: `trocar_estudo_amanha`
    sobrescreve o registro do dia com um token novo (upsert por `data`), então o antigo
    para de casar com qualquer linha. Enquanto o rascunho antigo ainda existe, ou está
    "andamento" (sem erro) ou "erro" (campo `erro_troca` preenchido). `data` só entra em
    jogo no caminho de sucesso, pra achar o registro novo — o token antigo sozinho não
    basta depois que ele deixou de existir."""
    r = por_token(token_antigo)
    if r:
        erro = r.get("erro_troca")
        if erro:
            return {"status": "erro", "msg": erro, "voltar": f"/revisar/{token_antigo}"}
        return {"status": "andamento"}
    atual = carregar(data) if data else None
    if atual and atual.get("review_token") and atual["review_token"] != token_antigo:
        return {"status": "pronto", "link": f"/revisar/{atual['review_token']}"}
    return {"status": "andamento"}     # nunca finge saber o que não sabe


def iniciar_troca(r):
    """Limpa `erro_troca` de uma tentativa de troca anterior antes de começar uma nova
    (o mesmo token pode ser reusado se a troca de antes falhou) — sem isto, um erro
    velho "vazaria" pra tentativa nova em `status_troca`."""
    r["erro_troca"] = ""
    salvar(r)


def falhar_troca(r, msg):
    """Grava o erro de uma troca que falhou no MESMO rascunho (token antigo) — é o que
    `status_troca` consulta pra dizer "erro" em vez de ficar "andamento" pra sempre."""
    r["erro_troca"] = msg
    salvar(r)
```

- [ ] **Step 4: Rodar os testes de novo e confirmar que passam**

Run: `cd app && python3 -m pytest tests/test_aviso_troca_termina.py -v`
Expected: PASS (7 testes: `TestStatusTroca` x5, `TestIniciarTroca` x2, `TestFalharTroca` x1).

- [ ] **Step 5: Commit**

```bash
git add app/draft_store.py app/tests/test_aviso_troca_termina.py
git commit -m "feat(revisar): estado da troca em draft_store (status_troca/iniciar_troca/falhar_troca)"
```

---

## Task 2: `daily.trocar_estudo_amanha` grava o erro quando o preparo falha

**Files:**
- Modify: `app/daily.py:502-542` (função `trocar_estudo_amanha`)
- Test: Modify `app/tests/test_trocar_estudo.py` (classe `TestTrocarEstudoAmanha`)

**Interfaces:**
- Consumes: `draft_store.falhar_troca(r, msg)` (Task 1).
- Produces: `daily.trocar_estudo_amanha(token, tipo, cid)` — assinatura e retorno inalterados; novo efeito colateral: quando o preparo do escolhido falha, chama `draft_store.falhar_troca(r, msg)` antes do aviso no WhatsApp.

- [ ] **Step 1: Estender o teste existente (falha — a chamada ainda não acontece)**

Em `app/tests/test_trocar_estudo.py`, dentro de `class TestTrocarEstudoAmanha`, trocar o teste `test_preparo_falha_avisa_curador_sem_tocar_agenda` por esta versão (adiciona o mock/assert de `falhar_troca`, mantém tudo que já existia):

```python
    def test_preparo_falha_avisa_curador_e_grava_erro_no_rascunho(self):
        daily = self.daily
        import db
        r = {"candidato_id": "c_velho", "data": "2026-07-28", "artigo": {"tema": "Obesidade"}}
        with mock.patch.object(daily.draft_store, "por_token", return_value=r), \
             mock.patch.object(db, "agenda_upsert") as m_up, \
             mock.patch.object(db, "marcar_candidato_pronto") as m_pool, \
             mock.patch.object(daily, "_preparar_da_reserva", side_effect=RuntimeError("boom")), \
             mock.patch.object(daily.draft_store, "falhar_troca") as m_falhar, \
             mock.patch.object(daily.deliver, "enviar_curador") as m_cur:
            out = daily.trocar_estudo_amanha("tok", "reserva", "res_x")
        self.assertIsNone(out)
        m_falhar.assert_called_once_with(
            r, "Não consegui trocar o estudo; o anterior segue valendo.")
        m_cur.assert_called_once()
        m_up.assert_not_called()
        m_pool.assert_not_called()
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `cd app && python3 -m pytest tests/test_trocar_estudo.py::TestTrocarEstudoAmanha::test_preparo_falha_avisa_curador_e_grava_erro_no_rascunho -v`
Expected: FAIL — `AttributeError: <module 'draft_store'> does not have the attribute 'falhar_troca'` (mock em atributo inexistente) OU, se a Task 1 já rodou antes, `AssertionError: Expected 'falhar_troca' to be called once. Called 0 times.`

- [ ] **Step 3: Implementar em `app/daily.py`**

Trocar o bloco `if not novo:` dentro de `trocar_estudo_amanha` (linha ~521):

De:
```python
    if not novo:
        deliver.enviar_curador("⚠️ Não consegui trocar o estudo; o anterior segue valendo.")
        return None
```

Para:
```python
    if not novo:
        msg = "Não consegui trocar o estudo; o anterior segue valendo."
        draft_store.falhar_troca(r, msg)
        deliver.enviar_curador(f"⚠️ {msg}")
        return None
```

Também atualizar a docstring da função (linha ~503-505), acrescentando uma frase — ela some da vista de quem só lê o corpo, e é o tipo de contrato entre módulos que vale documentar:

De:
```python
def trocar_estudo_amanha(token, tipo, cid):
    """Refaz o rascunho de amanhã a partir do estudo escolhido (roda em thread).
    Grava o slot de amanhã no escolhido (consome, igual ao materialize) e devolve o
    estudo atual ao pool. Fail-safe: exceção no preparo -> avisa o curador, o antigo fica."""
```

Para:
```python
def trocar_estudo_amanha(token, tipo, cid):
    """Refaz o rascunho de amanhã a partir do estudo escolhido (roda em thread).
    Grava o slot de amanhã no escolhido (consome, igual ao materialize) e devolve o
    estudo atual ao pool. Fail-safe: exceção no preparo -> avisa o curador, o antigo fica.

    Quando o preparo falha, grava a mensagem em `erro_troca` no MESMO rascunho (token
    antigo) além do aviso por WhatsApp — é o que `pagina_trocando` mostra sozinha via
    `draft_store.status_troca`, sem precisar checar o WhatsApp."""
```

- [ ] **Step 4: Rodar os testes de `daily.py` e confirmar que passam**

Run: `cd app && python3 -m pytest tests/test_trocar_estudo.py -v`
Expected: PASS (todos — o teste renomeado e os outros 5 de `TestTrocarEstudoAmanha` continuam passando sem mudança).

- [ ] **Step 5: Commit**

```bash
git add app/daily.py app/tests/test_trocar_estudo.py
git commit -m "feat(daily): trocar_estudo_amanha grava erro_troca quando o preparo falha"
```

---

## Task 3: `review_web.pagina_trocando` — painel + JS de polling

**Files:**
- Modify: `app/review_web.py:221-227` (função `pagina_trocando`)
- Modify: `app/tests/test_trocar_estudo.py` (o único teste que chama a assinatura antiga)
- Test: Modify `app/tests/test_aviso_troca_termina.py` (acrescenta as classes `TestPaginaTrocando` e `TestComportamentoDoJs`)

**Interfaces:**
- Produces: `review_web.pagina_trocando(token: str, data: str) -> str` — assinatura MUDA (antes não tinha parâmetros). HTML embute `id="troca-status"` com `data-token`/`data-data`, um `<span class="troca-espera">` com o texto estático de hoje, e um `<script>` que consulta `GET /revisar-status?token=...&data=...` a cada 3s e reage a `{"status": "pronto"|"erro"|"andamento", ...}` (mesmo formato de `draft_store.status_troca`, Task 1).
- Consumes: nada de outro módulo além de `html` (já importado no topo do arquivo).

- [ ] **Step 1: Corrigir o teste existente que quebra com a assinatura nova (falha até o Step 3)**

Em `app/tests/test_trocar_estudo.py`, trocar:

```python
    def test_pagina_trocando(self):
        import review_web
        self.assertIn("Trocando", review_web.pagina_trocando())
```

Por:

```python
    def test_pagina_trocando(self):
        import review_web
        self.assertIn("Trocando", review_web.pagina_trocando("tok-velho", "2026-08-27"))
```

- [ ] **Step 2: Escrever os testes de markup e o teste do JS (falham — a função ainda não existe/está com a assinatura velha)**

Em `app/tests/test_aviso_troca_termina.py`, acrescentar (import `re`, `subprocess`, `shutil`, `tempfile` já estão no topo do arquivo criado na Task 1):

```python
def _extrair_script(html, marca="troca-status"):
    for corpo in re.findall(r"<script>(.*?)</script>", html, re.S):
        if marca in corpo:
            return corpo
    raise AssertionError("o <script> da troca não está na página")


class TestPaginaTrocando(unittest.TestCase):
    def test_traz_os_ganchos_que_o_js_procura(self):
        import review_web
        h = review_web.pagina_trocando("tok-velho", "2026-08-27")
        self.assertIn('id="troca-status"', h)
        self.assertIn('data-token="tok-velho"', h)
        self.assertIn('data-data="2026-08-27"', h)
        self.assertIn('class="troca-espera"', h)
        self.assertIn("troca-status", _extrair_script(h))

    def test_escapa_token_no_atributo(self):
        import review_web
        h = review_web.pagina_trocando('tok"malicioso', "2026-08-27")
        self.assertIn('data-token="tok&quot;malicioso"', h)

    def test_sem_js_mostra_o_texto_estatico_de_hoje(self):
        import review_web
        h = review_web.pagina_trocando("tok", "2026-08-27")
        self.assertIn("Pode fechar esta página", h)


_SHIM = r"""
'use strict';
// -- shim de DOM minimo: so o que o script de troca-status usa --------------
var agora = 0;                                    // relogio falso (Date.now)
global.Date = { now: function(){ return agora; } };
function avancarRelogio(ms){ agora += ms; }

function El(tag, attrs){
  this.tagName = tag; this.attrs = attrs || {}; this._texto = '';
}
Object.defineProperty(El.prototype, 'textContent', {
  get: function(){ return this._texto; },
  set: function(v){ this._texto = String(v); }
});
El.prototype.getAttribute = function(k){ return this.attrs[k] === undefined ? null : this.attrs[k]; };

var espera = new El('span', {});
espera.textContent = 'O novo resumo esta sendo gerado. Em ~1-2 min voce recebe no WhatsApp ' +
  'o estudo novo (com PDF, audio e um link de revisao novo). Pode fechar esta pagina.';

var statusEl = new El('div', {'data-token': 'tok-velho', 'data-data': '2026-08-27'});
statusEl._html = '';
statusEl._substituido = false;
Object.defineProperty(statusEl, 'innerHTML', {
  get: function(){ return this._html; },
  set: function(v){ this._html = v; this._substituido = true; }
});
statusEl.querySelector = function(sel){
  return (sel === '.troca-espera' && !this._substituido) ? espera : null;
};

var mapa = {'troca-status': statusEl};
function removerElemento(){ mapa['troca-status'] = null; }
function removerAtributos(){ statusEl.attrs = {}; }

global.document = { getElementById: function(id){ return mapa[id] || null; } };

var timers = [];
global.setInterval = function(fn){ timers.push({fn: fn, vivo: true}); return timers.length; };
global.clearInterval = function(id){ if (timers[id - 1]) timers[id - 1].vivo = false; };
function tick(){ timers.forEach(function(t){ if (t.vivo) t.fn(); }); }

var filaRespostas = [];
function enfileirar(j){ filaRespostas.push(j); }
function fetchPadrao(){
  var resp = filaRespostas.length ? filaRespostas.shift() : {status: 'andamento'};
  return Promise.resolve({ json: function(){ return Promise.resolve(resp); } });
}
global.fetch = fetchPadrao;
global.window = { fetch: fetchPadrao };

function relatarDepois(){
  setTimeout(function(){
    console.log(JSON.stringify({
      html: statusEl._html,
      esperaTexto: espera.textContent,
      timerVivo: timers.length ? timers[0].vivo : null
    }));
  }, 0);
}
"""


@unittest.skipUnless(_NODE, "node não está no PATH — teste de comportamento do JS")
class TestComportamentoDoJs(unittest.TestCase):
    """Roda o JS DA PÁGINA (extraído, não copiado) sobre um shim de DOM — mesmo método
    de `test_upload_progresso.py` (item 34) / `test_cupom_previa_js.py`."""

    @classmethod
    def setUpClass(cls):
        import review_web
        cls.script = _extrair_script(review_web.pagina_trocando("tok-velho", "2026-08-27"))
        cls.tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _rodar(self, roteiro, prelude=""):
        src = _SHIM + "\n" + prelude + "\n" + self.script + "\n" + roteiro
        caminho = os.path.join(self.tmp, "t.js")
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(src)
        out = subprocess.run([_NODE, caminho], capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            self.fail(f"node falhou: {out.stderr[:900]}")
        import json
        return json.loads(out.stdout.strip().splitlines()[-1])

    def test_pronto_mostra_o_link_novo(self):
        r = self._rodar("enfileirar({status:'pronto', link:'/revisar/novo'}); tick(); relatarDepois();")
        self.assertIn("Troca conclu", r["html"])
        self.assertIn("/revisar/novo", r["html"])
        self.assertFalse(r["timerVivo"])

    def test_erro_mostra_mensagem_e_link_de_volta(self):
        r = self._rodar(
            "enfileirar({status:'erro', msg:'Não consegui trocar', voltar:'/revisar/velho'});"
            " tick(); relatarDepois();")
        self.assertIn("Não consegui trocar", r["html"])
        self.assertIn("/revisar/velho", r["html"])
        self.assertFalse(r["timerVivo"])

    def test_andamento_nao_mexe_na_pagina_antes_do_prazo(self):
        r = self._rodar("enfileirar({status:'andamento'}); tick(); relatarDepois();")
        self.assertEqual(r["html"], "")
        self.assertIn("Pode fechar esta p", r["esperaTexto"])
        self.assertTrue(r["timerVivo"])

    def test_demora_troca_o_texto_em_vez_de_mentir(self):
        r = self._rodar(
            "avancarRelogio(76000); enfileirar({status:'andamento'}); tick(); relatarDepois();")
        self.assertIn("Ainda trabalhando", r["esperaTexto"])
        self.assertEqual(r["html"], "")

    def test_erro_de_rede_nao_trava_tenta_de_novo_depois(self):
        r = self._rodar(
            "global.fetch = function(){ return Promise.reject(new Error('rede')); };"
            " tick(); relatarDepois();")
        self.assertEqual(r["html"], "")
        self.assertTrue(r["timerVivo"])

    def test_sem_o_elemento_no_dom_o_js_nao_explode(self):
        r = self._rodar("relatarDepois();", prelude="removerElemento();")
        self.assertIsNone(r["timerVivo"])

    def test_sem_os_atributos_o_js_nao_explode(self):
        r = self._rodar("relatarDepois();", prelude="removerAtributos();")
        self.assertIsNone(r["timerVivo"])
```

- [ ] **Step 3: Rodar tudo e confirmar que falha**

Run: `cd app && python3 -m pytest tests/test_aviso_troca_termina.py tests/test_trocar_estudo.py -v`
Expected: FAIL — `TypeError: pagina_trocando() takes 0 positional arguments but 2 were given` (assinatura ainda não mudou).

- [ ] **Step 4: Implementar em `app/review_web.py`**

Trocar a função inteira (linhas 221-227):

De:
```python
def pagina_trocando():
    return ('<!doctype html><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<body style="font-family:system-ui;max-width:600px;margin:40px auto;padding:0 16px;color:#1a2b28">'
            '<h3>🔄 Trocando…</h3>'
            '<p>O novo resumo está sendo gerado. Em ~1-2 min você recebe no WhatsApp o estudo novo '
            '(com PDF, áudio e um link de revisão novo). Pode fechar esta página.</p></body>')
```

Para:
```python
def pagina_trocando(token, data):
    """Tela pós-troca: consulta /revisar-status a cada ~3s e mostra sozinha quando
    terminou (sucesso com link novo, ou erro) — sem precisar checar o WhatsApp. Sem
    JS/fetch, cai pro texto estático (nunca quebra). Ver `draft_store.status_troca`
    (formato da resposta) e `daily.trocar_estudo_amanha` (quem faz a troca de verdade)."""
    esc = _html.escape
    return f"""<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<body style="font-family:system-ui;max-width:600px;margin:40px auto;padding:0 16px;color:#1a2b28">
<h3>🔄 Trocando…</h3>
<div id="troca-status" data-token="{esc(token)}" data-data="{esc(data)}">
<p><span class="troca-espera">O novo resumo está sendo gerado. Em ~1-2 min você recebe no
WhatsApp o estudo novo (com PDF, áudio e um link de revisão novo). Pode fechar esta
página.</span></p>
</div>
<script>
(function(){{
  var el = document.getElementById('troca-status');
  if (!el || !window.fetch) return;
  var token = el.getAttribute('data-token'), data = el.getAttribute('data-data');
  if (!token || !data) return;
  var t0 = Date.now(), timer = setInterval(consultar, 3000);
  function consultar(){{
    fetch('/revisar-status?token=' + encodeURIComponent(token) + '&data=' + encodeURIComponent(data))
      .then(function(r){{ return r.json(); }})
      .then(tratar)
      .catch(function(){{}});
  }}
  function tratar(j){{
    if (j.status === 'pronto'){{
      clearInterval(timer);
      el.innerHTML = '<b>✅ Troca concluída!</b><br><a href="' + j.link + '">Ver a revisão nova</a>';
    }} else if (j.status === 'erro'){{
      clearInterval(timer);
      el.innerHTML = '<b>⚠️ ' + j.msg + '</b><br><a href="' + j.voltar + '">← Voltar pra revisão</a>';
    }} else if (Date.now() - t0 > 75000){{
      var esp = el.querySelector('.troca-espera');
      if (esp) esp.textContent = 'Ainda trabalhando nisso — mais que o esperado. O aviso ' +
        'também chega no seu WhatsApp assim que terminar.';
    }}
  }}
  consultar();
}})();
</script>
</body>"""
```

- [ ] **Step 5: Rodar tudo de novo e confirmar que passa**

Run: `cd app && python3 -m pytest tests/test_aviso_troca_termina.py tests/test_trocar_estudo.py -v`
Expected: PASS. Se `node` não estiver no PATH, `TestComportamentoDoJs` aparece como `skipped` (não falha) — os outros continuam passando.

- [ ] **Step 6: Commit**

```bash
git add app/review_web.py app/tests/test_aviso_troca_termina.py app/tests/test_trocar_estudo.py
git commit -m "feat(revisar): pagina_trocando avisa sozinha quando a troca termina (polling)"
```

---

## Task 4: `serve.py` — liga o endpoint e o início da troca

**Files:**
- Modify: `app/serve.py` (`do_GET`: novo branch `/revisar-status`; `do_POST`, branch `trocar_confirmar`)

**Interfaces:**
- Consumes: `draft_store.status_troca` (Task 1), `draft_store.iniciar_troca` (Task 1), `review_web.pagina_trocando(token, data)` (Task 3).
- Produces: nada consumido por outra task — é o fim da cadeia.

Sem teste automatizado dedicado nesta task: `do_GET`/`do_POST` são despacho puro (if/elif por `path`), e este arquivo não tem NENHUMA rota testada nesse nível hoje — a lógica de verdade (`status_troca`, `iniciar_troca`, `falhar_troca`, `pagina_trocando`) já foi testada nas Tasks 1-3 (mesmo padrão de `serve._destino_seguro`, testado direto em `test_destino_seguro.py`, sem passar pelo dispatch do `do_GET`/`do_POST`). A verificação aqui é rodar a suite inteira (pra pegar qualquer chamador que ainda use a assinatura velha) + um smoke test manual.

- [ ] **Step 1: Adicionar o branch `GET /revisar-status` em `app/serve.py`**

Dentro de `do_GET` (a função começa na linha 253), logo depois do branch existente `if path.startswith("/revisar/"):` (linhas 271-278), adicionar:

```python
        if path == "/revisar-status":
            import draft_store
            q = up.parse_qs(up.urlparse(self.path).query)
            tok = (q.get("token") or [""])[0]
            data = (q.get("data") or [""])[0]
            return self._json(draft_store.status_troca(tok, data))
```

(`up` já está importado no topo de `do_GET`, linha 254 — `import urllib.parse as up`.)

- [ ] **Step 2: Ligar `trocar_confirmar` ao novo fluxo em `app/serve.py`**

Dentro de `do_POST`, no branch `if g("acao") == "trocar_confirmar":` (por volta da linha 791-800):

De:
```python
            if g("acao") == "trocar_confirmar":
                import daily, threading
                tipo, cid = g("tipo"), g("id")
                if not daily.alternativa_valida(r, tipo, cid):
                    return self._html(review_web.pagina_revisao(
                        r, aviso="Esse estudo saiu da lista — escolha outro.",
                        audio_on=config.audio_ligado(), areas=areas))
                threading.Thread(target=daily.trocar_estudo_amanha,
                                 args=(tok, tipo, cid), daemon=True).start()
                return self._html(review_web.pagina_trocando())
```

Para:
```python
            if g("acao") == "trocar_confirmar":
                import daily, threading
                tipo, cid = g("tipo"), g("id")
                if not daily.alternativa_valida(r, tipo, cid):
                    return self._html(review_web.pagina_revisao(
                        r, aviso="Esse estudo saiu da lista — escolha outro.",
                        audio_on=config.audio_ligado(), areas=areas))
                draft_store.iniciar_troca(r)
                threading.Thread(target=daily.trocar_estudo_amanha,
                                 args=(tok, tipo, cid), daemon=True).start()
                return self._html(review_web.pagina_trocando(tok, r["data"]))
```

(`draft_store` já está importado no topo deste bloco de `do_POST`, linha 772 — `import area_estudo, config, draft_store, review_web`.)

- [ ] **Step 3: Sanity check de sintaxe/import**

Run: `cd app && python3 -c "import serve"`
Expected: sem erro (confirma que não sobrou nenhum `SyntaxError`/`NameError` óbvio — `serve.py` só inicia o servidor dentro do `if __name__ == "__main__":`, então importar é seguro).

- [ ] **Step 4: Rodar a suíte inteira**

Run: `cd app && python3 -m pytest tests/ -q`
Expected: PASS em tudo — em especial confirma que nenhum outro lugar do código ainda chama `review_web.pagina_trocando()` sem argumentos (só havia UM call site, o que acabou de mudar).

- [ ] **Step 5: Smoke test manual (local)**

Suba o servidor localmente (`cd app && python3 serve.py`, numa aba separada) e confira à mão, contra um rascunho de teste no ambiente local:

```bash
# status de um token que não existe (nunca deve dar 500)
curl -s "http://localhost:3000/revisar-status?token=lixo&data=2026-08-27"
# esperado: {"status": "andamento"}
```

E, pelo picker do 🔁 (`/revisar/<tok>` → trocar → escolher um estudo), confirmar visualmente que a página "🔄 Trocando…" atualiza sozinha pra "✅ Troca concluída!" (ou pro erro) dentro de alguns segundos, sem recarregar a página à mão.

- [ ] **Step 6: Commit**

```bash
git add app/serve.py
git commit -m "feat(revisar): liga /revisar-status e trocar_confirmar ao aviso ao vivo"
```
