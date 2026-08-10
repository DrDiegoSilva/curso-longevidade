# Item 33 — a base emite uma OPINIÃO no fim do estudo do dia

**Data:** 2026-08-10
**Origem:** debate com o Diego nesta sessão. Palavras dele: *"eu quero que tenha base de
dados pra emitir uma opinião no final com base em todo o conhecimento que temos dos
assuntos"* e *"aparecer pra mim na aprovação, eu leio sobre e se fizer sentido dou ok, se
não eu ajusto, e aquela opinião vai para o assinante também, e aí ficaria legal essa
opinião no áudio"*.

Funde os itens 30 (dossiê por tema) e 31 (áudio como análise de colega sênior) do backlog.

## O problema

O assinante recebe **um estudo bem resumido** — o que qualquer newsletter de papers faz.
Falta o que só o Diego tem: o estudo **situado dentro de tudo que já foi acompanhado
naquele tema**. Esse conhecimento existe, está no banco, e nunca é lido de volta.

## O corpus (verificado no código, 2026-08-10)

| Fonte | O que tem | Cresce |
|---|---|---|
| `curadoria_candidatos` | `abstract` **inteiro**, tema, tags da triagem, score | ~43/semana ignorados |
| `digests` | resumo em PT dos estudos **já enviados** (aprovados pelo Diego) | 1/dia |
| `classicos` | estudos-marco por citações, resumo em PT | por varredura manual |

**Não há `DELETE` em nenhuma das três.** Os 5 DELETEs do `db.py` são de outras tabelas
(`webhook_events`, `automacoes_renovacao`, `avisos_renovacao`, `serie_itens`,
`reserva_resumos`).

⚠️ **O corpus é MAGRO hoje, não "de meses".** O cron da varredura semanal entrou em
`7a4364d`, **2026-07-25** — 2 a 3 domingos, ~100-150 estudos, **~25-30 por tema**.
**O gargalo não é a janela de busca** (`rodar_varredura` já busca desde `2026-01-01`)
**e sim os CAPS por rodada**: Obesidade 20, Hormonal 9, Performance 8, Longevidade 7,
Lipedema 6.

## O achado que derruba a parte cara

A anotação antiga previa banco vetorial ou full-text search do Postgres, tropeçando na
restrição de o container ser **stdlib puro, sem pip**.

**Não precisa de nada disso.** ~30 abstracts × ~400 tokens ≈ **12 mil tokens** — cabe
folgado numa chamada. Manda-se **o corpus inteiro do tema** e o modelo acha as ligações.

A recuperação só vira problema quando o corpus multiplicar por 5-7. Até lá, a decisão
certa é não construí-la. Quando chegar a hora, as tags da triagem (`retatrutida`,
`glp1`, `massa magra`) já estão no banco e viram o filtro natural.

## Decisões do debate

1. **A opinião aparece na aprovação das 18h, editável.** Segunda caixa de texto ao lado
   do resumo. O que o Diego aprovar é o que sai — mesmo contrato do resumo hoje.
2. **Depois de aprovada, vai pro assinante**: bloco no fim do PDF, página do portal, e
   narrada no fim do áudio.
3. **Discordância: aponta o conflito e NÃO resolve.** *"Tensiona com JAMA jun/26; a
   literatura ainda não converge."* Duas razões: é o que um colega sênior faz quando a
   literatura não fechou, e é o único formato em que o erro não custa caro. Quem toma
   partido é o Diego, reescrevendo na caixa — aí vira palavra dele, não da IA.
4. **Fonte do corpus: a ÁREA inteira**, não as tags. Com 30 por tema, visão ampla gera
   mais conexão que filtro estreito. Tag entra quando a base crescer.

## Arquitetura

### Módulo novo: `app/opiniao.py`

| Função | Responsabilidade |
|---|---|
| `corpus_do_tema(tema, excluir_doi=None)` | junta candidatos + digests + clássicos do tema num formato só |
| `montar_prompt(estudo, corpus)` | o material + as regras de ancoragem |
| `gerar(estudo, corpus, llm=None)` | devolve `{"texto": str, "citados": [...], "ancorado": bool}`; **nunca levanta** |
| `ancorada(citados, corpus)` | **a guarda** — toda citação tem que existir no corpus |

`llm` injetável, como `triage.triar` e `curadoria.gerar_resumo` — testável sem rede.

### A guarda de ancoragem (o coração)

O risco real **não** é a IA errar um dado: é escrever bonito sem olhar os estudos, e o
Diego aprovar porque soou bem. Isso não é memória — é um modelo opinando com passos extras.

O modelo responde **JSON**, no padrão que o `triage.extrair_metadados` já usa:

```json
{"opiniao": "...", "citados": [{"titulo": "...", "fonte": "...", "data": "2026-03"}]}
```

