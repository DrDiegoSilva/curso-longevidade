# Aviso quando a troca do estudo de amanhã termina — design

**Data:** 2026-08-26
**Status:** spec aprovada no brainstorm, aguardando plano de implementação

## O problema

Item 43 (parte A) do backlog. Depois de escolher um estudo novo no picker do 🔁
(`/revisar/<tok>` → "trocar" → escolher → `trocar_confirmar`), o servidor sobe uma thread
em background (`daily.trocar_estudo_amanha`) e devolve na hora `review_web.pagina_trocando()`
— uma página **100% estática**, sem JS, sem polling, sem redirect. O texto diz literalmente
"pode fechar esta página", mas quem fica na aba não tem nenhum sinal de quando terminou.

O aviso "de verdade" hoje só chega por outro canal, o WhatsApp (`deliver.enviar_curador`),
tanto no sucesso (link novo de revisão) quanto na falha. Achado no brainstorm: se o Diego
recarregar a URL antiga (`/revisar/<token-antigo>`) depois que a troca dá certo, cai num
beco sem saída — **"Link inválido/expirado" (404)** — porque `trocar_estudo_amanha` sobrescreve
o registro do dia com um token novo (`daily_drafts` é upsert por `data`, `ON CONFLICT(data) DO
UPDATE ... review_token=excluded.review_token`), e o token antigo para de casar com qualquer
linha.

Decisão do Diego: quer que a **própria tela** avise quando terminar (sucesso com link novo,
ou erro), sem precisar checar o WhatsApp. O WhatsApp continua chegando do jeito que está hoje,
como rede de segurança (caso ele feche a aba antes de terminar).

## O que muda

- `pagina_trocando()` ganha um `<script>` que pergunta pro servidor a cada ~3s se a troca já
  terminou, e atualiza a própria página quando souber — sem barra de progresso falsa, só os
  estados que a página realmente sabe (mesmo espírito honesto do painel de upload do item 34,
  `ui.progresso_upload`).
- Sem JS (desligado, navegador exótico): a página cai pro texto estático de hoje. Nunca quebra.
- Novo endpoint só-leitura, `GET /revisar-status`, que resolve o estado atual da troca.
- Novo campo no payload do rascunho, `erro_troca`, pra guardar a mensagem de erro (ou vazio) —
  sem tabela nova, sem estado em memória.

## Onde mora o estado da troca

Reaproveita o registro do rascunho de amanhã que já existe em `daily_drafts` (via
`draft_store`/`db.py`), sem criar tabela nem dicionário em memória — sobrevive a um reinício do
servidor no meio da espera (o WhatsApp seria o único aviso nesse caso raro; a tela nunca finge
saber o que não sabe, só continua "andamento").

Estados possíveis pro token **antigo** (o da página `pagina_trocando()`):

| Estado | Como é detectado |
|---|---|
| **andamento** | O rascunho ainda existe com esse token, e `erro_troca` está vazio. |
| **erro** | O rascunho ainda existe com esse token, e `erro_troca` tem uma mensagem. |
| **pronto** | O rascunho **não existe mais** com esse token — foi sobrescrito pelo novo (mesmo mecanismo que já causa o 404 hoje). |

`trocar_confirmar` (em `serve.py`), antes de subir a thread, limpa `erro_troca` no rascunho
atual — garante que um erro de uma tentativa de troca anterior não "vaze" pra uma tentativa
nova feita em cima do mesmo token:

```python
if g("acao") == "trocar_confirmar":
    import daily, threading
    tipo, cid = g("tipo"), g("id")
    if not daily.alternativa_valida(r, tipo, cid):
        return self._html(review_web.pagina_revisao(
            r, aviso="Esse estudo saiu da lista — escolha outro.",
            audio_on=config.audio_ligado(), areas=areas))
    r["erro_troca"] = ""
    draft_store.salvar(r)
    threading.Thread(target=daily.trocar_estudo_amanha,
                     args=(tok, tipo, cid), daemon=True).start()
    return self._html(review_web.pagina_trocando(tok, r["data"]))
```

