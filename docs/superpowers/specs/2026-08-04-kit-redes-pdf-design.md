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

3. **Como falar** (NÃO recortável, de propósito)
   - O porquê o tema importa
   - **3 dicas de Instagram**, rotuladas (não numeradas — não são passos de uma sequência):
     - **Formato** — como montar o post e qual peça vai em cada tela
     - **Abertura** — a primeira frase, pensada pros 3 primeiros segundos
     - **Cuidado** — a armadilha específica DESTE tema (ex.: comparar com bariátrica sem contexto)
   - Corpo menor e tratamento visual distinto dos dois de cima — tem que ficar óbvio que é
     briefing pro médico, não peça de post. Se parecer com os outros, alguém recorta junto.

   ⚠️ **As 3 dicas têm que ser específicas do estudo do dia.** Dica genérica de rede social
   ("poste às 19h", "use hashtags") o médico aprende a pular em uma semana, e aí o bloco inteiro
   vira ruído — inclusive o "Por que importa", que é útil. O prompt precisa exigir especificidade
   e proibir conselho que serviria para qualquer edição.

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
    "porque_importa": "…1 parágrafo curto…",
    "dicas": [
      {"rotulo": "Formato",  "texto": "…"},
      {"rotulo": "Abertura", "texto": "…"},
      {"rotulo": "Cuidado",  "texto": "…"}
    ]
  }
  ```

  - **Compatibilidade:** valor antigo que não parseia como JSON é tratado como `porque_importa`, e
    renderiza como hoje. A reserva, os clássicos e os digests antigos continuam funcionando.
  - **Degradação parcial:** faltando `dicas`, some só a lista; faltando `frase`, some só o bloco 2.
    Nenhum campo ausente pode levantar exceção nem imprimir "None" na página.
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

- `gancho` JSON novo → renderiza os três blocos e as 3 dicas com seus rótulos.
- `gancho` texto puro (formato antigo) → renderiza só o "porque importa", sem quebrar.
- `gancho` JSON inválido ou parcial (sem `dicas`, sem `frase`, `dicas` vazia, `dicas` com mais de
  3 itens) → degrada sem levantar e sem imprimir `None`.
- Bloco "como falar" tem classe/visual distinto dos recortáveis.
- Link do rodapé sai como `<a href>` com a URL do estudo.
- Legenda do WhatsApp leva a URL **e** o nome do arquivo continua derivado só do título.
- Site e PDF renderizam o mesmo kit a partir dos mesmos dados.
