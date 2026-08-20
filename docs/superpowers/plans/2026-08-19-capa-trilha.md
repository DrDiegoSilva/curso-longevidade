# Capa e página 2 do PDF da trilha — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar à peça da trilha uma capa com identidade visual (banda verde, ícone DS, assinatura, selo de semana) e resolver a página 2 quase vazia com blocos de tarefa/mentalidade mais ricos — sem forçar tudo numa página só, sem reduzir o tamanho da letra.

**Architecture:** `app/pdf_trilha.py` ganha uma nova seção de capa em `montar_html`, usando a mesma técnica de sangria (`@page` sem margem lateral + `@page :first` sem margem no topo) que `app/pdf.py` já usa pra sua própria capa — comprovado no PDF real durante o brainstorming, não é técnica nova. `config.TRILHA_NOME` muda de valor só; ele já é a fonte única lida em 4 lugares (capa, rodapé do PDF, título do portal, legenda do WhatsApp), então a mudança propaga sem tocar nos outros arquivos.

**Tech Stack:** Python 3 stdlib puro, Chromium headless via `pdf.gerar_pdf` (já existe, não muda), `unittest`.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-08-19-capa-trilha-design.md`. Ler antes de começar.
- **Suíte:** `cd app && python3 -m unittest discover -s tests` — verde ao fim de cada task.
- **Python 3 stdlib puro.** Sem dependência nova (nem Pillow em runtime — o processamento de imagem já foi feito fora do código de produção; o resultado é uma string base64 fixa).
- **Todo dado que entra no HTML passa por `_esc`** (função já existe em `pdf_trilha.py`), inclusive os campos novos da capa.
- **Sem selo de tema/categoria na capa** — não existe esse campo em `trilha_pecas`, e o Diego decidiu não criar um.
- **Tamanho de letra do corpo não muda em nenhum lugar** — só espaçamento (margens, `line-height`, padding dos blocos).
- **Testes de HTML usam a frase inteira como âncora**, nunca um trecho curto — lição já cara neste projeto (`-webkit-` casando com `"kit"`, etc.).
- **A capa entra SÓ na trilha.** Não mexer em `app/pdf.py` (fora de escopo — item 41 do backlog).
- **Asset do ícone:** `docs/superpowers/specs/assets/2026-08-19-ds-mark-icone.b64` — PNG 130×168 (ícone "DS", traço dourado, fundo 100% transparente), já processado e testado no PDF real. Ler o conteúdo desse arquivo literalmente; não regenerar, não editar.

---

### Task 1: Renomear `TRILHA_NOME` + provar a propagação

**Files:**
- Modify: `app/config.py:73`
- Test: `app/tests/test_trilha_nome_propaga.py` (criar)

**Interfaces:**
- Produces: `config.TRILHA_NOME` com o valor novo `"Trilha do Consultório Lucrativo"` — consumido, sem mudança de assinatura, por `pdf_trilha.montar_html` (Task 3), `trilha.py:179`, `site_web.py:944,954,2531,2537`.

- [ ] **Step 1: Write the failing test**

```python
"""O nome da trilha e' um valor unico em config.TRILHA_NOME — mudar ali tem que refletir
em TUDO que o le, sem edicao propria em cada lugar."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestTrilhaNomePropaga(unittest.TestCase):
    def test_nome_e_o_esperado(self):
        import config
        self.assertEqual(config.TRILHA_NOME, "Trilha do Consultório Lucrativo")

    def test_env_ainda_sobrescreve(self):
        """DSCURSO_TRILHA_NOME continua tendo prioridade — e' a valvula de escape sem deploy."""
        os.environ["DSCURSO_TRILHA_NOME"] = "Nome Via Env"
        try:
            import importlib
            import config
            importlib.reload(config)
            self.assertEqual(config.TRILHA_NOME, "Nome Via Env")
        finally:
            del os.environ["DSCURSO_TRILHA_NOME"]
            import importlib
            import config
            importlib.reload(config)

    def test_legenda_do_whatsapp_usa_o_nome_novo(self):
        """trilha.enviar_para monta a legenda com config.TRILHA_NOME — sem edicao propria."""
        import inspect
        import trilha
        fonte = inspect.getsource(trilha.enviar_para)
        self.assertIn("config.TRILHA_NOME", fonte)

    def test_titulo_do_portal_usa_o_nome_novo(self):
        import config
        import site_web
        html = site_web.pagina_trilha_assinante(
            [], subscriber_id="x", token_regra=None) if hasattr(
            site_web, "pagina_trilha_assinante") else None
        # A funcao exata pode variar; o que importa e' que o modulo referencia
        # config.TRILHA_NOME em vez de string literal — checado por fonte.
        import inspect
        fonte = inspect.getsource(site_web)
        self.assertIn("config.TRILHA_NOME", fonte)
        self.assertIn("_cfg.TRILHA_NOME", fonte)  # ha' import "as _cfg" tambem
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_trilha_nome_propaga -v`
Expected: FAIL em `test_nome_e_o_esperado` — `'Trilha do Consultório' != 'Trilha do Consultório Lucrativo'`

- [ ] **Step 3: Write minimal implementation**

Em `app/config.py:73`, trocar:

```python
TRILHA_NOME = os.environ.get("DSCURSO_TRILHA_NOME") or "Trilha do Consultório"
```

por:

```python
TRILHA_NOME = os.environ.get("DSCURSO_TRILHA_NOME") or "Trilha do Consultório Lucrativo"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_trilha_nome_propaga -v`
Expected: PASS (4 testes)

- [ ] **Step 5: Commit**

```bash
git add app/config.py app/tests/test_trilha_nome_propaga.py
git commit -m "feat(trilha): renomeia para Trilha do Consultorio Lucrativo"
```

---

### Task 2: Embutir o ícone DS como constante

**Files:**
- Modify: `app/pdf_trilha.py` (acrescentar constante `_ICONE_DS_B64` logo após os imports, antes de `_CSS`)
- Test: `app/tests/test_pdf_trilha.py` (criar — as tasks seguintes acrescentam mais classes nele)

**Interfaces:**
- Produces: `pdf_trilha._ICONE_DS_B64` (`str`) — string base64 de um PNG válido, consumida pela Task 3 dentro do `<img src="data:image/png;base64,...">`.

- [ ] **Step 1: Write the failing test**

```python
"""Testes de app/pdf_trilha.py — a capa nova, o icone DS, e os blocos maiores."""
import base64
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _decodifica_png(b64):
    """Le os primeiros bytes e confirma que e' PNG de verdade, sem precisar de Pillow."""
    bruto = base64.b64decode(b64)
    assinatura_png = b"\x89PNG\r\n\x1a\n"
    return bruto[:8] == assinatura_png, bruto


