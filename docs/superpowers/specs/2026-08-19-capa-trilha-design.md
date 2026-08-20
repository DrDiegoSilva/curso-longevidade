# Capa e página 2 do PDF da trilha do consultório

**Data:** 2026-08-19
**Base:** `origin/main` = `aeabced`
**Branch:** a definir na implementação (fora do worktree `aviso-venda-whatsapp`, que está
ocupado com o item 36 fatia 2)

## O problema

O Diego abriu a prévia de uma peça da trilha (`/admin/trilha/peca/<n>`) e viu uma página
branca com uma etiqueta cinza pequena e um título preto — sem capa, sem identidade visual.
Comparado com o PDF do estudo diário (que passou pelo redesenho do item 35: faixa colorida,
assinatura, selo de área), a trilha parece um documento avulso, não parte do mesmo produto.

Renderizei o PDF real (peça 1, "O custo real da sua hora") pelo mesmo motor de produção
(Chromium headless via `pdf.gerar_pdf`) pra confirmar o problema com o artefato de verdade,
não com a prévia HTML. Dois achados guiaram o desenho:

1. **Sem capa nenhuma.** `pdf_trilha.montar_html` (`app/pdf_trilha.py`) não tem o equivalente
   da `.cover`/`.brand`/`.tag` que `app/pdf.py` usa — só uma linha de texto pequena.
2. **A página 2 sobra quase toda em branco.** O conteúdo termina a ~1/3 da segunda página.

## Decisões do Diego (2026-08-19)

Percorridas com mockups reais (companheiro visual + renders reais via Chromium):

1. **Capa com banda verde**, não a cor dourada/marrom testada primeiro — `#0e211a → #1e5045`,
   o mesmo par de tons que `pdf.py` usa na capa do estudo diário.
2. **Ícone "DS" + "Dr. Diego Silva" no topo da banda**, alinhados na mesma linha com o selo
   "Semana X de 12" (à direita). "Trilha do Consultório Lucrativo" (ver renomeação abaixo) fica
   numa segunda linha, menor, em dourado, abaixo dessa primeira linha.
3. **Ícone de 42px de altura** (testado em 28px primeiro; o Diego pediu maior).
4. **Renomear** "Trilha do Consultório" → **"Trilha do Consultório Lucrativo"**.
5. **Sem selo de tema/categoria.** Cheguei a desenhar um selo "Mentalidade" ao lado de
   "Semana X de 12", mas **não existe campo de categoria por peça** no banco
   (`trilha_pecas`: `eixo`, `titulo`, `corpo`, `micro_resultado`, `mentalidade`,
   `ferramenta_slug` — sem coluna de tema/tipo). Inventar uma taxonomia agora seria decisão de
   produto que o Diego não pediu. Ele escolheu não ter o selo.
6. **Página 2: aceitar que ela existe, mas fazer parecer proposital.** Medi as 12 peças reais
   (`seed/trilha/*.md`): o corpo varia de 2.176 a 4.661 caracteres, e pelo menos 4 peças
   (01, 04, 05, 07) são longas o bastante pra vazar pra 2 páginas mesmo com tipografia
   apertada — **testei isso de verdade**, renderizando com margem e entrelinha reduzidas
   (sem tocar no tamanho da letra), e a peça 1 continuou em 2 páginas. Forçar tudo em 1
   página exigiria diminuir a letra, que o Diego não quer. Decisão: blocos de "Sua tarefa"
   e "Mentalidade" maiores e mais ricos (borda dourada, fundo levemente diferenciado), pra
   quando a página 2 existir ela pareça um fechamento desenhado, não sobra de texto.

## A logo — de onde veio e o que NÃO usar

O Diego mencionou querer a logo da clínica e a ideia de um "ecossistema DS" — registrada
como **item 41 do backlog** (`curso-longevidade-backlog.md`), maior que esta entrega e sem
asset pronto pro produto inteiro.

Vasculhei `/Users/diegosilva/dev/clinicdspro/public/` (outro repositório, o SaaS de gestão de
clínica) atrás de arquivos de logo. Achei várias marcas de produtos DIFERENTES — importante
não confundir:

