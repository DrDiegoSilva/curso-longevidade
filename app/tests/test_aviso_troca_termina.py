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
  this.tagName = tag; this.attrs = attrs || {}; this._texto = ''; this.children = [];
}
Object.defineProperty(El.prototype, 'textContent', {
  get: function(){ return this._texto; },
  set: function(v){ this._texto = String(v); }
});
El.prototype.getAttribute = function(k){ return this.attrs[k] === undefined ? null : this.attrs[k]; };
El.prototype.appendChild = function(no){ this.children.push(no); return no; };

var espera = new El('span', {});
espera.textContent = 'O novo resumo esta sendo gerado. Em ~1-2 min voce recebe no WhatsApp ' +
  'o estudo novo (com PDF, audio e um link de revisao novo). Pode fechar esta pagina.';

var statusEl = new El('div', {'data-token': 'tok-velho', 'data-data': '2026-08-27'});
statusEl._html = '';
statusEl._substituido = false;
Object.defineProperty(statusEl, 'innerHTML', {
  get: function(){ return this._html; },
  set: function(v){ this._html = v; this._substituido = true; this.children = []; }
});
statusEl.querySelector = function(sel){
  return (sel === '.troca-espera' && !this._substituido) ? espera : null;
};

var mapa = {'troca-status': statusEl};
function removerElemento(){ mapa['troca-status'] = null; }
function removerAtributos(){ statusEl.attrs = {}; }

global.document = {
  getElementById: function(id){ return mapa[id] || null; },
  createElement: function(tag){ return new El(tag); }
};

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

function resumoFilhos(){
  return statusEl.children.map(function(c){
    if (c.tagName === 'a') return 'LINK(' + c.textContent + ',' + c.href + ')';
    if (c.tagName === 'b') return 'B(' + c.textContent + ')';
    return c.tagName || '';
  }).join('|');
}
function relatarDepois(){
  setTimeout(function(){
    console.log(JSON.stringify({
      resumo: resumoFilhos(),
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
        self.assertIn("Troca conclu", r["resumo"])
        self.assertIn("/revisar/novo", r["resumo"])
        self.assertFalse(r["timerVivo"])

    def test_erro_mostra_mensagem_e_link_de_volta(self):
        r = self._rodar(
            "enfileirar({status:'erro', msg:'Não consegui trocar', voltar:'/revisar/velho'});"
            " tick(); relatarDepois();")
        self.assertIn("Não consegui trocar", r["resumo"])
        self.assertIn("/revisar/velho", r["resumo"])
        self.assertFalse(r["timerVivo"])

    def test_mensagem_de_erro_maliciosa_nao_vira_html(self):
        """A mensagem de erro entra como TEXTO (textContent), nunca como HTML — sem
        isso, um erro com conteúdo controlável (ex: mensagem de exceção) viraria XSS."""
        r = self._rodar(
            "enfileirar({status:'erro', msg:'<img src=x onerror=alert(1)>', voltar:'/revisar/velho'});"
            " tick(); relatarDepois();")
        self.assertIn("<img src=x onerror=alert(1)>", r["resumo"])

    def test_andamento_nao_mexe_na_pagina_antes_do_prazo(self):
        r = self._rodar("enfileirar({status:'andamento'}); tick(); relatarDepois();")
        self.assertEqual(r["resumo"], "")
        self.assertIn("Pode fechar esta p", r["esperaTexto"])
        self.assertTrue(r["timerVivo"])

    def test_demora_troca_o_texto_em_vez_de_mentir(self):
        r = self._rodar(
            "avancarRelogio(76000); enfileirar({status:'andamento'}); tick(); relatarDepois();")
        self.assertIn("Ainda trabalhando", r["esperaTexto"])
        self.assertEqual(r["resumo"], "")

    def test_erro_de_rede_nao_trava_tenta_de_novo_depois(self):
        r = self._rodar(
            "global.fetch = function(){ return Promise.reject(new Error('rede')); };"
            " tick(); relatarDepois();")
        self.assertEqual(r["resumo"], "")
        self.assertTrue(r["timerVivo"])

    def test_sem_o_elemento_no_dom_o_js_nao_explode(self):
        r = self._rodar("relatarDepois();", prelude="removerElemento();")
        self.assertIsNone(r["timerVivo"])

    def test_sem_os_atributos_o_js_nao_explode(self):
        r = self._rodar("relatarDepois();", prelude="removerAtributos();")
        self.assertIsNone(r["timerVivo"])


if __name__ == "__main__":
    unittest.main()