class TestIconeDS(unittest.TestCase):
    def test_e_um_png_valido(self):
        import pdf_trilha
        ok, bruto = _decodifica_png(pdf_trilha._ICONE_DS_B64)
        self.assertTrue(ok, "a constante nao decodifica pra um PNG valido")
        self.assertGreater(len(bruto), 1000, "arquivo suspeito de pequeno/truncado")

    def test_tem_canal_alfa_com_transparencia_real(self):
        """O PNG precisa ser RGBA com pixel(s) realmente transparente(s) — e' o que
        permite compor o icone sobre a banda verde sem caixa branca ao redor.
        Checagem sem Pillow: o PNG usa chunk IHDR pra declarar o tipo de cor; tipo 6
        = RGBA. Basta olhar o byte de "color type" no cabecalho IHDR."""
        import pdf_trilha
        _, bruto = _decodifica_png(pdf_trilha._ICONE_DS_B64)
        # IHDR comeca no byte 8 (assinatura) + 4 (tamanho do chunk) + 4 ("IHDR") = 16
        # width(4) height(4) bitdepth(1) colortype(1) ...
        color_type = bruto[16 + 9]
        self.assertEqual(color_type, 6, "PNG nao e' RGBA (color type 6) — sem alfa")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_pdf_trilha -v`
Expected: FAIL — `AttributeError: module 'pdf_trilha' has no attribute '_ICONE_DS_B64'`

- [ ] **Step 3: Write minimal implementation**

Ler o conteúdo LITERAL de `docs/superpowers/specs/assets/2026-08-19-ds-mark-icone.b64`
(uma linha só, ~17.500 caracteres) e colar como o valor de `_ICONE_DS_B64` em
`app/pdf_trilha.py`, logo depois dos imports (`import html`, `import re`, `import config`,
`import tabela_pipe`) e antes de `_CSS`:

```python
# Icone "DS" (monograma dourado, fundo transparente) — extraido e isolado de um asset
# do ecossistema DS (ver docs/superpowers/specs/2026-08-19-capa-trilha-design.md pra a
# origem e o script que removeu o fundo). Embutido como string, nao como arquivo .png
# em disco: este projeto nao tem NENHUM asset binario hoje (pdf.py desenha sua textura
# como SVG inline, _MOTIF) — manter essa convencao evita introduzir o primeiro arquivo
# binario do zero.
_ICONE_DS_B64 = (
    "<COLAR AQUI O CONTEUDO LITERAL DE "
    "docs/superpowers/specs/assets/2026-08-19-ds-mark-icone.b64>"
)
```

⚠️ O placeholder acima é só pra você (o implementador) saber ONDE colar — o valor real
vem do arquivo `.b64`, não deve ser digitado à mão nem resumido. Copie o arquivo inteiro,
sem quebras de linha, como uma string Python de uma linha só (use aspas triplas se preferir
não escapar nada, já que a string base64 não contém aspas nem barras invertidas).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_pdf_trilha -v`
Expected: PASS (2 testes)

