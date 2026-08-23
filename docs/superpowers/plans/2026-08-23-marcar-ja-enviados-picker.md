# Marcar estudos já enviados no picker do 🔁 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** No picker de trocar o estudo de amanhã (`/revisar` das 18h, botão 🔁), marcar
quais estudos da reserva/candidatos já apareceram num PDF diário antes, separando-os num
sub-bloco próprio dentro de cada card de tema.

**Architecture:** `app/daily.py` ganha uma função que cruza a lista de alternativas com a
tabela `digests` (por DOI, com fallback por título normalizado) e anota cada uma com a
data mais antiga em que já saiu. `app/review_web.py` usa essa anotação pra separar,
dentro de cada card de tema, os estudos disponíveis dos já enviados.

**Tech Stack:** Python 3, `unittest` + `unittest.mock` (os testes deste picker usam mock
de `db`, não um banco real — ver `tests/test_trocar_estudo.py`).

## Global Constraints

- Casa por DOI primeiro (normalizado: `strip().lower()`); só cai pro título quando falta
  DOI de um dos lados. Título comparado (normalizado: espaços colapsados, `strip().lower()`)
  contra `titulo_original` OU `titulo_pt` do digest — a reserva guarda título em PT, o
  candidato guarda em EN, comparar só um dos dois campos erraria metade dos casos.
- Guarda a data MAIS ANTIGA quando o mesmo DOI/título aparece em mais de um digest.
- A data mostrada fica em ISO cru (`AAAA-MM-DD`) — o picker é tela interna, não introduz
  um formato novo de data.
- Estudos já enviados continuam com o botão "Usar este amanhã" — nunca ficam bloqueados.
- O contador `(N)` no `<summary>` de cada tema continua sendo o TOTAL (disponíveis +
  já enviados) — não muda esse número, só o que tem embaixo dele.
- Não mexe em `app/db.py`, `app/curadoria.py`, `app/content.py`, nem na lógica de
  `trocar_estudo_amanha` — só leitura (`db.listar_digests()`, que já existe) e apresentação.
- Fora de escopo: recalcular a nota (`score`) zerada do estoque antigo da reserva —
  decisão do Diego, não faz parte deste plano.

---

## Arquivos afetados

| Arquivo | Papel |
|---|---|
| `app/daily.py` | `marcar_ja_enviados` + `_normalizar_titulo` novas; `montar_alternativas` passa a incluir `doi` em cada alternativa e chamar `marcar_ja_enviados` |
| `app/review_web.py` | `_item_troca` (aviso condicional); `pagina_trocar_estudo` (separa disponíveis/já-enviados dentro de cada card de tema) |
| `app/tests/test_trocar_estudo.py` | testes de `marcar_ja_enviados`, `montar_alternativas` (doi propagado) e do picker (aviso + separação) |

Nenhum arquivo novo é criado.

---

### Task 1: `app/daily.py` — casar alternativas com o histórico de envios

**Files:**
- Modify: `app/daily.py:17` (import novo) e `app/daily.py:435-462` (`montar_alternativas`
  + funções novas antes dela)
- Test: `app/tests/test_trocar_estudo.py`

**Interfaces:**
- Produces: `marcar_ja_enviados(alts: list[dict]) -> list[dict]` — recebe a lista de
  alternativas (cada uma com pelo menos as chaves `titulo` e `doi`), devolve a MESMA
  lista com a chave `ja_enviado_em` adicionada em cada dict (`str` ISO ou `None`).
  `_normalizar_titulo(t: str | None) -> str` — auxiliar, não é chamada de fora deste
  arquivo.
- Modifica (contrato não muda pra quem já chama): `montar_alternativas(r) -> list[dict]`
  — cada dict da lista agora também tem as chaves `doi` e `ja_enviado_em`.

- [ ] **Step 1: Escrever os testes que ainda falham**

Abra `app/tests/test_trocar_estudo.py`. Insira uma classe nova **logo antes** de
`class TestMontarAlternativas(unittest.TestCase):`:

```python
class TestMarcarJaEnviados(unittest.TestCase):
    def setUp(self):
        import daily
        importlib.reload(daily)
        self.daily = daily

    def test_casa_por_doi(self):
        import db
        digests = [{"data": "2026-07-14", "doi": "10.1/X", "titulo_original": "", "titulo_pt": ""}]
        with mock.patch.object(db, "listar_digests", return_value=digests):
            alts = self.daily.marcar_ja_enviados([{"titulo": "Y", "doi": "10.1/x"}])
        self.assertEqual(alts[0]["ja_enviado_em"], "2026-07-14")

    def test_casa_por_titulo_original_quando_falta_doi(self):
        import db
        digests = [{"data": "2026-07-14", "doi": "", "titulo_original": "Effects of X", "titulo_pt": ""}]
        with mock.patch.object(db, "listar_digests", return_value=digests):
            alts = self.daily.marcar_ja_enviados([{"titulo": "effects of x", "doi": ""}])
        self.assertEqual(alts[0]["ja_enviado_em"], "2026-07-14")

    def test_casa_por_titulo_pt_quando_falta_doi(self):
        import db
        digests = [{"data": "2026-07-14", "doi": "", "titulo_original": "", "titulo_pt": "Efeitos de X"}]
        with mock.patch.object(db, "listar_digests", return_value=digests):
            alts = self.daily.marcar_ja_enviados([{"titulo": "Efeitos de X", "doi": ""}])
        self.assertEqual(alts[0]["ja_enviado_em"], "2026-07-14")

    def test_guarda_a_data_mais_antiga(self):
        import db
        digests = [{"data": "2026-08-01", "doi": "10.1/x", "titulo_original": "", "titulo_pt": ""},
                   {"data": "2026-06-01", "doi": "10.1/x", "titulo_original": "", "titulo_pt": ""}]
        with mock.patch.object(db, "listar_digests", return_value=digests):
            alts = self.daily.marcar_ja_enviados([{"titulo": "Y", "doi": "10.1/X"}])
        self.assertEqual(alts[0]["ja_enviado_em"], "2026-06-01")

    def test_sem_casamento_fica_none(self):
        import db
        with mock.patch.object(db, "listar_digests", return_value=[]):
            alts = self.daily.marcar_ja_enviados([{"titulo": "Nunca saiu", "doi": ""}])
        self.assertIsNone(alts[0]["ja_enviado_em"])

    def test_doi_e_titulo_vazios_nao_casam_a_toa(self):
        import db
        digests = [{"data": "2026-07-14", "doi": "", "titulo_original": "", "titulo_pt": ""}]
        with mock.patch.object(db, "listar_digests", return_value=digests):
            alts = self.daily.marcar_ja_enviados([{"titulo": "", "doi": ""}])
        self.assertIsNone(alts[0]["ja_enviado_em"])
```

Agora atualize `class TestMontarAlternativas`. O helper `_db` (perto do topo da classe)
precisa mockar `listar_digests` também, senão as chamadas reais batem no sqlite de teste
e o `digests` pode nem existir ainda:

```python
    def _db(self, reserva, candidatos):
        import db
        return (mock.patch.object(db, "listar_reserva", return_value=reserva),
                mock.patch.object(db, "listar_candidatos", return_value=candidatos),
                mock.patch.object(db, "listar_digests", return_value=[]))
```

Nos 3 métodos que usam esse helper, troque `p1, p2 = self._db(...)` / `with p1, p2:` por
`p1, p2, p3 = self._db(...)` / `with p1, p2, p3:` (são
`test_reserva_primeiro_e_exclui_atual_e_ordena`, `test_exclui_candidato_atual_e_normaliza`
e `test_alternativa_valida`).

Em `test_exclui_candidato_atual_e_normaliza`, a comparação exata do dict quebra porque a
alternativa ganha 2 chaves novas — atualize para:

```python
        self.assertEqual(alts[0], {"tipo": "candidato", "id": "c_ok",
                                   "titulo": "Outro", "fonte": "Sports Med",
                                   "tema": "Performance", "score": 7,
                                   "doi": "", "ja_enviado_em": None})
```

E adicione um teste novo confirmando que o `doi` de cada linha da reserva/candidato
chega até a alternativa, logo depois de `test_alternativa_valida`:

```python
    def test_doi_passa_para_a_alternativa(self):
        daily = self.daily
        r = {"reserva_id": None, "candidato_id": None, "artigo": {"tema": "Obesidade"}}
        reserva = [{"id": "res1", "titulo_pt": "R", "fonte": "X", "tema": "Obesidade",
                    "prioridade": 0, "score": 1, "doi": "10.1/res"}]
        candidatos = [{"id": "c1", "titulo": "C", "fonte": "Y", "tema": "Obesidade",
                       "score": 2, "doi": "10.1/cand"}]
        p1, p2, p3 = self._db(reserva, candidatos)
        with p1, p2, p3:
            alts = daily.montar_alternativas(r)
        dois = {a["id"]: a["doi"] for a in alts}
        self.assertEqual(dois, {"res1": "10.1/res", "c1": "10.1/cand"})
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `cd app && python3 -m unittest tests.test_trocar_estudo -v 2>&1 | tail -40`
Expected: `TestMarcarJaEnviados` inteira falha (`AttributeError: module 'daily' has no
attribute 'marcar_ja_enviados'`). `TestMontarAlternativas` falha nos 3 testes que agora
desempacotam `p1, p2, p3` (`ValueError: not enough values to unpack` — o `_db` só devolve
2 ainda) e no `test_doi_passa_para_a_alternativa` novo.

- [ ] **Step 3: Adicionar o import e as funções novas**

Em `app/daily.py`, logo depois de `import json` (linha 17), adicione:

```python
import re
```

Logo ANTES de `def montar_alternativas(r):` (linha 438 hoje), adicione:

```python
def _normalizar_titulo(t):
    return re.sub(r"\s+", " ", (t or "").strip().lower())


def marcar_ja_enviados(alts):
    """Anota cada alternativa com `ja_enviado_em` (data ISO mais antiga em que aquele
    estudo já saiu) ou None. Casa por DOI primeiro (sem risco de traducao); sem DOI dos
    dois lados, cai pro titulo normalizado contra titulo_original OU titulo_pt do digest
    -- a reserva guarda titulo em PT, o candidato em EN, entao um so' dos dois campos
    erraria metade dos casos."""
    import db
    por_doi, por_titulo = {}, {}
    for d in db.listar_digests():
        data = d.get("data", "")
        doi = (d.get("doi") or "").strip().lower()
        if doi and (doi not in por_doi or data < por_doi[doi]):
            por_doi[doi] = data
        for campo in ("titulo_original", "titulo_pt"):
            t = _normalizar_titulo(d.get(campo))
            if t and (t not in por_titulo or data < por_titulo[t]):
                por_titulo[t] = data
    for a in alts:
        doi = (a.get("doi") or "").strip().lower()
        a["ja_enviado_em"] = por_doi.get(doi) if doi else None
        if not a["ja_enviado_em"]:
            a["ja_enviado_em"] = por_titulo.get(_normalizar_titulo(a.get("titulo")))
    return alts
