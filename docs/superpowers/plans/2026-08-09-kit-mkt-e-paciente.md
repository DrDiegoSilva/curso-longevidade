# Kit de redes para MKT + bloco do paciente — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cada pauta de Reels do PDF diário vira um card com gancho, roteiro numerado e o dado que sustenta; mais um bloco por estudo com os limites do CFM e um bloco clínico com a fala para o paciente.

**Architecture:** Estende o JSON já guardado no campo `gancho` — sem coluna nova, sem migração, sem segunda chamada de IA. `parse_gancho` passa a aceitar quatro formatos de entrada porque o estoque de reserva já tem ganchos no formato antigo. O layout muda em `pdf.py` e no CSS espelhado de `site_web.py`.

**Tech Stack:** Python stdlib (sem pip), `unittest`, HTML+CSS renderizado por Chromium headless.

## Global Constraints

- **Sem dependência nova.** O container é stdlib + psycopg2. Não adicionar pacote.
- **Não modificar** `app/daily.py`, `app/db.py`, `app/resumo_diario.py`. O `SYS_ESTUDO` e o resumo clínico ficam **intactos** — é requisito explícito do dono do produto.
- **`parse_gancho` nunca levanta exceção e nunca devolve `None` em campo nenhum.** Roda no caminho do envio diário, onde uma exceção custa o envio do dia.
- **Escape antes de virar tag.** Todo conteúdo vindo da IA passa por `_html.escape` antes de entrar no HTML.
- **Nunca `git add -A`, nunca `git stash` / `git stash pop`.** A pilha de stash é compartilhada entre worktrees e há outras sessões neste repo. Stagear só os arquivos do próprio task.
- Testes: `cd app && python3 -m unittest discover -s tests`. A suíte está **100% verde (1185 testes)** — tem que continuar.
- Código e comentários em **português**, como o resto do repo.

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `app/content.py` (modificar) | `SYS_GANCHO` (prompt), `parse_gancho` (parse + compatibilidade), `max_tokens` da chamada. |
| `app/pdf.py` (modificar) | `_kit_html` (cards + bloco CFM), `_paciente_html` (novo), `montar_html` (encaixe), CSS do kit. |
| `app/site_web.py` (modificar) | Cópia própria do CSS do kit (linhas ~238-255). O site renderiza o mesmo HTML via `pdf._kit_html` em `site_web.py:1976`. |
| `app/tests/test_kit_redes.py` (modificar) | Já existe com 33 testes. **Seis mudam de significado** — ver Task 1. |

---

### Task 1: `parse_gancho` — formato novo, compatibilidade e o fim do JSON cru

**Files:**
- Modify: `app/content.py` (constantes perto da linha 121; `parse_gancho` nas linhas 129-157)
- Test: `app/tests/test_kit_redes.py` (classe `TestParseGancho`, linhas 9-62)

**Interfaces:**
- Consumes: `content._txt(v) -> str` (já existe, linha 124), `content.MAX_REELS = 3` (linha 121)
- Produces: `content.parse_gancho(bruto) -> dict` com as chaves fixas
  `{"frase": str, "paciente": str, "limites": list[str], "reels": list[dict]}`,
  onde cada reel é `{"titulo": str, "gancho": str, "roteiro": list[str], "apoio": str}`.
  **A chave do texto de abertura passa a ser `gancho`, não `angulo`.**

- [ ] **Step 1: Atualizar os seis testes que mudam de significado**

Estes testes existem e afirmam `reels[0]["angulo"]`. Com o formato novo a chave é `gancho`.
**Atualize-os, não os apague nem enfraqueça** — vários deles passam a ser a prova de que o
estoque antigo continua funcionando.

Em `app/tests/test_kit_redes.py`, classe `TestParseGancho`:

```python
    def test_json_formato_antigo_com_angulo_vira_gancho(self):
        """O estoque de reserva/classicos esta cheio deste formato: `angulo` sem
        roteiro. Se parar de funcionar, todo estudo ja na fila sai com o kit vazio."""
        bruto = ('{"frase": "Perdeu 20,9% do peso.",'
                 ' "reels": [{"angulo": "Nao e forca de vontade.", "apoio": "O comparador perdeu 3,1%."}]}')
        r = self.c.parse_gancho(bruto)
        self.assertEqual(r["frase"], "Perdeu 20,9% do peso.")
        self.assertEqual(len(r["reels"]), 1)
        self.assertEqual(r["reels"][0]["gancho"], "Nao e forca de vontade.")
        self.assertEqual(r["reels"][0]["apoio"], "O comparador perdeu 3,1%.")
        self.assertEqual(r["reels"][0]["roteiro"], [])

    def test_texto_puro_antigo_vira_um_reel(self):
        """Formato legado: o banco de reserva/classicos esta cheio deles."""
        r = self.c.parse_gancho("Fale sobre obesidade como doenca cronica.")
        self.assertEqual(r["frase"], "")
        self.assertEqual(len(r["reels"]), 1)
        self.assertEqual(r["reels"][0]["gancho"], "Fale sobre obesidade como doenca cronica.")
        self.assertEqual(r["reels"][0]["apoio"], "")

    def test_item_sem_angulo_e_descartado(self):
        r = self.c.parse_gancho('{"reels": [{"apoio": "orfao"}, {"angulo": "bom"}]}')
        self.assertEqual(len(r["reels"]), 1)
        self.assertEqual(r["reels"][0]["gancho"], "bom")

    def test_nunca_imprime_none(self):
        r = self.c.parse_gancho('{"frase": null, "reels": [{"angulo": "x", "apoio": null}]}')
        self.assertEqual(r["frase"], "")
        self.assertEqual(r["reels"][0]["apoio"], "")
```

