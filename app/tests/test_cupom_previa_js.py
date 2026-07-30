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

function Select(){
  El.call(this, 'select', {name: 'parcelas'});
  this.selectedIndex = -1;
}
Select.prototype = Object.create(El.prototype);
Select.prototype.constructor = Select;
Object.defineProperty(Select.prototype, 'options', {
  get: function(){
    return this.children.filter(function(c){ return c.tagName === 'option'; });
  }
});
Object.defineProperty(Select.prototype, 'value', {
  get: function(){
    var o = this.options[this.selectedIndex];
    return o === undefined ? '' : String(o.value);
  },
  set: function(v){
    var opts = this.options;
    for (var i = 0; i < opts.length; i++)
      if (String(opts[i].value) === String(v)) { this.selectedIndex = i; return; }
    this.selectedIndex = -1;      // valor inexistente: o browser deixa em -1/''
  }
});
Object.defineProperty(Select.prototype, 'textContent', {
  get: function(){
    return this.children.map(function(c){ return c.textContent; }).join('');
  },
  set: function(v){ this._texto = String(v); this.children = []; this.selectedIndex = -1; }
});
Select.prototype.appendChild = function(no){
  this.children.push(no);
  // REGRA DO HTML que causa o bug: <select> sem nada selecionado seleciona a 1a
  // option sozinho. É isto que fazia o rebuild "voltar pra 1x" sem ninguém pedir.
  if (this.selectedIndex < 0 && no.tagName === 'option') this.selectedIndex = 0;
  return no;
};

var CFG = JSON.parse(process.argv[2]);
var registro = {};
var btn = new El('button', {id: 'cupom-aplicar'});
var input = new El('input', {id: 'cupom-input', value: CFG.valor_input});
input.value = CFG.valor_input;
var msg = new El('span', {id: 'cupom-msg'});
var sumPrice = new El('div', {id: 'sum-price'});
sumPrice.textContent = CFG.preco_inicial;
var periodo = new El('span', {});
periodo.textContent = CFG.periodo;
sumPrice.appendChild(periodo);
var select = new Select();
CFG.parcelas_iniciais.forEach(function(n){
  var o = new El('option', {}); o.value = n; o.textContent = n + 'x';
  select.appendChild(o);
});
select.value = CFG.parcelas_escolhida;
var planoInput = new El('input', {id: '', value: 'anual'});
planoInput.value = 'anual';
var metodoEl = new El('input', {}); metodoEl.value = 'CARTAO';

registro['#cupom-aplicar'] = btn;
registro['#cupom-input'] = input;
registro['#cupom-msg'] = msg;
registro['#sum-price'] = sumPrice;
registro['select[name="parcelas"]'] = CFG.sem_select ? null : select;
registro['input[name="plano"]'] = planoInput;
registro['input[name="metodo"]:checked'] = metodoEl;

var document = {
  getElementById: function(id){ return registro['#' + id] || null; },
  querySelector: function(sel){ return registro[sel] || null; },
  createElement: function(tag){ return new El(tag, {}); }
};
var fetches = [];
var fetch = function(url, opts){
  fetches.push({url: url, body: String(opts.body), metodo: opts.method});
  return Promise.resolve({json: function(){ return Promise.resolve(CFG.resposta); }});
};
var prevenidos = 0;
"""

_DRIVER = r"""
// ── ação + coleta ─────────────────────────────────────────────────────────────
var ev = {key: CFG.tecla || 'x', keyCode: CFG.tecla === 'Enter' ? 13 : 88,
          preventDefault: function(){ prevenidos++; }};
