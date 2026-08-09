# Kit de redes para equipe de marketing + bloco de explicação ao paciente — design

**Data:** 2026-08-09
**Status:** spec aprovada no brainstorm, aguardando plano de implementação

## O problema

Duas queixas do dono do produto sobre o PDF diário:

1. **O kit de redes não serve para uma equipe de marketing.** Hoje as pautas de Reels são itens
   de uma lista, com ângulo e dado de apoio na mesma linha, em corpo 14px contra os 20px do texto
   — "tudo em card pequeno com texto corrido". Um social media não consegue produzir a partir dali.
2. **O estudo não ajuda na prática clínica.** Falta a fala que o médico usa no consultório para
   explicar o achado ao paciente.

Uma terceira queixa apareceu no brainstorm e **não entra aqui**: cada estudo chega como uma ilha,
sem conversar com os anteriores. Virou o item 30 do backlog (dossiê vivo por tema) — projeto
próprio, do tamanho da trilha.

## Regra editorial (a decisão mais importante)

O público das pautas é o **paciente do médico assinante**, não o médico. Paciente não lê estudo.

- Cada pauta **abre numa dor que o paciente reconhece em si mesmo** e **termina apontando para
  algo que se resolve com acompanhamento** — que é o que o assinante vende.
- O estudo é a **prova**, nunca a manchete.
- **Proibido** pauta sobre metodologia, grupo comparador, tamanho de amostra ou tempo de
  seguimento. Isso é conversa de médico para médico e faz o paciente rolar o feed.
- Crítica de metodologia continua existindo — no resumo clínico (`SYS_ESTUDO`), que é para o
  médico. Não no Reels, que é para o paciente dele.

**Linguagem simples, sem jargão.** É proibido o texto gerado usar "nomeia a cena", "vira a
chave", "prova por baixo", "quebra de padrão", "dor do público", "CTA". Cada passo do roteiro
começa com verbo e diz o que fazer: "Comece contando que...", "Explique que...", "Diga a
ressalva:...", "Termine assim:...". Quem lê é médico ou social media, não publicitário.

## O que muda no PDF

```
capa · título · metadados          intacto
resumo clínico (SYS_ESTUDO)        INTACTO — o formato aprovado em julho não é tocado
braços · gráfico                   intacto
─────────────────────────────────
Como explicar pro paciente         BLOCO NOVO (clínico)
─────────────────────────────────
kit de redes
   1 · O estudo                    igual
   2 · A frase                     igual
   3 · Reels                       CADA PAUTA VIRA UM CARD
   4 · O que não dá pra afirmar    BLOCO NOVO (CFM)
rodapé                             intacto
```

**Cada pauta, dentro do card:** título curto · "Primeiros 3 segundos" (o gancho) · "O que falar,
nesta ordem" (3 a 5 passos numerados) · "Dado do estudo" (o que sustenta, para o médico conferir,
não para ser dito no vídeo). Tipografia no tamanho do corpo, não em 14px.

**O bloco do CFM é por estudo, não por pauta** — os limites da evidência são os mesmos para todas
as pautas que saem dela. E é **específico daquele estudo**, puxado do próprio texto (amostra
pequena, uso fora de bula, desfecho que é questionário e não exame, limitação declarada pelos
autores), somado ao que o CFM veda. Nunca uma lista genérica de boas práticas.

**"Como explicar pro paciente" fica antes do kit**, para o clínico ficar junto do clínico: o
médico lê e para no fim do gráfico; quem vai produzir post pula direto para o final.

## Arquitetura

**Estende o JSON que já existe no campo `gancho`.** Descartado: coluna nova por pedaço (exigiria
migrar `digests`, `reserva_resumos` e `classicos` sem ganho real) e segunda chamada de IA (mais
custo, mais latência, mais um ponto de falha no caminho do envio diário).

```json
{
  "frase": "...",
  "paciente": "...",
  "limites": ["...", "..."],
  "reels": [{"titulo": "...", "gancho": "...", "roteiro": ["...", "..."], "apoio": "..."}]
}
```

### Onde mexe

| Arquivo | O quê |
|---|---|
| `app/content.py` | `SYS_GANCHO` (prompt novo), `parse_gancho` (formato novo + compatibilidade), `max_tokens` |
| `app/pdf.py` | `_kit_html` (cards, blocos novos) e o CSS do kit |
| `app/site_web.py` | cópia própria do CSS do kit (linhas ~238-255) — o site renderiza o mesmo HTML via `pdf._kit_html` em `site_web.py:1976` |

`app/daily.py`, `app/db.py` e `resumo_diario.SYS_ESTUDO` não são tocados.

## Os três cuidados

Verificados com uma saída real, gerada sobre um estudo puxado do Europe PMC pela mesma busca que
a máquina usa (testosterona transdérmica na pós-menopausa, EJOG, jun/2026):

**1. O teto de tokens estoura.** A saída real deu **934 tokens**; o limite hoje é **900**. Sobe
para 2500. Sem isso o JSON chega cortado — e é aí que mora o cuidado 3.

**2. Compatibilidade com o que já está no banco.** O estoque de `reserva_resumos` **já tem
ganchos gerados no formato antigo**. Trocar o parse sem cuidado quebra o kit de todo estudo que
já está na fila. `parse_gancho` passa a aceitar quatro formas, sem levantar exceção em nenhuma
(isto roda no caminho do envio do dia):

| Entrada | Comportamento |
|---|---|
| JSON novo | todos os campos |
| JSON atual (`angulo`/`apoio`) | `angulo` vira `gancho`, sem roteiro; `paciente` e `limites` vazios |
| texto puro (legado) | vira uma pauta só com gancho, como hoje |
| lixo / vazio | estrutura vazia |

**3. Nunca imprimir JSON cru.** Hoje, quando o `json.loads` falha, o texto bruto inteiro vira uma
pauta — e o PDF imprime `{"frase":...` na cara do assinante. Reproduzido em teste. Passa a: se o
parse falhar e o texto parecer JSON, o bloco não sai. Melhor faltar o kit do que entregar código.

## Testes

- cada um dos quatro formatos de entrada do `parse_gancho`, incluindo o do estoque de reserva
- JSON truncado não produz pauta nenhuma e não imprime `{` no HTML
- pauta com roteiro vira card com os passos numerados
- `limites` vazio não deixa bloco órfão no PDF; `paciente` vazio idem
- as classes CSS novas existem nos **dois** lugares (`pdf.py` e `site_web.py`)
- escape: `<script>` em qualquer campo (gancho, passo do roteiro, limite) sai escapado
- uma peça real ponta a ponta: `parse_gancho` → `_kit_html`, sem sobrar marcador

## Fora de escopo

- **Dossiê vivo por tema** — item 30 do backlog, projeto próprio.
- **Legenda pronta para o post** — considerada e descartada pelo dono no brainstorm.
- `SYS_ESTUDO` e o resumo clínico.
- Verificação visual do PDF renderizado: exige Chromium, que não existe no ambiente de
  desenvolvimento. O teste real é a revisão das 18h, que entrega o rascunho de amanhã ao curador
  antes de qualquer assinante receber.
