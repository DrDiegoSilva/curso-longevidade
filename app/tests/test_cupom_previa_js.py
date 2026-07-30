"""Comportamento REAL do JS da prévia do cupom (o que a página envia pro navegador),
mais o contrato entre o markup de `pagina_assinar` e os seletores desse JS.

Achados cobertos (revisão final fatiada, 2026-07-29):
- Important site_web.py:2122 — aplicar cupom RESETAVA a escolha de parcelas pra 1x em
  silêncio (quem escolheu 12x podia fechar sem perceber: R$ 997 numa cobrança em vez
  de 12x de R$ 83).
- Important — nenhum teste assegurava que `pagina_assinar` emite os hooks de DOM que o
  JS procura (`sum-price`, `cupom-aplicar`, `cupom-input`, `cupom-msg`). O JS é todo
  null-guarded: um refactor de markup DESLIGA a feature inteira com a suíte verde.
- Minor — Enter no campo do cupom submetia o PEDIDO em vez de conferir o cupom.
- (bônus) guarda de campo vazio no cliente, par da guarda do servidor.

Como o JS é testado de verdade: o `<script>` é EXTRAÍDO da página gerada (nunca uma
cópia colada aqui — uma cópia testaria a cópia) e roda no `node` sobre um shim de DOM
mínimo, definido em `_SHIM`. O shim reproduz de propósito a regra do HTML que causa o
bug: um `<select>` sem nenhuma `<option>` marcada auto-seleciona a PRIMEIRA
("selectedness" do WHATWG) — é ela que transformava o rebuild em "voltou pra 1x".

`node` não é dependência do projeto (a app é stdlib puro e a página não carrega JS
externo): sem `node` no PATH estes testes são SKIPADOS, não falham. O contrato de
markup (`TestContratoMarkupJs`) é Python puro e roda sempre.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_NODE = shutil.which("node")


def _pagina(slug="anual"):
    for m in ("config", "site_web", "pricing", "db"):
        sys.modules.pop(m, None)
    import site_web
    return site_web.pagina_assinar(slug)


def _extrair_script(html):
    """O <script> da prévia (o que menciona o botão Aplicar), sem as tags."""
    for corpo in re.findall(r"<script>(.*?)</script>", html, re.S):
        if "cupom-aplicar" in corpo:
            return corpo
    raise AssertionError("o <script> da prévia do cupom não está na página")


_SHIM = r"""
'use strict';
// ── shim de DOM mínimo (só o que o JS da prévia usa) ──────────────────────────
function El(tag, attrs){
  this.tagName = tag; this.attrs = attrs || {}; this.style = {};
  this.children = []; this._texto = ''; this.listeners = {}; this.disabled = false;
  if (tag !== 'select') this.value = this.attrs.value === undefined ? '' : this.attrs.value;
}
Object.defineProperty(El.prototype, 'textContent', {
  get: function(){
    var meu = this._texto;
    return meu + this.children.map(function(c){ return c.textContent; }).join('');
  },
  set: function(v){ this._texto = String(v); this.children = []; }
});
El.prototype.getAttribute = function(nome){
  return this.attrs[nome] === undefined ? null : this.attrs[nome];
};
El.prototype.addEventListener = function(tipo, fn){
  (this.listeners[tipo] = this.listeners[tipo] || []).push(fn);
};
El.prototype.disparar = function(tipo, ev){
  (this.listeners[tipo] || []).forEach(function(fn){ fn(ev); });
};
El.prototype.appendChild = function(no){ this.children.push(no); return no; };
El.prototype.querySelector = function(sel){
  for (var i = 0; i < this.children.length; i++)
    if (this.children[i].tagName === sel) return this.children[i];
  return null;
};

var CFG = JSON.parse(process.argv[2]);
var registro = {};
var btn = new El('button', {id: 'cupom-aplicar'});
var input = new El('input', {id: 'cupom-input', value: CFG.valor_input});
input.value = CFG.valor_input;
var msg = new El('span', {id: 'cupom-msg'});
var sumPrice = new El('div', {id: 'sum-price', 'data-base': CFG.preco_base});
sumPrice.textContent = CFG.preco_inicial;
var periodo = new El('span', {});
periodo.textContent = CFG.periodo;
sumPrice.appendChild(periodo);
// as outras DUAS figuras de dinheiro da tela, cada uma com o baseline que o servidor
// renderizou no `data-base` (é a ele que a tela volta quando não há cupom aplicado).
var pixDesc = new El('span', {id: 'pt-desc-pix', 'data-base': CFG.pix_base});
pixDesc.textContent = CFG.pix_base;
var cartaoDesc = new El('span', {id: 'pt-desc-cartao', 'data-base': CFG.cartao_base});
cartaoDesc.textContent = CFG.cartao_base;
// Escolha de contrato no cartão: à vista (1) ou parcelado (12). São RÁDIOS, não um
// <select> reconstruído — é o que torna "a escolha foi resetada em silêncio"
// impossível por construção, e não por cuidado do JS.
var campoParcelas = new El('div', {id: 'parcelas-field'});
var parceladoDesc = new El('span', {id: 'pt-desc-parcelado', 'data-base': CFG.parcelado_base});
parceladoDesc.textContent = CFG.parcelado_base;
var parcelasRadios = ['1', '12'].map(function(v){
  var r = new El('input', {name: 'parcelas', value: v});
  r.value = v;
  r.checked = (v === String(CFG.parcelas_escolhida));
  campoParcelas.appendChild(r);
  return r;
});
campoParcelas.appendChild(parceladoDesc);
var planoInput = new El('input', {id: '', value: 'anual'});
planoInput.value = 'anual';
// rádios de forma de pagamento (o `checked` é o que a página lê pra saber o método)
var radios = (CFG.metodos || ['PIX', 'CARTAO']).map(function(v){
  var r = new El('input', {name: 'metodo', value: v});
  r.value = v;
  r.checked = (v === (CFG.metodo_inicial || 'CARTAO'));
  return r;
});