`daily.trocar_estudo_amanha` passa a gravar a mensagem de erro no MESMO registro (token
antigo) nos dois pontos de falha, além de continuar mandando pro WhatsApp como já faz hoje:

```python
def trocar_estudo_amanha(token, tipo, cid):
    import db
    r = draft_store.por_token(token)
    if not r:
        deliver.enviar_curador("⚠️ Não consegui trocar o estudo (rascunho não encontrado).")
        return None
    try:
        novo = _preparar_da_reserva(reserva_id=cid) if tipo == "reserva" else (
               _preparar_de_candidato(cid) if tipo == "candidato" else None)
    except Exception as e:
        print(f"[trocar] preparo do escolhido falhou: {e}", flush=True)
        novo = None
    if not novo:
        msg = "Não consegui trocar o estudo; o anterior segue valendo."
        r["erro_troca"] = msg
        draft_store.salvar(r)
        deliver.enviar_curador(f"⚠️ {msg}")
        return None
    ...   # resto igual (agenda_upsert, marcar_*_agendado, devolver o atual ao pool)
```

## O endpoint de status

`GET /revisar-status?token=<token-antigo>&data=<data-de-amanhã>` — caminho separado (não
`/revisar/status`) pra não colidir com a rota existente que trata tudo depois de `/revisar/`
como token.

```python
if path == "/revisar-status":
    import draft_store
    q = up.parse_qs(up.urlparse(self.path).query)
    tok = (q.get("token") or [""])[0]
    data = (q.get("data") or [""])[0]
    r = draft_store.por_token(tok)
    if r:
        erro = r.get("erro_troca")
        if erro:
            return self._json({"status": "erro", "msg": erro, "voltar": f"/revisar/{tok}"})
        return self._json({"status": "andamento"})
    atual = draft_store.carregar(data) if data else None
    if atual and atual.get("review_token") and atual["review_token"] != tok:
        return self._json({"status": "pronto", "link": f"/revisar/{atual['review_token']}"})
    return self._json({"status": "andamento"})     # nunca 500, pior caso é ficar esperando
```

Reaproveita `draft_store.por_token` e `draft_store.carregar` (já existem) e `self._json` (já
existe, usado no webhook do Asaas). Nenhuma tabela nova.

O `data` viaja desde `pagina_trocando()` porque, uma vez que o token antigo some (caso
"pronto"), só a data permite achar o registro novo — o token sozinho não basta.

## A página e o JavaScript

`pagina_trocando(token, data)` passa a receber os dois parâmetros e embute um `<div>` com os
dados em atributos + um `<script>` no mesmo estilo testável do item 34 (extraído da página e
testado com um shim de DOM em `node` — nunca uma cópia colada em `tests/`).

```python
def pagina_trocando(token, data):
    import html as _html
    esc = _html.escape
    return f"""<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<body style="font-family:system-ui;max-width:600px;margin:40px auto;padding:0 16px;color:#1a2b28">
<h3>🔄 Trocando…</h3>
<div id="troca-status" data-token="{esc(token)}" data-data="{esc(data)}">
  <p><span class="troca-espera">O novo resumo está sendo gerado. Em ~1-2 min você recebe no
  WhatsApp o estudo novo (com PDF, áudio e um link de revisão novo). Pode fechar esta
  página.</span></p>
</div>
<script>
(function(){{
  var el = document.getElementById('troca-status');
  if (!el || !window.fetch) return;         // sem markup/fetch: fica no texto estático
  var token = el.getAttribute('data-token'), data = el.getAttribute('data-data');
  if (!token || !data) return;
  var t0 = Date.now(), timer = setInterval(consultar, 3000);
  function consultar(){{
    fetch('/revisar-status?token=' + encodeURIComponent(token) + '&data=' + encodeURIComponent(data))
      .then(function(r){{ return r.json(); }})
      .then(tratar)
      .catch(function(){{}});               // falha de rede pontual: tenta de novo no próximo ciclo
  }}
  function tratar(j){{
    if (j.status === 'pronto'){{
      clearInterval(timer);
      el.innerHTML = '<b>✅ Troca concluída!</b><br><a href="' + j.link + '">Ver a revisão nova</a>';
    }} else if (j.status === 'erro'){{
      clearInterval(timer);
      el.innerHTML = '<b>⚠️ ' + j.msg + '</b><br><a href="' + j.voltar + '">← Voltar pra revisão</a>';
    }} else if (Date.now() - t0 > 75000){{
      var esp = el.querySelector('.troca-espera');
      if (esp) esp.textContent = 'Ainda trabalhando nisso — mais que o esperado. O aviso ' +
        'também chega no seu WhatsApp assim que terminar.';
    }}
  }}
  consultar();
}})();
</script>
</body>"""
```

