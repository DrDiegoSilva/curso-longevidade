# Assinatura para Médicos — Digest Científico Diário (Fase 1)

**Data:** 2026-07-18
**Produto:** `curso-longevidade` (app isolado, VPS EasyPanel Campinas — separado do clinicdspro)
**Status:** design aprovado no brainstorm; pendente revisão da spec antes do plano de implementação.

---

## 1. Contexto e visão

Hoje o app envia, às 08h, um resumo de longevidade para o WhatsApp do Dr. Diego (um destinatário só) e mantém um "ebook" público.

A virada: transformar isso num **produto de assinatura para médicos**. Todo dia útil, o médico assinante recebe **no WhatsApp o resumo de um artigo científico** (temas rotativos: obesidade, hormônios, longevidade, etc.) **+ um PDF bonito e personalizado**. A assinatura **renova automaticamente até o médico cancelar**.

O leitor final é o **próprio médico** (educação/atualização clínica), não o paciente dele.

## 2. Objetivos e não-objetivos (Fase 1)

**Objetivos**
- Motor de conteúdo com **rigor**: busca em vários bancos científicos, escolhe o artigo do dia, gera resumo estruturado e um **PDF caprichado**.
- **Revisão "silêncio = aprovado"**: às ~18h o candidato do dia vai para o Dr. Diego revisar/editar/vetar; às 08h dispara automaticamente se não for barrado.
- **Landing page** com **autocadastro + pagamento recorrente** (4 planos).
- **Entrada/saída automática** da lista de envio conforme o pagamento (webhook).
- **Cancelamento self-service** com save flow.
- Entrega **WhatsApp + PDF personalizado** para a lista de assinantes ativos.

**Não-objetivos (Fase 1)**
- Área de membros com login / biblioteca navegável do histórico.
- Personalização de temas por médico (todos recebem o mesmo digest).
- App mobile nativo.
- Múltiplos artigos por dia (Fase 1 = **1 artigo/dia**).

## 3. Usuários

| Papel | O que faz |
|---|---|
| **Dr. Diego (curador/admin)** | Revisa/edita/aprova/veta o resumo do dia; define planos e preços; gerencia a lista-semente. |
| **Médico assinante** | Se cadastra e paga na landing; recebe WhatsApp+PDF; gerencia/cancela a assinatura por link secreto. |
| **Robô (sistema)** | Busca, resume, gera PDF, notifica o curador, dispara para assinantes, processa webhooks de pagamento. |

## 4. Fluxo diário (visão de negócio)

1. **~18h (véspera):** robô procura o melhor artigo do tema do dia → escreve o resumo → monta o PDF → envia **só para o Dr. Diego** (WhatsApp) com um **link de revisão secreto**.
2. **À noite:** Dr. Diego abre o link quando puder. Pode **aprovar**, **editar** (o PDF se regenera), **gerar outra versão** (IA refaz) ou **não enviar hoje**. Se **não fizer nada**, segue.
3. **08h (dia seguinte):** se não foi vetado, o resumo + PDF vão automaticamente para **todos os assinantes ativos** (WhatsApp + PDF personalizado com o nome de cada um), com envio espaçado.

## 5. Arquitetura / componentes

App único em container (Python), servido em `curso.drdiegosilva.com.br`, **isolado** do clinicdspro. Volume persistente em `/data`.

Componentes (módulos em `app/`):
- **`sources/`** — conectores de busca (PubMed, Europe PMC, ClinicalTrials.gov, medRxiv). Cada um: entrada = termo+filtros; saída = lista normalizada de artigos.
- **`selection.py`** — escolhe o artigo do dia (recência, tipo de estudo, dedupe).
- **`summarize.py`** — chama Claude com prompt estruturado; retorna o resumo.
- **`pdf.py`** — monta o PDF (HTML+CSS → renderizador).
- **`review.py`** — máquina de estado do rascunho do dia + páginas de revisão.
- **`billing/asaas.py`** — cria assinatura, recebe webhooks, cancela.
- **`subscribers.py`** — CRUD da lista de assinantes (arquivo em `/data`).
- **`deliver.py`** — envio WhatsApp+PDF aos assinantes (Z-API), com throttle.
- **`web/serve.py`** — landing, autocadastro, "minha assinatura", revisão, `/health`.
- **`scheduler.py`** — dispara jobs 18h e 08h (fuso BRT).
- **`config.py`** — planos/preços/temas/toggles (lê `/data/config.json`, editável por telinha admin).

