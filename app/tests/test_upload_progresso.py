"""Item 34 — o upload de estudo não dava NENHUM retorno na tela.

Diego: *"não aparece na tela se deu certo subir, se a IA tá lendo ou não — só percebe
que no favicon fica rodando em carregamento"*.

O upload é síncrono e passa por várias chamadas de IA (triagem, título, resumo, gancho,
gráfico, metadados): dezenas de segundos com a tela muda. Tempo de sobra pra achar que
travou e **apertar de novo — o que hoje cria o estudo DUPLICADO na fila**.

Como o JS é testado: o `<script>` é EXTRAÍDO da página gerada e roda no `node` sobre um
shim de DOM (mesmo método do `test_cupom_previa_js.py`). Copiar o JS pra cá testaria a
cópia — e o JS é todo null-guarded, então um refactor de markup DESLIGA a feature
inteira com a suíte verde. Daí os testes de contrato de markup também.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_NODE = shutil.which("node")


def _extrair_script(html, marca):
    for corpo in re.findall(r"<script>(.*?)</script>", html, re.S):
        if marca in corpo:
            return corpo
    raise AssertionError(f"o <script> do progresso de upload ({marca}) não está na página")


class TestComponente(unittest.TestCase):
    """O componente em si (`ui.progresso_upload`), fora das páginas."""

    def setUp(self):
        import ui
        self.ui = ui

    def test_traz_os_ganchos_que_o_js_procura(self):
        h = self.ui.progresso_upload("up-x")
        for gancho in ('id="up-x-prog"', 'id="up-x-passo"', 'id="up-x-crono"'):
            self.assertIn(gancho, h)
        self.assertIn("up-x", _extrair_script(h, "up-x"))

    def test_painel_comeca_escondido(self):
        h = self.ui.progresso_upload("up-x")
        painel = h.split('id="up-x-prog"', 1)[1].split(">", 1)[0]
        self.assertIn("display:none", painel)

    def test_avisa_pra_nao_fechar_a_aba(self):
        """Fechar a aba mata a geração no meio — o texto tem que dizer isso."""
        self.assertIn("Não feche", self.ui.progresso_upload("up-x"))

    def test_dois_formularios_na_mesma_pagina_nao_colidem(self):
        a, b = self.ui.progresso_upload("up-a"), self.ui.progresso_upload("up-b")
        self.assertNotIn("up-b", a)
        self.assertNotIn("up-a", b)


class TestPaginasUsamOComponente(unittest.TestCase):
    """Contrato de markup: o JS é null-guarded e sai de fininho se os ids sumirem."""

    def _curadoria(self):
        import site_web
        return site_web.pagina_curadoria(
            {"pronto": 0, "minimo": 3}, None, [], [], {"candidatos": [], "banco": []}, "tok")

    def test_curadoria_tem_form_com_id_e_painel(self):
        html = self._curadoria()
        self.assertIn('id="up-curadoria"', html)
        self.assertIn('id="up-curadoria-prog"', html)
        self.assertIn('id="up-curadoria-passo"', html)
        self.assertIn('id="up-curadoria-crono"', html)

    def test_curadoria_mantem_o_form_multipart_pro_caso_do_js_falhar(self):
        """Progressive enhancement: sem JS o POST normal tem que continuar funcionando."""
        html = self._curadoria()
        form = html.split('id="up-curadoria"', 1)[0]
        form = form[form.rfind("<form"):]
        self.assertIn('method="post"', form)
        self.assertIn('action="/curadoria"', form)
        self.assertIn('enctype="multipart/form-data"', form)


@unittest.skipUnless(_NODE, "node não está no PATH — teste de comportamento do JS")
class TestComportamentoDoJs(unittest.TestCase):
    """Roda o JS DA PÁGINA (extraído, não copiado) sobre um shim de DOM."""

    @classmethod
    def setUpClass(cls):
        import ui
        cls.script = _extrair_script(ui.progresso_upload("up-x"), "up-x")
        cls.tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _rodar(self, roteiro, prelude=""):
        """roteiro = JS disparado DEPOIS do script carregar; prelude = ANTES (o script é
        um IIFE que captura os elementos no load, então mexer no DOM depois não adianta)."""
        src = _SHIM + "\n" + prelude + "\n" + self.script + "\n" + roteiro
        caminho = os.path.join(self.tmp, "t.js")
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(src)
        out = subprocess.run([_NODE, caminho], capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            self.fail(f"node falhou: {out.stderr[:900]}")
        import json
        return json.loads(out.stdout.strip().splitlines()[-1])

    def test_submeter_desabilita_o_botao_e_abre_o_painel(self):
        r = self._rodar("submeter(); relatar();")
        self.assertTrue(r["btnDisabled"])
        self.assertEqual(r["painelDisplay"], "block")

    def test_clique_duplo_nao_envia_duas_vezes(self):
        """O bug caro: hoje o 2º clique gera um estudo DUPLICADO na fila."""
        r = self._rodar("submeter(); submeter(); submeter(); relatar();")
        self.assertEqual(r["envios"], 1)

    def test_fim_do_upload_diz_que_a_ia_esta_lendo(self):
        r = self._rodar("submeter(); ultimoXhr.upload.disparar('load'); relatar();")
        self.assertIn("IA", r["passo"])

    def test_sucesso_navega_pra_url_final_que_carrega_a_mensagem(self):
        r = self._rodar("submeter(); ultimoXhr.responseURL='/curadoria?msg=ok';"
                        " ultimoXhr.disparar('load'); relatar();")
        self.assertEqual(r["href"], "/curadoria?msg=ok")

    def test_erro_de_rede_reabilita_o_botao_em_vez_de_travar(self):
        r = self._rodar("submeter(); ultimoXhr.disparar('error'); relatar();")
        self.assertFalse(r["btnDisabled"])
        self.assertEqual(r["btnTexto"], "Enviar")
        self.assertNotEqual(r["passo"], "")

    def test_depois_do_erro_da_pra_tentar_de_novo(self):
        r = self._rodar("submeter(); ultimoXhr.disparar('error'); submeter(); relatar();")
        self.assertEqual(r["envios"], 2)

    def test_cronometro_conta_em_mm_ss(self):
        self.assertEqual(self._rodar("submeter(); avancar(75); relatar();")["crono"], "1:15")
        self.assertEqual(self._rodar("submeter(); avancar(8); relatar();")["crono"], "0:08")
        # 65s é o caso que pega a falta do zero à esquerda ("1:5" em vez de "1:05");
        # 75s sozinho passava com os dois formatos.
        self.assertEqual(self._rodar("submeter(); avancar(65); relatar();")["crono"], "1:05")

    def test_demora_longa_troca_o_texto_em_vez_de_mentir(self):
        curto = self._rodar("submeter(); avancar(10); relatar();")
        longo = self._rodar("submeter(); avancar(90); relatar();")
        self.assertNotEqual(curto["passo"], longo["passo"])

    def test_avisa_ao_fechar_a_aba_so_enquanto_esta_gerando(self):
        antes = self._rodar("relatar_unload();")
        durante = self._rodar("submeter(); relatar_unload();")
        depois = self._rodar("submeter(); ultimoXhr.disparar('error'); relatar_unload();")
        self.assertFalse(antes["bloqueou"])
        self.assertTrue(durante["bloqueou"])
        self.assertFalse(depois["bloqueou"])

    def test_sem_o_painel_no_dom_o_js_nao_explode(self):
        """Null-guard: se um refactor tirar o painel, o form volta ao POST normal."""
        r = self._rodar("submeter(); relatar();", prelude="removerPainel();")
        self.assertEqual(r["envios"], 0)          # não interceptou -> POST normal do browser
        self.assertFalse(r["erroJs"])


_SHIM = r"""
'use strict';
// ── shim de DOM mínimo: só o que o JS do progresso usa ──────────────────────
var agora = 0;                                   // relógio falso (Date.now)
var timers = [];
function El(tag, attrs){
  this.tagName = tag; this.attrs = attrs || {}; this.style = {};
  this.listeners = {}; this.disabled = false; this.textContent = '';
}
El.prototype.addEventListener = function(ev, fn){
  (this.listeners[ev] = this.listeners[ev] || []).push(fn);
};
El.prototype.getAttribute = function(k){ return this.attrs[k]; };
El.prototype.querySelector = function(sel){
  return sel.indexOf('submit') >= 0 ? botao : null;
};
El.prototype.disparar = function(ev, obj){
  var d = obj || {defaultPrevented:false, preventDefault:function(){this.defaultPrevented=true;}};
  (this.listeners[ev] || []).forEach(function(f){ f(d); });
  return d;
};