- [ ] **Step 5: Commit**

```bash
git add app/pdf_trilha.py app/tests/test_pdf_trilha.py docs/superpowers/specs/assets/2026-08-19-ds-mark-icone.b64
git commit -m "feat(trilha): embute o icone DS como constante base64"
```

---

### Task 3: A capa nova em `montar_html`

**Files:**
- Modify: `app/pdf_trilha.py` (`_CSS` inteiro + `montar_html`)
- Test: `app/tests/test_pdf_trilha.py` (acrescentar classe)

**Interfaces:**
- Consumes: `pdf_trilha._ICONE_DS_B64` (Task 2), `config.TRILHA_NOME`, `config.TRILHA_TOTAL` (já existem)
- Produces: `pdf_trilha.montar_html(peca, nome_assinante, abertura="", link_ferramenta="")` — mesma assinatura de hoje, HTML de saída muda.

Testado no PDF real durante o brainstorming (Chromium headless, técnica de sangria idêntica
à de `app/pdf.py`): a capa renderiza edge-to-edge, ícone e assinatura alinhados, selo de
semana no canto, nome do produto em dourado na linha de baixo. Os valores abaixo são os
que saíram bons nesse teste — usar exatamente estes, não improvisar novos.

- [ ] **Step 1: Write the failing test**

