# Cartão do estudo com cara de paper — bloco printável sem marca — design

**Data:** 2026-08-21
**Status:** spec aprovada no brainstorm, aguardando plano de implementação

## O problema

Item 42 do backlog, ideia do Diego: *"temos que criar no PDF um pedaço que seja printável... o
header do estudo real e aí logo abaixo os achados que são significativos do estudo que
trouxeram, mas lembrando esse achado tem que ser coisa boa para poder postar nas redes."* A
restrição que dá o motivo de existir: *"não pode ter nossa logo — acho que isso pode bloquear
as pessoas de postarem."*

**Descoberta no brainstorm: isso já existe.** O rodapé do PDF (`app/pdf.py::_kit_html`) já tem,
desde 2026-08-04, um "1 · O estudo" (revista/título original/DOI, sem marca) e um "2 · A frase"
(o achado em destaque, sem marca) — pensados desde então para "PRINT RECORTADO". O problema real
não é a existência do bloco, é que ele **não tem cara de paper de verdade**: hoje é uma caixa
genérica com uma borda colorida em cima, igual a qualquer outro card do kit.

## O que muda (e o que NÃO muda)

- **Muda:** o estilo visual do cartão "1 · O estudo" — de "card com borda colorida" para
  "masthead de periódico acadêmico" (nome da revista centralizado em itálico, régua fina,
  título centralizado, data+DOI no rodapé).
- **Muda:** os rótulos `1 · O ESTUDO` e `2 · A FRASE` **saem** — são numeração do kit inteiro
  (que tem 4 partes), e apareceriam no print de quem capturar só essas duas.
- **Muda:** o espaço entre o cartão do estudo e o quadro da frase aumenta um pouco, para dar
  "espaço de corte" entre os dois, já que continuam sendo 2 imagens separadas.
- **NÃO muda:** o quadro da frase (`.frase-box`) mantém o estilo de hoje (destaque dourado) —
  só ganha mais espaço acima.
- **NÃO muda:** os blocos 3 (Reels) e 4 (limites do CFM) — continuam numerados, não são para
  print.
- **NÃO muda:** ausência de marca nos dois blocos — decisão de 2026-08-04, reafirmada aqui.
- **NÃO muda:** posição no PDF (continua depois de "Como explicar pro paciente", antes dos
  Reels) nem o mecanismo de aprovação (edição/exclusão do campo `frase` na tela das 18h — se
  apagar, o bloco some, igual hoje).

## Por que não replicar o visual real de cada revista

Considerado e descartado no brainstorm: reproduzir a identidade visual real de cada revista
(cores/logo da NEJM, JAMA, Nature etc.) exigiria (a) catalogar manualmente o design de dezenas
de revistas de origem diferente, com o sistema hoje só guardando metadado de texto (nome, data,
DOI) e nenhum asset visual da publicação; (b) ainda assim cairia num padrão genérico para
qualquer revista nova nunca vista; (c) risco de marca registrada ao reproduzir a identidade
visual de uma publicação que não é nossa. Optou-se por um masthead **genérico**, com convenções
tipográficas universais de citação acadêmica (nome da revista em itálico, título centralizado,
DOI monoespaçado) — não imita nenhuma revista específica, mas fica consistente para qualquer uma.

## HTML e CSS

### Antes

```html
<div class="kit-paper"><div class="kit-rot">1 &middot; O estudo</div>
  <div class="paper-box">
    <div class="paper-rev">{revista}</div>
    <p class="paper-tit">{titulo}</p>
    <div class="paper-doi">DOI {doi}</div>
  </div>
</div>
<div class="kit-frase"><div class="kit-rot">2 &middot; A frase</div>
  <div class="frase-box"><p>{frase}</p></div>
</div>
```

### Depois

```html
<div class="kit-paper">
  <div class="paper-box">
    <p class="paper-rev">{revista}</p>            <!-- só o nome da fonte; omitido se vazio -->
    <hr class="paper-rule">                        <!-- só se paper-rev existir -->
    <p class="paper-tit">{titulo}</p>
    <p class="paper-doi">{data-e-doi}</p>          <!-- "{data} · DOI {doi}", só com o que existir -->
  </div>
</div>
<div class="kit-frase">
  <div class="frase-box"><p>{frase}</p></div>
</div>
```

Repare que o agrupamento dos metadados muda: hoje `revista` já combina fonte+data e o DOI fica
sozinho embaixo; no masthead, o topo mostra **só o nome da fonte** (convenção de cabeçalho de
periódico) e o rodapé combina **data + DOI** (convenção de linha de citação). Reaproveita a
lógica de "só com o que existir" que `_meta_linha` já usa para o cabeçalho principal do PDF —
mesma função pode ser extraída/reaproveitada em vez de duplicar a regra.

