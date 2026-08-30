# Série de Peptídeos (item 44) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A trilha (hoje só "empreendedorismo médico") vira multi-produto: um catálogo em `config.py`, um seletor de "qual trilha está ativa" no admin, e um motor de envio que resolve por assinante qual produto ele recebe — quem está no meio de um termina antes de entrar no próximo. A trilha de peptídeos entra nesse catálogo com 2 peças por sábado (vs. 1 da trilha de empreendedorismo) e uma 4ª seção de peça, `aviso`, que vira um bloco de alerta com cor própria no PDF.

**Architecture:** Generaliza `trilha.py`/`db.py`/`config.py` (já existentes, isolados de `daily.py`) em vez de duplicar o motor por produto. As 3 tabelas da trilha ganham `produto` como parte da chave; um catálogo `config.TRILHAS` substitui as constantes fixas `TRILHA_NOME`/`TRILHA_TOTAL`/`TRILHA_DIR`; uma função nova, `trilha.produto_do_assinante`, decide a cada sábado qual produto cada assinante recebe. Não modifica `daily.py`. O texto das 11 peças de peptídeos é trabalho separado, depois deste plano — o catálogo já suporta o produto "peptideos" com um diretório de seed vazio (`semear()` não quebra com diretório ausente/vazio, mesmo comportamento de hoje).

**Tech Stack:** Python stdlib (sem pip), SQLite em dev/teste e Postgres/Supabase em produção via `db._conn()`, `unittest`, HTML server-side em `site_web.py`.

## Global Constraints

- **Sem dependência nova.**
- **Todo SQL roda em SQLite E Postgres.** Placeholder é `?` (o `_Wrap` traduz pra `%s`).
- **Toda tabela entra em `db._TABELAS`** (`db.py:304`) — alimenta `_habilitar_rls()`. Os nomes das 3 tabelas da trilha não mudam, só o schema — nada a adicionar na lista.
- **Catálogo, não hardcode.** Nenhuma função do motor (`trilha.py`) pode ter um `if produto == "peptideos"` — tudo que varia por produto (nome, total, diretório, peças por envio, se exige aviso) mora em `config.TRILHAS`.
- **Não modificar `daily.py`.** Se um task parecer exigir isso, pare e reporte.
- **Nunca `git add -A`.** Outros agentes trabalham neste repo em paralelo; stagear só os arquivos do próprio task.
- **Rodar os testes assim:** `cd app && python3 -m unittest discover -s tests`
- Idioma de código e comentários: português, como o resto do repo.
- **Migração assume produção com as tabelas praticamente vazias** (a trilha de empreendedorismo nunca foi ligada — `trilha_progresso`/`trilha_envios` não têm assinante nenhum; `trilha_pecas` tem as 12 peças escritas). A migração cobre os dois casos (vazio e com dado) da mesma forma — não é uma suposição arriscada, é o design certo de qualquer jeito.

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `app/config.py` (modificar) | `TRILHAS` — catálogo por produto (nome/total/dir/pecas_por_envio/exige_aviso). `TRILHA_DIA` continua compartilhado. |
| `app/db.py` (modificar) | Schema das 3 tabelas com `produto` na chave + coluna `aviso`; migração idempotente; toda função `trilha_*` ganha parâmetro `produto`. |
| `app/trilha.py` (modificar) | `parse_peca` ganha a seção `aviso`; `semear`/`semear_produto` por produto; `produto_do_assinante` (o coração da troca-sem-perder-progresso); `produto_ativo`/`definir_produto_ativo` no lugar do booleano `ativa`/`definir_ativa`; `proxima_peca`/`abertura` produto-aware; `enviar_para` manda `pecas_por_envio` peças em sequência; `caminho_ferramenta` busca em todos os diretórios do catálogo. |
| `app/pdf_trilha.py` (modificar) | Bloco `.bloco.alerta` (borda vermelho/âmbar) pra seção `aviso`; nome/total do produto lidos de `config.TRILHAS[peca["produto"]]` em vez de constante fixa. |
| `app/site_web.py` (modificar) | `pagina_trilha` e `pagina_admin_trilha` ganham parâmetro `produto` (e `pagina_admin_trilha` ganha `produto_ativo` pro seletor). |
| `app/serve.py` (modificar) | Rotas `/trilha`, `/admin/trilha`, `/admin/trilha/peca/<n>` resolvem `produto` (do assinante ou da querystring); `_trilha_numero_valido` ganha parâmetro `produto`. |
| `app/tests/test_trilha.py` (modificar) | Toda a suíte passa `produto` explícito; casos novos de `produto_do_assinante`, migração, lote de 2 peças, bloco de aviso. |
| `app/tests/test_trilha_web.py` (modificar) | Rotas admin/assinante com `produto`; seletor de trilha ativa. |

---

### Task 1: Catálogo de trilhas + migração das tabelas

**Files:**
- Modify: `app/config.py:70-77` (bloco `TRILHA_NOME`/`TRILHA_DIA`/`TRILHA_TOTAL`/`TRILHA_DIR`)
- Modify: `app/db.py:252-274` (CREATE TABLE de `trilha_pecas`/`trilha_progresso`/`trilha_envios`)
- Modify: `app/db.py` (`init()`, `_migrar_colunas` e vizinhança) — nova função `_tem_coluna` e `_migrar_trilha_multiproduto`
- Test: `app/tests/test_trilha.py` (nova classe `TestMigracaoMultiproduto`)

**Interfaces:**
- Produces: `config.TRILHAS` (dict, chave = id do produto: `"empreendedorismo"`, `"peptideos"`; valores: `nome`, `total`, `dir`, `pecas_por_envio`, `exige_aviso`), `config.TRILHA_DIA` (str, inalterado).
- Produces: `db._tem_coluna(c, tabela, coluna) -> bool`, `db._migrar_trilha_multiproduto()` (chamada de dentro de `db.init()`).

- [ ] **Step 1: Write the failing test**

```python
# em app/tests/test_trilha.py, adicionar a classe abaixo (junto das outras)
class TestMigracaoMultiproduto(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg, self.db, self.subs = _recarregar(self.tmp)

    def test_catalogo_tem_os_dois_produtos(self):
        self.assertIn("empreendedorismo", self.cfg.TRILHAS)
        self.assertIn("peptideos", self.cfg.TRILHAS)
        self.assertEqual(self.cfg.TRILHAS["empreendedorismo"]["total"], 12)
        self.assertEqual(self.cfg.TRILHAS["peptideos"]["total"], 11)
        self.assertEqual(self.cfg.TRILHAS["peptideos"]["pecas_por_envio"], 2)
        self.assertEqual(self.cfg.TRILHAS["empreendedorismo"]["pecas_por_envio"], 1)

    def test_tabelas_novas_tem_coluna_produto(self):
        with self.db._conn() as c:
            self.assertTrue(self.db._tem_coluna(c, "trilha_pecas", "produto"))
            self.assertTrue(self.db._tem_coluna(c, "trilha_progresso", "produto"))
            self.assertTrue(self.db._tem_coluna(c, "trilha_envios", "produto"))
            self.assertTrue(self.db._tem_coluna(c, "trilha_pecas", "aviso"))

    def test_migracao_preserva_pecas_existentes_marcando_empreendedorismo(self):
        # simula um banco ANTIGO (schema de 1 produto só) já com 1 peça gravada,
        # roda a migração de novo e confere que a peça sobrevive marcada.
        with self.db._conn() as c:
            c.execute("DROP TABLE trilha_pecas")
            c.execute("""CREATE TABLE trilha_pecas (
                numero INTEGER PRIMARY KEY, eixo TEXT DEFAULT '', titulo TEXT DEFAULT '',
                corpo TEXT DEFAULT '', micro_resultado TEXT DEFAULT '',
                mentalidade TEXT DEFAULT '', ferramenta_slug TEXT DEFAULT '',
                ativa INTEGER DEFAULT 1, atualizado_em TEXT)""")
            c.execute("INSERT INTO trilha_pecas (numero, titulo) VALUES (1, 'Peça velha')")
        self.db._migrar_trilha_multiproduto()
        p = self.db.trilha_peca("empreendedorismo", 1)
        self.assertIsNotNone(p)
        self.assertEqual(p["titulo"], "Peça velha")

    def test_migracao_e_idempotente(self):
        self.db._migrar_trilha_multiproduto()   # 2ª chamada não pode quebrar
        self.assertTrue(True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_trilha.TestMigracaoMultiproduto -v`
Expected: FAIL — `config` não tem atributo `TRILHAS`, `db` não tem `_tem_coluna`/`_migrar_trilha_multiproduto`.

- [ ] **Step 3: Implementar o catálogo em `config.py`**

Substituir o bloco em `app/config.py:70-77`:

```python
# Trilhas semanais (sábado, drip por assinante). Só UMA fica ativa por vez —
# ver trilha.produto_ativo()/definir_produto_ativo(). Quem já está no meio de
# uma trilha termina ela antes de entrar na próxima, não importa qual está
# ativa (trilha.produto_do_assinante decide isso, não este catálogo).
_SEED_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRILHA_DIA = "sabado"
TRILHAS = {
    "empreendedorismo": {
        # Mesmas env vars de antes (DSCURSO_TRILHA_NOME/DSCURSO_TRILHA_DIR) —
        # overrides já usados em deploy e em testes que isolam o diretório
        # continuam funcionando sem mudança nenhuma.
        "nome": os.environ.get("DSCURSO_TRILHA_NOME") or "Trilha do Consultório Lucrativo",
        "total": 12,
        "dir": os.environ.get("DSCURSO_TRILHA_DIR") or os.path.join(_SEED_BASE, "seed", "trilha"),
        "pecas_por_envio": 1,
        "exige_aviso": False,
    },
    "peptideos": {
        "nome": os.environ.get("DSCURSO_PEPTIDEOS_NOME") or "Peptídeos (nome a definir)",
        "total": 11,
        "dir": os.environ.get("DSCURSO_PEPTIDEOS_DIR") or os.path.join(_SEED_BASE, "seed", "peptideos"),
        "pecas_por_envio": 2,
        # Achado do levantamento de pesquisa: praticamente toda peça precisa da
        # nota de "sem registro ANVISA" — `trilha.semear()` avisa no log quantas
        # peças deste produto ficaram sem o campo `aviso`.
        "exige_aviso": True,
    },
}
```

- [ ] **Step 4: Recriar o schema das 3 tabelas em `db.py`**

Substituir o bloco em `app/db.py:252-274` (dentro do `executescript` de `init()`):

```python
            CREATE TABLE IF NOT EXISTS trilha_pecas (
                produto TEXT NOT NULL DEFAULT 'empreendedorismo',
                numero INTEGER NOT NULL,
                eixo TEXT DEFAULT '',
                titulo TEXT DEFAULT '',
                corpo TEXT DEFAULT '',
                micro_resultado TEXT DEFAULT '',
                mentalidade TEXT DEFAULT '',
                aviso TEXT DEFAULT '',
                ferramenta_slug TEXT DEFAULT '',
                ativa INTEGER DEFAULT 1,
                atualizado_em TEXT,
                PRIMARY KEY (produto, numero)
            );
            CREATE TABLE IF NOT EXISTS trilha_progresso (
                subscriber_id TEXT NOT NULL,
                produto TEXT NOT NULL,
                proxima_peca INTEGER DEFAULT 1,
                ultimo_envio TEXT DEFAULT '',
                PRIMARY KEY (subscriber_id, produto)
            );
            CREATE TABLE IF NOT EXISTS trilha_envios (
                subscriber_id TEXT NOT NULL,
                produto TEXT NOT NULL,
                numero INTEGER,
                enviado_em TEXT,
                feito_em TEXT,
                PRIMARY KEY (subscriber_id, produto, numero)
            );
```

- [ ] **Step 5: Helper de introspecção de coluna e migração, em `db.py`**

Adicionar logo depois de `_add_coluna` (perto de `app/db.py:321`):

```python
def _tem_coluna(c, tabela, coluna):
    """True se `coluna` já existe em `tabela` — usado ANTES de recriar schema
    (diferente de `_add_coluna`, que só adiciona coluna solta)."""
    if _is_pg():
        r = c.execute("SELECT 1 FROM information_schema.columns "
                      "WHERE table_name=? AND column_name=?", (tabela, coluna)).fetchone()
        return r is not None
    linhas = c.execute(f"PRAGMA table_info({tabela})").fetchall()
    return any(dict(l)["name"] == coluna for l in linhas)


def _migrar_trilha_multiproduto():
    """As 3 tabelas da trilha ganham `produto` na CHAVE (não só uma coluna solta:
    sem isso, a peça 1 de "peptideos" colidiria com a peça 1 de "empreendedorismo"
    no PRIMARY KEY antigo). PRIMARY KEY não dá pra alterar com ALTER TABLE nem no
    SQLite nem no Postgres -- recria as 3 tabelas com o schema novo e copia o que
    já existe, marcado como 'empreendedorismo' (único produto que já rodou).
    Idempotente: sai cedo se `trilha_pecas` já tem a coluna `produto` (banco novo,
    criado direto pelo CREATE TABLE de cima, cai aqui também e não faz nada)."""
    with _conn() as c:
        if _tem_coluna(c, "trilha_pecas", "produto"):
            return
        c.execute("""CREATE TABLE trilha_pecas_novo (
                produto TEXT NOT NULL DEFAULT 'empreendedorismo',
                numero INTEGER NOT NULL,
                eixo TEXT DEFAULT '', titulo TEXT DEFAULT '', corpo TEXT DEFAULT '',
                micro_resultado TEXT DEFAULT '', mentalidade TEXT DEFAULT '',
                aviso TEXT DEFAULT '', ferramenta_slug TEXT DEFAULT '',
                ativa INTEGER DEFAULT 1, atualizado_em TEXT,
                PRIMARY KEY (produto, numero))""")
        c.execute("""INSERT INTO trilha_pecas_novo
                (produto, numero, eixo, titulo, corpo, micro_resultado, mentalidade,
                 aviso, ferramenta_slug, ativa, atualizado_em)
            SELECT 'empreendedorismo', numero, eixo, titulo, corpo, micro_resultado,
                   mentalidade, '', ferramenta_slug, ativa, atualizado_em
            FROM trilha_pecas""")
        c.execute("DROP TABLE trilha_pecas")
        c.execute("ALTER TABLE trilha_pecas_novo RENAME TO trilha_pecas")

        c.execute("""CREATE TABLE trilha_progresso_novo (
                subscriber_id TEXT NOT NULL, produto TEXT NOT NULL,
                proxima_peca INTEGER DEFAULT 1, ultimo_envio TEXT DEFAULT '',
                PRIMARY KEY (subscriber_id, produto))""")
        c.execute("""INSERT INTO trilha_progresso_novo
                (subscriber_id, produto, proxima_peca, ultimo_envio)
            SELECT subscriber_id, 'empreendedorismo', proxima_peca, ultimo_envio
            FROM trilha_progresso""")
        c.execute("DROP TABLE trilha_progresso")
        c.execute("ALTER TABLE trilha_progresso_novo RENAME TO trilha_progresso")

        c.execute("""CREATE TABLE trilha_envios_novo (
                subscriber_id TEXT NOT NULL, produto TEXT NOT NULL, numero INTEGER,
                enviado_em TEXT, feito_em TEXT,
                PRIMARY KEY (subscriber_id, produto, numero))""")
        c.execute("""INSERT INTO trilha_envios_novo
                (subscriber_id, produto, numero, enviado_em, feito_em)
            SELECT subscriber_id, 'empreendedorismo', numero, enviado_em, feito_em
            FROM trilha_envios""")
        c.execute("DROP TABLE trilha_envios")
        c.execute("ALTER TABLE trilha_envios_novo RENAME TO trilha_envios")
```