| Arquivo | O que é | Usar aqui? |
|---|---|---|
| `logos/clinicds-logo-dark-bg.png`, `logo-clinicdspro.svg`, `logos/clinicds-pro-*.svg` | Marca do **ClinicDS Pro** (o SaaS de gestão) | ❌ produto errado |
| `logos/logo-ds-wellness-longevidade.png` | "DS" + "WELLNESS LONGEVIDADE" | ❌ o Diego queria só o ícone, texto à parte |
| `imunidade/dr-diego-logo.png` | Ícone "S" + "Dr. Diego Silva" + tagline, **tudo já achatado numa imagem só** (texto branco, invisível em fundo branco — foi o que me enganou na 1ª tentativa) | ❌ não dá pra separar o texto pra estilizar à parte |
| **`logos/ds-mark-512.png`** | **Só o monograma "DS"**, traço dourado em gradiente, 512×512, fundo verde-escuro SÓLIDO opaco (`#143... ` → RGB exato `(20,51,42)`) | ✅ **É este** |

### Isolar o ícone (o fundo verde do arquivo original não pode ir pra capa)

`ds-mark-512.png` tem o traço dourado sobre um quadrado verde-escuro opaco — não é
transparente. Escrevi um script que remove esse fundo por chroma-key (todo pixel a menos de
30 de distância euclidiana de RGB `(20,51,42)` vira transparente) e recorta pro bounding box
do conteúdo real. Resultado testado e aprovado: `504×504`, RGBA, fundo 100% transparente,
traço dourado limpo — composto sobre a banda verde da capa (`#6b5220` na 1ª tentativa,
depois `#0e211a→#1e5045`) sem halo nem artefato de borda.

**Recipe pra reproduzir** (a implementação vai rodar isto uma vez e congelar o resultado):

```python
from PIL import Image
import math

im = Image.open("ds-mark-512.png").convert("RGBA")
bg = (20, 51, 42)
thresh = 30
out = Image.new("RGBA", im.size)
for x in range(im.width):
    for y in range(im.height):
        r, g, b, a = im.getpixel((x, y))
        if a == 0:
            continue
        d = math.sqrt((r-bg[0])**2 + (g-bg[1])**2 + (b-bg[2])**2)
        if d >= thresh:
            out.putpixel((x, y), (r, g, b, a))
crop = out.crop(out.getbbox())  # 504x504
```

### Onde o arquivo processado mora

Este repositório (`app/`) **não tem nenhum arquivo binário hoje** — `pdf.py` desenha toda a
textura da capa como SVG inline (`_MOTIF`, uma string Python), sem imagem nenhuma no disco.
Pra manter essa convenção (zero dependência de asset externo, tudo no controle do deploy),
o ícone processado entra como **string base64 embutida no código** (`pdf_trilha.py`), do
mesmo jeito que `_MOTIF` já é uma constante grande — não como um arquivo `.png` solto em
`app/`. É mais feio de ler no source, mas evita introduzir o primeiro asset binário do zero
num projeto que nunca teve nenhum.

**A logo entra só na capa da trilha por enquanto.** A capa do estudo diário (`pdf.py`)
continua com o padrão de texto que já tem — trazer a logo pra lá também é decisão maior
(item 41), não desta entrega.

## O que muda

### 1. `config.TRILHA_NOME`

```python
TRILHA_NOME = os.environ.get("DSCURSO_TRILHA_NOME") or "Trilha do Consultório Lucrativo"
```

Propaga sozinho pra tudo que já lê essa constante: a capa nova, o rodapé do PDF
(`pdf_trilha.montar_html`), o título das páginas do portal do assinante (`site_web.py:944,
954, 2531, 2537`) e a legenda que sai junto do PDF no WhatsApp (`trilha.py:179`). Nenhum
desses lugares precisa de edição própria — é o motivo de já ser uma constante única (comentário
no `config.py`: "TRILHA_NOME é provisório").

### 2. Capa nova em `pdf_trilha.montar_html`

Estrutura (todo texto passa por `_esc`, como já é):