`test_vazio_nao_quebra`, `test_json_so_com_frase`, `test_item_sem_apoio` e `test_corta_em_tres`
continuam iguais — não os toque.

- [ ] **Step 2: Escrever os testes do formato novo**

Acrescentar à mesma classe `TestParseGancho`:

```python
    def test_json_novo_completo(self):
        bruto = ('{"frase": "A frase do post.",'
                 ' "paciente": "Como eu explico na consulta.",'
                 ' "limites": ["Nao prometa resultado.", "Nao cite marca."],'
                 ' "reels": [{"titulo": "Quando dizem que e psicologico",'
                 '            "gancho": "Se te disseram que era da sua cabeca, escuta isso.",'
                 '            "roteiro": ["Comece contando a situacao.", "Explique o que muda."],'
                 '            "apoio": "47 mulheres na pos-menopausa."}]}')
        r = self.c.parse_gancho(bruto)
        self.assertEqual(r["frase"], "A frase do post.")
        self.assertEqual(r["paciente"], "Como eu explico na consulta.")
        self.assertEqual(r["limites"], ["Nao prometa resultado.", "Nao cite marca."])
        self.assertEqual(len(r["reels"]), 1)
        p = r["reels"][0]
        self.assertEqual(p["titulo"], "Quando dizem que e psicologico")
        self.assertEqual(p["gancho"], "Se te disseram que era da sua cabeca, escuta isso.")
        self.assertEqual(p["roteiro"], ["Comece contando a situacao.", "Explique o que muda."])
        self.assertEqual(p["apoio"], "47 mulheres na pos-menopausa.")

    def test_campos_novos_ausentes_viram_vazio(self):
        """Formato antigo nao tem paciente/limites/titulo/roteiro -- nao pode virar None."""
        r = self.c.parse_gancho('{"reels": [{"angulo": "so o angulo"}]}')
        self.assertEqual(r["paciente"], "")
        self.assertEqual(r["limites"], [])
        self.assertEqual(r["reels"][0]["titulo"], "")
        self.assertEqual(r["reels"][0]["roteiro"], [])

    def test_roteiro_com_lixo_dentro_e_limpo(self):
        r = self.c.parse_gancho(
            '{"reels": [{"gancho": "g", "roteiro": ["passo bom", "", null, "outro"]}]}')
        self.assertEqual(r["reels"][0]["roteiro"], ["passo bom", "outro"])

    def test_roteiro_que_nao_e_lista_nao_quebra(self):
        r = self.c.parse_gancho('{"reels": [{"gancho": "g", "roteiro": "virou string"}]}')
        self.assertEqual(r["reels"][0]["roteiro"], [])

    def test_limites_corta_no_teto(self):
        itens = ",".join('"limite %d"' % i for i in range(9))
        r = self.c.parse_gancho('{"limites": [%s]}' % itens)
        self.assertEqual(len(r["limites"]), self.c.MAX_LIMITES)

    def test_roteiro_corta_no_teto(self):
        passos = ",".join('"passo %d"' % i for i in range(9))
        r = self.c.parse_gancho('{"reels": [{"gancho": "g", "roteiro": [%s]}]}' % passos)
        self.assertEqual(len(r["reels"][0]["roteiro"]), self.c.MAX_PASSOS)

    def test_json_cortado_nao_vira_pauta(self):
        """O defeito que mais dói: com a IA estourando o limite de tokens, o JSON
        chega pela metade, o json.loads falha e o texto bruto virava UMA pauta --
        o PDF imprimia {"frase":... na cara do assinante pagante."""
        cortado = '{"frase": "A frase do post.", "reels": [{"gancho": "Se te disser'
        r = self.c.parse_gancho(cortado)
        self.assertEqual(r["reels"], [], "JSON cortado nao pode virar pauta")
        self.assertEqual(r["frase"], "")

    def test_lista_json_tambem_nao_vira_pauta(self):
        r = self.c.parse_gancho('[{"gancho": "veio lista em vez de objeto"}')
        self.assertEqual(r["reels"], [])

    def test_texto_que_so_comeca_com_chave_no_meio_ainda_vira_pauta(self):
        """Texto legado de verdade nao comeca com { -- so o JSON cortado comeca."""
        r = self.c.parse_gancho("Fale que {isto} nao e JSON.")
        self.assertEqual(len(r["reels"]), 1)
```

