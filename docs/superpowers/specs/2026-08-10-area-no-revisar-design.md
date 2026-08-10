# Item 36, fatia 1 — corrigir a ÁREA do estudo na tela do `/revisar`

**Data:** 2026-08-10
**Base:** `origin/main` = `d6f6c9d`
**Branch:** `feat/area-no-revisar`

## O problema

O estudo de 2026-08-10 foi subido à mão ANTES do deploy da detecção automática de área,
saiu com **"MEUS ESTUDOS"** na capa do PDF, e **não havia nenhum lugar no sistema pra
corrigir** — nem tela, nem botão. Nem pelo banco: as credenciais de produção só saem do
EasyPanel junto com todas as outras em texto puro.

Esta é a **fatia 1** de três (ver backlog item 36): cobre o caso "amanhã", que é o do dia
a dia daqui pra frente. As fatias 2 (retroativo, `digests`) e 3 (dias futuros, reserva)
ficam pra depois.

## Achado que dimensiona a tarefa

`daily.enviar_slot` (08h) monta o PDF **na hora do envio**, lendo `artigo["tema"]` do
rascunho:

```
draft.artigo.tema → daily._tema_meta() → tmeta ┬→ _pdf_master()          (capa do PDF)
                                               ├→ montar_texto_resumo()  (texto do WhatsApp)
                                               └→ db.registrar_digest()  (página do portal)
```

Corrigir a área no rascunho conserta os três de uma vez, desde que seja antes das 08h.
`_pdf_master` grava `{dia}-master.pdf` — arquivo diferente do `{dia}-preview.pdf` gerado
às 18h — então não há PDF cacheado atrapalhando o envio.

Origem do "MEUS ESTUDOS": `curadoria.adicionar_meu_estudo` cai em `"Meus estudos"` quando
a IA não acha a área, e `daily._tema_meta` devolve nome desconhecido como rótulo cru.

## Decisões do Diego (2026-08-10)

1. **O `<select>` de área salva junto com "Aprovar" e "Salvar edição"** — sem botão
   próprio. A tela já tem 5 botões; o fluxo real é escolher a área e aprovar num passo só.
2. **A correção grava também na reserva de origem.** Se o estudo for trocado (🔁) depois,
   ele volta ao estoque com a área já certa, em vez de a correção evaporar.

## Arquitetura

### Módulo novo: `app/area_estudo.py`

A correção de área como uma coisa só, com fronteira própria:

| Função | Responsabilidade |
|---|---|
| `areas()` | as chaves de área do `temas_config.json` |
| `valida(area, atual)` | **guarda**: devolve `area` só se estiver na lista; senão devolve `atual` |
| `aplicar_no_rascunho(r, area)` | escreve `r["artigo"]["tema"]`, invalida o preview, grava na reserva; devolve se mudou |

Módulo novo em vez de crescer `daily.py` (35 KB) porque a fatia 2 pede exatamente isto —
"um lugar que sabe escrever a área no lugar certo conforme a origem". A fatia 2 vira
`aplicar_no_digest`, a 3 `aplicar_na_reserva`, no mesmo arquivo.

### Mudanças em arquivos existentes

| Arquivo | Mudança |
|---|---|
| `review_web.pagina_revisao` | ganha `areas=()`; desenha `<select name="area">` acima do textarea |
| `draft_store.aplicar` | ganha `area=None`; em `aprovar`/`editar` delega ao `area_estudo` |
| `db.atualizar_reserva` | ganha o kwarg `tema=None` (a função já monta `sets` dinamicamente) |
| `serve.py` | GET passa as áreas à página; POST passa `g("area")` ao `aplicar` |
| `curadoria._areas_config` | vira `areas_config` (público) — agora tem dois donos |

## Dois detalhes que decidem se a feature parece funcionar

### 1. O preview PDF fica velho

`📄 Ver PDF` aponta pro `{dia}-preview.pdf` gerado às 18h com a capa errada. Sem tratar
isso, o Diego troca a área, clica em Ver PDF, vê "MEUS ESTUDOS" de novo e conclui que não
funcionou.

**Solução:** ao mudar a área, limpar `r["pdf_path"]`. O `serve.py` já regenera sob demanda
quando o arquivo não existe (`serve.py:281-297`), e esse caminho já lê
`daily._tema_meta(art["tema"])`. Zero código novo de PDF.

### 2. Área fora da lista tem que aparecer no `<select>`

Se o tema atual for `"Meus estudos"` ou vazio, ele entra como **primeira opção, marcada**.
Sem isso, abrir a tela e apertar Aprovar sem tocar em nada trocaria a área silenciosamente
pro primeiro item da lista.

## Guarda de entrada

`/revisar/<token>` é rota pública, protegida só pelo token. Um POST forjado não pode
carimbar área arbitrária na capa do PDF do assinante. `valida()` só aceita chave que está
no `temas_config.json`; qualquer outra coisa é no-op e mantém a área atual — mesmo espírito
da guarda do `triage.extrair_metadados`.

Campo ausente ou vazio também é no-op, o que mantém compatibilidade com os POSTs que não
mandam área (`nao_enviar`, `regerar_audio`, `trocar`).

## Testes

Escritos antes do código, cada um falhando primeiro:

- área da lista → grava no rascunho **e** na reserva
- área fora da lista → ignorada, tema atual intacto (a guarda)
- área vazia / campo ausente → no-op
- mudar a área **limpa o `pdf_path`**; não mudar **preserva**
- `<select>` traz as áreas com a atual marcada; tema fora da lista aparece como opção extra
- integração: mudar a área do rascunho muda o `tmeta` que o `_montar_ctx` entrega ao envio
- rascunho sem `reserva_id` (veio de candidato/clássico) não explode

Correções mortas por mutação antes de fechar — suíte verde não é evidência.

## Ajustes vindos da revisão de código

Três achados, todos consequência direta do desenho acima:

1. **`/pdf` passou a gravar o caminho regenerado.** Zerar o `pdf_path` invalida o preview
   velho, mas sem gravar o novo o rascunho fica "sempre inválido" e cada clique em
   "Ver PDF" paga um Chromium (até 3 × 120 s). Era raro antes; a correção de área tornaria
   isso o estado normal de todo rascunho corrigido.
2. **Estudo já enviado avisa em vez de dizer "Feito ✅".** Depois do 1º slot a área não
   chega no PDF (`_pdf_master` cacheia `{hoje}-master.pdf`) e o `digests` do portal já foi
   escrito — só o badge do WhatsApp mudaria, e o estudo sairia inconsistente. O aviso só
   aparece quando uma área NOVA foi pedida de fato, e `nao_enviar` continua valendo (é o
   freio de emergência dos slots seguintes, que só respeitam `SKIPPED`).
3. **`areas()` falha fechada.** Aprovar/editar agora lê o `temas_config.json` em toda
   chamada; config ilegível devolve lista vazia em vez de derrubar a aprovação.

O teste da guarda #2 pegou um bug de ordem: `draft_store.aplicar` sobrescrevia o status
antes de chamar a guarda, apagando o `SENT` que ela procura. A área passou a ser aplicada
antes do status.

## Fora de escopo

- Fatia 2: escrita retroativa no `digests` + entrada pela agenda (conserta 2026-08-10)
- Fatia 3: dias futuros pela agenda (reserva)
- Regerar o áudio quando a área muda (o áudio não fala a área)
