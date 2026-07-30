# Prévia do cupom + limite de tentativas — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** No `/assinar`, digitar o cupom e apertar "Aplicar" mostra o valor com desconto na hora (resumo + parcelas), sem recarregar. E fechar o oráculo de cupons que já está exposto hoje, com limite de tentativas por IP nos dois caminhos.

**Architecture:** Um módulo novo `app/ratelimit.py` (contagem em memória, thread-safe, com evicção) usado por dois pontos do `serve.py`. Um endpoint `POST /assinar/cupom` devolve JSON com o preço já formatado, calculado por `pricing.base_cobrada` — a MESMA função do fechamento, nunca uma cópia. JS inline atualiza dois lugares na tela.

**Tech Stack:** Python 3 stdlib, `ThreadingHTTPServer`, SQLite/Postgres, `unittest`. JS inline sem build step nem dependência externa.

**Spec:** `docs/superpowers/specs/2026-07-29-cupom-previa-design.md` (commit `af47969`)

## Global Constraints

- **Worktree:** `.claude/worktrees/cupom-previa`, branch `feat/cupom-previa`, base main `4225a7d`. Testes: `cd app && python3 -m unittest discover -s tests`. **Baseline: 880 testes verdes.**
- **Repo multi-agente:** stagear só os arquivos da task; **nunca** `git add -A`.
- **TDD com prova por mutação:** teste primeiro, RED pelo motivo certo, fix, GREEN, e reverter o fix no scratch pra confirmar vermelho. Suíte verde não é evidência — este repo entregou 17 defeitos provados com suíte 100% verde nesta sessão.
- **A PRÉVIA NUNCA APLICA DESCONTO.** O endpoint só devolve o que exibir; o valor cobrado segue calculado no fechamento. Nenhuma escrita no banco no caminho da prévia: não consome cupom, não cria assinante, não marca nada.
- **Reusar `pricing.base_cobrada(plano, metodo, base_vig, cupom_pct=0.0, cupom_valor=0.0)`** (pricing.py:63) pra calcular a prévia. Proibido reimplementar a aritmética do desconto — tela e cobrança divergiriam no primeiro ajuste de regra.
- **Erro genérico e único.** Código inexistente, inativo, de cortesia, ou de outro plano → **exatamente a mesma** resposta e mensagem. `db.cupom_desconto(codigo, plano_slug)` (db.py:680) já devolve `0.0` em todos esses casos: um só caminho de falha, sem `if` por caso.
- **Cortesia continua funcionando no fechamento.** A prévia a ignora (aparece como inválida); o POST `/assinar` não muda de comportamento além de passar a contar tentativa.
- **Lock obrigatório** na estrutura de rate limit: o servidor é `ThreadingHTTPServer`, duas threads sem lock corrompem a contagem.
- **Evicção obrigatória** no rate limit: sem ela o dict cresce sem limite com IPs de bot = vazamento de memória.
- **Só tentativa FALHA conta.** Cupom válido não gasta cota.
- Não mexer no cálculo do desconto, no fluxo do Asaas, no gate 18h, na rotação nem na materialização.
- Sem push, sem deploy.

## File Structure

- `app/ratelimit.py` — **criar**: contagem por chave, em memória, thread-safe, com evicção. Sem dependência de `db` nem de `config`.
- `app/serve.py` — **modificar**: helper `_json`; rota `POST /assinar/cupom`; limite no POST `/assinar` existente.
- `app/site_web.py` — **modificar**: botão "Aplicar", aviso sob o campo, `id`s nos dois alvos, JS inline.
- `app/tests/test_cupom_previa.py` — **criar**.

---

### Task 1: `ratelimit.py` + limite no POST `/assinar` existente

**Files:**
- Create: `app/ratelimit.py`
- Modify: `app/serve.py` (POST `/assinar`, perto de `cupom = g("cupom").strip()` na linha 1348)
- Test: `app/tests/test_cupom_previa.py` (criar)