- [ ] **Step 3: Rodar e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_kit_redes.TestParseGancho -v`
Expected: FAIL — `KeyError: 'gancho'` nos testes novos e nos quatro atualizados.

- [ ] **Step 4: Implementar**

Em `app/content.py`, logo depois de `MAX_REELS = 3` (linha 121):

```python
MAX_PASSOS = 6      # passos do roteiro de um Reels
MAX_LIMITES = 6     # itens do bloco "o que nao da pra afirmar"
```

Depois de `_txt` (linha 124-126), acrescentar:

```python
def _lista(v, limite):
    """Lista de strings limpas a partir do que a IA devolver. Nao levanta se vier
    string, None ou dict no lugar da lista."""
    if not isinstance(v, list):
        return []
    saida = [_txt(x) for x in v]
    return [s for s in saida if s][:limite]


def _kit_vazio():
    return {"frase": "", "paciente": "", "limites": [], "reels": []}
```

E substituir `parse_gancho` inteira (linhas 129-157) por:

```python
def parse_gancho(bruto):
    """Normaliza o campo `gancho` para
    {"frase", "paciente", "limites", "reels": [{"titulo","gancho","roteiro","apoio"}]}.

    Aceita QUATRO formatos, porque os quatro existem no banco:
      1. JSON novo   -> gancho/roteiro/titulo por pauta + paciente + limites
      2. JSON atual  -> `angulo` vira `gancho`, sem roteiro (o estoque de
         reserva_resumos esta cheio destes; quebrar aqui esvazia o kit de todo
         estudo ja na fila)
      3. texto puro  -> formato legado (classicos/digests antigos); vira uma pauta
      4. lixo/vazio  -> estrutura vazia

    Nunca levanta e nunca devolve None em campo nenhum: isto roda no caminho do PDF
    do assinante, onde uma excecao custa o envio do dia.
    """
    texto = _txt(bruto)
    if not texto:
        return _kit_vazio()
    try:
        dados = json.loads(texto)
    except Exception:
        dados = None
    if not isinstance(dados, dict):
        # JSON que nao fechou (IA estourou o teto de tokens) NAO pode virar pauta:
        # o PDF imprimiria {"frase":... na cara do assinante. Melhor faltar o kit.
        if texto.lstrip()[:1] in ("{", "["):
            return _kit_vazio()
        return {"frase": "", "paciente": "", "limites": [],
                "reels": [{"titulo": "", "gancho": texto, "roteiro": [], "apoio": ""}]}
    reels = []
    for item in (dados.get("reels") or []):
        if not isinstance(item, dict):
            continue
        # `angulo` e o nome antigo de `gancho` -- compatibilidade com o estoque
        gancho = _txt(item.get("gancho")) or _txt(item.get("angulo"))
        if not gancho:
            continue                      # item sem abertura nao rende video nenhum
        reels.append({"titulo": _txt(item.get("titulo")),
                      "gancho": gancho,
                      "roteiro": _lista(item.get("roteiro"), MAX_PASSOS),
                      "apoio": _txt(item.get("apoio"))})
    return {"frase": _txt(dados.get("frase")),
            "paciente": _txt(dados.get("paciente")),
            "limites": _lista(dados.get("limites"), MAX_LIMITES),
            "reels": reels[:MAX_REELS]}