### Casos sem dado (upload manual sem fonte/data/DOI)

Mesma guarda que já existe hoje, adaptada:

| Falta | Comportamento |
|---|---|
| `revista` (fonte) vazia | `.paper-rev` e `.paper-rule` não renderizam; título vira o primeiro elemento do cartão |
| `data` e `doi` vazios | `.paper-doi` não renderiza (hoje já é assim para o DOI sozinho) |
| `titulo` vazio (nem original nem PT) | o `kit-paper` inteiro não renderiza — guarda já existente, não muda |

### CSS (`app/pdf.py`, dentro do bloco `_CSS`/f-string do template)

```css
.paper-box { border-top:2.5px solid #14332a; border-bottom:1px solid #14332a; background:#fcfdfc;
             padding:16px 20px 18px; break-inside:avoid; }
.paper-rev { text-align:center; font-style:italic; font-size:14px; letter-spacing:.02em;
             color:#14332a; margin:0 0 10px; }
.paper-rule { border:none; border-top:1px solid #c7cec8; margin:0 0 12px; }
.paper-tit { text-align:center; margin:0 0 10px; font-size:17.5px; line-height:1.32; color:#16211c; }
.paper-doi { text-align:center; font-family:ui-monospace,Menlo,monospace; font-size:11.5px;
             color:#6f7d78; }
.kit-frase { margin-top:8px; }   /* soma ao gap:15px do flex .kit -> ~23px de respiro de corte */
```

**`#14332a` é fixo, não o `{cor}` do tema do dia.** O `.paper-box` de hoje já usa essa cor verde
fixa independente do tema (Obesidade/Hormonal/Performance/etc. — ver `temas_config.json`), e
esta spec preserva essa decisão existente: o masthead não muda de cor por tema, para não
introduzir uma variação visual nova e não aprovada nos mockups. Os outros elementos do PDF
(gráfico, capa, braços) continuam themed por `{cor}` normalmente — só o masthead do paper fica
fixo, como já era.

## Onde mexe

| Arquivo | O quê |
|---|---|
| `app/pdf.py` | `_kit_html` (monta o HTML sem os `kit-rot` dos blocos 1/2, reagrupa data+doi) e o CSS (`.paper-box`, `.paper-rev`, `.paper-tit`, `.paper-doi` restilizados, `.paper-rule` novo, `.kit-frase` com margin extra) |
| `app/site_web.py` | cópia própria do CSS do kit (perto de `.chart`, ~linha 270) — **tem que replicar as mesmas classes**, senão o cartão sai sem estilo no portal. Há teste (`test_site_tem_o_css_do_kit`) que trava as classes existentes; estender pra cobrir `.paper-rule`. |

`app/content.py` (parse do gancho/JSON), `app/daily.py` e o resumo clínico (`SYS_ESTUDO`) não
são tocados — isto é só apresentação de dados que já existem.

## Testes

- `kit-paper` e `kit-frase` **não têm mais** `<div class="kit-rot">` dentro — string `1 &middot;
  O estudo` / `2 &middot; A frase` não aparece mais no HTML.
- `kit-brief` (Reels) e `kit-limites` (CFM) **continuam** com `kit-rot` — não regredir os blocos
  que não mudam.
- Sem `revista`: HTML não contém `<p class="paper-rev">` nem `<hr class="paper-rule">`; título
  aparece normalmente.
- Sem `data` e sem `doi`: `<p class="paper-doi">` não aparece (elemento vazio removido, mesma
  regra do `.meta:empty` que já existe no cabeçalho principal).
- Com `data` e sem `doi` (e vice-versa): `.paper-doi` mostra só o que existe, sem `· ` órfão —
  mesmo padrão de `_meta_linha`.
- Escape: `<script>` em `revista`/`titulo`/`doi` sai escapado (já coberto por teste existente,
  conferir que sobrevive à refatoração).
- `test_site_tem_o_css_do_kit` estendido: `.paper-rule{` também precisa existir em `site_web.py`.
- Uma peça real ponta a ponta (fixture com revista+data+doi+titulo+frase preenchidos): o HTML
  gerado não contém nenhum `kit-rot` antes do `paper-box` nem do `frase-box`.

## Fora de escopo

- Réplica visual de revistas específicas (ver seção acima — descartado por inviabilidade e
  risco de marca).
- Qualquer UI nova de aprovação/gating — reusa a edição do campo `frase` na tela das 18h.
- Mudar a posição do bloco no PDF.
- Mexer nos blocos 3 (Reels) e 4 (limites do CFM) além de preservá-los como estão.
- Fundir o cartão do estudo e o quadro da frase numa caixa só — decisão explícita do Diego foi
  manter como 2 imagens separadas, com mais respiro entre elas.