## 6. Modelo de dados (arquivos em `/data`)

Fase 1 sem banco relacional — arquivos JSON no volume persistente:
- `/data/base/` — histórico de artigos já enviados (dedupe) e rascunhos.
- `/data/drafts/AAAA-MM-DD.json` — rascunho do dia: `{status, tema, artigo{titulo,fonte,doi,url,abstract}, resumo, pdf_path, review_token, criado_em, decidido_em}`. `status ∈ {DRAFT, APPROVED, EDITED, SKIPPED, SENT}`.
- `/data/subscribers.json` — `[{id, nome, email, whatsapp, cpf, plano, status, asaas_id, secret_token, inicio, fim_periodo_pago, criado_em}]`. `status ∈ {ATIVO, PAUSADO, CANCELADO, INADIMPLENTE}`.
- `/data/config.json` — `{planos:[{chave, ciclo, preco}], temas:[...], schedule:{prep:"18:00", send:"08:00"}, reminder:{canal:"email", ligado:true}, brand:{...}}`.
- `/data/churn.json` — motivos de cancelamento coletados.
- `/data/delivery-log.jsonl` — log de entregas (quem, quando, status).

## 7. Motor de conteúdo

**Bancos (APIs públicas gratuitas):**
- **PubMed / NCBI E-utilities** (esearch + efetch).
- **Europe PMC** (REST; inclui Cochrane indexado e preprints).
- **ClinicalTrials.gov** (API v2).
- **medRxiv/bioRxiv** (API).
- *(Semantic Scholar como reforço opcional.)*

**Temas:** lista configurável em `config.json`, rotação diária. Dr. Diego edita a lista.

**Seleção do artigo:** filtra por recência (janela configurável), prioriza desenho forte (meta-análise, ensaio clínico randomizado), remove o que já foi enviado (dedupe pelo DOI/PMID), pega o melhor candidato. Se nada bom: notifica o curador ("sem artigo forte hoje") em vez de enviar algo fraco.

**Resumo (Claude, chave `DSCURSO_ANTHROPIC_KEY`):** prompt com estrutura fixa:
*Contexto · Método (desenho, nº de pacientes, população) · Achado principal (com os números) · Aplicação clínica · Limitações · Referência (DOI/link).*
Guardrails no prompt: **não inventar números** — usar só o que está no artigo; sinalizar incerteza; tom técnico para médicos; **sem conselho ao paciente**.

## 8. Geração de PDF

**Decisão:** o "PDF bonito" exige um renderizador — o app deixa de ser "só stdlib". PDF montado de **template HTML+CSS** (permite marca/beleza real) renderizado no container (WeasyPrint **ou** Chrome headless `--print-to-pdf`, a decidir no plano; o clinicdspro já usou Chrome headless). O `Dockerfile` ganha essa dependência via `apt-get`.

