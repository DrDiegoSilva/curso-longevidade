# Editar número + suporte internacional (seletor de país) — Design

**Data:** 2026-07-26 · **Host:** `artigos.` (assinatura) · Backlog item 19 (clientes fora do BR). Relacionado a [[projeto-c-conta-assinante]] (troca de nº por OTP) e ao [[guard-troca-slot]].
**Status:** Design aprovado (brainstorming) — aguardando revisão do spec.

## Problema

`phone.normalizar` prepend `55` em qualquer número de **10–11 dígitos** (assume BR sem país). Um número dos EUA com código do país (`1` + 10 = **11 dígitos**) colide com esse ramo e vira `55 1 …` (lixo). Roda no **cadastro E no envio** (dupla normalização via `subscribers._norm`), então o número internacional é corrompido nas duas pontas. O Diego já cadastrou o irmão (EUA) e o número está quebrado; não há como corrigir pelo fluxo de OTP (o código de troca vai pro número NOVO via WhatsApp, que não funciona enquanto estiver quebrado).

## Objetivo

Permitir número **internacional** (E.164) sem quebrar os números BR existentes, e dar ao **admin** um jeito de **editar o número** de um assinante na mão (com seletor de país), pra corrigir o irmão agora e outros casos no futuro.

## Decisões (Diego, 2026-07-26)

1. **Seletor de país** no modal de editar número: `[País ▼ (🇧🇷 Brasil +55, pré-selecionado)] [número local]`. O país fornece o código; junta com o local. Elimina a ambiguidade "+CC digitado na mão".
2. **Lista curada** (~20 países: BR default + EUA, Portugal, Reino Unido, Espanha, Argentina, Canadá, França, Alemanha, Itália, México, Chile, Colômbia, Paraguai, Uruguai, Japão, Austrália, Suíça, Holanda, Irlanda). Adicionar país = 1 linha.
3. **`normalizar` canônico e retrocompatível:** BR → dígitos `55…` (sem "+", igual ao legado); internacional → `+CC…` (mantém "+", idempotente); BR sem país (10–11 díg) → ganha `55` como hoje.
4. **Envio:** a camada da API manda **só dígitos** (tira o "+").
5. **Superfícies (3), via um widget reutilizável `_seletor_pais`:** (a) admin "Adicionar cortesia"; (b) admin **modal "Editar número"** (novo); (c) **signup público** (checkout `/assinar`). No público, **CPF continua obrigatório e o pagamento NÃO muda** — quem compra é brasileiro (tem CPF), podendo morar fora; o seletor é só pro **telefone**. Fuso do envio continua **BRT** (fora de escopo).
6. **Corrigir o irmão:** via o novo modal admin (escolhe 🇺🇸 EUA +1, digita o número) — sem OTP.
7. **Branch:** tudo em `feat/editar-numero-intl`. Toca `pagina_assinar` (checkout), que a `feat/landing-copy-pizza` também edita (copy/preço) → o controller reconcilia no merge (não é bloqueio; regiões próximas mas o seletor é aditivo).

## Arquitetura (por arquivo)

### 1. `app/phone.py` — normalização canônica + formato de API
```python
def normalizar(w):
    """Canônico: BR = dígitos '55…' (sem +, legado); internacional = '+CC…' (mantém +).
    Idempotente. BR sem país (10-11 díg) ganha 55."""
    w = (w or "").strip()
    intl = w.startswith("+")
    d = "".join(c for c in w if c.isdigit())
    if intl:
        return d if d.startswith("55") else "+" + d   # +55… -> BR dígitos (consistente); +1… -> mantém +
    if len(d) in (10, 11):
        return "55" + d
    return d

def para_api(w):
    """Formato que o WhatsApp aceita: só dígitos com código do país (sem +)."""
    return normalizar(w).lstrip("+")
```
- **Idempotência:** `normalizar("+13055551234")` → `"+13055551234"`; `normalizar("5511987654321")` → `"5511987654321"`. Dupla normalização (cadastro→envio) não corrompe.
- **Consistência BR:** BR sempre vira `55…` (com "+" ou sem, ou legado), então `por_whatsapp`/login/envio — que normalizam **os dois lados** — casam. Só o Brasil é `+55`; nenhum outro código começa com `55`, e número US começa com `1…` (o `startswith("55")` só pega BR).

