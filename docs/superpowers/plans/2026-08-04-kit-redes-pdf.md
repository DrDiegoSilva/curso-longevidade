# Kit para suas redes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar o rodapé do PDF diário num kit de post pronto — recorte do header do paper, a frase em linguagem de paciente, e de 1 a 3 pautas de Reels tiradas do estudo.

**Architecture:** O campo `gancho` (hoje texto puro) passa a guardar JSON, seguindo o padrão que o `grafico` já usa nas mesmas tabelas. Um parser puro converte qualquer formato (JSON novo, texto antigo, JSON quebrado) numa estrutura única, e um renderizador único desenha o kit no PDF e no site. O título original em inglês passa a ser carregado ponta a ponta, da curadoria até o digest.

**Tech Stack:** Python 3 stdlib, `unittest`, SQLite/Postgres via `db.py`, Chromium headless para PDF.

## Global Constraints

- **Testes:** `cd app && python3 -m unittest discover -s tests`. A suíte tem que ficar verde ao fim de cada tarefa.
- **Sem dependência nova.** Só stdlib.
- **Nunca levantar exceção no caminho do assinante.** Campo faltando degrada; nada pode imprimir `None` na página.
- **Ética CFM no prompt (inegociável, já existe em `content.py:14-16`):** sem promessa de cura/milagre, sem garantia de resultado, sem promover medicamento de receita para leigo (falar do CONCEITO), sem sensacionalismo.
- **Não commitar `git add -A`** — outros agentes trabalham neste repo. Stagear só os arquivos da tarefa.
- **Mensagens de commit em ASCII**, seguindo o padrão do repo (`fix(escopo): ...`, `feat(escopo): ...`).

## File Structure

| arquivo | responsabilidade nesta feature |
|---|---|
| `app/content.py` | `parse_gancho()` (novo) + `SYS_GANCHO` reescrito |
| `app/pdf.py` | `_kit_html()` (substitui `_gancho_html`) + CSS + link clicável no rodapé |
| `app/site_web.py` | passa a chamar `_kit_html` |
| `app/db.py` | coluna `titulo_original` em 4 tabelas + gravação |
| `app/daily.py` | carregar `titulo_original` no `art` + legenda do WhatsApp |
| `app/deliver.py` | separar legenda de nome de arquivo |
| `app/tests/test_kit_redes.py` | novo: parser + render |

---

### Task 1: Parser do `gancho`

Função pura que aceita qualquer formato já existente no banco e devolve uma estrutura única. Sem ela, o renderizador teria que lidar com três formatos e viraria um ninho de `if`.

**Files:**
- Modify: `app/content.py` (adicionar função nova; não mexer em nada existente)
- Test: `app/tests/test_kit_redes.py` (criar)

**Interfaces:**
- Consumes: nada
- Produces: `content.parse_gancho(bruto: str) -> dict` com a forma
  `{"frase": str, "reels": [{"angulo": str, "apoio": str}]}`.
  `frase` pode ser `""`; `reels` pode ser `[]`; nunca `None`; no máximo 3 itens.

- [ ] **Step 1: Write the failing test**

Criar `app/tests/test_kit_redes.py`:

```python
"""Parser e render do kit de redes (rodape do PDF). Standalone."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestParseGancho(unittest.TestCase):
    def setUp(self):
        import content
        self.c = content

    def test_json_novo_completo(self):
        bruto = ('{"frase": "Perdeu 20,9% do peso.",'
                 ' "reels": [{"angulo": "Nao e forca de vontade.", "apoio": "O comparador perdeu 3,1%."}]}')
        r = self.c.parse_gancho(bruto)
        self.assertEqual(r["frase"], "Perdeu 20,9% do peso.")
        self.assertEqual(len(r["reels"]), 1)
        self.assertEqual(r["reels"][0]["angulo"], "Nao e forca de vontade.")
        self.assertEqual(r["reels"][0]["apoio"], "O comparador perdeu 3,1%.")

    def test_texto_puro_antigo_vira_um_reel(self):
        """Formato legado: o banco de reserva/classicos esta cheio deles."""
        r = self.c.parse_gancho("Fale sobre obesidade como doenca cronica.")
        self.assertEqual(r["frase"], "")
        self.assertEqual(len(r["reels"]), 1)
        self.assertEqual(r["reels"][0]["angulo"], "Fale sobre obesidade como doenca cronica.")
        self.assertEqual(r["reels"][0]["apoio"], "")

    def test_vazio_nao_quebra(self):
        for entrada in ("", None, "   "):
            r = self.c.parse_gancho(entrada)
            self.assertEqual(r["frase"], "")
            self.assertEqual(r["reels"], [])

    def test_json_so_com_frase(self):
        r = self.c.parse_gancho('{"frase": "So a frase."}')
        self.assertEqual(r["frase"], "So a frase.")
        self.assertEqual(r["reels"], [])

    def test_item_sem_apoio(self):
        r = self.c.parse_gancho('{"reels": [{"angulo": "So o angulo."}]}')
        self.assertEqual(r["reels"][0]["apoio"], "")

    def test_corta_em_tres(self):
        """A IA vai extrapolar alguma hora; nao pode virar bloco gigante no PDF."""
        itens = ",".join('{"angulo": "a%d"}' % i for i in range(5))
        r = self.c.parse_gancho('{"reels": [%s]}' % itens)
        self.assertEqual(len(r["reels"]), 3)

    def test_item_sem_angulo_e_descartado(self):
        r = self.c.parse_gancho('{"reels": [{"apoio": "orfao"}, {"angulo": "bom"}]}')
        self.assertEqual(len(r["reels"]), 1)
        self.assertEqual(r["reels"][0]["angulo"], "bom")

    def test_nunca_imprime_none(self):
        r = self.c.parse_gancho('{"frase": null, "reels": [{"angulo": "x", "apoio": null}]}')
        self.assertEqual(r["frase"], "")
        self.assertEqual(r["reels"][0]["apoio"], "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_kit_redes -v`