Chamar a migração em `init()`, logo depois de `_migrar_colunas()` (`app/db.py:294`):

```python
    _migrar_colunas()
    _migrar_trilha_multiproduto()
    _migrar_indices()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_trilha.TestMigracaoMultiproduto -v`
Expected: PASS. (Vai FALHAR ainda em outras classes que chamam `trilha_upsert_peca`/`trilha_peca` com a assinatura antiga — normal, o Task 2 corrige.)

- [ ] **Step 7: Commit**

```bash
git add app/config.py app/db.py app/tests/test_trilha.py
git commit -m "feat(trilha): catalogo de trilhas + migracao multi-produto das tabelas"
```

---

### Task 2: Funções de banco produto-aware

**Files:**
- Modify: `app/db.py:1898-2041` (todas as funções `trilha_*`)
- Test: `app/tests/test_trilha.py` (classe `TestBancoTrilha`)

**Interfaces:**
- Consumes: schema do Task 1 (`produto` na chave das 3 tabelas).
- Produces: `db.trilha_upsert_peca(produto, numero, eixo, titulo, corpo, micro_resultado, mentalidade, aviso="", ferramenta_slug="")`, `db.trilha_peca(produto, numero)`, `db.trilha_posicao(sub_id, produto)`, `db.trilha_posicao_leitura(sub_id, produto)` (nova — leitura sem criar linha), `db.trilha_registrar_envio(sub_id, produto, numero)`, `db.trilha_avancar(sub_id, produto, numero)`, `db.trilha_marcar_feito(sub_id, produto, numero)`, `db.trilha_fez(sub_id, produto, numero)`, `db.trilha_historico(sub_id, produto)`, `db.trilha_painel(produto)`, `db.trilha_listar_pecas(produto)`.

- [ ] **Step 1: Write the failing test — substituir a classe `TestBancoTrilha` inteira**

```python
class TestBancoTrilha(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg, self.db, self.subs = _recarregar(self.tmp)

    def _peca(self, produto="empreendedorismo", numero=1):
        self.db.trilha_upsert_peca(produto, numero, "Saber onde você está", f"Peça {numero}",
                                   "corpo", "micro", "mentalidade", "", "")

    def test_upsert_peca_grava_e_le(self):
        self._peca()
        p = self.db.trilha_peca("empreendedorismo", 1)
        self.assertEqual(p["titulo"], "Peça 1")
        self.assertEqual(p["micro_resultado"], "micro")
        self.assertEqual(p["produto"], "empreendedorismo")

    def test_upsert_peca_atualiza_em_vez_de_duplicar(self):
        self._peca()
        self.db.trilha_upsert_peca("empreendedorismo", 1, "eixo novo", "Título novo",
                                   "c", "m", "t", "", "")
        self.assertEqual(self.db.trilha_peca("empreendedorismo", 1)["titulo"], "Título novo")

    def test_dois_produtos_podem_usar_o_mesmo_numero(self):
        # a razão de existir do `produto` na chave: sem ele, a peça 1 de
        # "peptideos" pisaria na peça 1 de "empreendedorismo".
        self._peca("empreendedorismo", 1)
        self.db.trilha_upsert_peca("peptideos", 1, "eixo", "Peça peptídeo 1",
                                   "corpo p", "", "", "aviso p", "")
        self.assertEqual(self.db.trilha_peca("empreendedorismo", 1)["titulo"], "Peça 1")
        self.assertEqual(self.db.trilha_peca("peptideos", 1)["titulo"], "Peça peptídeo 1")
        self.assertEqual(self.db.trilha_peca("peptideos", 1)["aviso"], "aviso p")

    def test_peca_inexistente_devolve_none(self):
        self.assertIsNone(self.db.trilha_peca("empreendedorismo", 13))

    def test_posicao_nasce_em_1(self):
        self.assertEqual(self.db.trilha_posicao("sub-a", "empreendedorismo"), 1)

    def test_posicao_leitura_nao_cria_linha_quando_nunca_comecou(self):
        self.assertIsNone(self.db.trilha_posicao_leitura("sub-a", "peptideos"))
        # confirma que NÃO criou linha (senão a próxima leitura devolveria 1, não None)
        self.assertIsNone(self.db.trilha_posicao_leitura("sub-a", "peptideos"))

    def test_posicao_leitura_reflete_avanco(self):
        self.db.trilha_avancar("sub-a", "empreendedorismo", 1)
        self.assertEqual(self.db.trilha_posicao_leitura("sub-a", "empreendedorismo"), 2)

    def test_registrar_envio_e_idempotente(self):
        self.assertTrue(self.db.trilha_registrar_envio("sub-a", "empreendedorismo", 1))
        self.assertFalse(self.db.trilha_registrar_envio("sub-a", "empreendedorismo", 1))
        self.assertTrue(self.db.trilha_registrar_envio("sub-a", "empreendedorismo", 2))
        self.assertTrue(self.db.trilha_registrar_envio("sub-b", "empreendedorismo", 1))
        # mesmo numero, produto diferente -- não é a mesma linha
        self.assertTrue(self.db.trilha_registrar_envio("sub-a", "peptideos", 1))

    def test_avancar_move_a_posicao(self):
        self.db.trilha_avancar("sub-a", "empreendedorismo", 1)
        self.assertEqual(self.db.trilha_posicao("sub-a", "empreendedorismo"), 2)

    def test_marcar_feito_e_idempotente(self):
        self.db.trilha_registrar_envio("sub-a", "empreendedorismo", 1)
        self.assertFalse(self.db.trilha_fez("sub-a", "empreendedorismo", 1))
        self.assertTrue(self.db.trilha_marcar_feito("sub-a", "empreendedorismo", 1))
        self.assertTrue(self.db.trilha_fez("sub-a", "empreendedorismo", 1))
        self.assertFalse(self.db.trilha_marcar_feito("sub-a", "empreendedorismo", 1))

    def test_marcar_feito_em_peca_nao_enviada_nao_grava(self):
        self.assertFalse(self.db.trilha_marcar_feito("sub-a", "empreendedorismo", 7))
        self.assertFalse(self.db.trilha_fez("sub-a", "empreendedorismo", 7))

    def test_historico_vem_do_mais_recente(self):
        self.db.trilha_registrar_envio("sub-a", "empreendedorismo", 1)
        self.db.trilha_registrar_envio("sub-a", "empreendedorismo", 2)
        h = self.db.trilha_historico("sub-a", "empreendedorismo")
        self.assertEqual([x["numero"] for x in h], [2, 1])

    def test_historico_nao_mistura_produtos(self):
        self.db.trilha_registrar_envio("sub-a", "empreendedorismo", 1)
        self.db.trilha_registrar_envio("sub-a", "peptideos", 1)
        self.assertEqual(len(self.db.trilha_historico("sub-a", "empreendedorismo")), 1)
        self.assertEqual(len(self.db.trilha_historico("sub-a", "peptideos")), 1)

    def test_painel_conta_enviadas_e_feitas(self):
        self.db.trilha_registrar_envio("sub-a", "empreendedorismo", 1)
        self.db.trilha_registrar_envio("sub-a", "empreendedorismo", 2)
        self.db.trilha_marcar_feito("sub-a", "empreendedorismo", 1)
        self.db.trilha_avancar("sub-a", "empreendedorismo", 2)
        linha = [l for l in self.db.trilha_painel("empreendedorismo")
                if l["subscriber_id"] == "sub-a"][0]
        self.assertEqual(linha["enviadas"], 2)
        self.assertEqual(linha["feitas"], 1)
        self.assertEqual(linha["proxima_peca"], 3)

    def test_painel_nao_mistura_produtos(self):
        self.db.trilha_registrar_envio("sub-a", "empreendedorismo", 1)
        self.db.trilha_registrar_envio("sub-a", "peptideos", 1)
        self.db.trilha_registrar_envio("sub-a", "peptideos", 2)
        linha_pep = [l for l in self.db.trilha_painel("peptideos")
                    if l["subscriber_id"] == "sub-a"][0]
        self.assertEqual(linha_pep["enviadas"], 2)

    def test_tabelas_novas_estao_na_lista_de_rls(self):
        for t in ("trilha_pecas", "trilha_progresso", "trilha_envios"):
            self.assertIn(t, self.db._TABELAS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_trilha.TestBancoTrilha -v`
Expected: FAIL — funções ainda usam a assinatura antiga.

- [ ] **Step 3: Reescrever as funções `trilha_*` em `db.py`**

Substituir o bloco inteiro de `app/db.py:1898-2041` (de `trilha_upsert_peca` até `trilha_listar_pecas`):

```python
def trilha_upsert_peca(produto, numero, eixo, titulo, corpo, micro_resultado,
                       mentalidade, aviso="", ferramenta_slug=""):
    """Grava (ou atualiza) a peça `numero` do `produto`. Upsert de propósito: editar
    o arquivo em seed/<produto>/ e redeployar propaga o texto novo, não duplica."""
    from datetime import datetime
    with _conn() as c:
        c.execute(
            "INSERT INTO trilha_pecas "
            "(produto,numero,eixo,titulo,corpo,micro_resultado,mentalidade,aviso,"
            "ferramenta_slug,ativa,atualizado_em) "
            "VALUES (?,?,?,?,?,?,?,?,?,1,?) "
            "ON CONFLICT (produto,numero) DO UPDATE SET eixo=excluded.eixo, "
            "titulo=excluded.titulo, corpo=excluded.corpo, "
            "micro_resultado=excluded.micro_resultado, mentalidade=excluded.mentalidade, "
            "aviso=excluded.aviso, ferramenta_slug=excluded.ferramenta_slug, "
            "atualizado_em=excluded.atualizado_em",
            (produto, int(numero), eixo or "", titulo or "", corpo or "",
             micro_resultado or "", mentalidade or "", aviso or "", ferramenta_slug or "",
             datetime.now().isoformat()))


def trilha_peca(produto, numero):
    with _conn() as c:
        r = c.execute("SELECT * FROM trilha_pecas WHERE produto=? AND numero=? AND ativa=1",
                      (produto, int(numero))).fetchone()
    return dict(r) if r else None


def trilha_posicao(sub_id, produto):
    """Posição do assinante nesse produto. Quem nunca recebeu nasce em 1 (cria a
    linha). Para checar sem criar, ver `trilha_posicao_leitura`."""
    with _conn() as c:
        c.execute("INSERT INTO trilha_progresso (subscriber_id,produto,proxima_peca,ultimo_envio) "
                  "VALUES (?,?,1,'') ON CONFLICT (subscriber_id,produto) DO NOTHING",
                  (sub_id or "", produto))
        r = c.execute("SELECT proxima_peca FROM trilha_progresso "
                      "WHERE subscriber_id=? AND produto=?", (sub_id or "", produto)).fetchone()
    return int(r["proxima_peca"]) if r else 1


def trilha_posicao_leitura(sub_id, produto):
    """Posição do assinante nesse produto, ou None se ele NUNCA começou (não cria
    linha). Usado só pra decidir qual produto ele está fazendo agora
    (`trilha.produto_do_assinante`) -- chamar `trilha_posicao` aqui inscreveria
    todo mundo em todo produto do catálogo só de perguntar."""
    with _conn() as c:
        r = c.execute("SELECT proxima_peca FROM trilha_progresso "
                      "WHERE subscriber_id=? AND produto=?", (sub_id or "", produto)).fetchone()
    return int(r["proxima_peca"]) if r else None


def trilha_registrar_envio(sub_id, produto, numero):
    """Claim atômico do envio de UMA peça a UM assinante. True só na 1ª vez."""
    from datetime import datetime
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO trilha_envios (subscriber_id,produto,numero,enviado_em,feito_em) "
            "VALUES (?,?,?,?,NULL) ON CONFLICT (subscriber_id,produto,numero) DO NOTHING",
            (sub_id or "", produto, int(numero), datetime.now().isoformat()))
        return cur.rowcount > 0


def trilha_avancar(sub_id, produto, numero):
    """Move a posição para `numero`+1. Chamado SÓ depois do envio dar certo."""
    from datetime import datetime
    agora = datetime.now().isoformat()
    with _conn() as c:
        c.execute("INSERT INTO trilha_progresso (subscriber_id,produto,proxima_peca,ultimo_envio) "
                  "VALUES (?,?,?,?) ON CONFLICT (subscriber_id,produto) DO UPDATE SET "
                  "proxima_peca=excluded.proxima_peca, ultimo_envio=excluded.ultimo_envio",
                  (sub_id or "", produto, int(numero) + 1, agora))


def trilha_marcar_feito(sub_id, produto, numero):
    from datetime import datetime
    with _conn() as c:
        cur = c.execute("UPDATE trilha_envios SET feito_em=? "
                        "WHERE subscriber_id=? AND produto=? AND numero=? AND feito_em IS NULL",
                        (datetime.now().isoformat(), sub_id or "", produto, int(numero)))
        return cur.rowcount > 0


def trilha_fez(sub_id, produto, numero):
    with _conn() as c:
        r = c.execute("SELECT 1 FROM trilha_envios WHERE subscriber_id=? AND produto=? "
                      "AND numero=? AND feito_em IS NOT NULL",
                      (sub_id or "", produto, int(numero))).fetchone()
    return r is not None


def trilha_historico(sub_id, produto):
    with _conn() as c:
        rows = c.execute("SELECT numero, enviado_em, feito_em FROM trilha_envios "
                         "WHERE subscriber_id=? AND produto=? ORDER BY numero DESC",
                         (sub_id or "", produto)).fetchall()
    return [dict(r) for r in rows]


def trilha_painel(produto):
    """Uma linha por assinante que já entrou nesse produto: posição, quantas
    recebeu e quantas marcou como feitas. Alimenta /admin/trilha."""
    with _conn() as c:
        rows = c.execute(
            "SELECT p.subscriber_id AS subscriber_id, p.proxima_peca AS proxima_peca, "
            "COUNT(e.numero) AS enviadas, COUNT(e.feito_em) AS feitas "
            "FROM trilha_progresso p LEFT JOIN trilha_envios e "
            "ON e.subscriber_id = p.subscriber_id AND e.produto = p.produto "
            "WHERE p.produto=? "
            "GROUP BY p.subscriber_id, p.proxima_peca "
            "ORDER BY p.proxima_peca DESC", (produto,)).fetchall()
    return [dict(r) for r in rows]


def trilha_listar_pecas(produto):
    """Todas as peças do produto, em ordem. Alimenta a prévia do admin."""
    with _conn() as c:
        rows = c.execute("SELECT * FROM trilha_pecas WHERE produto=? ORDER BY numero",
                         (produto,)).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_trilha.TestBancoTrilha -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/db.py app/tests/test_trilha.py
git commit -m "feat(trilha): funcoes de banco da trilha ganham dimensao produto"
```