```

- [ ] **Step 4: Atualizar `montar_alternativas`**

Substitua o corpo de `montar_alternativas` (a partir de `alts = (` até o `return`, hoje
linhas 454-462) por:

```python
    alts = (
        [{"tipo": "reserva", "id": x["id"], "titulo": x.get("titulo_pt", ""),
          "fonte": x.get("fonte", ""), "tema": x.get("tema", ""), "score": x.get("score", 0) or 0,
          "doi": x.get("doi", "")}
         for x in res_rows]
        + [{"tipo": "candidato", "id": x["id"], "titulo": x.get("titulo", ""),
            "fonte": x.get("fonte", ""), "tema": x.get("tema", ""), "score": x.get("score", 0) or 0,
            "doi": x.get("doi", "")}
           for x in cand_rows]
    )
    return marcar_ja_enviados(alts[:ALTERNATIVAS_MAX])
```

- [ ] **Step 5: Rodar os testes e confirmar que passam**

Run: `cd app && python3 -m unittest tests.test_trocar_estudo -v 2>&1 | tail -50`
Expected: PASS em tudo — `TestMarcarJaEnviados` inteira, os 3 testes atualizados de
`TestMontarAlternativas`, e o `test_doi_passa_para_a_alternativa` novo.

Run também a suíte inteira, pra garantir que nada mais dependia do formato antigo do
dict de alternativa:

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -20`
Expected: `OK`, sem nenhuma falha.

- [ ] **Step 6: Commit**

```bash
git add app/daily.py app/tests/test_trocar_estudo.py
git commit -m "$(cat <<'EOF'
feat(daily): marca no picker do 🔁 quem ja foi enviado antes

marcar_ja_enviados cruza reserva+candidatos com a tabela digests
(historico completo de tudo que ja saiu). Casa por DOI primeiro; sem
DOI de um dos lados, cai pro titulo normalizado contra titulo_original
OU titulo_pt do digest -- a reserva guarda titulo em PT, o candidato
em EN, um so' dos dois campos erraria metade dos casos. Guarda a data
mais antiga quando o mesmo estudo saiu mais de uma vez.

Ver docs/superpowers/specs/2026-08-23-marcar-ja-enviados-picker-design.md
EOF
)"
```

---

### Task 2: `app/review_web.py` — separar já-enviados dentro de cada card de tema

**Files:**
- Modify: `app/review_web.py:147-160` (`_item_troca`) e `app/review_web.py:162-206`
  (`pagina_trocar_estudo`)
- Test: `app/tests/test_trocar_estudo.py`

**Interfaces:**
- Consumes: cada dict de alternativa passado pra `pagina_trocar_estudo`/`_item_troca` já
  tem a chave `ja_enviado_em` (`str` ISO ou `None`/ausente) — produzida pela Task 1, mas
  os testes deste arquivo constroem os dicts à mão, sem depender de `daily.py`.
- Modifica (assinatura não muda): `_item_troca(a, tok) -> str` e
  `pagina_trocar_estudo(alternativas, r, token, areas=()) -> str`.

- [ ] **Step 1: Escrever os testes que ainda falham**

Em `app/tests/test_trocar_estudo.py`, dentro de `class TestReviewWebTrocar`, adicione
estes métodos logo depois de `test_pagina_trocar_lista_e_escapa`:

```python
    def test_item_com_aviso_de_ja_enviado(self):
        import review_web
        alts = [{"tipo": "reserva", "id": "res1", "titulo": "T",
                 "fonte": "NEJM", "tema": "Obesidade", "score": 9,
                 "ja_enviado_em": "2026-07-14"}]
        r = {"artigo": {"titulo": "Atual"}}
        html = review_web.pagina_trocar_estudo(alts, r, "tok")
        self.assertIn("já enviado em 2026-07-14", html)

    def test_item_sem_aviso_quando_nunca_enviado(self):
        import review_web
        alts = [{"tipo": "reserva", "id": "res1", "titulo": "T",
                 "fonte": "NEJM", "tema": "Obesidade", "score": 9,
                 "ja_enviado_em": None}]
        r = {"artigo": {"titulo": "Atual"}}
        html = review_web.pagina_trocar_estudo(alts, r, "tok")
        self.assertNotIn("já enviado", html)

    def test_tema_so_com_disponiveis_nao_mostra_cabecalho_ja_enviados(self):
        import review_web
        alts = [{"tipo": "reserva", "id": "res1", "titulo": "T",
                 "fonte": "NEJM", "tema": "Obesidade", "score": 9,
                 "ja_enviado_em": None}]
        html = review_web.pagina_trocar_estudo(alts, {"artigo": {"titulo": "Atual"}}, "tok")
        self.assertNotIn("Já enviados", html)

    def test_tema_so_com_ja_enviados_mostra_nada_disponivel_e_o_bloco(self):
        import review_web
        alts = [{"tipo": "reserva", "id": "res1", "titulo": "T",
                 "fonte": "NEJM", "tema": "Obesidade", "score": 9,
                 "ja_enviado_em": "2026-07-14"}]
        html = review_web.pagina_trocar_estudo(alts, {"artigo": {"titulo": "Atual"}}, "tok")
        self.assertIn("Nada disponível neste tema.", html)
        self.assertIn("Já enviados", html)
        self.assertIn('value="trocar_confirmar"', html)   # continua escolhível

    def test_tema_misto_mostra_disponiveis_antes_dos_ja_enviados(self):
        import review_web
        alts = [
            {"tipo": "reserva", "id": "disp", "titulo": "Disponível",
             "fonte": "NEJM", "tema": "Obesidade", "score": 9, "ja_enviado_em": None},
            {"tipo": "reserva", "id": "env", "titulo": "Enviado",
             "fonte": "NEJM", "tema": "Obesidade", "score": 5, "ja_enviado_em": "2026-07-14"},
        ]
        html = review_web.pagina_trocar_estudo(alts, {"artigo": {"titulo": "Atual"}}, "tok")
        self.assertLess(html.index("Disponível"), html.index("Já enviados"))
        self.assertLess(html.index("Já enviados"), html.index("Enviado"))
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `cd app && python3 -m unittest tests.test_trocar_estudo.TestReviewWebTrocar -v 2>&1 | tail -30`
Expected: os 5 testes novos falham (`_item_troca`/`pagina_trocar_estudo` ainda não sabem
da chave `ja_enviado_em` — o aviso nunca aparece e não existe separação nenhuma).

- [ ] **Step 3: Atualizar `_item_troca`**

Em `app/review_web.py`, substitua a função inteira (hoje linhas 147-160) por:

```python
def _item_troca(a, tok):
    esc = _html.escape
    aviso = (f'<br><small style="color:#9c3226">⚠️ já enviado em {esc(a["ja_enviado_em"])}</small>'
              if a.get("ja_enviado_em") else "")
    return (f'<li style="margin:12px 0">'
            f'<form method="post" action="/revisar/{tok}" '
            f'style="display:flex;gap:10px;align-items:center;justify-content:space-between">'
            f'<span><b>{esc(a["titulo"])}</b><br>'
            f'<small style="color:#6b7a76">{esc(a["fonte"])} · '
            f'nota {esc(str(a["score"]))} · {esc(a["tipo"])}</small>{aviso}</span>'
            f'<input type="hidden" name="acao" value="trocar_confirmar">'
            f'<input type="hidden" name="tipo" value="{esc(a["tipo"])}">'
            f'<input type="hidden" name="id" value="{esc(str(a["id"]))}">'
            f'<button type="submit">Usar este amanhã</button>'
            f'</form></li>')
```

- [ ] **Step 4: Separar disponíveis/já-enviados em `pagina_trocar_estudo`**

Ainda em `app/review_web.py`, dentro de `pagina_trocar_estudo`, localize o laço `for t in
temas:` (dentro do bloco `else:` que monta `cards`, hoje por volta da linha 178-196):

```python
        for t in temas:
            itens = por_tema.get(t, [])
            corpo_card = (f'<ul style="list-style:none;padding:0">'
                          + "".join(_item_troca(a, tok) for a in itens) + "</ul>"
                          ) if itens else '<p style="color:#6b7a76">Nada neste tema.</p>'
            aberto = " open" if t == tema_amanha else ""
            cards.append(
                f'<details name="troca-tema"{aberto} style="border:1px solid #d8ddd7;'
                f'border-radius:10px;margin:8px 0;padding:0 12px">'
                f'<summary style="cursor:pointer;padding:12px 0;font-weight:600">'
                f'{area_estudo.emoji(t)} {esc(t)} '
                f'<span style="color:#6b7a76;font-weight:400">({len(itens)})</span>'
                f'</summary>{corpo_card}</details>')
```

Substitua por:

```python
        for t in temas:
            itens = por_tema.get(t, [])
            if not itens:
                corpo_card = '<p style="color:#6b7a76">Nada neste tema.</p>'
            else:
                disponiveis = [a for a in itens if not a.get("ja_enviado_em")]
                enviados = [a for a in itens if a.get("ja_enviado_em")]
                corpo_card = (f'<ul style="list-style:none;padding:0">'
                              + "".join(_item_troca(a, tok) for a in disponiveis) + "</ul>"
                              ) if disponiveis else '<p style="color:#6b7a76">Nada disponível neste tema.</p>'
                if enviados:
                    corpo_card += (
                        '<p style="color:#9c3226;font-weight:600;margin:14px 0 4px">'
                        '⚠️ Já enviados</p>'
                        '<ul style="list-style:none;padding:0">'
                        + "".join(_item_troca(a, tok) for a in enviados) + "</ul>")
            aberto = " open" if t == tema_amanha else ""
            cards.append(
                f'<details name="troca-tema"{aberto} style="border:1px solid #d8ddd7;'
                f'border-radius:10px;margin:8px 0;padding:0 12px">'
                f'<summary style="cursor:pointer;padding:12px 0;font-weight:600">'
                f'{area_estudo.emoji(t)} {esc(t)} '
                f'<span style="color:#6b7a76;font-weight:400">({len(itens)})</span>'
                f'</summary>{corpo_card}</details>')
```

- [ ] **Step 5: Rodar os testes e confirmar que passam**

Run: `cd app && python3 -m unittest tests.test_trocar_estudo -v 2>&1 | tail -60`
Expected: PASS em tudo, incluindo os testes já existentes (`test_pagina_trocar_lista_e_escapa`,
`test_pagina_trocar_vazio`, etc. — nenhum deles usa `ja_enviado_em`, então `.get()` cai em
`None`/falsy e o comportamento visível é igual ao de antes pra eles).

Run também a suíte inteira:

Run: `cd app && python3 -m unittest discover -s tests 2>&1 | tail -20`
Expected: `OK`, sem nenhuma falha.

- [ ] **Step 6: Commit**

```bash
git add app/review_web.py app/tests/test_trocar_estudo.py
git commit -m "$(cat <<'EOF'
feat(revisar): separa ja-enviados dentro de cada tema do picker do 🔁

Cada card de tema mostra os disponiveis primeiro, como antes; se
houver algum ja enviado (marcado por daily.marcar_ja_enviados), entra
um sub-bloco "⚠️ Ja enviados" abaixo, com data e o mesmo botao "Usar
este amanha" -- continua escolhivel de proposito.

Ver docs/superpowers/specs/2026-08-23-marcar-ja-enviados-picker-design.md
EOF
)"
```

---

## Self-Review

**Cobertura da spec:** casamento por DOI+título ✅ (Task 1, `marcar_ja_enviados`); data
mais antiga quando repete ✅ (testado); `doi` propagado nas alternativas ✅ (Task 1,
`montar_alternativas` + teste dedicado); aviso com data no item ✅ (Task 2, `_item_troca`);
separação dentro do card de tema, disponíveis antes ✅ (Task 2, `pagina_trocar_estudo` +
teste de ordem); botão continua presente nos já-enviados ✅ (testado explicitamente);
contador do `<summary>` continua o total ✅ (não alterado — `len(itens)` continua sobre a
lista inteira, antes de separar); nota zerada fora de escopo ✅ (nenhuma task mexe em
`score`).

**Placeholders:** nenhum "TBD"/"implementar depois" — todo código dos steps é literal.

**Consistência de tipos/nomes:** `marcar_ja_enviados`/`_normalizar_titulo` usados com os
mesmos nomes em Task 1 e citados (sem redefinir) na Task 2. Chave `ja_enviado_em`
idêntica nos dois arquivos e em todos os testes novos.