Expected: FAIL — `AttributeError: module 'content' has no attribute 'parse_gancho'`

- [ ] **Step 3: Write minimal implementation**

Em `app/content.py`, depois de `_braco` (perto da linha 108):

```python
MAX_REELS = 3


def _txt(v):
    """String limpa a partir de qualquer coisa que a IA devolva (inclusive None)."""
    return str(v).strip() if v is not None else ""


def parse_gancho(bruto):
    """Normaliza o campo `gancho` para {"frase": str, "reels": [{"angulo","apoio"}]}.

    Aceita tres formatos, porque os tres existem no banco:
      1. JSON novo  -> {"frase": ..., "reels": [...]}
      2. texto puro -> formato LEGADO (reserva/classicos/digests antigos); vira um reel
      3. lixo/vazio -> estrutura vazia, sem levantar

    Nunca levanta e nunca devolve None em campo nenhum: isto roda no caminho do PDF
    do assinante, onde uma excecao custa o envio do dia.
    """
    texto = _txt(bruto)
    if not texto:
        return {"frase": "", "reels": []}
    try:
        dados = json.loads(texto)
    except Exception:
        dados = None
    if not isinstance(dados, dict):
        return {"frase": "", "reels": [{"angulo": texto, "apoio": ""}]}
    reels = []
    for item in (dados.get("reels") or []):
        if not isinstance(item, dict):
            continue
        angulo = _txt(item.get("angulo"))
        if not angulo:
            continue                      # item sem angulo nao rende video nenhum
        reels.append({"angulo": angulo, "apoio": _txt(item.get("apoio"))})
    return {"frase": _txt(dados.get("frase")), "reels": reels[:MAX_REELS]}
```