### 2. `app/deliver.py` — usar `phone.para_api` no payload
- `_evolution_texto_payload`/`_evolution_media_payload` e o(s) payload(s) Z-API passam a montar o número com `phone.para_api(whatsapp)` (tira o "+"). BR não muda (`5511…`); internacional vira dígitos (`+1305…` → `13055551234`).

### 3. `app/paises.py` (novo) — lista curada
```python
# (codigo ISO, nome, bandeira emoji, dial). BR primeiro (default no seletor).
PAISES = [
    ("BR", "Brasil", "🇧🇷", "55"), ("US", "Estados Unidos", "🇺🇸", "1"),
    ("PT", "Portugal", "🇵🇹", "351"), ("GB", "Reino Unido", "🇬🇧", "44"),
    ("ES", "Espanha", "🇪🇸", "34"), ("AR", "Argentina", "🇦🇷", "54"),
    ("CA", "Canadá", "🇨🇦", "1"), ("FR", "França", "🇫🇷", "33"),
    ("DE", "Alemanha", "🇩🇪", "49"), ("IT", "Itália", "🇮🇹", "39"),
    ("MX", "México", "🇲🇽", "52"), ("CL", "Chile", "🇨🇱", "56"),
    ("CO", "Colômbia", "🇨🇴", "57"), ("PY", "Paraguai", "🇵🇾", "595"),
    ("UY", "Uruguai", "🇺🇾", "598"), ("JP", "Japão", "🇯🇵", "81"),
    ("AU", "Austrália", "🇦🇺", "61"), ("CH", "Suíça", "🇨🇭", "41"),
    ("NL", "Holanda", "🇳🇱", "31"), ("IE", "Irlanda", "🇮🇪", "353"),
]
```

### 4. `app/subscribers.py` — reusa `atualizar_whatsapp` (já existe)
- `atualizar_whatsapp(id, novo)` (linha 179) já faz `UPDATE ... SET whatsapp=_norm(novo)`. Com o `normalizar` novo, grava certo. Nada a mudar aqui além de confiar no `_norm`.

### 5. `app/phone.py` — helper de composição (reutilizável no servidor)
```python
def montar_e164(dial, local):
    """Junta código do país (do seletor) + número local -> '+<dial><digitos>'.
    Ex.: montar_e164('1', '(305) 555-1234') -> '+13055551234'."""
    d = "".join(c for c in (local or "") if c.isdigit())
    return "+" + "".join(c for c in (dial or "") if c.isdigit()) + d
```
(o `normalizar` depois canoniza: BR vira `55…`, internacional mantém `+…`.)

### 6. `app/site_web.py` — widget `_seletor_pais` + 3 superfícies
- **`_seletor_pais(selecionado="BR")`** (novo helper) → devolve o HTML de um `<select name="pais_dial">` com as opções de `paises.PAISES` (BR `selected`). **Uma peça, reutilizada nos 3 forms** (DRY), seguindo o estilo dos `<select>` que já existem no arquivo (ex.: o de "dias de acesso" do cupom).
- **(a) Adicionar cortesia** (admin, `acao=adicionar`): coloca o `_seletor_pais` antes do campo de número; label vira "WhatsApp" (o "(com DDD)" fica só quando BR).
- **(b) Modal "✏️ Editar número"** (admin, lista de assinantes, ao lado de "remover"): `_seletor_pais` + `<input name="numero">` + `token`/`id`/`acao=editar_numero`, no padrão dos modais admin existentes ([[feedback-nao-supor-landing]] — reusa o estilo, não inventa layout).
- **(c) Checkout público** (`pagina_assinar`, form `/assinar`): `_seletor_pais` ao lado do campo WhatsApp. **CPF e pagamento inalterados.** ⚠️ Mudança pequena e aditiva; o controller reconcilia com a `feat/landing-copy-pizza` no merge.

