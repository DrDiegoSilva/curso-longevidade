# Alerta de gasto abusivo de IA — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Se o gasto de IA de um dia passar de um teto configurável (R$20 por padrão), o Diego recebe um aviso por WhatsApp — uma vez por dia, sem derrubar a geração de conteúdo se algo falhar.

**Architecture:** Um único ponto de checagem, dentro de `ia_custo.registrar()` (o único lugar por onde toda gravação de custo já passa). Depois de gravar, soma o gasto de hoje (já tem query pronta), compara com o teto, e se passou E ainda não avisou hoje, manda WhatsApp só pro admin e marca o dia como avisado — reaproveitando a tabela `settings` (chave/valor) que já existe, nunca `/data` (efêmero).

**Tech Stack:** Python stdlib puro, mesmo padrão do resto do ledger de custos (`ia_custo.py`, `db.py`).

## Global Constraints

- Teto padrão: **R$ 20,00/dia**, overridável por env **`DSCURSO_LIMIAR_CUSTO_DIA`** (mesma convenção de `DSCURSO_USD_BRL`).
- Nenhuma tabela nova — usa `db.get_config`/`db.set_config` (tabela `settings`, chave/valor, já existe).
- Alerta vai só pro admin (`deliver.enviar_admin`), **não** para os curadores convidados (`deliver.enviar_curador` continua fora de uso aqui).
- Dispara **no máximo uma vez por dia** — a marca de "já avisei hoje" é a data (`AAAA-MM-DD`) salva em `settings["custo_alerta_ultimo_dia"]`.
- A checagem **nunca pode levantar exceção** — mesma garantia que `ia_custo.registrar` já tem hoje ("perder uma linha de custo é aceitável, perder o estudo do dia não é").
- Sem detecção de anomalia/spike relativo — é teto fixo simples, por decisão do Diego.

---

## Task 1: teto configurável + checagem de alerta em `ia_custo.registrar`

**Files:**
- Modify: `app/config.py` (novo `LIMIAR_CUSTO_DIA_BRL`, perto de `USD_BRL`)
- Modify: `app/ia_custo.py` (`registrar` chama a checagem nova; nova função `_checar_alerta_do_dia`)
- Test: Modify `app/tests/test_ia_custo.py` (nova classe `TestAlertaDeCustoAbusivo`)

**Interfaces:**
- Consumes: `db.resumo_ia_uso(desde)`, `db.get_config(chave, default="")`, `db.set_config(chave, valor)` (já existem), `deliver.enviar_admin(msg)` (já existe), `ia_custo.total_usd(linhas)` / `ia_custo.em_brl(usd)` (já existem, mesmo arquivo).
- Produces: `config.LIMIAR_CUSTO_DIA_BRL: float`. `ia_custo.registrar(...)` — assinatura e retorno inalterados; novo efeito colateral (chama a checagem depois de gravar com sucesso).

- [ ] **Step 1: Escrever os testes (falham — a checagem ainda não existe)**

Em `app/tests/test_ia_custo.py`, acrescentar (depois de `TestRegistrarNuncaLevanta`, que já estabelece o padrão de banco isolado que esta classe reaproveita):

