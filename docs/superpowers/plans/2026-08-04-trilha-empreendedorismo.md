# Trilha de Empreendedorismo Médico — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar, todo sábado, uma peça semanal de empreendedorismo médico em PDF pelo WhatsApp, cada assinante na sua própria posição da trilha de 12 peças.

**Architecture:** Módulo `trilha.py` isolado, com 3 tabelas próprias. Não modifica `daily.py`. Reaproveita a infraestrutura existente de assinantes (`subscribers.ativos`/`slot_de`), envio (`deliver.enviar_pdf`), renderização (`pdf.gerar_pdf`) e sessão de site. O agendador de `serve.py` ganha um tick de trilha por slot, que só faz algo aos sábados.

**Tech Stack:** Python stdlib (sem pip), SQLite em dev/teste e Postgres/Supabase em produção via `db._conn()`, `unittest`, HTML server-side em `site_web.py`, Chromium headless pra gerar PDF.

## Global Constraints

- **Sem dependência nova.** O container é stdlib + psycopg2 já existente. Não adicionar pacote.
- **Todo SQL roda em SQLite E Postgres.** Placeholder é `?` (o `_Wrap` traduz pra `%s`). Usar `ON CONFLICT (...) DO NOTHING` / `DO UPDATE SET ... = excluded.x`, que funcionam nos dois.
- **Toda tabela nova entra em `db._TABELAS`** (`db.py:262`) — essa lista alimenta `_habilitar_rls()`, que tranca a Data API pública do Supabase. Tabela fora da lista fica **legível pela internet** em produção.
- **Marca em config, não hardcoded.** O nome do produto/trilha sai de `config.TRILHA_NOME`. A trilha ainda não tem nome; o default é provisório e será trocado por um campo, nunca por varredura no código.
- **Não modificar `daily.py`.** Se um task parecer exigir isso, pare e reporte.
- **Nunca `git add -A`.** Outros agentes trabalham neste repo em paralelo; stagear só os arquivos do próprio task.
- **Rodar os testes assim:** `cd app && python3 -m unittest discover -s tests`
- Idioma de código e comentários: português, como o resto do repo.

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `app/trilha.py` (criar) | Domínio da trilha: parse/seed das peças, posição do assinante, montagem e envio de sábado. |
| `app/pdf_trilha.py` (criar) | HTML da peça pra virar PDF. Separado de `pdf.py` (23K, layout de estudo científico) — só compartilha o renderizador `pdf.gerar_pdf`. |
| `app/db.py` (modificar) | 3 tabelas + funções de acesso. |
| `app/site_web.py` (modificar) | `pagina_trilha` e `pagina_admin_trilha`. |
| `app/serve.py` (modificar) | Rotas `/trilha`, `/ferramentas/<slug>`, `/admin/trilha` + tick de sábado no agendador. |
| `app/config.py` (modificar) | `TRILHA_NOME`, `TRILHA_DIA`, `TRILHA_TOTAL`, `TRILHA_DIR`. |
| `seed/trilha/NN-slug.md` (criar) | As 12 peças. **Nesta entrega vão com texto-esqueleto**; a redação final é trabalho separado. |
| `seed/trilha/ferramentas/` (criar) | Arquivos baixáveis. Começa vazio. |
| `app/tests/test_trilha.py` (criar) | Domínio, banco, drip, envio. |
| `app/tests/test_trilha_web.py` (criar) | Rotas, sessão, download, admin. |

---

### Task 1: Tabelas e acesso a banco

**Files:**
- Modify: `app/db.py` (schema em `init()`, lista `_TABELAS` na linha 262, funções novas ao fim do arquivo)
- Test: `app/tests/test_trilha.py`

**Interfaces:**
- Consumes: `db._conn()`, `db.init()`
- Produces:
  - `db.trilha_upsert_peca(numero:int, eixo:str, titulo:str, corpo:str, micro_resultado:str, mentalidade:str, ferramenta_slug:str) -> None`
  - `db.trilha_peca(numero:int) -> dict|None`
  - `db.trilha_posicao(sub_id:str) -> int` — cria em 1 se não existir
  - `db.trilha_registrar_envio(sub_id:str, numero:int) -> bool` — claim atômico, True só na 1ª vez
  - `db.trilha_avancar(sub_id:str, numero:int) -> None` — posição vira `numero+1`
  - `db.trilha_marcar_feito(sub_id:str, numero:int) -> bool`
  - `db.trilha_fez(sub_id:str, numero:int) -> bool`
  - `db.trilha_historico(sub_id:str) -> list[dict]` — envios do assinante, mais recente primeiro
  - `db.trilha_painel() -> list[dict]` — `subscriber_id`, `proxima_peca`, `enviadas`, `feitas`

- [ ] **Step 1: Escrever os testes que falham**

Criar `app/tests/test_trilha.py`:

```python
"""Testes da trilha semanal de empreendedorismo médico. Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _recarregar(tmp):
    """Isola config/db/subscribers/trilha num banco temporário."""
    os.environ["DSCURSO_DATA"] = tmp
    os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(tmp, "t.db")
    for m in ("config", "db", "subscribers", "trilha"):
        if m in sys.modules:
            importlib.reload(sys.modules[m])
    import config, db, subscribers
    importlib.reload(config); importlib.reload(db); importlib.reload(subscribers)
    subscribers._migrado = False
    db.init()
    return config, db, subscribers


class TestBancoTrilha(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg, self.db, self.subs = _recarregar(self.tmp)

    def _peca(self, numero=1):
        self.db.trilha_upsert_peca(numero, "Saber onde você está", f"Peça {numero}",
                                   "corpo", "micro", "mentalidade", "")

    def test_upsert_peca_grava_e_le(self):
        self._peca(1)
        p = self.db.trilha_peca(1)
        self.assertEqual(p["titulo"], "Peça 1")
        self.assertEqual(p["micro_resultado"], "micro")

    def test_upsert_peca_atualiza_em_vez_de_duplicar(self):
        self._peca(1)
        self.db.trilha_upsert_peca(1, "eixo novo", "Título novo", "c", "m", "t", "")
        self.assertEqual(self.db.trilha_peca(1)["titulo"], "Título novo")

    def test_peca_inexistente_devolve_none(self):
        self.assertIsNone(self.db.trilha_peca(13))

    def test_posicao_nasce_em_1(self):
        self.assertEqual(self.db.trilha_posicao("sub-a"), 1)

    def test_registrar_envio_e_idempotente(self):
        self.assertTrue(self.db.trilha_registrar_envio("sub-a", 1))    # 1ª vez
        self.assertFalse(self.db.trilha_registrar_envio("sub-a", 1))   # repetido
        self.assertTrue(self.db.trilha_registrar_envio("sub-a", 2))    # outra peça
        self.assertTrue(self.db.trilha_registrar_envio("sub-b", 1))    # outro assinante

    def test_avancar_move_a_posicao(self):
        self.db.trilha_avancar("sub-a", 1)
        self.assertEqual(self.db.trilha_posicao("sub-a"), 2)

    def test_marcar_feito_e_idempotente(self):
        self.db.trilha_registrar_envio("sub-a", 1)
        self.assertFalse(self.db.trilha_fez("sub-a", 1))
        self.assertTrue(self.db.trilha_marcar_feito("sub-a", 1))
        self.assertTrue(self.db.trilha_fez("sub-a", 1))
        self.assertFalse(self.db.trilha_marcar_feito("sub-a", 1))   # 2º clique não duplica

    def test_marcar_feito_em_peca_nao_enviada_nao_grava(self):
        self.assertFalse(self.db.trilha_marcar_feito("sub-a", 7))
        self.assertFalse(self.db.trilha_fez("sub-a", 7))

    def test_historico_vem_do_mais_recente(self):
        self.db.trilha_registrar_envio("sub-a", 1)
        self.db.trilha_registrar_envio("sub-a", 2)
        h = self.db.trilha_historico("sub-a")
        self.assertEqual([x["numero"] for x in h], [2, 1])

    def test_painel_conta_enviadas_e_feitas(self):
        self.db.trilha_registrar_envio("sub-a", 1)
        self.db.trilha_registrar_envio("sub-a", 2)
        self.db.trilha_marcar_feito("sub-a", 1)
        self.db.trilha_avancar("sub-a", 2)
        linha = [l for l in self.db.trilha_painel() if l["subscriber_id"] == "sub-a"][0]
        self.assertEqual(linha["enviadas"], 2)
        self.assertEqual(linha["feitas"], 1)
        self.assertEqual(linha["proxima_peca"], 3)

    def test_tabelas_novas_estao_na_lista_de_rls(self):
        # fora de _TABELAS, a tabela fica exposta na Data API pública do Supabase
        for t in ("trilha_pecas", "trilha_progresso", "trilha_envios"):
            self.assertIn(t, self.db._TABELAS)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_trilha -v`