**Interfaces:**
- Produces: `ratelimit.permitir(chave, limite=5, janela_s=600) -> bool` (True = pode tentar) e `ratelimit.registrar_falha(chave, janela_s=600) -> None`. A Task 2 usa as duas no endpoint novo.
- Consumes: nada além do stdlib (`time`, `threading`).

**Contexto:** este limite é conserto de algo **já exposto**. Hoje dá pra chutar códigos no POST `/assinar` sem limite, e um cupom de cortesia acertado cria assinante ATIVO sem pagar (`serve.py:1356`).

- [ ] **Step 1: Write the failing test** — criar `app/tests/test_cupom_previa.py`:

```python
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRateLimit(unittest.TestCase):
    def setUp(self):
        import ratelimit
        ratelimit.zerar()          # estado limpo entre testes
        self.rl = ratelimit

    def test_permite_ate_o_limite_e_barra_depois(self):
        for i in range(5):
            self.assertTrue(self.rl.permitir("ip-1", limite=5, janela_s=600),
                            f"tentativa {i+1} devia passar")
            self.rl.registrar_falha("ip-1", janela_s=600)
        self.assertFalse(self.rl.permitir("ip-1", limite=5, janela_s=600),
                         "a 6a tentativa depois de 5 falhas tem que barrar")

    def test_chaves_independentes(self):
        for _ in range(5):
            self.rl.registrar_falha("ip-1", janela_s=600)
        self.assertFalse(self.rl.permitir("ip-1", limite=5, janela_s=600))
        self.assertTrue(self.rl.permitir("ip-2", limite=5, janela_s=600),
                        "um IP nao pode bloquear outro")

    def test_janela_expira(self):
        for _ in range(5):
            self.rl.registrar_falha("ip-1", janela_s=1)
        self.assertFalse(self.rl.permitir("ip-1", limite=5, janela_s=1))
        time.sleep(1.1)
        self.assertTrue(self.rl.permitir("ip-1", limite=5, janela_s=1),
                        "passada a janela, libera")

    def test_eviccao_nao_deixa_o_dict_crescer_sem_limite(self):
        for i in range(500):
            self.rl.registrar_falha(f"ip-{i}", janela_s=1)
        time.sleep(1.1)
        self.rl.permitir("gatilho", limite=5, janela_s=1)   # a chamada faz a limpeza
        self.assertLess(self.rl.tamanho(), 500,
                        "entradas vencidas tem que ser removidas, senao vaza memoria")

    def test_concorrencia_nao_corrompe_a_contagem(self):
        import threading
        def bate():
            for _ in range(20):
                self.rl.registrar_falha("ip-x", janela_s=600)
        ts = [threading.Thread(target=bate) for _ in range(10)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        # 10 threads x 20 = 200 falhas; sem lock a contagem se perde
        self.assertFalse(self.rl.permitir("ip-x", limite=199, janela_s=600),
                         "200 falhas registradas -> limite 199 tem que barrar")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_cupom_previa.TestRateLimit -v`
Expected: todos FALHAM com `ModuleNotFoundError: No module named 'ratelimit'`.

- [ ] **Step 3: Write minimal implementation** — criar `app/ratelimit.py`:

```python
"""Limite de tentativas em MEMÓRIA, por chave (ex.: IP). Sem dependência de db/config.

Existe pra fechar um oráculo real: o campo de cupom do /assinar permitia chutar
códigos sem limite, e um cupom de CORTESIA acertado cria assinante ATIVO sem passar
pelo Asaas (serve.py) — acesso de graça, não desconto.

⚠️ ESCOPO: a contagem vive no processo. O serviço roda com UMA instância
(deploy.replicas=1), então isso basta. Com duas instâncias o limite passa a ser POR
instância e afrouxa proporcionalmente — resolver exigiria store compartilhado
(Redis), que o projeto não tem. Registrado no backlog.
"""
import threading
import time

_LOCK = threading.Lock()
_FALHAS = {}          # chave -> [timestamps das falhas]
_MAX_CHAVES = 5000    # teto de segurança: além disso, poda agressiva


def _podar(agora, janela_s):
    """Remove timestamps vencidos e chaves que ficaram vazias. Chamado sob _LOCK."""
    for k in list(_FALHAS.keys()):
        vivos = [t for t in _FALHAS[k] if agora - t < janela_s]
        if vivos:
            _FALHAS[k] = vivos
        else:
            del _FALHAS[k]


def permitir(chave, limite=5, janela_s=600):
    """True se `chave` ainda pode tentar. Também é o ponto onde a evicção roda."""
    agora = time.time()
    with _LOCK:
        _podar(agora, janela_s)
        return len(_FALHAS.get(chave, [])) < int(limite)


def registrar_falha(chave, janela_s=600):
    """Conta UMA tentativa falha. Sucesso nunca chama isto — quem tem cupom bom
    não gasta cota por conferir."""
    agora = time.time()
    with _LOCK:
        _FALHAS.setdefault(chave, []).append(agora)
        if len(_FALHAS) > _MAX_CHAVES:
            _podar(agora, janela_s)


def zerar():
    """Só pra teste."""
    with _LOCK:
        _FALHAS.clear()


def tamanho():
    """Nº de chaves rastreadas — só pra teste de evicção."""
    with _LOCK:
        return len(_FALHAS)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_cupom_previa.TestRateLimit -v`
Expected: PASS (5 testes).

- [ ] **Step 5: Aplicar o limite no POST `/assinar` que já existe**

Em `app/serve.py`, no bloco do POST `/assinar`: o `ip_cliente` já é calculado (linha ~1336, `X-Forwarded-For` primeiro, senão `client_address[0]`) e o cupom em `cupom = g("cupom").strip()` (linha ~1348). **Leia a região antes de editar** — a ordem das linhas pode ter mudado; o `ip_cliente` tem que estar definido antes do seu uso.

Onde o código conclui que o cupom **não serve** (nem cortesia nem desconto), chame `ratelimit.registrar_falha(ip_cliente)`. E antes de avaliar um cupom **não vazio**, recuse com mensagem de bloqueio se `not ratelimit.permitir(ip_cliente)`. Cupom vazio não é tentativa: não conta e não pode ser barrado — a maioria compra sem cupom e não pode ser afetada.

Escreva o teste desse caminho seguindo os testes de rota que já existem no repo (`tests/test_precos_lancamento.py` e `tests/test_series.py::TestRotaSeries` instanciam o handler direto — **leia um dos dois e siga a mesma forma**, não invente stub novo). Cubra: (a) 5 cupons inválidos seguidos do mesmo IP e o 6º barrado; (b) compra **sem** cupom nunca é barrada, mesmo após bloqueio; (c) cupom **válido** não gasta cota.

