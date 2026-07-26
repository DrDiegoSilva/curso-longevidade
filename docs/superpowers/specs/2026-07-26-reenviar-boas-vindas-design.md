# Reenviar boas-vindas (WhatsApp) no admin de Assinantes

**Data:** 2026-07-26
**Status:** aprovado (brainstorming) → aguardando plano de implementação

## Objetivo

Na tabela de **Assinantes** do admin, oferecer um botão por linha que **reenvia a mensagem de boas-vindas do WhatsApp** para aquele assinante, com um **link novo de criar-senha** (token de 1º acesso, 7 dias). O botão pede **confirmação** antes de disparar e mostra o **resultado** (✅ enviado / ❌ motivo).

Uso imediato: testar o fluxo de boas-vindas com o Gleidson sem depender de um novo pagamento no Asaas.

### Decisões (do brainstorming)

- **Canal:** somente WhatsApp. **Não** dispara e-mail.
- **UX:** clique → confirmação → envia (mesmo padrão do "remover").
- **Conteúdo:** mesma mensagem editável do admin (`mensagens.wa_boas_vindas`), com link novo de criar-senha (7 dias).

## Não-objetivos (YAGNI)

- Não reenviar e-mail de boas-vindas.
- Não criar envio em lote / "reenviar para todos".
- Não alterar o fluxo automático do webhook (`webhook_asaas._boas_vindas`) — ele continua igual (WhatsApp + e-mail).
- Não mexer nos templates das mensagens.

## Componentes

### 1. `auth_web.reenviar_boas_vindas_wa(assinante, enviar_fn=None) -> tuple[bool, str]`

Nova função. Mora em `auth_web` porque ele já é dono de `preparar_primeiro_acesso`.

Comportamento:

1. Lê `whatsapp = assinante.get("whatsapp")`. Se vazio → retorna `(False, "assinante sem WhatsApp")`.
2. Gera link novo: `link = preparar_primeiro_acesso(whatsapp)` (token de 1º acesso, `FIRST_ACCESS_TTL_H` = 7 dias).
3. Monta o texto: `texto = mensagens.wa_boas_vindas(link, assinante.get("nome", ""))`.
4. Envia: `(enviar_fn or deliver.enviar_texto)(whatsapp, texto)`.
5. Sucesso (sem exceção) → `(True, "")`. Exceção (link ou envio) → loga `[reenviar]` no servidor e retorna `(False, str(e))`.

Notas:
- **Só WhatsApp** — nenhuma importação/chamada de `email_send`.
- Não reaproveita `webhook_asaas._boas_vindas` porque aquele faz e-mail também e engole os erros por canal; aqui precisamos de canal único + retorno de sucesso/falha para dar feedback ao admin.
- `enviar_fn` injetável mantém a função testável sem rede (padrão já usado em `deliver.distribuir` e no `_boas_vindas` do webhook).

### 2. UI — `site_web.pagina_admin(...)`

Assinatura passa a aceitar dois parâmetros novos (com default), preservando os existentes:

```
def pagina_admin(assinantes, token="", cupons=None, confirmar_id=None, erro="",
                 reenviar_id=None, sucesso=""):
```

Mudanças:

- **Botão na linha** (nova célula compacta, padrão `actbtn ghost`): form POST `/admin` com `acao=reenviar` + `token` + `id`. Rótulo: `📨 Reenviar`. Adiciona a coluna correspondente no `<thead>` (ex.: "Boas-vindas") e ajusta o `colspan` da linha "Nenhum assinante ainda." (hoje 9).
- **Caixa de confirmação** (espelha a de remoção, `confirm_html`): quando `reenviar_id` casa com um assinante da lista, renderiza um bloco com o nome + número e dois botões:
  - **Confirmar** → form `acao=reenviar_confirmar` + `token` + `id`.
  - **Cancelar** → link de volta para `/admin` (mantendo `token`).
- **Feedback de sucesso** (novo `sucesso_html`, verde, espelhando `erro_html`): renderizado no topo quando `sucesso` presente.

### 3. Handler — `serve.py`, dispatcher do POST `/admin`

Dentro do bloco `if path == "/admin"` (que já valida admin por token/sessão):

- `elif acao == "reenviar":` → redirect para `/admin?...&reenviar=<id>` (mantendo `token` quando `token_ok`), mostrando a confirmação. Espelha o `acao == "remover"`.
- `elif acao == "reenviar_confirmar":`
  1. `sub = subscribers.por_id(g("id"))`. Se não existir → redirect com `erro`.
  2. `ok, detalhe = auth_web.reenviar_boas_vindas_wa(sub)`.
  3. Redirect com `sucesso=✅ Boas-vindas reenviadas` (se `ok`) ou `erro=❌ Falha ao reenviar: <detalhe>` (caso contrário). Usa `up.quote` como as outras mensagens.

### 4. GET `/admin` — passar os params novos

No render (`serve.py:220-223`), passar também:

```
reenviar_id=q.get("reenviar", [""])[0] or None,
sucesso=q.get("sucesso", [""])[0],
```

## Tratamento de erros

- Falha de envio no WhatsApp **não é engolida**: vira `❌` visível pro admin com o motivo.
- Assinante sem WhatsApp → `❌ assinante sem WhatsApp` (não tenta enviar).
- Assinante inexistente (id inválido no confirmar) → `erro` no redirect.

## Segurança

- Rota `/admin` já é admin-only (token de admin **ou** sessão de admin) — nenhuma nova superfície de auth.
- A confirmação evita clique acidental que dispararia mensagem real a um terceiro.
- O link é o mesmo token single-purpose de 1º acesso (7 dias) já usado pelo webhook; cada reenvio gera um token novo.

## Testes (unittest standalone, padrão `test_mensagens` / `test_webhook`)

`app/tests/test_reenviar_boas_vindas.py`:

1. **sucesso:** `enviar_fn` falso registra `(whatsapp, texto)`; retorna `(True, "")`; o texto contém o link de criar-senha; garante que **nenhum e-mail** foi enviado (nenhuma chamada a `email_send`).
2. **falha de envio:** `enviar_fn` levanta exceção → retorna `(False, <motivo>)`.
3. **sem whatsapp:** assinante sem número → `(False, ...)` e `enviar_fn` não é chamado.

## Critérios de aceite

- [ ] Botão `📨 Reenviar` aparece por linha na tabela de Assinantes.
- [ ] Clicar mostra a confirmação com nome + número; Cancelar volta sem enviar.
- [ ] Confirmar dispara **só** o WhatsApp com link novo de criar-senha e volta com ✅/❌ visível.
- [ ] `webhook_asaas._boas_vindas` (fluxo automático) permanece inalterado.
- [ ] Testes novos passam; suíte existente segue verde.