registro['#cupom-aplicar'] = btn;
registro['#cupom-input'] = input;
registro['#cupom-msg'] = msg;
registro['#sum-price'] = sumPrice;
registro['#pt-desc-pix'] = CFG.sem_tile_pix ? null : pixDesc;
registro['#pt-desc-cartao'] = cartaoDesc;
registro['#parcelas-field'] = CFG.sem_campo_parcelas ? null : campoParcelas;
registro['#pt-desc-parcelado'] = CFG.sem_campo_parcelas ? null : parceladoDesc;
registro['input[name="plano"]'] = planoInput;

var document = {
  getElementById: function(id){ return registro['#' + id] || null; },
  querySelector: function(sel){
    if (sel === 'input[name="metodo"]:checked') {
      for (var i = 0; i < radios.length; i++) if (radios[i].checked) return radios[i];
      return null;
    }
    return registro[sel] || null;
  },
  querySelectorAll: function(sel){
    if (sel === 'input[name="metodo"]') return radios;
    if (sel === 'input[name="parcelas"]') return parcelasRadios;
    return [];
  },
  createElement: function(tag){ return new El(tag, {}); }
};
var fetches = [];
var fila = (CFG.respostas || []).slice();
var fetch = function(url, opts){
  var corpo = String(opts.body);
  fetches.push({url: url, body: corpo, metodo: opts.method});
  // `rejeitar_apos: N` -> da N-ésima chamada em diante a rede falha (1-indexado)
  if (CFG.rejeitar_apos && fetches.length >= CFG.rejeitar_apos)
    return Promise.reject(new Error('rede caiu'));
  // `atrasos: [ms, ...]` -> resposta i chega depois de ms (pra testar fora de ordem)
  var atraso = (CFG.atrasos || [])[fetches.length - 1] || 0;
  var d;
  if (fila.length) d = fila.length > 1 ? fila.shift() : fila[0];
  else if (CFG.por_metodo) {
    var m = /metodo=([A-Z]*)/.exec(corpo);
    d = CFG.por_metodo[m ? m[1] : ''];
  } else d = CFG.resposta;
  var resposta = {json: function(){ return Promise.resolve(d); }};
  if (!atraso) return Promise.resolve(resposta);
  return new Promise(function(ok){ setTimeout(function(){ ok(resposta); }, atraso); });
};
var prevenidos = 0;
"""

_DRIVER = r"""
// ── passos + coleta ───────────────────────────────────────────────────────────
// Um passo por macrotask: entre dois passos as .then de um fetch já resolvido
// terminam, então o passo seguinte enxerga a tela como o visitante enxergaria.
// `passos: []` (lista vazia, explícita) = NÃO faz nada — só carrega a página. Sem
// `passos` nenhum, cai no driver antigo (`cliques` × `acao`).
var passos = CFG.passos ? CFG.passos.slice() : null;
if (passos === null) {
  passos = [];
  for (var c = 0; c < (CFG.cliques || 1); c++)
    passos.push({tipo: CFG.acao === 'enter' ? 'enter' : 'click'});
}
function evento(){
  return {key: CFG.tecla || 'x', keyCode: CFG.tecla === 'Enter' ? 13 : 88,
          preventDefault: function(){ prevenidos++; }};
}
function executar(p){
  if (p.tipo === 'click') { btn.disparar('click', evento()); return; }
  if (p.tipo === 'enter') { input.disparar('keydown', evento()); return; }
  if (p.tipo === 'digitar') { input.value = p.valor; input.disparar('input', {}); return; }
  if (p.tipo === 'escolher_parcelas') {   // como o navegador: marca um, desmarca o outro
    parcelasRadios.forEach(function(r){ r.checked = (r.value === String(p.valor)); });
    return;
  }
  if (p.tipo === 'metodo') {          // como o navegador: marca um, desmarca os outros
    radios.forEach(function(r){ r.checked = (r.value === p.valor); });
    for (var i = 0; i < radios.length; i++)
      if (radios[i].checked) { radios[i].disparar('change', {}); return; }
    return;
  }
  throw new Error('passo desconhecido: ' + p.tipo);
}
function coletar(){
  console.log(JSON.stringify({
    parcelas_marcada: (parcelasRadios.filter(function(r){ return r.checked; })[0] || {value: ''}).value,
    parcelas_disabled: parcelasRadios.map(function(r){ return r.disabled; }),
    parcelado_desc: parceladoDesc.textContent,
    parcelas_display: campoParcelas.style.display === undefined
                        ? null : String(campoParcelas.style.display),
    msg: msg.textContent,
    msg_cor: msg.style.color || '',
    preco: sumPrice.textContent,
    filhos_preco: sumPrice.children.map(function(c){ return c.tagName; }),
    pix_desc: pixDesc.textContent,
    cartao_desc: cartaoDesc.textContent,
    fetches: fetches,
    prevenidos: prevenidos,
    btn_disabled: btn.disabled
  }));
}
function rodar(i){
  // `espera`: tempo extra no fim, pra respostas ATRASADAS ainda chegarem antes da coleta
  if (i >= passos.length) { setTimeout(coletar, CFG.espera || 0); return; }
  executar(passos[i]);
  setTimeout(function(){ rodar(i + 1); }, 0);
}
rodar(0);
"""


def _parcelas_payload(ns, por_parcela="R$ 83,08", total="R$ 997,00"):
    return [{"parcelas": n, "por_parcela": por_parcela, "total": total} for n in ns]


# Respostas realistas do `POST /assinar/cupom` pro anual com LANCAMENTO (−R$ 500).
# `parcelas` é IGUAL nas duas: o parcelamento sai sempre da base do CARTÃO (997), nunca
# do Pix (947,15) — Pix é à vista.
_RESP_CARTAO = {"ok": True, "preco": "R$ 997,00", "msg": "−R$ 500,00 aplicado",
                "pix_desc": "R$ 947,15 à vista",
                "cartao_desc": "à vista ou parcelado",
                "parcelado_desc": "em até 12x de R$ 83,08",
                "parcelas": _parcelas_payload(range(1, 13))}
_RESP_PIX = dict(_RESP_CARTAO, preco="R$ 947,15")


class _HarnessJs:
    """Roda o JS DA PÁGINA (extraído, não copiado) sobre o shim de DOM. Mixin: as
    classes de teste herdam daqui + `unittest.TestCase` (herdar de uma TestCase
    concreta re-rodaria os testes dela)."""

    @classmethod
    def setUpClass(cls):
        cls.script = _extrair_script(_pagina("anual"))
        cls.tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _rodar(self, script=None, **cfg):
        base = {"valor_input": "LANCAMENTO", "preco_inicial": "R$ 1.497",
                "preco_base": "R$ 1.497", "periodo": "por ano",
                "parcelado_base": "em até 12x de R$ 124,75",
                "pix_base": "R$ 1.422,15 à vista",
                "cartao_base": "à vista ou parcelado",
                "metodos": ["PIX", "CARTAO"], "metodo_inicial": "CARTAO",
                "parcelas_escolhida": "1", "acao": "click", "sem_campo_parcelas": False,
                "sem_tile_pix": False, "resposta": dict(_RESP_CARTAO)}
        base.update(cfg)
        caminho = os.path.join(self.tmp, "harness.js")
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(_SHIM + (script if script is not None else self.script) + _DRIVER)
        p = subprocess.run([_NODE, caminho, json.dumps(base)], capture_output=True,
                           text=True, timeout=60)
        self.assertEqual(p.returncode, 0, f"node falhou:\n{p.stderr}")
        self.assertEqual(p.stderr.strip(), "", f"o JS não pode emitir erro/aviso: {p.stderr}")
        return json.loads(p.stdout)


@unittest.skipUnless(_NODE, "node não está no PATH — teste de comportamento do JS")
class TestJsDaPrevia(_HarnessJs, unittest.TestCase):
    """Roda o JS DA PÁGINA (extraído, não copiado) sobre o shim de DOM."""

    # ── A escolha de contrato no cartão não pode ser mexida pela prévia ──
    def test_parcelado_sobrevive_ao_cupom(self):
        """Origem: quem escolheu 12x e aplicava um cupom era movido pra 1x em silêncio
        (R$ 997 numa cobrança em vez de 12x de R$ 83). Com rádios não há rebuild que
        possa mover a escolha — este teste é a trava de que ninguém reintroduza um."""
        r = self._rodar(parcelas_escolhida="12")
        self.assertEqual(r["parcelas_marcada"], "12")
        self.assertEqual(r["msg"], "−R$ 500,00 aplicado",
                         "nada de aviso de ajuste: a escolha não foi tocada")

    def test_a_vista_continua_a_vista(self):
        r = self._rodar(parcelas_escolhida="1")
        self.assertEqual(r["parcelas_marcada"], "1")

    def test_cupom_repinta_a_cifra_do_parcelado(self):
        """A opção "parcelado" mostra dinheiro ("até 12x de R$ 124,75"), então é a
        QUARTA figura da tela. Se a prévia não repintar, ela fica com o valor SEM o
        cupom — a mesma mentira que o tile do Pix contava em 2026-07-29."""
        r = self._rodar(parcelas_escolhida="12")
        self.assertEqual(r["parcelado_desc"], "em até 12x de R$ 83,08")

    def test_sem_campo_de_parcelas_no_plano_mensal_nao_explode(self):
        r = self._rodar(parcelas_escolhida="1", sem_campo_parcelas=True)
        self.assertEqual(r["msg"], "−R$ 500,00 aplicado")
        self.assertEqual(len(r["fetches"]), 1)

    # ── Minor: Enter no campo do cupom ──
    def test_enter_no_campo_roda_a_previa_e_nao_submete_o_pedido(self):
        r = self._rodar(acao="enter", tecla="Enter")
        self.assertEqual(len(r["fetches"]), 1,
                         "Enter no campo do cupom tem que conferir o cupom")
        self.assertEqual(r["prevenidos"], 1,
                         "sem preventDefault, o Enter submete o FORM inteiro (o pedido) "
                         "em vez de rodar a prévia")
        self.assertEqual(r["parcelas_marcada"], "1")

    def test_outra_tecla_nao_dispara_nada(self):
        r = self._rodar(acao="enter", tecla="a")
        self.assertEqual(r["fetches"], [])
        self.assertEqual(r["prevenidos"], 0)

    # ── guarda de campo vazio no cliente (par da do servidor) ──
    def test_campo_vazio_nao_chega_a_chamar_o_servidor(self):
        r = self._rodar(valor_input="   ")
        self.assertEqual(r["fetches"], [],
                         "campo em branco não pode virar requisição (no servidor ele "
                         "também não conta tentativa)")
        self.assertTrue(r["msg"].strip(), "tem que avisar o visitante")

    # ── propriedades que a revisão confirmou OK e não podem regredir ──
    def test_span_do_periodo_sobrevive_a_cliques_repetidos(self):
        r = self._rodar()
        self.assertEqual(r["filhos_preco"], ["span"],
                         "o <span> do período tem que ser reencaixado (mesmo nó)")
        self.assertEqual(r["preco"], "R$ 997,00por ano")

    def test_cinco_cliques_seguidos_nao_duplicam_nem_perdem_o_span(self):
        """Propriedade que a revisão confirmou OK e não pode regredir: o mesmo nó do
        <span> é reencaixado, então clicar várias vezes não duplica o período nem o
        perde — e as parcelas continuam onde o visitante deixou."""
        r = self._rodar(parcelas_escolhida="12", cliques=5)
        self.assertEqual(r["filhos_preco"], ["span"])
        self.assertEqual(r["preco"], "R$ 997,00por ano")
        self.assertEqual(r["parcelas_marcada"], "12")
        self.assertEqual(r["parcelado_desc"], "em até 12x de R$ 83,08",
                         "a cifra do parcelado não pode concatenar a cada clique")
        self.assertEqual(len(r["fetches"]), 5)
        self.assertEqual(r["msg"], "−R$ 500,00 aplicado", "a mensagem não pode concatenar")

    def test_o_codigo_vai_pro_servidor_normalizado(self):
        r = self._rodar(valor_input="  lancamento  ")
        self.assertEqual(len(r["fetches"]), 1)
        self.assertEqual(r["fetches"][0]["url"], "/assinar/cupom")
        self.assertIn("cupom=lancamento", r["fetches"][0]["body"],
                      "o valor vai sem os espaços das pontas (o servidor faz upper)")
        self.assertIn("plano=anual", r["fetches"][0]["body"])
        self.assertIn("metodo=CARTAO", r["fetches"][0]["body"])

    def test_resposta_de_falha_nao_mexe_em_preco_nem_parcelas(self):
        r = self._rodar(parcelas_escolhida="12",
                        resposta={"ok": False, "msg": "Cupom inválido."})
        self.assertEqual(r["msg"], "Cupom inválido.")
        self.assertEqual(r["preco"], "R$ 1.497por ano")
        self.assertEqual(r["parcelas_marcada"], "12")
        self.assertEqual(r["parcelado_desc"], "em até 12x de R$ 124,75",
                         "cupom recusado tem que deixar a cifra do parcelado no baseline")
        self.assertFalse(r["btn_disabled"], "o botão tem que voltar a funcionar")


@unittest.skipUnless(_NODE, "node não está no PATH — teste de comportamento do JS")
class TestJsMetodoEFiguras(_HarnessJs, unittest.TestCase):
    """BUG AO VIVO (2026-07-29, achado dirigindo a página deployada, minutos depois do
    deploy): a prévia atualizava só o resumo, e TROCAR A FORMA DE PAGAMENTO não
    atualizava nada — a página prometia R$ 947,15 (Pix) num cartão que cobraria
    R$ 997,00, R$ 49,85 a menos do que a cobrança. Nenhum dos 962 testes pegou: o
    servidor respondia certo, era a página que segurava uma resposta velha.

    Estes testes dirigem o JS DA PÁGINA (extraído, não copiado) como o visitante:
    clicar em Aplicar, trocar o rádio de método, editar a caixa do cupom."""

    _POR_METODO = {"CARTAO": dict(_RESP_CARTAO), "PIX": dict(_RESP_PIX)}

    def _metodo(self, valor):
        return {"tipo": "metodo", "valor": valor}

    # ── 1. trocar de método com cupom aplicado reprecifica as TRÊS figuras ──
    def test_trocar_para_pix_com_cupom_aplicado_atualiza_as_tres_figuras(self):
        r = self._rodar(por_metodo=self._POR_METODO, resposta=None,
                        passos=[{"tipo": "click"}, self._metodo("PIX")])
        self.assertEqual(len(r["fetches"]), 2,
                         "trocar de método tem que refazer a prévia — senão as figuras "
                         "ficam do método anterior")
        self.assertIn("metodo=PIX", r["fetches"][1]["body"])
        self.assertEqual(r["preco"], "R$ 947,15por ano", "o resumo tem que seguir o método")
        self.assertEqual(r["pix_desc"], "R$ 947,15 à vista",
                         "o tile do Pix tem que levar o cupom (mostrava 1.422,15 ao vivo)")
        self.assertEqual(r["parcelado_desc"], "em até 12x de R$ 83,08",
                         "parcelas são do CARTÃO: 78,93/947,15 (Pix parcelado) não existe")

    def test_trocar_para_cartao_com_cupom_aplicado_tambem_reprecifica(self):
        r = self._rodar(metodo_inicial="PIX", por_metodo=self._POR_METODO, resposta=None,
                        passos=[{"tipo": "click"}, self._metodo("CARTAO")])
        self.assertEqual(len(r["fetches"]), 2)
        self.assertIn("metodo=PIX", r["fetches"][0]["body"])
        self.assertIn("metodo=CARTAO", r["fetches"][1]["body"])
        self.assertEqual(r["preco"], "R$ 997,00por ano",
                         "com o cartão marcado a tela não pode mostrar o preço do Pix — "
                         "era exatamente a promessa de R$ 49,85 a menos do que a cobrança")

    def test_ir_e_voltar_de_metodo_nao_deixa_figura_do_outro_metodo(self):
        r = self._rodar(por_metodo=self._POR_METODO, resposta=None,
                        passos=[{"tipo": "click"}, self._metodo("PIX"),
                                self._metodo("CARTAO"), self._metodo("PIX")])
        self.assertEqual(len(r["fetches"]), 4)
        self.assertEqual(r["preco"], "R$ 947,15por ano")
        self.assertEqual(r["filhos_preco"], ["span"], "o período não pode se perder")

    def test_parcelas_escolhidas_sobrevivem_a_troca_de_metodo(self):
        r = self._rodar(por_metodo=self._POR_METODO, resposta=None,
                        parcelas_escolhida="12",
                        passos=[{"tipo": "click"}, self._metodo("PIX")])
        self.assertEqual(r["parcelas_marcada"], "12")
        self.assertEqual(r["msg"], "−R$ 500,00 aplicado", "sem aviso de ajuste à toa")

    # ── 2. sem cupom aplicado: volta pro baseline do SERVIDOR, sem requisição ──
    def test_trocar_de_metodo_sem_cupom_nao_chama_o_servidor(self):
        r = self._rodar(valor_input="", passos=[self._metodo("PIX"),
                                               self._metodo("CARTAO"),
                                               self._metodo("PIX")])
        self.assertEqual(r["fetches"], [],
                         "caixa vazia + troca de método não pode gastar requisição "
                         "(nem cota de tentativas) nenhuma")
        self.assertEqual(r["preco"], "R$ 1.497por ano")
        self.assertEqual(r["pix_desc"], "R$ 1.422,15 à vista")
        self.assertEqual(r["parcelado_desc"], "em até 12x de R$ 124,75")

    def test_apagar_o_cupom_e_trocar_de_metodo_volta_o_baseline(self):
        """Sem isto a tela ficaria com o desconto de um cupom que não está mais na
        caixa: mostrado MENOR que o cobrado."""
        r = self._rodar(por_metodo=self._POR_METODO, resposta=None,
                        passos=[{"tipo": "click"}, {"tipo": "digitar", "valor": ""},
                                self._metodo("PIX")])
        self.assertEqual(len(r["fetches"]), 1, "sem cupom aplicado não há o que reconferir")
        self.assertEqual(r["preco"], "R$ 1.497por ano")
        self.assertEqual(r["pix_desc"], "R$ 1.422,15 à vista")
        self.assertEqual(r["cartao_desc"], "à vista ou parcelado")
        self.assertEqual(r["parcelado_desc"], "em até 12x de R$ 124,75",
                         "a cifra do parcelado tem que voltar à que o servidor renderizou")

    def test_editar_o_codigo_depois_de_aplicar_volta_o_baseline_na_hora(self):
        r = self._rodar(por_metodo=self._POR_METODO, resposta=None,
                        passos=[{"tipo": "click"}, {"tipo": "digitar", "valor": "OUTROCODIGO"}])
        self.assertEqual(len(r["fetches"]), 1)
        self.assertEqual(r["preco"], "R$ 1.497por ano",
                         "o desconto do código ANTIGO não pode ficar na tela com um "
                         "código novo (não conferido) na caixa")
        self.assertEqual(r["msg"], "", "a mensagem do cupom anterior também sai")

    def test_mudar_so_a_caixa_alta_do_mesmo_codigo_continua_aplicado(self):
        # o servidor faz upper(): "lancamento" e "LANCAMENTO" são o MESMO cupom, então
        # trocar de método continua reconferindo (e o preço não volta pro cheio).
        r = self._rodar(valor_input="lancamento", por_metodo=self._POR_METODO,
                        resposta=None,
                        passos=[{"tipo": "click"}, {"tipo": "digitar", "valor": "Lancamento"},
                                self._metodo("PIX")])
        self.assertEqual(len(r["fetches"]), 2)
        self.assertEqual(r["preco"], "R$ 947,15por ano")

    def test_falha_depois_de_um_valido_tira_o_desconto_da_tela(self):
        """Cupom desativado no admin entre dois cliques: a tela não pode continuar
        mostrando o desconto que o checkout já não vai dar."""
        r = self._rodar(resposta=None,
                        respostas=[dict(_RESP_CARTAO), {"ok": False, "msg": "Cupom inválido."}],
                        passos=[{"tipo": "click"}, {"tipo": "click"}])
        self.assertEqual(r["msg"], "Cupom inválido.")
        self.assertEqual(r["preco"], "R$ 1.497por ano")
        self.assertEqual(r["pix_desc"], "R$ 1.422,15 à vista")

    def test_rede_caindo_na_troca_de_metodo_nao_deixa_preco_baixo_na_tela(self):
        """O caminho mais traiçoeiro do reprecificar-na-troca: a prévia do Pix deu certo
        (R$ 947,15 na tela), o visitante marca Cartão e a reconferência FALHA. Manter o
        valor de antes prometeria R$ 49,85 menos do que o cartão cobra — a tela volta
        pro preço de tabela e diz que não deu pra conferir."""
        r = self._rodar(metodo_inicial="PIX", por_metodo=self._POR_METODO, resposta=None,
                        rejeitar_apos=2,
                        passos=[{"tipo": "click"}, self._metodo("CARTAO")])
        self.assertEqual(len(r["fetches"]), 2)
        self.assertEqual(r["preco"], "R$ 1.497por ano")
        self.assertEqual(r["pix_desc"], "R$ 1.422,15 à vista")
        self.assertIn("não foi possível", r["msg"].lower())
        self.assertFalse(r["btn_disabled"], "o botão tem que voltar a funcionar")

    def test_resposta_atrasada_do_metodo_antigo_nao_repinta_a_tela(self):
        """Com o cupom aplicado, duas trocas rápidas deixam DUAS conferências no ar. Se
        a do método ANTIGO voltar por último, ela repinta a tela com o valor do outro
        método — a mesma classe de "a página segurou uma resposta velha" que este fix
        existe pra matar. Aqui a prévia do Pix (947,15) demora e a do Cartão (997,00)
        chega antes: a tela tem que acabar no CARTÃO, o método que está marcado."""
        r = self._rodar(por_metodo=self._POR_METODO, resposta=None,
                        atrasos=[0, 120, 0], espera=400,
                        passos=[{"tipo": "click"}, self._metodo("PIX"),
                                self._metodo("CARTAO")])
        self.assertEqual(len(r["fetches"]), 3)
        self.assertIn("metodo=PIX", r["fetches"][1]["body"])
        self.assertIn("metodo=CARTAO", r["fetches"][2]["body"])
        self.assertEqual(r["preco"], "R$ 997,00por ano",
                         "a resposta atrasada do Pix não pode vencer a do Cartão")
        self.assertEqual(r["parcelas_display"], "", "e o campo de parcelas volta")
        self.assertFalse(r["btn_disabled"])

    def test_rede_caindo_no_primeiro_clique_nao_mexe_em_dinheiro(self):
        r = self._rodar(rejeitar_apos=1, passos=[{"tipo": "click"}])
        self.assertEqual(r["preco"], "R$ 1.497por ano")
        self.assertIn("não foi possível", r["msg"].lower())

    # ── 3. código INVÁLIDO na caixa não pode virar cota queimada por troca de rádio ──
    def test_trocar_de_metodo_com_codigo_invalido_nao_gasta_cota(self):
        """A cota é 5 tentativas/10min por IP, compartilhada com o fechamento: se cada
        clique no rádio de método reconferisse um código inválido, o visitante se
        trancaria fora sozinho — e o cupom BOM dele seria recusado no checkout."""
        r = self._rodar(valor_input="CHUTE", resposta={"ok": False, "msg": "Cupom inválido."},
                        passos=[{"tipo": "click"}, self._metodo("PIX"),
                                self._metodo("CARTAO"), self._metodo("PIX"),
                                self._metodo("CARTAO")])
        self.assertEqual(len(r["fetches"]), 1,
                         "só o clique em Aplicar podia falar com o servidor: 4 trocas de "
                         "método com código inválido queimariam a cota inteira")
        self.assertEqual(r["msg"], "Cupom inválido.")

    def test_troca_de_metodo_com_a_caixa_intocada_nunca_chama_nada(self):
        r = self._rodar(valor_input="   ", passos=[self._metodo("PIX"), self._metodo("CARTAO")])
        self.assertEqual(r["fetches"], [])

    # ── 4. Pix é à vista: o campo de parcelas não existe nesse método ──
    def test_pix_esconde_o_campo_de_parcelas_desde_o_carregamento(self):
        r = self._rodar(metodo_inicial="PIX", passos=[])
        self.assertEqual(r["parcelas_display"], "none",
                         "com Pix marcado (o default do anual) não se oferece parcela")
        self.assertEqual(r["fetches"], [], "esconder o campo não fala com o servidor")

    def test_cartao_mostra_o_campo_de_parcelas(self):
        r = self._rodar(metodo_inicial="CARTAO", passos=[])
        self.assertEqual(r["parcelas_display"], "")

    def test_trocar_entre_metodos_esconde_e_mostra_o_campo(self):
        pix = self._rodar(valor_input="", passos=[self._metodo("PIX")])
        self.assertEqual(pix["parcelas_display"], "none")
        volta = self._rodar(metodo_inicial="PIX", valor_input="",
                            passos=[self._metodo("PIX"), self._metodo("CARTAO")])
        self.assertEqual(volta["parcelas_display"], "")

    def test_os_radios_continuam_habilitados_e_marcados(self):
        """Esconder, não desabilitar: o `POST /assinar` lê `parcelas` e o campo tem que
        continuar submetendo o mesmo name/value de sempre (no Pix o servidor já ignora
        esse campo — ver asaas.montar_checkout)."""
        r = self._rodar(metodo_inicial="PIX", parcelas_escolhida="12", valor_input="",
                        passos=[self._metodo("PIX")])
        self.assertEqual(r["parcelas_disabled"], [False, False])
        self.assertEqual(r["parcelas_marcada"], "12")

    # ── robustez: markup do mensal (sem tile de Pix, sem parcelas) e resposta antiga ──
    def test_plano_sem_tile_de_pix_e_sem_parcelas_nao_explode(self):
        r = self._rodar(sem_tile_pix=True, sem_campo_parcelas=True, metodos=["CARTAO"],
                        passos=[{"tipo": "click"}])
        self.assertEqual(r["msg"], "−R$ 500,00 aplicado")
        self.assertEqual(len(r["fetches"]), 1)
        self.assertIsNone(r["parcelas_display"],
                          "sem campo de parcelas o script não mexe em estilo nenhum")

    def test_resposta_sem_as_figuras_novas_nao_apaga_dinheiro_da_tela(self):
        """Defesa contra branco na tela: uma resposta sem `pix_desc`/`cartao_desc`/
        `parcelado_desc` (formato antigo, cache de proxy) atualiza o que veio e deixa o
        resto como está — em vez de escrever "undefined" onde havia um preço."""
        r = self._rodar(resposta={"ok": True, "preco": "R$ 997,00", "msg": "ok",
                                  "parcelas": _parcelas_payload(range(1, 13))},
                        passos=[{"tipo": "click"}])
        self.assertEqual(r["preco"], "R$ 997,00por ano")
        self.assertEqual(r["pix_desc"], "R$ 1.422,15 à vista")
        self.assertEqual(r["cartao_desc"], "à vista ou parcelado")
        self.assertEqual(r["parcelado_desc"], "em até 12x de R$ 124,75")


class TestContratoMarkupJs(unittest.TestCase):
    """Important da revisão: o JS é todo null-guarded (`if (!btn) return;`), então
    renomear/remover um `id` no markup DESLIGA a prévia inteira sem quebrar teste
    nenhum. Este teste amarra os dois lados: TODO hook que o script procura tem que
    existir no HTML da mesma página — e os hooks conhecidos hoje têm que continuar
    sendo procurados (senão apagar o script deixaria o teste passar à toa)."""

    def setUp(self):
        self.html = _pagina("anual")
        self.script = _extrair_script(self.html)

    def test_todo_getElementById_do_script_existe_no_markup(self):
        ids = sorted(set(re.findall(r"getElementById\('([^']+)'\)", self.script)))
        self.assertEqual(ids, ["cupom-aplicar", "cupom-input", "cupom-msg",
                               "parcelas-field", "pt-desc-cartao", "pt-desc-parcelado",
                               "pt-desc-pix", "sum-price"],
                         "hooks conhecidos mudaram — confira os dois lados de propósito")
        for hook in ids:
            self.assertIn(f'id="{hook}"', self.html,
                          f'o script procura #{hook}, que não existe no markup')

    def test_todo_querySelector_do_script_casa_com_o_markup(self):
        sels = sorted(set(re.findall(
            r"""querySelectorAll?\('([a-z]+\[name="[^"]+"\][^']*)'\)""", self.script)))
        self.assertTrue(sels, "o script tem que continuar usando seletores por atributo")
        for sel in sels:
            tag, nome = re.match(r'([a-z]+)\[name="([^"]+)"\]', sel).groups()
            self.assertRegex(self.html, rf'<{tag}[^>]*name="{nome}"',
                             f'o script procura {sel}, que o markup não emite')

    def test_o_script_escuta_os_radios_de_metodo(self):
        # sem ouvir o `change` dos rádios, trocar a forma de pagamento deixa TODAS as
        # figuras do método anterior na tela (o bug ao vivo de 2026-07-29)
        self.assertIn("""querySelectorAll('input[name="metodo"]')""", self.script)
        self.assertIn("'change'", self.script)

    def test_toda_figura_de_dinheiro_carrega_o_baseline_do_servidor(self):
        """O `restaurar()` do script só pode usar strings que o SERVIDOR renderizou (a
        alternativa seria recalcular preço no cliente). Cada elemento que ele repinta
        tem que trazer o próprio baseline num `data-base`, e o baseline tem que ser
        IGUAL ao texto renderizado — senão a tela "volta" pra um valor que nunca
        esteve nela."""
        self.assertIn("getAttribute('data-base')", self.script)
        for hook in ("sum-price", "pt-desc-pix", "pt-desc-cartao", "pt-desc-parcelado"):
            m = re.search(rf'id="{hook}"[^>]*data-base="([^"]*)"[^>]*>([^<]*)', self.html)
            self.assertIsNotNone(m, f'#{hook} tem que emitir data-base')
            self.assertEqual(m.group(1), m.group(2),
                             f'o data-base de #{hook} tem que ser o texto renderizado')

    def test_baseline_do_resumo_e_o_preco_de_tabela_do_plano(self):
        import config
        preco = config.plano_por_slug("anual")["preco"]
        self.assertIn(f'id="sum-price" data-base="{preco}"', self.html)

    def test_baseline_do_tile_pix_e_o_a_vista_do_pix(self):
        # 1497 − 5% = 1.422,15 (sem cupom): é o que a página abre mostrando
        self.assertIn('id="pt-desc-pix" data-base="R$ 1.422,15 à vista"', self.html)

    def test_campo_de_parcelas_embrulha_as_duas_ofertas(self):
        # o script esconde o CAMPO inteiro no Pix; se o id ficasse num dos rádios, o
        # outro continuaria sozinho na tela num método que não parcela
        m = re.search(r'id="parcelas-field"(.*?)</div>', self.html, re.S)
        self.assertIsNotNone(m, "o campo de parcelas tem que ter id pro script achar")
        self.assertIn('name="parcelas" value="1"', m.group(1))
        self.assertIn('name="parcelas" value="12"', m.group(1))

    def test_mensal_nao_emite_tile_de_pix_nem_campo_de_parcelas(self):
        """O plano mensal não aceita Pix e é sempre 1x — o script é null-guarded pra
        isso; este teste trava o cenário que exige as guardas."""
        html = _pagina("mensal")
        self.assertNotIn('id="pt-desc-pix"', html)
        self.assertNotIn('id="parcelas-field"', html)
        self.assertIn('name="parcelas" value="1"', html)   # hidden, como hoje
        self.assertIn('id="pt-desc-cartao"', html)

    def test_o_script_nao_monta_rotulo_de_parcela_no_cliente(self):
        """O rótulo do parcelado passou a vir PRONTO do servidor (`parcelado_desc`),
        igual a `pix_desc` e `cartao_desc`. Antes ele existia em dois lugares — o markup
        e um rebuild em JS — e bastava os formatos divergirem pra aplicar um cupom
        trocar o texto sozinho. Se o script voltar a montar rótulo (ou a dividir valor)
        no navegador, os dois lados podem discordar de novo."""
        self.assertNotIn("'x de '", self.script)
        self.assertNotIn("' — total '", self.script)
        self.assertIn("pt-desc-parcelado", self.script)

    def test_radios_de_parcelas_continuam_sem_disabled_no_markup(self):
        # o campo é ESCONDIDO no Pix, nunca desabilitado: `POST /assinar` lê `parcelas`
        radios = re.findall(r'<input[^>]*name="parcelas"[^>]*>', self.html)
        self.assertEqual(len(radios), 2)
        for r in radios:
            self.assertNotIn("disabled", r)

    def test_span_do_periodo_dentro_do_sum_price(self):
        # o JS guarda `sumPrice.querySelector('span')` pra reencaixar depois do
        # textContent — sem o <span> aninhado, o período desaparece no 1º clique
        self.assertRegex(self.html, r'id="sum-price"[^>]*>[^<]*<span>')

    def test_botao_aplicar_e_type_button(self):
        # `type="submit"` (o default dentro de <form>) enviaria o pedido ao clicar
        # em Aplicar
        trecho = self.html[self.html.index('id="cupom-aplicar"') - 200:
                           self.html.index('id="cupom-aplicar"') + 40]
        self.assertIn('type="button"', trecho)

    def test_campo_do_cupom_continua_um_input_do_form(self):
        # degradação sem JS: sem `name="cupom"` dentro do <form>, quem está sem JS
        # perde o cupom no fechamento
        self.assertRegex(self.html, r'<input[^>]*id="cupom-input"[^>]*name="cupom"')

    def test_sem_innerHTML_em_lugar_nenhum(self):
        # sem os comentários // (um deles EXPLICA por que não se usa innerHTML)
        codigo = re.sub(r"//[^\n]*", "", self.script)
        self.assertNotIn("innerHTML", codigo)
        self.assertNotIn("insertAdjacentHTML", codigo)


if __name__ == "__main__":
    unittest.main()