- [ ] **Step 6: Rodar a suíte inteira**

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -6`
Expected: OK. 880 + os novos.

- [ ] **Step 7: Prove by mutation**

No scratch: (a) tirar o `with _LOCK` do `registrar_falha` → o teste de concorrência fica vermelho (pode precisar de mais threads pra evidenciar; se não ficar vermelho de forma confiável, **diga no report** em vez de fingir que provou); (b) tirar a poda → o teste de evicção fica vermelho; (c) tirar o `registrar_falha` do caminho de falha do `/assinar` → o teste do 6º barrado fica vermelho. Restaure cada um.

- [ ] **Step 8: Commit**

```bash
git add app/ratelimit.py app/serve.py app/tests/test_cupom_previa.py
git commit -m "feat(seguranca): limite de tentativas de cupom por IP (fecha oraculo do /assinar)"
```

---

### Task 2: endpoint da prévia + botão + JS

**Files:**
- Modify: `app/serve.py` (helper `_json`; rota `POST /assinar/cupom`)
- Modify: `app/site_web.py` (`pagina_assinar`: botão, aviso, `id`s, JS inline)
- Test: `app/tests/test_cupom_previa.py` (adicionar classes)

**Interfaces:**
- Consumes: `ratelimit.permitir` / `registrar_falha` (Task 1); `db.cupom_desconto(codigo, plano_slug)` (db.py:680, devolve `0.0` em todo caso de falha); `pricing.base_cobrada` (pricing.py:63); `pricing.opcoes_parcelas(base)` (pricing.py:15, devolve `[{"parcelas","total","por_parcela"}]`); `pricing.fmt_brl(v)` (pricing.py:52, formato `R$ 1.497,00`); `config.plano_por_slug(slug)`.
- Produces: `POST /assinar/cupom` → JSON.

- [ ] **Step 1: Write the failing test** — adicionar em `app/tests/test_cupom_previa.py`:

```python
class TestPreviaCupom(unittest.TestCase):
    """A prévia usa a MESMA `base_cobrada` do fechamento — os testes conferem contra
    ela, nunca contra aritmética duplicada aqui."""

    def setUp(self):
        import ratelimit
        ratelimit.zerar()

    def _resp(self, plano="anual", cupom="LANCAMENTO", metodo="CARTAO", ip="ip-teste"):
        """POSTa em /assinar/cupom e devolve o dict do JSON."""
        raise NotImplementedError(
            "monte o handler seguindo o padrao de teste de rota do repo — leia "
            "tests/test_series.py::TestRotaSeries (_make_stub_cls) ou "
            "tests/test_precos_lancamento.py e reuse a forma de lá")

    def test_cupom_valido_devolve_preco_e_parcelas_com_desconto(self):
        import config, pricing, db
        db.init()
        plano = config.plano_por_slug("anual")
        esperado = pricing.base_cobrada(plano, "CARTAO", float(plano["base"]),
                                        cupom_valor=db.cupom_desconto("LANCAMENTO", "anual"))
        r = self._resp(cupom="LANCAMENTO")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["preco"], pricing.fmt_brl(esperado))
        self.assertTrue(r["parcelas"], "o dropdown de parcelas tem que vir atualizado")

    def test_cortesia_responde_invalido_generico(self):
        """Cortesia (desconto 0) daria acesso GRATIS no fechamento. A previa nao pode
        confirmar que o codigo existe, senao vira detector de jackpot."""
        import db
        db.init()
        db.criar_cupom(descricao="cortesia teste", uso_unico=False, dias_acesso=0,
                       codigo="CORTESIATESTE")
        r = self._resp(cupom="CORTESIATESTE")
        self.assertFalse(r["ok"])
        self.assertEqual(r["msg"], self._resp(cupom="NAOEXISTEZZZ")["msg"],
                         "cortesia e inexistente tem que ser INDISTINGUIVEIS")

    def test_cupom_de_outro_plano_invalido_generico(self):
        import db
        db.init()
        r = self._resp(plano="mensal", cupom="LANCAMENTO")   # LANCAMENTO e do anual
        self.assertFalse(r["ok"])
        self.assertEqual(r["msg"], self._resp(cupom="NAOEXISTEZZZ", plano="mensal")["msg"])

    def test_cupom_desativado_no_admin_invalido(self):
        import db
        db.init()
        db.toggle_cupom("LANCAMENTO", False)
        try:
            r = self._resp(cupom="LANCAMENTO")
            self.assertFalse(r["ok"])
        finally:
            db.toggle_cupom("LANCAMENTO", True)

    def test_previa_nao_escreve_nada_no_banco(self):
        """Nem consome cupom, nem cria assinante. Se a previa gastasse o cupom,
        conferir o preco queimaria o desconto."""
        import db, subscribers
        db.init()
        antes_usos = (db.obter_cupom("LANCAMENTO") or {}).get("usos", 0)
        antes_assin = len(subscribers.listar())
        self._resp(cupom="LANCAMENTO")
        self.assertEqual((db.obter_cupom("LANCAMENTO") or {}).get("usos", 0), antes_usos)
        self.assertEqual(len(subscribers.listar()), antes_assin)

    def test_bloqueia_depois_de_5_invalidos_e_valido_nao_gasta_cota(self):
        for _ in range(5):
            self.assertFalse(self._resp(cupom="NAOEXISTEZZZ", ip="ip-bloq")["ok"])
        r = self._resp(cupom="NAOEXISTEZZZ", ip="ip-bloq")
        self.assertTrue(r.get("bloqueado"), f"6a tentativa devia bloquear: {r}")

        import ratelimit
        ratelimit.zerar()
        for _ in range(5):
            self.assertTrue(self._resp(cupom="LANCAMENTO", ip="ip-ok")["ok"])
        self.assertTrue(self._resp(cupom="LANCAMENTO", ip="ip-ok")["ok"],
                        "cupom valido nao gasta cota")