```python
class TestAlertaDeCustoAbusivo(unittest.TestCase):
    """Segunda camada depois do vazamento de credenciais via EasyPanel (2026-08-27):
    se o gasto de HOJE passar do teto, avisa o Diego por WhatsApp -- só uma vez por
    dia, nunca derruba a geração. Mesmo isolamento de banco de TestRegistrarNuncaLevanta."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.snap = (os.environ.get("DSCURSO_ARTIGOS_DB"), os.environ.get("DATABASE_URL"),
                     os.environ.get("DSCURSO_LIMIAR_CUSTO_DIA"))
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ.pop("DATABASE_URL", None)

    def tearDown(self):
        artigos, database_url, limiar = self.snap
        for k, v in (("DSCURSO_ARTIGOS_DB", artigos), ("DATABASE_URL", database_url),
                     ("DSCURSO_LIMIAR_CUSTO_DIA", limiar)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        import config, db
        importlib.reload(config)
        importlib.reload(db)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _modulos(self, limiar):
        os.environ["DSCURSO_LIMIAR_CUSTO_DIA"] = str(limiar)
        import config, db, ia_custo
        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(ia_custo)
        return config, db, ia_custo

    def test_abaixo_do_teto_nao_avisa(self):
        cfg, db, ia = self._modulos(1_000_000)  # teto altíssimo -- 1 chamada não estoura
        with mock.patch("deliver.enviar_admin") as m_env:
            ia.registrar("kit", "claude-sonnet-4-6", 100, 10, 1)
        m_env.assert_not_called()

    def test_acima_do_teto_avisa_uma_vez_e_marca_o_dia(self):
        cfg, db, ia = self._modulos(0.001)  # teto baixíssimo -- 1 chamada já estoura
        with mock.patch("deliver.enviar_admin") as m_env:
            ia.registrar("kit", "claude-sonnet-4-6", 1_000_000, 0, 1)
        m_env.assert_called_once()
        from datetime import datetime
        self.assertEqual(db.get_config("custo_alerta_ultimo_dia"),
                         datetime.now().strftime("%Y-%m-%d"))

    def test_segunda_chamada_no_mesmo_dia_nao_avisa_de_novo(self):
        cfg, db, ia = self._modulos(0.001)
        with mock.patch("deliver.enviar_admin") as m_env:
            ia.registrar("kit", "claude-sonnet-4-6", 1_000_000, 0, 1)
            ia.registrar("kit", "claude-sonnet-4-6", 1_000_000, 0, 1)
        m_env.assert_called_once()

    def test_dia_diferente_volta_a_poder_avisar(self):
        cfg, db, ia = self._modulos(0.001)
        db.init()
        db.set_config("custo_alerta_ultimo_dia", "2000-01-01")
        with mock.patch("deliver.enviar_admin") as m_env:
            ia.registrar("kit", "claude-sonnet-4-6", 1_000_000, 0, 1)
        m_env.assert_called_once()

    def test_falha_no_envio_nao_propaga(self):
        cfg, db, ia = self._modulos(0.001)
        with mock.patch("deliver.enviar_admin", side_effect=RuntimeError("whatsapp caiu")):
            ia.registrar("kit", "claude-sonnet-4-6", 1_000_000, 0, 1)  # não pode levantar

    def test_falha_ao_ler_o_resumo_nao_propaga(self):
        cfg, db, ia = self._modulos(0.001)
        with mock.patch.object(db, "resumo_ia_uso", side_effect=RuntimeError("banco caiu")):
            ia.registrar("kit", "claude-sonnet-4-6", 1_000_000, 0, 1)  # não pode levantar

    def test_override_de_env_muda_o_teto(self):
        cfg, db, ia = self._modulos(5)
        self.assertEqual(cfg.LIMIAR_CUSTO_DIA_BRL, 5.0)
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `cd app && python3 -m unittest tests.test_ia_custo.TestAlertaDeCustoAbusivo -v`
Expected: FAIL — `AttributeError: module 'config' has no attribute 'LIMIAR_CUSTO_DIA_BRL'` (e o resto da classe também falha, já que depende dela).

- [ ] **Step 3: Implementar o teto em `app/config.py`**

Adicionar logo depois do bloco de `USD_BRL` (por volta da linha 258-260):

```python
# Teto diário de gasto de IA (R$) que dispara alerta por WhatsApp pro admin -- ver
# ia_custo._checar_alerta_do_dia. Corrigível sem deploy via DSCURSO_LIMIAR_CUSTO_DIA.
try:
    LIMIAR_CUSTO_DIA_BRL = float(os.environ.get("DSCURSO_LIMIAR_CUSTO_DIA") or 20.0)
except ValueError:
    LIMIAR_CUSTO_DIA_BRL = 20.0