```

- [ ] **Step 5: Rodar e confirmar que passa**

Run: `cd app && python3 -m unittest tests.test_kit_redes -v`
Expected: PASS.

Se `TestKitHtml` quebrar aqui, **pare e reporte** — `_kit_html` ainda lê a chave antiga e é
o Task 3 que a atualiza. É esperado que quebre; o que não pode é você "consertar" enfraquecendo
o teste.

- [ ] **Step 6: Rodar a suíte inteira**

Run: `cd app && python3 -m unittest discover -s tests`
Expected: as falhas, se houver, são só de `TestKitHtml`/`TestMontarHtmlKit` (Task 3). Reporte o
total `Ran N tests` e o nome de cada falha.

- [ ] **Step 7: Commit**

```bash
git add app/content.py app/tests/test_kit_redes.py
git commit -m "feat(kit): parse do formato novo, compat com o estoque e fim do JSON cru no PDF"
```

---

### Task 2: O prompt novo e o teto de tokens

**Files:**
- Modify: `app/content.py` (`SYS_GANCHO`, linhas 8-26; `max_tokens` na linha 166)
- Test: `app/tests/test_kit_redes.py` (classe `TestPromptGancho`, linha ~145)

**Interfaces:**
- Consumes: nada de tasks anteriores.
- Produces: `content.SYS_GANCHO` (str) descrevendo o schema que o Task 1 parseia.

Por que o teto sobe: uma saída real, gerada sobre um estudo do Europe PMC (testosterona
transdérmica na pós-menopausa, EJOG jun/2026), deu **934 tokens**. O teto hoje é **900**.
Sem subir, o JSON chega cortado — e cai no caminho do `test_json_cortado_nao_vira_pauta`,
ou seja, o assinante fica sem kit nenhum.

- [ ] **Step 1: Escrever os testes**

Acrescentar à classe `TestPromptGancho` em `app/tests/test_kit_redes.py`:

```python
    def test_prompt_descreve_o_schema_novo(self):
        for chave in ('"paciente"', '"limites"', '"gancho"', '"roteiro"', '"titulo"'):
            self.assertIn(chave, self.c.SYS_GANCHO, f"schema sem {chave}")

    def test_prompt_manda_falar_com_o_paciente_e_proibe_metodologia(self):
        s = self.c.SYS_GANCHO.lower()
        self.assertIn("paciente", s)
        self.assertIn("metodologia", s)
        self.assertIn("comparador", s)

    def test_prompt_proibe_jargao_de_marketing(self):
        """O texto gerado ia com 'nomeia a cena'/'vira a chave' -- quem le e medico
        ou social media, nao publicitario."""
        s = self.c.SYS_GANCHO.lower()
        for termo in ("nomeia a cena", "vira a chave", "prova por baixo"):
            self.assertIn(termo, s, f"o prompt precisa PROIBIR '{termo}' pelo nome")

    def test_prompt_mantem_as_travas_do_cfm(self):
        s = self.c.SYS_GANCHO.lower()
        for termo in ("cfm", "receita", "resultado"):
            self.assertIn(termo, s)

    def test_teto_de_tokens_cabe_na_saida_real(self):
        """Saida real medida: 934 tokens. Com 900 o JSON chega cortado."""
        import inspect
        fonte = inspect.getsource(self.c.gerar_conteudo)
        self.assertIn("SYS_GANCHO", fonte)
        self.assertNotIn("max_tokens=900", fonte)
        self.assertIn("max_tokens=2500", fonte)
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_kit_redes.TestPromptGancho -v`
Expected: FAIL — o prompt atual não tem as chaves novas nem a proibição de jargão.

- [ ] **Step 3: Substituir `SYS_GANCHO`**

Em `app/content.py`, trocar o bloco `SYS_GANCHO = (...)` (linhas 8-26) por:

```python
SYS_GANCHO = (
    "Você prepara o material de redes sociais de um médico a partir de UM estudo. "
    "Ele trata obesidade, menopausa e reposição hormonal, e produz SÓ REELS (vídeo curto). "
    "Responda SÓ JSON, sem cercas de código, neste formato:\n"
    '{"frase":"...","paciente":"...","limites":["..."],'
    '"reels":[{"titulo":"...","gancho":"...","roteiro":["...","..."],"apoio":"..."}]}\n'
    "\n"
    "REGRA CENTRAL DAS PAUTAS — o público é o PACIENTE do médico, não o médico. O paciente "
    "não lê estudo e não se interessa por desenho de pesquisa. Cada pauta ABRE numa dor que "
    "ele reconhece em si mesmo e TERMINA apontando para algo que se resolve com acompanhamento "
    "médico. O estudo é a prova que sustenta, nunca a manchete. É PROIBIDO fazer pauta sobre "
    "metodologia, grupo comparador, tamanho de amostra ou tempo de seguimento — isso é conversa "
    "de médico para médico e faz o paciente rolar o feed.\n"
    "\n"
    "- `frase`: o achado em linguagem de paciente, UMA frase que se sustenta sozinha como "
    "imagem de post.\n"
    "- `paciente`: como o MÉDICO explica esse achado ao paciente no consultório — 2 a 4 frases, "
    "linguagem de conversa, incluindo a ressalva honesta que mantém a confiança. É para o médico "
    "ler antes da consulta, não para postar.\n"
    "- `limites`: 3 a 5 itens do que NÃO pode ser dito sobre ESTE estudo — específicos dele, "
    "nunca regras genéricas. Puxe do próprio texto: amostra pequena, uso fora de bula, desfecho "
    "que é questionário e não exame, limitação que os autores declararam. Somado ao que o CFM "
    "veda: promessa de resultado, antes/depois, promoção de medicamento de receita a leigo, "
    "convocação para consulta.\n"
    "- `reels`: de 1 a 3 pautas. PREFIRA MENOS — se o estudo só sustenta uma dor de verdade, "
    "devolva UMA. Pauta inventada para fechar número faz o médico parar de ler o bloco. Cada "
    "pauta sai de uma DOR DIFERENTE, nunca do mesmo assunto com outras palavras.\n"
    "  - `titulo`: 3 a 6 palavras nomeando o assunto da pauta, para o médico achar de relance.\n"
    "  - `gancho`: a frase EXATA dos 3 primeiros segundos do vídeo. Fala com o paciente na "
    "segunda pessoa, nomeia a dor dele, e NÃO cita o estudo.\n"
    "  - `roteiro`: 3 a 5 passos NA ORDEM DE GRAVAÇÃO, cada um uma linha do que o médico diz. "
    "Um dos passos, sempre, é a ressalva honesta. O último fecha na dor ou aponta o caminho. "
    "Quem lê tem que conseguir gravar sem saber nada de medicina. "
    "ESCREVA CADA PASSO EM PORTUGUÊS SIMPLES, como quem instrui uma pessoa: 'Comece contando "
    "que...', 'Explique que...', 'Diga a ressalva:...', 'Termine assim:...'. É PROIBIDO jargão "
    "de marketing — não escreva 'nomeia a cena', 'vira a chave', 'prova por baixo', 'quebra de "
    "padrão' nem 'CTA'; quem lê é médico ou social media, não publicitário.\n"
    "  - `apoio`: o dado do estudo que sustenta aquela pauta, em uma linha. É para o médico "
    "conferir, não para ser dito no vídeo.\n"
    "\n"
    "ÉTICA (CFM, inegociável): não prometa milagre/cura, não garanta resultado, "
    "NÃO promova remédio de receita para leigo (fale do CONCEITO, não do 'use tal remédio'), "
    "sem sensacionalismo, sem chamada para ação ('agende sua consulta'). "
    "Nunca invente número que não esteja na fonte. Tudo em português do Brasil.")