Layout: cabeçalho com a marca do Dr. Diego, selo do tema, título, seções estruturadas, números em destaque, rodapé com referência (DOI) e **nome do médico** (marca d'água anti-repasse) + link "Minha assinatura".

## 9. Fluxo de revisão (máquina de estado)

- **18h job:** monta candidato → salva `draft` com `status=DRAFT` e um `review_token` aleatório longo → envia WhatsApp ao curador com o link `/revisar/<token>`.
- **Página `/revisar/<token>`** (token do dia, sem senha; **PIN de 4 dígitos opcional**): mostra artigo+fonte, texto **editável**, prévia do PDF, botões: **Aprovar** / **Salvar edição** (regenera PDF) / **Gerar outra versão** (IA refaz) / **Não enviar hoje** (`SKIPPED`).
- **08h job:** se `status ≠ SKIPPED` → envia aos assinantes e marca `SENT`. Silêncio (ainda `DRAFT`) = aprovado.
- Barrar rápido por WhatsApp ("PULA") fica como reforço opcional (exige webhook de entrada do Z-API) — não bloqueia a Fase 1; o link já resolve.

## 10. Assinatura e cobrança (Asaas)

**Gateway:** Asaas (recorrência brasileira; **mensalidade zero**, paga-se só por cobrança recebida; webhooks de pagamento).

**Forma de pagamento principal = Pix Automático** (débito recorrente autorizado na conta do banco do médico), com **cartão como alternativa**. Motivos: **sem chargeback** (o débito é autorizado no app do banco), **MDR muito menor** (~0,4–1,2% vs 3–4,5% do cartão) e **maior taxa de sucesso de renovação** (conta bancária não vence/troca como cartão). Boleto/cartão ficam como fallback.

**Planos (4), todos recorrentes até cancelar — valores definidos pelo Dr. Diego, editáveis:**
| Chave | Ciclo Asaas |
|---|---|
| `mensal` | MONTHLY |
| `trimestral` | QUARTERLY |
| `semestral` | SEMIANNUALLY |
| `anual` | YEARLY |

**Fluxo:** landing → autocadastro (nome, e-mail, WhatsApp, CPF) → cria cliente+assinatura no Asaas no plano escolhido → checkout do Asaas → **webhook de pagamento confirmado** → assinante vira `ATIVO`, gera `secret_token`, entra na lista de envio, recebe boas-vindas.

**Webhooks tratados:** pagamento confirmado (ativa/renova), pagamento atrasado (`INADIMPLENTE`, sai do envio após carência), assinatura cancelada/estornada (`CANCELADO`).

## 11. Landing + autocadastro

Página pública de vendas (`/`): proposta de valor, amostra grátis de um resumo/PDF, os 4 planos com preço, e o formulário de autocadastro → checkout Asaas. Também um **"Já sou assinante"** que reenvia o link "Minha assinatura" por e-mail/WhatsApp.

## 12. Ciclo de vida do assinante

`novo → (paga) ATIVO → (atrasa) INADIMPLENTE → (não regulariza) CANCELADO`
`ATIVO → (pausa/cancela) PAUSADO/CANCELADO`. Só `ATIVO` (e `PAUSADO` até o fim do período) recebe envio. Ao cancelar, **mantém acesso até `fim_periodo_pago`** e só então sai.

## 13. Cancelamento + save flow

Página **"Minha assinatura"** por `secret_token` (link no rodapé de todo WhatsApp/PDF e reenviável na landing). Mostra plano, próxima cobrança e **"Cancelar assinatura"**.

Ao clicar em cancelar → tela **"Antes de cancelar"**:
1. Ofertas de retenção: **⏸️ pausar 1 mês** · **⬇️ trocar por plano mais barato** · **🎁 desconto de retenção**.
2. **Campo livre obrigatório**: "Nos explique por que está querendo desistir, para melhorarmos o produto." (salvo em `churn.json`).
3. Botão **Confirmar cancelamento** (continua acessível — nada de labirinto; cancelamento completa em seguida).
4. **Oferta final: +30 dias grátis** (pausa a cobrança por 30 dias). Se aceitar, `PAUSADO`, cobrança volta automática ao fim dos 30 dias.

**Aviso pré-cobrança (decisão do Dr. Diego):** ao voltar a cobrar após o mês grátis, o **canal e o liga/desliga são configuráveis** (`config.reminder`), **default = e-mail, ligado**. O "interruptor" fica pronto para trocar de estratégia (ex.: ligar aviso claro/WhatsApp) sem reengenharia caso apareça chargeback. *(Ver Riscos §22.)*

## 14. Entrega

`deliver.py` lê `subscribers.json` (só `ATIVO`/`PAUSADO`-em-período). Para cada um: envia WhatsApp com o texto + o **PDF personalizado com o nome** (Z-API), **espaçando** os envios (delay configurável) para reduzir risco de bloqueio. Registra em `delivery-log.jsonl`; falha em um assinante não derruba o lote (retry + log).

## 15. Agendamento

`scheduler.py` roda dois disparos diários em **America/Sao_Paulo**: **18:00** (preparar + notificar curador) e **08:00** (enviar). Implementado no loop do `serve.py` (como o robô atual) ou cron no container.

## 16. Configuração

`config.json` no volume, editável por uma **telinha admin** protegida (token/PIN): planos+preços, lista de temas, horários, `reminder{canal,ligado}`, delay de envio, marca do PDF. Preço muda sem tocar em código.

## 17. Segurança

- Sem segredos no repo — tudo por env var (`DSCURSO_ANTHROPIC_KEY`, `ZAPI_*`, `ASAAS_API_KEY`, `ASAAS_WEBHOOK_TOKEN`, admin token/PIN).
- Links secretos = tokens aleatórios longos; `review_token` expira no dia; `secret_token` do assinante é por-assinante.
- Webhook do Asaas valida token/assinatura.
- LGPD: guarda-se nome/e-mail/WhatsApp/CPF do médico com finalidade clara (assinatura); nunca logar CPF em claro.
- Isolamento absoluto do clinicdspro (outro projeto EasyPanel, sem acesso ao banco/dados de paciente).

## 18. Tratamento de erros

- Busca sem resultado bom → notifica curador, não envia.
- Claude falha → notifica curador, não envia rascunho ruim.
- Render de PDF falha → notifica curador, não envia.
- Envio Z-API falha por assinante → retry + log, segue o lote.
- Webhook duplicado (Asaas reenvia) → idempotência por id de evento.
- `entrypoint` já não derruba o container em falha de geração.

## 19. Testes

- Unit (pytest) das partes puras: parsing de cada fonte, dedupe, rotação de tema, seleção, aritmética de período, montagem do texto do PDF, roteamento de webhook (mapeia evento→estado).
- **Modo dry-run:** prepara o rascunho e envia **só para o número do curador**, sem tocar na lista.
- Teste manual de ponta a ponta com a lista-semente antes de abrir a landing.

## 20. Deploy (isolado)

Serviço EasyPanel novo `curso` (projeto próprio), source GitHub `DrDiegoSilva/curso-longevidade` branch `main`, build Dockerfile, porta 3000, volume `/data`, domínio `curso.drdiegosilva.com.br` (Let's Encrypt), DNS A `curso` → `187.77.58.74` (Cloudflare DNS-only). Env: `DSCURSO_ANTHROPIC_KEY`, `ZAPI_INSTANCE_ID/TOKEN/CLIENT_TOKEN/DESTINO`, `ASAAS_API_KEY`, `ASAAS_WEBHOOK_TOKEN`, admin token/PIN. (O deploy inicial estava pausado aguardando este design; sobe com a versão Fase 1.)

## 21. Fora de escopo (Fase 2+)

- Área de membros com login + biblioteca navegável do histórico.
- Personalização de temas por médico.
- Cupons/afiliados, período de teste gratuito na entrada, upsell de trilhas.
- Métricas/painel de churn e receita.

## 22. Riscos e decisões em aberto

- **Renderizador de PDF** (WeasyPrint × Chrome headless) — decidir no plano (peso da imagem × qualidade).
- **Chargeback / cobrança pós-mês-grátis:** com **Pix Automático como forma principal, o chargeback deixa de existir** (débito autorizado no banco) — o que dissolve boa parte desta preocupação. Para quem pagar via **cartão**: decisão do Dr. Diego = cobrança volta automática, aviso por **e-mail** (canal padrão de billing), claro e sem esconder; o aviso é **configurável** (canal/ligado). Compliance CDC/Decreto 11.034 sob decisão de negócio do titular.
- **"PULA" por WhatsApp** (webhook de entrada Z-API) — reforço opcional pós-Fase 1.
- **Escala de WhatsApp:** uma instância Z-API para muitos envios diários tem teto/risco de bloqueio; mitigado por throttle + PDF personalizado. Reavaliar se a base crescer.
- **Preços dos planos:** a definir pelo Dr. Diego (config, não código).