var form   = new El('form', {action: '/curadoria'});
var painel = new El('div');  painel.style.display = 'none';
var passo  = new El('div');
var crono  = new El('div');
var botao  = new El('button', {type: 'submit'});  botao.textContent = 'Enviar';

var mapa = {'up-x': form, 'up-x-prog': painel, 'up-x-passo': passo, 'up-x-crono': crono};
function removerPainel(){ delete mapa['up-x-prog']; }

var envios = 0, ultimoXhr = null, erroJs = false;
function XHRFalso(){
  this.upload = new El('upload');
  this.listeners = {}; this.responseURL = '';
}
XHRFalso.prototype.addEventListener = El.prototype.addEventListener;
XHRFalso.prototype.disparar = El.prototype.disparar;
XHRFalso.prototype.open = function(){};
XHRFalso.prototype.send = function(){ envios++; };

global.XMLHttpRequest = XHRFalso;
global.FormData = function(){};
global.Date = {now: function(){ return agora; }};
global.setInterval = function(fn, ms){ timers.push({fn: fn, ms: ms, vivo: true}); return timers.length; };
global.clearInterval = function(i){ if (timers[i-1]) timers[i-1].vivo = false; };
global.document = {
  getElementById: function(id){ return mapa[id] || null; }
};
global.window = {
  XMLHttpRequest: XHRFalso,
  location: {href: ''},
  listeners: {},
  addEventListener: function(ev, fn){ (this.listeners[ev] = this.listeners[ev] || []).push(fn); }
};