```

**Step 1a — obrigatório antes de escrever:** `_resp` está com `NotImplementedError` de propósito. **Leia `tests/test_series.py::TestRotaSeries` (helper `_make_stub_cls`) e `tests/test_precos_lancamento.py`, escolha a forma que já existe no repo e implemente `_resp` com ela.** Não crie um terceiro padrão de stub. Confirme também: `db.criar_cupom` aceita `codigo=`? `db.obter_cupom` devolve `usos`? `subscribers.listar()` existe? Ajuste aos nomes reais e registre no report o que divergiu.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_cupom_previa.TestPreviaCupom -v`
Expected: FALHAM — a rota `/assinar/cupom` não existe (404/redirect, não JSON).

- [ ] **Step 3: Write minimal implementation**

**3a. `_json` em `serve.py`**, ao lado do `_html` (linha 478):

```python
    def _json(self, obj, code=200):
        import json
        corpo = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)
```

**3b. A rota**, no `do_POST`, **antes** do bloco do `/assinar` (pra não ser engolida por ele):

```python
        if path == "/assinar/cupom":
            import config, db, pricing, ratelimit
            ip = (self.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                  or self.client_address[0])
            plano = config.plano_por_slug(g("plano"))
            if not plano:
                return self._json({"ok": False, "msg": "Plano inválido."}, 400)
            if not ratelimit.permitir(ip):
                return self._json({"ok": False, "bloqueado": True,
                                   "msg": "Muitas tentativas. Tente de novo em alguns minutos."})
            db.init()
            metodo = "PIX" if (g("metodo") or "").upper() == "PIX" else "CARTAO"
            # cupom_desconto devolve 0.0 pra: inexistente, inativo, CORTESIA (desconto 0)
            # e escopo de outro plano -> um único caminho de falha, indistinguível.
            desconto = db.cupom_desconto(g("cupom").strip().upper(), plano["slug"])
            if desconto <= 0:
                ratelimit.registrar_falha(ip)
                return self._json({"ok": False, "msg": "Cupom inválido."})
            base = pricing.base_cobrada(plano, metodo, float(plano["base"]),
                                        cupom_valor=desconto)
            return self._json({
                "ok": True,
                "preco": pricing.fmt_brl(base),
                "msg": f"−{pricing.fmt_brl(desconto)} aplicado",
                "parcelas": [{"parcelas": o["parcelas"],
                              "por_parcela": pricing.fmt_brl(o["por_parcela"]),
                              "total": pricing.fmt_brl(o["total"])}
                             for o in pricing.opcoes_parcelas(base)],
            })
```

