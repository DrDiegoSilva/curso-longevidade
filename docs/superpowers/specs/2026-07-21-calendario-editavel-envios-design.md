# Calendário editável de envios — Design (Projeto A)

**Data:** 2026-07-21
**Autor:** Dr. Diego + Claude
**Status:** Aprovado no brainstorming; aguardando revisão do spec antes do plano de implementação.

---

## 1. Contexto

O app (container único no EasyPanel) roda dois produtos por host:

- `artigos.drdiegosilva.com.br` → assinatura ("atualização semanal"): landing, `/assinar`, portal `/entrar`, cobrança Asaas, e o **robô diário** que envia 1 estudo/dia por WhatsApp, seg–sex, 08h BRT.
- `curso.drdiegosilva.com.br` → ebook do curso de longevidade (produto separado; **não** é escopo deste spec — ver Projeto B).

Hoje o robô decide o estudo do dia **só na véspera, às 18h**, sem nada agendado para o futuro:

- `daily.preparar_18h()` (18h): reabastece a fila se `queue_store.tamanho() < 2`, tira `queue_store.proximo()` (fila fresca de artigos crus, ordenada por score + regra de variedade), gera conteúdo, salva rascunho e avisa o curador com link de revisão. Se a fila fresca está vazia, cai em `_preparar_da_reserva()` (próximo resumo pronto da reserva).
- `daily.enviar_08h()` (08h): se há rascunho não-vetado, gera PDF/áudio e envia aos assinantes ativos.

Dois estoques distintos:
- **Fila fresca** — `queue_store` (`/data/queue.json`): artigos crus triados, **sem** resumo gerado. Conteúdo é gerado no 18h.
- **Reserva** — `reserva_resumos` (SQLite via `db.py`): resumos **prontos** (curadoria "gerar" + estudos do Diego com prioridade). `proximo_da_reserva()` ordena por `prioridade DESC, criado_em ASC`.

**Problema:** o Diego não consegue ver nem reorganizar a ordem dos próximos dias. Só influencia via cotas de tema, adicionar estudo próprio (fura fila), ou editar/vetar o rascunho de amanhã no link das 18h — um dia por vez.

## 2. Objetivo

Uma **agenda materializada** dos próximos ~15 dias úteis (2–3 semanas rolantes) que o sistema pré-preenche automaticamente e o Diego reordena/edita numa tela `/agenda`, com **tema e estudo** visíveis por dia.

### Metas
- Ver e reorganizar 2–3 semanas de envios de uma vez.
- Pré-preenchimento automático (rotação de tema + variedade), preferindo reserva pronta e caindo pra fila fresca.
- Arrastar-e-soltar pra reordenar; fixar, trocar e pular dias.
- Envio automático segue funcionando sem o Diego mexer toda semana.

### Não-metas (fora deste spec)
- Transformar o ebook em mini-curso vendável (**Projeto B**, spec próprio).
- Mudar PDF, áudio, cobrança, portal do assinante ou lógica de envio das 08h.
- Unificar os dois estoques (fila fresca × reserva) num só — fora de escopo (YAGNI).

## 3. Decisões de escopo (confirmadas)

- **Horizonte:** ~15 dias úteis materializados (rolagem contínua).
- **Fonte dos slots:** reserva (pronto ✓) **e** fila fresca (⏳ gera às 18h). Incluir fila fresca em v1 preserva o envio automático sem depender de curadoria semanal.
- **Arquitetura:** agenda materializada (tabela `data → estudo`), não override leve nem fila sem datas.

## 4. Modelo de dados

Nova tabela `agenda` em `db.py` (criada no `init()`), uma linha por dia útil:

| campo | tipo | conteúdo |
|---|---|---|
| `data` | TEXT PK | `YYYY-MM-DD` (só seg–sex) |
| `tipo` | TEXT | `reserva` · `fila` · `pulado` · `vazio` |
| `ref_id` | TEXT | id de `reserva_resumos` (quando `tipo=reserva`) |
| `payload` | TEXT | JSON do artigo cru (quando `tipo=fila`) |
| `tema` | TEXT | snapshot do tema (exibição) |
| `titulo` | TEXT | snapshot do título (exibição) |
| `fixado` | INTEGER | 0/1 — fixado pelo Diego; materializador não sobrescreve |
| `criado_em` | TEXT | ISO |
| `atualizado_em` | TEXT | ISO |

