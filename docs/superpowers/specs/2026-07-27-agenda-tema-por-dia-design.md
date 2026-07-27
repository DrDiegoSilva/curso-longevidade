# Agenda — tema amarrado ao dia da semana

**Data:** 2026-07-27
**Origem:** o Diego quis "2 dias de Obesidade, e Longevidade + Performance dividindo um dia". Ao investigar, descobriu-se que a rotação atual **não amarra tema a dia nenhum** — então o pedido não sai de uma edição de config.

## Contexto: por que a rotação de hoje não resolve

`temas_config.json` tem `rotacao_semana = ["Obesidade","Hormonal","Longevidade","Performance","Lipedema"]`, e `daily.materializar_agenda` a repassa para `agenda_plan.planejar_agenda` (`daily.py:192`).

Dentro de `planejar_agenda` (`agenda_plan.py:69`):

```python
rot_i = 0
for data, tema_atual, bloqueado in dias_ordenados:
    if bloqueado or tema_atual is not None:
        prev = tema_atual
        continue                      # <- NÃO avança rot_i
    preferido = rot[rot_i % len(rot)] if rot else None
    ...
    rot_i += 1                        # <- avança só quando PREENCHE
```

Três consequências:

1. **`rot_i` reinicia em 0 a cada materialização.** A posição 0 é "o próximo dia vago", não segunda-feira.
2. **A janela começa em amanhã** (`daily.py:114`, `d >= amanha_str`), não no início da semana.
3. **Dias bloqueados/fixados/já preenchidos não avançam o ponteiro**, então o alinhamento com o calendário deriva a cada rodada.

Evidência real (2026-07-27, segunda): o envio do dia foi **Longevidade** e o rascunho de terça saiu **Performance** — posições 3 e 4 do ciclo caindo em segunda e terça. O ciclo está sendo respeitado; o que não existe é vínculo com o dia da semana.

**Nunca houve previsibilidade de tema por dia** — nem para o admin, nem para o assinante.

## Objetivo

Amarrar tema a dia da semana, de forma determinística, com este calendário:

| Dia | Tema |
|---|---|
| segunda | Longevidade / Performance (alterna por semana) |
| terça | **Obesidade** |
| quarta | Hormonal |
| quinta | **Obesidade** |
| sexta | Lipedema |

Motivação de produto: os `CAPS` da varredura (`curadoria.py:18`) refletem o volume real por tema — Obesidade 20, Hormonal 9, Performance 8, Longevidade 7, Lipedema 6. Dar dois dias a Obesidade troca um estudo mediano de um tema raso pelo segundo melhor de um tema fundo. Não é sobre escassez (tudo está em superávit: ~50 candidatos para 5 envios), é sobre qualidade.

## Não-objetivos (YAGNI)

- **Não** mexer nos `CAPS` nem no piso de nota (`SCORE_PISO`/`MIN_POR_TEMA`).
- **Não** mexer na ordem do `_rank` — variedade continua acima da rotação.
- **Não** adicionar domingo/empreendedorismo (item 9 do backlog). O formato novo já acomoda, mas não é escopo.
- **Não** mudar `dias_envio` nem quem envia em que horário.
- **Não** criar tela de admin para editar o calendário — é config de arquivo, como já era.

## Componentes

### 1. Config — `app/temas_config.json`

`rotacao_semana` **sai**; entra `temas_por_dia`:

```json
"temas_por_dia": {
  "segunda": ["Longevidade", "Performance"],
  "terca":   ["Obesidade"],
  "quarta":  ["Hormonal"],
  "quinta":  ["Obesidade"],
  "sexta":   ["Lipedema"]
}
```

Lista por dia: um item = tema fixo; dois ou mais = alterna por semana. Escolhido dicionário (e não lista posicional) porque o item 9 do backlog quer domingo — com dicionário é só acrescentar a chave.

As chaves usam os mesmos nomes de `agenda_plan.DIAS` (`agenda_plan.py:11`), que já são os nomes que `dias_envio` usa.

### 2. `agenda_plan.tema_do_dia()` — função pura

```python
def tema_do_dia(data, temas_por_dia):
    """Tema preferido p/ a data (YYYY-MM-DD). Alterna a cada semana quando o dia tem
    mais de um tema. Devolve None quando o dia não está no mapa (aí não há preferência)."""
    dt = datetime.strptime(data, "%Y-%m-%d")
    temas = (temas_por_dia or {}).get(DIAS[dt.weekday()]) or []
    return temas[(dt.toordinal() // 7) % len(temas)] if temas else None
```

**Alternância sem estado:** cada data decide sozinha, a partir do próprio número ordinal. Não há contador para desincronizar, então planejar quatro semanas à frente sai coerente e a materialização pode rodar a qualquer hora sem deslocar nada. É exatamente isso que mata a deriva.

**Por que `toordinal() // 7` e não `isocalendar()[1]`:** a paridade da semana ISO quebra na virada de ano em anos com 53 semanas — semana 53 e semana 1 têm a mesma paridade, o que repetiria o tema em duas segundas seguidas. `toordinal()` é monotônico e não conhece fronteira de ano; como a função só é consultada num dia fixo da semana, segundas consecutivas ficam exatamente 7 dias apart e o balde avança de exatamente 1 a cada semana.

### 3. `agenda_plan.planejar_agenda()` — troca do contador pelo mapa

