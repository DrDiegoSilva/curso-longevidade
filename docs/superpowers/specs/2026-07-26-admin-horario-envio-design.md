# Admin: ver/trocar horário de envio (slot) — Design

**Data:** 2026-07-26
**Status:** aprovado (brainstorming) → aguardando plano
**Branch:** feat/admin-horario (base a884aa1 = main após login-cpf)
**Backlog:** item 18

## Objetivo

Dar ao admin, na tela de **Assinantes**, a capacidade de **ver** a distribuição de assinantes por horário de envio (slot) e **trocar** o horário de um assinante específico.

### Decisões (do brainstorming)

- **Formato:** coluna "Horário" por linha na tabela (dropdown p/ trocar) + um **resumo** de quantos assinantes por horário no topo. Nada de tela separada.
- **Teto:** o admin **fura o teto** por slot — o dropdown oferece **todos** os `config.SLOTS`; `subscribers.definir_slot` já valida só que o slot ∈ SLOTS (não checa teto). O assinante em `/meus-dados` continua limitado pelo teto.
- **Catch-up:** ao mover pra um horário que **já disparou hoje**, reusa `daily.enviar_catch_up(sub)` — que **só envia se o assinante ainda não recebeu hoje** (claim atômico em `envios_dia` via `db.registrar_envio_assinante`). Ou seja: quem veio de um horário mais pra frente (ainda não recebeu) recebe o estudo na hora; quem já recebeu hoje não recebe de novo. Comportamento idêntico ao `/meus-dados`.

## Não-objetivos (YAGNI)

- Não criar tela separada agrupada por horário.
- Não mexer no `/meus-dados` do assinante, no teto, nem em `subscribers.definir_slot`/`daily.enviar_catch_up`.
- Não adicionar filtro/ordenação por horário (só o resumo + a coluna).

## Componentes

### 1. UI — `site_web.pagina_admin`

Assinatura ganha `contagem_slots=None` (default → resumo não renderiza; backward-compat):

```
def pagina_admin(assinantes, token="", cupons=None, confirmar_id=None, erro="",
                 reenviar_id=None, sucesso="", contagem_slots=None):
```

- **Resumo** (quando `contagem_slots`): uma linha no topo (perto do `len/ativos/curadores`), tipo:
  `Envio por horário — 07h: 0 · 08h: 12 · 12h: 3 · 18h: 1 · 20h: 4` (na ordem de `config.SLOTS`).
- **Coluna "Horário"** por linha (nova `cel_horario(s)`): `<select name="slot">` com **todos** os `config.SLOTS`, com o atual (`subscribers.slot_de(s)`, import lazy) pré-selecionado, + hidden `token`/`acao=definir_slot`/`id`, + botão "Salvar". Mesmo padrão visual das outras células de ação.
- Novo `<th>Horário</th>` no `<thead>` (antes do `<th></th>` final, depois de "Boas-vindas") e `colspan` do estado vazio de **10 → 11**.
- Feedback de sucesso reusa o `sucesso`/`sucesso_html` já existente.

### 2. GET `/admin` (`serve.py`)

Passar a contagem ao render:
```python
..., sucesso=q.get("sucesso", [""])[0],
contagem_slots=subscribers.contar_por_slot()), 200)
```

### 3. POST `/admin` (`serve.py`) — `acao=definir_slot`

Dentro do dispatcher `/admin` (já admin-gated), novo branch:
```python
elif acao == "definir_slot":
    import daily as _daily
    sub = subscribers.por_id(g("id"))
    if not sub:
        erro = up.quote("Assinante não encontrado.")
        return self._redirect(f"/admin?token={config.ADMIN_TOKEN}&erro={erro}"
                              if token_ok else f"/admin?erro={erro}")
    novo = g("slot")
    subscribers.definir_slot(sub["id"], novo)   # valida ∈ SLOTS; SEM teto (admin fura)
    if novo in config.SLOTS and db.slot_ja_enviou(_daily._hoje_iso(), novo):
        try:
            _daily.enviar_catch_up(subscribers.por_id(sub["id"]))
        except Exception as e:
            print(f"[admin] catch-up de slot falhou: {e}", flush=True)  # não derruba a página
    msg = up.quote("✅ Horário atualizado.")
    return self._redirect(f"/admin?token={config.ADMIN_TOKEN}&sucesso={msg}"
                          if token_ok else f"/admin?sucesso={msg}")
```
`config`, `subscribers`, `db`, `up` já estão no escopo do bloco `/admin` (import na entrada do handler). `daily` é import lazy.

## Segurança / correção

- Rota `/admin` já é admin-only (token/sessão). Nenhuma nova superfície de auth.
- `definir_slot` ignora silenciosamente slot inválido; como o `<select>` só oferece `config.SLOTS`, o caminho normal é sempre válido. O gate `novo in config.SLOTS` evita catch-up com valor inválido.
- **Sem duplo envio:** o catch-up passa pelo claim `envios_dia` por assinante — quem já recebeu hoje não recebe de novo; se mover pra um slot futuro, o `enviar_slot` daquele slot também respeita o claim. (Guard `envios_dia` já existente.)
- `contar_por_slot`/`slot_de` são as funções canônicas (DRY) — sem reimplementar contagem/resolução no render.

## Testes (unittest standalone, padrão do `test_admin_reenviar_ui`)

`app/tests/test_admin_horario_ui.py`:
- `pagina_admin([sub], contagem_slots={...})` renderiza a coluna com `name="acao" value="definir_slot"`, um `<option value="07h"` (todos os slots) e o atual selecionado (`<option value="12h" selected` p/ um sub com `slot_envio="12h"`).
- Resumo renderiza a contagem por horário (ex.: contém `08h: 12`).
- Sub sem `slot_envio` → o `<option>` do `config.SLOT_DEFAULT` (08h) vem selecionado.

(O `definir_slot` e o `enviar_catch_up` já têm cobertura; o handler `/admin` é glue fino sem harness HTTP, como os demais — verificação por suíte + `import serve` + smoke manual.)

## Critérios de aceite

- [ ] Resumo "Envio por horário" aparece no topo de Assinantes com a contagem correta.
- [ ] Cada linha mostra o horário atual num `<select>` com os 5 slots; trocar + Salvar grava.
- [ ] Admin move pra qualquer slot (fura o teto); ao mover pra slot já disparado hoje, o assinante que ainda não recebeu recebe na hora (catch-up), e quem já recebeu não recebe de novo.
- [ ] Login/tabela existentes inalterados fora a coluna + resumo novos; testes novos passam; suíte verde.

## Arquivos

- `app/site_web.py` — `pagina_admin` (param `contagem_slots`, resumo, coluna, header, colspan).
- `app/serve.py` — GET passa `contagem_slots`; POST ganha `acao=definir_slot`.
- `app/tests/test_admin_horario_ui.py` — novo.