Expected: FAIL — `AttributeError: module 'db' has no attribute 'trilha_upsert_peca'`

- [ ] **Step 3: Criar as tabelas**

Em `app/db.py`, dentro do `executescript` de `init()`, logo depois do bloco `CREATE TABLE IF NOT EXISTS serie_itens (...)` e do seu índice, acrescentar:

```sql
            CREATE TABLE IF NOT EXISTS trilha_pecas (
                numero INTEGER PRIMARY KEY,
                eixo TEXT DEFAULT '',
                titulo TEXT DEFAULT '',
                corpo TEXT DEFAULT '',
                micro_resultado TEXT DEFAULT '',
                mentalidade TEXT DEFAULT '',
                ferramenta_slug TEXT DEFAULT '',
                ativa INTEGER DEFAULT 1,
                atualizado_em TEXT
            );
            CREATE TABLE IF NOT EXISTS trilha_progresso (
                subscriber_id TEXT PRIMARY KEY,
                proxima_peca INTEGER DEFAULT 1,
                ultimo_envio TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS trilha_envios (
                subscriber_id TEXT,
                numero INTEGER,
                enviado_em TEXT,
                feito_em TEXT,
                PRIMARY KEY (subscriber_id, numero)
            );
```

E acrescentar as três à lista `_TABELAS` (`app/db.py:262`), no fim:

```python
_TABELAS = ["digests", "login_codes", "sessions", "subscribers",
            "pending_signups", "webhook_events", "cupons", "senha_tokens",
            "curadoria_candidatos", "reserva_resumos", "daily_drafts", "agenda",
            "afiliados", "comissoes", "settings", "envios_slot", "envios_dia",
            "automacoes_renovacao", "avisos_renovacao", "classicos",
            "series", "serie_itens",
            "trilha_pecas", "trilha_progresso", "trilha_envios"]
```

- [ ] **Step 4: Escrever as funções de acesso**

Ao fim de `app/db.py`:

```python
# ---------------------------------------------------------------- trilha
def trilha_upsert_peca(numero, eixo, titulo, corpo, micro_resultado,
                       mentalidade, ferramenta_slug=""):
    """Grava (ou atualiza) a peça `numero`. É upsert de propósito: editar o arquivo
    em seed/trilha/ e redeployar tem que propagar o texto novo, não criar duplicata."""
    from datetime import datetime
    with _conn() as c:
        c.execute(
            "INSERT INTO trilha_pecas "
            "(numero,eixo,titulo,corpo,micro_resultado,mentalidade,ferramenta_slug,ativa,atualizado_em) "
            "VALUES (?,?,?,?,?,?,?,1,?) "
            "ON CONFLICT (numero) DO UPDATE SET eixo=excluded.eixo, titulo=excluded.titulo, "
            "corpo=excluded.corpo, micro_resultado=excluded.micro_resultado, "
            "mentalidade=excluded.mentalidade, ferramenta_slug=excluded.ferramenta_slug, "
            "atualizado_em=excluded.atualizado_em",
            (int(numero), eixo or "", titulo or "", corpo or "", micro_resultado or "",
             mentalidade or "", ferramenta_slug or "", datetime.now().isoformat()))


def trilha_peca(numero):
    with _conn() as c:
        r = c.execute("SELECT * FROM trilha_pecas WHERE numero=? AND ativa=1",
                      (int(numero),)).fetchone()
    return dict(r) if r else None


def trilha_posicao(sub_id):
    """Posição do assinante na trilha. Quem nunca recebeu nasce em 1."""
    with _conn() as c:
        c.execute("INSERT INTO trilha_progresso (subscriber_id,proxima_peca,ultimo_envio) "
                  "VALUES (?,1,'') ON CONFLICT (subscriber_id) DO NOTHING", (sub_id or "",))
        r = c.execute("SELECT proxima_peca FROM trilha_progresso WHERE subscriber_id=?",
                      (sub_id or "",)).fetchone()
    return int(r["proxima_peca"]) if r else 1


def trilha_registrar_envio(sub_id, numero):
    """Claim atômico do envio de UMA peça a UM assinante. True só na 1ª vez.
    Mesma defesa de `registrar_envio_assinante`: mata reenvio em restart/retry."""
    from datetime import datetime
    with _conn() as c:
        cur = c.execute("INSERT INTO trilha_envios (subscriber_id,numero,enviado_em,feito_em) "
                        "VALUES (?,?,?,NULL) ON CONFLICT (subscriber_id,numero) DO NOTHING",
                        (sub_id or "", int(numero), datetime.now().isoformat()))
        return cur.rowcount > 0


def trilha_avancar(sub_id, numero):
    """Move a posição para `numero`+1. Chamado SÓ depois do envio dar certo."""
    from datetime import datetime
    agora = datetime.now().isoformat()
    with _conn() as c:
        c.execute("INSERT INTO trilha_progresso (subscriber_id,proxima_peca,ultimo_envio) "
                  "VALUES (?,?,?) ON CONFLICT (subscriber_id) DO UPDATE SET "
                  "proxima_peca=excluded.proxima_peca, ultimo_envio=excluded.ultimo_envio",
                  (sub_id or "", int(numero) + 1, agora))


def trilha_marcar_feito(sub_id, numero):
    """Marca o '✅ fiz'. False se a peça não foi enviada a ele ou já estava marcada
    (o botão é idempotente: 2º clique não duplica nem mente pro usuário)."""
    from datetime import datetime
    with _conn() as c:
        cur = c.execute("UPDATE trilha_envios SET feito_em=? "
                        "WHERE subscriber_id=? AND numero=? AND feito_em IS NULL",
                        (datetime.now().isoformat(), sub_id or "", int(numero)))
        return cur.rowcount > 0


def trilha_fez(sub_id, numero):
    with _conn() as c:
        r = c.execute("SELECT 1 FROM trilha_envios WHERE subscriber_id=? AND numero=? "
                      "AND feito_em IS NOT NULL", (sub_id or "", int(numero))).fetchone()
    return r is not None


def trilha_historico(sub_id):
    with _conn() as c:
        rows = c.execute("SELECT numero, enviado_em, feito_em FROM trilha_envios "
                         "WHERE subscriber_id=? ORDER BY numero DESC", (sub_id or "",)).fetchall()
    return [dict(r) for r in rows]


def trilha_painel():
    """Uma linha por assinante que já entrou na trilha: posição, quantas recebeu e
    quantas marcou como feitas. Alimenta /admin/trilha."""
    with _conn() as c:
        rows = c.execute(
            "SELECT p.subscriber_id AS subscriber_id, p.proxima_peca AS proxima_peca, "
            "COUNT(e.numero) AS enviadas, "
            "COUNT(e.feito_em) AS feitas "
            "FROM trilha_progresso p LEFT JOIN trilha_envios e "
            "ON e.subscriber_id = p.subscriber_id "
            "GROUP BY p.subscriber_id, p.proxima_peca "
            "ORDER BY p.proxima_peca DESC").fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 5: Rodar e confirmar que passa**

Run: `cd app && python3 -m unittest tests.test_trilha -v`
Expected: PASS (12 testes)

- [ ] **Step 6: Rodar a suíte inteira**

Run: `cd app && python3 -m unittest discover -s tests`
Expected: PASS — nenhum teste existente quebrado

- [ ] **Step 7: Commit**

```bash
git add app/db.py app/tests/test_trilha.py
git commit -m "feat(trilha): tabelas e acesso a banco da trilha semanal"
```

---

### Task 2: Config e leitura das peças do disco

**Files:**
- Modify: `app/config.py`
- Create: `app/trilha.py`
- Create: `seed/trilha/01-custo-da-hora.md` … `seed/trilha/12-painel-do-dono.md`
- Create: `seed/trilha/ferramentas/.gitkeep`
- Test: `app/tests/test_trilha.py` (classe nova)

**Interfaces:**
- Consumes: `db.trilha_upsert_peca`, `db.trilha_peca` (Task 1)
- Produces:
  - `config.TRILHA_NOME:str`, `config.TRILHA_DIA:str`, `config.TRILHA_TOTAL:int`, `config.TRILHA_DIR:str`
  - `trilha.parse_peca(texto:str) -> dict` — chaves `titulo`, `eixo`, `ferramenta`, `corpo`, `micro_resultado`, `mentalidade`
  - `trilha.semear(diretorio:str|None=None) -> int` — quantas peças gravou

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar ao fim de `app/tests/test_trilha.py`, antes do `if __name__`:

```python
class TestParseESeed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg, self.db, self.subs = _recarregar(self.tmp)
        import trilha
        importlib.reload(trilha)
        self.t = trilha

    def test_parse_le_cabecalho_e_secoes(self):
        p = self.t.parse_peca(
            "titulo: O custo real da sua hora\n"
            "eixo: Saber onde você está\n"
            "ferramenta: planilha-custo-hora\n"
            "\n"
            "## corpo\n"
            "Primeiro parágrafo.\n"
            "\n"
            "Segundo parágrafo.\n"
            "\n"
            "## micro-resultado\n"
            "Calcule o custo da sua hora.\n"
            "\n"
            "## mentalidade\n"
            "Empenho é diferente de desempenho.\n")
        self.assertEqual(p["titulo"], "O custo real da sua hora")
        self.assertEqual(p["eixo"], "Saber onde você está")
        self.assertEqual(p["ferramenta"], "planilha-custo-hora")
        self.assertIn("Segundo parágrafo.", p["corpo"])
        self.assertEqual(p["micro_resultado"], "Calcule o custo da sua hora.")
        self.assertEqual(p["mentalidade"], "Empenho é diferente de desempenho.")

    def test_parse_sem_ferramenta_devolve_vazio(self):
        p = self.t.parse_peca("titulo: X\neixo: Y\n\n## corpo\nz\n")
        self.assertEqual(p["ferramenta"], "")
        self.assertEqual(p["micro_resultado"], "")

    def test_semear_grava_as_pecas_do_diretorio(self):
        d = os.path.join(self.tmp, "trilha")
        os.makedirs(d)
        with open(os.path.join(d, "01-um.md"), "w", encoding="utf-8") as f:
            f.write("titulo: Um\neixo: A\n\n## corpo\ncorpo um\n")
        with open(os.path.join(d, "02-dois.md"), "w", encoding="utf-8") as f:
            f.write("titulo: Dois\neixo: A\n\n## corpo\ncorpo dois\n")
        self.assertEqual(self.t.semear(d), 2)
        self.assertEqual(self.db.trilha_peca(1)["titulo"], "Um")
        self.assertEqual(self.db.trilha_peca(2)["titulo"], "Dois")

    def test_semear_e_idempotente_e_atualiza_texto_editado(self):
        d = os.path.join(self.tmp, "trilha")
        os.makedirs(d)
        caminho = os.path.join(d, "01-um.md")
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("titulo: Um\neixo: A\n\n## corpo\nversao 1\n")
        self.t.semear(d)
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("titulo: Um\neixo: A\n\n## corpo\nversao 2\n")
        self.t.semear(d)
        self.assertIn("versao 2", self.db.trilha_peca(1)["corpo"])

    def test_semear_ignora_arquivo_sem_numero_no_nome(self):
        d = os.path.join(self.tmp, "trilha")
        os.makedirs(d)
        with open(os.path.join(d, "leiame.md"), "w", encoding="utf-8") as f:
            f.write("titulo: X\n\n## corpo\ny\n")
        self.assertEqual(self.t.semear(d), 0)

    def test_semear_diretorio_inexistente_nao_quebra(self):
        self.assertEqual(self.t.semear(os.path.join(self.tmp, "nao-existe")), 0)

    def test_as_12_pecas_do_repo_carregam(self):
        # o diretório real do repo tem que estar parseável e completo
        self.assertEqual(self.t.semear(), self.cfg.TRILHA_TOTAL)
        for n in range(1, self.cfg.TRILHA_TOTAL + 1):
            p = self.db.trilha_peca(n)
            self.assertIsNotNone(p, f"peça {n} não carregou")
            self.assertTrue(p["titulo"].strip(), f"peça {n} sem título")
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_trilha.TestParseESeed -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trilha'`