**3c. A tela**, em `site_web.pagina_assinar`: dar `id` aos dois alvos — o `div.sum-price` (site_web.py:2088) e o `<select name="parcelas">` (dentro do `parcelas_html`) — acrescentar o botão Aplicar ao lado do campo de cupom (site_web.py:2109), o aviso fixo sob ele, e um `<span>` pra mensagem. **Todo valor interpolado por `_esc`.**

**3d. O JS inline**, no fim da página: ao clicar Aplicar, `fetch("/assinar/cupom", {method:"POST", headers:{"Content-Type":"application/x-www-form-urlencoded"}, body: new URLSearchParams({...})})`, e com a resposta: se `ok`, trocar o texto do `sum-price` (preservando o `<span>` do período, que está dentro dele) e reconstruir as `<option>` do select; se não, mostrar `msg` no span de mensagem. **Sem dependência externa** (a CSP não permite). O botão precisa de `type="button"` — senão submete o formulário.

**Degradação sem JS:** não mudar o comportamento do campo. Sem JS, digitar o cupom e fechar a compra continua aplicando o desconto no servidor, como hoje.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_cupom_previa -v` depois `cd app && python3 -m unittest discover -s tests 2>&1 | tail -6`
Expected: OK, saída limpa.

- [ ] **Step 5: Prove by mutation**

No scratch: (a) trocar a mensagem de cortesia por algo específico → o teste de indistinguibilidade fica vermelho; (b) tirar o `registrar_falha` da rota → o teste de bloqueio fica vermelho; (c) trocar `base_cobrada` por `base - desconto` na mão → **o teste do Pix tem que pegar**; se não pegar, acrescente um caso com `metodo="PIX"` (o `base_cobrada` empilha os 5% do Pix e a subtração crua não). Restaure.

- [ ] **Step 6: Commit**

```bash
git add app/serve.py app/site_web.py app/tests/test_cupom_previa.py
git commit -m "feat(assinar): previa do cupom na tela (preco + parcelas) via /assinar/cupom"
```

---

## Notas de execução

- **Smoke manual (documentar, não executar):** `/assinar?plano=anual` → digitar LANCAMENTO → Aplicar → resumo vira R$997 e o dropdown vira 12x de R$83 → fechar a compra e conferir que o Asaas cobra 997. Trocar pra Pix e conferir que a prévia mostra 947,15 (997 − 5%).
- **Backlog:** rate limit por instância (store compartilhado se um dia escalar); aviso ao portador de cortesia de que o código só funciona no fechamento.

## Self-Review (checklist do autor)

- **Cobertura do spec:** prévia sem recarregar (T2) ✓; atualiza resumo E parcelas (T2 3c/3d) ✓; reusa `base_cobrada` (T2 3b + mutação (c)) ✓; erro genérico único via `cupom_desconto` (T2 3b) ✓; cortesia indistinguível (T2 teste) ✓; escopo por plano (T2 teste) ✓; prévia não escreve no banco (T2 teste) ✓; limite nos DOIS caminhos (T1 Step 5 + T2 3b) ✓; só falha conta (T1 + T2 teste) ✓; lock (T1) ✓; evicção (T1) ✓; degradação sem JS (T2 3d) ✓.
- **Consistência de tipos:** `permitir -> bool`, `registrar_falha -> None`; `cupom_desconto -> float` (0.0 em falha); `base_cobrada -> float`; `fmt_brl -> str`; o JSON tem sempre `ok` e `msg`, e `preco`/`parcelas` só quando `ok`.
- **Placeholders:** o único `NotImplementedError` é o `_resp` da Task 2, deliberado e com instrução explícita no Step 1a pra escolher entre **dois padrões de stub que já existem no repo** — é integração contra código real, não design faltando. Nenhum outro `...`/TBD.
- **Risco que assumi:** o teste de concorrência do rate limit pode não ficar vermelho de forma confiável ao remover o lock (GIL pode mascarar). O Step 7 manda **declarar isso no report** em vez de alegar prova que não houve.