**Invariante — nada agendado em dobro nem perdido:** materializar um slot **remove o item do estoque** e o prende na data:
- `reserva`: o `reserva_resumos` correspondente vai de `status='pronto'` → `status='agendado'` (novo status; continua fora da varredura de `proximo_da_reserva`/`contar_reserva_pronto`).
- `fila`: o artigo sai da `queue.json` e vira snapshot em `payload`.

Desagendar/desfixar/trocar **devolve** o item ao estoque (reserva volta a `pronto`; item de fila volta pra `queue_store`).

Estados de slot:
- `reserva` / `fila` — tem estudo pronto pra sair.
- `pulado` — dia de folga escolhido pelo Diego; não envia.
- `vazio` — sem item disponível (estoque insuficiente); dispara alerta.

## 5. Materializador

`daily.materializar_agenda(dias=15)` — mantém a janela rolante preenchida:

1. Calcula os próximos `dias` dias úteis a partir de amanhã (usa `_e_dia_util`).
2. Slots **fixados** e **pulados** são preservados.
3. Para cada dia não-fixado/não-pulado ainda **vazio**, escolhe o próximo item por:
   - **rotação de tema** (padrão = ordem de `temas_config.temas`; editável) como guia inicial;
   - **variedade** — não repetir o tema do dia anterior quando houver alternativa;
   - **preferência de fonte** — reserva pronta antes de fila fresca.
4. Ao escolher, materializa (tira do estoque, grava o slot).

**Pureza/testabilidade:** a lógica de seleção é uma **função pura** `planejar_agenda(dias_uteis, slots_fixados, itens_reserva, itens_fila, rotacao, ultimo_tema) -> [slot...]`, sem I/O. `materializar_agenda` faz só a orquestração (ler estoques, chamar a função pura, gravar).

**Gatilhos:** roda diariamente antes das 18h (dentro de/antes de `preparar_18h`) pra manter a janela cheia; e sob demanda pelo botão **"Rematerializar"** no painel (só mexe em dias não-fixados).

**Rotação padrão:** opcional `rotacao_semana` no `temas_config.json` (lista de temas por posição). Ausente → usa a ordem de `temas`. Como o Diego reordena depois, é só um ponto de partida.

## 6. Integração no envio (18h / 08h)

`preparar_18h` passa a **ler o slot de amanhã** em vez de chutar da fila:

```
slot = db.agenda_slot(amanha)
- pulado            -> não prepara nada (folga escolhida); loga e sai.
- reserva(ref_id)   -> monta rascunho daquele resumo pronto (reusa _preparar_da_reserva parametrizado por id).
- fila(payload)     -> gera conteúdo do artigo do slot (fluxo atual: content.gerar_conteudo) e monta rascunho.
- vazio / ausente / erro -> FALLBACK ao comportamento atual (queue_store.proximo -> _preparar_da_reserva)
                            para nunca falhar um dia útil, e avisa o curador.
```

Antes de ler o slot, `preparar_18h` chama `materializar_agenda()` (mantém a janela rolante). O `enviar_08h` e todo o restante (PDF único, áudio, distribuição, `registrar_digest`, marcar reserva enviada) ficam **inalterados** — só muda a origem do rascunho. Ao enviar, o slot de hoje é marcado como consumido.

## 7. Painel `/agenda`