- [ ] **Step 3: Acrescentar a config**

Em `app/config.py`, logo depois do bloco de `SLOTS`/`SLOT_HORA`/`SLOT_DEFAULT` (linhas 64-67):

```python
# Trilha semanal de empreendedorismo médico (sábado, drip por assinante).
# TRILHA_NOME é provisório: o nome do produto ainda vai ser decidido. Mora aqui,
# e não espalhado no código, justamente pra troca ser um campo e não uma varredura.
TRILHA_NOME = os.environ.get("DSCURSO_TRILHA_NOME") or "Trilha do Consultório"
TRILHA_DIA = "sabado"
TRILHA_TOTAL = 12
TRILHA_DIR = os.environ.get("DSCURSO_TRILHA_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seed", "trilha")
```

- [ ] **Step 4: Criar `app/trilha.py` com parse e seed**

```python
"""Trilha semanal de empreendedorismo médico.

Uma peça por sábado, no horário (slot) que o assinante já escolheu pro estudo.
Drip por assinante: cada um percorre as 12 peças a partir da 1, independente de
quando assinou. Conteúdo é evergreen e mora em `seed/trilha/NN-slug.md`.

Isolado de propósito: NÃO importa nem altera `daily.py`. Se a trilha quebrar,
o estudo diário continua saindo.
"""
import os
import re

import config
import db

_SECOES = {"corpo": "corpo", "micro-resultado": "micro_resultado",
           "mentalidade": "mentalidade"}


def parse_peca(texto):
    """Converte o arquivo de uma peça em dict.

    Formato: linhas `chave: valor` até a primeira linha em branco, depois blocos
    `## secao`. Seção ausente vira string vazia — peça de mentalidade pura pode
    não ter ferramenta, e isso não é erro.
    """
    linhas = (texto or "").replace("\r\n", "\n").split("\n")
    cab, i = {}, 0
    while i < len(linhas) and linhas[i].strip():
        if ":" in linhas[i]:
            k, v = linhas[i].split(":", 1)
            cab[k.strip().lower()] = v.strip()
        i += 1
    secoes, atual = {}, None
    for linha in linhas[i:]:
        m = re.match(r"^##\s+(.+?)\s*$", linha)
        if m:
            atual = _SECOES.get(m.group(1).strip().lower())
            if atual:
                secoes[atual] = []
            continue
        if atual and atual in secoes:
            secoes[atual].append(linha)
    return {
        "titulo": cab.get("titulo", ""),
        "eixo": cab.get("eixo", ""),
        "ferramenta": cab.get("ferramenta", ""),
        "corpo": "\n".join(secoes.get("corpo", [])).strip(),
        "micro_resultado": "\n".join(secoes.get("micro_resultado", [])).strip(),
        "mentalidade": "\n".join(secoes.get("mentalidade", [])).strip(),
    }


def semear(diretorio=None):
    """Lê `seed/trilha/NN-*.md` e grava no banco. Idempotente por número: editar o
    texto e redeployar propaga a versão nova (o upsert atualiza a linha).
    Retorna quantas peças gravou."""
    d = diretorio or config.TRILHA_DIR
    if not os.path.isdir(d):
        return 0
    n = 0
    for nome in sorted(os.listdir(d)):
        m = re.match(r"^(\d{1,2})[-_]", nome)
        if not m or not nome.endswith(".md"):
            continue
        with open(os.path.join(d, nome), encoding="utf-8") as f:
            p = parse_peca(f.read())
        db.trilha_upsert_peca(int(m.group(1)), p["eixo"], p["titulo"], p["corpo"],
                              p["micro_resultado"], p["mentalidade"], p["ferramenta"])
        n += 1
    return n
```

- [ ] **Step 5: Criar as 12 peças com texto-esqueleto**

Criar `seed/trilha/ferramentas/.gitkeep` (arquivo vazio) e os 12 arquivos abaixo. **O texto é esqueleto deliberado** — a redação final é trabalho separado, com o sócio nas peças 7 e 8. O que precisa estar certo agora é o número, o título, o eixo, o slug da ferramenta e a existência das três seções.

Modelo exato (usar para todos, trocando os campos):

```markdown
titulo: O custo real da sua hora
eixo: Saber onde você está
ferramenta: planilha-custo-hora

## corpo
RASCUNHO — texto final pendente.

Você atende, atende, atende e no fim do mês não sobra. O problema quase nunca é
volume: é que ninguém te ensinou quanto custa uma hora sua com a porta aberta.

## micro-resultado
Calcule o custo da sua hora: some tudo que sai por mês (aluguel, secretária,
software, impostos, seu pró-labore) e divida pelas horas que você realmente
atende. Anote o número. É a partir dele que todo o resto desta trilha funciona.

## mentalidade
Empenho é diferente de desempenho. Trabalhar muito não é o mesmo que ganhar bem,
e confundir as duas coisas é o que mantém médico bom vivendo pequeno.
```

Os 12 arquivos, com `titulo` / `eixo` / `ferramenta`:

| Arquivo | titulo | eixo | ferramenta |
|---|---|---|---|
| `01-custo-da-hora.md` | O custo real da sua hora | Saber onde você está | `planilha-custo-hora` |
| `02-dono-que-decide.md` | De médico que atende a dono que decide | Saber onde você está | *(vazio)* |
| `03-uma-linha.md` | Escolha uma linha de tratamento | Saber onde você está | `mapa-de-linha` |
| `04-do-avulso-ao-plano.md` | Do avulso ao plano de acompanhamento | Construir a oferta | `modelo-de-plano` |
| `05-precificacao.md` | Precificação sem culpa | Construir a oferta | `planilha-precificacao` |
| `06-posicionamento.md` | Por que ele te escolhe e não o vizinho | Construir a oferta | *(vazio)* |
| `07-consulta-que-vende.md` | A consulta que vende sozinha | Vender e reter | `roteiro-5-perguntas` |
| `08-sofrendo-uma-compra.md` | Você não está fazendo uma venda, está sofrendo uma compra | Vender e reter | *(vazio)* |
| `09-paciente-que-some.md` | O paciente que some no mês 2 | Vender e reter | `regua-de-acompanhamento` |
| `10-quantos-cabem.md` | Quantos planos cabem em você | Escalar sem se destruir | *(vazio)* |
| `11-proximo-paciente.md` | De onde vem o próximo paciente | Escalar sem se destruir | *(vazio)* |
| `12-painel-do-dono.md` | O painel do dono | Escalar sem se destruir | `painel-mensal` |

Cada arquivo leva as três seções. Nas de corpo ainda não escrito, começar o `## corpo` com a linha `RASCUNHO — texto final pendente.` para que fique óbvio no PDF de teste que aquilo não é conteúdo final.

- [ ] **Step 6: Rodar e confirmar que passa**

Run: `cd app && python3 -m unittest tests.test_trilha -v`
Expected: PASS — incluindo `test_as_12_pecas_do_repo_carregam`

- [ ] **Step 7: Commit**

```bash
git add app/config.py app/trilha.py app/tests/test_trilha.py seed/trilha
git commit -m "feat(trilha): config, parser das pecas e seed do disco pro banco"
```

---

### Task 3: Motor do drip — qual peça vai pra quem

**Files:**
- Modify: `app/trilha.py`
- Test: `app/tests/test_trilha.py` (classe nova)

**Interfaces:**
- Consumes: `db.trilha_posicao`, `db.trilha_peca`, `db.trilha_fez` (Task 1); `config.TRILHA_TOTAL`, `config.TRILHA_DIA` (Task 2)
- Produces:
  - `trilha.e_dia_da_trilha(quando:datetime|date|None=None) -> bool`
  - `trilha.proxima_peca(sub_id:str) -> dict|None` — `None` quando concluiu as 12
  - `trilha.abertura(sub_id:str, numero:int) -> str` — linha de retomada da peça anterior

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar a `app/tests/test_trilha.py`:

```python
class TestDrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg, self.db, self.subs = _recarregar(self.tmp)
        import trilha
        importlib.reload(trilha)
        self.t = trilha
        self.t.semear()

    def test_dia_da_trilha_e_sabado(self):
        from datetime import date
        self.assertTrue(self.t.e_dia_da_trilha(date(2026, 8, 8)))     # sábado
        self.assertFalse(self.t.e_dia_da_trilha(date(2026, 8, 7)))    # sexta
        self.assertFalse(self.t.e_dia_da_trilha(date(2026, 8, 9)))    # domingo

    def test_assinante_novo_recebe_a_peca_1(self):
        self.assertEqual(self.t.proxima_peca("sub-a")["numero"], 1)

    def test_peca_nao_avanca_sozinha(self):
        self.assertEqual(self.t.proxima_peca("sub-a")["numero"], 1)
        self.assertEqual(self.t.proxima_peca("sub-a")["numero"], 1)   # sem avanço, mesma peça

    def test_avanco_leva_a_proxima(self):
        self.db.trilha_avancar("sub-a", 1)
        self.assertEqual(self.t.proxima_peca("sub-a")["numero"], 2)

    def test_quem_concluiu_nao_tem_proxima(self):
        self.db.trilha_avancar("sub-a", self.cfg.TRILHA_TOTAL)
        self.assertIsNone(self.t.proxima_peca("sub-a"))

    def test_abertura_da_peca_1_nao_cobra_nada(self):
        self.assertEqual(self.t.abertura("sub-a", 1), "")

    def test_abertura_reconhece_quem_fez(self):
        self.db.trilha_registrar_envio("sub-a", 1)
        self.db.trilha_marcar_feito("sub-a", 1)
        self.assertIn("semana passada", self.t.abertura("sub-a", 2).lower())

    def test_abertura_retoma_quem_nao_fez(self):
        self.db.trilha_registrar_envio("sub-a", 1)
        texto = self.t.abertura("sub-a", 2)
        self.assertTrue(texto)
        self.assertNotIn("parabéns", texto.lower())
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_trilha.TestDrip -v`
Expected: FAIL — `AttributeError: module 'trilha' has no attribute 'e_dia_da_trilha'`

- [ ] **Step 3: Implementar**

Acrescentar a `app/trilha.py`:

```python
_DIAS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]


def e_dia_da_trilha(quando=None):
    """True se `quando` cai no dia da trilha (config.TRILHA_DIA). Aceita date ou datetime."""
    from datetime import datetime
    d = quando or datetime.now()
    return _DIAS[d.weekday()] == config.TRILHA_DIA


def proxima_peca(sub_id):
    """A peça que este assinante deve receber agora. None se já concluiu a trilha
    (ou se a peça não existe no banco — trilha incompleta não vira envio errado)."""
    n = db.trilha_posicao(sub_id)
    if n > config.TRILHA_TOTAL:
        return None
    p = db.trilha_peca(n)
    if not p:
        return None
    p["numero"] = n
    return p


def abertura(sub_id, numero):
    """Linha de retomada no topo da peça, olhando a peça anterior.

    É a cobrança da trilha: sem grupo, sem live, sem canal de entrada no WhatsApp —
    a peça seguinte é que reconhece ou retoma. Vazia na peça 1 (não há anterior)."""
    if numero <= 1:
        return ""
    if db.trilha_fez(sub_id, numero - 1):
        return "Você marcou a tarefa da semana passada como feita. É assim que essa trilha funciona."
    return "A tarefa da semana passada continua em aberto — ela leva menos tempo do que parece."
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `cd app && python3 -m unittest tests.test_trilha -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/trilha.py app/tests/test_trilha.py
git commit -m "feat(trilha): motor do drip -- posicao por assinante e linha de retomada"
```

---

### Task 4: PDF da peça

**Files:**
- Create: `app/pdf_trilha.py`
- Test: `app/tests/test_trilha.py` (classe nova)

**Interfaces:**
- Consumes: `config.TRILHA_NOME`, `config.TRILHA_TOTAL` (Task 2)
- Produces: `pdf_trilha.montar_html(peca:dict, nome_assinante:str, abertura:str="", link_ferramenta:str="") -> str`

Nota de escopo: o layout aqui é sóbrio e legível, **não** uma cópia do PDF de estudo. Refino visual entra depois, com um PDF real em mãos — mesma lição registrada no PDF diário, cuja diagramação só se prova imprimindo.

- [ ] **Step 1: Escrever os testes que falham**

```python
class TestPdfTrilha(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg, self.db, self.subs = _recarregar(self.tmp)
        import pdf_trilha
        importlib.reload(pdf_trilha)
        self.p = pdf_trilha
        self.peca = {"numero": 3, "titulo": "Escolha uma linha", "eixo": "Saber onde você está",
                     "corpo": "Primeiro.\n\nSegundo.", "micro_resultado": "Faça a conta.",
                     "mentalidade": "Pense grande.", "ferramenta_slug": "mapa-de-linha"}

    def test_html_traz_titulo_e_progresso(self):
        h = self.p.montar_html(self.peca, "Diego")
        self.assertIn("Escolha uma linha", h)
        self.assertIn(f"3 de {self.cfg.TRILHA_TOTAL}", h)

    def test_html_traz_as_tres_camadas(self):
        h = self.p.montar_html(self.peca, "Diego")
        self.assertIn("Faça a conta.", h)
        self.assertIn("Pense grande.", h)
        self.assertIn("Segundo.", h)

    def test_paragrafos_do_corpo_viram_p(self):
        h = self.p.montar_html(self.peca, "Diego")
        self.assertIn("<p>Primeiro.</p>", h)
        self.assertIn("<p>Segundo.</p>", h)

    def test_link_da_ferramenta_aparece_quando_existe(self):
        h = self.p.montar_html(self.peca, "Diego", link_ferramenta="https://x/ferramentas/mapa")
        self.assertIn('href="https://x/ferramentas/mapa"', h)

    def test_sem_ferramenta_nao_deixa_botao_orfao(self):
        h = self.p.montar_html(self.peca, "Diego")
        self.assertNotIn("Baixar", h)

    def test_abertura_entra_quando_existe(self):
        h = self.p.montar_html(self.peca, "Diego", abertura="Continua em aberto.")
        self.assertIn("Continua em aberto.", h)

    def test_escapa_html_do_conteudo(self):
        peca = dict(self.peca, titulo="Dose <script>alert(1)</script>")
        h = self.p.montar_html(peca, "Diego")
        self.assertNotIn("<script>", h)
        self.assertIn("&lt;script&gt;", h)

    def test_escapa_nome_do_assinante(self):
        h = self.p.montar_html(self.peca, "<img src=x onerror=1>")
        self.assertNotIn("<img src=x", h)
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_trilha.TestPdfTrilha -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pdf_trilha'`

- [ ] **Step 3: Implementar**

Criar `app/pdf_trilha.py`:

```python
"""HTML da peça da trilha, pronto pra virar PDF por `pdf.gerar_pdf`.

