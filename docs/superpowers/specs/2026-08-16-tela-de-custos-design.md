# Item 40 — a tela de custos de IA

**Data:** 2026-08-16
**Base:** `origin/main` = `9191e75`
**Branch:** `feat/tela-custos`

## O problema

O ledger de custos entrou no ar em 2026-08-14 (ver `2026-08-12-excluir-estudo-do-corpus-design.md`,
parte 2) e desde então grava tokens e caracteres a cada chamada paga. **Mas grava no vazio:**
não existe nenhum lugar onde ler o que foi acumulado.

O pedido original do Diego era de preço, não de curiosidade: *"pra eu ter uma noção dos
custos ou uma tela com custos que já tivemos pra poder saber repassar na precificação"*.

## O fato que molda a tela

**O custo de IA é praticamente FIXO, não por assinante.** O estudo do dia é gerado uma vez
e enviado a todos; o assinante nº 200 não custa quase nada a mais que o nº 20. Logo:

- "custo por assinante" é uma divisão que **despenca conforme a base cresce**;
- o número que sustenta preço é **quanto a máquina custa por mês** e **quantos assinantes
  cobrem isso**.

A tela mostra os dois, e diz essa frase — senão o Diego olha um número que cai sozinho e
tira a conclusão errada sobre o próprio produto.

## Decisões do Diego (2026-08-16)

1. A tela **abre pelo gasto do mês** e mostra o "por assinante" logo abaixo, com a quebra
   por ação.
2. **Quer a conferência contra a fatura real** da Anthropic — ele gera a chave de admin.

## A tela `/admin/custos`

Protegida por `ADMIN_TOKEN` na querystring, como `/admin/precos`.

1. **Gasto do mês corrente** em R$ (nomeando a cotação usada) e em US$.
2. **"Com N assinantes ativos, dá R$ X cada"** — N vem de `subscribers.ativos()` — seguido
   da frase sobre o custo ser fixo.
3. **Quebra por ação**, ordenada do que mais pesa para o que menos pesa: `dossie`,
   `resumo_estudo`, `boletim`, `kit`, `triagem`, `tags`, `metadados`, `perguntas`,
   `titulo`, `grafico`, `aula`, `audio_roteiro`, `audio_tts`, `desconhecido`.
4. **Ledger × fatura, dia a dia, últimos 30 dias** — nossa medição, o valor faturado e a
   diferença.

## A conferência com a fatura (Admin API)

Contrato conferido na documentação em 2026-08-16
(`platform.claude.com/docs/en/api/admin/cost_report/retrieve`):

```
GET https://api.anthropic.com/v1/organizations/cost_report
    ?starting_at=<RFC3339>&bucket_width=1d[&ending_at=…][&page=…]
headers: anthropic-version: 2023-06-01  +  a credencial de admin
resposta: {"data":[{"starting_at","ending_at","results":[{"amount","currency",…}]}],
           "has_more":bool, "next_page":str|null}
```

⚠️ **`amount` vem em CENTAVOS**, como string decimal: `"123.45"` em `"USD"` significa
**US$ 1,23**. A própria documentação diz isso numa linha fácil de pular. Sem dividir por
100, a tela mostraria um gasto 100× maior — plausível o bastante para o Diego acreditar.
**Dividir por 100 é requisito, e tem teste próprio.**

⚠️ **A fatura é da ORGANIZAÇÃO inteira**, não deste app. Qualquer outro uso da mesma conta
Anthropic entra no total. Portanto uma diferença entre ledger e fatura **não significa
automaticamente que a nossa tabela de preços está errada** — pode ser uso de outra origem.
A tela diz isso ao lado da coluna; sem essa frase ela mente por omissão.

**Credencial:** `config.ANTHROPIC_ADMIN_KEY`, da env `DSCURSO_ANTHROPIC_ADMIN_KEY`. É
**diferente da chave que o app usa** para gerar conteúdo, e o Diego precisa criá-la no
console da Anthropic. A documentação exemplifica com `Authorization: Bearer <token>`,
enquanto chaves de admin históricas usam `x-api-key`. Como não dá para testar sem a chave
dele, o cliente manda **`x-api-key` quando o valor começa com `sk-ant-`** e
`Authorization: Bearer` caso contrário — e o erro é reportado na tela, não escondido.

**Degradação, em três estados nomeados na tela:**

| Estado | O que a tela mostra |
|---|---|
| Sem chave configurada | Só a coluna do ledger + "configure `DSCURSO_ANTHROPIC_ADMIN_KEY` para comparar com a fatura" |
| Chave recusada (401/403) | Só o ledger + "a chave de admin foi recusada" |
| API respondeu | As três colunas: nosso ledger, fatura, diferença |

Falha na API **nunca derruba a tela** — o número que já é nosso continua lá. Uma página de
erro tiraria do Diego o dado que existe por causa de uma parte opcional.

## Interfaces

```python
# db.py
resumo_ia_uso(desde, ate=None)   # -> [{"dia","acao","modelo","tokens_in","tokens_out",
                                 #      "chamadas"}], agregado em SQL

# ia_custo.py  (já tem custo_usd, em_brl, registrar, ACOES)
por_acao(linhas)                 # -> [{"acao","usd","brl"}], maior primeiro
por_dia(linhas)                  # -> {"AAAA-MM-DD": usd}

# anthropic_admin.py  (novo — isolado de propósito: é o único ponto que eu não consigo testar)
custo_por_dia(desde, ate=None)   # -> {"estado": "sem_chave"|"recusada"|"erro"|"ok",
                                 #     "dias": {"AAAA-MM-DD": usd}}
```

`resumo_ia_uso` agrega em SQL em vez de trazer todas as linhas: a tela é de admin e roda
pouco, mas o ledger cresce para sempre e a página não pode piorar com o tempo.

## Fora de escopo

- Estimativa de custo nos botões antes do clique. Agora que há medição, ela vira média
  real — mas é outra entrega.
- Gráfico/histórico mês a mês: hoje há dois dias de dados; nasceria vazio.
- Custo de Z-API (WhatsApp) e de infraestrutura. Este ledger é de IA.
- `group_by=workspace_id` na Admin API, que separaria o uso deste app do resto da
  organização. Anotado como o conserto certo se a diferença ficar grande.

## Testes

TDD, `unittest`, `cd app && python3 -m unittest discover -s tests`.

- `resumo_ia_uso` agrega por dia/ação/modelo e respeita a janela (`desde`/`ate`);
- `por_acao` ordena do maior gasto para o menor e soma entrada+saída;
- **`amount` em centavos vira dólar** — `"123.45"` → `1.2345`; é o teste que impede o erro
  de 100×;
- paginação: `has_more` + `next_page` são seguidos (fatura com muitos dias não some);
- os três estados de degradação, com a tela renderizando em todos;
- a tela mostra a cotação usada, o N de assinantes e a frase do custo fixo;
- a tela diz que a fatura é da organização inteira;
- sem token: 403.

Fechando: quebrar cada guarda de propósito e conferir que a suíte cai.