```python
from unittest import mock


def _peca(numero=1, titulo="O custo real da sua hora", eixo="Saber onde você está",
          corpo="Texto do corpo.", micro_resultado="A tarefa.", mentalidade="A mentalidade.",
          ferramenta_slug="planilha-x"):
    return {"numero": numero, "titulo": titulo, "eixo": eixo, "corpo": corpo,
            "micro_resultado": micro_resultado, "mentalidade": mentalidade,
            "ferramenta_slug": ferramenta_slug}


class TestCapaNova(unittest.TestCase):
    def _html(self, **kw):
        import pdf_trilha
        with mock.patch("config.TRILHA_NOME", "Trilha do Consultório Lucrativo"), \
             mock.patch("config.TRILHA_TOTAL", 12):
            return pdf_trilha.montar_html(_peca(**kw), "Dr. Diego",
                                          link_ferramenta="https://ex.com/f")

    def test_tem_a_banda_verde(self):
        h = self._html()
        self.assertIn("linear-gradient(120deg,#0e211a,#1e5045)", h)

    def test_tem_o_icone_embutido(self):
        import pdf_trilha
        h = self._html()
        self.assertIn(f'src="data:image/png;base64,{pdf_trilha._ICONE_DS_B64}"', h)

    def test_tem_o_nome_do_medico(self):
        h = self._html()
        self.assertIn('<span class="capa-nome">Dr. Diego Silva</span>', h)

    def test_tem_o_selo_da_semana(self):
        h = self._html(numero=3)
        self.assertIn('<span class="capa-selo">Semana 3 de 12</span>', h)

    def test_tem_o_nome_do_produto_embaixo(self):
        h = self._html()
        self.assertIn('<div class="capa-produto">Trilha do Consultório Lucrativo</div>', h)

    def test_sem_selo_de_tema(self):
        """Decisao explicita do Diego — nao existe campo de categoria por peca."""
        h = self._html()
        self.assertNotIn("Mentalidade</div>", h)  # nao ha' selo generico de categoria
        # "Mentalidade" so' pode aparecer como ROTULO do bloco (Task 4), nunca como selo
        # da capa — essa distincao e' o que este teste protege.

    def test_a_capa_esta_fora_do_wrapper_de_margem(self):
        """A tecnica de sangria exige que .capa fique FORA de .pagina (senao herda a
        margem lateral e para de bater de ponta a ponta)."""
        h = self._html()
        pos_capa = h.index('<div class="capa">')
        pos_pagina = h.index('<div class="pagina">')
        self.assertLess(pos_capa, pos_pagina)
        # o </div> que fecha .capa tem que vir ANTES da abertura de .pagina
        fim_capa = h.index("</div>", h.index('<div class="capa-produto">'))
        self.assertLess(fim_capa, pos_pagina)

    def test_titulo_e_corpo_continuam_depois_da_capa(self):
        h = self._html(titulo="Título Teste")
        self.assertIn("<h1>Título Teste</h1>", h)

    def test_numero_e_nome_vao_escapados(self):
        """Defesa em profundidade: TRILHA_NOME e' hoje um valor de config, nao entrada
        de usuario por requisicao — mas continua indo por _esc, como todo campo aqui."""
        with mock.patch("config.TRILHA_NOME", '<script>alert(1)</script>'), \
             mock.patch("config.TRILHA_TOTAL", 12):
            import pdf_trilha
            h = pdf_trilha.montar_html(_peca(), "Dr. Diego")
        self.assertNotIn("<script>alert(1)</script>", h)
        self.assertIn("&lt;script&gt;", h)


class TestTipografiaMaisJusta(unittest.TestCase):
    """Prova a alegacao do spec (secao 4): margem/entrelinha reduzidas, SEM tocar em
    nenhum font-size de texto de leitura. font-size do body continua ausente de proposito
    (herda o padrao do navegador) — se algum dia alguem adicionar um font-size aqui pra
    'resolver' a pagina 2, e' a troca errada que o Diego recusou; este teste segura isso."""

    def test_pagina_sem_margem_lateral_no_page_rule(self):
        import pdf_trilha
        self.assertIn("margin: 15mm 0 13mm", pdf_trilha._CSS)

    def test_entrelinha_do_corpo_e_1_5(self):
        import pdf_trilha
        self.assertIn("line-height: 1.5;", pdf_trilha._CSS)

    def test_paragrafo_do_corpo_tem_margem_reduzida(self):
        import pdf_trilha
        self.assertIn(".corpo p { margin: 0 0 9px; }", pdf_trilha._CSS)

    def test_item_de_lista_tem_margem_reduzida(self):
        import pdf_trilha
        self.assertIn("li { margin: 0 0 4px; }", pdf_trilha._CSS)

    def test_body_nao_declara_font_size_proprio(self):
        """O corpo continua no tamanho padrao do navegador — nenhuma letra encolheu."""
        import re
        import pdf_trilha
        regra_body = re.search(r"\bbody\s*\{([^}]*)\}", pdf_trilha._CSS)
        self.assertIsNotNone(regra_body)
        self.assertNotIn("font-size", regra_body.group(1))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_pdf_trilha.TestCapaNova -v`
Expected: FAIL em todos — a capa antiga (`.selo` texto simples) ainda está no lugar.

- [ ] **Step 3: Write minimal implementation**

Em `app/pdf_trilha.py`, substituir `_CSS` inteiro por:

```python
_CSS = """
  @page { size: A4; margin: 15mm 0 13mm; }
  @page :first { margin-top: 0; }
  *{box-sizing:border-box}
  body { font-family: Georgia, 'Times New Roman', serif; color: #1b1b1b; line-height: 1.5;
         margin: 0; }

  .capa { background: linear-gradient(120deg,#0e211a,#1e5045); padding: 16px 16mm 18px; }
  .capa-topo { display:flex; align-items:center; justify-content:space-between; gap:10px; }
  .capa-assinatura { display:flex; align-items:center; gap:9px; }
  .capa-icone { height:42px; width:42px; flex:none; }
  .capa-nome { color:#f4f1e7; font-size:19px; white-space:nowrap; }
  .capa-selo { background:#f4f1e7; color:#14332a; font-family:system-ui,sans-serif;
               font-size:9px; letter-spacing:.08em; font-weight:700; padding:5px 11px;
               border-radius:100px; white-space:nowrap; flex:none; align-self:flex-start;
               margin-top:4px; }
  .capa-produto { font-family:system-ui,sans-serif; font-size:9px; letter-spacing:.12em;
                  text-transform:uppercase; color:#e7c766; font-weight:600; margin-top:9px; }

  .pagina { padding: 0 16mm; }
  h1 { font-size: 25px; line-height: 1.2; margin: 22px 0 2px; }
  h2 { font-family: system-ui, sans-serif; font-size: 13.5px; font-weight: 700;
       color: #4a3a12; letter-spacing: .01em; margin: 14px 0 6px; line-height: 1.3; }
  .eixo { font-family: system-ui, sans-serif; font-size: 12px; color: #6b6b6b; margin: 0 0 16px; }
  .abertura { font-style: italic; color: #4a4a4a; border-left: 3px solid #d8c9a6;
              padding-left: 12px; margin: 0 0 16px; }
  .corpo p { margin: 0 0 9px; }
  ul, ol { margin: 0 0 9px; padding-left: 20px; }
  li { margin: 0 0 4px; }
  table { width: 100%; table-layout: fixed; border-collapse: collapse;
          margin: 5px 0 12px; font-family: system-ui, sans-serif; font-size: 11px; }
  th, td { border: 1px solid #e2dccc; padding: 4px 7px; text-align: left;
           overflow-wrap: break-word; font-variant-numeric: tabular-nums; }
  th { font-size: 9px; letter-spacing: .08em; text-transform: uppercase; color: #6b6b6b;
       background: #f7f4ec; font-weight: 600; }
  td.num { text-align: right; }
  .bloco { border: 1px solid #e2dccc; border-radius: 8px; padding: 14px 16px; margin: 22px 0 0; }
  .bloco .rot { font-family: system-ui, sans-serif; font-size: 10px; letter-spacing: .16em;
                text-transform: uppercase; color: #8a6a2f; margin: 0 0 6px; }
  .bloco p { margin: 0; }
  .ferramenta { margin: 22px 0 0; }
  .ferramenta a { font-family: system-ui, sans-serif; font-size: 13px; color: #8a6a2f; }
  .rodape { margin-top: 30px; font-family: system-ui, sans-serif; font-size: 11px; color: #8a8a8a; }
"""
```

(Os `.bloco` acima ainda estão nos valores ANTIGOS de propósito — a Task 4 os substitui.
Não pule essa distinção: se você já colar os valores novos aqui, o teste da Task 4 não vai
provar nada, porque não vai ter passado de FALHA pra PASSA.)

Substituir `montar_html` inteiro por:

```python
def montar_html(peca, nome_assinante, abertura="", link_ferramenta=""):
    """HTML completo de uma peça. `link_ferramenta` vazio some com o bloco inteiro —
    peça de mentalidade pura não tem anexo e não pode exibir botão órfão.

    A capa fica FORA do wrapper `.pagina`: é a técnica de sangria que `app/pdf.py` já usa
    (margem lateral do `@page` zerada, cover ocupa a largura inteira, o resto do conteúdo
    ganha padding próprio pra simular a margem). Colocar a capa dentro de `.pagina` faria
    ela herdar o padding lateral e parar de bater de ponta a ponta.
    """
    numero = peca.get("numero", 0)
    abertura_html = (f'<p class="abertura">{_esc(abertura)}</p>' if abertura else "")
    ferramenta_html = ""
    if link_ferramenta:
        ferramenta_html = (f'<p class="ferramenta">📎 <a href="{_esc(link_ferramenta)}">'
                           f'Baixar a ferramenta desta semana</a></p>')
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<style>{_CSS}</style></head><body>
  <div class="capa">
    <div class="capa-topo">
      <div class="capa-assinatura">
        <img class="capa-icone" src="data:image/png;base64,{_ICONE_DS_B64}" alt="">
        <span class="capa-nome">Dr. Diego Silva</span>
      </div>
      <span class="capa-selo">Semana {numero} de {config.TRILHA_TOTAL}</span>
    </div>
    <div class="capa-produto">{_esc(config.TRILHA_NOME)}</div>
  </div>
  <div class="pagina">
  <h1>{_esc(peca.get('titulo'))}</h1>
  <p class="eixo">{_esc(peca.get('eixo'))}</p>
  {abertura_html}
  <div class="corpo">{_paragrafos(peca.get('corpo'))}</div>
  <div class="bloco"><p class="rot">Sua tarefa desta semana</p>
    {_paragrafos(peca.get('micro_resultado')) or '<p></p>'}</div>
  <div class="bloco"><p class="rot">Mentalidade</p>
    {_paragrafos(peca.get('mentalidade')) or '<p></p>'}</div>
  {ferramenta_html}
  <p class="rodape">Para {_esc(nome_assinante)} · {_esc(config.TRILHA_NOME)}</p>
  </div>
</body></html>"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_pdf_trilha -v`
Expected: PASS (16 testes — 9 de `TestCapaNova` + 5 de `TestTipografiaMaisJusta` +
2 de `TestIconeDS` da Task 2)

- [ ] **Step 5: Rodar a suíte inteira**

Run: `cd app && python3 -m unittest discover -s tests`
Expected: OK. `app/tests/test_area_no_revisar.py` e outros que tocam PDF não deveriam
quebrar — a mudança é isolada em `pdf_trilha.py`. Se algo quebrar fora deste arquivo,
pare e investigue antes de commitar (não é esperado).

- [ ] **Step 6: Commit**

```bash
git add app/pdf_trilha.py app/tests/test_pdf_trilha.py
git commit -m "feat(trilha): capa com banda verde, icone DS e selo de semana"
```

---

### Task 4: Blocos "Sua tarefa" / "Mentalidade" maiores + tipografia mais justa

**Files:**
- Modify: `app/pdf_trilha.py` (só a seção `.bloco`/`.pagina h1`/`.corpo p`/`li`/`.ferramenta`/`.rodape` dentro de `_CSS` — não mexe em `montar_html`)
- Test: `app/tests/test_pdf_trilha.py` (acrescentar classe)

**Interfaces:**
- Nenhuma interface nova — só valores de CSS mudam. Nada que outra task consuma por nome.

⚠️ **O que este task NÃO faz:** não elimina a página 2 (medido no brainstorming: pelo menos
4 das 12 peças reais vazam pra 2 páginas mesmo com esta tipografia mais justa). Não reduz
NENHUM `font-size` de texto de leitura — só `padding`, `margin`, `line-height` do `body` e
o `@page margin` (já mudou na Task 3, pra 15mm 0 13mm — este task não mexe nisso de novo).

- [ ] **Step 1: Write the failing test**

```python
class TestBlocosMaiores(unittest.TestCase):
    def test_bloco_tem_borda_dourada_a_esquerda(self):
        import pdf_trilha
        self.assertIn("border-left: 4px solid #c9a227", pdf_trilha._CSS)

    def test_bloco_tem_fundo_creme(self):
        import pdf_trilha
        self.assertIn("background: #fdfbf5", pdf_trilha._CSS)

    def test_bloco_tem_padding_maior(self):
        import pdf_trilha
        self.assertIn("padding: 22px 26px", pdf_trilha._CSS)

    def test_texto_do_bloco_e_maior_que_o_corpo(self):
        """O corpo continua no tamanho padrao (sem font-size explicito = herda do body);
        o texto DENTRO do bloco agora e' explicitamente maior (15px) — e' o oposto de
        'apertar a letra': aqui a letra de destaque CRESCE."""
        import pdf_trilha
        self.assertIn(".bloco p { margin: 0; font-size: 15px; line-height: 1.6; }",
                      pdf_trilha._CSS.replace("\n", " ").replace("  ", " "))

    def test_o_rotulo_do_bloco_ficou_mais_espacoso(self):
        import pdf_trilha
        self.assertIn("letter-spacing: .18em", pdf_trilha._CSS)
        self.assertIn("font-weight: 700", pdf_trilha._CSS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_pdf_trilha.TestBlocosMaiores -v`