Separado de `pdf.py` de propósito: aquele arquivo carrega o layout do estudo
científico (gráfico, braços, limites, referência) e já passa de 23K. A peça da
trilha é outro objeto — texto, uma tarefa e uma frase de cabeça — e não tem por
que herdar aquele CSS nem fazer aquele arquivo crescer.
"""
import html

import config

_CSS = """
  @page { size: A4; margin: 18mm 16mm; }
  body { font-family: Georgia, 'Times New Roman', serif; color: #1b1b1b; line-height: 1.55; }
  .selo { font-family: system-ui, sans-serif; font-size: 10px; letter-spacing: .18em;
          text-transform: uppercase; color: #8a6a2f; }
  h1 { font-size: 26px; line-height: 1.2; margin: 6px 0 2px; }
  .eixo { font-family: system-ui, sans-serif; font-size: 12px; color: #6b6b6b; margin: 0 0 22px; }
  .abertura { font-style: italic; color: #4a4a4a; border-left: 3px solid #d8c9a6;
              padding-left: 12px; margin: 0 0 22px; }
  .corpo p { margin: 0 0 12px; }
  .bloco { border: 1px solid #e2dccc; border-radius: 8px; padding: 14px 16px; margin: 22px 0 0; }
  .bloco .rot { font-family: system-ui, sans-serif; font-size: 10px; letter-spacing: .16em;
                text-transform: uppercase; color: #8a6a2f; margin: 0 0 6px; }
  .bloco p { margin: 0; }
  .ferramenta { margin: 22px 0 0; }
  .ferramenta a { font-family: system-ui, sans-serif; font-size: 13px; color: #8a6a2f; }
  .rodape { margin-top: 30px; font-family: system-ui, sans-serif; font-size: 11px; color: #8a8a8a; }
"""


def _esc(s):
    return html.escape(str(s or ""), quote=True)


def _paragrafos(texto):
    """Blocos separados por linha em branco viram <p>. Sem markdown: o conteúdo é
    nosso e escrito à mão, não vale carregar um parser pra isso."""
    blocos = [b.strip() for b in (texto or "").replace("\r\n", "\n").split("\n\n")]
    return "".join(f"<p>{_esc(b)}</p>" for b in blocos if b)


def montar_html(peca, nome_assinante, abertura="", link_ferramenta=""):
    """HTML completo de uma peça. `link_ferramenta` vazio some com o bloco inteiro —
    peça de mentalidade pura não tem anexo e não pode exibir botão órfão."""
    numero = peca.get("numero", 0)
    abertura_html = (f'<p class="abertura">{_esc(abertura)}</p>' if abertura else "")
    ferramenta_html = ""
    if link_ferramenta:
        ferramenta_html = (f'<p class="ferramenta">📎 <a href="{_esc(link_ferramenta)}">'
                           f'Baixar a ferramenta desta semana</a></p>')
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<style>{_CSS}</style></head><body>
  <p class="selo">{_esc(config.TRILHA_NOME)} · Semana {numero} de {config.TRILHA_TOTAL}</p>
  <h1>{_esc(peca.get('titulo'))}</h1>
  <p class="eixo">{_esc(peca.get('eixo'))}</p>
  {abertura_html}
  <div class="corpo">{_paragrafos(peca.get('corpo'))}</div>
  <div class="bloco"><p class="rot">Sua tarefa desta semana</p>
    {_paragrafos(peca.get('micro_resultado')) or '<p></p>'}</div>
  <div class="bloco"><p class="rot">Mentalidade</p>
    {_paragrafos(peca.get('mentalidade')) or '<p></p>'}</div>
  {ferramenta_html}
  <p class="rodape">Para {_esc(nome_assinante)} · {_esc(config.TRILHA_NOME)}</p>
</body></html>"""
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `cd app && python3 -m unittest tests.test_trilha -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/pdf_trilha.py app/tests/test_trilha.py
git commit -m "feat(trilha): HTML da peca pro PDF, separado do layout de estudo"
```

---

### Task 5: Envio de sábado

**Files:**
- Modify: `app/trilha.py`
- Modify: `app/serve.py` (função `agendador`, linhas 71-105)
- Test: `app/tests/test_trilha.py` (classe nova)

**Interfaces:**
- Consumes: `trilha.proxima_peca`, `trilha.abertura`, `trilha.e_dia_da_trilha` (Task 3); `pdf_trilha.montar_html` (Task 4); `db.trilha_registrar_envio`, `db.trilha_avancar` (Task 1); `subscribers.ativos`, `subscribers.slot_de`; `deliver.enviar_pdf`; `pdf.gerar_pdf`
- Produces:
  - `trilha.enviar_para(sub:dict, enviar_fn=None, render_fn=None) -> bool`
  - `trilha.enviar_slot(slot:str, quando=None, enviar_fn=None, render_fn=None) -> dict` — `{"enviados": int, "falhas": int}`

`enviar_fn` e `render_fn` existem pra teste: sem eles não há como exercitar o envio sem WhatsApp e sem Chromium.

- [ ] **Step 1: Escrever os testes que falham**

```python
class TestEnvio(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg, self.db, self.subs = _recarregar(self.tmp)
        import trilha
        importlib.reload(trilha)
        self.t = trilha
        self.t.semear()
        self.enviados = []

    def _fake_enviar(self, whatsapp, pdf_path, caption="", nome_arquivo=""):
        self.enviados.append({"whatsapp": whatsapp, "caption": caption})

    def _fake_render(self, html, out_path):
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("pdf")
        return out_path

    def _sub(self, nome="Fulano", numero="5543999990000", slot="08h"):
        reg = self.subs.adicionar(nome, numero)
        self.subs.definir_slot(reg["id"], slot)
        return self.subs.por_id(reg["id"])

    def test_envia_a_peca_1_e_avanca(self):
        sub = self._sub()
        ok = self.t.enviar_para(sub, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertTrue(ok)
        self.assertEqual(len(self.enviados), 1)
        self.assertEqual(self.db.trilha_posicao(sub["id"]), 2)

    def test_nao_envia_a_mesma_peca_duas_vezes(self):
        sub = self._sub()
        self.db.trilha_registrar_envio(sub["id"], 1)          # já reivindicada
        ok = self.t.enviar_para(sub, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertFalse(ok)
        self.assertEqual(self.enviados, [])

    def test_falha_no_envio_nao_avanca_a_posicao(self):
        sub = self._sub()

        def explode(*a, **k):
            raise RuntimeError("zap caiu")

        ok = self.t.enviar_para(sub, enviar_fn=explode, render_fn=self._fake_render)
        self.assertFalse(ok)
        self.assertEqual(self.db.trilha_posicao(sub["id"]), 1)   # continua na peça 1

    def test_falha_no_envio_libera_o_claim_pra_proxima_semana(self):
        sub = self._sub()

        def explode(*a, **k):
            raise RuntimeError("zap caiu")

        self.t.enviar_para(sub, enviar_fn=explode, render_fn=self._fake_render)
        ok = self.t.enviar_para(sub, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertTrue(ok, "a mesma peça tem que poder ser reenviada depois de falhar")

    def test_quem_concluiu_nao_recebe_mais(self):
        sub = self._sub()
        self.db.trilha_avancar(sub["id"], self.cfg.TRILHA_TOTAL)
        ok = self.t.enviar_para(sub, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertFalse(ok)
        self.assertEqual(self.enviados, [])

    def test_slot_envia_so_pro_proprio_slot(self):
        from datetime import date
        a = self._sub("A", "5543999990001", "08h")
        b = self._sub("B", "5543999990002", "18h")
        res = self.t.enviar_slot("08h", quando=date(2026, 8, 8),
                                 enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertEqual(res["enviados"], 1)
        self.assertEqual(self.db.trilha_posicao(a["id"]), 2)
        self.assertEqual(self.db.trilha_posicao(b["id"]), 1)

    def test_slot_nao_envia_em_dia_util(self):
        from datetime import date
        self._sub()
        res = self.t.enviar_slot("08h", quando=date(2026, 8, 7),   # sexta
                                 enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertEqual(res["enviados"], 0)
        self.assertEqual(self.enviados, [])

    def test_slot_e_idempotente_no_mesmo_sabado(self):
        from datetime import date
        self._sub()
        sab = date(2026, 8, 8)
        self.t.enviar_slot("08h", quando=sab, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        res = self.t.enviar_slot("08h", quando=sab, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertEqual(res["enviados"], 0)
        self.assertEqual(len(self.enviados), 1)

    def test_cancelado_nao_recebe(self):
        from datetime import date
        sub = self._sub()
        self.subs.marcar_status(sub["id"], "CANCELADO", acesso_ate="2020-01-01")
        res = self.t.enviar_slot("08h", quando=date(2026, 8, 8),
                                 enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertEqual(res["enviados"], 0)
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_trilha.TestEnvio -v`
Expected: FAIL — `AttributeError: module 'trilha' has no attribute 'enviar_para'`

- [ ] **Step 3: Implementar o envio**

Acrescentar a `app/trilha.py`:

```python
def _liberar_claim(sub_id, numero):
    """Desfaz o claim de `trilha_registrar_envio` quando o envio falhou. Sem isso o
    assinante ficaria travado: a posição não avançou (certo) mas o claim impediria
    a retentativa no sábado seguinte (errado) — ele nunca mais receberia a peça."""
    with db._conn() as c:
        c.execute("DELETE FROM trilha_envios WHERE subscriber_id=? AND numero=? "
                  "AND feito_em IS NULL", (sub_id or "", int(numero)))


def enviar_para(sub, enviar_fn=None, render_fn=None):
    """Envia a peça da vez a UM assinante. True se enviou.

    Ordem que importa: claim -> render -> envia -> avança. A posição só anda depois
    do envio dar certo; se falhar, o claim é liberado e ele recebe a MESMA peça no
    sábado seguinte. Nunca pula conteúdo."""
    import os
    import tempfile
    import deliver
    import phone

    sub_id = sub.get("id")
    peca = proxima_peca(sub_id)
    if peca is None:
        return False
    numero = peca["numero"]
    if not db.trilha_registrar_envio(sub_id, numero):    # já reivindicada
        return False

    enviar_fn = enviar_fn or deliver.enviar_pdf
    if render_fn is None:
        import pdf as _pdf
        render_fn = _pdf.gerar_pdf

    try:
        import pdf_trilha
        link = ""
        if peca.get("ferramenta_slug"):
            link = f"{config.PUBLIC_URL}/ferramentas/{peca['ferramenta_slug']}"
        html_peca = pdf_trilha.montar_html(peca, sub.get("nome", ""),
                                           abertura=abertura(sub_id, numero), link_ferramenta=link)
        out = os.path.join(tempfile.gettempdir(), f"trilha-{numero}-{sub_id}.pdf")
        render_fn(html_peca, out)
        enviar_fn(phone.normalizar(sub.get("whatsapp", "")), out,
                  caption=f"{config.TRILHA_NOME} · Semana {numero}: {peca.get('titulo','')}",
                  nome_arquivo=f"semana-{numero:02d}.pdf")
    except Exception as e:
        print(f"[trilha] peça {numero} p/ {sub_id} falhou: {e}", flush=True)
        _liberar_claim(sub_id, numero)
        return False

    db.trilha_avancar(sub_id, numero)
    return True


def enviar_slot(slot, quando=None, enviar_fn=None, render_fn=None):
    """Envia a peça da semana aos assinantes ativos de `slot`. Só roda no dia da
    trilha. Idempotente por (data, slot) usando `envios_slot` com chave namespaced —
    mesmo truque da varredura semanal, sem tabela nova."""
    from datetime import datetime
    import subscribers

    d = quando or datetime.now()
    if not e_dia_da_trilha(d):
        return {"enviados": 0, "falhas": 0}
    data = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)
    if not db.registrar_envio_slot(f"trilha:{data}", slot):   # slot já rodou hoje
        return {"enviados": 0, "falhas": 0}

    enviados = falhas = 0
    for s in subscribers.ativos():
        if subscribers.slot_de(s) != slot:
            continue
        if enviar_para(s, enviar_fn=enviar_fn, render_fn=render_fn):
            enviados += 1
        else:
            falhas += 1
    if enviados or falhas:
        try:
            import deliver
            deliver.enviar_curador(f"📘 Trilha (slot {slot}): {enviados} enviada(s)"
                                   + (f" · {falhas} sem envio" if falhas else ""))
        except Exception as e:
            print(f"[trilha] aviso ao curador falhou: {e}", flush=True)
    return {"enviados": enviados, "falhas": falhas}
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `cd app && python3 -m unittest tests.test_trilha -v`
Expected: PASS

Nota: `falhas` conta também quem **não tinha peça** (concluiu a trilha). Se isso poluir o aviso ao curador na prática, separar os dois contadores é ajuste de uma linha — não vale complicar agora.

- [ ] **Step 5: Ligar no agendador**

Em `app/serve.py`, na função `agendador()` (linha 71), substituir o corpo entre a linha `import daily, config` e a linha `# (hora, nome) — ...` por:

```python
    import daily, config, trilha

    def _trilha_tick(sl):
        """Sábado: manda a peça da trilha nesse slot. Dia útil: no-op.
        Fica FORA de daily.enviar_slot de propósito — o motor do estudo não muda."""
        try:
            trilha.enviar_slot(sl)
        except Exception as e:
            print(f"[trilha] slot {sl} erro: {e}", flush=True)

    def _rotina08():
        daily.rotina_08h()      # régua + estudo (o estudo é no-op no sábado)
        _trilha_tick("08h")

    def _prep_e_18h():
        daily.enviar_slot("18h")   # envia HOJE 1º (independente da preparação de amanhã, que pode falhar)
        _trilha_tick("18h")
        daily.preparar_18h()       # prepara amanhã (o try/except do loop do agendador cobre se falhar)
    tarefas = {"rotina08": _rotina08, "prep18": _prep_e_18h,
               "varredura_semanal": daily.varredura_semanal,
               "gerar_curadoria": daily.gerar_selecionados_noturno}
    for s in config.SLOTS:
        if s not in ("08h", "18h"):
            tarefas[f"slot:{s}"] = (lambda sl=s: (daily.enviar_slot(sl), _trilha_tick(sl)))
```

**Não** acrescentar entradas novas em `horarios`. `proximo_disparo` usa `min()` sobre `(alvo, nome)`: duas tarefas na mesma hora fariam uma delas ser sempre preterida e só rodar no dia seguinte. Por isso o tick da trilha é chamado *dentro* da tarefa do slot, e não como tarefa própria.

- [ ] **Step 6: Semear as peças no boot**

Em `app/serve.py`, no bloco `if __name__ == "__main__":` (linha 1849), logo depois do
`try/except` do `db.init()` e **antes** da `threading.Thread(target=agendador...)`:

```python
    try:
        import trilha as _trilha
        _trilha.semear()          # idempotente: upsert por número
    except Exception as e:
        print(f"[trilha] seed falhou: {e}", flush=True)
```

O `db.init()` das rotas (linhas 286, 302, 313…) **não** serve pra isso: são chamadas por request.
O seed roda uma vez, no boot.

- [ ] **Step 7: Rodar a suíte inteira**

Run: `cd app && python3 -m unittest discover -s tests`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add app/trilha.py app/serve.py app/tests/test_trilha.py
git commit -m "feat(trilha): envio de sabado por slot, com claim e retentativa"
```

---

### Task 6: Página do assinante, botão "fiz" e download da ferramenta

**Files:**
- Modify: `app/site_web.py` (função nova, ao lado de `pagina_minha`, linha ~1400)
- Modify: `app/serve.py` (rotas GET `/trilha`, GET `/ferramentas/<slug>`, POST `/trilha`)
- Create: `app/tests/test_trilha_web.py`

**Interfaces:**
- Consumes: `db.trilha_historico`, `db.trilha_peca`, `db.trilha_marcar_feito` (Task 1); `trilha.proxima_peca` (Task 3)
- Produces:
  - `site_web.pagina_trilha(sub:dict, itens:list[dict], msg:str="") -> str` — cada item: `numero`, `titulo`, `feito:bool`, `ferramenta_slug`
  - `trilha.caminho_ferramenta(slug:str) -> str|None` — caminho absoluto, ou `None` se inválido/inexistente

- [ ] **Step 1: Escrever os testes que falham**

Criar `app/tests/test_trilha_web.py`:

```python
"""Testes das rotas da trilha: página do assinante, '✅ fiz' e download. Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPaginaTrilha(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        for m in ("config", "db", "subscribers", "trilha", "site_web"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, subscribers, trilha, site_web
        for m in (config, db, subscribers, trilha, site_web):
            importlib.reload(m)
        subscribers._migrado = False
        db.init()
        self.cfg, self.db, self.subs, self.t, self.w = config, db, subscribers, trilha, site_web
        self.t.semear()

    def test_pagina_mostra_a_peca_e_o_botao(self):
        itens = [{"numero": 1, "titulo": "O custo real da sua hora", "feito": False,
                  "ferramenta_slug": ""}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens)
        self.assertIn("O custo real da sua hora", h)
        self.assertIn("fiz", h.lower())

    def test_peca_feita_nao_mostra_botao_de_novo(self):
        itens = [{"numero": 1, "titulo": "X", "feito": True, "ferramenta_slug": ""}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens)
        self.assertNotIn('value="marcar_feito"', h)

    def test_ferramenta_vira_link_de_download(self):
        itens = [{"numero": 1, "titulo": "X", "feito": False, "ferramenta_slug": "planilha-x"}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens)
        self.assertIn("/ferramentas/planilha-x", h)

    def test_escapa_titulo(self):
        itens = [{"numero": 1, "titulo": "<script>x</script>", "feito": False,
                  "ferramenta_slug": ""}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens)
        self.assertNotIn("<script>x", h)


class TestFerramentaSegura(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["DSCURSO_TRILHA_DIR"] = self.tmp
        for m in ("config", "db", "trilha"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, trilha
        for m in (config, db, trilha):
            importlib.reload(m)
        db.init()
        self.cfg, self.t = config, trilha
        os.makedirs(os.path.join(self.tmp, "ferramentas"), exist_ok=True)
        with open(os.path.join(self.tmp, "ferramentas", "planilha-x.csv"), "w") as f:
            f.write("a,b\n")

    def test_acha_a_ferramenta_existente(self):
        self.assertTrue(self.t.caminho_ferramenta("planilha-x"))

    def test_slug_inexistente_devolve_none(self):
        self.assertIsNone(self.t.caminho_ferramenta("nao-existe"))

    def test_path_traversal_e_barrado(self):
        for mau in ("../db.py", "..%2Fdb.py", "a/../../etc/passwd", "/etc/passwd",
                    "..", ".", "a\\..\\b"):
            self.assertIsNone(self.t.caminho_ferramenta(mau), f"passou: {mau}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_trilha_web -v`
Expected: FAIL — `AttributeError: module 'site_web' has no attribute 'pagina_trilha'`

- [ ] **Step 3: Implementar `caminho_ferramenta`**

Acrescentar a `app/trilha.py`:

```python
_SLUG_OK = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")


def caminho_ferramenta(slug):
    """Caminho absoluto do arquivo da ferramenta, ou None.

    O slug vem da URL, então é entrada não confiável: só minúscula/dígito/hífen
    passa, o que já elimina `..`, `/` e `\\`. A checagem de prefixo depois é cinto
    e suspensório — se o regex mudar um dia, o arquivo servido continua preso ao
    diretório de ferramentas."""
    if not slug or not _SLUG_OK.match(slug):
        return None
    base = os.path.realpath(os.path.join(config.TRILHA_DIR, "ferramentas"))
    for nome in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        raiz, _ext = os.path.splitext(nome)
        if raiz != slug:
            continue
        caminho = os.path.realpath(os.path.join(base, nome))
        if caminho.startswith(base + os.sep) and os.path.isfile(caminho):
            return caminho
    return None
```

- [ ] **Step 4: Implementar a página**

Acrescentar a `app/site_web.py`, logo depois de `pagina_minha`:

```python
def pagina_trilha(sub, itens, msg=""):
    """Trilha do assinante: peça da semana no topo, anteriores abaixo.

    `itens` já vem pronto do serve (mais recente primeiro), com numero, titulo,
    feito e ferramenta_slug. A página não consulta banco."""
    import config as _cfg
    msg_html = f'<div class="infobox">{_esc(msg)}</div>' if msg else ""
    if not itens:
        linhas = ('<p class="hint">Sua primeira peça chega no próximo sábado, '
                  'no mesmo horário em que você recebe os estudos.</p>')
    else:
        partes = []
        for i, it in enumerate(itens):
            ferramenta = ""
            if it.get("ferramenta_slug"):
                ferramenta = (f'<p style="margin:8px 0 0"><a class="cta ghost" '
                              f'href="/ferramentas/{_esc(it["ferramenta_slug"])}">'
                              f'📎 Baixar a ferramenta</a></p>')
            if it.get("feito"):
                acao = '<p class="hint" style="margin:8px 0 0">✅ Você marcou como feita.</p>'
            else:
                acao = (f'<form method="post" action="/trilha" style="margin:8px 0 0">'
                        f'<input type="hidden" name="acao" value="marcar_feito">'
                        f'<input type="hidden" name="numero" value="{int(it["numero"])}">'
                        f'<button class="actbtn" type="submit">✅ Fiz a tarefa desta semana</button>'
                        f'</form>')
            destaque = ' style="border-color:var(--ouro2)"' if i == 0 else ""
            partes.append(
                f'<div class="panel"{destaque}>'
                f'<p class="plabel">Semana {int(it["numero"])} de {_cfg.TRILHA_TOTAL}</p>'
                f'<h3 style="margin:4px 0 0">{_esc(it["titulo"])}</h3>'
                f'{ferramenta}{acao}</div>')
        linhas = "".join(partes)
    corpo = f"""
    <div class="wrap">
      <h2 class="disp">{_esc(_cfg.TRILHA_NOME)}</h2>
      <p class="hint">Uma peça por sábado. Cada uma tem uma tarefa pequena — é ela que faz a diferença.</p>
      {msg_html}
      {linhas}
      <p style="margin:22px 0 0"><a class="cta ghost" href="/minha">Voltar</a></p>
    </div>"""
    return _pagina(f"{_cfg.TRILHA_NOME} · {PRODUTO}", corpo, logado=True, atual="/trilha",
                   meta_extra='<meta name="robots" content="noindex">')
```

- [ ] **Step 5: Ligar as rotas**

Em `app/serve.py`, no handler GET, logo depois do bloco `if path == "/meus-dados":` (linha ~514), acrescentar:

```python
        if path == "/trilha":
            sub = self._sub_logado()
            if not sub:
                return self._redirect("/entrar")
            return self._html(self._pagina_trilha(sub))
        if path.startswith("/ferramentas/"):
            if not self._sub_logado():          # download é fechado: só assinante logado
                return self._redirect("/entrar")
            import mimetypes
            import trilha as _trilha
            caminho = _trilha.caminho_ferramenta(path[len("/ferramentas/"):])
            if not caminho:
                return self._html("<h3>Arquivo não encontrado</h3>", 404)
            tipo = mimetypes.guess_type(caminho)[0] or "application/octet-stream"
            body = open(caminho, "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Disposition",
                             f'attachment; filename="{os.path.basename(caminho)}"')
            self.end_headers()
            return self.wfile.write(body)
```

E acrescentar o helper na mesma classe do handler:

```python
    def _pagina_trilha(self, sub, msg=""):
        """Monta os itens da trilha do assinante (peça atual + anteriores)."""
        import db as _db, site_web as _sw, trilha as _trilha
        itens = []
        atual = _trilha.proxima_peca(sub["id"])
        vistos = set()
        for env in _db.trilha_historico(sub["id"]):
            p = _db.trilha_peca(env["numero"]) or {}
            itens.append({"numero": env["numero"], "titulo": p.get("titulo", ""),
                          "feito": bool(env.get("feito_em")),
                          "ferramenta_slug": p.get("ferramenta_slug", "")})
            vistos.add(env["numero"])
        if atual and atual["numero"] not in vistos:
            # ainda não recebeu por WhatsApp (entrou hoje): mostra o que vem aí
            itens.insert(0, {"numero": atual["numero"], "titulo": atual.get("titulo", ""),
                             "feito": False, "ferramenta_slug": atual.get("ferramenta_slug", "")})
        return _sw.pagina_trilha(sub, itens, msg=msg)
```

No handler POST (`do_POST`, linha 571), **depois** da linha `g = lambda k: form.get(k, [""])[0]`
(linha 592) — `g` é o acessor de formulário do repo; não existe `self._form()`:

```python
        if path == "/trilha":
            sub = self._sub_logado()
            if not sub:
                return self._redirect("/entrar")
            msg = ""
            if g("acao") == "marcar_feito":
                import db as _db
                try:
                    numero = int(g("numero") or 0)
                except ValueError:
                    numero = 0
                if _db.trilha_marcar_feito(sub["id"], numero):
                    msg = "Marcado. Bom trabalho."
            return self._html(self._pagina_trilha(sub, msg=msg))
```

Acrescentar também o cartão de acesso em `site_web.pagina_minha`, dentro do `<p>` final:

```python
      <p style="margin:22px 0 0"><a class="cta ghost" href="/trilha">Minha trilha</a>
      <a class="cta ghost" href="/meus-dados">Meus dados</a></p>
```

Helpers do handler que este task usa e que **já existem** (não criar duplicata):
`self._sessao()` (137), `self._redirect()` (144), `self._html()` (556), `self._sub_logado()` (1144).
Não existem `self._form()`, `self._404()` nem `self._arquivo()` — por isso o código acima escreve
o download na mão, no mesmo formato da rota `/pdf/` (linha 242).

- [ ] **Step 6: Conferir a guarda de sessão do download**

Run: `cd app && grep -n -A3 'path.startswith("/ferramentas/")' serve.py`
Expected: o `if not self._sub_logado(): return self._redirect("/entrar")` aparece **antes** de
qualquer leitura de arquivo.

Este repo testa funções puras, não rotas HTTP — não há harness de request nos testes existentes.
A trava de travessia de diretório está coberta em teste (`test_path_traversal_e_barrado`); a trava
de sessão é verificada por inspeção aqui. Não invente um teste de rota que não roda.

- [ ] **Step 7: Rodar e confirmar que passa**

Run: `cd app && python3 -m unittest tests.test_trilha_web -v`
Expected: PASS

- [ ] **Step 8: Rodar a suíte inteira**

Run: `cd app && python3 -m unittest discover -s tests`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add app/trilha.py app/site_web.py app/serve.py app/tests/test_trilha_web.py
git commit -m "feat(trilha): pagina do assinante, botao fiz e download fechado da ferramenta"
```

---

### Task 7: Painel do admin

**Files:**
- Modify: `app/site_web.py`
- Modify: `app/serve.py` (rota GET `/admin/trilha` + item no `_admin_nav`)
- Test: `app/tests/test_trilha_web.py` (classe nova)

**Interfaces:**
- Consumes: `db.trilha_painel` (Task 1); `subscribers.por_id`
- Produces: `site_web.pagina_admin_trilha(linhas:list[dict], token:str="") -> str` — cada linha: `nome`, `proxima_peca`, `enviadas`, `feitas`, `concluiu:bool`

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar a `app/tests/test_trilha_web.py`:

```python
class TestAdminTrilha(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        for m in ("config", "db", "site_web"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, site_web
        for m in (config, db, site_web):
            importlib.reload(m)
        db.init()
        self.w = site_web

    def test_lista_assinantes_com_posicao(self):
        linhas = [{"nome": "Diego", "proxima_peca": 4, "enviadas": 3, "feitas": 2,
                   "concluiu": False}]
        h = self.w.pagina_admin_trilha(linhas)
        self.assertIn("Diego", h)
        self.assertIn("4", h)

    def test_marca_quem_concluiu(self):
        linhas = [{"nome": "Ana", "proxima_peca": 13, "enviadas": 12, "feitas": 12,
                   "concluiu": True}]
        h = self.w.pagina_admin_trilha(linhas)
        self.assertIn("Concluiu", h)

    def test_sem_ninguem_na_trilha_nao_quebra(self):
        h = self.w.pagina_admin_trilha([])
        self.assertIn("Ninguém", h)

    def test_escapa_nome(self):
        linhas = [{"nome": "<script>x</script>", "proxima_peca": 1, "enviadas": 0,
                   "feitas": 0, "concluiu": False}]
        self.assertNotIn("<script>x", self.w.pagina_admin_trilha(linhas))
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `cd app && python3 -m unittest tests.test_trilha_web.TestAdminTrilha -v`
Expected: FAIL — `AttributeError: module 'site_web' has no attribute 'pagina_admin_trilha'`

- [ ] **Step 3: Implementar a página**

Acrescentar a `app/site_web.py`:

```python
def pagina_admin_trilha(linhas, token=""):
    """Quem está em qual semana da trilha, quanto recebeu e quanto executou."""
    import config as _cfg
    if not linhas:
        corpo_lista = '<p class="hint">Ninguém entrou na trilha ainda.</p>'
    else:
        cards = []
        for l in linhas:
            estado = "Concluiu" if l.get("concluiu") else f"Semana {int(l['proxima_peca'])}"
            cards.append(
                f'<div class="panel">'
                f'<h3 style="margin:0">{_esc(l.get("nome") or "—")}</h3>'
                f'<p class="hint" style="margin:6px 0 0">{_esc(estado)} · '
                f'{int(l.get("enviadas", 0))} recebida(s) · {int(l.get("feitas", 0))} feita(s)</p>'
                f'</div>')
        corpo_lista = "".join(cards)
    corpo = f"""
    <div class="wrap">
      {_admin_nav(token, atual="/admin/trilha")}
      <h2 class="disp">{_esc(_cfg.TRILHA_NOME)}</h2>
      <p class="hint">{len(linhas)} assinante(s) na trilha · {_cfg.TRILHA_TOTAL} peças no total.</p>
      {corpo_lista}
    </div>"""
    return _pagina(f"Trilha · {PRODUTO}", corpo, logado=True, atual="/admin/trilha",
                   meta_extra='<meta name="robots" content="noindex">')
```

Usa `panel` (classe que já existe no `_CSS` de `site_web.py`), não tabela: `.tbl` **não existe**
no CSS deste repo, e a tela de assinantes já foi redesenhada em cartões justamente porque tabela
trunca no celular.

- [ ] **Step 4: Ligar a rota**

Em `app/serve.py`, no handler GET, **antes** do bloco genérico `if path.startswith("/admin"):`
(linha ~343) — senão o genérico captura a rota primeiro. A guarda é a mesma de `/admin/precos`
(linha 333), copiada literalmente:

```python
        if path == "/admin/trilha":
            import config, site_web, db as _db, subscribers as _subs
            q = up.parse_qs(up.urlparse(self.path).query)
            token_ok = config.ADMIN_TOKEN and q.get("token", [""])[0] == config.ADMIN_TOKEN
            if not token_ok:
                return self._html("<h3>Acesso negado</h3>", 403)
            _db.init()
            linhas = []
            for l in _db.trilha_painel():
                reg = _subs.por_id(l["subscriber_id"]) or {}
                linhas.append({"nome": reg.get("nome") or l["subscriber_id"],
                               "proxima_peca": l["proxima_peca"],
                               "enviadas": l["enviadas"], "feitas": l["feitas"],
                               "concluiu": l["proxima_peca"] > config.TRILHA_TOTAL})
            return self._html(site_web.pagina_admin_trilha(linhas, config.ADMIN_TOKEN or ""), 200)
```

Acrescentar o item `📘 Trilha → /admin/trilha` em `site_web._admin_nav` (linha 645), no mesmo formato dos itens existentes.

- [ ] **Step 5: Rodar a suíte inteira**

Run: `cd app && python3 -m unittest discover -s tests`
Expected: PASS

- [ ] **Step 6: Verificar a rota de admin manualmente**

Run: `cd app && python3 -c "import serve" && grep -n "admin/trilha" serve.py site_web.py`
Expected: importa sem erro e a rota aparece nos dois arquivos.

- [ ] **Step 7: Commit**

```bash
git add app/site_web.py app/serve.py app/tests/test_trilha_web.py
git commit -m "feat(trilha): painel do admin com posicao e execucao por assinante"
```

---

## Depois do plano (não são tasks)

1. **Escrever o texto das 12 peças.** O que entra aqui é esqueleto. As peças 7 e 8 são do sócio comercial.
2. **Produzir as ferramentas** (`seed/trilha/ferramentas/`): planilha de custo/hora, mapa de linha, modelo de plano, planilha de precificação, roteiro de 5 perguntas, régua de acompanhamento, painel mensal.
3. **Conferir um PDF real** antes de mandar pra base. O layout aqui nunca foi impresso.
4. **Trocar `config.TRILHA_NOME`** quando o nome do negócio for decidido com o sócio.
5. **Deploy:** `git push origin main` + `services.app.deployService` no EasyPanel.