function submeter(){
  try {
    var ev = form.disparar('submit');
    // o browser só faz o POST nativo se o JS NÃO chamou preventDefault
    if (!ev.defaultPrevented) return;
    ultimoXhr = ultimoXhrDoSend();
  } catch (e) { erroJs = true; }
}
var _criados = [];
var _origSend = XHRFalso.prototype.send;
XHRFalso.prototype.send = function(){ _criados.push(this); _origSend.call(this); };
function ultimoXhrDoSend(){ return _criados[_criados.length - 1] || null; }

function avancar(seg){                            // avança o relógio e roda os ticks
  for (var s = 1; s <= seg; s++){
    agora += 1000;
    timers.forEach(function(t){ if (t.vivo) t.fn(); });
  }
}
function relatar(){
  console.log(JSON.stringify({
    btnDisabled: botao.disabled, btnTexto: botao.textContent,
    painelDisplay: painel.style.display, passo: passo.textContent,
    crono: crono.textContent, envios: envios, href: window.location.href,
    erroJs: erroJs
  }));
}
function relatar_unload(){
  var d = {defaultPrevented: false, preventDefault: function(){ this.defaultPrevented = true; }};
  (window.listeners['beforeunload'] || []).forEach(function(f){ f(d); });
  console.log(JSON.stringify({bloqueou: d.defaultPrevented}));
}
"""


if __name__ == "__main__":
    unittest.main()
