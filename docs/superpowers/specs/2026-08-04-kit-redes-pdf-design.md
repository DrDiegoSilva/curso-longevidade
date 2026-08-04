# Kit para suas redes — rodapé do PDF diário

**Data:** 2026-08-04 · **Autor:** Diego + Claude · **Status:** aprovado, aguardando plano

## Problema

O rodapé do PDF tem hoje um card único (`📣 Para suas redes`) com **um parágrafo em itálico**: uma
*dica* de como o médico poderia abordar o tema. O prompt que o gera (`SYS_GANCHO`, `content.py:8`)
pede explicitamente "NÃO é um post pronto".

O médico assinante, na prática, faz outra coisa: **tira print do paper** (header com título e
revista), às vezes print de um gráfico, e escreve o texto por conta. Ou seja, o card atual não
entrega a peça que ele realmente usa, e o trabalho de recortar continua com ele.

## Objetivo

Transformar o rodapé num **kit de post pronto**: as peças que o médico já recorta hoje, só que
limpas e prontas pra print, mais a fala já escrita.

Critério de sucesso: o médico consegue postar sem abrir o paper e sem escrever nada — recorta dois
retângulos do PDF e usa o texto que está ali.

## Decisões do Diego (2026-08-04)

| decisão | escolha |
|---|---|
| Fonte no recorte | Cartão do estudo com **título original em INGLÊS** + revista · ano · DOI, com cara de recorte de paper |
| Marca (Atualização Científica / Dr. Diego) | **Não entra** nos blocos recortáveis — o card é do assinante |
| Tom da frase | **Achado em linguagem de paciente** ("o ponto do estudo", traduzido) |
| Link pro paper | **Sim** — clicável no PDF e na mensagem do WhatsApp |
| Gráfico duplicado no kit | **Não** — já existe em cartão próprio acima e já é recortável |

## Desenho

### Os três blocos

1. **Cartão do estudo** (recortável)
   - Título **original em inglês** + linha `revista · ano · DOI`
   - Visual de header de paper; respiro generoso nas bordas pra um recorte torto ainda ficar bom
   - Sem marca do Diego

2. **A frase** (recortável)
   - O achado em linguagem de paciente, corpo grande, legível sozinha
   - Sem marca do Diego

3. **Reels que saem deste estudo** (NÃO recortável, de propósito)
   - **De 1 a 3 assuntos de vídeo** tirados do estudo. Cada item: um ângulo curto (o que o médico
     fala) + uma linha do dado que sustenta aquele ângulo.
   - O Diego produz **só Reels** — não é conselho de formato, diagramação ou horário de post.
     São PAUTAS.
   - Corpo menor e tratamento visual distinto dos dois de cima — tem que ficar óbvio que é
     briefing pro médico, não peça de post. Se parecer com os outros, alguém recorta junto.
   - O título do bloco NÃO leva número fixo ("Reels que saem deste estudo"), porque a quantidade
     varia.

   ⚠️ **Nunca completar cota.** Se o estudo só rende um assunto bom, vem **um**. Modelo de IA
   preenche a lista até o número pedido quando você pede "3", e o terceiro sai inventado ou
   redundante — o médico percebe e para de ler o bloco inteiro. O prompt tem que dizer
   explicitamente: de 1 a 3, prefira menos, e **nunca** invente pra fechar número.

   ⚠️ **Ângulos de partes DIFERENTES do estudo** (ex.: braço comparador, duração, desenho do
   protocolo) — não três formas de dizer o mesmo achado, senão viram um Reels só repetido.

O **gráfico** continua onde está. Recebe o mesmo tratamento de borda/respiro dos outros dois
recortáveis, pra que os três cortem bem.

### Link pro paper

- **PDF:** o `Referência: <url>` do rodapé (`pdf.py:324`) vira `<a href>` de verdade. Chromium com
  `--print-to-pdf` (`pdf.py:345`) preserva hyperlink como anotação — o link fica clicável.
- **WhatsApp:** a legenda do envio diário passa a levar a URL do estudo.

