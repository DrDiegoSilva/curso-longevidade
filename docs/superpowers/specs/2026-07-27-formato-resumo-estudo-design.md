# Novo formato do resumo de estudo (🎯 direto + apreciação crítica) — Design

**Data:** 2026-07-27
**Status:** aprovado (brainstorming) → aguardando plano
**Branch:** feat/formato-resumo-estudo (base 8823a61)
**Backlog:** item 25

## Objetivo

Fazer a máquina de conteúdo gerar todo resumo de UM estudo no formato aprovado pelo Diego (mockup: https://claude.ai/code/artifact/11b9ff6b-f50e-4b4d-ade3-c987a520f426): **🎯 RESUMO DIRETO no topo** (TL;DR em linhas curtas com emoji) + **📋 RESUMO COMPLETO** (apreciação crítica: perguntas/domínios, desenho, quem entrou, doses, resultados, vieses/limitações, pontos fortes, conduta, conflito de interesse), leve e arejado.

### Decisões (brainstorming)

- **Onde:** nos dois caminhos de UM estudo (upload de PDF full-text + diário automático abstract), com **degradação graciosa** — o que a fonte não sustenta, o prompt omite (exceção: conflito ausente → "não declarado").
- **Seções clínicas:** **mesclar** efeitos adversos / conduta quando o estudo tiver; formato se adapta ao tipo (observacional × RCT × meta).

## Descobertas que moldam a implementação

- O formato vive num **system prompt**. `SYS_APROF` é usado em 3 lugares: `gerar_texto_do_artigo` (um estudo — máquina ativa via `daily.py`+`content.gerar_conteudo`), `curadoria.gerar_resumo` (um estudo), e `modo_atualizacao` (**digest de VÁRIOS estudos** numa mensagem só).
- Por isso: **criar `SYS_ESTUDO` novo** (formato aprovado) e apontar só os geradores de UM estudo (`gerar_texto_do_artigo` + `curadoria.gerar_resumo`) pra ele. **`SYS_APROF` (digest) fica intocado** (aplicar o formato profundo por estudo num digest de vários estouraria o tamanho).
- O wrapper `daily.montar_texto_resumo` **já adiciona** `🔬 *Título*` (+ selo de recência + badge do tema) antes do `resumo`. Então o `SYS_ESTUDO` **não repete o título** — começa na linha `📚 revista · mês/ano`.

## O novo prompt (`SYS_ESTUDO`) — texto exato

```python
SYS_ESTUDO = (
    "Você escreve o resumo de UM estudo científico para o Dr. Diego (médico), pra enviar no WhatsApp. "
    "O título do estudo JÁ é colocado antes do seu texto por outro trecho — NÃO repita o título; comece pela linha da revista. "
    "REGRAS DE OURO: nunca invente números/dados fora da fonte. Se uma seção não tiver base na fonte, OMITA-A "
    "(exceção — Conflito de interesse: se não houver menção, escreva 'não declarado'). "
    "Linguagem CLARA: frases curtas, uma ideia por frase; traduza cada sigla/estatística na 1ª vez em palavras simples "
    "(ex.: 'HR 0,67 — ~33% menos risco'). Adapte as seções ao TIPO de estudo (observacional, ensaio clínico, meta-análise): "
    "só inclua o que se aplica. WhatsApp: *negrito* com asteriscos (sem markdown), use emojis, LEVE E AREJADO — "
    "uma linha em branco entre as seções.\n\n"
    "ESTRUTURA (nesta ordem):\n"
    "1) `📚 <revista> · <mês/ano>` — linha de metadados (desenho e n podem entrar aqui ou em 'O estudo').\n"
    "2) `🎯 *RESUMO DIRETO*` LOGO NO TOPO — linhas curtas, uma por emoji: quem (n/população), achados-chave COM NÚMEROS, "
    "e 1 linha de ressalva do nível de evidência (ex.: ⚠️ observacional → 'associação, não causa'). É o TL;DR: quem ler só isso já entende.\n"
    "3) Linha `━━━━━━━━━━` e `📋 *RESUMO COMPLETO*`, com as seções abaixo (cada uma com emoji; OMITA as que não se aplicam):\n"
    "   🧪 *O estudo* — desenho + n + população + revista/DOI, em 1-2 frases.\n"
    "   ❓ *O que o estudo perguntou* — a(s) pergunta(s) de pesquisa; se houver, os domínios/desfechos medidos.\n"
    "   👥 *Quem entrou* — inclusão/exclusão relevantes.\n"
    "   💊 *Doses / intervenção* — só se for intervenção com doses.\n"
    "   📊 *Resultados* — os desfechos reais, COM números (um por linha quando forem vários).\n"
    "   ⚠️ *Efeitos adversos* — só se reportados, com números.\n"
    "   🧯 *Vieses e limitações* — honesto; pode inferir do desenho (ex.: 'retrospectivo, sem controle → não prova causa').\n"
    "   ✅ *Pontos fortes* — breve.\n"
    "   🧠 *O que muda na prática* — conduta, separando o consolidado do que é só deste estudo; só quando fizer sentido.\n"
    "   ⚠️ *Conflito de interesse* — quem declarou o quê; se ausente, 'não declarado'.\n"
    "Sem seção 'para paciente'. Honesto sobre hype/evidência fraca."
)
```

## Componentes / mudanças

1. `app/resumo_diario.py`: adicionar `SYS_ESTUDO` (acima de `gerar_texto_do_artigo`). Trocar em `gerar_texto_do_artigo` `system=SYS_APROF` → `system=SYS_ESTUDO`. Manter `max_tokens` (subir p/ 3600, o formato é mais longo).
2. `app/curadoria.py:182-189`: importar/usar `SYS_ESTUDO` no lugar de `SYS_APROF` no gerador de UM estudo.
3. **Não mexer:** `SYS_APROF` (digest `modo_atualizacao`), `gancho` (SYS_GANCHO — é outra coisa: ângulo do médico nas redes), gráfico, PDF, fila, aprovação 18h, envio, `montar_texto_resumo`.

## Guarda-corpos (no prompt)

- Nunca inventar número/dado fora da fonte.
- Seção sem base → omite; conflito ausente → "não declarado".
- Traduz sigla/estatística; adapta ao tipo de estudo; WhatsApp *negrito*, emojis, arejado.
- Não repete o título (o wrapper já põe).

## Testes

Formato = prompt (saída de IA não-determinística), então o teste automatizado é **estrutural**, em `app/tests/test_formato_estudo.py`:
- `SYS_ESTUDO` contém os marcadores/guarda-corpos exigidos: `"RESUMO DIRETO"`, `"RESUMO COMPLETO"`, `"O que o estudo perguntou"`, `"Vieses e limita"`, `"Pontos fortes"`, `"Conflito de interesse"`, `"não declarado"`, `"nunca invente"` (ou "não invente"), e a regra de NÃO repetir o título.
- `gerar_texto_do_artigo` usa `SYS_ESTUDO` (não `SYS_APROF`) — via monkeypatch de `claude` capturando o `system` recebido; e passa o texto do artigo no prompt.
- `curadoria` usa `SYS_ESTUDO` no gerador de um estudo (mesma técnica, se testável sem rede).
- **Regressão:** `SYS_APROF` continua existindo e sendo o system do `modo_atualizacao` (digest).

**Validação real (manual, não bloqueia merge):** rodar `gerar_texto_do_artigo` no texto do estudo TRT (o PDF do Diego) com a **chave da API Anthropic** e comparar com o mockup. Precisa da chave (rodar no ambiente que tiver, ou o Diego roda um comando pronto). Documentar no plano como smoke.

## Critérios de aceite

- [ ] `SYS_ESTUDO` existe e produz o formato aprovado (🎯 no topo + completo + vieses/pontos fortes/conflito), verificado ao vivo num estudo real.
- [ ] `gerar_texto_do_artigo` e `curadoria.gerar_resumo` usam `SYS_ESTUDO`; `modo_atualizacao` segue com `SYS_APROF`.
- [ ] Sem título duplicado (wrapper já põe).
- [ ] Testes estruturais passam; suíte inteira verde.

## Arquivos

- `app/resumo_diario.py` (novo `SYS_ESTUDO`, gerar_texto_do_artigo aponta pra ele).
- `app/curadoria.py` (usa `SYS_ESTUDO`).
- `app/tests/test_formato_estudo.py` (novo).
