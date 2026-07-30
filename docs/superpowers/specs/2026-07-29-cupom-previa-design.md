# Prévia do cupom no /assinar + limite de tentativas — design

**Data:** 2026-07-29 · **Aprovado pelo Diego** (chat, 2026-07-29).

## Problema

Duas coisas, e a segunda é mais séria que o pedido.

**1. Pedido do Diego:** hoje o `/assinar` mostra o preço cheio (R$1.497) e o desconto do cupom só aparece no Asaas, depois do redirect. Ele quer digitar o cupom, aplicar, e ver o valor novo na própria tela.

**2. Achado ao investigar:** o campo de cupom é um oráculo de códigos, **já hoje**, antes de qualquer mudança. Dá pra chutar códigos no POST do `/assinar` sem limite nenhum. E o prêmio não é desconto: cupom de **cortesia** (`desconto_valor == 0`) cria assinante `ATIVO` na hora, **sem passar pelo Asaas** (`serve.py:1356`) — acesso ao produto de graça. Os códigos existentes eram palavras de dicionário (`DIEGO2026` = nome + ano; `LANCAMENTO`), e o seed marca os do env como **multiuso**, então quem descobrisse ganhava acesso ilimitado, não um.

O Diego desativou o `DIEGO2026` durante esta sessão (usando o botão de [[cupom-liga-desliga]]). O limite de tentativas cobre o resto.

## Decisões (aprovadas)

**A prévia NUNCA aplica desconto.** O endpoint só devolve o que mostrar. O valor cobrado continua sendo calculado no servidor no fechamento. JavaScript adulterado muda só a tela do próprio visitante, nunca o preço cobrado.

**A prévia reusa `pricing.base_cobrada`** — a mesma função do fechamento, não uma cópia. Tela e cobrança não podem divergir por drift.

**Cortesia fora da prévia; erro genérico; escopo por plano** — os três caem de graça de `db.cupom_desconto(codigo, plano_slug)` (db.py:680), que devolve `0.0` para código inexistente, inativo, cortesia (desconto ≤ 0) **e** escopo que não casa. Um único caminho de falha, indistinguível de fora. Nenhum código especial, nenhum `if` novo por caso.

Consequências que o Diego aceitou explicitamente:
- Quem recebeu **cortesia** da mão dele digita o código e lê "inválido" — mas o código **continua funcionando** no fechamento. Evita que a prévia vire detector de jackpot ("achei o que dá R$0").
- Quem digita um cupom de outro plano (`LANCAMENTO` no mensal) lê "inválido" sem saber por quê. Compensado por um aviso fixo sob o campo: alguns cupons valem só para um plano.

**Limite por IP, em memória do processo.** 5 tentativas por 10 min, depois recusa. Serve porque o serviço roda com **uma** instância (`deploy.replicas: 1`). ⚠️ Se um dia virar duas, o limite passa a ser por instância e afrouxa proporcionalmente — registrar no backlog, não resolver agora (o repo não tem Redis nem store compartilhado).

O limite vale para **os dois** caminhos: o endpoint novo e o POST `/assinar` que já está no ar sem proteção.

## Interface

**`POST /assinar/cupom`** (admin-livre, é público — é a página de vendas) recebe `plano`, `metodo`, `parcelas`, `cupom`; devolve JSON:

```json
{"ok": true,  "preco": "R$ 997", "parcelas": [{"parcelas":12,"por_parcela":"R$ 83","total":"R$ 997"}], "msg": "−R$ 500 aplicado"}
{"ok": false, "msg": "Cupom inválido."}
{"ok": false, "msg": "Muitas tentativas. Tente de novo em alguns minutos.", "bloqueado": true}
```

`serve.py` **não tem helper de JSON hoje** — criar um (`_json(obj, code=200)`), no mesmo formato do `_html`.

**Na tela:** o campo de cupom ganha um botão "Aplicar" ao lado. Ao aplicar, atualiza **dois** lugares — o valor grande do resumo (`.sum-price`) **e** as opções do dropdown de parcelas, que vêm de `pricing.opcoes_parcelas`. Atualizar só um deixaria "R$ 997" em cima e "12x de R$ 124" embaixo.

**JS inline**, sem build step, seguindo o que o arquivo já faz (o `_varredura` usa JS inline). Sem dependência externa (a CSP do projeto não permitiria).

**Degradação sem JS:** o campo continua funcionando como hoje — digita o cupom, fecha a compra, o desconto é aplicado no servidor. O botão Aplicar é conveniência, não requisito.

## Limite de tentativas — comportamento

Contagem por IP (`X-Forwarded-For` primeiro, senão `client_address`, igual `serve.py:1336`). Estrutura em memória protegida por lock (o servidor é `ThreadingHTTPServer` — sem lock, duas threads corrompem a contagem). Precisa de **evicção**: sem ela o dict cresce sem limite com IP de bot e vira vazamento de memória.

Só conta tentativa **falha**. Cupom válido não gasta cota — quem tem cupom bom não é punido por conferir.

## Fora de escopo

- Store compartilhado de rate limit (Redis) — anotado, uma instância hoje.
- Mudar como o desconto é calculado ou cobrado.
- Mexer no caminho de cortesia (só passa a contar tentativa).
- CAPTCHA.
- Prévia do desconto Pix separada — `base_cobrada` já empilha o Pix quando o método é Pix, então a prévia reflete o método escolhido sem código extra.

## Testes

- cupom válido no plano certo → `ok`, preço e parcelas com desconto, **calculados por `base_cobrada`** (não por aritmética duplicada no teste)
- cupom de **cortesia** → `ok: false` genérico (não vaza o jackpot) **e** segue funcionando no POST do fechamento
- cupom de outro plano → `ok: false` genérico
- código inexistente → `ok: false` genérico, **mensagem idêntica** aos dois de cima (é o ponto: indistinguível)
- cupom desativado no `/admin` → `ok: false`
- 6ª tentativa falha no mesmo IP → bloqueado; tentativa **válida** não gasta cota
- o limite também barra o POST `/assinar` (o caminho antigo)
- a prévia **não** altera nada no banco (nem consome cupom, nem cria assinante)
- evicção: o dict não cresce indefinidamente
- concorrência: contagem sob lock não se corrompe

Cada correção provada por mutação.