Notas de design:

- `j.msg` e `j.link`/`j.voltar` entram via `innerHTML` — vêm do próprio servidor (mensagens
  fixas de erro já usadas hoje no WhatsApp, e links montados a partir de tokens gerados por
  `secrets.token_urlsafe`), não de entrada do usuário; sem risco de XSS novo.
- Limiar de demora igual ao item 34 (75s, `ui._DEMORA_LONGA`) — mesmo texto honesto, sem
  prometer prazo que não cumpre.
- `serve.py` precisa passar a chamar `review_web.pagina_trocando(tok, r["data"])` em vez de
  `review_web.pagina_trocando()` (hoje sem argumentos).

## Erros e casos de borda

- **Token inválido/forjado em `/revisar-status`**: cai no "andamento" (não vaza detalhe
  interno, não devolve 500). Pior caso é a tela ficar esperando pra sempre — seguro.
- **Trocar de novo enquanto a troca anterior ainda está "andamento"**: não é bloqueado hoje
  (fora do escopo deste item); o novo pedido limpa `erro_troca` de novo e passa a valer,
  comportamento consistente com o que já existe.
- **Reinício do servidor no meio da espera**: a thread morre junto; a aba aberta consulta pra
  sempre "andamento" (nunca inventa sucesso nem erro). O estudo de amanhã já tinha um
  "anterior" válido antes da troca — nada quebra pro assinante. Ponto cego aceito (processo
  único, raro coincidir com o reinício).
- **Erro de rede pontual no `fetch`**: ignora e tenta de novo no próximo ciclo de 3s, sem
  mostrar erro por causa de uma falha passageira.

## Onde mexe

| Arquivo | O quê |
|---|---|
| `app/serve.py` | `trocar_confirmar` limpa `erro_troca` antes de subir a thread e passa `(tok, r["data"])` pra `pagina_trocando`; novo branch `GET /revisar-status` |
| `app/daily.py` | `trocar_estudo_amanha` grava `erro_troca` no rascunho nos dois pontos de falha |
| `app/review_web.py` | `pagina_trocando` ganha os parâmetros `token`/`data`, o painel e o `<script>` |

`app/db.py`, `app/draft_store.py` não são tocados — `erro_troca` é só mais um campo dentro do
payload JSON já existente, sem migração.

## Testes

Mesmo padrão do item 34 (`tests/test_upload_progresso.py`):

- **Backend**: `/revisar-status` cobrindo os três estados (andamento/pronto/erro) e token
  inválido; `trocar_confirmar` limpa `erro_troca` de uma tentativa anterior antes de subir a
  thread nova; `trocar_estudo_amanha` grava `erro_troca` nos dois caminhos de falha (rascunho
  não encontrado, preparo do escolhido falhou) sem deixar de mandar o WhatsApp.
- **Componente/markup**: `pagina_trocando` traz os `id`/`data-*` que o JS procura; sem
  JS/fetch o texto estático de hoje continua presente.
- **JS extraído** (roda em `node` sobre shim de DOM, pulado se `node` não estiver no PATH):
  transição pra "pronto" mostra o link; transição pra "erro" mostra a mensagem + link de
  volta; aviso de demora aparece depois de 75s ainda em "andamento"; falha de rede no fetch
  não trava nem mostra erro, só tenta de novo.

## Fora de escopo

- Redesign do layout do picker do 🔁 (item 43 parte B) — fica pra depois, brainstorm
  separado.
- Bloquear uma segunda troca enquanto a primeira ainda está em andamento.
- Mudar o texto ou o conteúdo do aviso que já vai pro WhatsApp — decisão do Diego, mantém
  como está.