```

- [ ] **Step 4: Implementar a checagem em `app/ia_custo.py`**

Trocar a função `registrar` (linhas 43-54):

De:
```python
def registrar(acao, modelo, unidades_in, unidades_out=0, chamadas=1):
    """Grava uma linha do ledger. NUNCA levanta: perder uma linha de custo é aceitável,
    perder o estudo do dia não é."""
    try:
        import db
        db.init()
        # `acao or "desconhecido"`: claude() já normaliza antes de chamar, mas repetimos
        # aqui como defesa para um futuro chamador direto que esqueça de normalizar.
        db.registrar_ia_uso(acao or "desconhecido", modelo, unidades_in,
                            unidades_out, chamadas)
    except Exception as e:
        print(f"[custo] não registrei o uso ({acao}): {e}", flush=True)
```

Para:
```python
def registrar(acao, modelo, unidades_in, unidades_out=0, chamadas=1):
    """Grava uma linha do ledger. NUNCA levanta: perder uma linha de custo é aceitável,
    perder o estudo do dia não é."""
    try:
        import db
        db.init()
        # `acao or "desconhecido"`: claude() já normaliza antes de chamar, mas repetimos
        # aqui como defesa para um futuro chamador direto que esqueça de normalizar.
        db.registrar_ia_uso(acao or "desconhecido", modelo, unidades_in,
                            unidades_out, chamadas)
    except Exception as e:
        print(f"[custo] não registrei o uso ({acao}): {e}", flush=True)
        return
    _checar_alerta_do_dia()


def _checar_alerta_do_dia():
    """Se o gasto de HOJE passar do teto (`config.LIMIAR_CUSTO_DIA_BRL`) e ainda não
    tiver avisado hoje, manda WhatsApp pro admin (não pros curadores convidados -- é
    assunto de conta, não de curadoria) e marca o dia como avisado em `settings`
    (chave/valor já existente -- nunca `/data`, que é apagado a cada deploy/restart).
    Dispara só uma vez por dia: um job de conteúdo sozinho já gera dezenas de chamadas
    de IA, e sem essa marca viraria spam de WhatsApp a cada uma delas. NUNCA levanta --
    mesma garantia de `registrar`."""
    try:
        import config, db, deliver
        from datetime import datetime
        hoje = datetime.now().strftime("%Y-%m-%d")
        if db.get_config("custo_alerta_ultimo_dia") == hoje:
            return
        gasto_brl = em_brl(total_usd(db.resumo_ia_uso(hoje)))
        if gasto_brl > config.LIMIAR_CUSTO_DIA_BRL:
            deliver.enviar_admin(
                f"⚠️ Gasto de IA hoje já passou de R$ {config.LIMIAR_CUSTO_DIA_BRL:.0f}: "
                f"R$ {gasto_brl:.2f}. Detalhe: {config.PUBLIC_URL}/admin/custos?token={config.ADMIN_TOKEN}")
            db.set_config("custo_alerta_ultimo_dia", hoje)
    except Exception as e:
        print(f"[custo] checagem de alerta falhou: {e}", flush=True)
```

- [ ] **Step 5: Rodar os testes de novo e confirmar que passam**

Run: `cd app && python3 -m unittest tests.test_ia_custo -v`
Expected: PASS — toda a suíte de `test_ia_custo.py` (as classes antigas continuam passando sem mudança, mais os 7 testes novos de `TestAlertaDeCustoAbusivo`).

- [ ] **Step 6: Rodar a suíte inteira**

Run: `cd app && python3 -m unittest discover -s tests`
Expected: PASS em tudo — confirma que nada em `resumo_diario.py`/`audio.py` (os dois chamadores reais de `ia_custo.registrar`) quebrou com o novo efeito colateral.

- [ ] **Step 7: Commit**

```bash
git add app/config.py app/ia_custo.py app/tests/test_ia_custo.py
git commit -m "feat(custos): alerta por WhatsApp quando o gasto de IA do dia passa do teto"
```