```

- [ ] **Step 4: Subir o teto de tokens**

Em `app/content.py`, linha 166, dentro de `gerar_conteudo`:

```python
        # 2500, nao 900: a saida real medida (frase + paciente + limites + 2 pautas com
        # roteiro) deu 934 tokens. Com o teto antigo o JSON chega cortado e o kit some.
        gerar_gancho = lambda a: claude(SONNET, _prompt_gancho(a), system=SYS_GANCHO, max_tokens=2500)
```

- [ ] **Step 5: Rodar e confirmar que passa**

Run: `cd app && python3 -m unittest tests.test_kit_redes -v`
Expected: PASS em `TestPromptGancho` e `TestParseGancho`.

- [ ] **Step 6: Commit**

```bash
git add app/content.py app/tests/test_kit_redes.py
git commit -m "feat(kit): prompt do paciente-primeiro, sem jargao, e teto de tokens que cabe"
```

---

### Task 3: Cards no PDF, bloco do CFM e bloco do paciente

**Files:**
- Modify: `app/pdf.py` (`_kit_html` linhas 222-266; CSS do kit linhas ~348-368; `montar_html` linhas ~275-295)
- Modify: `app/site_web.py` (CSS do kit, linhas ~238-255)
- Test: `app/tests/test_kit_redes.py` (classes `TestKitHtml` e `TestMontarHtmlKit`)

**Interfaces:**
- Consumes: `content.parse_gancho(bruto) -> dict` do Task 1, com reels
  `{"titulo","gancho","roteiro","apoio"}` e as chaves `paciente` e `limites`.
- Produces: `pdf._paciente_html(gancho_bruto) -> str` (novo) e `pdf._kit_html(gancho_bruto, artigo) -> str`.

- [ ] **Step 1: Escrever os testes**

Acrescentar à classe `TestKitHtml` em `app/tests/test_kit_redes.py`:

```python
    def test_pauta_vira_card_com_roteiro_numerado(self):
        bruto = ('{"reels": [{"titulo": "O assunto", "gancho": "A abertura.",'
                 ' "roteiro": ["Comece contando.", "Termine assim."], "apoio": "47 mulheres."}]}')
        h = self.pdf._kit_html(bruto, {"titulo": "T"})
        self.assertIn("reel-card", h)
        self.assertIn("A abertura.", h)
        self.assertIn("<ol", h)
        self.assertIn("Comece contando.", h)
        self.assertIn("Termine assim.", h)
        self.assertIn("47 mulheres.", h)
        self.assertIn("O assunto", h)

    def test_pauta_sem_roteiro_nao_deixa_lista_vazia(self):
        """Formato antigo do estoque: so `angulo`, sem roteiro."""
        h = self.pdf._kit_html('{"reels": [{"angulo": "so a abertura"}]}', {"titulo": "T"})
        self.assertIn("so a abertura", h)
        self.assertNotIn("<ol", h)

    def test_limites_viram_bloco_proprio(self):
        h = self.pdf._kit_html('{"limites": ["Nao prometa.", "Nao cite marca."]}', {"titulo": "T"})
        self.assertIn("kit-limites", h)
        self.assertIn("Nao prometa.", h)
        self.assertIn("Nao cite marca.", h)

    def test_sem_limites_nao_deixa_bloco_orfao(self):
        h = self.pdf._kit_html('{"reels": [{"gancho": "g"}]}', {"titulo": "T"})
        self.assertNotIn("kit-limites", h)

    def test_escapa_script_no_roteiro_e_nos_limites(self):
        bruto = ('{"limites": ["<script>alert(1)</script>"],'
                 ' "reels": [{"gancho": "g", "roteiro": ["<script>alert(2)</script>"]}]}')
        h = self.pdf._kit_html(bruto, {"titulo": "T"})
        self.assertNotIn("<script>", h)
        self.assertIn("&lt;script&gt;", h)

    def test_paciente_vira_bloco_proprio(self):
        h = self.pdf._paciente_html('{"paciente": "Eu explico assim na consulta."}')
        self.assertIn("Eu explico assim na consulta.", h)
        self.assertIn("paciente", h)

    def test_sem_paciente_devolve_vazio(self):
        self.assertEqual(self.pdf._paciente_html('{"frase": "so a frase"}'), "")
        self.assertEqual(self.pdf._paciente_html(""), "")

    def test_paciente_escapa_html(self):
        h = self.pdf._paciente_html('{"paciente": "<script>alert(1)</script>"}')
        self.assertNotIn("<script>", h)

    def test_json_cortado_nao_imprime_chave_no_html(self):
        """A regressao que mais dói: JSON cortado virando texto cru no PDF."""
        h = self.pdf._kit_html('{"frase": "x", "reels": [{"gancho": "corta', {"titulo": "T"})
        self.assertNotIn('{"frase"', h)
        self.assertNotIn("reel-card", h)