- Rota nova em `serve.py`, **protegida por `ADMIN_TOKEN`** (mesmo padrão de `/curadoria`).
- GET renderiza `site_web.pagina_agenda(slots, estoque, ...)`: grade de 3 semanas, cada dia com emoji/tema, título e badge (✓ reserva / ⏳ fila / 💤 pulado / ⚠️ vazio). Rodapé com estoque ("32 prontos") e alerta se faltar item pra fechar 15 dias.
- **Arrastar-e-soltar nativo** (HTML5 DnD em JS vanilla inline — sem biblioteca, compatível com CSP). **Fallback sem JS**: botões ↑/↓ e "mover para [select de dia]".
- Ações (POST, admin-gated):
  - `mover` (data_orig → data_dest): se o destino já tem estudo, os dois **trocam de dia** (swap); se está vazio/pulado, o item só realoca. Fixados no destino bloqueiam a troca (recusado com aviso).
  - `trocar` (data): substitui o estudo do slot por outro do estoque (lista da reserva/fila do mesmo tema, ou qualquer).
  - `fixar` / `desafixar` (data).
  - `pular` / `despular` (data).
  - `rematerializar`: re-preenche dias não-fixados vazios.

## 8. Ajuste C — intake da fila

`daily.reabastecer` (e/ou o gatilho da curadoria) passa a **acumular todos os bons frescos da semana**, não só quando `queue_store.tamanho() < 2`. Objetivo: alimentar a agenda sem perder estudos bons quando a semana rende 3–4. Mudança pequena, entra junto do Projeto A. Dedupe permanente do `queue_store` já evita repetição.

## 9. Erros / bordas

- Slot `reserva` com `ref_id` inexistente (item apagado) → vira `vazio` + alerta + fallback no 18h.
- `payload` de fila corrompido/vazio → fallback + alerta.
- Estoque insuficiente pra fechar 15 dias → slots `vazio` + reusa o alerta de "estoque baixo" existente (`avisar_estoque_baixo`).
- Mover pra dia passado ou fim de semana → recusado na validação do handler.
- Concorrência (Diego edita enquanto o 18h roda) → o 18h lê o slot no momento da execução; a última edição do Diego antes das 18h vence (last-write simples).
- Redeploy → `queue.json` é efêmero em `/app`? Não: `queue_store` usa `config.DATA` (`/data`, volume persistente). A tabela `agenda` também é persistente (SQLite em `/data`). OK.

## 10. Testes (pytest)

- **`planejar_agenda` (função pura):** variedade (sem tema repetido em dias seguidos), fixados e pulados respeitados, preferência reserva>fila, idempotência ao re-rodar sobre agenda já boa, preenche exatamente N dias úteis, comportamento com estoque magro (gera `vazio`).
- **CRUD `agenda`** em SQLite temporário: upsert, mover, fixar, pular, slot, devolução ao estoque.
- **`preparar_18h`** leitura de slot: fonte correta por tipo + caminho de fallback (partes de rede/IA injetadas/mockadas, como hoje).
- **Handler `/agenda`:** ações atualizam o banco corretamente; validações (dia passado/fim de semana) recusam.
- Meta de cobertura do projeto (80%) mantida nas partes puras/CRUD.

## 11. Arquivos tocados

| arquivo | mudança |
|---|---|
| `app/db.py` | tabela `agenda` no `init()`; status `agendado` na reserva; funções CRUD (`agenda_listar`, `agenda_slot`, `agenda_upsert`, `agenda_mover`, `agenda_fixar`, `agenda_pular`, `agenda_devolver`); `marcar_reserva_agendado/pronto`. |
| `app/daily.py` | `materializar_agenda` + `planejar_agenda` (pura); `preparar_18h` lê o slot com fallback; `_preparar_da_reserva` parametrizado por id; ajuste C no `reabastecer`. |
| `app/queue_store.py` | suporte a remover/devolver item específico (materialização da fila). |
| `app/serve.py` | rota `/agenda` (GET render + POST ações), admin-gated. |
| `app/site_web.py` | `pagina_agenda(...)` (grade + DnD inline + fallback). |
| `app/temas_config.json` | `rotacao_semana` opcional. |
| `app/tests/` | testes acima. |

Fiel ao stack: Python stdlib (sem pip), SQLite via `db.py`, HTML server-rendered, JS vanilla inline.

## 12. Rollout

1. Tabela + CRUD + `planejar_agenda` puro (com testes).
2. `materializar_agenda` + integração no `preparar_18h` (com fallback) + ajuste C.
3. Painel `/agenda` (render + ações + DnD/fallback).
4. Deploy no EasyPanel; validar uma semana com fallback ativo antes de confiar 100% na agenda.