```
┌──────────────────────────────────────────────┐
│  [ícone DS 42px]  Dr. Diego Silva   Semana N de 12  │  ← banda verde
│  TRILHA DO CONSULTÓRIO LUCRATIVO                     │  ← dourado, caps, menor
├──────────────────────────────────────────────┤
│  Título da peça                                │
│  eixo (subtítulo)                              │
│  ...corpo...                                   │
```

- Banda: `background: linear-gradient(120deg, #0e211a, #1e5045)`.
- Ícone: o PNG isolado (504×504 fonte, renderizado a 42px de altura, proporção mantida).
- "Dr. Diego Silva": cor `#f4f1e7` (creme), mesma família do resto do produto.
- Selo "Semana N de 12": pílula `background:#f4f1e7; color:#14332a`, alinhado na mesma linha
  do ícone/nome (não mais solto no canto independente).
- "TRILHA DO CONSULTÓRIO LUCRATIVO": `color:#e7c766` (dourado), caixa alta, `letter-spacing`,
  linha abaixo da primeira.
- **Sem selo de tema.** Não criar campo novo pra isso.

### 3. Blocos "Sua tarefa" / "Mentalidade" — mais presença

```css
.bloco { border: 1px solid #e2dccc; border-left: 4px solid #c9a227; border-radius: 8px;
         padding: 22px 26px; margin: 26px 0 0; background: #fdfbf5; }
.bloco .rot { font-size: 11px; letter-spacing: .18em; font-weight: 700; margin: 0 0 10px; }
.bloco p { font-size: 15px; line-height: 1.6; }
```

Testado no PDF real (peça 1, que vaza pra página 2): os dois blocos maiores preenchem boa
parte da página 2 e o conjunto lê como fechamento, não como sobra. Ainda fica alguma margem
em branco no fim — aceito, não é o problema que motivou o item.

### 4. Tipografia — ajuste menor, mantido mesmo não resolvendo sozinho a página 2

```css
@page { size: A4; margin: 13mm 15mm; }        /* era 18mm 16mm */
body { line-height: 1.5; }                     /* era 1.55 */
.corpo p { margin: 0 0 9px; }                  /* era 12px */
li { margin: 0 0 4px; }                        /* era 6px */
```

**Tamanho da letra não muda em nenhum lugar.** Testei essa versão contra a peça 1 (a mais
longa entre as testadas) e ela continuou em 2 páginas — a tipografia mais justa ajuda peças
médias a caberem numa página só, mas não é o que resolve o caso das peças longas. Fica,
porque não piora nada e ajuda o caso comum; a página 2 é resolvida pelo item 3 acima, não
por aqui.

## Fora de escopo

- Levar a logo/ícone DS pra capa do PDF do estudo diário (`pdf.py`) — item 41, decisão maior,
  sem asset de produto pronto ainda.
- Criar um campo de categoria/tema por peça da trilha.
- Forçar toda peça a caber em 1 página (exigiria reduzir a letra, recusado pelo Diego).
- Editar o conteúdo das 12 peças (`seed/trilha/*.md`).

## Testes

- **Escape**: nenhum campo (nome, semana, título) pode ir pro HTML sem `_esc` — já é a
  disciplina do arquivo, só confirmar que a capa nova não introduz um caminho nu.
- **Rename**: `config.TRILHA_NOME` lido nos 4 lugares (capa, rodapé PDF, título do portal,
  legenda do WhatsApp) reflete o valor novo sem edição própria em cada um — teste que muda
  a env `DSCURSO_TRILHA_NOME` e confere os 4 pontos.
- **Ícone**: o asset embutido decodifica pra uma imagem válida, com transparência real
  (canal alfa não uniformemente 255) — pega regressão se alguém colar o base64 errado.
- **Render real**: pelo menos 1 teste que roda `pdf_trilha.montar_html` + `pdf.gerar_pdf`
  de ponta a ponta (Chromium) pra uma peça curta (ex. peça 12, 2.176 caracteres) e confirma
  saída de 1 página, e outro pra uma peça longa (peça 1) confirmando 2 páginas — trava a
  suposição que este spec faz sobre o comportamento das 12 peças reais.