```

E à classe `TestMontarHtmlKit`:

```python
    def test_bloco_do_paciente_entra_no_pdf_antes_do_kit(self):
        conteudo = dict(self.conteudo,
                        gancho='{"paciente": "Explico assim.", "reels": [{"gancho": "g"}]}')
        h = self.pdf.montar_html(self.artigo, conteudo, self.tema)
        self.assertIn("Explico assim.", h)
        self.assertLess(h.index("Explico assim."), h.index('class="kit"'),
                        "o bloco clinico fica ANTES do kit de marketing")

    def test_classes_novas_existem_no_css_do_pdf_e_do_site(self):
        """O site tem copia PROPRIA do CSS e renderiza o mesmo HTML via pdf._kit_html
        (site_web.py:1976). Classe que so existe num dos dois sai sem estilo la."""
        import site_web
        h = self.pdf.montar_html(self.artigo, dict(self.conteudo,
            gancho='{"paciente":"p","limites":["l"],"reels":[{"gancho":"g","roteiro":["r"]}]}'),
            self.tema)
        for classe in ("reel-card", "reel-gancho", "reel-roteiro", "reel-apoio",
                       "reel-mini", "kit-limites", "paciente"):
            self.assertIn(f".{classe}", h, f"{classe} sem regra no CSS do PDF")
            self.assertIn(f".{classe}", site_web._CSS, f"{classe} sem regra no CSS do site")
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_kit_redes -v`
Expected: FAIL — `AttributeError: module 'pdf' has no attribute '_paciente_html'`.

- [ ] **Step 3: Reescrever `_kit_html` e criar `_paciente_html`**

Em `app/pdf.py`, substituir a função `_kit_html` (linhas 222-266) por:

```python
def _paciente_html(gancho_bruto):
    """Bloco clinico: a fala que o medico usa no consultorio pra explicar o achado.

    Fica ANTES do kit de marketing de proposito -- o clinico junto do clinico. O
    medico le e para no fim do grafico; quem vai produzir post pula pro final.
    """
    import content
    dados = content.parse_gancho(gancho_bruto)
    if not dados["paciente"]:
        return ""
    return ('<div class="paciente"><div class="pac-rot">Como explicar pro paciente</div>'
            f'<p>{_html.escape(dados["paciente"])}</p></div>')


def _kit_html(gancho_bruto, artigo):
    """Kit de post no rodape: recorte do paper + a frase + as pautas de Reels + os
    limites do CFM.

    Os dois primeiros blocos sao pensados para PRINT RECORTADO -- o medico ja fazia
    isso na mao, printando o PDF do artigo. Por isso nao levam a marca do Diego: quem
    posta e o assinante. O terceiro e briefing pra equipe de marketing, e por isso e
    visualmente diferente: se parecesse com os outros, alguem recortaria a instrucao
    junto e postaria. O quarto sao os limites daquele estudo -- fica por ESTUDO e nao
    por pauta, porque a evidencia e a mesma pras tres.
    """
    import content
    esc = _html.escape
    dados = content.parse_gancho(gancho_bruto)
    titulo = (artigo.get("titulo_original") or artigo.get("titulo") or "").strip()
    blocos = []

    if titulo:
        revista = " · ".join(x for x in [(artigo.get("fonte") or "").strip(),
                                         (artigo.get("data") or "").strip()] if x)
        doi = (artigo.get("doi") or "").strip()
        blocos.append(
            f'<div class="kit-paper"><div class="kit-rot">1 &middot; O estudo</div>'
            f'<div class="paper-box">'
            f'<div class="paper-rev">{esc(revista)}</div>'
            f'<p class="paper-tit">{esc(titulo)}</p>'
            + (f'<div class="paper-doi">DOI {esc(doi)}</div>' if doi else "")
            + '</div></div>')

    if dados["frase"]:
        blocos.append(
            f'<div class="kit-frase"><div class="kit-rot">2 &middot; A frase</div>'
            f'<div class="frase-box"><p>{esc(dados["frase"])}</p></div></div>')

    if dados["reels"]:
        cards = []
        for i, r in enumerate(dados["reels"], 1):
            rotulo = f'<span class="reel-tit">{esc(r["titulo"])}</span>' if r["titulo"] else ""
            passos = "".join(f"<li>{esc(p)}</li>" for p in r["roteiro"])
            roteiro = (f'<p class="reel-mini">O que falar, nesta ordem</p>'
                       f'<ol class="reel-roteiro">{passos}</ol>') if passos else ""
            apoio = (f'<p class="reel-apoio"><b>Dado do estudo:</b> {esc(r["apoio"])}</p>'
                     if r["apoio"] else "")
            cards.append(
                f'<div class="reel-card">'
                f'<div class="reel-top"><span class="reel-n">{i}</span>{rotulo}</div>'
                f'<p class="reel-mini">Primeiros 3 segundos</p>'
                f'<p class="reel-gancho">{esc(r["gancho"])}</p>'
                f'{roteiro}{apoio}</div>')
        blocos.append(
            f'<div class="kit-brief"><div class="kit-rot">3 &middot; Reels que saem deste estudo</div>'
            f'<div class="reel-cards">{"".join(cards)}</div></div>')

    if dados["limites"]:
        itens = "".join(f"<li>{esc(x)}</li>" for x in dados["limites"])
        blocos.append(
            f'<div class="kit-limites"><div class="kit-rot">4 &middot; O que n&atilde;o d&aacute; pra afirmar</div>'
            f'<ul>{itens}</ul></div>')

    if not blocos:
        return ""
    return f'<div class="kit">{"".join(blocos)}</div>'
