# Alerta de gasto abusivo de IA — design

**Data:** 2026-08-27
**Status:** spec aprovada no brainstorm, aguardando plano de implementação

## O problema

Nasceu de um incidente: durante um deploy, uma chamada rotineira ao EasyPanel
(`inspectService`) vazou as credenciais de produção em texto puro — inclusive
`OPENAI_API_KEY` e `DSCURSO_ANTHROPIC_KEY`, chaves com custo por uso. O bloqueio técnico do
vazamento em si já foi resolvido à parte (hook em `.claude/settings.json`). Diego pediu uma
segunda camada: um alerta que avise por WhatsApp se o gasto de IA de um dia sair da curva —
não porque isso pega uso indevido de uma chave vazada usada FORA do sistema (o ledger só
enxerga o que passa pelo nosso próprio código), mas porque cobre a classe de problema que o
ledger consegue ver: bug em loop, uso indevido de dentro do próprio app, reconstrução do
corpus disparada sem querer, etc. Diego já entendeu e aceitou essa distinção.

## O que já existe (reaproveitado, nada novo)

- `ia_custo.registrar(acao, modelo, unidades_in, unidades_out, chamadas)` — único ponto de
  entrada do ledger (`db.registrar_ia_uso`), chamado por `resumo_diario.claude()` e
  `audio.narrar()`. Nunca levanta exceção.
- `db.resumo_ia_uso(desde, ate=None)` — agregado por dia, já pronto pra somar "gasto de
  hoje".
- `db.get_config(chave, default="")` / `db.set_config(chave, valor)` — key-value genérico
  (tabela `settings`) já usado para outras flags do sistema. **Reaproveitado para marcar "já
  avisei hoje"** — nada de arquivo em `/data` (é efêmero, apagado a cada deploy/restart,
  mesma razão pela qual `daily_drafts` deixou de usar `/data/drafts`) nem tabela nova.
- `deliver.enviar_admin(msg)` — manda só pro(s) admin(s) (Dr. Diego), sem notificar os
  curadores convidados. Já é o padrão usado para outros alertas operacionais (ex.: estoque
  de estudos baixo).
- `config.PRECOS_IA` / `config.USD_BRL` — convenção de constante de preço com override por
  env, sem precisar de deploy pra corrigir.

## O que muda

- **Novo:** `config.LIMIAR_CUSTO_DIA_BRL` — teto diário em R$, **20.0** por padrão,
  overridável por `DSCURSO_LIMIAR_CUSTO_DIA` (mesma convenção de `DSCURSO_USD_BRL`).
- **`ia_custo.registrar`** passa a chamar uma checagem depois de gravar com sucesso: soma o
  gasto de **hoje** (`db.resumo_ia_uso` com `desde` = data de hoje), converte pra BRL, e se
  passar do teto **e ainda não tiver avisado hoje**, manda WhatsApp pro Diego
  (`deliver.enviar_admin`) e marca o dia como avisado (`db.set_config`).
- **Dispara só uma vez por dia** — não é "toda gravação depois de passar do teto": um único
  job de conteúdo pode gerar dezenas de chamadas de IA em minutos, e isso viraria spam de
  WhatsApp.
- **Nunca derruba a geração** — mesmo espírito do resto do ledger ("perder uma linha de
  custo é aceitável, perder o estudo do dia não é"). Qualquer exceção na checagem (banco
  fora do ar, `enviar_admin` falhando) é capturada e só loga.
- Mensagem inclui o valor gasto, o teto, e um link direto pra `/admin/custos?token=...` (com
  o token de admin já embutido, mesmo padrão de outros links administrativos enviados por
  WhatsApp neste sistema).

## Fora de escopo

- Qualquer coisa que dependa de enxergar uso da chave FORA do nosso app (isso é proteção de
  provedor — limites de gasto configurados direto no painel da OpenAI/Anthropic, ação do
  próprio Diego, não deste sistema).
- Detecção de anomalia/spike relativo (ex.: "3x a média dos últimos 7 dias") — o pedido foi
  um teto fixo simples.
- Alertar os curadores convidados — só o admin.

## Testes

Mesmo padrão de `tests/test_ia_custo.py` (`TestRegistrarNuncaLevanta` já prova que
`registrar` nunca levanta mesmo com o banco fora do ar — a checagem nova precisa da mesma
garantia):

- Gasto abaixo do teto: não chama `enviar_admin`, não grava `set_config`.
- Gasto acima do teto, primeira vez no dia: chama `enviar_admin` uma vez, grava
  `set_config("custo_alerta_ultimo_dia", hoje)`.
- Gasto acima do teto, `set_config` já marcado com o dia de hoje: NÃO chama `enviar_admin`
  de novo (mata o spam).
- Dia seguinte (flag do dia anterior): volta a poder avisar.
- Falha em `db.resumo_ia_uso`, `deliver.enviar_admin` ou `db.set_config` durante a checagem:
  não propaga — `registrar` continua não levantando exceção nenhuma.
- Override de `DSCURSO_LIMIAR_CUSTO_DIA` muda o teto sem precisar mexer no código (mesmo
  padrão de teste de `TestOverrideDeEnv`).