`json` já está importado no topo de `content.py` (linha 5).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_kit_redes -v`
Expected: PASS (8 testes)

- [ ] **Step 5: Run the whole suite**

Run: `cd app && python3 -m unittest discover -s tests`
Expected: OK

- [ ] **Step 6: Commit**

```bash
git add app/content.py app/tests/test_kit_redes.py
git commit -m "feat(kit): parser do gancho aceita JSON novo e texto legado"
```

---

### Task 2: Render do kit no PDF

**Files:**
- Modify: `app/pdf.py:222-227` (substituir `_gancho_html`), CSS perto de `app/pdf.py:305`
- Test: `app/tests/test_kit_redes.py` (adicionar classe)

**Interfaces:**
- Consumes: `content.parse_gancho(bruto)` da Task 1
- Produces: `pdf._kit_html(gancho_bruto: str, artigo: dict) -> str`.
  Lê `artigo["titulo_original"]` e cai para `artigo["titulo"]`; usa também
  `artigo["fonte"]`, `artigo["data"]`, `artigo["doi"]`.
  Devolve `""` quando não há nada para mostrar.

- [ ] **Step 1: Write the failing test**

Adicionar em `app/tests/test_kit_redes.py`, antes do `if __name__`:

```python
class TestKitHtml(unittest.TestCase):
    def setUp(self):
        import pdf
        self.pdf = pdf
        self.artigo = {"titulo_original": "Tirzepatide Once Weekly for Obesity",
                       "titulo": "Tirzepatida semanal para obesidade",
                       "fonte": "N Engl J Med", "data": "2022", "doi": "10.1056/NEJMoa2206038"}
        self.gancho = ('{"frase": "Perdeu 20,9% do peso em 72 semanas.",'
                       ' "reels": [{"angulo": "Nao e forca de vontade.", "apoio": "O comparador perdeu 3,1%."},'
                       '           {"angulo": "Nao acontece em um mes.", "apoio": "Foram 72 semanas."}]}')

    def test_mostra_titulo_original_em_ingles(self):
        html = self.pdf._kit_html(self.gancho, self.artigo)
        self.assertIn("Tirzepatide Once Weekly for Obesity", html)
        self.assertNotIn("Tirzepatida semanal", html)     # o pt fica no topo do PDF, nao aqui

    def test_cai_para_titulo_quando_nao_ha_original(self):
        art = dict(self.artigo)
        del art["titulo_original"]
        html = self.pdf._kit_html(self.gancho, art)
        self.assertIn("Tirzepatida semanal para obesidade", html)

    def test_mostra_frase_e_os_reels(self):
        html = self.pdf._kit_html(self.gancho, self.artigo)
        self.assertIn("Perdeu 20,9% do peso em 72 semanas.", html)
        self.assertIn("Nao e forca de vontade.", html)
        self.assertIn("Nao acontece em um mes.", html)
        self.assertIn("O comparador perdeu 3,1%.", html)

    def test_um_reel_so_renderiza_igual_bem(self):
        """Caso ESPERADO agora (o prompt prefere menos): nao pode sobrar item vazio."""
        html = self.pdf._kit_html('{"reels": [{"angulo": "Unico."}]}', self.artigo)
        self.assertEqual(html.count('class="reel"'), 1)
        self.assertNotIn("None", html)

    def test_texto_legado_nao_quebra(self):
        html = self.pdf._kit_html("Fale sobre obesidade como doenca cronica.", self.artigo)
        self.assertIn("Fale sobre obesidade como doenca cronica.", html)
        self.assertNotIn("None", html)

    def test_gancho_vazio_ainda_mostra_o_cartao_do_estudo(self):
        """O recorte do paper vale por si so, mesmo sem texto de IA."""
        html = self.pdf._kit_html("", self.artigo)
        self.assertIn("Tirzepatide Once Weekly for Obesity", html)

    def test_sem_gancho_e_sem_estudo_devolve_vazio(self):
        self.assertEqual(self.pdf._kit_html("", {}), "")

    def test_escapa_html_do_conteudo(self):
        art = dict(self.artigo, titulo_original="A <script>alert(1)</script> B")
        html = self.pdf._kit_html("", art)
        self.assertNotIn("<script>", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_kit_redes.TestKitHtml -v`
Expected: FAIL — `AttributeError: module 'pdf' has no attribute '_kit_html'`

- [ ] **Step 3: Write minimal implementation**

Em `app/pdf.py`, substituir a função `_gancho_html` inteira (linhas 222-227) por:

```python
def _kit_html(gancho_bruto, artigo):
    """Kit de post no rodape: recorte do paper + a frase + as pautas de Reels.

    Os dois primeiros blocos sao pensados para PRINT RECORTADO -- o medico ja fazia
    isso na mao, printando o PDF do artigo. Por isso nao levam a marca do Diego: quem
    posta e o assinante. O terceiro e briefing, e por isso e visualmente diferente:
    se parecesse com os outros, alguem recortaria a instrucao junto e postaria.
    """
    import content
    esc = _html.escape
    dados = content.parse_gancho(gancho_bruto)
    titulo = (artigo.get("titulo_original") or artigo.get("titulo") or "").strip()
    blocos = []

    if titulo:
        revista = " · ".join(x for x in [(artigo.get("fonte") or "").strip(),
                                         (artigo.get("data") or "").strip()] if x)
        doi = (artigo.get("doi") or "").strip()
        blocos.append(
            f'<div class="kit-paper"><div class="kit-rot">1 &middot; O estudo</div>'
            f'<div class="paper-box">'
            f'<div class="paper-rev">{esc(revista)}</div>'
            f'<p class="paper-tit">{esc(titulo)}</p>'
            + (f'<div class="paper-doi">DOI {esc(doi)}</div>' if doi else "")
            + '</div></div>')

    if dados["frase"]:
        blocos.append(
            f'<div class="kit-frase"><div class="kit-rot">2 &middot; A frase</div>'
            f'<div class="frase-box"><p>{esc(dados["frase"])}</p></div></div>')

    if dados["reels"]:
        itens = []
        for i, r in enumerate(dados["reels"], 1):
            apoio = f' <span class="reel-apoio">{esc(r["apoio"])}</span>' if r["apoio"] else ""
            itens.append(f'<li class="reel"><span class="reel-n">{i}</span>'
                         f'<span><b>{esc(r["angulo"])}</b>{apoio}</span></li>')
        blocos.append(
            f'<div class="kit-brief"><div class="kit-rot">Reels que saem deste estudo</div>'
            f'<ul class="reels">{"".join(itens)}</ul></div>')

    if not blocos:
        return ""
    return f'<div class="kit">{"".join(blocos)}</div>'
```

Adicionar o CSS, substituindo as regras `.social*` (linhas 305-307) por:

```css
  .kit {{ margin:28px 0 8px; display:flex; flex-direction:column; gap:22px; }}
  .kit-rot {{ font-family:system-ui,sans-serif; font-size:13px; letter-spacing:.08em;
           text-transform:uppercase; color:#8a6a06; font-weight:700; margin-bottom:9px; }}
  .paper-box {{ border:1px solid #d8ddd7; border-top:3px solid #14332a; background:#fcfdfc;
           padding:18px 20px; break-inside:avoid; }}
  .paper-rev {{ font-family:system-ui,sans-serif; font-size:11.5px; letter-spacing:.13em;
           text-transform:uppercase; color:#14332a; font-weight:700; margin-bottom:9px; }}
  .paper-tit {{ margin:0 0 11px; font-size:20px; line-height:1.28; color:#16211c; }}
  .paper-doi {{ font-family:ui-monospace,Menlo,monospace; font-size:13px; color:#6f7d78; }}
  .frase-box {{ border:2px solid #c9a227; border-radius:12px; padding:22px 24px;
           background:linear-gradient(180deg,#fff9e9,#fbf3d9); break-inside:avoid; }}
  .frase-box p {{ margin:0; font-size:21px; line-height:1.4; color:#3a2f10; }}
  .kit-brief {{ break-inside:avoid; }}
  .kit-brief .kit-rot {{ color:#6f7d78; }}
  .reels {{ list-style:none; margin:0; padding:15px 18px; border-left:3px solid #c8cfca;
           background:#f6f8f6; border-radius:0 8px 8px 0; }}
  .reel {{ display:flex; gap:10px; align-items:flex-start; margin-bottom:9px;
           font-family:system-ui,sans-serif; font-size:14px; line-height:1.55; color:#4d5a54; }}
  .reel:last-child {{ margin-bottom:0; }}
  .reel b {{ color:#33403a; }}
  .reel-n {{ flex:0 0 20px; height:20px; display:inline-flex; align-items:center;
           justify-content:center; border:1px solid #c3ccc6; border-radius:50%;
           font-size:11.5px; font-weight:700; color:#6f7d78; }}
```

> As chaves duplas (`{{`) são obrigatórias: o CSS vive dentro de uma f-string em `montar_html`.

- [ ] **Step 4: Run tests**

Run: `cd app && python3 -m unittest tests.test_kit_redes -v`
Expected: PASS

- [ ] **Step 5: Alinhar o gráfico ao mesmo tratamento de recorte**

O gráfico não entra no kit (decisão do Diego: não duplicar), mas ele é o **terceiro** elemento que
o médico recorta. Se ele cortar diferente dos outros dois, o kit não cumpre a promessa.

Em `app/pdf.py`, na regra `.chart` (perto da linha 276), garantir os mesmos valores de respiro e
quebra que os blocos novos usam:

```css
  .chart {{ /* ...propriedades existentes... */ padding:20px 22px; break-inside:avoid; }}
```

Não trocar cor nem borda do gráfico — a identidade dele (cor semântica das barras) foi decidida
antes e continua valendo. O que se iguala é só padding e `break-inside`.

- [ ] **Step 6: Verify nothing else referenced the old name**

Run: `cd app && grep -rn "_gancho_html" . --include="*.py"`
Expected: só `site_web.py:1878` (tratado na Task 5). Se aparecer outro, ajustar antes de commitar.

- [ ] **Step 7: Commit**

```bash
git add app/pdf.py app/tests/test_kit_redes.py
git commit -m "feat(kit): renderiza recorte do paper, a frase e as pautas de Reels"
```

---

### Task 3: Ligar o kit no PDF e tornar a referência clicável

**Files:**
- Modify: `app/pdf.py:247` (chamada), `app/pdf.py:322` (slot), `app/pdf.py:324` (rodapé)
- Test: `app/tests/test_kit_redes.py`

**Interfaces:**
- Consumes: `pdf._kit_html` da Task 2
- Produces: `montar_html` passa a emitir o kit e um `<a href>` na referência

- [ ] **Step 1: Write the failing test**

```python
class TestMontarHtmlKit(unittest.TestCase):
    def setUp(self):
        import pdf
        self.pdf = pdf
        self.artigo = {"titulo": "Tirzepatide Once Weekly", "fonte": "NEJM", "data": "2022",
                       "doi": "10.1056/x", "url": "https://doi.org/10.1056/x", "tema": "Obesidade"}
        self.conteudo = {"titulo_pt": "Tirzepatida semanal", "resumo": "Resumo.",
                         "gancho": '{"frase": "A frase.", "reels": [{"angulo": "Angulo."}]}',
                         "grafico": None}

    def test_kit_entra_no_pdf(self):
        html = self.pdf.montar_html(self.artigo, self.conteudo, {"cor": "#14332a", "rotulo": "Obesidade"})
        self.assertIn("A frase.", html)
        self.assertIn("Angulo.", html)
        self.assertIn("Tirzepatide Once Weekly", html)

    def test_referencia_vira_link_clicavel(self):
        """Chromium --print-to-pdf preserva hyperlink; texto puro nao clica."""
        html = self.pdf.montar_html(self.artigo, self.conteudo, {"cor": "#14332a", "rotulo": "Obesidade"})
        self.assertIn('<a href="https://doi.org/10.1056/x"', html)

    def test_sem_url_nao_gera_link_vazio(self):
        art = dict(self.artigo, url="")
        html = self.pdf.montar_html(art, self.conteudo, {"cor": "#14332a", "rotulo": "Obesidade"})
        self.assertNotIn('<a href=""', html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_kit_redes.TestMontarHtmlKit -v`
Expected: FAIL — o kit não aparece e a referência não é link.

- [ ] **Step 3: Write minimal implementation**

Em `app/pdf.py:247`, trocar:

```python
    gancho_html = _gancho_html(conteudo.get("gancho", ""))
```

por:

```python
    kit_html = _kit_html(conteudo.get("gancho", ""), artigo)
    url = (artigo.get("url") or "").strip()
    # Link de verdade: o Chromium (--print-to-pdf, `gerar_pdf`) preserva hyperlink como
    # anotacao no PDF. Como texto puro, o medico tinha que copiar o DOI na mao.
    ref_html = (f'Refer&ecirc;ncia: <a href="{esc(url)}">{esc(url)}</a>' if url
                else 'Refer&ecirc;ncia: &mdash;')
```

Em `app/pdf.py:322`, trocar `{gancho_html}` por `{kit_html}`.

Em `app/pdf.py:324`, trocar:

```python
      <span>Refer&ecirc;ncia: {esc(artigo.get('url',''))}</span>
```

por:

```python
      <span>{ref_html}</span>
```

Adicionar ao CSS (junto das regras `.foot`, perto da linha 308):

```css
  .foot a {{ color:#1b6b4f; }}
```

- [ ] **Step 4: Run tests**

Run: `cd app && python3 -m unittest discover -s tests`
Expected: OK

- [ ] **Step 5: Commit**

```bash
git add app/pdf.py app/tests/test_kit_redes.py
git commit -m "feat(kit): kit no rodape do PDF e referencia clicavel"
```

---

### Task 4: Carregar o título original em inglês ponta a ponta

Sem esta tarefa o cartão do estudo mostra o título em **português** na maioria das edições — porque `art["titulo"]` já é `titulo_pt` nos caminhos de reserva (`daily.py:274`), regeração (`:319`) e clássico (`:392`). Só o caminho de candidato (`:375`) carrega o original.

**Files:**
- Modify: `app/db.py` — `CREATE TABLE` de `curadoria_candidatos`, `reserva_resumos`, `classicos`, `digests`; `_migrar_colunas()`; as funções de INSERT dessas tabelas
- Modify: `app/daily.py:274`, `:319`, `:392` (montagem do `art`)
- Test: `app/tests/test_kit_redes.py`

**Interfaces:**
- Consumes: nada
- Produces: chave `titulo_original` disponível no `art` e coluna `titulo_original` nas 4 tabelas

- [ ] **Step 1: Write the failing test**

```python
class TestTituloOriginal(unittest.TestCase):
    def setUp(self):
        import os, tempfile, importlib
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import config, db
        importlib.reload(config)
        importlib.reload(db)
        self.db = db
        db.init()

    def test_digest_guarda_o_titulo_original(self):
        art = {"tema": "Obesidade", "titulo": "Tirzepatide Once Weekly",
               "titulo_original": "Tirzepatide Once Weekly",
               "fonte": "NEJM", "doi": "10.1056/x", "url": "https://x"}
        self.db.registrar_digest(art, {"titulo_pt": "Tirzepatida semanal", "resumo": "r",
                                       "gancho": "", "grafico": None}, data="2026-08-04")
        d = self.db.digest_do_dia("2026-08-04")
        self.assertEqual(d["titulo_original"], "Tirzepatide Once Weekly")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_kit_redes.TestTituloOriginal -v`
Expected: FAIL — `KeyError: 'titulo_original'` (a coluna não existe).

- [ ] **Step 3: Write minimal implementation**

**(a)** Nos `CREATE TABLE` de `db.py`, acrescentar `titulo_original TEXT,` em:
`curadoria_candidatos` (linha ~182), `reserva_resumos` (~194), `classicos` (~189), `digests` (~102).

**(b)** Em `_migrar_colunas()` (perto da linha 293), acrescentar:

```python
        # Titulo em INGLES do paper: o cartao "recorte do estudo" do kit mostra o
        # original, e ele se perdia -- `art["titulo"]` vira titulo_pt nos caminhos de
        # reserva/classico/regeracao (daily.py:274, :319, :392).
        _add_coluna(c, "curadoria_candidatos", "titulo_original", "TEXT")
        _add_coluna(c, "reserva_resumos", "titulo_original", "TEXT")
        _add_coluna(c, "classicos", "titulo_original", "TEXT")
        _add_coluna(c, "digests", "titulo_original", "TEXT")
```

**(c)** Em `registrar_digest` (db.py:1556), incluir a coluna no INSERT, no `ON CONFLICT` e nos valores:
- lista de colunas: `...,titulo_pt,titulo_original,resumo,...`
- `ON CONFLICT ... DO UPDATE SET`: acrescentar `titulo_original=excluded.titulo_original,`
- valores: depois do `titulo_pt`, `art.get("titulo_original") or art.get("titulo", "")`

**(d)** Nos INSERTs de `reserva_resumos` (db.py:1039) e `classicos` (db.py:1111), acrescentar a coluna
`titulo_original` e o valor `reg.get("titulo_original") or reg.get("titulo", "")`.

**(e)** Em `daily.py`, nas três montagens de `art`, acrescentar a chave:
- linha 274: `art = {"titulo": r_res.get("titulo_pt", ""), "titulo_original": r_res.get("titulo_original", ""), ...}`
- linha 319: `art = {..., "titulo": dg.get("titulo_pt", ""), "titulo_original": dg.get("titulo_original", ""), ...}`
- linha 392: `art = {"titulo": cl.get("titulo_pt", ""), "titulo_original": cl.get("titulo_original", ""), ...}`
- linha 375 (candidato): `art = {"titulo": c.get("titulo", ""), "titulo_original": c.get("titulo", ""), ...}`
  — aqui `titulo` **já é** o original em inglês.

- [ ] **Step 4: Run tests**

Run: `cd app && python3 -m unittest discover -s tests`
Expected: OK

- [ ] **Step 5: Commit**

```bash
git add app/db.py app/daily.py app/tests/test_kit_redes.py
git commit -m "feat(kit): carrega o titulo original em ingles ate o digest"
```

---

### Task 5: Site usa o mesmo kit

**Files:**
- Modify: `app/site_web.py:1878`
- Test: `app/tests/test_kit_redes.py`

**Interfaces:**
- Consumes: `pdf._kit_html` (Task 2), coluna `titulo_original` (Task 4)
- Produces: nada

- [ ] **Step 1: Write the failing test**

```python
class TestKitNoSite(unittest.TestCase):
    def test_pagina_digest_mostra_o_kit(self):
        import site_web
        d = {"titulo_pt": "Tirzepatida semanal", "titulo_original": "Tirzepatide Once Weekly",
             "fonte": "NEJM", "data": "2026-08-04", "doi": "10.1056/x", "url": "https://x",
             "resumo": "Resumo.", "grafico": None,
             "gancho": '{"frase": "A frase.", "reels": [{"angulo": "Angulo."}]}'}
        html = site_web.pagina_digest({"rotulo": "Obesidade", "emoji": ""}, d)
        self.assertIn("A frase.", html)
        self.assertIn("Angulo.", html)
        self.assertIn("Tirzepatide Once Weekly", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_kit_redes.TestKitNoSite -v`
Expected: FAIL — o site ainda chama `_gancho_html`.

- [ ] **Step 3: Write minimal implementation**

Em `app/site_web.py:1878`, trocar:

```python
                 f'{pdf._grafico_html(grafico)}{pdf._gancho_html(d.get("gancho",""))}')
```

por:

```python
                 f'{pdf._grafico_html(grafico)}{pdf._kit_html(d.get("gancho",""), d)}')
```

> O dict `d` do digest já tem `titulo_original`, `fonte`, `data`, `doi` — os mesmos nomes que
> `_kit_html` lê do `artigo`. Nenhuma adaptação é necessária.

Agora descobrir se o CSS do site já cobre as classes novas:

Run: `cd app && grep -n "\.chart\b" site_web.py | head`

- **Se aparecer** — a página do digest tem cópia própria das regras do PDF. Copiar para lá, no
  mesmo lugar onde `.chart` está definido, o bloco CSS inteiro da Task 2 (`.kit`, `.kit-rot`,
  `.paper-box`, `.paper-rev`, `.paper-tit`, `.paper-doi`, `.frase-box`, `.kit-brief`, `.reels`,
  `.reel`, `.reel-n`), **sem** as chaves duplas — o CSS do site pode não estar dentro de f-string.
  Conferir o contexto antes de colar.
- **Se não aparecer** — o site reusa o `<style>` do PDF e não há nada a fazer.

Em qualquer dos casos, o teste desta tarefa só verifica o HTML; a conferência visual fica na
verificação final, abrindo a página de um digest.

- [ ] **Step 4: Run tests**

Run: `cd app && python3 -m unittest discover -s tests`
Expected: OK

- [ ] **Step 5: Commit**

```bash
git add app/site_web.py app/tests/test_kit_redes.py
git commit -m "feat(kit): pagina do estudo no site usa o mesmo kit do PDF"
```

---

### Task 6: Prompt — a IA passa a emitir o JSON do kit

**Files:**
- Modify: `app/content.py:8-16` (`SYS_GANCHO`), `app/content.py:36-39` (`_prompt_gancho`)
- Test: `app/tests/test_kit_redes.py`

**Interfaces:**
- Consumes: contrato de `parse_gancho` (Task 1)
- Produces: `gerar_conteudo()["gancho"]` passa a ser JSON

- [ ] **Step 1: Write the failing test**

```python
class TestPromptGancho(unittest.TestCase):
    def setUp(self):
        import content
        self.c = content

    def test_prompt_pede_json_com_frase_e_reels(self):
        s = self.c.SYS_GANCHO
        self.assertIn("frase", s)
        self.assertIn("reels", s)
        self.assertIn("angulo", s)

    def test_prompt_proibe_completar_cota(self):
        """Modelo de IA preenche ate o numero pedido; o 3o sai inventado."""
        s = self.c.SYS_GANCHO.lower()
        self.assertIn("1 a 3", s)
        self.assertTrue("nunca invente" in s or "nao invente" in s)

    def test_prompt_mantem_as_travas_do_cfm(self):
        s = self.c.SYS_GANCHO.lower()
        self.assertIn("cfm", s)
        self.assertIn("receita", s)          # nao promover medicamento de receita p/ leigo

    def test_gerar_conteudo_devolve_gancho_parseavel(self):
        falso = ('{"frase": "F", "reels": [{"angulo": "A", "apoio": "B"}]}')
        r = self.c.gerar_conteudo({"titulo": "t", "resumo": "r", "fonte": "f"},
                                  gerar_resumo=lambda a: "resumo",
                                  gerar_gancho=lambda a: falso,
                                  gerar_grafico_json=lambda a: "{}",
                                  gerar_titulo=lambda a: "titulo")
        self.assertEqual(self.c.parse_gancho(r["gancho"])["frase"], "F")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_kit_redes.TestPromptGancho -v`
Expected: FAIL — o `SYS_GANCHO` atual não menciona `frase`/`reels`.

- [ ] **Step 3: Write minimal implementation**

Substituir `SYS_GANCHO` (content.py:8-16) por:

```python
SYS_GANCHO = (
    "Voce prepara o material de redes sociais de um medico a partir de UM estudo. "
    "Ele produz SO REELS (video curto). "
    "Responda SO JSON, sem cercas de codigo, neste formato:\n"
    '{"frase":"...","reels":[{"angulo":"...","apoio":"..."}]}\n'
    "- `frase`: o ACHADO PRINCIPAL em linguagem de paciente, uma frase, sem jargao. "
    "E o texto que vai virar imagem de post: precisa se sustentar sozinho.\n"
    "- `reels`: de 1 a 3 PAUTAS de video. Cada `angulo` e a frase que o medico fala; "
    "cada `apoio` e o dado do estudo que sustenta aquele angulo (uma linha).\n"
    "REGRAS DAS PAUTAS:\n"
    "1. De 1 a 3. PREFIRA MENOS. Se o estudo so rende uma pauta boa, devolva UMA. "
    "NUNCA invente pauta para fechar numero -- pauta fraca faz o medico parar de ler o bloco.\n"
    "2. Cada pauta sai de uma PARTE DIFERENTE do estudo (ex.: o grupo comparador, a duracao, "
    "o desenho do protocolo). Tres jeitos de dizer o mesmo achado e um Reels so, repetido.\n"
    "3. Nada de conselho de producao (formato, horario, hashtag, iluminacao) -- so ASSUNTO.\n"
    "ETICA (CFM, inegociavel): nao prometa milagre/cura, nao garanta resultado, "
    "NAO promova remedio de receita para leigo (fale do CONCEITO, nao do 'use tal remedio'), "
    "sem sensacionalismo, sem chamada para acao ('agende sua consulta'). "
    "Tudo em portugues do Brasil.")
```

Trocar `_prompt_gancho` (content.py:36-39) por:

```python
def _prompt_gancho(artigo):
    return (f"Estudo: {artigo.get('titulo','')} ({artigo.get('fonte','')}).\n"
            f"Resumo: {(artigo.get('resumo','') or '')[:900]}\n\n"
            "Devolva o JSON com a frase e as pautas de Reels deste estudo.")
```

Em `gerar_conteudo` (content.py:117), subir o teto de tokens, porque o JSON é maior que o
parágrafo antigo:

```python
        gerar_gancho = lambda a: claude(SONNET, _prompt_gancho(a), system=SYS_GANCHO, max_tokens=900)
```

- [ ] **Step 4: Run tests**

Run: `cd app && python3 -m unittest discover -s tests`
Expected: OK

- [ ] **Step 5: Commit**

```bash
git add app/content.py app/tests/test_kit_redes.py
git commit -m "feat(kit): prompt passa a emitir frase + pautas de Reels em JSON"
```

---

### Task 7: Link do estudo na mensagem do WhatsApp

⚠️ **`deliver.py:48` deriva o NOME DO ARQUIVO do caption.** Colar a URL na legenda sem separar
os dois faz o PDF chegar como `Tirzepatida_e_perda_de_peso_https_do.pdf`.

**Files:**
- Modify: `app/deliver.py:46-50` (`_evolution_media_payload`), `app/deliver.py:79-83` (`enviar_pdf`)
- Modify: `app/daily.py:335`, `app/daily.py:718` (chamadas)
- Test: `app/tests/test_deliver_phone.py` (arquivo existente de testes do deliver)

**Interfaces:**
- Consumes: nada
- Produces: `deliver.enviar_pdf(whatsapp, pdf_path, caption="", nome_arquivo="")`.
  Quando `nome_arquivo` vem vazio, mantém o comportamento antigo (derivar do caption).

- [ ] **Step 1: Write the failing test**

Adicionar em `app/tests/test_deliver_phone.py`:

```python
class TestNomeDoArquivo(unittest.TestCase):
    def test_nome_do_arquivo_ignora_a_url_da_legenda(self):
        """A legenda passou a levar o link do estudo; o nome do arquivo nao pode virar lixo."""
        import deliver
        p = deliver._evolution_media_payload(
            "5543999990000", __file__,
            caption="Tirzepatida semanal\n\nEstudo: https://doi.org/10.1056/x",
            nome_arquivo="Tirzepatida semanal")
        self.assertEqual(p["fileName"], "Tirzepatida_semanal.pdf")
        self.assertIn("https://doi.org/10.1056/x", p["caption"])

    def test_sem_nome_explicito_mantem_o_comportamento_antigo(self):
        import deliver
        p = deliver._evolution_media_payload("5543999990000", __file__, caption="Titulo do estudo")
        self.assertEqual(p["fileName"], "Titulo_do_estudo.pdf")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_deliver_phone -v`
Expected: FAIL — `_evolution_media_payload() got an unexpected keyword argument 'nome_arquivo'`

- [ ] **Step 3: Write minimal implementation**

Em `app/deliver.py`, trocar `_evolution_media_payload` (linhas 46-50) por:

```python
def _evolution_media_payload(whatsapp, pdf_path, caption, nome_arquivo=""):
    """`nome_arquivo` separado da legenda de proposito: a legenda passou a levar o LINK
    do estudo, e o nome do arquivo saia dela -- o PDF chegava como
    `Titulo_do_estudo_https_doi_org_10_1.pdf` no celular do assinante."""
    b64 = base64.b64encode(open(pdf_path, "rb").read()).decode("ascii")
    base = (nome_arquivo or caption)
    nome = (re.sub(r"[^\w-]", "_", base)[:40] or "documento") + ".pdf"
    return {"number": phone.para_api(whatsapp), "mediatype": "document", "mimetype": "application/pdf",
            "media": b64, "fileName": nome, "caption": caption}
```

Trocar `enviar_pdf` (linhas 79-83) por:

```python
def enviar_pdf(whatsapp, pdf_path, caption="", nome_arquivo=""):
    """pdf_path = arquivo LOCAL. Evolution manda em base64; Z-API precisaria de URL."""
    if config.WHATSAPP_BACKEND == "evolution":
        return _evolution_post("message/sendMedia",
                               _evolution_media_payload(whatsapp, pdf_path, caption, nome_arquivo))
    return _zapi_post("send-document/pdf", _zapi_pdf_payload(whatsapp, pdf_path, caption))
```

Em `app/daily.py:335`, trocar:

```python
            deliver.enviar_pdf(w, master_pdf, caption=dg.get("titulo_pt", ""))
```

por:

```python
            titulo = dg.get("titulo_pt", "")
            url = (dg.get("url") or "").strip()
            legenda = f"{titulo}\n\nEstudo original: {url}" if url else titulo
            deliver.enviar_pdf(w, master_pdf, caption=legenda, nome_arquivo=titulo)
```

Para `app/daily.py:718`, primeiro descobrir o que o `ctx` carrega:

Run: `cd app && grep -n "ctx = \|ctx\[" daily.py | head -20`

- **Se o `ctx` já tiver a URL** (chave `url` ou o `art` dentro dele), aplicar a mesma mudança:

```python
            titulo = ctx["titulo"]
            url = (ctx.get("url") or "").strip()
            legenda = f"{titulo}\n\nEstudo original: {url}" if url else titulo
            deliver.enviar_pdf(whatsapp, ctx["master_pdf"], caption=legenda, nome_arquivo=titulo)
```

- **Se não tiver**, acrescentar `"url": art.get("url", "")` no dicionário onde o `ctx` é montado,
  usando o **mesmo** `art` que já alimenta `montar_html` no `_pdf_mestre` (`daily.py:640`).
  Não criar chave com outro nome nem buscar a URL de outra fonte — os dois envios têm que mandar
  exatamente o mesmo link.

- [ ] **Step 4: Run tests**

Run: `cd app && python3 -m unittest discover -s tests`
Expected: OK

- [ ] **Step 5: Commit**

```bash
git add app/deliver.py app/daily.py app/tests/test_deliver_phone.py
git commit -m "feat(kit): legenda do WhatsApp leva o link do estudo, sem estragar o nome do arquivo"
```

---

## Verificação final (antes de merge)

- [ ] `cd app && python3 -m unittest discover -s tests` → OK
- [ ] Gerar um PDF de verdade e abrir: os três blocos aparecem, nada estoura a página, e o link da
      referência **clica**. Um estudo com 1 pauta só tem que ficar tão bom quanto um com 3.
- [ ] Abrir a página de um digest ANTIGO no site (gancho em texto puro) e confirmar que não quebrou.
- [ ] `git log --oneline` → 7 commits, um por tarefa.