`ancorada()` confere que **cada** item de `citados` casa com um estudo do corpus que foi
enviado no prompt. Citação que não casa é referência inventada → descartada. Se sobrar
nenhuma âncora, a opinião é substituída por *"A base ainda é fina sobre este assunto —
{n} estudos no tema."* Falha fechada, e de quebra ensina ao Diego que o tema precisa de
mais varredura.

### Onde a opinião mora

- **Rascunho**: `r["opiniao"]` — o payload do `daily_drafts` é JSON, **sem migração**.
- **Portal**: coluna nova `opiniao TEXT` em `digests`, via o `_add_coluna`/`_migrar_colunas`
  que já existe (idempotente, cobre pg e sqlite).

### Mudanças em arquivos existentes

| Arquivo | Mudança |
|---|---|
| `daily._preparar_*` | gera a opinião ao montar o rascunho; falha → rascunho sem opinião (nunca derruba o preparo) |
| `review_web.pagina_revisao` | 2ª `<textarea name="opiniao">` |
| `draft_store.aplicar` | grava `opiniao` junto com `texto` em aprovar/editar |
| `pdf.montar_html` | bloco "OPINIÃO" no fim, depois do kit |
| `audio.gerar_roteiro` | acrescenta a opinião ao `material` (cai no fim da narração) |
| `db.registrar_digest` | persiste `opiniao` |
| `site_web` (portal) | renderiza o bloco na página do estudo |

## Riscos e travas

**Teto silencioso do áudio.** `audio.narrar` corta a entrada em **4000 caracteres**
(`audio.py:48`). Hoje o roteiro cabe; com a opinião pode passar — e o corte é mudo,
justamente a opinião (que fica no fim) é o que desaparece. Precisa de guarda explícita e
teste: se o roteiro + opinião passar do teto, encurtar a opinião **antes** de narrar, não
deixar o corte cego decidir.

**Não está confirmado que o áudio está ligado em produção.** Depende de `OPENAI_API_KEY`
e de `DSCURSO_AUDIO != "0"` (`config.py:218-220`), e o item 1 do backlog
("re-checagem de áudio TTS") está aberto desde julho. Por isso o áudio é a **fatia 3**.

**Autoria e CFM.** Opinião clínica publicada sai com o CRM do Diego, pra médicos que podem
mudar conduta. Mitigação: nada é publicado sem ele aprovar às 18h (o gate já existe), a
decisão 3 evita tomar partido, e a ancoragem obrigatória impede afirmação sem lastro.

**Custo.** Uma chamada Sonnet a mais por dia, com ~12k tokens de entrada. Desprezível
frente ao que o preparo já gasta.

## Fatias

1. **Encorpar o corpus** — subir os caps e rodar a varredura algumas vezes com janelas
   históricas. **Pré-requisito**: com 25 abstracts de Lipedema a opinião nasce pobre e o
   Diego julga a ideia errada por causa do material, não do desenho.
2. **Núcleo** — `opiniao.py` + geração no preparo + caixa no `/revisar` + bloco no PDF +
   portal. É onde vive a guarda de ancoragem.
3. **Áudio** — depois de confirmar que o áudio está no ar.

## Testes

- corpus junta as 3 fontes, filtra por tema, exclui o próprio estudo (pelo DOI)
- corpus vazio / tema seco → opinião degrada pra "base fina", não inventa
- **citação que não existe no corpus é descartada** (a guarda) — e se sobrar nenhuma, degrada
- JSON malformado / IA fora do ar → rascunho sem opinião, **preparo não cai**
- opinião editada no `/revisar` é a que chega no PDF, no portal e no áudio
- roteiro + opinião acima de 4000 chars → encurta a opinião em vez de sofrer corte cego
- `digests` de banco antigo recebe a coluna `opiniao` (migração idempotente)
- estudo sem tema (`""`) não explode

Correções mortas por mutação antes de fechar — e atenção às duas armadilhas de
[[mutacao-pyc-e-restauro]] (restauro com arquivo untracked; `.pyc` velho em mutação que
não muda o tamanho).

## Fora de escopo

- **Dossiê por tema** (item 30 puro): uma página viva por assunto. A opinião diária vem
  primeiro porque melhora o que o assinante já paga; o dossiê é produto novo.
- **Texto completo** (Europe PMC `fullTextXML`, Unpaywall). Pra sintetizar um assunto, 200
  abstracts valem mais que 20 textos completos — e o Diego já faz o mergulho num estudo
  subindo o PDF na curadoria. Vira incremento, não pré-requisito.
- **Busca semântica / banco vetorial.** Ver o achado acima: desnecessário nesta escala.
- **Busca interna** ("o que já vimos sobre creatina?"). Cai fora por ora; a opinião diária
  entrega o mesmo valor sem tela nova.