Expected: FAIL — os valores antigos (`padding: 14px 16px`, sem `border-left`, sem
`background: #fdfbf5`) ainda estão em `_CSS`.

- [ ] **Step 3: Write minimal implementation**

Dentro de `_CSS` (em `app/pdf_trilha.py`), trocar o bloco de regras `.bloco`/`.corpo
p`/`li`/`.ferramenta`/`.rodape` por:

```css
  .corpo p { margin: 0 0 9px; }
  ul, ol { margin: 0 0 9px; padding-left: 20px; }
  li { margin: 0 0 4px; }
  .bloco { border: 1px solid #e2dccc; border-left: 4px solid #c9a227; border-radius: 8px;
           padding: 22px 26px; margin: 26px 0 0; background: #fdfbf5; }
  .bloco .rot { font-family: system-ui, sans-serif; font-size: 11px; letter-spacing: .18em;
                text-transform: uppercase; color: #8a6a2f; font-weight: 700; margin: 0 0 10px; }
  .bloco p { margin: 0; font-size: 15px; line-height: 1.6; }
  .ferramenta { margin: 26px 0 0; }
  .ferramenta a { font-family: system-ui, sans-serif; font-size: 13px; color: #8a6a2f; }
  .rodape { margin-top: 24px; font-family: system-ui, sans-serif; font-size: 11px; color: #8a8a8a; }
```

(As regras de `.corpo p`, `ul, ol`, `li` já foram escritas com estes valores na Task 3 —
confirme que não ficaram duplicadas; deve haver uma ocorrência só de cada seletor em
`_CSS`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_pdf_trilha -v`
Expected: PASS (21 testes: os 16 anteriores + 5 de `TestBlocosMaiores`)

- [ ] **Step 5: Rodar a suíte inteira**

Run: `cd app && python3 -m unittest discover -s tests`
Expected: OK.

- [ ] **Step 6: Verificação visual real (não é teste automatizado — é conferência manual)**

Este projeto não roda Chromium dentro da suíte de testes (`app/tests/test_pdf_retry.py`
dubla `subprocess.run`; nenhum teste chama o binário de verdade). A prova de que os blocos
maiores realmente preenchem a página 2 já foi feita manualmente durante o brainstorming
(peça 1, render real via Chromium headless) — não repita isso como parte da suíte. Se
quiser reconferir com os próprios olhos depois de implementar, o comando é:

```bash
python3 -c "
import sys; sys.path.insert(0, 'app')
import pdf_trilha
peca = {'numero': 1, 'titulo': 'Teste', 'eixo': 'Eixo teste',
        'corpo': 'Parágrafo. ' * 200, 'micro_resultado': 'Tarefa de teste.',
        'mentalidade': 'Mentalidade de teste.', 'ferramenta_slug': ''}
html = pdf_trilha.montar_html(peca, 'Teste')
open('/tmp/teste.html', 'w').write(html)
"
# depois abra /tmp/teste.html num navegador, ou gere o PDF com Chromium se tiver instalado
```

- [ ] **Step 7: Commit**

```bash
git add app/pdf_trilha.py app/tests/test_pdf_trilha.py
git commit -m "feat(trilha): blocos de tarefa e mentalidade maiores, com destaque dourado"
```

---

## Conferência ao vivo (depois do deploy)

A trilha está **desligada em produção** — o Diego aperta "Ligar" em `/admin/trilha` quando
aprovar. Antes disso:

1. Abrir `/admin/trilha/peca/1` (token de admin) e conferir a capa: banda verde, ícone DS
   nítido, "Dr. Diego Silva", selo "Semana 1 de 12", "TRILHA DO CONSULTÓRIO LUCRATIVO"
   embaixo em dourado.
2. Abrir uma peça mais longa (`/admin/trilha/peca/1`, `/4`, `/5` ou `/7` — as mais longas
   medidas no brainstorming) e conferir a página 2: blocos com borda dourada e fundo creme,
   preenchendo a maior parte da página.
3. Conferir que o rodapé, o título da aba do navegador e (quando um assinante real receber)
   a legenda do WhatsApp dizem "Trilha do Consultório Lucrativo".