Assinatura muda de `(dias_ordenados, candidatos, rotacao, tema_anterior)` para `(dias_ordenados, candidatos, temas_por_dia, tema_anterior)`.

O contador `rot_i` é removido; `preferido` passa a vir de `tema_do_dia(data, temas_por_dia)`.

### 4. `daily` — leitura da config

`_rotacao()` (`daily.py:97`) vira `_temas_por_dia()`, lendo a chave `temas_por_dia`. Se a chave faltar, devolve `{}` — `tema_do_dia` então devolve `None` para todo dia, `preferido` fica `None`, e a escolha degrada para fresco → camada → nota. Nenhum dia fica vazio por causa disso.

A chamada em `daily.py:192` passa a repassar `_temas_por_dia()`.

## Comportamentos preservados de propósito

**Variedade continua ganhando da rotação.** No `_rank` (`agenda_plan.py:52`) a ordem é variedade → rotação → fresco → camada → nota. Consequência: se a segunda cair em Obesidade por falta de candidato do tema dela, a terça vai preferir outro tema a repetir Obesidade em dias seguidos. É o comportamento desejado — dois dias iguais em sequência é pior que furar o mapa um dia.

Com o calendário escolhido, terça e quinta não são adjacentes (quarta é Hormonal), então no caminho feliz a variedade nunca briga com o mapa.

**Dia sem candidato do tema preferido não fica vazio.** `_escolher` (`agenda_plan.py:62`) já pega o melhor disponível quando ninguém casa com a preferência — `preferido` só contribui com 0 ou 1 no ranking. Nada a mudar. Com Obesidade em cap 20, terça e quinta praticamente nunca vão cair nesse caminho.

## Testes

Padrão da casa: `unittest` standalone em `app/tests/`, sem rede.

**`test_agenda_plan.py`** (existente):

- `tema_do_dia` devolve o tema do dia para dias de um item só (terça → Obesidade; quinta → Obesidade)
- `tema_do_dia` alterna entre semanas consecutivas num dia de dois itens (duas segundas seguidas devolvem temas diferentes)
- `tema_do_dia` continua alternando na virada de ano (duas segundas seguidas que cruzam 31/12 devolvem temas diferentes) — o caso que a paridade de semana ISO erraria
- `tema_do_dia` é estável dentro da mesma semana (chamar duas vezes a mesma data dá o mesmo tema)
- `tema_do_dia` devolve `None` para dia fora do mapa (ex.: sábado) e para mapa vazio/`None`
- `planejar_agenda` respeita o mapa: numa terça com candidato de Obesidade disponível, escolhe Obesidade
- `planejar_agenda` cai para outro tema quando não há candidato do tema do dia — e o dia **não** fica vazio
- variedade ainda vence o mapa quando o dia anterior teve o mesmo tema

⚠️ **Os testes existentes de `TestPlanejar` e `TestRankPiramide` passam `rotacao` como lista** (`["A"]`, `["A","B"]`, `["Obesidade"]`, `["Performance"]` — 11 call sites entre as linhas 64 e 146). Todos precisam migrar para o formato de dicionário. Para preservar a intenção de cada teste com edição mecânica, adicionar um helper no topo do arquivo:

```python
def _todo_dia(tema):
    """Mapa que preferre o mesmo tema em qualquer dia — preserva a intenção dos
    testes que só queriam 'a rotação pede X'."""
    return {d: [tema] for d in ap.DIAS}
```

Os testes que passavam `["A"]` passam a `_todo_dia("A")`. O único que precisa de mapa de verdade é `test_variedade_nao_repete_tema` (usava `["A","B"]`): as datas são 2026-07-27 (segunda), 28 (terça) e 29 (quarta), então `{"segunda": ["A"], "terca": ["B"], "quarta": ["A"]}` mantém o que ele testava.

**`test_dias_envio.py`** — conferir se algum teste depende de `rotacao_semana`; se depender, migrar.

## Critérios de aceite

1. `tema_do_dia("2026-07-28", MAPA)` (terça) devolve `"Obesidade"`; `"2026-07-30"` (quinta) também.
2. Duas segundas consecutivas devolvem temas diferentes entre Longevidade e Performance.
3. Materializando uma semana cheia com estoque de todos os temas, a grade sai seg=Longe ou Perfo, ter=Obesidade, qua=Hormonal, qui=Obesidade, sex=Lipedema.
4. Terça sem nenhum candidato de Obesidade recebe outro tema — não fica vazia.
5. A chave `rotacao_semana` foi removida de `temas_config.json` e não é mais lida por nenhum código.
6. `cd app && python3 -m unittest discover -s tests` verde.

## Arquivos

| Arquivo | Mudança |
|---|---|
| `app/temas_config.json` | `rotacao_semana` sai, `temas_por_dia` entra |
| `app/agenda_plan.py` | `tema_do_dia()` nova; `planejar_agenda` troca `rot_i` pelo mapa |
| `app/daily.py` | `_rotacao()` → `_temas_por_dia()`; chamada em `materializar_agenda` |
| `app/tests/test_agenda_plan.py` | testes de `tema_do_dia` + migração dos 10 call sites |

## Verificação que só o Diego pode fazer

Depois do deploy, abrir `/agenda` no admin e conferir que a grade das próximas semanas mostra Obesidade na terça e na quinta, e que a segunda alterna entre Longevidade e Performance de uma semana para a outra.
