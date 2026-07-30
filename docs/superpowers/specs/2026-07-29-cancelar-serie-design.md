# Cancelar série — design

**Data:** 2026-07-29 · **Contexto:** follow-up nº1 da Fase 2 (Séries), que subiu na main `76cbbaa`.

## Problema

Hoje não existe como desfazer uma ativação de série. Duas consequências, uma banal e uma grave:

1. **Banal e frequente:** o admin ativa com a data errada (queria dia 12, mandou dia 5). Não tem volta pela tela.
2. **Grave:** se a ativação falha no meio de um jeito que o rollback automático também falha, a série fica `ativa` sem nenhum dia marcado. `reconciliar` **se recusa de propósito** a fechar série sem data (pra não correr com o claim de "uma ativa por vez"), então esse estado hoje só sai editando o banco. Está documentado no docstring de `series._devolver_claim`.

A trava de "uma série ativa por vez" faz de qualquer um dos dois um bloqueio total: enquanto a série presa existe, **nenhuma outra série pode ser ativada**.

## Comportamento decidido (Diego, 2026-07-29)

Cancelar uma série ativa:

- **Dias ainda não enviados:** o dia volta a ficar vazio e o estudo volta pro estoque de disponíveis. A rotação normal volta a preencher o dia.
- **Dias já enviados:** ficam como estão. Não existe des-enviar.
- **A série:** volta pra `rascunho` com os itens intactos (só perdem a data atribuída), pronta pra ser reativada com a data certa.

O objetivo é ser o **desfazer de verdade**, não um "arquivar".

## Regras de borda

**Dia de hoje nunca é liberado.** O envio das 08h já passou (ou está em curso) quando o admin mexe na tela; liberar hoje não desfaz nada e pode confundir o registro. Só dias estritamente futuros entram.

**Dia cujo rascunho das 18h já foi montado não é liberado — e o admin é avisado.** É a mesma limitação que já justifica a existência de `series.dia_minimo_inicio`: o rascunho pronto seria enviado de qualquer forma, então liberar o slot daria a impressão falsa de que o dia foi desfeito. Na prática isso costuma pegar o dia seguinte, quando o cancelamento acontece depois das 18h. A checagem reusa `draft_store.carregar(dia) is not None`, igual `dia_minimo_inicio`.

**Só libera o dia se ele ainda for daquele item.** Antes de devolver, confere que o slot da agenda ainda aponta pro `ref_id` do item. Se alguma outra coisa tomou o dia no meio (troca do Item 23, edição manual na `/agenda`, rotação), o dia não é mexido e o estudo **não** volta pro estoque — ele não é mais nosso. Devolver às cegas duplicaria o estudo no estoque.

**Preserva `fixado`.** Igual `db.agenda_devolver` já faz.

**Série `ativa` sem nenhum dia marcado (a presa):** cancelar simplesmente solta o claim e devolve pra `rascunho`. Nenhum dia pra liberar. É a saída que hoje não existe.

**Série `incompleta`:** cancelável do mesmo jeito. É o estado de ativação parcial, e ele também merece desfazer.

**Série `concluida` ou `rascunho`:** não tem o que cancelar. O botão não aparece.

## Fail-safe

Mesma regra que a ativação já segue, e pelo mesmo motivo: **liberação dia-a-dia em `try/except`**, e falha parcial **avisa** em vez de sumir. Se 2 de 4 dias falharem, o admin vê quais e a série não fica num estado que ele não consegue enxergar. A ordem importa: devolve o estudo ao estoque **antes** de limpar o slot, para que uma falha no meio deixe o slot ainda apontando pro estudo em vez de perdê-lo — é o cuidado que `db.agenda_devolver` já documenta.

## Bug pré-existente que entra no caminho

`db.agenda_devolver` trata `reserva` e `fila`, mas **não `candidato`** — enquanto `series._liberar_dia` trata os três. Consequência atual: `agenda_pular` num dia ocupado por candidato **vaza o candidato** (o slot é limpo e o estudo nunca volta pro estoque). Já tinha sido apontado na review da Fase 2 e ficou diferido.

Cancelar série precisa liberar dias de candidato corretamente, então esse buraco entra no escopo: `agenda_devolver` passa a tratar `candidato` via `marcar_candidato_pronto`, alinhando com `_liberar_dia`. Corrige de tabela o vazamento do `agenda_pular`.

## Interface

**`series.cancelar_serie(serie_id, db_mod=None, hoje=None, preparado_fn=None) -> (ok, msg)`**

`hoje` e `preparado_fn` injetáveis pra teste, mesmo padrão de `dia_minimo_inicio`/`ativar_serie`.

A mensagem diz o que aconteceu em números — quantos dias liberados, quantos mantidos e por quê:
> `Série cancelada: 2 dias liberados, 2 mantidos (1 já enviado, 1 com rascunho pronto). Os estudos voltaram pro estoque.`

Falha parcial:
> `Série cancelada com ressalva: 3 dias liberados, 1 falhou (2026-08-07 — ver logs). Confira a /agenda.`

**Tela `/series`:** botão **🚫 Cancelar** na série ativa/incompleta. Confirmação em duas etapas, seguindo o padrão que o `/admin` já usa pra remover assinante (`acao=cancelar` renderiza a confirmação, `acao=cancelar_confirmar` executa). A confirmação diz quantos dias serão liberados e quantos ficam — o admin decide vendo o efeito, não no escuro.

**Rota:** `POST /series` ganha `cancelar` e `cancelar_confirmar`, no bloco já gateado.

## Fora de escopo

- Cancelar dia individual (a `/agenda` já tem pular/mover).
- Desfazer envio.
- Fazer `reconciliar` rodar de noite (follow-up separado da Fase 2).
- Reordenar/editar série depois de ativada.

## Testes

- libera dia futuro: estudo volta a `pronto`, slot vira `vazio`, item perde a `data`
- não mexe em dia passado nem no de hoje
- não mexe em dia com rascunho pronto, e **avisa**
- não mexe (nem devolve o estudo) em dia cujo slot já é de outro `ref_id`
- preserva `fixado`
- candidato volta pro estoque (o bug do `agenda_devolver`)
- série presa (`ativa`, zero datas) → volta pra `rascunho` e **libera a próxima ativação**
- `incompleta` cancelável; `concluida`/`rascunho` recusadas
- falha parcial: avisa, não fica silenciosa
- rota: sem token → 403; confirmação em duas etapas
- **regressão que fecha o ciclo:** ativar com data errada → cancelar → reativar na data certa → agenda certa

Cada correção provada por mutação (reverte o fix, o teste tem que ficar vermelho pelo motivo certo).