```

- [ ] **Step 4: Encaixar o bloco do paciente em `montar_html`**

Em `app/pdf.py`, dentro de `montar_html`, junto das outras variáveis (perto da linha 285):

```python
    paciente_html = _paciente_html(conteudo.get("gancho", ""))
```

E no corpo do HTML, entre `{grafico_html}` e `{kit_html}`:

```html
    {grafico_html}
    {paciente_html}
    {kit_html}
```

- [ ] **Step 5: Trocar o CSS do kit no `pdf.py`**

Em `app/pdf.py`, substituir as regras `.reels`, `.reel`, `.reel b`, `.reel-n` e `.reel-apoio`
(dentro do bloco CSS, a partir da linha ~362) por:

```css
  .paciente {{ border:1px solid #d8ddd7; border-left:4px solid {cor}; background:#f7faf8;
           padding:17px 20px; margin:26px 0 0; border-radius:0 8px 8px 0; break-inside:avoid; }}
  .pac-rot {{ font-family:system-ui,sans-serif; font-size:13px; letter-spacing:.08em;
           text-transform:uppercase; color:{cor}; font-weight:700; margin-bottom:9px; }}
  .paciente p {{ margin:0; font-size:18px; line-height:1.62; }}
  .reel-cards {{ display:flex; flex-direction:column; gap:14px; }}
  .reel-card {{ border:1px solid #d8ddd7; border-radius:8px; background:#f8faf9;
           padding:16px 18px; break-inside:avoid; }}
  .reel-top {{ display:flex; align-items:center; gap:9px; margin-bottom:11px; }}
  .reel-n {{ flex:0 0 22px; height:22px; border-radius:50%; background:{cor}; color:#fff;
           font-family:system-ui,sans-serif; font-size:12px; font-weight:700;
           display:inline-flex; align-items:center; justify-content:center; }}
  .reel-tit {{ font-family:system-ui,sans-serif; font-size:11px; letter-spacing:.11em;
           text-transform:uppercase; color:#6f7d78; font-weight:700; }}
  .reel-mini {{ font-family:system-ui,sans-serif; font-size:11px; letter-spacing:.1em;
           text-transform:uppercase; color:#6f7d78; font-weight:700; margin:0 0 6px; }}
  .reel-gancho {{ font-size:19px; line-height:1.36; color:#16211c; margin:0 0 13px;
           padding-left:11px; border-left:3px solid #c9a227; }}
  .reel-roteiro {{ margin:0 0 13px; padding-left:20px; }}
  .reel-roteiro li {{ font-size:16.5px; line-height:1.55; margin-bottom:5px; color:#2c3a34; }}
  .reel-apoio {{ background:#eef3f0; border-radius:6px; padding:9px 12px; font-size:15px;
           line-height:1.5; color:#46544e; font-family:system-ui,sans-serif; margin:0; }}
  .reel-apoio b {{ color:#24332c; }}
  .kit-limites {{ border:1px solid #e6d6d2; border-left:4px solid #9c3226; background:#fdf7f6;
           padding:16px 19px; border-radius:0 8px 8px 0; break-inside:avoid; }}
  .kit-limites .kit-rot {{ color:#9c3226; }}
  .kit-limites ul {{ margin:0; padding-left:20px; }}
  .kit-limites li {{ font-size:16px; line-height:1.55; margin-bottom:7px; color:#4a3a37; }}
```

Nota: o CSS de `pdf.py` está dentro de uma f-string — as chaves são **duplicadas** (`{{`/`}}`)
e `{cor}` é a cor do tema, que já existe como variável na função. Não desduplique.

- [ ] **Step 6: Espelhar o CSS em `site_web.py`**

Em `app/site_web.py`, no `_CSS` (linhas ~238-255), substituir as regras `.reels`, `.reel`,
`.reel b` e `.reel-n` pelo bloco abaixo. Aqui **não** é f-string: chaves simples, e a cor do tema
vira o dourado fixo do site (`--ouro`), porque o site não sabe o tema do estudo. O site é escuro,
mas os cartões ficam claros de propósito — o kit é uma ilha clara na página, como já é hoje com
`.paper-box` e `.frase-box`.

```css
.paciente{border:1px solid #d8ddd7;border-left:4px solid var(--ouro);background:#f7faf8;padding:16px 18px;margin:22px 0 0;border-radius:0 8px 8px 0}
.pac-rot{font-family:system-ui,sans-serif;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#7a4b2b;font-weight:700;margin-bottom:8px}
.paciente p{margin:0;font-size:17px;line-height:1.62;color:#20302b}
.reel-cards{display:flex;flex-direction:column;gap:12px}
.reel-card{border:1px solid #d8ddd7;border-radius:8px;background:#f8faf9;padding:15px 17px}
.reel-top{display:flex;align-items:center;gap:9px;margin-bottom:10px}
.reel-n{flex:0 0 22px;height:22px;border-radius:50%;background:#7a4b2b;color:#fff;font-family:system-ui,sans-serif;font-size:12px;font-weight:700;display:inline-flex;align-items:center;justify-content:center}
.reel-tit{font-family:system-ui,sans-serif;font-size:11px;letter-spacing:.11em;text-transform:uppercase;color:#6f7d78;font-weight:700}
.reel-mini{font-family:system-ui,sans-serif;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#6f7d78;font-weight:700;margin:0 0 6px}
.reel-gancho{font-size:18px;line-height:1.36;color:#16211c;margin:0 0 12px;padding-left:11px;border-left:3px solid var(--ouro)}
.reel-roteiro{margin:0 0 12px;padding-left:20px}
.reel-roteiro li{font-size:16px;line-height:1.55;margin-bottom:5px;color:#2c3a34}
.reel-apoio{background:#eef3f0;border-radius:6px;padding:9px 12px;font-size:14.5px;line-height:1.5;color:#46544e;font-family:system-ui,sans-serif;margin:0}
.reel-apoio b{color:#24332c}
.kit-limites{border:1px solid #e6d6d2;border-left:4px solid #9c3226;background:#fdf7f6;padding:15px 18px;border-radius:0 8px 8px 0}
.kit-limites .kit-rot{color:#9c3226}
.kit-limites ul{margin:0;padding-left:20px}
.kit-limites li{font-size:15.5px;line-height:1.55;margin-bottom:7px;color:#4a3a37}
```

- [ ] **Step 7: Rodar e confirmar que passa**

Run: `cd app && python3 -m unittest tests.test_kit_redes -v`
Expected: PASS, incluindo `test_classes_novas_existem_no_css_do_pdf_e_do_site`.

- [ ] **Step 8: Renderizar as 12 combinações e conferir que não sobra marcador**

Run:

```bash
cd app && python3 -c "
import pdf, json
casos = {
 'completo': '{\"frase\":\"f\",\"paciente\":\"p\",\"limites\":[\"l1\",\"l2\"],\"reels\":[{\"titulo\":\"t\",\"gancho\":\"g\",\"roteiro\":[\"r1\",\"r2\"],\"apoio\":\"a\"}]}',
 'formato antigo': '{\"frase\":\"f\",\"reels\":[{\"angulo\":\"g\",\"apoio\":\"a\"}]}',
 'texto legado': 'Fale sobre obesidade.',
 'json cortado': '{\"frase\":\"f\",\"reels\":[{\"gancho\":\"cor',
 'vazio': '',
}
for nome, g in casos.items():
    h = pdf._kit_html(g, {'titulo':'T','fonte':'NEJM','data':'2026','doi':'10.1/x'})
    p = pdf._paciente_html(g)
    ruim = [m for m in ('{\"', 'None', 'angulo') if m in h + p]
    print(f'{nome:16} kit={len(h):>5}B paciente={len(p):>4}B  {\"OK\" if not ruim else \"SOBROU \"+str(ruim)}')
"
```

Expected: nenhum caso com `SOBROU`. O caso `json cortado` deve dar `kit` pequeno (só o cartão do
estudo) e `paciente=0`.

- [ ] **Step 9: Rodar a suíte inteira**

Run: `cd app && python3 -m unittest discover -s tests`
Expected: PASS, 100% verde. Reporte o total `Ran N tests`.

- [ ] **Step 10: Commit**

```bash
git add app/pdf.py app/site_web.py app/tests/test_kit_redes.py
git commit -m "feat(kit): pauta vira card com roteiro, bloco do CFM e bloco do paciente"
```

---

## Depois do plano (não são tasks)

1. **Deploy e revisão das 18h.** O rascunho de amanhã passa a ser gerado com o prompt novo e
   chega ao curador para aprovar antes de qualquer assinante receber. É o único teste real —
   não há Chromium no ambiente de desenvolvimento, então a diagramação nunca foi vista.
2. **Conferir o primeiro PDF de verdade**, em especial a quebra de página: os cartões têm
   `break-inside:avoid`, mas três pautas com roteiro fazem o PDF crescer cerca de uma página.
   Se ficar longo, o corte natural é o prompt gerar duas pautas em vez de três.
3. **O estoque de reserva continua com ganchos antigos.** Eles renderizam (sem roteiro, sem
   limites, sem bloco do paciente) até serem consumidos. Não há backfill previsto.