### 7. `app/serve.py` — servidor combina país + local nos 3 handlers
- Todos usam `phone.montar_e164(g("pais_dial"), g("numero"|"whatsapp"))` e seguem pro fluxo existente:
  - **cortesia** (`acao=adicionar`): `subscribers.adicionar(g("nome"), phone.montar_e164(...))`.
  - **editar_numero** (admin, novo, junto de `remover`/`remover_confirmar`, mesma auth token/sessão-admin, sem OTP):
    ```python
    elif acao == "editar_numero":
        novo = phone.montar_e164(g("pais_dial"), g("numero"))
        outro = subscribers.por_whatsapp(novo)
        if outro and outro["id"] != g("id"):
            msg = "Esse número já é de outro assinante."
        else:
            subscribers.atualizar_whatsapp(g("id"), novo); msg = "Número atualizado."
    ```
  - **checkout** (`_post_assinar`): `dados["whatsapp"] = phone.montar_e164(g("pais_dial"), g("whatsapp"))` (CPF/plano/pagamento iguais).
- Compat: se `pais_dial` vier vazio (form antigo/cache), cair no default BR (`"55"`) pra não regredir.

## Comportamento (matriz)

| Entrada (país + local) | Guardado | Enviado à API |
|---|---|---|
| 🇧🇷 Brasil + `11987654321` | `5511987654321` | `5511987654321` |
| 🇺🇸 EUA + `3055551234` | `+13055551234` | `13055551234` |
| 🇵🇹 Portugal + `912345678` | `+351912345678` | `351912345678` |
| Legado BR (já `5511…`) | inalterado | `5511…` (via para_api) |

## Erros & bordas
- **Só o Brasil é `+55`** e US começa com `1…`; o `startswith("55")` no ramo internacional só canoniza BR → sem falso-positivo com a lista curada.
- **Colisão de número:** admin edit checa `por_whatsapp` (não sobrescreve número de outro assinante).
- **Login do irmão:** ele loga com o número; `auth_web` normaliza → `+1305…` dos dois lados → casa.
- **Números BR existentes:** intocados (continuam `55…`); `para_api` no envio não muda nada pra eles.
- **`atualizar_whatsapp` do fluxo OTP** (/meus-dados) segue funcionando (BR → `55…`, consistente).

## Testes (unittest, `cd app && python3 -m unittest discover -s tests`)
- **`test_phone`:** `normalizar` — BR sem país→`55…`; BR `+55…`→`55…`; US `+1…`→`+1305…` (não vira `551…`); idempotência (normalizar 2x = igual); `para_api` tira o "+"; `montar_e164('1','(305) 555-1234')`→`+13055551234` e `montar_e164('55','43 99999-0000')`→normaliza p/ BR. Guard: US 11 díg **com** "+" nunca ganha `55`.
- **`deliver`:** payload usa `para_api` (número sem "+"); BR inalterado.
- **`serve`:** `editar_numero` monta via `montar_e164`, chama `atualizar_whatsapp`; colisão com outro assinante → msg de erro, não atualiza; auth admin exigida. `_post_assinar` monta o whatsapp com país+local (CPF/plano intactos). `pais_dial` vazio → default BR.
- **`site_web`:** `_seletor_pais()` renderiza as opções com BR `selected`; presente nos 3 forms (cortesia, editar número, checkout).
- **Regressão:** testes atuais de `phone`/`subscribers`/`troca_numero`/checkout continuam passando (BR intocado).

## Fora de escopo (YAGNI)
- **Mudar CPF/pagamento** — seguem obrigatórios (quem compra é brasileiro, com CPF); o seletor é só do telefone.
- **Fuso horário** do envio por assinante (continua BRT).
- **Lista completa de países** (curada resolve; adicionar é 1 linha).
- **OTP no admin edit** (é admin de confiança; sem código).