---

### Task 3: Parser da peça ganha `aviso` + semear multi-produto

**Files:**
- Modify: `app/trilha.py` (`_SECOES`, `parse_peca`, `semear`)
- Test: `app/tests/test_trilha.py` (classe `TestParseESeed`)

**Interfaces:**
- Consumes: `db.trilha_upsert_peca(produto, ...)` do Task 2.
- Produces: `trilha.parse_peca(texto) -> dict` (ganha chave `"aviso"`), `trilha.semear_produto(produto, diretorio=None) -> int`, `trilha.semear() -> dict` (`{produto: contagem}`).

- [ ] **Step 1: Write the failing test — substituir a classe `TestParseESeed` inteira**

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
        self.assertEqual(p["aviso"], "")

    def test_parse_le_secao_aviso(self):
        p = self.t.parse_peca(
            "titulo: GHK-Cu\neixo: Reparo de pele\n\n"
            "## corpo\ntexto\n\n"
            "## aviso\n"
            "A Anvisa nomeou o GHK-Cu injetável como ilegal para qualquer uso em saúde.\n")
        self.assertIn("ilegal", p["aviso"])

    def test_parse_sem_ferramenta_devolve_vazio(self):
        p = self.t.parse_peca("titulo: X\neixo: Y\n\n## corpo\nz\n")
        self.assertEqual(p["ferramenta"], "")
        self.assertEqual(p["micro_resultado"], "")

    def test_semear_produto_grava_as_pecas_do_diretorio(self):
        d = os.path.join(self.tmp, "trilha")
        os.makedirs(d)
        with open(os.path.join(d, "01-um.md"), "w", encoding="utf-8") as f:
            f.write("titulo: Um\neixo: A\n\n## corpo\ncorpo um\n")
        with open(os.path.join(d, "02-dois.md"), "w", encoding="utf-8") as f:
            f.write("titulo: Dois\neixo: A\n\n## corpo\ncorpo dois\n")
        self.assertEqual(self.t.semear_produto("empreendedorismo", d), 2)
        self.assertEqual(self.db.trilha_peca("empreendedorismo", 1)["titulo"], "Um")
        self.assertEqual(self.db.trilha_peca("empreendedorismo", 2)["titulo"], "Dois")

    def test_semear_produto_e_idempotente_e_atualiza_texto_editado(self):
        d = os.path.join(self.tmp, "trilha")
        os.makedirs(d)
        caminho = os.path.join(d, "01-um.md")
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("titulo: Um\neixo: A\n\n## corpo\nversao 1\n")
        self.t.semear_produto("empreendedorismo", d)
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("titulo: Um\neixo: A\n\n## corpo\nversao 2\n")
        self.t.semear_produto("empreendedorismo", d)
        self.assertIn("versao 2", self.db.trilha_peca("empreendedorismo", 1)["corpo"])

    def test_semear_produto_ignora_arquivo_sem_numero_no_nome(self):
        d = os.path.join(self.tmp, "trilha")
        os.makedirs(d)
        with open(os.path.join(d, "leiame.md"), "w", encoding="utf-8") as f:
            f.write("titulo: X\n\n## corpo\ny\n")
        self.assertEqual(self.t.semear_produto("empreendedorismo", d), 0)

    def test_semear_produto_diretorio_inexistente_nao_quebra(self):
        self.assertEqual(self.t.semear_produto("empreendedorismo",
                                               os.path.join(self.tmp, "nao-existe")), 0)

    def test_semear_roda_todos_os_produtos_do_catalogo(self):
        contagens = self.t.semear()
        self.assertEqual(contagens["empreendedorismo"], self.cfg.TRILHAS["empreendedorismo"]["total"])
        # "peptideos" ainda não tem conteúdo escrito -- 0 é o resultado correto,
        # não um erro (mesmo comportamento de diretório vazio/ausente).
        self.assertEqual(contagens.get("peptideos", 0), 0)

    def test_as_12_pecas_do_repo_carregam(self):
        contagens = self.t.semear()
        for n in range(1, self.cfg.TRILHAS["empreendedorismo"]["total"] + 1):
            p = self.db.trilha_peca("empreendedorismo", n)
            self.assertIsNotNone(p, f"peça {n} não carregou")
            self.assertTrue(p["titulo"].strip(), f"peça {n} sem título")

    def test_semear_avisa_quando_produto_exige_aviso_e_peca_nao_tem(self):
        d = os.path.join(self.tmp, "peptideos")
        os.makedirs(d)
        with open(os.path.join(d, "01-um.md"), "w", encoding="utf-8") as f:
            f.write("titulo: Sem aviso\neixo: A\n\n## corpo\ntexto\n")
        os.environ["DSCURSO_PEPTIDEOS_DIR"] = d
        import config
        importlib.reload(config)
        importlib.reload(self.t)
        try:
            with _CapturaPrint() as saida:
                self.t.semear()
            self.assertIn("sem `aviso`", saida.texto)
            self.assertIn("1", saida.texto)
        finally:
            os.environ.pop("DSCURSO_PEPTIDEOS_DIR", None)


class _CapturaPrint:
    """Captura stdout pra checar o aviso de log de `semear()` sem depender de
    `logging` (o repo usa `print(..., flush=True)` em toda parte)."""
    def __enter__(self):
        import io, contextlib
        self._redirect = contextlib.redirect_stdout(io.StringIO())
        self._buf = self._redirect.__enter__()
        self.texto = ""
        return self

    def __exit__(self, *exc):
        self.texto = self._buf.getvalue()
        self._redirect.__exit__(*exc)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_trilha.TestParseESeed -v`
Expected: FAIL — `semear_produto` não existe, `semear()` ainda devolve `int`, `parse_peca` não tem `aviso`.

- [ ] **Step 3: Implementar em `trilha.py`**

Substituir `_SECOES` (`app/trilha.py:16-17`):

```python
_SECOES = {"corpo": "corpo", "micro-resultado": "micro_resultado",
           "mentalidade": "mentalidade", "aviso": "aviso"}
```

Adicionar `"aviso"` ao dict devolvido por `parse_peca` (`app/trilha.py:44-51`):

```python
    return {
        "titulo": cab.get("titulo", ""),
        "eixo": cab.get("eixo", ""),
        "ferramenta": cab.get("ferramenta", ""),
        "corpo": "\n".join(secoes.get("corpo", [])).strip(),
        "micro_resultado": "\n".join(secoes.get("micro_resultado", [])).strip(),
        "mentalidade": "\n".join(secoes.get("mentalidade", [])).strip(),
        "aviso": "\n".join(secoes.get("aviso", [])).strip(),
    }
```

Substituir `semear` (`app/trilha.py:54-71`) por duas funções:

```python
def semear_produto(produto, diretorio=None):
    """Lê `seed/<produto>/NN-*.md` e grava no banco desse produto. Idempotente por
    (produto, numero): editar o texto e redeployar propaga a versão nova.
    Retorna quantas peças gravou."""
    d = diretorio if diretorio is not None else config.TRILHAS[produto]["dir"]
    if not os.path.isdir(d):
        return 0
    n = 0
    for nome in sorted(os.listdir(d)):
        m = re.match(r"^(\d{1,2})[-_]", nome)
        if not m or not nome.endswith(".md"):
            continue
        with open(os.path.join(d, nome), encoding="utf-8") as f:
            p = parse_peca(f.read())
        db.trilha_upsert_peca(produto, int(m.group(1)), p["eixo"], p["titulo"], p["corpo"],
                              p["micro_resultado"], p["mentalidade"], p["aviso"], p["ferramenta"])
        n += 1
    return n