for (var c = 0; c < (CFG.cliques || 1); c++) {
  if (CFG.acao === 'enter') input.disparar('keydown', ev);
  else btn.disparar('click', ev);
}
setTimeout(function(){          // microtasks (as .then) já rodaram
  console.log(JSON.stringify({
    select_value: select.value,
    select_opcoes: select.options.map(function(o){ return String(o.value); }),
    msg: msg.textContent,
    msg_cor: msg.style.color || '',
    preco: sumPrice.textContent,
    filhos_preco: sumPrice.children.map(function(c){ return c.tagName; }),
    fetches: fetches,
    prevenidos: prevenidos,
    btn_disabled: btn.disabled
  }));
}, 0);
"""


def _parcelas_payload(ns):
    return [{"parcelas": n, "por_parcela": "R$ 83,08", "total": "R$ 997,00"} for n in ns]


@unittest.skipUnless(_NODE, "node não está no PATH — teste de comportamento do JS")
class TestJsDaPrevia(unittest.TestCase):
    """Roda o JS DA PÁGINA (extraído, não copiado) sobre o shim de DOM."""

    @classmethod
    def setUpClass(cls):
        cls.script = _extrair_script(_pagina("anual"))
        cls.tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _rodar(self, script=None, **cfg):
        base = {"valor_input": "LANCAMENTO", "preco_inicial": "R$ 1.497",
                "periodo": "por ano", "parcelas_iniciais": list(range(1, 13)),
                "parcelas_escolhida": "1", "acao": "click", "sem_select": False,
                "resposta": {"ok": True, "preco": "R$ 997,00", "msg": "−R$ 500,00 aplicado",
                             "parcelas": _parcelas_payload(range(1, 13))}}
        base.update(cfg)
        caminho = os.path.join(self.tmp, "harness.js")
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(_SHIM + (script if script is not None else self.script) + _DRIVER)
        p = subprocess.run([_NODE, caminho, json.dumps(base)], capture_output=True,
                           text=True, timeout=60)
        self.assertEqual(p.returncode, 0, f"node falhou:\n{p.stderr}")
        self.assertEqual(p.stderr.strip(), "", f"o JS não pode emitir erro/aviso: {p.stderr}")
        return json.loads(p.stdout)

    # ── Important: a escolha de parcelas não pode ser resetada em silêncio ──
    def test_doze_vezes_sobrevive_ao_cupom(self):
        r = self._rodar(parcelas_escolhida="12")
        self.assertEqual(r["select_value"], "12",
                         "quem escolheu 12x e aplicou um cupom foi movido pra 1x — "
                         "R$ 997 numa cobrança em vez de 12x de R$ 83")
        self.assertEqual(r["select_opcoes"], [str(n) for n in range(1, 13)])
        self.assertEqual(r["msg"], "−R$ 500,00 aplicado",
                         "sem opção sumindo, não pode haver aviso de ajuste")

    def test_qualquer_escolha_intermediaria_sobrevive(self):
        for escolha in ("2", "6", "10"):
            r = self._rodar(parcelas_escolhida=escolha)
            self.assertEqual(r["select_value"], escolha)

    def test_uma_vez_continua_uma_vez(self):
        r = self._rodar(parcelas_escolhida="1")
        self.assertEqual(r["select_value"], "1")

    def test_opcao_que_sumiu_cai_no_fallback_e_AVISA(self):
        """Se a opção escolhida não existe mais na resposta, o fallback é permitido —
        o que não é permitido é ser silencioso."""
        r = self._rodar(parcelas_escolhida="12",
                        resposta={"ok": True, "preco": "R$ 997,00", "msg": "−R$ 500,00 aplicado",
                                  "parcelas": _parcelas_payload([1, 2, 3])})
        self.assertEqual(r["select_opcoes"], ["1", "2", "3"])
        self.assertEqual(r["select_value"], "1", "fallback tem que selecionar algo válido")
        self.assertNotEqual(r["msg"], "−R$ 500,00 aplicado",
                            "a mudança de parcelas tem que ficar VISÍVEL, não silenciosa")
        self.assertIn("parcelas", r["msg"].lower())

    def test_sem_select_no_plano_mensal_nao_explode(self):
        r = self._rodar(parcelas_escolhida="1", sem_select=True)
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
        self.assertEqual(r["select_value"], "1")

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
        self.assertEqual(r["select_value"], "12")
        self.assertEqual(len(r["select_opcoes"]), 12, "as opções não podem acumular")
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
        self.assertEqual(r["select_value"], "12")
        self.assertFalse(r["btn_disabled"], "o botão tem que voltar a funcionar")


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
        self.assertEqual(ids, ["cupom-aplicar", "cupom-input", "cupom-msg", "sum-price"],
                         "hooks conhecidos mudaram — confira os dois lados de propósito")
        for hook in ids:
            self.assertIn(f'id="{hook}"', self.html,
                          f'o script procura #{hook}, que não existe no markup')

    def test_todo_querySelector_do_script_casa_com_o_markup(self):
        sels = sorted(set(re.findall(r"""querySelector\('([a-z]+\[name="[^"]+"\][^']*)'\)""",
                                     self.script)))
        self.assertTrue(sels, "o script tem que continuar usando seletores por atributo")
        for sel in sels:
            tag, nome = re.match(r'([a-z]+)\[name="([^"]+)"\]', sel).groups()
            self.assertRegex(self.html, rf'<{tag}[^>]*name="{nome}"',
                             f'o script procura {sel}, que o markup não emite')

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