⚠️ **Armadilha:** `deliver.py:48` deriva o **nome do arquivo** do caption
(`re.sub(r"[^\w-]", "_", caption)[:40] + ".pdf"`). Jogar a URL na legenda faria o PDF chegar como
`Tirzepatida_e_perda_de_peso_https_do.pdf`. O envio precisa **separar legenda de nome de arquivo**
antes de mexer na legenda.

### Dados

- **`gancho` vira JSON** — mesmo padrão que o `grafico` já usa nessas mesmas tabelas (coluna TEXT
  com JSON dentro):

  ```json
  {
    "frase": "…o achado em linguagem de paciente…",
    "reels": [
      {"angulo": "Não é falta de força de vontade.",
       "apoio": "O grupo sem tratamento fez a mesma dieta e perdeu 3,1%."}
    ]
  }
  ```

  `reels` tem de **1 a 3** itens — a lista é curta de propósito (ver a trava de cota acima).

  - **Compatibilidade:** valor antigo que não parseia como JSON vira um único item de `reels` com
    o texto no `angulo`, e renderiza no lugar do bloco 3. A reserva, os clássicos e os digests
    antigos continuam funcionando.
  - **Degradação parcial:** faltando `reels`, some só o bloco 3; faltando `frase`, some só o
    bloco 2. Item sem `apoio` renderiza só o ângulo. Nenhum campo ausente pode levantar exceção
    nem imprimir "None" na página.
  - **Corte defensivo:** se vierem mais de 3 itens, renderiza os 3 primeiros — a IA vai extrapolar
    alguma hora e isso não pode virar um bloco gigante no PDF do assinante.
- **Título original em inglês precisa ser guardado.** Hoje `digests` só tem `titulo_pt`
  (`db.py:1557`), então o site (`site_web.pagina_digest`) não tem como mostrar o cartão do estudo
  igual ao PDF. O título original tem que ser **carregado de ponta a ponta**: nasce no candidato
  da curadoria e precisa sobreviver até o `digests`, que é o que o site lê. Coluna nova
  `titulo_original` em `curadoria_candidatos`, `reserva_resumos`, `classicos` e `digests` — gravar
  só no `digests` não resolve, porque o digest é montado a partir dos outros.
- **`SYS_GANCHO` reescrito** (`content.py:8`) pra emitir os dois campos. As travas do CFM ficam
  **inalteradas e inegociáveis**: sem promessa de cura/milagre, sem garantia de resultado, sem
  promover medicamento de receita para leigo (falar do CONCEITO), sem sensacionalismo.

### Superfícies afetadas

- `pdf.py` — `_gancho_html` vira o kit; muda de assinatura (passa a precisar dos dados do estudo).
- `site_web.py:1878` — segundo call site do mesmo bloco; tem que acompanhar.
- `content.py` — prompt e parse.
- `db.py` — migração da coluna de título original.
- `daily.py` / `deliver.py` — legenda + nome de arquivo do envio.

## Fora de escopo

- Duplicar o gráfico dentro do kit.
- Gerar imagem pronta (PNG) do card — o recorte segue sendo print do médico.
- Regerar retroativamente o banco de reserva/clássicos.

## Expectativas explícitas

1. **Conteúdo já gerado mantém o formato antigo** até ser regerado. O kit completo só aparece em
   estudos novos. (Mesmo efeito já visto quando os campos novos do gráfico entraram.)
2. **O cartão do estudo em inglês só aparece no site depois da migração** — antes disso, PDF e site
   divergem nesse bloco.

## Testes

- `gancho` JSON novo → renderiza os três blocos, com todos os itens de `reels`.
- **`reels` com 1 item renderiza igual bem** que com 3 — sem "2." e "3." vazios, sem espaço órfão.
- `gancho` texto puro (formato antigo) → vira um item só, sem quebrar.
- `gancho` JSON inválido ou parcial (sem `reels`, sem `frase`, `reels` vazia, item sem `apoio`)
  → degrada sem levantar e sem imprimir `None`.
- `reels` com 5 itens → renderiza 3.
- Bloco "como falar" tem classe/visual distinto dos recortáveis.
- Link do rodapé sai como `<a href>` com a URL do estudo.
- Legenda do WhatsApp leva a URL **e** o nome do arquivo continua derivado só do título.
- Site e PDF renderizam o mesmo kit a partir dos mesmos dados.