def semear():
    """Semeia TODOS os produtos do catálogo. Produto sem diretório de conteúdo
    ainda (ex.: peptideos antes da redação das peças) conta 0, sem quebrar --
    mesma tolerância que `semear_produto` já tinha pra diretório ausente.

    Produtos com `exige_aviso=True` (a série de peptídeos) têm suas peças
    conferidas: cada uma sem o campo `aviso` preenchido vira uma linha no log de
    deploy -- sinal visível, não bloqueio duro (a peça de abertura pode
    legitimamente não precisar)."""
    contagens = {}
    for produto, info in config.TRILHAS.items():
        contagens[produto] = semear_produto(produto)
        if info.get("exige_aviso"):
            sem_aviso = [p["numero"] for p in db.trilha_listar_pecas(produto)
                        if not (p.get("aviso") or "").strip()]
            if sem_aviso:
                print(f"[trilha] {len(sem_aviso)} peça(s) de \"{produto}\" sem `aviso`: "
                      f"{sem_aviso}", flush=True)
    return contagens
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_trilha.TestParseESeed -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/trilha.py app/tests/test_trilha.py
git commit -m "feat(trilha): secao aviso na peca + semear multi-produto com log de faltantes"
```

---

### Task 4: `produto_do_assinante` — o motor da troca sem perder progresso

**Files:**
- Modify: `app/trilha.py` (nova função `produto_do_assinante`; `ativa`/`definir_ativa` viram `produto_ativo`/`definir_produto_ativo`)
- Test: `app/tests/test_trilha.py` (nova classe `TestProdutoDoAssinante`; classe `TestInterruptor` reescrita)

**Interfaces:**
- Consumes: `db.trilha_posicao_leitura`, `db.get_config`/`db.set_config`, `config.TRILHAS`.
- Produces: `trilha.produto_do_assinante(sub_id) -> str | None`, `trilha.produto_ativo() -> str` (`""` = nenhuma), `trilha.definir_produto_ativo(produto)` (aceita `""`/`None` = desligar; levanta `ValueError` pra produto desconhecido).

- [ ] **Step 1: Write the failing test**

```python
# em app/tests/test_trilha.py, adicionar:
class TestProdutoDoAssinante(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg, self.db, self.subs = _recarregar(self.tmp)
        import trilha
        importlib.reload(trilha)
        self.t = trilha

    def test_ninguem_ativo_e_ninguem_comecou_devolve_none(self):
        self.assertIsNone(self.t.produto_do_assinante("sub-a"))

    def test_assinante_novo_entra_no_produto_ativo(self):
        self.t.definir_produto_ativo("peptideos")
        self.assertEqual(self.t.produto_do_assinante("sub-a"), "peptideos")

    def test_meio_de_um_produto_continua_nele_mesmo_trocando_o_ativo(self):
        self.t.definir_produto_ativo("empreendedorismo")
        self.db.trilha_avancar("sub-a", "empreendedorismo", 1)   # está na peça 2 de 12
        self.t.definir_produto_ativo("peptideos")                # Diego troca a ativa
        self.assertEqual(self.t.produto_do_assinante("sub-a"), "empreendedorismo",
                         "quem tá no meio tem que terminar antes de trocar")

    def test_quem_concluiu_cai_no_produto_ativo(self):
        self.t.definir_produto_ativo("empreendedorismo")
        self.db.trilha_avancar("sub-a", "empreendedorismo", self.cfg.TRILHAS["empreendedorismo"]["total"])
        self.t.definir_produto_ativo("peptideos")
        self.assertEqual(self.t.produto_do_assinante("sub-a"), "peptideos")

    def test_definir_produto_ativo_rejeita_produto_desconhecido(self):
        with self.assertRaises(ValueError):
            self.t.definir_produto_ativo("nao-existe")

    def test_definir_produto_ativo_vazio_desliga(self):
        self.t.definir_produto_ativo("peptideos")
        self.t.definir_produto_ativo("")
        self.assertEqual(self.t.produto_ativo(), "")
        self.assertIsNone(self.t.produto_do_assinante("sub-a"))


class TestInterruptor(unittest.TestCase):
    """O interruptor mestre virou seletor de produto. Nasce sem nenhuma trilha
    ativa porque a trilha não tem aprovação por envio (o estudo diário tem, às
    18h): o conteúdo vai do arquivo direto pro WhatsApp de assinante pagante. Um
    deploy sozinho não pode começar a enviar."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg, self.db, self.subs = _recarregar(self.tmp)
        import trilha
        importlib.reload(trilha)
        self.t = trilha
        self.t.semear()

    def test_nasce_sem_produto_ativo(self):
        self.assertEqual(self.t.produto_ativo(), "")

    def test_ligar_e_desligar(self):
        self.t.definir_produto_ativo("empreendedorismo")
        self.assertEqual(self.t.produto_ativo(), "empreendedorismo")
        self.t.definir_produto_ativo("")
        self.assertEqual(self.t.produto_ativo(), "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_trilha.TestProdutoDoAssinante tests.test_trilha.TestInterruptor -v`
Expected: FAIL — `produto_do_assinante`/`produto_ativo`/`definir_produto_ativo` não existem ainda; `ativa`/`definir_ativa` (antigos) continuam na classe velha.

- [ ] **Step 3: Implementar em `trilha.py`**

Substituir `ativa`/`definir_ativa` (`app/trilha.py:202-213`):

```python
def produto_ativo():
    """Qual trilha aceita gente NOVA agora. Vazio = nenhuma -- mesma postura de
    segurança de antes (`ativa()` nascia False): sem escolha explícita, ninguém
    novo entra. Quem já está em progresso em outro produto não é afetado por
    isto (ver `produto_do_assinante`)."""
    v = db.get_config("trilha_produto_ativo", "")
    return v if v in config.TRILHAS else ""


def definir_produto_ativo(produto):
    if produto and produto not in config.TRILHAS:
        raise ValueError(f"produto de trilha desconhecido: {produto}")
    db.set_config("trilha_produto_ativo", produto or "")


def produto_do_assinante(sub_id):
    """Qual produto de trilha este assinante recebe agora.

    1. Se ele tem progresso INCOMPLETO em algum produto do catálogo, é esse --
       não importa qual está ativo agora. É isso que garante "termina antes de
       trocar".
    2. Senão (nunca começou nada, ou concluiu tudo que já tinha começado), cai
       no produto ativo do momento.
    3. Sem produto ativo, `None` -- ninguém novo entra.

    Invariante que sustenta o passo 1: nunca há dois produtos incompletos ao
    mesmo tempo pro mesmo assinante, porque só se entra num produto novo quando
    não sobra nenhum em aberto (não existe caminho pra "meio de A e meio de B"
    simultaneamente)."""
    for produto, info in config.TRILHAS.items():
        pos = db.trilha_posicao_leitura(sub_id, produto)
        if pos is not None and pos <= info["total"]:
            return produto
    return produto_ativo() or None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_trilha.TestProdutoDoAssinante tests.test_trilha.TestInterruptor -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/trilha.py app/tests/test_trilha.py
git commit -m "feat(trilha): produto_do_assinante decide qual trilha cada um recebe"
```

---

### Task 5: `proxima_peca`/`abertura` produto-aware

**Files:**
- Modify: `app/trilha.py` (`proxima_peca`, `abertura`, `_liberar_claim`)
- Test: `app/tests/test_trilha.py` (classe `TestDrip` reescrita)

**Interfaces:**
- Consumes: `trilha.produto_do_assinante` (Task 4).
- Produces: `trilha.proxima_peca(sub_id) -> dict | None` (dict ganha chave `"produto"`), `trilha.abertura(sub_id, produto, numero) -> str`, `trilha._liberar_claim(sub_id, produto, numero)`.

- [ ] **Step 1: Write the failing test — substituir a classe `TestDrip` inteira**

```python
class TestDrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg, self.db, self.subs = _recarregar(self.tmp)
        import trilha
        importlib.reload(trilha)
        self.t = trilha
        self.t.semear()
        self.t.definir_produto_ativo("empreendedorismo")

    def test_dia_da_trilha_e_sabado(self):
        from datetime import date
        self.assertTrue(self.t.e_dia_da_trilha(date(2026, 8, 8)))     # sábado
        self.assertFalse(self.t.e_dia_da_trilha(date(2026, 8, 7)))    # sexta
        self.assertFalse(self.t.e_dia_da_trilha(date(2026, 8, 9)))    # domingo

    def test_assinante_novo_recebe_a_peca_1(self):
        peca = self.t.proxima_peca("sub-a")
        self.assertEqual(peca["numero"], 1)
        self.assertEqual(peca["produto"], "empreendedorismo")

    def test_peca_nao_avanca_sozinha(self):
        self.assertEqual(self.t.proxima_peca("sub-a")["numero"], 1)
        self.assertEqual(self.t.proxima_peca("sub-a")["numero"], 1)

    def test_avanco_leva_a_proxima(self):
        self.db.trilha_avancar("sub-a", "empreendedorismo", 1)
        self.assertEqual(self.t.proxima_peca("sub-a")["numero"], 2)

    def test_quem_concluiu_e_sem_produto_ativo_nao_tem_proxima(self):
        self.db.trilha_avancar("sub-a", "empreendedorismo", self.cfg.TRILHAS["empreendedorismo"]["total"])
        self.t.definir_produto_ativo("")
        self.assertIsNone(self.t.proxima_peca("sub-a"))

    def test_quem_conclui_cai_na_proxima_trilha_ativa(self):
        self.db.trilha_avancar("sub-a", "empreendedorismo", self.cfg.TRILHAS["empreendedorismo"]["total"])
        self.t.definir_produto_ativo("peptideos")
        produto = self.t.produto_do_assinante("sub-a")
        self.assertEqual(produto, "peptideos")

    def test_abertura_da_peca_1_nao_cobra_nada(self):
        self.assertEqual(self.t.abertura("sub-a", "empreendedorismo", 1), "")

    def test_abertura_reconhece_quem_fez(self):
        self.db.trilha_registrar_envio("sub-a", "empreendedorismo", 1)
        self.db.trilha_marcar_feito("sub-a", "empreendedorismo", 1)
        self.assertIn("semana passada", self.t.abertura("sub-a", "empreendedorismo", 2).lower())

    def test_abertura_retoma_quem_nao_fez(self):
        self.db.trilha_registrar_envio("sub-a", "empreendedorismo", 1)
        texto = self.t.abertura("sub-a", "empreendedorismo", 2)
        self.assertTrue(texto)
        self.assertNotIn("parabéns", texto.lower())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_trilha.TestDrip -v`
Expected: FAIL.

- [ ] **Step 3: Implementar em `trilha.py`**

Substituir `proxima_peca` (`app/trilha.py:84-94`):

```python
def proxima_peca(sub_id):
    """A peça que este assinante deve receber agora (no produto que
    `produto_do_assinante` resolver). None se não há produto pra ele agora, ou se
    ele já concluiu o produto atual (trilha incompleta não vira envio errado)."""
    produto = produto_do_assinante(sub_id)
    if produto is None:
        return None
    info = config.TRILHAS[produto]
    n = db.trilha_posicao(sub_id, produto)
    if n > info["total"]:
        return None
    p = db.trilha_peca(produto, n)
    if not p:
        return None
    p["numero"] = n
    return p
```

Substituir `abertura` (`app/trilha.py:97-106`):

```python
def abertura(sub_id, produto, numero):
    """Linha de retomada no topo da peça, olhando a peça anterior DO MESMO
    produto. Vazia na peça 1 (não há anterior)."""
    if numero <= 1:
        return ""
    if db.trilha_fez(sub_id, produto, numero - 1):
        return "Você marcou a tarefa da semana passada como feita. É assim que essa trilha funciona."
    return "A tarefa da semana passada continua em aberto — ela leva menos tempo do que parece."
```

Substituir `_liberar_claim` (`app/trilha.py:109-116`):

```python
def _liberar_claim(sub_id, produto, numero):
    """Desfaz o claim de `trilha_registrar_envio` quando o envio falhou."""
    with db._conn() as c:
        c.execute("DELETE FROM trilha_envios WHERE subscriber_id=? AND produto=? AND numero=? "
                  "AND feito_em IS NULL", (sub_id or "", produto, int(numero)))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_trilha.TestDrip -v`
Expected: PASS. (`enviar_para`/`enviar_slot` ainda quebrados — Task 6 corrige, eles chamam `abertura`/`_liberar_claim` com a assinatura antiga.)

- [ ] **Step 5: Commit**

```bash
git add app/trilha.py app/tests/test_trilha.py
git commit -m "feat(trilha): proxima_peca e abertura resolvem produto do assinante"
```

---

### Task 6: Envio em lote — `pecas_por_envio`

**Files:**
- Modify: `app/trilha.py` (`enviar_para` vira wrapper de lote sobre `_enviar_uma_peca`; `enviar_slot` perde o gate booleano)
- Test: `app/tests/test_trilha.py` (classe `TestEnvio` reescrita; nova classe `TestLoteDePecas`)

**Interfaces:**
- Consumes: `trilha.proxima_peca`, `trilha.abertura`, `trilha._liberar_claim`, `trilha.produto_do_assinante` (Tasks 4-5); `config.TRILHAS[produto]["pecas_por_envio"]`.
- Produces: `trilha._enviar_uma_peca(sub, produto, enviar_fn=None, render_fn=None) -> bool` (novo), `trilha.enviar_para(sub, enviar_fn=None, render_fn=None) -> bool` (mesma assinatura pública, comportamento em lote por dentro), `trilha.enviar_slot(slot, quando=None, enviar_fn=None, render_fn=None) -> dict` (mesma assinatura; sem a chave `"desligada"`).

- [ ] **Step 1: Write the failing test — substituir `TestEnvio` inteira e adicionar `TestLoteDePecas`**

```python
class TestEnvio(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg, self.db, self.subs = _recarregar(self.tmp)
        import trilha
        importlib.reload(trilha)
        self.t = trilha
        self.t.semear()
        self.t.definir_produto_ativo("empreendedorismo")
        self.enviados = []

    def _fake_enviar(self, whatsapp, pdf_path, caption=""):
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
        self.assertEqual(self.db.trilha_posicao(sub["id"], "empreendedorismo"), 2)

    def test_claim_orfao_e_retomado_assinante_volta_a_receber(self):
        sub = self._sub()
        self.db.trilha_registrar_envio(sub["id"], "empreendedorismo", 1)
        self.assertEqual(self.db.trilha_posicao(sub["id"], "empreendedorismo"), 1)
        ok = self.t.enviar_para(sub, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertTrue(ok, "claim órfão tem que ser retomado, não travar o assinante pra sempre")
        self.assertEqual(len(self.enviados), 1)
        self.assertEqual(self.db.trilha_posicao(sub["id"], "empreendedorismo"), 2)

    def test_falha_no_envio_nao_avanca_a_posicao(self):
        sub = self._sub()

        def explode(*a, **k):
            raise RuntimeError("zap caiu")

        ok = self.t.enviar_para(sub, enviar_fn=explode, render_fn=self._fake_render)
        self.assertFalse(ok)
        self.assertEqual(self.db.trilha_posicao(sub["id"], "empreendedorismo"), 1)

    def test_falha_no_envio_libera_o_claim_pra_proxima_semana(self):
        sub = self._sub()

        def explode(*a, **k):
            raise RuntimeError("zap caiu")

        self.t.enviar_para(sub, enviar_fn=explode, render_fn=self._fake_render)
        ok = self.t.enviar_para(sub, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertTrue(ok, "a mesma peça tem que poder ser reenviada depois de falhar")

    def test_quem_concluiu_e_sem_ativo_nao_recebe_mais(self):
        sub = self._sub()
        self.db.trilha_avancar(sub["id"], "empreendedorismo", self.cfg.TRILHAS["empreendedorismo"]["total"])
        self.t.definir_produto_ativo("")
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
        self.assertEqual(self.db.trilha_posicao(a["id"], "empreendedorismo"), 2)
        self.assertEqual(self.db.trilha_posicao(b["id"], "empreendedorismo"), 1)

    def test_slot_nao_envia_em_dia_util(self):
        from datetime import date
        self._sub()
        res = self.t.enviar_slot("08h", quando=date(2026, 8, 7),
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

    def test_falha_no_avanco_apos_envio_nao_trava_o_assinante(self):
        sub = self._sub()
        avancar_original = self.db.trilha_avancar
        chamadas = {"n": 0}

        def avancar_com_falha(sub_id, produto, numero):
            chamadas["n"] += 1
            if chamadas["n"] == 1:
                raise RuntimeError("disco cheio")
            return avancar_original(sub_id, produto, numero)

        self.db.trilha_avancar = avancar_com_falha
        try:
            ok1 = self.t.enviar_para(sub, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
            self.assertFalse(ok1, "avanço falhou -- não pode reportar sucesso")
            self.assertEqual(self.db.trilha_posicao(sub["id"], "empreendedorismo"), 1)

            ok2 = self.t.enviar_para(sub, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
            self.assertTrue(ok2, "claim liberado -- a mesma peça tem que poder sair de novo")
            self.assertEqual(self.db.trilha_posicao(sub["id"], "empreendedorismo"), 2)
        finally:
            self.db.trilha_avancar = avancar_original

        self.assertEqual(len(self.enviados), 2, "peça 1 saiu duas vezes -- duplicata, não sumiço")

    def test_falha_inesperada_num_assinante_nao_impede_os_demais_do_slot(self):
        from datetime import date
        from unittest.mock import patch
        a = self._sub("A", "5543999990005", "08h")
        b = self._sub("B", "5543999990006", "08h")

        produto_original = self.t.produto_do_assinante

        def produto_com_explosao(sub_id):
            if sub_id == a["id"]:
                raise RuntimeError("banco caiu bem na hora do Fulano A")
            return produto_original(sub_id)

        self.t.produto_do_assinante = produto_com_explosao
        try:
            with patch("time.sleep"):
                res = self.t.enviar_slot("08h", quando=date(2026, 8, 8),
                                         enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        finally:
            self.t.produto_do_assinante = produto_original

        self.assertEqual(res["enviados"], 1, "B tinha que receber mesmo com A explodindo")
        self.assertEqual(res["falhas"], 1)
        self.assertEqual(self.db.trilha_posicao(b["id"], "empreendedorismo"), 2)

    def test_slot_respeita_o_delay_entre_assinantes(self):
        from datetime import date
        from unittest.mock import patch
        a = self._sub("A", "5543999990010", "08h")
        b = self._sub("B", "5543999990011", "08h")
        c = self._sub("C", "5543999990012", "08h")
        with patch("time.sleep") as mock_sleep:
            res = self.t.enviar_slot("08h", quando=date(2026, 8, 8),
                                     enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertEqual(res["enviados"], 3)
        self.assertEqual(mock_sleep.call_count, 2, "3 envios -> 2 pausas entre eles, nunca no fim")
        for chamada in mock_sleep.call_args_list:
            self.assertEqual(chamada.args[0], self.cfg.SEND_DELAY_SEC)

    def test_troca_de_slot_no_mesmo_sabado_nao_duplica(self):
        from datetime import date
        sub = self._sub(slot="08h")
        sab = date(2026, 8, 8)

        res1 = self.t.enviar_slot("08h", quando=sab, enviar_fn=self._fake_enviar,
                                  render_fn=self._fake_render)
        self.assertEqual(res1["enviados"], 1)
        self.assertEqual(self.db.trilha_posicao(sub["id"], "empreendedorismo"), 2)

        self.subs.definir_slot(sub["id"], "18h")

        res2 = self.t.enviar_slot("18h", quando=sab, enviar_fn=self._fake_enviar,
                                  render_fn=self._fake_render)
        self.assertEqual(res2["enviados"], 0, "já recebeu a peça da semana -- não pode duplicar")
        self.assertEqual(len(self.enviados), 1, "só UMA peça no sábado, apesar da troca de slot")
        self.assertEqual(self.db.trilha_posicao(sub["id"], "empreendedorismo"), 2)

    def test_link_da_ferramenta_aponta_pro_portal_do_assinante(self):
        capturado = {}

        def espiao(whatsapp, pdf_path, caption=""):
            with open(pdf_path, encoding="utf-8") as f:
                capturado["html"] = f.read()

        def render_html(html, out_path):
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html)
            return out_path

        sub = self._sub()
        self.assertTrue(self.t.enviar_para(sub, enviar_fn=espiao, render_fn=render_html))
        html = capturado["html"]
        self.assertIn(f"{self.cfg.ARTIGOS_URL}/ferramentas/", html)
        self.assertNotIn(f"{self.cfg.PUBLIC_URL}/ferramentas/", html)


class TestLoteDePecas(unittest.TestCase):
    """Peptídeos manda 2 peças por sábado (vs. 1 da trilha de empreendedorismo) --
    `config.TRILHAS["peptideos"]["pecas_por_envio"]`."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        d = os.path.join(self.tmp, "peptideos")
        os.makedirs(d)
        for n, titulo in ((1, "Um"), (2, "Dois"), (3, "Três")):
            with open(os.path.join(d, f"{n:02d}-p.md"), "w", encoding="utf-8") as f:
                f.write(f"titulo: {titulo}\neixo: A\n\n## corpo\ncorpo {n}\n")
        os.environ["DSCURSO_PEPTIDEOS_DIR"] = d
        self.cfg, self.db, self.subs = _recarregar(self.tmp)
        import trilha
        importlib.reload(trilha)
        self.t = trilha
        self.t.semear()
        self.t.definir_produto_ativo("peptideos")
        self.enviados = []

    def tearDown(self):
        os.environ.pop("DSCURSO_PEPTIDEOS_DIR", None)

    def _fake_enviar(self, whatsapp, pdf_path, caption=""):
        self.enviados.append(caption)

    def _fake_render(self, html, out_path):
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("pdf")
        return out_path

    def _sub(self):
        reg = self.subs.adicionar("Fulano", "5543999990000")
        self.subs.definir_slot(reg["id"], "08h")
        return self.subs.por_id(reg["id"])

    def test_manda_2_pecas_numa_visita_so(self):
        sub = self._sub()
        ok = self.t.enviar_para(sub, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertTrue(ok)
        self.assertEqual(len(self.enviados), 2)
        self.assertIn("Semana 1", self.enviados[0])
        self.assertIn("Semana 2", self.enviados[1])
        self.assertEqual(self.db.trilha_posicao(sub["id"], "peptideos"), 3)

    def test_pausa_entre_as_2_pecas_da_mesma_pessoa(self):
        from unittest.mock import patch
        sub = self._sub()
        with patch("time.sleep") as mock_sleep:
            self.t.enviar_para(sub, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        mock_sleep.assert_called_once_with(self.cfg.SEND_DELAY_SEC)

    def test_trilha_acaba_no_meio_do_lote_manda_a_ultima_e_para(self):
        sub = self._sub()
        self.db.trilha_avancar(sub["id"], "peptideos", 2)   # só falta a peça 3
        ok = self.t.enviar_para(sub, enviar_fn=self._fake_enviar, render_fn=self._fake_render)
        self.assertTrue(ok)
        self.assertEqual(len(self.enviados), 1)
        self.assertIn("Semana 3", self.enviados[0])
        self.assertEqual(self.db.trilha_posicao(sub["id"], "peptideos"), 4)

    def test_2a_peca_falha_nao_desfaz_a_1a(self):
        sub = self._sub()
        chamadas = {"n": 0}

        def enviar_falha_na_2a(whatsapp, pdf_path, caption=""):
            chamadas["n"] += 1
            if chamadas["n"] == 2:
                raise RuntimeError("zap caiu na 2ª")
            self.enviados.append(caption)

        ok = self.t.enviar_para(sub, enviar_fn=enviar_falha_na_2a, render_fn=self._fake_render)
        self.assertTrue(ok, "a 1ª peça saiu de verdade -- não é falha total")
        self.assertEqual(len(self.enviados), 1)
        self.assertEqual(self.db.trilha_posicao(sub["id"], "peptideos"), 2,
                         "avançou só da 1ª -- a 2ª fica pro próximo sábado")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_trilha.TestEnvio tests.test_trilha.TestLoteDePecas -v`
Expected: FAIL.

- [ ] **Step 3: Implementar em `trilha.py`**

Substituir `enviar_para` (`app/trilha.py:118-199`) por duas funções:

```python
def _enviar_uma_peca(sub, produto, enviar_fn=None, render_fn=None):
    """Um ciclo claim->render->envia->avança, pra UMA peça de UM produto.
    Extraído pra `enviar_para` poder rodar isto `pecas_por_envio` vezes seguidas
    na mesma visita, sem duplicar a lógica de claim/retomada/falha."""
    import os
    import tempfile
    import deliver
    import phone

    sub_id = sub.get("id")
    info = config.TRILHAS[produto]
    n = db.trilha_posicao(sub_id, produto)
    if n > info["total"]:
        return False
    peca = db.trilha_peca(produto, n)
    if not peca:
        return False
    peca["numero"] = n
    if not db.trilha_registrar_envio(sub_id, produto, n):
        # INVARIANTE que sustenta este "retomar" em vez de `return False`: `n`
        # acabou de sair de `db.trilha_posicao(sub_id, produto)`, ou seja, É a
        # posição ATUAL do assinante NESSE produto. Um claim que colide com a
        # posição atual só pode ser órfão (execução anterior morreu entre o
        # INSERT do claim e o envio/avanço). Sem retomar aqui, o assinante trava
        # NESSA peça pra sempre, em silêncio.
        print(f"[trilha] retomando claim órfão da peça {n} ({produto}) p/ {sub_id} "
              f"(execução anterior não completou)", flush=True)

    enviar_fn = enviar_fn or deliver.enviar_pdf
    if render_fn is None:
        import pdf as _pdf
        render_fn = _pdf.gerar_pdf

    try:
        import pdf_trilha
        link = ""
        if peca.get("ferramenta_slug") and caminho_ferramenta(peca["ferramenta_slug"]):
            link = f"{config.ARTIGOS_URL}/ferramentas/{peca['ferramenta_slug']}"
        html_peca = pdf_trilha.montar_html(peca, sub.get("nome", ""),
                                           abertura=abertura(sub_id, produto, n), link_ferramenta=link)
        out = os.path.join(tempfile.gettempdir(), f"trilha-{produto}-{n}-{sub_id}.pdf")
        render_fn(html_peca, out)
        enviar_fn(phone.normalizar(sub.get("whatsapp", "")), out,
                  caption=f"{info['nome']} · Semana {n}: {peca.get('titulo','')}")
    except Exception as e:
        print(f"[trilha] peça {n} ({produto}) p/ {sub_id} falhou: {e}", flush=True)
        _liberar_claim(sub_id, produto, n)
        return False

    try:
        db.trilha_avancar(sub_id, produto, n)
    except Exception as e:
        print(f"[trilha] AVANÇO da peça {n} ({produto}) p/ {sub_id} falhou (mensagem JÁ enviada!): {e}",
              flush=True)
        _liberar_claim(sub_id, produto, n)
        return False

    return True


def enviar_para(sub, enviar_fn=None, render_fn=None):
    """Envia a(s) peça(s) da vez a UM assinante -- `pecas_por_envio` do produto em
    que ele está agora (1 pra empreendedorismo, 2 pra peptídeos). Se a trilha
    acabar no meio do lote, manda a que resta e para -- nunca emenda no próximo
    produto no mesmo sábado (isso só é decidido de novo no sábado seguinte, por
    `produto_do_assinante`). True se enviou AO MENOS uma peça."""
    import time

    sub_id = sub.get("id")
    produto = produto_do_assinante(sub_id)
    if produto is None:
        return False
    n_lote = config.TRILHAS[produto].get("pecas_por_envio", 1)
    enviou_alguma = False
    for i in range(n_lote):
        if i > 0:
            # mesmo número de WhatsApp que sustenta o produto pago inteiro -- não
            # dispara 2 mensagens grudadas pra mesma pessoa.
            time.sleep(config.SEND_DELAY_SEC)
        ok = _enviar_uma_peca(sub, produto, enviar_fn=enviar_fn, render_fn=render_fn)
        if not ok:
            return enviou_alguma
        enviou_alguma = True
        if db.trilha_posicao(sub_id, produto) > config.TRILHAS[produto]["total"]:
            break
    return enviou_alguma
```

Em `enviar_slot` (`app/trilha.py:216-278`), remover o gate booleano do início (o `if not ativa(): ... desligada: True`) — agora quem decide "recebe ou não" é `produto_do_assinante`, individualmente, dentro de `enviar_para`. Novo corpo:

```python
def enviar_slot(slot, quando=None, enviar_fn=None, render_fn=None):
    """Envia a peça (ou peças, se `pecas_por_envio>1`) da semana aos assinantes
    ativos de `slot`. Só roda no dia da trilha. Quem não tem produto pra receber
    agora (`produto_do_assinante` devolve None) simplesmente não conta nem como
    enviado nem como falha -- não existe mais um "desligada" global: cada
    assinante é resolvido individualmente, então quem está no meio de uma trilha
    continua recebendo mesmo sem nenhum produto NOVO ativo.

    Dois claims empilhados, cada um matando um bug diferente:
    - por (data, slot): o TICK inteiro não roda duas vezes (restart do cron).
    - por (data, assinante): o ASSINANTE não leva DUAS peças no mesmo sábado por
      troca de horário no meio do dia -- reaproveitado com chave namespaced
      (`trilha:{data}`) pra não brigar com o claim do estudo diário."""
    from datetime import datetime
    import time
    import subscribers

    d = quando or datetime.now()
    if not e_dia_da_trilha(d):
        return {"enviados": 0, "falhas": 0}
    data = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)
    if not db.registrar_envio_slot(f"trilha:{data}", slot):   # slot já rodou hoje
        return {"enviados": 0, "falhas": 0}

    enviados = falhas = 0
    primeiro = True
    for s in subscribers.ativos():
        if subscribers.slot_de(s) != slot:
            continue
        if not db.registrar_envio_assinante(f"trilha:{data}", s.get("id")):
            continue   # já recebeu a(s) peça(s) da semana hoje
        if not primeiro:
            time.sleep(config.SEND_DELAY_SEC)
        primeiro = False
        try:
            ok = enviar_para(s, enviar_fn=enviar_fn, render_fn=render_fn)
        except Exception as e:
            print(f"[trilha] envio a {s.get('id')} explodiu fora do enviar_para: {e}", flush=True)
            ok = False
        if ok:
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

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_trilha.TestEnvio tests.test_trilha.TestLoteDePecas -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/trilha.py app/tests/test_trilha.py
git commit -m "feat(trilha): envio em lote (pecas_por_envio) e fim do gate booleano global"
```

---

### Task 7: Bloco de alerta ANVISA no PDF

**Files:**
- Modify: `app/pdf_trilha.py` (`_CSS`, `montar_html`)
- Test: `app/tests/test_trilha.py` (classe `TestPdfTrilha` reescrita)

**Interfaces:**
- Consumes: `peca["produto"]`, `peca["aviso"]` (do banco, Task 2/3).
- Produces: `pdf_trilha.montar_html(peca, nome_assinante, abertura="", link_ferramenta="")` (assinatura pública inalterada).

- [ ] **Step 1: Write the failing test — substituir a classe `TestPdfTrilha` inteira**

```python
class TestPdfTrilha(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg, self.db, self.subs = _recarregar(self.tmp)
        import pdf_trilha
        importlib.reload(pdf_trilha)
        self.p = pdf_trilha
        self.peca = {"produto": "empreendedorismo", "numero": 3, "titulo": "Escolha uma linha",
                     "eixo": "Saber onde você está", "corpo": "Primeiro.\n\nSegundo.",
                     "micro_resultado": "Faça a conta.", "mentalidade": "Pense grande.",
                     "ferramenta_slug": "mapa-de-linha", "aviso": ""}

    def test_html_traz_titulo_e_progresso(self):
        h = self.p.montar_html(self.peca, "Diego")
        self.assertIn("Escolha uma linha", h)
        total = self.cfg.TRILHAS["empreendedorismo"]["total"]
        self.assertIn(f"3 de {total}", h)

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

    def test_sem_aviso_nao_mostra_bloco_de_alerta(self):
        h = self.p.montar_html(self.peca, "Diego")
        self.assertNotIn("Sem registro na Anvisa", h)
        self.assertNotIn("bloco alerta", h)

    def test_com_aviso_mostra_bloco_de_alerta_depois_do_corpo(self):
        peca = dict(self.peca, produto="peptideos",
                   aviso="A Anvisa nomeou esta substância como ilegal para qualquer uso.")
        h = self.p.montar_html(peca, "Diego")
        self.assertIn("Sem registro na Anvisa", h)
        self.assertIn("ilegal para qualquer uso", h)
        # ordem: depois do corpo, antes do bloco de tarefa da semana
        pos_corpo = h.index('<div class="corpo">')
        pos_alerta = h.index('bloco alerta')
        pos_tarefa = h.index("Sua tarefa desta semana")
        self.assertTrue(pos_corpo < pos_alerta < pos_tarefa)

    def test_aviso_escapa_html(self):
        peca = dict(self.peca, aviso="<script>alert(1)</script>")
        h = self.p.montar_html(peca, "Diego")
        self.assertNotIn("<script>alert", h)

    def test_nome_e_total_vem_do_catalogo_do_produto(self):
        peca = dict(self.peca, produto="peptideos", numero=1)
        h = self.p.montar_html(peca, "Diego")
        total_pep = self.cfg.TRILHAS["peptideos"]["total"]
        self.assertIn(f"1 de {total_pep}", h)
        self.assertIn(self.cfg.TRILHAS["peptideos"]["nome"], h)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_trilha.TestPdfTrilha -v`
Expected: FAIL — `config.TRILHA_TOTAL` não existe mais (o teste antigo usava), bloco de alerta não existe.

- [ ] **Step 3: Implementar em `pdf_trilha.py`**

Adicionar ao final de `_CSS` (perto de `app/pdf_trilha.py:66`, antes do fechamento das aspas triplas):

```css
  .bloco.alerta { border-left-color: #b3402a; background: #fdf3f0; }
  .bloco.alerta .rot { color: #a13a26; }
```

Substituir `montar_html` (`app/pdf_trilha.py:140-179`):

```python
def montar_html(peca, nome_assinante, abertura="", link_ferramenta=""):
    """HTML completo de uma peça. `link_ferramenta` vazio some com o bloco inteiro
    -- peça de mentalidade pura não tem anexo e não pode exibir botão órfão.
    `peca["aviso"]` vazio some com o bloco de alerta inteiro, mesma regra.

    Nome/total do produto vêm de `config.TRILHAS[peca["produto"]]`, não de
    constante fixa -- é o que permite a mesma função servir qualquer trilha do
    catálogo sem saber seus nomes de antemão."""
    numero = peca.get("numero", 0)
    info = config.TRILHAS.get(peca.get("produto", ""), {})
    nome_produto = info.get("nome", config.PRODUTO)
    total_produto = info.get("total", numero)
    abertura_html = (f'<p class="abertura">{_esc(abertura)}</p>' if abertura else "")
    ferramenta_html = ""
    if link_ferramenta:
        ferramenta_html = (f'<p class="ferramenta">📎 <a href="{_esc(link_ferramenta)}">'
                           f'Baixar a ferramenta desta semana</a></p>')
    aviso_html = ""
    if peca.get("aviso"):
        aviso_html = (f'<div class="bloco alerta"><p class="rot">⚠ Sem registro na Anvisa</p>'
                      f'{_paragrafos(peca.get("aviso"))}</div>')
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<style>{_CSS}</style></head><body>
  <div class="capa">
    <div class="capa-topo">
      <div class="capa-assinatura">
        <img class="capa-icone" src="data:image/png;base64,{_ICONE_DS_B64}" alt="">
        <span class="capa-nome">Dr. Diego Silva</span>
      </div>
      <span class="capa-selo">Semana {_esc(numero)} de {_esc(total_produto)}</span>
    </div>
    <div class="capa-produto">{_esc(nome_produto)}</div>
  </div>
  <div class="pagina">
  <h1>{_esc(peca.get('titulo'))}</h1>
  <p class="eixo">{_esc(peca.get('eixo'))}</p>
  {abertura_html}
  <div class="corpo">{_paragrafos(peca.get('corpo'))}</div>
  {aviso_html}
  <div class="bloco"><p class="rot">Sua tarefa desta semana</p>
    {_paragrafos(peca.get('micro_resultado')) or '<p></p>'}</div>
  <div class="bloco"><p class="rot">Mentalidade</p>
    {_paragrafos(peca.get('mentalidade')) or '<p></p>'}</div>
  {ferramenta_html}
  <p class="rodape">Para {_esc(nome_assinante)} · {_esc(nome_produto)}</p>
  </div>
</body></html>"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_trilha.TestPdfTrilha -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/pdf_trilha.py app/tests/test_trilha.py
git commit -m "feat(trilha): bloco de alerta ANVISA no PDF, cor propria, depois do corpo"
```

---

### Task 8: Ferramenta multi-produto

**Files:**
- Modify: `app/trilha.py` (`caminho_ferramenta`)
- Test: `app/tests/test_trilha.py` (classe `TestLinkFerramentaNoEnvio`); `app/tests/test_trilha_web.py` (classe `TestFerramentaSegura`)

**Interfaces:**
- Consumes: `config.TRILHAS` (Task 1).
- Produces: `trilha.caminho_ferramenta(slug)` (assinatura pública inalterada — busca em todos os diretórios do catálogo, não só num fixo).

- [ ] **Step 1: Write the failing test**

Em `app/tests/test_trilha.py`, atualizar a classe `TestLinkFerramentaNoEnvio` (só o `setUp` e as chamadas de `trilha_upsert_peca`/`enviar_para` mudam — o resto já está coberto pelo Task 6):

```python
class TestLinkFerramentaNoEnvio(unittest.TestCase):
    """Important 4 da revisão original: o PDF só pode oferecer o link de download
    da ferramenta quando o arquivo existe de verdade em seed/<produto>/ferramentas/
    -- caso contrário o assinante loga e recebe 404."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_TRILHA_DIR"] = os.path.join(self.tmp, "trilha")
        os.makedirs(os.path.join(self.tmp, "trilha", "ferramentas"))
        self.cfg, self.db, self.subs = _recarregar(self.tmp)
        import trilha
        importlib.reload(trilha)
        self.t = trilha
        self.t.definir_produto_ativo("empreendedorismo")
        self.db.trilha_upsert_peca("empreendedorismo", 1, "eixo", "Peça 1", "corpo", "micro",
                                   "mentalidade", "", "planilha-custo-hora")
        self.enviados = []

    def tearDown(self):
        os.environ.pop("DSCURSO_TRILHA_DIR", None)

    def _fake_enviar(self, whatsapp, pdf_path, caption=""):
        self.enviados.append({"whatsapp": whatsapp, "caption": caption})

    def _render_capturando(self, htmls):
        def render(html, out_path):
            htmls.append(html)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("pdf")
            return out_path
        return render

    def _sub(self, nome="Fulano", numero="5543999990000", slot="08h"):
        reg = self.subs.adicionar(nome, numero)
        self.subs.definir_slot(reg["id"], slot)
        return self.subs.por_id(reg["id"])

    def test_link_some_quando_arquivo_da_ferramenta_nao_existe(self):
        sub = self._sub()
        htmls = []
        ok = self.t.enviar_para(sub, enviar_fn=self._fake_enviar,
                                render_fn=self._render_capturando(htmls))
        self.assertTrue(ok)
        self.assertNotIn("Baixar", htmls[0])
        self.assertNotIn("planilha-custo-hora", htmls[0])

    def test_link_aparece_quando_arquivo_da_ferramenta_existe(self):
        caminho = os.path.join(self.cfg.TRILHAS["empreendedorismo"]["dir"], "ferramentas",
                               "planilha-custo-hora.csv")
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("a,b\n")
        sub = self._sub()
        htmls = []
        ok = self.t.enviar_para(sub, enviar_fn=self._fake_enviar,
                                render_fn=self._render_capturando(htmls))
        self.assertTrue(ok)
        self.assertIn("/ferramentas/planilha-custo-hora", htmls[0])
        self.assertIn("Baixar", htmls[0])
```

Em `app/tests/test_trilha_web.py`, adicionar ao final de `TestFerramentaSegura`:

```python
    def test_acha_ferramenta_de_qualquer_produto_do_catalogo(self):
        # a rota /ferramentas/<slug> não sabe de qual produto é o slug -- a busca
        # tem que varrer TODOS os diretórios do catálogo, não só um fixo.
        d_pep = os.path.join(self.tmp2, "peptideos", "ferramentas")
        os.makedirs(d_pep)
        with open(os.path.join(d_pep, "checklist-pep.csv"), "w") as f:
            f.write("a,b\n")
        os.environ["DSCURSO_PEPTIDEOS_DIR"] = os.path.join(self.tmp2, "peptideos")
        import config
        importlib.reload(config)
        importlib.reload(self.t)
        try:
            self.assertTrue(self.t.caminho_ferramenta("checklist-pep"))
        finally:
            os.environ.pop("DSCURSO_PEPTIDEOS_DIR", None)
```

E, no `setUp` de `TestFerramentaSegura`, adicionar `self.tmp2 = tempfile.mkdtemp()` (diretório extra, separado do `self.tmp` usado pra `DSCURSO_TRILHA_DIR`, pra não misturar os dois catálogos no mesmo teste):

```python
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tmp2 = tempfile.mkdtemp()
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_trilha.TestLinkFerramentaNoEnvio tests.test_trilha_web.TestFerramentaSegura -v`
Expected: FAIL — `caminho_ferramenta` ainda só olha `config.TRILHA_DIR` (que não existe mais).

- [ ] **Step 3: Implementar em `trilha.py`**

Substituir `caminho_ferramenta` (`app/trilha.py:284-301`):

```python
def caminho_ferramenta(slug):
    """Caminho absoluto do arquivo da ferramenta, ou None. Busca em TODOS os
    diretórios do catálogo (a rota /ferramentas/<slug> não sabe de qual produto é
    o slug) -- primeiro achado vence, mesma tolerância de sempre.

    O slug vem da URL, então é entrada não confiável: só minúscula/dígito/hífen
    passa, o que já elimina `..`, `/` e `\\`. A checagem de prefixo depois é cinto
    e suspensório -- se o regex mudar um dia, o arquivo servido continua preso ao
    diretório de ferramentas daquele produto."""
    if not slug or not _SLUG_OK.match(slug):
        return None
    for info in config.TRILHAS.values():
        base = os.path.realpath(os.path.join(info["dir"], "ferramentas"))
        if not os.path.isdir(base):
            continue
        for nome in sorted(os.listdir(base)):
            raiz, _ext = os.path.splitext(nome)
            if raiz != slug:
                continue
            caminho = os.path.realpath(os.path.join(base, nome))
            if caminho.startswith(base + os.sep) and os.path.isfile(caminho):
                return caminho
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_trilha.TestLinkFerramentaNoEnvio tests.test_trilha_web.TestFerramentaSegura -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/trilha.py app/tests/test_trilha.py app/tests/test_trilha_web.py
git commit -m "feat(trilha): caminho_ferramenta busca em todos os diretorios do catalogo"
```

---

### Task 9: Admin — seletor de trilha ativa

**Files:**
- Modify: `app/site_web.py` (`pagina_admin_trilha`)
- Modify: `app/serve.py` (`_trilha_numero_valido`; rotas `GET`/`POST /admin/trilha`, `GET /admin/trilha/peca/<n>`)
- Test: `app/tests/test_trilha_web.py` (classes `TestTrilhaNumeroValido`, `TestAdminTrilha`, `TestPreviaPecas`, `TestRotaPreviaPeca`)

**Interfaces:**
- Consumes: `trilha.produto_ativo`/`definir_produto_ativo` (Task 4), `db.trilha_painel`/`trilha_listar_pecas`/`trilha_peca` (Task 2).
- Produces: `site_web.pagina_admin_trilha(linhas, token="", pecas=None, produto="", produto_ativo="", msg="")`; `serve._trilha_numero_valido(numero_str, produto)`.

- [ ] **Step 1: Write the failing test**

Em `app/tests/test_trilha_web.py`, substituir `TestTrilhaNumeroValido`:

```python
class TestTrilhaNumeroValido(unittest.TestCase):
    def setUp(self):
        import serve
        self.f = serve._trilha_numero_valido

    def test_numero_valido_passa(self):
        self.assertEqual(self.f("1", "empreendedorismo"), 1)
        self.assertEqual(self.f("12", "empreendedorismo"), 12)

    def test_numero_fora_da_faixa_vira_zero(self):
        self.assertEqual(self.f("0", "empreendedorismo"), 0)
        self.assertEqual(self.f("13", "empreendedorismo"), 0)
        self.assertEqual(self.f("-1", "empreendedorismo"), 0)

    def test_numero_valido_no_produto_errado_vira_zero(self):
        # 12 é válido pra empreendedorismo (total 12), mas não pra peptideos (11)
        self.assertEqual(self.f("12", "peptideos"), 0)
        self.assertEqual(self.f("11", "peptideos"), 11)

    def test_produto_desconhecido_vira_zero(self):
        self.assertEqual(self.f("1", "nao-existe"), 0)

    def test_numero_nao_numerico_vira_zero(self):
        self.assertEqual(self.f("abc", "empreendedorismo"), 0)
        self.assertEqual(self.f("", "empreendedorismo"), 0)
        self.assertEqual(self.f(None, "empreendedorismo"), 0)

    def test_numero_gigante_nao_estoura_e_vira_zero(self):
        self.assertEqual(self.f("9" * 90, "empreendedorismo"), 0)
```

Substituir `TestAdminTrilha`:

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
        self.cfg, self.w = config, site_web

    def test_lista_assinantes_com_posicao(self):
        linhas = [{"nome": "Diego", "proxima_peca": 4, "enviadas": 3, "feitas": 2,
                   "concluiu": False}]
        h = self.w.pagina_admin_trilha(linhas, produto="empreendedorismo")
        self.assertIn("Diego", h)
        self.assertIn("4", h)

    def test_marca_quem_concluiu(self):
        linhas = [{"nome": "Ana", "proxima_peca": 13, "enviadas": 12, "feitas": 12,
                   "concluiu": True}]
        h = self.w.pagina_admin_trilha(linhas, produto="empreendedorismo")
        self.assertIn("Concluiu", h)

    def test_sem_ninguem_na_trilha_nao_quebra(self):
        h = self.w.pagina_admin_trilha([], produto="empreendedorismo")
        self.assertIn("Ninguém", h)

    def test_escapa_nome(self):
        linhas = [{"nome": "<script>x</script>", "proxima_peca": 1, "enviadas": 0,
                   "feitas": 0, "concluiu": False}]
        self.assertNotIn("<script>x", self.w.pagina_admin_trilha(linhas, produto="empreendedorismo"))

    def test_mostra_qual_produto_esta_ativo(self):
        h = self.w.pagina_admin_trilha([], produto="empreendedorismo", produto_ativo="peptideos")
        self.assertIn("checked", h)   # o rádio de "peptideos" vem marcado

    def test_lista_os_produtos_do_catalogo_como_opcoes(self):
        h = self.w.pagina_admin_trilha([], produto="empreendedorismo", produto_ativo="")
        for info in self.cfg.TRILHAS.values():
            self.assertIn(info["nome"], h)

    def test_produto_default_e_o_primeiro_do_catalogo_se_invalido(self):
        h = self.w.pagina_admin_trilha([], produto="nao-existe")
        primeiro_nome = next(iter(self.cfg.TRILHAS.values()))["nome"]
        self.assertIn(primeiro_nome, h)
```

Substituir `TestPreviaPecas`:

```python
class TestPreviaPecas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        for m in ("config", "db", "trilha", "pdf_trilha", "site_web"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, trilha, pdf_trilha, site_web
        for m in (config, db, trilha, pdf_trilha, site_web):
            importlib.reload(m)
        db.init()
        self.cfg, self.db, self.t, self.w = config, db, trilha, site_web
        self.t.semear()

    def test_listar_pecas_vem_ordenado(self):
        nums = [p["numero"] for p in self.db.trilha_listar_pecas("empreendedorismo")]
        self.assertEqual(nums, sorted(nums))
        self.assertEqual(len(nums), self.cfg.TRILHAS["empreendedorismo"]["total"])

    def test_admin_lista_as_pecas_com_link_de_previa(self):
        h = self.w.pagina_admin_trilha([], pecas=self.db.trilha_listar_pecas("empreendedorismo"),
                                       produto="empreendedorismo")
        self.assertIn("/admin/trilha/peca/1", h)
        total = self.cfg.TRILHAS["empreendedorismo"]["total"]
        self.assertIn(f"/admin/trilha/peca/{total}", h)

    def test_admin_sem_pecas_nao_quebra(self):
        h = self.w.pagina_admin_trilha([], pecas=[], produto="empreendedorismo")
        self.assertIn("Nenhuma peça", h)
```

Em `TestRotaPreviaPeca`, ajustar as URLs pra incluírem `&produto=empreendedorismo` (o token já vem com `?`, então o produto entra com `&`) e trocar `self.cfg.TRILHA_TOTAL` por `self.cfg.TRILHAS["empreendedorismo"]["total"]`:

```python
    def test_sem_token_barra_antes_de_ler_o_banco(self):
        r = self._get("/admin/trilha/peca/1")
        self.assertEqual(r["code"], 403)

    def test_token_errado_barra_mesmo_com_numero_invalido(self):
        r = self._get("/admin/trilha/peca/abc?token=errado&produto=empreendedorismo")
        self.assertEqual(r["code"], 403)

    def test_numero_nao_inteiro_com_token_bom_devolve_404_sem_traceback(self):
        r = self._get("/admin/trilha/peca/abc?token=tok123&produto=empreendedorismo")
        self.assertEqual(r["code"], 404)

    def test_numero_inexistente_devolve_404(self):
        total = self.cfg.TRILHAS["empreendedorismo"]["total"]
        r = self._get(f"/admin/trilha/peca/{total + 1}?token=tok123&produto=empreendedorismo")
        self.assertEqual(r["code"], 404)

    def test_numero_gigante_devolve_404_sem_estourar(self):
        r = self._get(f"/admin/trilha/peca/{'9' * 90}?token=tok123&produto=empreendedorismo")
        self.assertEqual(r["code"], 404)

    def test_numero_zero_devolve_404(self):
        r = self._get("/admin/trilha/peca/0?token=tok123&produto=empreendedorismo")
        self.assertEqual(r["code"], 404)

    def test_numero_negativo_devolve_404(self):
        r = self._get("/admin/trilha/peca/-1?token=tok123&produto=empreendedorismo")
        self.assertEqual(r["code"], 404)

    def test_produto_ausente_devolve_404(self):
        r = self._get("/admin/trilha/peca/1?token=tok123")
        self.assertEqual(r["code"], 404)

    def test_produto_desconhecido_devolve_404(self):
        r = self._get("/admin/trilha/peca/1?token=tok123&produto=nao-existe")
        self.assertEqual(r["code"], 404)

    def test_token_certo_devolve_a_mesma_renderizacao_do_pdf(self):
        titulo = self.db.trilha_peca("empreendedorismo", 1)["titulo"]
        r = self._get("/admin/trilha/peca/1?token=tok123&produto=empreendedorismo")
        self.assertEqual(r["code"], 200)
        self.assertIn(titulo, r["body"])

    def test_previa_nao_mostra_link_de_ferramenta_que_nao_existe(self):
        self.assertTrue(self.db.trilha_peca("empreendedorismo", 1)["ferramenta_slug"])
        r = self._get("/admin/trilha/peca/1?token=tok123&produto=empreendedorismo")
        self.assertEqual(r["code"], 200)
        self.assertNotIn("Baixar", r["body"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_trilha_web.TestTrilhaNumeroValido tests.test_trilha_web.TestAdminTrilha tests.test_trilha_web.TestPreviaPecas tests.test_trilha_web.TestRotaPreviaPeca -v`
Expected: FAIL.

- [ ] **Step 3: Implementar `_trilha_numero_valido` em `serve.py`**

Substituir (`app/serve.py:71-90`):

```python
def _trilha_numero_valido(numero_str, produto):
    """Converte um `numero` (form do POST /trilha OU segmento de URL da rota GET
    /admin/trilha/peca/<n>) num inteiro de peça válido pro `produto` dado
    (1..total DESSE produto), ou devolve 0. Único ponto de verdade pras duas
    rotas -- nenhuma delas valida `numero` por conta própria.

    A faixa é checada AQUI, antes de qualquer valor chegar em `db.trilha_marcar_feito`
    ou `db.trilha_peca`: `int()` do Python não estoura com string gigante, mas o
    `sqlite3` estoura ao converter esse int pra INTEGER de 64 bits sem try/except
    no caminho do banco."""
    import config
    if produto not in config.TRILHAS:
        return 0
    try:
        numero = int(numero_str or 0)
    except ValueError:
        return 0
    total = config.TRILHAS[produto]["total"]
    return numero if 1 <= numero <= total else 0
```

- [ ] **Step 4: Implementar `pagina_admin_trilha` em `site_web.py`**

Substituir a função inteira (`app/site_web.py:878-958`):

```python
def pagina_admin_trilha(linhas, token="", pecas=None, produto="", produto_ativo="", msg=""):
    """Painel do admin: quem está em qual semana da trilha, quanto recebeu e
    quanto executou, MAIS o seletor de qual trilha está ativa (só uma por vez).

    `produto` é qual trilha está sendo VISUALIZADA (peças/painel abaixo);
    `produto_ativo` é qual trilha está aceitando gente NOVA agora -- podem ser
    diferentes (ex.: visualizando a prévia de peptídeos enquanto empreendedorismo
    ainda está ativa pra quem já começou nela).

    `pecas` alimenta a prévia sob demanda: um link por peça pra
    `/admin/trilha/peca/<n>&produto=...`, que renderiza com a MESMA função que
    gera o PDF enviado no WhatsApp -- assim a prévia não pode divergir do envio
    real."""
    import config
    catalogo = config.TRILHAS
    if produto not in catalogo:
        produto = next(iter(catalogo), "")
    info = catalogo.get(produto, {"nome": "", "total": 0})
    tk = f"token={_esc(token)}" if token else ""

    abas = "".join(
        f'<a class="{"actbtn" if p == produto else "actbtn ghost"}" '
        f'href="/admin/trilha?produto={p}{("&" + tk) if tk else ""}" '
        f'style="text-decoration:none;padding:8px 15px;font-size:13px">{_esc(dados["nome"])}</a>'
        for p, dados in catalogo.items())

    pecas = pecas or []
    if not pecas:
        bloco_pecas = '<p class="hint">Nenhuma peça carregada.</p>'
    else:
        itens = []
        for p in pecas:
            itens.append(
                f'<p style="margin:0 0 6px"><a class="cta ghost" '
                f'href="/admin/trilha/peca/{int(p["numero"])}?produto={produto}'
                f'{("&" + tk) if tk else ""}">'
                f'Semana {int(p["numero"])} · {_esc(p.get("titulo") or "")}</a></p>')
        bloco_pecas = "".join(itens)

    msg_html = f'<div class="infobox">{_esc(msg)}</div>' if msg else ""

    seletor = "".join(
        f'<label style="display:block;margin:4px 0">'
        f'<input type="radio" name="produto_ativo" value="{p}" '
        f'{"checked" if p == produto_ativo else ""}> {_esc(dados["nome"])}</label>'
        for p, dados in catalogo.items())
    bloco_switch = (
        '<div class="panel" style="max-width:680px;margin:0 0 12px;padding:16px 20px">'
        '<p class="plabel">Qual trilha está ativa</p>'
        '<p class="hint" style="margin:6px 0 12px">Só uma por vez. Quem já está no meio de '
        'outra termina ela antes de entrar nesta — trocar aqui não interrompe ninguém.</p>'
        f'<form method="post" action="/admin/trilha">'
        f'<input type="hidden" name="token" value="{_esc(token)}">'
        f'<label style="display:block;margin:4px 0"><input type="radio" name="produto_ativo" '
        f'value="" {"checked" if not produto_ativo else ""}> Nenhuma</label>'
        f'{seletor}'
        '<button class="actbtn" type="submit" style="margin-top:10px">Salvar</button></form></div>')

    if not linhas:
        corpo_lista = '<p class="hint">Ninguém entrou na trilha ainda.</p>'
    else:
        cards = []
        for l in linhas:
            estado = "Concluiu" if l.get("concluiu") else f"Semana {int(l['proxima_peca'])}"
            cards.append(
                f'<div class="panel" style="max-width:680px;margin:0 0 12px;padding:16px 20px">'
                f'<h3 style="margin:0;font-family:var(--disp);color:var(--creme);font-size:20px">'
                f'{_esc(l.get("nome") or "—")}</h3>'
                f'<p class="hint" style="margin:6px 0 0">{_esc(estado)} · '
                f'{int(l.get("enviadas", 0))} recebida(s) · {int(l.get("feitas", 0))} feita(s)</p>'
                f'</div>')
        corpo_lista = "".join(cards)
    corpo = f"""
    <div class="wrap">
      {_admin_nav(token, "trilha")}
      <div class="sectag" style="margin-top:8px">Painel do curador</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin:2px 0 12px">{abas}</div>
      <h2 class="disp" style="font-size:40px;color:var(--creme);margin:2px 0 4px">{_esc(info["nome"])}</h2>
      <p class="hint">{len(linhas)} assinante(s) nesta trilha · {info["total"]} peças no total.</p>
      {msg_html}
      {bloco_switch}
      <div class="panel" style="max-width:680px;margin:0 0 12px;padding:16px 20px">
        <p class="plabel">As {info["total"]} peças</p>
        <p class="hint">Abra cada uma pra ver exatamente o que vira PDF no WhatsApp.</p>
        {bloco_pecas}</div>
      {corpo_lista}
    </div>"""
    return _pagina(f"{_esc(info['nome'])} · {PRODUTO}", corpo, logado=True, atual="trilha",
                   meta_extra='<meta name="robots" content="noindex">')
```

- [ ] **Step 5: Implementar as rotas em `serve.py`**

Substituir o bloco `GET /admin/trilha/peca/<n>` (`app/serve.py:438-467`):

```python
        if path.startswith("/admin/trilha/peca/"):
            import config, db as _db, pdf_trilha, trilha as _trilha_mod
            q = up.parse_qs(up.urlparse(self.path).query)
            token_ok = config.ADMIN_TOKEN and q.get("token", [""])[0] == config.ADMIN_TOKEN
            if not token_ok:
                return self._html("<h3>Acesso negado</h3>", 403)
            _db.init()
            produto = q.get("produto", [""])[0]
            if produto not in config.TRILHAS:
                return self._html("<h3>Produto inválido</h3>", 404)
            numero = _trilha_numero_valido(path.rsplit("/", 1)[1], produto)
            if not numero:
                return self._html("<h3>Peça inválida</h3>", 404)
            peca = _db.trilha_peca(produto, numero)
            if not peca:
                return self._html("<h3>Peça não encontrada</h3>", 404)
            peca["numero"] = numero
            slug = peca.get("ferramenta_slug")
            link = (f"{config.ARTIGOS_URL}/ferramentas/{slug}"
                    if slug and _trilha_mod.caminho_ferramenta(slug) else "")
            return self._html(pdf_trilha.montar_html(
                peca, "(prévia)", abertura="", link_ferramenta=link), 200)
```

Substituir o bloco `GET /admin/trilha` (`app/serve.py:468-484`):

```python
        if path == "/admin/trilha":
            import config, site_web, db as _db, subscribers as _subs, trilha as _trilha
            q = up.parse_qs(up.urlparse(self.path).query)
            token_ok = config.ADMIN_TOKEN and q.get("token", [""])[0] == config.ADMIN_TOKEN
            if not token_ok:
                return self._html("<h3>Acesso negado</h3>", 403)
            _db.init()
            produto = q.get("produto", [""])[0]
            if produto not in config.TRILHAS:
                produto = next(iter(config.TRILHAS), "")
            linhas = []
            total = config.TRILHAS[produto]["total"] if produto else 0
            for l in _db.trilha_painel(produto):
                reg = _subs.por_id(l["subscriber_id"]) or {}
                linhas.append({"nome": reg.get("nome") or l["subscriber_id"],
                               "proxima_peca": l["proxima_peca"],
                               "enviadas": l["enviadas"], "feitas": l["feitas"],
                               "concluiu": l["proxima_peca"] > total})
            return self._html(site_web.pagina_admin_trilha(
                linhas, config.ADMIN_TOKEN or "", pecas=_db.trilha_listar_pecas(produto),
                produto=produto, produto_ativo=_trilha.produto_ativo(),
                msg=q.get("msg", [""])[0]), 200)
```

Substituir o bloco `POST /admin/trilha` (`app/serve.py:902-912`):

```python
        if path == "/admin/trilha":
            import config, db, trilha as _trilha
            token_ok = bool(config.ADMIN_TOKEN) and g("token") == config.ADMIN_TOKEN
            if not token_ok:
                return self._html("<h3>Acesso negado</h3>", 403)
            db.init()
            novo = g("produto_ativo")
            try:
                _trilha.definir_produto_ativo(novo)
            except ValueError:
                return self._redirect(f"/admin/trilha?token={config.ADMIN_TOKEN}"
                                      f"&msg={up.quote('Produto inválido.')}")
            if novo:
                msg = (f"Trilha ativa: {config.TRILHAS[novo]['nome']}. Quem já está no meio de "
                       "outra termina antes de entrar nesta.")
            else:
                msg = "Nenhuma trilha ativa. Ninguém novo entra; quem já está em progresso continua recebendo."
            return self._redirect(f"/admin/trilha?token={config.ADMIN_TOKEN}&msg={up.quote(msg)}")
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_trilha_web.TestTrilhaNumeroValido tests.test_trilha_web.TestAdminTrilha tests.test_trilha_web.TestPreviaPecas tests.test_trilha_web.TestRotaPreviaPeca -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/site_web.py app/serve.py app/tests/test_trilha_web.py
git commit -m "feat(trilha): admin ganha seletor de qual trilha esta ativa"
```

---

### Task 10: Página do assinante multi-produto

**Files:**
- Modify: `app/site_web.py` (`pagina_trilha`)
- Modify: `app/serve.py` (`_pagina_trilha`, `_trilha_post`)
- Test: `app/tests/test_trilha_web.py` (classes `TestPaginaTrilha`, `TestPaginaTrilhaFerramentaFaltando`, `TestTrilhaPostRota`)

**Interfaces:**
- Consumes: `trilha.produto_do_assinante` (Task 4), `db.trilha_historico`/`trilha_peca` (Task 2).
- Produces: `site_web.pagina_trilha(sub, itens, produto, msg="")`.

- [ ] **Step 1: Write the failing test**

Em `app/tests/test_trilha_web.py`, substituir `TestPaginaTrilha`:

```python
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
        h = self.w.pagina_trilha({"nome": "Diego"}, itens, "empreendedorismo")
        self.assertIn("O custo real da sua hora", h)
        self.assertIn("fiz", h.lower())

    def test_peca_feita_nao_mostra_botao_de_novo(self):
        itens = [{"numero": 1, "titulo": "X", "feito": True, "ferramenta_slug": ""}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens, "empreendedorismo")
        self.assertNotIn('value="marcar_feito"', h)

    def test_ferramenta_vira_link_de_download(self):
        itens = [{"numero": 1, "titulo": "X", "feito": False, "ferramenta_slug": "planilha-x"}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens, "empreendedorismo")
        self.assertIn("/ferramentas/planilha-x", h)

    def test_escapa_titulo(self):
        itens = [{"numero": 1, "titulo": "<script>x</script>", "feito": False,
                  "ferramenta_slug": ""}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens, "empreendedorismo")
        self.assertNotIn("<script>x", h)

    def test_lista_vazia_mostra_mensagem_de_fallback(self):
        h = self.w.pagina_trilha({"nome": "Diego"}, [], "empreendedorismo")
        self.assertIn("chega no próximo sábado", h)

    def test_produto_vazio_mostra_mensagem_neutra(self):
        # ninguém ativo e o assinante nunca começou nada -- não existe "a peça
        # da vez" nem "próximo sábado" nenhum pra prometer.
        h = self.w.pagina_trilha({"nome": "Diego"}, [], "")
        self.assertIn("Nenhuma trilha disponível", h)

    def test_peca_ainda_nao_entregue_nao_mostra_botao(self):
        itens = [{"numero": 1, "titulo": "X", "feito": False, "ferramenta_slug": "",
                  "entregue": False}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens, "empreendedorismo")
        self.assertNotIn('value="marcar_feito"', h)
        self.assertIn("sábado", h.lower())

    def test_item_sem_a_chave_entregue_continua_mostrando_o_botao(self):
        itens = [{"numero": 1, "titulo": "X", "feito": False, "ferramenta_slug": ""}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens, "empreendedorismo")
        self.assertIn('value="marcar_feito"', h)

    def test_saudacao_usa_o_nome_do_assinante(self):
        h = self.w.pagina_trilha({"nome": "Diego"}, [], "empreendedorismo")
        self.assertIn("Diego", h)

    def test_plabel_tem_regra_no_css_global(self):
        self.assertIn(".plabel", self.w._CSS)

    def test_nome_e_total_vem_do_produto_certo(self):
        itens = [{"numero": 1, "titulo": "X", "feito": False, "ferramenta_slug": ""}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens, "peptideos")
        total = self.cfg.TRILHAS["peptideos"]["total"]
        self.assertIn(f"de {total}", h)
        self.assertIn(self.cfg.TRILHAS["peptideos"]["nome"], h)
```

Em `TestPaginaTrilhaFerramentaFaltando`, ajustar `setUp`/testes pra produto explícito:

```python
class TestPaginaTrilhaFerramentaFaltando(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["DSCURSO_TRILHA_DIR"] = os.path.join(self.tmp, "trilha")
        os.makedirs(os.path.join(self.tmp, "trilha", "ferramentas"))
        for m in ("config", "db", "subscribers", "trilha", "site_web", "serve"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, subscribers, trilha, site_web, serve
        for m in (config, db, subscribers, trilha, site_web, serve):
            importlib.reload(m)
        subscribers._migrado = False
        db.init()
        self.cfg, self.db, self.subs, self.serve = config, db, subscribers, serve
        self.db.trilha_upsert_peca("empreendedorismo", 1, "eixo", "Peça 1", "corpo", "micro",
                                   "mentalidade", "", "planilha-custo-hora")
        self.sub = {"id": "sub-a", "nome": "Diego"}
        self.db.trilha_registrar_envio(self.sub["id"], "empreendedorismo", 1)
        self.db.trilha_avancar(self.sub["id"], "empreendedorismo", 1)

    def tearDown(self):
        os.environ.pop("DSCURSO_TRILHA_DIR", None)

    def test_link_some_quando_arquivo_nao_existe(self):
        html = self.serve.Handler._pagina_trilha(None, self.sub)
        self.assertNotIn("/ferramentas/planilha-custo-hora", html)

    def test_link_aparece_quando_arquivo_existe(self):
        caminho = os.path.join(self.cfg.TRILHAS["empreendedorismo"]["dir"], "ferramentas",
                               "planilha-custo-hora.csv")
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("a,b\n")
        html = self.serve.Handler._pagina_trilha(None, self.sub)
        self.assertIn("/ferramentas/planilha-custo-hora", html)
```

`TestTrilhaPostRota` não muda de código (usa o stub e não passa `produto` diretamente), mas precisa que `_trilha_post` resolva o produto do assinante — nenhum ajuste de teste aqui além do que já existe; ele serve como teste de regressão pro Step 3.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python3 -m unittest tests.test_trilha_web.TestPaginaTrilha tests.test_trilha_web.TestPaginaTrilhaFerramentaFaltando tests.test_trilha_web.TestTrilhaPostRota -v`
Expected: FAIL.

- [ ] **Step 3: Implementar `pagina_trilha` em `site_web.py`**

Substituir a função inteira (`app/site_web.py:2490-2541`):

```python
def pagina_trilha(sub, itens, produto, msg=""):
    """Trilha do assinante: peça da semana no topo, anteriores abaixo. `produto` é
    a trilha em que ele está agora (resolvido por `trilha.produto_do_assinante`) —
    "" quando não há nenhuma pra ele (nunca começou nada e nenhuma está ativa).

    `itens` já vem pronto do serve (mais recente primeiro), com numero, titulo,
    feito, ferramenta_slug e entregue. `entregue=False` é a peça de prévia que
    `serve._pagina_trilha` insere quando o assinante ainda não recebeu aquela
    peça pelo WhatsApp. Item sem a chave `entregue` é tratado como entregue
    (True), pra não quebrar dado antigo. A página não consulta banco."""
    import config as _cfg
    if not produto:
        corpo = f"""
        <div class="wrap"><div class="panel">
          <h2 class="disp">Trilha</h2>
          <p class="hint">Nenhuma trilha disponível no momento.</p>
          <p style="margin:22px 0 0"><a class="cta ghost" href="/minha">Voltar</a></p>
        </div></div>"""
        return _pagina(f"Trilha · {PRODUTO}", corpo, logado=True, atual="/trilha",
                       meta_extra='<meta name="robots" content="noindex">')
    info = _cfg.TRILHAS.get(produto, {"nome": _cfg.PRODUTO, "total": 0})
    nome = _esc(sub.get("nome") or "assinante")
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
            if not it.get("entregue", True):
                acao = ('<p class="hint" style="margin:8px 0 0">Ainda não chegou — '
                        'você recebe esta peça no seu WhatsApp no próximo sábado.</p>')
            elif it.get("feito"):
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
                f'<p class="plabel">Semana {int(it["numero"])} de {info["total"]}</p>'
                f'<h3 style="margin:4px 0 0">{_esc(it["titulo"])}</h3>'
                f'{ferramenta}{acao}</div>')
        linhas = "".join(partes)
    corpo = f"""
    <div class="wrap">
      <h2 class="disp">{_esc(info["nome"])}</h2>
      <p class="hint">Olá, {nome}. Uma peça por sábado — cada uma tem uma tarefa pequena, é ela que faz a diferença.</p>
      {msg_html}
      {linhas}
      <p style="margin:22px 0 0"><a class="cta ghost" href="/minha">Voltar</a></p>
    </div>"""
    return _pagina(f"{_esc(info['nome'])} · {PRODUTO}", corpo, logado=True, atual="/trilha",
                   meta_extra='<meta name="robots" content="noindex">')
```

- [ ] **Step 4: Implementar `_pagina_trilha`/`_trilha_post` em `serve.py`**

Substituir `_trilha_post` (`app/serve.py:1542-1561`):

```python
    def _trilha_post(self, g):
        """POST /trilha: `marcar_feito` MUTA dado do assinante (trilha_envios.feito_em)
        -- mesmo gate de aceite que `_meus_dados_post` usa."""
        import subscribers, trilha as _trilha
        sub = self._sub_logado()
        if not sub:
            return self._redirect("/entrar")
        if subscribers.precisa_aceitar(sub):
            import site_legal
            return self._html(site_legal.pagina_aceite_termos("/trilha"))
        msg = ""
        if g("acao") == "marcar_feito":
            produto = _trilha.produto_do_assinante(sub["id"])
            numero = _trilha_numero_valido(g("numero"), produto) if produto else 0
            if numero:
                import db as _db
                if _db.trilha_marcar_feito(sub["id"], produto, numero):
                    msg = "Marcado. Bom trabalho."
        return self._html(self._pagina_trilha(sub, msg=msg))
```

Substituir `_pagina_trilha` (`app/serve.py:1570-1603`):

```python
    def _pagina_trilha(self, sub, msg=""):
        """Monta os itens da trilha do assinante (peça atual + anteriores), no
        produto em que ele está agora."""
        import db as _db, site_web as _sw, trilha as _trilha

        def _slug_disponivel(slug):
            return slug if slug and _trilha.caminho_ferramenta(slug) else ""

        produto = _trilha.produto_do_assinante(sub["id"])
        if produto is None:
            return _sw.pagina_trilha(sub, [], "", msg=msg)

        itens = []
        atual = _trilha.proxima_peca(sub["id"])
        vistos = set()
        for env in _db.trilha_historico(sub["id"], produto):
            p = _db.trilha_peca(produto, env["numero"]) or {}
            itens.append({"numero": env["numero"], "titulo": p.get("titulo", ""),
                          "feito": bool(env.get("feito_em")),
                          "ferramenta_slug": _slug_disponivel(p.get("ferramenta_slug", "")),
                          "entregue": True})
            vistos.add(env["numero"])
        if atual and atual["numero"] not in vistos:
            itens.insert(0, {"numero": atual["numero"], "titulo": atual.get("titulo", ""),
                             "feito": False,
                             "ferramenta_slug": _slug_disponivel(atual.get("ferramenta_slug", "")),
                             "entregue": False})
        return _sw.pagina_trilha(sub, itens, produto, msg=msg)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd app && python3 -m unittest tests.test_trilha_web.TestPaginaTrilha tests.test_trilha_web.TestPaginaTrilhaFerramentaFaltando tests.test_trilha_web.TestTrilhaPostRota -v`
Expected: PASS.

- [ ] **Step 6: Rodar a suíte inteira**

Run: `cd app && python3 -m unittest discover -s tests`
Expected: PASS — nenhuma regressão em `daily.py`/`pdf.py`/o resto do repo (nada ali foi tocado).

- [ ] **Step 7: Commit**

```bash
git add app/site_web.py app/serve.py app/tests/test_trilha_web.py
git commit -m "feat(trilha): pagina do assinante multi-produto"
```

---

## Depois deste plano

- **Conteúdo das 11 peças de peptídeos** (`seed/peptideos/01-*.md` … `11-*.md`, cada uma com `## aviso` quando aplicável) — trabalho de redação separado, como foi com as 12 peças de empreendedorismo. O catálogo já aceita o produto vazio sem quebrar (`semear()` conta 0 peças, `enviar_slot` não manda nada pra quem cairia nele).
- **Nome definitivo da trilha de peptídeos** — hoje `"Peptídeos (nome a definir)"` em `config.TRILHAS["peptideos"]["nome"]` (ou via `DSCURSO_PEPTIDEOS_NOME`).
- **Confirmar o status ANVISA inferido** de Sermorelin e Kisspeptina antes de escrever as peças 4 e 7 (ver a spec).
- Só depois disso o Diego liga a trilha de peptídeos em `/admin/trilha`.
