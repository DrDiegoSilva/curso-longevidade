# Cartão do estudo com cara de paper — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesenhar o cartão "1 · O estudo" do kit de redes do PDF diário para ter cara de
masthead de periódico acadêmico, e remover a numeração "1·"/"2·" desses dois blocos
específicos (kit-paper e kit-frase), que hoje são pensados para print recortado sem marca.

**Architecture:** Mudança de apresentação pura em `app/pdf.py::_kit_html` (HTML) e no CSS
embutido em `app/pdf.py::montar_html`, espelhada na cópia própria de CSS que `app/site_web.py`
mantém para renderizar o mesmo HTML no portal. Nenhuma mudança de dados, parsing ou IA.

**Tech Stack:** Python 3, HTML/CSS puro (sem framework), `unittest`.

## Global Constraints

- Não mexe em `app/content.py` (parsing/prompt do gancho), `app/daily.py` nem no resumo clínico
  (`SYS_ESTUDO`) — spec: `docs/superpowers/specs/2026-08-21-bloco-printavel-item42-design.md`.
- Os blocos 3 (Reels) e 4 (limites do CFM) mantêm a numeração `kit-rot` — só os blocos 1 e 2
  perdem o rótulo.
- Sem marca do Diego nos dois blocos — comportamento já existente, não regredir.
- A cor do masthead (`#14332a`) é FIXA, não o `{cor}` do tema do dia — preserva o comportamento
  atual do `.paper-box` (ver seção "Por que não replicar..." da spec).
- `app/site_web.py` tem cópia PRÓPRIA do CSS do kit (não importa `app/pdf.py`) — toda classe
  nova ou alterada precisa existir nos dois arquivos, sob pena de o portal renderizar sem
  estilo. Guardado por `tests/test_kit_redes.py::TestKitNoSite::test_site_tem_o_css_do_kit`.
- Todo campo de texto (`revista`, `titulo`, `doi`) continua escapado via `html.escape` antes de
  virar HTML — nenhuma exceção nova.
- Sem HTML/CSS órfão quando falta um dado (upload manual sem fonte/data/DOI) — mesma regra
  "só com o que existe" que `_meta_linha` já aplica no cabeçalho principal do PDF.

---

## Arquivos afetados

| Arquivo | Papel |
|---|---|
| `app/pdf.py` | `_kit_html` (monta o HTML dos 4 blocos do kit) e o CSS embutido em `montar_html` (linhas do `<style>`) |
| `app/site_web.py` | cópia própria do CSS do kit, usada quando o mesmo HTML é renderizado no portal |
| `app/tests/test_kit_redes.py` | testes de `_kit_html`, `montar_html` e `site_web.pagina_digest` |

Nenhum arquivo novo é criado.

---

### Task 1: `app/pdf.py` — masthead sem rótulo no cartão do estudo e na frase

**Files:**
- Modify: `app/pdf.py:257-320` (`_kit_html`)
- Modify: `app/pdf.py` — adicionar `_data_doi_linha` logo após `_meta_linha` (hoje linhas
  331-342)
- Modify: `app/pdf.py:442-450` (CSS do kit dentro do `<style>` de `montar_html`)
- Test: `app/tests/test_kit_redes.py`

**Interfaces:**
- Produces: `_data_doi_linha(data, doi) -> str` — nova função módulo-level em `app/pdf.py`,
  devolve `"data &middot; DOI x"` só com o que existir (string vazia se os dois faltarem), já
  com `html.escape` aplicado internamente.
- Modifica (assinatura não muda): `_kit_html(gancho_bruto, artigo) -> str` — mesmos parâmetros
  e contrato de retorno (string HTML do `<div class="kit">...</div>`, ou `""` se nada a
  mostrar).

- [ ] **Step 1: Escrever os testes que ainda falham**

Abra `app/tests/test_kit_redes.py`. Insira uma classe nova **depois** de `TestMontarHtmlKit`
(que termina na função `test_classes_novas_existem_no_css_do_pdf_e_do_site`) e **antes** de
`class TestPromptGancho(unittest.TestCase):`:

```python
class TestCartaoDoEstudoSemRotulo(unittest.TestCase):
    """O cartao "1 O estudo" e a "2 A frase" perderam a numeracao e ganharam cara de
    masthead de periodico -- pensados pra print recortado, sem marca do Diego (item 42
    do backlog). Ver docs/superpowers/specs/2026-08-21-bloco-printavel-item42-design.md."""

    def setUp(self):
        import pdf
        self.pdf = pdf
        self.artigo = {"titulo_original": "Effects of Intermittent Fasting",
                       "fonte": "New England Journal of Medicine", "data": "2026-08-15",
                       "doi": "10.1056/NEJMoa2026123"}

    def test_rotulos_1_e_2_nao_aparecem_mais(self):
        h = self.pdf._kit_html('{"frase": "Jejum emagrece igual."}', self.artigo)
        self.assertNotIn("1 &middot; O estudo", h)
        self.assertNotIn("2 &middot; A frase", h)

    def test_rotulos_3_e_4_continuam(self):
        gancho = '{"frase": "F", "limites": ["L"], "reels": [{"gancho": "g"}]}'
        h = self.pdf._kit_html(gancho, self.artigo)
        self.assertIn("3 &middot; Reels que saem deste estudo", h)
        self.assertIn("4 &middot; O que n&atilde;o d&aacute; pra afirmar", h)

    def test_masthead_tem_revista_regua_e_titulo(self):
        h = self.pdf._kit_html("", self.artigo)
        self.assertIn('<p class="paper-rev">New England Journal of Medicine</p>', h)
        self.assertIn('<hr class="paper-rule">', h)
        self.assertIn("Effects of Intermittent Fasting", h)

    def test_rodape_combina_data_e_doi(self):
        h = self.pdf._kit_html("", self.artigo)
        self.assertIn('<p class="paper-doi">2026-08-15 &middot; DOI 10.1056/NEJMoa2026123</p>', h)

    def test_sem_revista_nao_sobra_masthead_vazio(self):
        art = dict(self.artigo, fonte="")
        h = self.pdf._kit_html("", art)
        self.assertNotIn('<p class="paper-rev">', h)
        self.assertNotIn('<hr class="paper-rule">', h)
        self.assertIn("Effects of Intermittent Fasting", h)

    def test_sem_data_e_sem_doi_nao_sobra_rodape_vazio(self):
        art = dict(self.artigo, data="", doi="")
        h = self.pdf._kit_html("", art)
        self.assertNotIn('<p class="paper-doi">', h)

    def test_rodape_so_com_data_sem_doi(self):
        art = dict(self.artigo, doi="")
        h = self.pdf._kit_html("", art)
        self.assertIn('<p class="paper-doi">2026-08-15</p>', h)

    def test_rodape_so_com_doi_sem_data(self):
        art = dict(self.artigo, data="")
        h = self.pdf._kit_html("", art)
        self.assertIn('<p class="paper-doi">DOI 10.1056/NEJMoa2026123</p>', h)

    def test_revista_e_titulo_escapam_html(self):
        art = dict(self.artigo, fonte="<script>alert(1)</script>",
                   titulo_original="<script>alert(2)</script>")
        h = self.pdf._kit_html("", art)
        self.assertNotIn("<script>alert(1)</script>", h)
        self.assertNotIn("<script>alert(2)</script>", h)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", h)
        self.assertIn("&lt;script&gt;alert(2)&lt;/script&gt;", h)

    def test_doi_escapa_html(self):
        art = dict(self.artigo, doi="<script>alert(3)</script>")
        h = self.pdf._kit_html("", art)
        self.assertNotIn("<script>alert(3)</script>", h)
        self.assertIn("&lt;script&gt;alert(3)&lt;/script&gt;", h)
```

Também adicione UM teste dentro da classe **já existente** `TestMontarHtmlKit` (logo depois de
`test_classes_novas_existem_no_css_do_pdf_e_do_site`), reaproveitando `self.artigo`/
`self.conteudo`/`self.tema` do `setUp` daquela classe — ele confirma que o CSS novo está no
`<style>` que só `montar_html` (não `_kit_html`) produz:

```python
    def test_css_do_masthead_existe(self):
        html = self.pdf.montar_html(self.artigo, self.conteudo, self.tema)
        self.assertIn(".paper-rule {", html)
        self.assertIn(".kit-frase {", html)
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `cd app && python3 -m unittest tests.test_kit_redes -v 2>&1 | tail -40`
Expected: `TestCartaoDoEstudoSemRotulo` — todos os testes novos falham (`_kit_html` ainda gera
`kit-rot`/`paper-rev` como `<div>`, não como `<p>`, e a classe `.paper-rule` não existe).
`test_css_do_masthead_existe` falha (`.paper-rule {` não está no CSS ainda).

- [ ] **Step 3: Implementar `_data_doi_linha` e reescrever `_kit_html`**

Em `app/pdf.py`, logo depois da função `_meta_linha` (que termina na linha 342 de hoje,
`return " &middot; ".join(partes)`), adicione:

```python


def _data_doi_linha(data, doi):
    """`data · DOI x`, só com o que existe -- mesma regra do `_meta_linha`, mas sem a
    revista (que no masthead do paper já aparece sozinha, acima do título)."""
    esc = _html.escape
    data = (data or "").strip()
    doi = (doi or "").strip()
    partes = []
    if data:
        partes.append(esc(data))
    if doi:
        partes.append(f"DOI {esc(doi)}")
    return " &middot; ".join(partes)
```

Substitua a função `_kit_html` inteira (linhas 257-320 de hoje) por:

```python
def _kit_html(gancho_bruto, artigo):
    """Kit de post no rodape: recorte do paper + a frase + as pautas de Reels + os
    limites do CFM.

    Os dois primeiros blocos sao pensados para PRINT RECORTADO -- o medico ja fazia
    isso na mao, printando o PDF do artigo. Por isso nao levam a marca do Diego (quem
    posta e o assinante) NEM rotulo "1·"/"2·" -- isso e' numeracao do kit inteiro, e
    apareceria no print de quem capturar so' os 2. O terceiro e briefing pra equipe de
    marketing, e por isso e visualmente diferente E numerado: se parecesse com os
    outros, alguem recortaria a instrucao junto e postaria. O quarto sao os limites
    daquele estudo -- fica por ESTUDO e nao por pauta, porque a evidencia e a mesma
    pras tres.
    """
    import content
    esc = _html.escape
    dados = content.parse_gancho(gancho_bruto)
    titulo = (artigo.get("titulo_original") or artigo.get("titulo") or "").strip()
    blocos = []

    if titulo:
        revista = (artigo.get("fonte") or "").strip()
        rodape = _data_doi_linha(artigo.get("data"), artigo.get("doi"))
        blocos.append(
            '<div class="kit-paper"><div class="paper-box">'
            # Estudo subido na mao nao tem fonte: sem a guarda sobra o topo do
            # masthead vazio (nome + regua) acima do titulo.
            + (f'<p class="paper-rev">{esc(revista)}</p><hr class="paper-rule">' if revista else "")
            + f'<p class="paper-tit">{esc(titulo)}</p>'
            + (f'<p class="paper-doi">{rodape}</p>' if rodape else "")
            + '</div></div>')

    if dados["frase"]:
        blocos.append(
            f'<div class="kit-frase"><div class="frase-box"><p>{esc(dados["frase"])}</p></div></div>')

    if dados["reels"]:
        cards = []
        for i, r in enumerate(dados["reels"], 1):
            rotulo = f'<span class="reel-tit">{esc(r["titulo"])}</span>' if r["titulo"] else ""
            passos = "".join(f"<li>{esc(p)}</li>" for p in r["roteiro"])
            roteiro = (f'<p class="reel-mini">O que falar, nesta ordem</p>'
                       f'<ol class="reel-roteiro">{passos}</ol>') if passos else ""
            apoio = (f'<p class="reel-apoio"><b>Dado do estudo:</b> {esc(r["apoio"])}</p>'
                     if r["apoio"] else "")
            cards.append(
                f'<div class="reel-card">'
                f'<div class="reel-top"><span class="reel-n">{i}</span>{rotulo}</div>'
                f'<p class="reel-mini">Primeiros 3 segundos</p>'
                f'<p class="reel-gancho">{esc(r["gancho"])}</p>'
                f'{roteiro}{apoio}</div>')
        blocos.append(
            f'<div class="kit-brief"><div class="kit-rot">3 &middot; Reels que saem deste estudo</div>'
            f'<div class="reel-cards">{"".join(cards)}</div></div>')

    if dados["limites"]:
        itens = "".join(f"<li>{esc(x)}</li>" for x in dados["limites"])
        blocos.append(
            f'<div class="kit-limites"><div class="kit-rot">4 &middot; O que n&atilde;o d&aacute; pra afirmar</div>'
            f'<ul>{itens}</ul></div>')

    if not blocos:
        return ""
    return f'<div class="kit">{"".join(blocos)}</div>'
```

(Único conteúdo alterado nos blocos 3 e 4: nada — copiados como já estão hoje, sem o `kit-rot`
que sai só dos blocos 1 e 2.)

- [ ] **Step 4: Atualizar o CSS do kit**

Ainda em `app/pdf.py`, dentro do `<style>` de `montar_html`, localize o bloco (hoje por volta
da linha 438-450):

```
  .kit {{ margin:22px 0 6px; display:flex; flex-direction:column; gap:15px; }}
  .kit-rot {{ font-family:system-ui,sans-serif; font-size:13px; letter-spacing:.08em;
           text-transform:uppercase; color:#8a6a06; font-weight:700; margin-bottom:7px;
           break-after:avoid; }}
  .paper-box {{ border:1px solid #d8ddd7; border-top:3px solid #14332a; background:#fcfdfc;
           padding:14px 17px; break-inside:avoid; }}
  .paper-rev {{ font-family:system-ui,sans-serif; font-size:11.5px; letter-spacing:.13em;
           text-transform:uppercase; color:#14332a; font-weight:700; margin-bottom:9px; }}
  .paper-tit {{ margin:0 0 9px; font-size:17px; line-height:1.28; color:#16211c; }}
  .paper-doi {{ font-family:ui-monospace,Menlo,monospace; font-size:13px; color:#6f7d78; }}
  .frase-box {{ border:2px solid #c9a227; border-radius:12px; padding:17px 20px;
           background:linear-gradient(180deg,#fff9e9,#fbf3d9); break-inside:avoid; }}
  .frase-box p {{ margin:0; font-size:18.5px; line-height:1.4; color:#3a2f10; }}
```

Substitua por:

```
  .kit {{ margin:22px 0 6px; display:flex; flex-direction:column; gap:15px; }}
  .kit-rot {{ font-family:system-ui,sans-serif; font-size:13px; letter-spacing:.08em;
           text-transform:uppercase; color:#8a6a06; font-weight:700; margin-bottom:7px;
           break-after:avoid; }}
  .paper-box {{ border-top:2.5px solid #14332a; border-bottom:1px solid #14332a; background:#fcfdfc;
           padding:16px 20px 18px; break-inside:avoid; }}
  .paper-rev {{ text-align:center; font-style:italic; font-size:14px; letter-spacing:.02em;
           color:#14332a; margin:0 0 10px; }}
  .paper-rule {{ border:none; border-top:1px solid #c7cec8; margin:0 0 12px; }}
  .paper-tit {{ text-align:center; margin:0 0 10px; font-size:17.5px; line-height:1.32; color:#16211c; }}
  .paper-doi {{ text-align:center; font-family:ui-monospace,Menlo,monospace; font-size:11.5px; color:#6f7d78; }}
  .kit-frase {{ margin-top:8px; }}
  .frase-box {{ border:2px solid #c9a227; border-radius:12px; padding:17px 20px;
           background:linear-gradient(180deg,#fff9e9,#fbf3d9); break-inside:avoid; }}
  .frase-box p {{ margin:0; font-size:18.5px; line-height:1.4; color:#3a2f10; }}
```

(A linha `.kit-brief .kit-rot {{ color:#6f7d78; }}` logo depois deste bloco não muda — mantenha
como está.)

- [ ] **Step 5: Rodar os testes e confirmar que passam**

Run: `cd app && python3 -m unittest tests.test_kit_redes -v 2>&1 | tail -50`
Expected: PASS em todos os testes de `TestCartaoDoEstudoSemRotulo` e no
`test_css_do_masthead_existe` novo. Nenhum teste pré-existente quebrou.

Run também a suíte inteira, pois `_kit_html` é usado por `montar_html` e por
`site_web.pagina_digest` (que ainda não foi atualizado — o próximo passo é justamente ver ele
falhar por causa disso):

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -20`
Expected: `tests.test_kit_redes.TestKitNoSite.test_site_tem_o_css_do_kit` **FALHA** — é o sinal
de que a Task 2 (espelhar o CSS no site) ainda não foi feita. Nenhuma outra falha deve aparecer.

- [ ] **Step 6: Commit**

```bash
git add app/pdf.py app/tests/test_kit_redes.py
git commit -m "$(cat <<'EOF'
feat(pdf): cartao do estudo vira masthead de paper, sem rotulo 1/2

Os blocos "1 O estudo" e "2 A frase" do kit de redes sao pensados pra
print recortado desde 2026-08-04 (sem marca do Diego), mas tinham cara
de card generico. Viram masthead de periodico academico (revista em
italico + regua + titulo centralizado + data/DOI no rodape) e perdem
a numeracao "1./2." -- que e' navegacao do kit inteiro e apareceria
no print de quem capturar so' os 2. Blocos 3/4 continuam numerados.

Ver docs/superpowers/specs/2026-08-21-bloco-printavel-item42-design.md
EOF
)"
```

---

### Task 2: `app/site_web.py` — espelhar o CSS do masthead no portal

**Files:**
- Modify: `app/site_web.py:269-277` (cópia própria do CSS do kit)
- Test: `app/tests/test_kit_redes.py::TestKitNoSite::test_site_tem_o_css_do_kit`

**Interfaces:**
- Consumes: nenhuma função nova — só CSS estático em `site_web._CSS`.
- Produces: nenhuma interface nova exposta a outras tasks.

- [ ] **Step 1: Estender o teste que já existe**

Em `app/tests/test_kit_redes.py`, dentro de `class TestKitNoSite`, localize
`test_site_tem_o_css_do_kit` (hoje por volta da linha 420-431):

```python
    def test_site_tem_o_css_do_kit(self):
        """O site tem copia PROPRIA do CSS do PDF: sem estas classes o kit sai sem estilo.

        `.reels`/`.reel` (lista) viraram `.reel-cards`/`.reel-card` (cards com roteiro
        numerado) na Task 3 -- atualizado junto."""
        import site_web
        d = {"titulo_pt": "T", "titulo_original": "T EN", "fonte": "NEJM", "data": "2026-08-04",
             "doi": "x", "url": "https://x", "resumo": "r", "grafico": None,
             "gancho": '{"frase": "F", "reels": [{"angulo": "A"}]}'}
        html = site_web.pagina_digest({"rotulo": "Obesidade", "emoji": "", "slug": "obesidade", "cor": "#14332a"}, d)
        for classe in (".paper-box{", ".frase-box{", ".reel-cards{", ".reel-card{", ".reel-n{"):
            self.assertIn(classe, html, classe)
```

Troque a tupla de classes por (acrescenta `.paper-rule{` e `.kit-frase{`, mantém as demais):

```python
        for classe in (".paper-box{", ".paper-rule{", ".kit-frase{", ".frase-box{",
                       ".reel-cards{", ".reel-card{", ".reel-n{"):
            self.assertIn(classe, html, classe)
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_kit_redes.TestKitNoSite.test_site_tem_o_css_do_kit -v`
Expected: FAIL — `.paper-rule{` (e possivelmente `.kit-frase{`) ainda não existem em
`site_web.py`.

- [ ] **Step 3: Espelhar o CSS em `site_web.py`**

Em `app/site_web.py`, localize o bloco (hoje linhas 269-277, logo abaixo do comentário "Kit de
redes (mesmo bloco do PDF...)"):

```
.kit{margin:24px 0 6px;display:flex;flex-direction:column;gap:20px}
.kit-rot{font-family:system-ui,sans-serif;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#8a6a06;font-weight:700;margin-bottom:8px}
.paper-box{border:1px solid #d8ddd7;border-top:3px solid #14332a;background:#fcfdfc;padding:16px 18px}
.paper-rev{font-family:system-ui,sans-serif;font-size:11px;letter-spacing:.13em;text-transform:uppercase;color:#14332a;font-weight:700;margin-bottom:8px}
.paper-tit{margin:0 0 10px;font-size:19px;line-height:1.28;color:#16211c}
.paper-doi{font-family:ui-monospace,Menlo,monospace;font-size:12.5px;color:#6f7d78;word-break:break-word}
.frase-box{border:2px solid var(--ouro);border-radius:12px;padding:20px 22px;background:linear-gradient(180deg,#fff9e9,#fbf3d9)}
.frase-box p{margin:0;font-size:20px;line-height:1.4;color:#3a2f10}
.kit-brief .kit-rot{color:#6f7d78}
```

Substitua por (mantém a escala de fonte maior do site, já maior que a do PDF hoje — só aplica o
mesmo tratamento de masthead: centralizado, itálico, régua, rodapé combinado):

```
.kit{margin:24px 0 6px;display:flex;flex-direction:column;gap:20px}
.kit-rot{font-family:system-ui,sans-serif;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#8a6a06;font-weight:700;margin-bottom:8px}
.paper-box{border-top:2.5px solid #14332a;border-bottom:1px solid #14332a;background:#fcfdfc;padding:18px 22px 20px}
.paper-rev{text-align:center;font-style:italic;font-size:15px;letter-spacing:.02em;color:#14332a;margin:0 0 11px}
.paper-rule{border:none;border-top:1px solid #c7cec8;margin:0 0 13px}
.paper-tit{text-align:center;margin:0 0 11px;font-size:19px;line-height:1.32;color:#16211c}
.paper-doi{text-align:center;font-family:ui-monospace,Menlo,monospace;font-size:12.5px;color:#6f7d78;word-break:break-word}
.kit-frase{margin-top:9px}
.frase-box{border:2px solid var(--ouro);border-radius:12px;padding:20px 22px;background:linear-gradient(180deg,#fff9e9,#fbf3d9)}
.frase-box p{margin:0;font-size:20px;line-height:1.4;color:#3a2f10}
.kit-brief .kit-rot{color:#6f7d78}
```

- [ ] **Step 4: Rodar o teste e confirmar que passa**

Run: `cd app && python3 -m unittest tests.test_kit_redes.TestKitNoSite.test_site_tem_o_css_do_kit -v`
Expected: PASS.

- [ ] **Step 5: Rodar a suíte inteira**

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -20`
Expected: `OK`, sem nenhuma falha.

- [ ] **Step 6: Commit**

```bash
git add app/site_web.py app/tests/test_kit_redes.py
git commit -m "$(cat <<'EOF'
fix(site): espelha o CSS do masthead do paper no portal

app/site_web.py tem copia propria do CSS do kit (renderiza o mesmo
HTML de app/pdf.py._kit_html via site_web.pagina_digest) -- sem isto
o cartao do estudo sairia sem estilo no portal, so' no PDF.
EOF
)"
```

---

## Verificação manual (fora do escopo dos testes automatizados)

Depois das duas tasks, gerar um PDF de amostra localmente (fora do container, com Chrome) pra
conferir visualmente o masthead — não é um passo de teste automatizado porque o ambiente de
produção roda Chromium dentro do container, mas serve de checagem rápida antes de pedir deploy:

```bash
cd app && python3 -c "
import sys; sys.path.insert(0, '.')
import pdf
ART = {'titulo_original': 'Effects of Intermittent Fasting on Weight Loss',
       'fonte': 'New England Journal of Medicine', 'data': '2026-08-15',
       'doi': '10.1056/NEJMoa2026123', 'url': 'https://doi.org/10.1056/NEJMoa2026123'}
TEMA = {'cor': '#14332a', 'rotulo': 'Obesidade', 'emoji': '⚖️'}
conteudo = {'titulo_pt': 'T', 'resumo': 'Resumo de teste.',
            'gancho': '{\"frase\": \"Frase de teste.\"}'}
with open('/tmp/amostra_masthead.html', 'w') as f:
    f.write(pdf.montar_html(ART, conteudo, TEMA))
print('gerado /tmp/amostra_masthead.html')
"
```

Depois, renderizar `/tmp/amostra_masthead.html` com Chrome headless (`--print-to-pdf`) e olhar
o cartão do estudo — deve aparecer sem rótulo "1·", com a revista em itálico centralizada, a
régua, o título centralizado e "2026-08-15 · DOI 10.1056/NEJMoa2026123" no rodapé.

## Self-Review

**Cobertura da spec:** cartão vira masthead ✅ (Task 1, CSS); rótulos 1/2 saem ✅ (Task 1,
`_kit_html`); rótulos 3/4 continuam ✅ (teste dedicado); casos sem revista/data/DOI ✅ (3
testes); reagrupamento revista-sozinha + data+DOI ✅ (`_data_doi_linha`); espelho no site ✅
(Task 2); sem UI nova de aprovação ✅ (nada implementado, fora de escopo cumprido); sem mudar
posição no PDF ✅ (nenhuma mudança em `montar_html` além do CSS); 2 caixas separadas com mais
respiro ✅ (`.kit-frase{margin-top:...}` soma ao gap do `.kit`, sem fundir os `<div>`).

**Placeholders:** nenhum "TBD"/"implementar depois" — todo código dos steps é literal, pronto
para copiar.

**Consistência de tipos/nomes:** `_data_doi_linha(data, doi)` usado uma única vez, dentro de
`_kit_html`, com os mesmos nomes de parâmetro em toda parte. Nomes de classes CSS
(`paper-rev`, `paper-rule`, `paper-tit`, `paper-doi`, `kit-frase`) idênticos entre
`app/pdf.py` e `app/site_web.py`.
