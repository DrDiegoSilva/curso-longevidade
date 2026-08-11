"""Banco do site artigos (SQLite, stdlib) — persiste cada digest ENVIADO e serve
o arquivo protegido (por tema/data) + tabelas de login OTP e sessões.

Caminho vem de config.artigos_db() (env DSCURSO_ARTIGOS_DB sobrescreve → testável).
Partes puras (slug, registrar/listar/obter) sem rede; auth_web usa as tabelas daqui.
"""
import os
import json
import sqlite3
import unicodedata
import re
import config

_TEMAS_JSON = os.path.join(os.path.dirname(__file__), "temas_config.json")


def _temas_cfg():
    try:
        with open(_TEMAS_JSON, encoding="utf-8") as f:
            return json.load(f).get("temas", {})
    except Exception:
        return {}


def slug(texto):
    """Slug ASCII minúsculo sem acento: 'Menopausa & Reposição' -> 'menopausa-reposicao'."""
    n = unicodedata.normalize("NFKD", texto or "")
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"[^a-zA-Z0-9]+", "-", n).strip("-").lower()
    return n or "tema"


def _is_pg():
    return bool(config.DATABASE_URL)


class _Wrap:
    """Interface comum estilo sqlite sobre sqlite3 OU psycopg2 (Postgres/Supabase).
    Traduz placeholders ? -> %s no Postgres; commit/rollback+close no fim do `with`.
    """
    def __init__(self, conn, pg):
        self._c = conn
        self._pg = pg

    def execute(self, sql, params=()):
        if self._pg:
            import psycopg2.extras
            cur = self._c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql.replace("?", "%s"), params)
        else:
            cur = self._c.cursor()
            cur.execute(sql, params)
        return cur

    def executescript(self, sql):
        cur = self._c.cursor()
        cur.execute(sql) if self._pg else cur.executescript(sql)
        return cur

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *a):
        try:
            self._c.commit() if exc_type is None else self._c.rollback()
        finally:
            self._c.close()


def _integrity_error():
    """Classe de IntegrityError do driver em uso — pra distinguir "violou uma
    constraint" (esperado, tratável) de "o banco caiu" (não tratável) sem
    inspecionar a mensagem de erro."""
    if _is_pg():
        import psycopg2
        return psycopg2.IntegrityError
    return sqlite3.IntegrityError


def _conn():
    if _is_pg():
        import psycopg2
        # connect_timeout: se a rede/banco não responder, falha em 10s em vez de
        # pendurar para sempre (o agendador roda em loop sequencial e travaria calado).
        return _Wrap(psycopg2.connect(config.DATABASE_URL, connect_timeout=10), True)
    os.makedirs(os.path.dirname(config.artigos_db()) or ".", exist_ok=True)
    c = sqlite3.connect(config.artigos_db())
    c.row_factory = sqlite3.Row
    return _Wrap(c, False)


_INITED = False


def init():
    global _INITED
    if _INITED:
        return
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS digests (
                data TEXT NOT NULL,
                titulo_original TEXT,
                tema TEXT NOT NULL,
                tema_slug TEXT NOT NULL,
                titulo_pt TEXT NOT NULL,
                resumo TEXT NOT NULL,
                gancho TEXT,
                grafico TEXT,
                doi TEXT,
                fonte TEXT,
                url TEXT,
                criado_em TEXT,
                PRIMARY KEY (data, tema_slug)
            );
            CREATE TABLE IF NOT EXISTS login_codes (
                whatsapp TEXT PRIMARY KEY,
                codigo_hash TEXT NOT NULL,
                expira TEXT NOT NULL,
                tentativas INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                whatsapp TEXT NOT NULL,
                nome TEXT,
                expira TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS subscribers (
                id TEXT PRIMARY KEY,
                nome TEXT, whatsapp TEXT, email TEXT, cpf TEXT,
                plano TEXT, metodo TEXT,
                status TEXT DEFAULT 'ATIVO',
                asaas_customer_id TEXT, asaas_subscription_id TEXT, asaas_payment_id TEXT,
                asaas_installment_id TEXT,
                proximo_vencimento TEXT, acesso_ate TEXT, carencia_ate TEXT, aviso_renov_em TEXT,
                criado_em TEXT, cancelado_em TEXT, cancel_motivo TEXT, oferta_retencao_em TEXT,
                senha_hash TEXT, curador INTEGER DEFAULT 0, slot_envio TEXT
            );
            CREATE TABLE IF NOT EXISTS pending_signups (
                token TEXT PRIMARY KEY,
                nome TEXT, email TEXT, cpf TEXT, whatsapp TEXT,
                plano TEXT, metodo TEXT, parcelas INTEGER, valor REAL,
                valor_base REAL,
                afiliado_codigo TEXT,
                criado_em TEXT
            );
            CREATE TABLE IF NOT EXISTS webhook_events (
                payment_id TEXT, event TEXT, processed_em TEXT,
                PRIMARY KEY (payment_id, event)
            );
            CREATE TABLE IF NOT EXISTS cupons (
                codigo TEXT PRIMARY KEY, ativo INTEGER DEFAULT 1, descricao TEXT, criado_em TEXT,
                desconto_valor REAL DEFAULT 0, plano_slug TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS afiliados (
                id TEXT PRIMARY KEY, nome TEXT, contato TEXT, codigo TEXT UNIQUE,
                pct_desconto REAL DEFAULT 10, pct_comissao REAL DEFAULT 3,
                ativo INTEGER DEFAULT 1, criado_em TEXT
            );
            CREATE TABLE IF NOT EXISTS comissoes (
                id TEXT PRIMARY KEY, afiliado_id TEXT, subscriber_id TEXT, plano TEXT,
                valor_venda REAL, valor_comissao REAL,
                pago INTEGER DEFAULT 0, criado_em TEXT, pago_em TEXT
            );
            CREATE TABLE IF NOT EXISTS settings (
                chave TEXT PRIMARY KEY, valor TEXT
            );
            CREATE TABLE IF NOT EXISTS envios_slot (
                data TEXT, slot TEXT, enviado_em TEXT,
                PRIMARY KEY (data, slot)
            );
            CREATE TABLE IF NOT EXISTS envios_dia (
                data TEXT, subscriber_id TEXT, enviado_em TEXT,
                PRIMARY KEY (data, subscriber_id)
            );
            CREATE TABLE IF NOT EXISTS senha_tokens (
                token TEXT PRIMARY KEY,
                whatsapp TEXT NOT NULL,
                expira TEXT NOT NULL,
                usado INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS curadoria_candidatos (
                id TEXT PRIMARY KEY,
                tema TEXT, titulo TEXT, fonte TEXT, data TEXT, doi TEXT, url TEXT,
                abstract TEXT, pergunta TEXT, score REAL, chave TEXT UNIQUE,
                citacoes INTEGER DEFAULT 0, tipo TEXT DEFAULT 'varredura',
                status TEXT DEFAULT 'novo', criado_em TEXT, tags TEXT DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS classicos (
                id TEXT PRIMARY KEY, tema TEXT, titulo_pt TEXT, titulo_original TEXT, resumo TEXT,
                gancho TEXT, grafico TEXT, doi TEXT, fonte TEXT, url TEXT, data TEXT,
                citacoes INTEGER DEFAULT 0, ultimo_envio TEXT, criado_em TEXT, tags TEXT DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS reserva_resumos (
                id TEXT PRIMARY KEY, candidato_id TEXT,
                tema TEXT, titulo_pt TEXT, titulo_original TEXT, resumo TEXT, gancho TEXT, grafico TEXT,
                doi TEXT, fonte TEXT, url TEXT, data TEXT,
                status TEXT DEFAULT 'pronto', prioridade INTEGER DEFAULT 0,
                origem TEXT DEFAULT 'varredura', enviado_em TEXT, criado_em TEXT,
                score REAL DEFAULT 0, tags TEXT DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS daily_drafts (
                data TEXT PRIMARY KEY,
                review_token TEXT,
                status TEXT DEFAULT 'DRAFT',
                payload TEXT,
                criado_em TEXT,
                atualizado_em TEXT
            );
            CREATE TABLE IF NOT EXISTS agenda (
                data TEXT PRIMARY KEY,
                tipo TEXT DEFAULT 'vazio',
                ref_id TEXT,
                payload TEXT,
                tema TEXT,
                titulo TEXT,
                fixado INTEGER DEFAULT 0,
                criado_em TEXT,
                atualizado_em TEXT
            );
            CREATE TABLE IF NOT EXISTS series (
                id TEXT PRIMARY KEY,
                nome TEXT,
                status TEXT DEFAULT 'rascunho',
                data_inicio TEXT DEFAULT '',
                criado_em TEXT,
                ativada_em TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS serie_itens (
                id TEXT PRIMARY KEY,
                serie_id TEXT,
                ordem INTEGER DEFAULT 0,
                ref_tipo TEXT,
                ref_id TEXT,
                titulo TEXT DEFAULT '',
                tema TEXT DEFAULT '',
                data TEXT DEFAULT '',
                enviado INTEGER DEFAULT 0,
                UNIQUE (serie_id, ref_tipo, ref_id)
            );
            CREATE UNIQUE INDEX IF NOT EXISTS ux_serie_itens_dedup
                ON serie_itens(serie_id, ref_tipo, ref_id);
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
            CREATE TABLE IF NOT EXISTS automacoes_renovacao (
                id TEXT PRIMARY KEY, dias INTEGER, canal TEXT, texto TEXT,
                ativo INTEGER DEFAULT 1, criado_em TEXT
            );
            CREATE TABLE IF NOT EXISTS avisos_renovacao (
                subscriber_id TEXT, automacao_id TEXT, vencimento_ref TEXT, enviado_em TEXT,
                PRIMARY KEY (subscriber_id, automacao_id, vencimento_ref)
            );
            """
        )
    _migrar_colunas()
    _migrar_indices()
    _seed_cupons()
    _seed_automacoes()
    _migrar_texto_seed0()
    if _is_pg():
        _habilitar_rls()        # trava a Data API pública do Supabase (app conecta direto e ignora RLS)
    _INITED = True


_TABELAS = ["digests", "login_codes", "sessions", "subscribers",
            "pending_signups", "webhook_events", "cupons", "senha_tokens",
            "curadoria_candidatos", "reserva_resumos", "daily_drafts", "agenda",
            "afiliados", "comissoes", "settings", "envios_slot", "envios_dia",
            "automacoes_renovacao", "avisos_renovacao", "classicos",
            "series", "serie_itens",
            "trilha_pecas", "trilha_progresso", "trilha_envios"]


def _add_coluna(c, tabela, coluna, tipo):
    """ADD COLUMN idempotente (pg: IF NOT EXISTS; sqlite: try/except duplicata)."""
    if _is_pg():
        c.execute(f"ALTER TABLE {tabela} ADD COLUMN IF NOT EXISTS {coluna} {tipo}")
    else:
        try:
            c.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
        except Exception:
            pass  # coluna já existe (banco recém-criado pela CREATE TABLE)


def _migrar_colunas():
    """Adiciona colunas novas a bancos JÁ existentes (idempotente).
    Banco novo/testes já nasce com a coluna via CREATE TABLE — aqui o ALTER é
    p/ o Supabase de produção que foi criado antes desta coluna existir."""
    with _conn() as c:
        _add_coluna(c, "subscribers", "senha_hash", "TEXT")
        _add_coluna(c, "subscribers", "curador", "INTEGER DEFAULT 0")
        _add_coluna(c, "subscribers", "slot_envio", "TEXT")
        # Titulo em INGLES do paper: o cartao "recorte do estudo" do kit mostra o
        # original, e ele se perdia -- `art["titulo"]` vira titulo_pt nos caminhos de
        # reserva/classico/regeracao (daily.py:274, :319, :392).
        _add_coluna(c, "reserva_resumos", "titulo_original", "TEXT")
        _add_coluna(c, "classicos", "titulo_original", "TEXT")
        _add_coluna(c, "digests", "titulo_original", "TEXT")
        _add_coluna(c, "cupons", "usos", "INTEGER DEFAULT 0")
        _add_coluna(c, "cupons", "uso_unico", "INTEGER DEFAULT 1")
        _add_coluna(c, "cupons", "dias_acesso", "INTEGER DEFAULT 0")
        _add_coluna(c, "cupons", "desconto_valor", "REAL DEFAULT 0")
        _add_coluna(c, "cupons", "plano_slug", "TEXT DEFAULT ''")
        _add_coluna(c, "reserva_resumos", "prioridade", "INTEGER DEFAULT 0")
        _add_coluna(c, "reserva_resumos", "origem", "TEXT DEFAULT 'varredura'")
        _add_coluna(c, "reserva_resumos", "enviado_em", "TEXT")
        _add_coluna(c, "reserva_resumos", "score", "REAL DEFAULT 0")
        _add_coluna(c, "pending_signups", "afiliado_codigo", "TEXT")
        _add_coluna(c, "subscribers", "termos_versao", "TEXT")
        _add_coluna(c, "subscribers", "termos_aceito_em", "TEXT")
        _add_coluna(c, "subscribers", "termos_ip", "TEXT")
        _add_coluna(c, "pending_signups", "termos_versao", "TEXT")
        _add_coluna(c, "pending_signups", "termos_ip", "TEXT")
        _add_coluna(c, "comissoes", "estornada_em", "TEXT")
        _add_coluna(c, "subscribers", "valor_contratado", "REAL")
        # B1/B2 da revisão final #2: o webhook precisa da BASE contratada (pré-desconto de
        # método e pré-cupom). `valor` guarda o que o cliente PAGA, que no parcelado é uma
        # parcela e no Pix já vem com 5% off — nenhum dos dois serve como preço de renovação.
        _add_coluna(c, "pending_signups", "valor_base", "REAL")
        # C1 da revisão #3: identifica o GRUPO de parcelamento do contrato vigente. Sem ele a
        # guarda de parcela não distingue uma parcela atrasada do contrato antigo da parcela 1
        # de um contrato NOVO — e o ex-assinante que voltava no anual em 12x pagava sem receber.
        _add_coluna(c, "subscribers", "asaas_installment_id", "TEXT")
        _add_coluna(c, "curadoria_candidatos", "citacoes", "INTEGER DEFAULT 0")
        _add_coluna(c, "curadoria_candidatos", "tipo", "TEXT DEFAULT 'varredura'")
        _add_coluna(c, "curadoria_candidatos", "tags", "TEXT DEFAULT '[]'")
        _add_coluna(c, "reserva_resumos", "tags", "TEXT DEFAULT '[]'")
        _add_coluna(c, "classicos", "tags", "TEXT DEFAULT '[]'")


# Índices ÚNICOS que podem falhar num banco já povoado (linhas já em conflito).
# Por isso ficam FORA do executescript do init(): um CREATE INDEX que levanta lá
# dentro aborta o script inteiro e o app sobe sem schema. Cada um tem um reparo
# determinístico que roda antes da 2ª tentativa.
_IDX_SERIE_ATIVA = ("CREATE UNIQUE INDEX IF NOT EXISTS ux_series_uma_ativa "
                    "ON series(status) WHERE status='ativa'")
_IDX_SERIE_ITENS_ORDEM = ("CREATE UNIQUE INDEX IF NOT EXISTS ux_serie_itens_ordem "
                          "ON serie_itens(serie_id, ordem)")


def _demover_series_ativas_extras():
    """Deixa ATIVA só a série ativada primeiro; as outras viram 'incompleta' —
    status visível na /series que NÃO tranca a próxima ativação. Só é alcançável
    num banco escrito antes de ux_series_uma_ativa existir (a corrida de
    check-then-act do series.ativar_serie deixava N séries ativas).

    `extras` nasce FORA do `with`: hoje o `_Wrap.__exit__` devolve None (não
    suprime) e um erro do bloco propaga antes do log, mas a ligação só é segura
    por causa desse detalhe. Se algum dia o wrapper passar a engolir exceção,
    esta função — cujo trabalho INTEIRO é limpeza — quebraria com variável solta
    em cima do erro de verdade."""
    extras = []
    with _conn() as c:
        rows = c.execute("SELECT id FROM series WHERE status='ativa' "
                         "ORDER BY ativada_em ASC, criado_em ASC, id ASC").fetchall()
        extras = [dict(r)["id"] for r in rows][1:]
        for sid in extras:
            c.execute("UPDATE series SET status='incompleta' WHERE id=?", (sid,))
    if extras:
        print(f"[db] {len(extras)} série(s) ativa(s) extra(s) marcadas 'incompleta': {extras}",
              flush=True)


def _renumerar_serie_itens():
    """Renumera 'ordem' 0..n-1 por série preservando a ordem visível (ordem, id).
    Repara bancos onde a corrida do `MAX(ordem)+1` já deixou ordens repetidas —
    pré-requisito pra ux_serie_itens_ordem existir."""
    with _conn() as c:
        rows = c.execute("SELECT id, serie_id FROM serie_itens "
                         "ORDER BY serie_id, ordem, id").fetchall()
        atual, n = object(), 0
        for r in rows:
            d = dict(r)
            if d["serie_id"] != atual:
                atual, n = d["serie_id"], 0
            c.execute("UPDATE serie_itens SET ordem=? WHERE id=?", (n, d["id"]))
            n += 1


def _criar_indice(sql):
    with _conn() as c:
        c.execute(sql)


def _migrar_indices():
    """Cria os índices únicos retroativos: tenta, repara o conflito, tenta de novo.
    Uma 2ª falha propaga (o banco está num estado que o reparo não previu — melhor
    barulho no boot do que uma constraint que o código acha que existe e não existe)."""
    for sql, reparo, nome in ((_IDX_SERIE_ATIVA, _demover_series_ativas_extras, "ux_series_uma_ativa"),
                              (_IDX_SERIE_ITENS_ORDEM, _renumerar_serie_itens, "ux_serie_itens_ordem")):
        try:
            _criar_indice(sql)
            continue
        except _integrity_error() as e:
            print(f"[db] {nome}: {e} — reparando as linhas em conflito", flush=True)
        reparo()
        _criar_indice(sql)


def _habilitar_rls():
    """ENABLE RLS em toda tabela (sem policy = Data API pública bloqueada). Idempotente."""
    with _conn() as c:
        for t in _TABELAS:
            c.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")


def _seed_cupons():
    from datetime import datetime
    codigos = config.cupons_seed()
    if codigos:
        with _conn() as c:
            for cod in codigos:
                # cupons do env = multi-uso (o Diego compartilha o mesmo código)
                c.execute("INSERT INTO cupons (codigo,ativo,descricao,uso_unico,criado_em) VALUES (?,1,'seed',0,?) "
                          "ON CONFLICT (codigo) DO UPDATE SET uso_unico=0", (cod, datetime.now().isoformat()))
    # Cupom de lançamento (-R$500 no anual). UPSERT (não DO NOTHING) porque uma linha
    # "LANCAMENTO" pré-existente como CORTESIA (ex.: alguém pôs o código no env
    # DSCURSO_CUPONS, cujo loop roda ANTES deste seed e grava desconto_valor=0/
    # dias_acesso=0 = acesso grátis) tem que ser corrigida pro formato promocional, nunca
    # deixada como está — senão `_eh_cortesia` (que olha desconto_valor==0) manda todo
    # comprador de LANCAMENTO pro caminho grátis. Blindado em try/except pra uma falha
    # aqui nunca derrubar o boot.
    try:
        with _conn() as c:
            c.execute(
                "INSERT INTO cupons (codigo,ativo,descricao,usos,uso_unico,dias_acesso,criado_em,desconto_valor,plano_slug) "
                "VALUES ('LANCAMENTO',1,'Lançamento: -R$500 no anual',0,0,0,?,500,'anual') "
                # Sem `ativo=1` aqui: o DO UPDATE ainda corrige a FORMA (shape) do cupom em
                # todo boot (a proteção contra a cortesia pré-existente do comentário acima
                # continua), mas não pisa mais o on/off — uma desativação pelo admin
                # (toggle_cupom) tem que sobreviver a um restart/deploy. `ativo=1` continua
                # no VALUES: um cupom NOVO nasce ativo.
                "ON CONFLICT (codigo) DO UPDATE SET uso_unico=0, dias_acesso=0, "
                "desconto_valor=500, plano_slug='anual'",
                (datetime.now().isoformat(),))
    except Exception as e:
        print(f"[db] seed LANCAMENTO falhou: {e}", flush=True)


def criar_pending(dados):
    """Cadastro em aberto (antes do redirect ao checkout). Retorna o token (externalReference)."""
    import secrets
    from datetime import datetime
    token = secrets.token_hex(16)
    with _conn() as c:
        c.execute(
            """INSERT INTO pending_signups (token,nome,email,cpf,whatsapp,plano,metodo,parcelas,valor,valor_base,afiliado_codigo,termos_versao,termos_ip,criado_em)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (token, dados.get("nome", ""), dados.get("email", ""), dados.get("cpf", ""),
             dados.get("whatsapp", ""), dados.get("plano", ""), dados.get("metodo", ""),
             int(dados.get("parcelas", 1)), float(dados.get("valor", 0)),
             # None (não 0) quando ausente: o webhook distingue "base desconhecida" de
             # "base zero" pra não gravar um valor_contratado inventado.
             (float(dados["valor_base"]) if dados.get("valor_base") else None),
             (dados.get("afiliado_codigo", "") or ""),
             (dados.get("termos_versao", "") or ""), (dados.get("termos_ip", "") or ""),
             datetime.now().isoformat()),
        )
    return token


def obter_pending(token):
    with _conn() as c:
        r = c.execute("SELECT * FROM pending_signups WHERE token=?", (token,)).fetchone()
    return dict(r) if r else None


def obter_pendings_por_cpf(cpf, limite=10):
    """Os pendings recentes desse CPF, do mais novo pro mais velho.

    Plural de propósito: o Asaas não devolve o `externalReference`, então o webhook casa o
    pending pelo CPF — e o cliente que volta no navegador e refaz o checkout com outro
    método/plano deixa mais de um em aberto. Pegando só o mais recente, o pending CERTO
    (o do link que ele de fato pagou) ficava enterrado atrás do abandonado.
    """
    dig = "".join(ch for ch in (cpf or "") if ch.isdigit())
    if not dig:
        return []
    with _conn() as c:
        rows = c.execute("SELECT * FROM pending_signups WHERE cpf=? ORDER BY criado_em DESC LIMIT ?",
                         (dig, int(limite))).fetchall()
    return [dict(r) for r in rows]


def obter_pending_por_cpf(cpf):
    """Pending mais recente para esse CPF (compara só dígitos). Fallback do webhook
    quando o Asaas NÃO propaga o externalReference do checkout — recupera o
    afiliado_codigo (e nome/e-mail/plano) pela pessoa. None se CPF vazio/sem match."""
    dig = "".join(ch for ch in (cpf or "") if ch.isdigit())
    if not dig:
        return None
    with _conn() as c:
        r = c.execute("SELECT * FROM pending_signups WHERE cpf=? ORDER BY criado_em DESC LIMIT 1",
                      (dig,)).fetchone()
    return dict(r) if r else None


def registrar_webhook(payment_id, event):
    """True se é a 1ª vez (processar); False se já visto (idempotência)."""
    from datetime import datetime
    with _conn() as c:
        cur = c.execute("INSERT INTO webhook_events (payment_id,event,processed_em) VALUES (?,?,?) "
                        "ON CONFLICT (payment_id,event) DO NOTHING",
                        (payment_id or "", event or "", datetime.now().isoformat()))
        return cur.rowcount > 0


def remover_webhook(payment_id, event):
    """Desfaz a marca de idempotência — usado quando o processamento falha, p/ o
    Asaas conseguir re-tentar o mesmo evento em vez de ser descartado como duplicado."""
    with _conn() as c:
        c.execute("DELETE FROM webhook_events WHERE payment_id=? AND event=?",
                  (payment_id or "", event or ""))


def registrar_envio_slot(data, slot):
    """True se é a 1ª vez que (data,slot) é registrado hoje; False se já registrado.
    Guarda idempotência do envio por slot (restart não reenvia)."""
    from datetime import datetime
    with _conn() as c:
        cur = c.execute("INSERT INTO envios_slot (data,slot,enviado_em) VALUES (?,?,?) "
                        "ON CONFLICT (data,slot) DO NOTHING",
                        (data or "", slot or "", datetime.now().isoformat()))
        return cur.rowcount > 0


def registrar_envio_assinante(data, sub_id):
    """True se é a 1ª vez que (data, assinante) é registrado hoje; False se já registrado.
    Claim atômico do envio do dia por assinante (guarda 2x na troca de slot)."""
    from datetime import datetime
    with _conn() as c:
        cur = c.execute("INSERT INTO envios_dia (data,subscriber_id,enviado_em) VALUES (?,?,?) "
                        "ON CONFLICT (data,subscriber_id) DO NOTHING",
                        (data or "", sub_id or "", datetime.now().isoformat()))
        return cur.rowcount > 0


def ja_enviou_hoje(data, sub_id):
    """True se o assinante já recebeu o estudo em `data` (leitura, não escreve)."""
    with _conn() as c:
        r = c.execute("SELECT 1 FROM envios_dia WHERE data=? AND subscriber_id=?",
                      (data or "", sub_id or "")).fetchone()
    return r is not None


def slot_ja_enviou(data, slot):
    """True se o tick daquele slot já rodou em `data` (leitura). Base do gate do catch-up."""
    with _conn() as c:
        r = c.execute("SELECT 1 FROM envios_slot WHERE data=? AND slot=?",
                      (data or "", slot or "")).fetchone()
    return r is not None


# Textos padrão da régua. {nome}, {ate} (data do vencimento) e {link} (URL do /renovar).
_AUTOMACOES_SEED = [
    (-7, "whatsapp", "Olá {nome}! Sua assinatura da Atualização Científica vence em {ate} — "
                     "daqui a 7 dias. Para não perder nenhum estudo, renove por aqui:\n{link}"),
    (-3, "whatsapp", "{nome}, faltam 3 dias: sua assinatura vence em {ate}. "
                     "A renovação leva 1 minuto:\n{link}"),
    # "a partir de amanhã" era falso: `acesso_ate` é data pura (meia-noite), então no dia do
    # vencimento os estudos JÁ pararam. Texto novo não promete um prazo que não existe.
    (0,  "whatsapp", "{nome}, sua assinatura venceu hoje e os estudos param de chegar. "
                     "Renove agora para retomar de onde parou:\n{link}"),
    (1,  "whatsapp", "{nome}, sua assinatura venceu ontem e os estudos pararam. Volte agora e "
                     "ganhe *1 mês extra* de acesso:\n{link}"),
    (3,  "whatsapp", "{nome}, seu acesso está parado há 3 dias. Se voltar agora, você ganha "
                     "*1 mês a mais* junto com a renovação:\n{link}"),
    (15, "whatsapp", "{nome}, última chamada: volte para a Atualização Científica e ganhe "
                     "*1 mês extra*. Depois desta, não insistimos mais.\n{link}"),
]


_TEXTO_SEED0_ANTIGO = ("{nome}, sua assinatura vence hoje. A partir de amanhã os estudos param "
                       "de chegar. Renove agora:\n{link}")


def _migrar_texto_seed0():
    """Corrige em bancos JÁ existentes o texto do aviso do dia do vencimento.

    `_seed_automacoes` usa ON CONFLICT DO NOTHING com id determinístico, então uma correção
    no seed nunca alcança quem já tem a linha — em produção a mensagem continuaria afirmando
    "a partir de amanhã os estudos param de chegar", o que é falso (`acesso_ate` é data pura,
    então no dia do vencimento já pararam) e agora contradiz o próprio link, que aponta para
    a recontratação. Só troca o texto se ele ainda for EXATAMENTE o seed antigo: se o Diego
    editou a mensagem na tela, a edição dele manda."""
    novo = next((t for d, _c, t in _AUTOMACOES_SEED if d == 0), None)
    if not novo:
        return
    with _conn() as c:
        c.execute("UPDATE automacoes_renovacao SET texto=? WHERE id='seed0' AND texto=?",
                  (novo, _TEXTO_SEED0_ANTIGO))


def _seed_automacoes():
    """Cria as automações padrão 1× (idempotente pelo id determinístico)."""
    from datetime import datetime
    with _conn() as c:
        for dias, canal, texto in _AUTOMACOES_SEED:
            c.execute("INSERT INTO automacoes_renovacao (id,dias,canal,texto,ativo,criado_em) "
                      "VALUES (?,?,?,?,1,?) ON CONFLICT (id) DO NOTHING",
                      (f"seed{dias}", dias, canal, texto, datetime.now().isoformat()))


def listar_automacoes(so_ativas=False):
    """Automações da régua, da mais antecipada para a mais tardia."""
    q = "SELECT * FROM automacoes_renovacao"
    if so_ativas:
        q += " WHERE ativo=1"
    q += " ORDER BY dias ASC"
    with _conn() as c:
        return [dict(r) for r in c.execute(q).fetchall()]


def salvar_automacao(id, dias, canal, texto, ativo=1):
    """Cria (id vazio) ou atualiza uma automação. Devolve o id."""
    import secrets
    from datetime import datetime
    id = (id or "").strip() or secrets.token_hex(6)
    with _conn() as c:
        c.execute("INSERT INTO automacoes_renovacao (id,dias,canal,texto,ativo,criado_em) "
                  "VALUES (?,?,?,?,?,?) ON CONFLICT (id) DO UPDATE SET "
                  "dias=excluded.dias, canal=excluded.canal, texto=excluded.texto, "
                  "ativo=excluded.ativo",
                  (id, int(dias), canal, texto, 1 if int(ativo or 0) else 0,
                   datetime.now().isoformat()))
    return id


def remover_automacao(id):
    with _conn() as c:
        return c.execute("DELETE FROM automacoes_renovacao WHERE id=?", (id,)).rowcount > 0


def registrar_aviso(subscriber_id, automacao_id, vencimento_ref):
    """Marca que este aviso já saiu para este assinante NESTE ciclo. True se marcou agora.

    O `vencimento_ref` é a data de vencimento vigente no momento do envio: quando o assinante
    renova, ela muda e a régua volta a valer no ciclo seguinte sem precisar limpar nada.
    Mesmo padrão do ledger `envios_dia`, que matou o reenvio duplicado dos estudos.
    """
    from datetime import datetime
    with _conn() as c:
        cur = c.execute("INSERT INTO avisos_renovacao "
                        "(subscriber_id,automacao_id,vencimento_ref,enviado_em) VALUES (?,?,?,?) "
                        "ON CONFLICT (subscriber_id,automacao_id,vencimento_ref) DO NOTHING",
                        (subscriber_id or "", automacao_id or "", vencimento_ref or "",
                         datetime.now().isoformat()))
        return cur.rowcount > 0


def remover_aviso(subscriber_id, automacao_id, vencimento_ref):
    """Desfaz a marca do ledger — usado quando o envio falha, para a próxima execução do
    mesmo dia tentar de novo."""
    with _conn() as c:
        c.execute("DELETE FROM avisos_renovacao WHERE subscriber_id=? AND automacao_id=? "
                  "AND vencimento_ref=?", (subscriber_id or "", automacao_id or "",
                                           vencimento_ref or ""))


def cupom_valido(codigo):
    if not codigo:
        return False
    with _conn() as c:
        r = c.execute("SELECT ativo FROM cupons WHERE codigo=?", ((codigo or "").strip().upper(),)).fetchone()
    return bool(r and r["ativo"])


def criar_cupom(descricao="", uso_unico=True, dias_acesso=0, codigo=None, desconto_valor=0, plano_slug=""):
    """Gera um cupom. dias_acesso>0 => cortesia (N dias grátis). desconto_valor>0 =>
    cupom PROMOCIONAL de valor fixo (R$ off no checkout pago), escopável por plano_slug
    ('' = qualquer). Retorna o código (UPPER)."""
    import secrets
    from datetime import datetime
    cod = (codigo or secrets.token_hex(4)).strip().upper()
    with _conn() as c:
        c.execute("INSERT INTO cupons (codigo,ativo,descricao,usos,uso_unico,dias_acesso,criado_em,desconto_valor,plano_slug) "
                  "VALUES (?,1,?,0,?,?,?,?,?) ON CONFLICT (codigo) DO NOTHING",
                  (cod, descricao or "", 1 if uso_unico else 0, int(dias_acesso or 0),
                   datetime.now().isoformat(), float(desconto_valor or 0), (plano_slug or "").strip()))
    return cod


def obter_cupom(codigo):
    with _conn() as c:
        r = c.execute("SELECT * FROM cupons WHERE codigo=?", ((codigo or "").strip().upper(),)).fetchone()
    return dict(r) if r else None


def cupom_desconto(codigo, plano_slug):
    """R$ de desconto fixo de um cupom PROMOCIONAL ativo cujo escopo casa o plano.
    0 se não existe, está inativo, não é promocional, ou o escopo não bate."""
    info = obter_cupom(codigo)
    if not info or not info.get("ativo"):
        return 0.0
    val = float(info.get("desconto_valor") or 0)
    if val <= 0:
        return 0.0
    escopo = (info.get("plano_slug") or "").strip()
    if escopo and escopo != plano_slug:
        return 0.0
    return val


def listar_cupons():
    with _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM cupons ORDER BY criado_em DESC").fetchall()]


def consumir_cupom(codigo):
    """Marca 1 uso do cupom. Se for de uso único, desativa (ativo=0). Se for multi-uso,
    PRESERVA o ativo atual — nunca escreve 1 fixo, senão um cupom multi-uso que o admin
    desativou (toggle_cupom) reativa sozinho no próximo uso."""
    cod = (codigo or "").strip().upper()
    with _conn() as c:
        r = c.execute("SELECT uso_unico,usos,ativo FROM cupons WHERE codigo=?", (cod,)).fetchone()
        if not r:
            return
        novos = (r["usos"] or 0) + 1
        ativo = 0 if r["uso_unico"] else r["ativo"]
        c.execute("UPDATE cupons SET usos=?, ativo=? WHERE codigo=?", (novos, ativo, cod))


def toggle_cupom(codigo, ativo):
    """Ativa/desativa um cupom (admin). `ativo` é um valor explícito (set), não um flip —
    mesmo padrão de `toggle_afiliado`: um double-submit do form não inverte duas vezes."""
    cod = (codigo or "").strip().upper()
    with _conn() as c:
        c.execute("UPDATE cupons SET ativo=? WHERE codigo=?", (1 if ativo else 0, cod))


# ── Afiliados / comissões (D3) ──
def afiliado_por_codigo(codigo):
    """Afiliado ATIVO pelo código (case-insensitive). None se não existe ou inativo."""
    if not codigo:
        return None
    with _conn() as c:
        r = c.execute("SELECT * FROM afiliados WHERE codigo=? AND ativo=1",
                      ((codigo or "").strip().upper(),)).fetchone()
    return dict(r) if r else None


def criar_afiliado(nome, contato, codigo, pct_desconto=10, pct_comissao=3):
    """Cadastra um afiliado. Retorna o código (UPPER). ON CONFLICT(codigo) DO NOTHING."""
    import secrets
    from datetime import datetime
    cod = (codigo or "").strip().upper()
    with _conn() as c:
        c.execute("INSERT INTO afiliados (id,nome,contato,codigo,pct_desconto,pct_comissao,ativo,criado_em) "
                  "VALUES (?,?,?,?,?,?,1,?) ON CONFLICT (codigo) DO NOTHING",
                  (secrets.token_hex(6), (nome or "").strip(), (contato or "").strip(), cod,
                   float(pct_desconto or 0), float(pct_comissao or 0), datetime.now().isoformat()))
    return cod


def toggle_afiliado(id, ativo):
    with _conn() as c:
        c.execute("UPDATE afiliados SET ativo=? WHERE id=?", (1 if ativo else 0, id))


def atualizar_afiliado(id, nome, contato, codigo, pct_desconto, pct_comissao):
    """Edita os campos de um afiliado. Código guardado em UPPER (mantém unicidade)."""
    with _conn() as c:
        c.execute("UPDATE afiliados SET nome=?, contato=?, codigo=?, pct_desconto=?, pct_comissao=? WHERE id=?",
                  ((nome or "").strip(), (contato or "").strip(), (codigo or "").strip().upper(),
                   float(pct_desconto or 0), float(pct_comissao or 0), id))


# ── Settings (chave/valor) — ex.: templates editáveis das mensagens ──
def get_config(chave, default=""):
    """Valor salvo em settings, ou o default. Defensivo: não quebra o fluxo se faltar a tabela."""
    try:
        with _conn() as c:
            r = c.execute("SELECT valor FROM settings WHERE chave=?", (chave,)).fetchone()
        return r["valor"] if (r and r["valor"] is not None) else default
    except Exception:
        return default


def set_config(chave, valor):
    with _conn() as c:
        c.execute("INSERT INTO settings (chave,valor) VALUES (?,?) "
                  "ON CONFLICT (chave) DO UPDATE SET valor=excluded.valor", (chave, valor or ""))


def registrar_comissao(afiliado_id, subscriber_id, plano, valor_venda, valor_comissao):
    """1 linha no ledger de comissões (pago=0). Retorna o id."""
    import secrets
    from datetime import datetime
    cid = secrets.token_hex(8)
    with _conn() as c:
        c.execute("INSERT INTO comissoes (id,afiliado_id,subscriber_id,plano,valor_venda,valor_comissao,pago,criado_em) "
                  "VALUES (?,?,?,?,?,?,0,?)",
                  (cid, afiliado_id, subscriber_id, plano or "",
                   float(valor_venda or 0), float(valor_comissao or 0), datetime.now().isoformat()))
    return cid


def listar_comissoes(afiliado_id=None, pago=None, incluir_estornadas=False):
    """`pago=False` é a consulta de "pendente" (usada no painel) — por isso, quando
    filtramos por não-paga, também excluímos as ESTORNADAS por padrão: uma comissão
    estornada (venda devolvida) não é mais devida, então não pode aparecer como pendente nem
    entrar na fila de pagamento. Sem filtro (`pago=None`) continua trazendo tudo,
    inclusive estornadas — é o que a tela de histórico/auditoria precisa ver.

    `incluir_estornadas=True` é o caso da tela /admin/afiliados: ela quer `pago=False`
    (não trazer o que já foi quitado) mas TAMBÉM quer ver as estornadas — pra exibi-las
    marcadas na UI, não pra escondê-las de novo. Não muda o default (False): quem chama
    sem esse parâmetro continua com o comportamento antigo, que é o que protege o
    agregado `comissao_pendente` (listar_afiliados) e o marcar_comissao_paga."""
    q = "SELECT * FROM comissoes"
    conds, params = [], []
    if afiliado_id is not None:
        conds.append("afiliado_id=?"); params.append(afiliado_id)
    if pago is not None:
        conds.append("pago=?"); params.append(1 if pago else 0)
        if not pago and not incluir_estornadas:
            conds.append("estornada_em IS NULL")
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY criado_em DESC"
    with _conn() as c:
        return [dict(r) for r in c.execute(q, params).fetchall()]


def marcar_comissao_paga(id):
    """`AND estornada_em IS NULL` é rede de segurança: mesmo que a listagem do painel
    já exclua comissões estornadas de "pendente", isto impede que um POST direto
    (bypass da tela) marque como paga uma comissão de venda que foi devolvida."""
    from datetime import datetime
    with _conn() as c:
        c.execute("UPDATE comissoes SET pago=1, pago_em=? WHERE id=? AND estornada_em IS NULL",
                  (datetime.now().isoformat(), id))


def estornar_comissao(subscriber_id):
    """Marca como estornada toda comissão gerada por esse assinante (venda devolvida).
    Sem isso o afiliado receberia comissão de uma venda que deixou de existir.
    Retorna quantas linhas foram marcadas."""
    from datetime import datetime
    with _conn() as c:
        cur = c.execute("UPDATE comissoes SET estornada_em=? WHERE subscriber_id=? AND estornada_em IS NULL",
                        (datetime.now().isoformat(), subscriber_id))
        return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0


def claim_cancelamento(subscriber_id, motivo, acesso_ate):
    """Grava o cancelamento INTEIRO (status + cancelado_em + motivo + acesso_ate) num
    ÚNICO UPDATE condicional atômico, que é ao mesmo tempo o claim contra corrida.

    PORQUÊ o claim é a própria gravação, e não uma marca prévia: enquanto "reservar o
    cancelamento" e "gravar o cancelamento" eram dois passos, existia uma janela entre
    eles em que o assinante estava marcado como cancelado mas o estado final (status,
    motivo, até quando o acesso vale) ainda não tinha sido escrito. Qualquer falha
    dentro dessa janela — banco, Asaas, processo morto — deixava o cadastro num meio
    termo: com cancelado_em preenchido (logo, impossível de cancelar de novo, porque o
    claim sempre perderia) e sem o cancelamento de fato registrado. Fundindo os dois
    passos, ou o cancelamento está inteiro no banco ou não aconteceu nada.

    O estorno deixa de fazer parte do claim e vira ajuste POSTERIOR (encerrar_acesso):
    se o reembolso der certo, zera-se o acesso; se falhar, o estado gravado aqui já é o
    correto (acesso até o fim do período pago) e não há nada a desfazer.

    `WHERE ... AND (cancelado_em IS NULL OR cancelado_em='')` é a condição do claim: um
    único UPDATE é atômico tanto no SQLite quanto no Postgres (trava a linha), então
    duplo clique ou retry de rede em /cancelar só entrega o fluxo a UMA chamada.

    Retorna True se esta chamada gravou agora (venceu o claim) e False se outra já
    tinha cancelado (perdeu — não é falha, é corrida; nada a repetir).
    """
    from datetime import datetime
    with _conn() as c:
        cur = c.execute(
            "UPDATE subscribers SET status='CANCELADO', cancelado_em=?, cancel_motivo=?, acesso_ate=? "
            "WHERE id=? AND (cancelado_em IS NULL OR cancelado_em='')",
            (datetime.now().isoformat(), motivo or "", acesso_ate, subscriber_id))
        return cur.rowcount > 0


def encerrar_acesso(subscriber_id):
    """Ajuste posterior ao claim: zera acesso_ate porque o estorno integral saiu (quem
    foi reembolsado não segue com acesso até o fim do período pago).

    Roda DEPOIS do cancelamento já estar gravado, de propósito: mover dinheiro é a
    parte que pode falhar de forma ambígua, e o cancelamento não pode depender dela.

    `AND status='CANCELADO'` protege contra tirar o acesso de quem voltou a ser ATIVO
    entre o claim e este ajuste (ex.: webhook de renovação chegando no meio).
    Retorna True se zerou.
    """
    with _conn() as c:
        cur = c.execute("UPDATE subscribers SET acesso_ate=NULL WHERE id=? AND status='CANCELADO'",
                        (subscriber_id,))
        return cur.rowcount > 0


def listar_afiliados():
    """Afiliados + agregados de comissão (n_vendas, comissao_total, comissao_pendente).

    `comissao_pendente` exclui comissão estornada (venda devolvida): sem essa
    exclusão, o painel mostraria como devido dinheiro de uma venda que já foi
    reembolsada integralmente ao cliente."""
    with _conn() as c:
        afs = [dict(r) for r in c.execute("SELECT * FROM afiliados ORDER BY criado_em DESC").fetchall()]
        for a in afs:
            ag = c.execute(
                "SELECT COUNT(*) n, COALESCE(SUM(valor_comissao),0) tot, "
                "COALESCE(SUM(CASE WHEN pago=0 AND estornada_em IS NULL THEN valor_comissao ELSE 0 END),0) pend "
                "FROM comissoes WHERE afiliado_id=?", (a["id"],)).fetchone()
            a["n_vendas"] = ag["n"]
            a["comissao_total"] = round(float(ag["tot"] or 0), 2)
            a["comissao_pendente"] = round(float(ag["pend"] or 0), 2)
    return afs


# ── Tokens de definição/redefinição de senha ──
def criar_token_senha(whatsapp, validade_horas=1):
    """Cria um token de uso único p/ criar/redefinir senha. Retorna o token."""
    import secrets
    from datetime import datetime, timedelta
    token = secrets.token_hex(24)
    expira = (datetime.now() + timedelta(hours=validade_horas)).isoformat()
    with _conn() as c:
        c.execute("INSERT INTO senha_tokens (token,whatsapp,expira,usado) VALUES (?,?,?,0)",
                  (token, whatsapp or "", expira))
    return token


def obter_token_senha(token):
    """Dados do token {whatsapp,expira} se existe, NÃO usado e NÃO expirado; senão None."""
    from datetime import datetime
    if not token:
        return None
    with _conn() as c:
        r = c.execute("SELECT * FROM senha_tokens WHERE token=?", (token,)).fetchone()
    if not r:
        return None
    d = dict(r)
    if d.get("usado"):
        return None
    try:
        if datetime.fromisoformat(d["expira"]) < datetime.now():
            return None
    except Exception:
        return None
    return d


def consumir_token_senha(token):
    """Marca o token como usado (uso único)."""
    with _conn() as c:
        c.execute("UPDATE senha_tokens SET usado=1 WHERE token=?", (token,))


# ── Curadoria (candidatos) + Reserva (resumos prontos) — banco privado, NÃO publica ──
def salvar_candidatos(cands):
    """Insere candidatos novos (dedup por chave). Retorna quantos NOVOS entraram.

    PROMOÇÃO: `tipo='corpus'` é a classificação de menor valor — é só memória, não passou
    por triagem semanal nem por ranking de citações. Se uma varredura posterior achar o
    mesmo paper como `varredura` ou `classico`, o registro é promovido (com a pergunta, o
    score e as citações que só a varredura calcula).

    Sem isso, o backfill do corpus ENGOLIA o paper: o `ON CONFLICT DO NOTHING` mantinha
    `tipo='corpus'` e ele nunca aparecia na Triagem nem nos Clássicos, que filtram por
    tipo. O caminho contrário não vale — backfill não rebaixa clássico a memória.

    Promoção não conta como "novo": inflar o número faria a tela dizer que a varredura
    trouxe mais do que trouxe. E não mexe no `status`, pra não jogar de volta pra fila
    um candidato que o Diego já triou.
    """
    import secrets
    from datetime import datetime
    with _conn() as c:
        # Conta pela DIFERENÇA de linhas: com `DO UPDATE` o `rowcount` é 1 tanto no
        # insert quanto na promoção, e distinguir os dois no SQL não é portável entre
        # SQLite e Postgres. Duas queries no total, não uma por candidato.
        antes = c.execute("SELECT COUNT(*) n FROM curadoria_candidatos").fetchone()["n"]
        for x in cands:
            if not x.get("chave"):
                continue
            cur = c.execute(
                """INSERT INTO curadoria_candidatos
                   (id,tema,titulo,fonte,data,doi,url,abstract,pergunta,score,chave,citacoes,tipo,tags,status,criado_em)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'novo', ?)
                   ON CONFLICT (chave) DO UPDATE SET
                     tipo=excluded.tipo, tema=excluded.tema, pergunta=excluded.pergunta,
                     score=excluded.score, citacoes=excluded.citacoes, tags=excluded.tags
                   WHERE curadoria_candidatos.tipo='corpus' AND excluded.tipo<>'corpus'""",
                (secrets.token_hex(8), x.get("tema", ""), x.get("titulo", ""), x.get("fonte", ""),
                 x.get("data", ""), x.get("doi", ""), x.get("url", ""), x.get("abstract", ""),
                 x.get("pergunta", ""), float(x.get("score", 0) or 0), x.get("chave"),
                 int(x.get("citacoes", 0) or 0), x.get("tipo", "varredura"),
                 json.dumps(x.get("tags") or []), datetime.now().isoformat()))
        depois = c.execute("SELECT COUNT(*) n FROM curadoria_candidatos").fetchone()["n"]
    return depois - antes


def listar_candidatos(status=None, tema=None, tipo=None):
    q = "SELECT * FROM curadoria_candidatos"
    conds, params = [], []
    if status:
        conds.append("status=?"); params.append(status)
    if tema:
        conds.append("tema=?"); params.append(tema)
    if tipo:
        conds.append("tipo=?"); params.append(tipo)
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY tema, score DESC, criado_em DESC"
    with _conn() as c:
        return [dict(r) for r in c.execute(q, params).fetchall()]


def definir_selecao(ids):
    """Marca 'selecionado' os ids dados e volta p/ 'novo' os que saíram da seleção.
    Não toca em 'resumido'/'descartado'."""
    alvo = set(ids or [])
    with _conn() as c:
        atuais = [r["id"] for r in c.execute(
            "SELECT id FROM curadoria_candidatos WHERE status IN ('novo','selecionado')").fetchall()]
        for i in atuais:
            c.execute("UPDATE curadoria_candidatos SET status=? WHERE id=?",
                      ("selecionado" if i in alvo else "novo", i))


def marcar_candidatos(ids, status):
    with _conn() as c:
        for i in (ids or []):
            c.execute("UPDATE curadoria_candidatos SET status=? WHERE id=?", (status, i))


def obter_candidato(cid):
    """Um candidato da curadoria por id (ou None). Espelha obter_reserva — usado
    por series._indisponiveis pra checar o status antes de agendar."""
    with _conn() as c:
        r = c.execute("SELECT * FROM curadoria_candidatos WHERE id=?", (cid,)).fetchone()
    return dict(r) if r else None


def marcar_candidato_agendado(cid):
    """Prende um candidato na agenda (sai do pool 'novo' até enviar/soltar)."""
    with _conn() as c:
        c.execute("UPDATE curadoria_candidatos SET status='agendado' WHERE id=?", (cid,))


def marcar_candidato_pronto(cid):
    """Devolve um candidato agendado ao pool (reconciliação de órfão)."""
    with _conn() as c:
        c.execute("UPDATE curadoria_candidatos SET status='novo' WHERE id=?", (cid,))


def contar_candidatos():
    with _conn() as c:
        rows = c.execute("SELECT status, COUNT(*) n FROM curadoria_candidatos GROUP BY status").fetchall()
    return {r["status"]: r["n"] for r in rows}


def salvar_reserva(reg):
    """Salva um resumo pronto na reserva/fila. prioridade>0 = fura fila (artigo do Diego).
    Retorna o id."""
    import secrets
    from datetime import datetime
    rid = secrets.token_hex(8)
    with _conn() as c:
        c.execute(
            """INSERT INTO reserva_resumos
               (id,candidato_id,tema,titulo_pt,titulo_original,resumo,gancho,grafico,doi,fonte,url,data,status,prioridade,origem,criado_em,score,tags)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'pronto', ?,?,?,?,?)""",
            (rid, reg.get("candidato_id"), reg.get("tema", ""), reg.get("titulo_pt", ""),
             reg.get("titulo_original") or reg.get("titulo", ""),
             reg.get("resumo", ""), reg.get("gancho", ""), reg.get("grafico", ""), reg.get("doi", ""),
             reg.get("fonte", ""), reg.get("url", ""), reg.get("data", ""),
             int(reg.get("prioridade", 0) or 0), reg.get("origem", "varredura"), datetime.now().isoformat(),
             float(reg.get("score", 0) or 0), json.dumps(reg.get("tags") or [])))
    return rid


def listar_reserva(status=None):
    q = "SELECT * FROM reserva_resumos"
    params = []
    if status:
        q += " WHERE status=?"; params.append(status)
    q += " ORDER BY prioridade DESC, score DESC, criado_em DESC"
    with _conn() as c:
        return [dict(r) for r in c.execute(q, params).fetchall()]


def contar_reserva_pronto():
    """Quantos resumos 'pronto' (estoque disponível p/ enviar) há na reserva."""
    with _conn() as c:
        r = c.execute("SELECT COUNT(*) n FROM reserva_resumos WHERE status='pronto'").fetchone()
    return r["n"] if r else 0


def proximo_da_reserva():
    """Próximo resumo a enviar da fila: prioridade (artigos do Diego) primeiro, depois nota
    (score) maior, depois os mais antigos. Só 'pronto'. Retorna dict ou None (não marca —
    o envio confirma)."""
    with _conn() as c:
        r = c.execute("SELECT * FROM reserva_resumos WHERE status='pronto' "
                      "ORDER BY prioridade DESC, score DESC, criado_em ASC LIMIT 1").fetchone()
    return dict(r) if r else None


def obter_reserva(rid):
    with _conn() as c:
        r = c.execute("SELECT * FROM reserva_resumos WHERE id=?", (rid,)).fetchone()
    return dict(r) if r else None


def marcar_reserva_enviado(rid):
    from datetime import datetime
    with _conn() as c:
        c.execute("UPDATE reserva_resumos SET status='enviado', enviado_em=? WHERE id=?",
                  (datetime.now().isoformat(), rid))


# ── Status da reserva p/ a agenda ──
def marcar_reserva_agendado(rid):
    """Tira o resumo da reserva 'pronto' e prende na agenda (não conta como estoque)."""
    with _conn() as c:
        c.execute("UPDATE reserva_resumos SET status='agendado' WHERE id=?", (rid,))


def marcar_reserva_pronto(rid):
    """Devolve o resumo agendado ao estoque 'pronto'."""
    with _conn() as c:
        c.execute("UPDATE reserva_resumos SET status='pronto' WHERE id=?", (rid,))


# ── Clássicos (estudos-marco evergreen, reusáveis — NÃO são consumidos no envio) ──
def salvar_classico(reg):
    """Banca um estudo-marco (evergreen, reusável). Retorna o id."""
    import secrets
    from datetime import datetime
    cid = secrets.token_hex(8)
    with _conn() as c:
        c.execute(
            """INSERT INTO classicos
               (id,tema,titulo_pt,titulo_original,resumo,gancho,grafico,doi,fonte,url,data,citacoes,criado_em,tags)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (cid, reg.get("tema", ""), reg.get("titulo_pt", ""),
             reg.get("titulo_original") or reg.get("titulo", ""), reg.get("resumo", ""),
             reg.get("gancho", ""), reg.get("grafico", ""), reg.get("doi", ""), reg.get("fonte", ""),
             reg.get("url", ""), reg.get("data", ""), int(reg.get("citacoes", 0) or 0),
             datetime.now().isoformat(), json.dumps(reg.get("tags") or [])))
    return cid


def obter_classico(cid):
    with _conn() as c:
        r = c.execute("SELECT * FROM classicos WHERE id=?", (cid,)).fetchone()
    return dict(r) if r else None


def listar_classicos(tema=None, elegiveis=True):
    """Clássicos do banco. elegiveis=True filtra por ciclo: nunca-enviado OU ultimo_envio mais
    antigo que config.CLASSICO_REUSO_MESES; ordena nunca-enviado/mais-antigo primeiro, + citado."""
    q = "SELECT * FROM classicos"
    conds, params = [], []
    if tema:
        conds.append("tema=?"); params.append(tema)
    if elegiveis:
        from datetime import datetime, timedelta
        corte = (datetime.now() - timedelta(days=30 * config.CLASSICO_REUSO_MESES)).isoformat()
        conds.append("(ultimo_envio IS NULL OR ultimo_envio < ?)"); params.append(corte)
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY (ultimo_envio IS NOT NULL), ultimo_envio ASC, citacoes DESC"
    with _conn() as c:
        return [dict(r) for r in c.execute(q, params).fetchall()]


def marcar_classico_enviado(cid, data):
    """Marca o envio de um clássico (NÃO deleta — reusável no próximo ciclo)."""
    with _conn() as c:
        c.execute("UPDATE classicos SET ultimo_envio=? WHERE id=?", (data, cid))


# ── Tags (Fase 1 — item 8) ──
_TAG_TAB = {"candidato": "curadoria_candidatos", "reserva": "reserva_resumos", "classico": "classicos"}


def atualizar_tags(tipo, id_, tags):
    """Sobrescreve as tags de um estudo (candidato/reserva/classico). tipo desconhecido = no-op."""
    tab = _TAG_TAB.get(tipo)
    if not tab:
        return
    with _conn() as c:
        c.execute(f"UPDATE {tab} SET tags=? WHERE id=?", (json.dumps(tags or []), id_))


def buscar_por_tag(termo):
    """Estudos (reserva+candidatos+clássicos) cuja 'tags' contém `termo` (substring, sem case).
    Retorna [{tipo,id,titulo,tema,tags}]. Termo vazio -> []."""
    termo = (termo or "").strip().lower()
    if not termo:
        return []
    like = f"%{termo}%"
    out = []
    with _conn() as c:
        for tipo, tab, tcol in (("reserva", "reserva_resumos", "titulo_pt"),
                                ("candidato", "curadoria_candidatos", "titulo"),
                                ("classico", "classicos", "titulo_pt")):
            for r in c.execute(f"SELECT id, {tcol} AS titulo, tema, tags FROM {tab} "
                               f"WHERE lower(tags) LIKE ?", (like,)).fetchall():
                d = dict(r)
                try:
                    tags = json.loads(d.get("tags") or "[]")
                except Exception:
                    tags = []
                out.append({"tipo": tipo, "id": d["id"], "titulo": d.get("titulo") or "",
                            "tema": d.get("tema") or "", "tags": tags})
    return out


# ── Séries de estudos (Fase 2 — item 8) ──
def criar_serie(nome):
    """Cria uma série (rascunho, sem itens). Retorna o id."""
    import secrets
    from datetime import datetime
    sid = secrets.token_hex(8)
    with _conn() as c:
        c.execute(
            "INSERT INTO series (id,nome,status,data_inicio,criado_em,ativada_em) "
            "VALUES (?,?, 'rascunho', '', ?, '')",
            (sid, nome or "", datetime.now().isoformat()))
    return sid


def listar_series():
    with _conn() as c:
        rows = c.execute("SELECT * FROM series ORDER BY criado_em DESC").fetchall()
    return [dict(r) for r in rows]


def obter_serie(serie_id):
    """{"serie": dict, "itens": [dict, ...]} ordenados por 'ordem', ou None se não existir.
    O desempate por 'id' deixa a leitura DETERMINÍSTICA mesmo num banco antigo que
    ainda tenha ordens repetidas (ver _renumerar_serie_itens): series.ativar_serie
    casa esta lista 1:1 com os dias de envio, então "ordem instável" = sequência
    curada embaralhada."""
    with _conn() as c:
        s = c.execute("SELECT * FROM series WHERE id=?", (serie_id,)).fetchone()
        if not s:
            return None
        itens = c.execute("SELECT * FROM serie_itens WHERE serie_id=? ORDER BY ordem, id",
                           (serie_id,)).fetchall()
    return {"serie": dict(s), "itens": [dict(i) for i in itens]}


_TENTATIVAS_ORDEM = 8       # colisões de 'ordem' entre threads: recomeça com MAX fresco


def adicionar_serie_item(serie_id, ref_tipo, ref_id, titulo="", tema=""):
    """Adiciona um item ao fim da série (ordem = max+1). Se (serie_id, ref_tipo,
    ref_id) já está na série, devolve o item EXISTENTE em vez de duplicar — um
    double-click no ➕ do /series não pode agendar o mesmo estudo duas vezes
    (ver serie_item_existe, usado pela rota pra escolher a mensagem certa).

    O pré-check abaixo é só um atalho pro caso comum (evita gerar id/computar
    ordem à toa quando o item já existe) — quem FECHA a corrida de verdade é o
    `UNIQUE (serie_id, ref_tipo, ref_id)` da tabela + `ON CONFLICT DO NOTHING`:
    o servidor é `ThreadingHTTPServer` (serve.py), então um double-click real
    chega como duas threads concorrentes, cada uma com sua própria conexão
    sqlite — um SELECT-antes-do-INSERT sem constraint tem uma janela TOCTOU
    (as duas threads podem ver "não existe" antes de qualquer INSERT commitar;
    comprovado com um teste de 8 threads concorrentes, que produzia 3 linhas
    em vez de 1 antes desta constraint). A tabela é nova nesta Fase 2 (ainda
    não deployada) — dá pra declarar a UNIQUE de cara, sem migração em tabela
    de produção existente. Retorna o id do item.

    A 'ordem' tinha o MESMO TOCTOU, e ele era pior: `SELECT MAX(ordem)+1` seguido
    de um INSERT sem UNIQUE(serie_id, ordem) atrás deixava 10 threads com 10 itens
    DISTINTOS gravarem ordem = [0,0,0,0,0,1,1,2,2,2] — sem erro nenhum, só a
    sequência curada (o ponto inteiro de uma série) embaralhada. Agora o índice
    ux_serie_itens_ordem recusa a colisão e a tentativa recomeça com um MAX fresco."""
    import secrets
    erro = None
    for _ in range(_TENTATIVAS_ORDEM):
        try:
            with _conn() as c:
                existente = c.execute(
                    "SELECT id FROM serie_itens WHERE serie_id=? AND ref_tipo=? AND ref_id=?",
                    (serie_id, ref_tipo, ref_id)).fetchone()
                if existente:
                    return dict(existente)["id"]
                iid = secrets.token_hex(8)
                r = c.execute("SELECT COALESCE(MAX(ordem), -1) AS m FROM serie_itens WHERE serie_id=?",
                              (serie_id,)).fetchone()
                ordem = int(dict(r)["m"]) + 1
                # ON CONFLICT com alvo explícito só cobre o alvo: uma colisão em
                # (serie_id, ordem) levanta IntegrityError e cai no retry abaixo.
                cur = c.execute(
                    "INSERT INTO serie_itens (id,serie_id,ordem,ref_tipo,ref_id,titulo,tema,data,enviado) "
                    "VALUES (?,?,?,?,?,?,?, '', 0) "
                    "ON CONFLICT (serie_id, ref_tipo, ref_id) DO NOTHING",
                    (iid, serie_id, ordem, ref_tipo, ref_id, titulo or "", tema or ""))
                if cur.rowcount > 0:
                    return iid
                # perdeu a corrida pro ON CONFLICT: outra thread inseriu entre o
                # pré-check e este INSERT — devolve o id de quem venceu.
                vencedor = c.execute(
                    "SELECT id FROM serie_itens WHERE serie_id=? AND ref_tipo=? AND ref_id=?",
                    (serie_id, ref_tipo, ref_id)).fetchone()
                return dict(vencedor)["id"]
        except _integrity_error() as e:
            erro = e            # (serie_id, ordem) ocupado por outra thread: recomeça
    raise erro


def serie_item_existe(serie_id, ref_tipo, ref_id):
    """True se (serie_id, ref_tipo, ref_id) já está na série. Usado pela rota
    /series ANTES de chamar adicionar_serie_item (que já evita duplicar) só
    pra escolher a mensagem certa ('já está na série' vs 'Adicionado')."""
    with _conn() as c:
        r = c.execute(
            "SELECT 1 FROM serie_itens WHERE serie_id=? AND ref_tipo=? AND ref_id=?",
            (serie_id, ref_tipo, ref_id)).fetchone()
    return r is not None


def remover_serie_item(item_id):
    with _conn() as c:
        c.execute("DELETE FROM serie_itens WHERE id=?", (item_id,))


def reordenar_serie_item(item_id, direcao):
    """Troca a 'ordem' do item com o vizinho ('cima' = ordem menor, 'baixo' = maior).

    O swap passa por uma SENTINELA porque ux_serie_itens_ordem é imediato (checado
    a cada statement, não no commit): um swap ingênuo em dois UPDATEs viola a
    constraint já no primeiro, quando os dois itens ficariam com a mesma 'ordem'.
    A sentinela é MIN(ordem)-1 da própria série, calculada na MESMA transação —
    sempre livre, e não depende de nenhum valor mágico que uma reordenação
    interrompida pudesse ter deixado pra trás."""
    with _conn() as c:
        it = c.execute("SELECT * FROM serie_itens WHERE id=?", (item_id,)).fetchone()
        if not it:
            return
        it = dict(it)
        if direcao == "cima":
            viz = c.execute("SELECT * FROM serie_itens WHERE serie_id=? AND ordem<? "
                             "ORDER BY ordem DESC LIMIT 1", (it["serie_id"], it["ordem"])).fetchone()
        else:
            viz = c.execute("SELECT * FROM serie_itens WHERE serie_id=? AND ordem>? "
                             "ORDER BY ordem ASC LIMIT 1", (it["serie_id"], it["ordem"])).fetchone()
        if not viz:
            return
        viz = dict(viz)
        r = c.execute("SELECT COALESCE(MIN(ordem), 0) - 1 AS s FROM serie_itens WHERE serie_id=?",
                      (it["serie_id"],)).fetchone()
        sentinela = int(dict(r)["s"])
        c.execute("UPDATE serie_itens SET ordem=? WHERE id=?", (sentinela, it["id"]))
        c.execute("UPDATE serie_itens SET ordem=? WHERE id=?", (it["ordem"], viz["id"]))
        c.execute("UPDATE serie_itens SET ordem=? WHERE id=?", (viz["ordem"], it["id"]))


def reivindicar_serie_ativa(serie_id, data_inicio, ativada_em):
    """Claim ATÔMICO do único slot de "série ativa". True se ESTA chamada virou a
    série (que precisa estar em 'rascunho') a ativa; False se perdeu.

    Duas travas, as duas no banco: (1) o UPDATE é condicional em
    status='rascunho', então N cliques na MESMA série só passam uma vez
    (rowcount==0 nos perdedores); (2) o índice único PARCIAL ux_series_uma_ativa
    recusa a segunda série DIFERENTE. Sem isso, o "uma série ativa" de
    series.ativar_serie era check-then-act com o loop inteiro de escrita na
    janela — e serve.py é ThreadingHTTPServer, uma thread por clique: 8 ativações
    concorrentes deixavam 8 séries ativas, e 8 cliques na mesma série
    consumiam/devolviam a mesma reserva várias vezes.

    O claim vem ANTES de escrever os dias justamente pra que o perdedor pare sem
    ter tocado na agenda (desfazer um agenda_upsert que já sobrescreveu o slot
    anterior não é reversível — o ocupante antigo já voltou pro estoque)."""
    try:
        with _conn() as c:
            cur = c.execute(
                "UPDATE series SET status='ativa', data_inicio=?, ativada_em=? "
                "WHERE id=? AND status='rascunho'", (data_inicio, ativada_em, serie_id))
            venceu = cur.rowcount > 0
    except _integrity_error():
        return False        # outra série já ocupa o slot de 'ativa'
    return venceu


def atualizar_serie(serie_id, **campos):
    """Atualiza campos da série (whitelist: nome/status/data_inicio/ativada_em). No-op se vazio."""
    permitidos = {"nome", "status", "data_inicio", "ativada_em"}
    sets = {k: v for k, v in campos.items() if k in permitidos}
    if not sets:
        return
    cols = ", ".join(f"{k}=?" for k in sets)
    with _conn() as c:
        c.execute(f"UPDATE series SET {cols} WHERE id=?", (*sets.values(), serie_id))


def set_serie_item_data(item_id, data):
    with _conn() as c:
        c.execute("UPDATE serie_itens SET data=? WHERE id=?", (data or "", item_id))


# ── Agenda (data -> estudo) ──
def agenda_slot(data):
    with _conn() as c:
        r = c.execute("SELECT * FROM agenda WHERE data=?", (data,)).fetchone()
    return dict(r) if r else None


def agenda_listar(desde, ate):
    with _conn() as c:
        rows = c.execute("SELECT * FROM agenda WHERE data BETWEEN ? AND ? ORDER BY data",
                         (desde, ate)).fetchall()
    return {r["data"]: dict(r) for r in rows}


def agenda_upsert(data, tipo="vazio", ref_id=None, payload=None, tema="", titulo="", fixado=0):
    from datetime import datetime
    now = datetime.now().isoformat()
    with _conn() as c:
        existe = c.execute("SELECT 1 FROM agenda WHERE data=?", (data,)).fetchone()
        if existe:
            c.execute("UPDATE agenda SET tipo=?, ref_id=?, payload=?, tema=?, titulo=?, "
                      "fixado=?, atualizado_em=? WHERE data=?",
                      (tipo, ref_id, payload, tema, titulo, int(fixado), now, data))
        else:
            c.execute("INSERT INTO agenda (data,tipo,ref_id,payload,tema,titulo,fixado,criado_em,atualizado_em) "
                      "VALUES (?,?,?,?,?,?,?,?,?)",
                      (data, tipo, ref_id, payload, tema, titulo, int(fixado), now, now))


def agenda_fixar(data, on=True):
    """Fixa/solta um dia. Cria a linha (vazio) se ainda não existir, p/ o pino persistir
    mesmo num dia que a agenda ainda não materializou."""
    if agenda_slot(data) is None:
        agenda_upsert(data, tipo="vazio")
    with _conn() as c:
        c.execute("UPDATE agenda SET fixado=? WHERE data=?", (1 if on else 0, data))


def _devolver_ao_estoque(slot):
    """Devolve ao estoque o item apontado por um slot de agenda (dict de uma linha da
    tabela `agenda`, ou None): reserva volta 'pronto', candidato volta 'novo', fila
    devolve à queue_store. Clássico e vazio/pulado não têm dono no estoque — no-op.

    Único lugar que sabe converter cada tipo de slot em devolução ao estoque. Ponto de
    extração (revisão final do Cancelar série): `agenda_devolver` e `series._liberar_dia`
    eram cópias verbatim desta lógica, e a divergência entre as duas cópias FOI o bug que
    o Task 1 consertou (`agenda_devolver` não tratava 'candidato', `_liberar_dia` tratava
    — o candidato vazava). As duas agora chamam esta função; um tipo de slot novo só
    precisa ser ensinado aqui uma vez. Não mexe no slot em si (não upserta, não limpa) —
    quem chama decide o que fazer com o slot depois."""
    if not slot:
        return
    tipo = slot.get("tipo")
    if tipo == "reserva" and slot.get("ref_id"):
        marcar_reserva_pronto(slot["ref_id"])
    elif tipo == "candidato" and slot.get("ref_id"):
        marcar_candidato_pronto(slot["ref_id"])
    elif tipo == "fila" and slot.get("payload"):
        import json
        import queue_store
        queue_store.devolver(json.loads(slot["payload"]))


def agenda_devolver(data):
    """Tira o item do slot e devolve ao estoque; slot vira 'vazio'. Preserva 'fixado'.
    Trata reserva/candidato/fila (via `_devolver_ao_estoque`). Se a devolução à fila
    falhar, a exceção propaga ANTES de limpar o slot — o item não é perdido (o slot
    continua apontando pra ele)."""
    s = agenda_slot(data)
    if not s:
        return
    _devolver_ao_estoque(s)
    agenda_upsert(data, tipo="vazio", fixado=s.get("fixado", 0))


def agenda_pular(data, on=True):
    """on=True: devolve item ao estoque e marca 'pulado' (preserva 'fixado').
    on=False: volta a 'vazio'."""
    if on:
        s = agenda_slot(data)
        fixado = s.get("fixado", 0) if s else 0
        agenda_devolver(data)
        agenda_upsert(data, tipo="pulado", fixado=fixado)
    else:
        agenda_upsert(data, tipo="vazio")


def _escrever_slot(data, s):
    if not s:
        agenda_upsert(data, tipo="vazio")
    else:
        agenda_upsert(data, tipo=s.get("tipo", "vazio"), ref_id=s.get("ref_id"),
                      payload=s.get("payload"), tema=s.get("tema", ""),
                      titulo=s.get("titulo", ""), fixado=s.get("fixado", 0))


def agenda_mover(data_orig, data_dest):
    """Troca (swap) os slots das duas datas. Retorna False se o destino está fixado."""
    a, b = agenda_slot(data_orig), agenda_slot(data_dest)
    if b and b.get("fixado"):
        return False
    _escrever_slot(data_orig, b)
    _escrever_slot(data_dest, a)
    return True


def agenda_ref_ids_reserva():
    """Conjunto de ref_ids de reserva referenciados por QUALQUER slot da agenda.
    Usado pela reconciliação do materializar (evita agendar o mesmo item 2x)."""
    with _conn() as c:
        rows = c.execute("SELECT ref_id FROM agenda WHERE tipo='reserva' AND ref_id IS NOT NULL").fetchall()
    return {r["ref_id"] for r in rows}


def agenda_ref_ids(tipo):
    """ref_ids de um tipo de slot (reserva/candidato/classico) — p/ a reconciliação."""
    with _conn() as c:
        rows = c.execute("SELECT ref_id FROM agenda WHERE tipo=? AND ref_id IS NOT NULL", (tipo,)).fetchall()
    return {r["ref_id"] for r in rows}


def agenda_payloads_fila():
    """Lista dos payloads (JSON cru) dos slots de fila — p/ reconciliar a fila fresca."""
    with _conn() as c:
        rows = c.execute("SELECT payload FROM agenda WHERE tipo='fila' AND payload IS NOT NULL").fetchall()
    return [r["payload"] for r in rows]


def atualizar_reserva(rid, titulo_pt=None, resumo=None, tema=None, gancho=None):
    """Edita título, resumo, tema e/ou kit de um item da reserva (curador ajusta o que a
    IA gerou). O tema vem da correção de área na tela de revisão (ver `area_estudo`); o
    gancho, da regeração do kit (`curadoria.regerar_kits`)."""
    sets, params = [], []
    if titulo_pt is not None:
        sets.append("titulo_pt=?"); params.append(titulo_pt)
    if resumo is not None:
        sets.append("resumo=?"); params.append(resumo)
    if tema is not None:
        sets.append("tema=?"); params.append(tema)
    if gancho is not None:
        sets.append("gancho=?"); params.append(gancho)
    if not sets:
        return
    params.append(rid)
    with _conn() as c:
        c.execute(f"UPDATE reserva_resumos SET {','.join(sets)} WHERE id=?", params)


def remover_reserva(rid):
    with _conn() as c:
        c.execute("DELETE FROM reserva_resumos WHERE id=?", (rid,))


# ── Rascunho do dia (persistido no banco — sobrevive a deploy/restart) ──
def salvar_draft(data, review_token, status, payload):
    from datetime import datetime
    agora = datetime.now().isoformat()
    with _conn() as c:
        c.execute(
            """INSERT INTO daily_drafts (data,review_token,status,payload,criado_em,atualizado_em)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(data) DO UPDATE SET review_token=excluded.review_token,
                 status=excluded.status, payload=excluded.payload, atualizado_em=excluded.atualizado_em""",
            (data, review_token or "", status or "DRAFT",
             json.dumps(payload, ensure_ascii=False), agora, agora))


def obter_draft(data):
    with _conn() as c:
        r = c.execute("SELECT payload FROM daily_drafts WHERE data=?", (data,)).fetchone()
    return json.loads(r["payload"]) if r and r["payload"] else None


def listar_drafts():
    """Todos os rascunhos (1 por dia). Usado pela limpeza do estoque — o estudo do dia
    já saiu da reserva e só existe aqui."""
    with _conn() as c:
        rows = c.execute("SELECT payload FROM daily_drafts").fetchall()
    return [json.loads(r["payload"]) for r in rows if r["payload"]]


def obter_draft_por_token(token):
    if not token:
        return None
    with _conn() as c:
        r = c.execute("SELECT payload FROM daily_drafts WHERE review_token=?", (token,)).fetchone()
    return json.loads(r["payload"]) if r and r["payload"] else None


def registrar_digest(art, conteudo, tmeta=None, data=None):
    """Upsert de um digest enviado (chave = data + tema_slug)."""
    from datetime import datetime
    tema = art.get("tema", "") or "Geral"
    s = slug(tema)
    d = data or datetime.now().strftime("%Y-%m-%d")
    grafico = conteudo.get("grafico")
    grafico_txt = json.dumps(grafico, ensure_ascii=False) if grafico else ""
    with _conn() as c:
        c.execute(
            """INSERT INTO digests (data,tema,tema_slug,titulo_pt,titulo_original,resumo,gancho,grafico,doi,fonte,url,criado_em)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(data,tema_slug) DO UPDATE SET
                 tema=excluded.tema, titulo_pt=excluded.titulo_pt,
                 titulo_original=excluded.titulo_original, resumo=excluded.resumo,
                 gancho=excluded.gancho, grafico=excluded.grafico, doi=excluded.doi,
                 fonte=excluded.fonte, url=excluded.url, criado_em=excluded.criado_em""",
            (d, tema, s, conteudo.get("titulo_pt", "") or art.get("titulo", ""),
             art.get("titulo_original") or art.get("titulo", ""),
             conteudo.get("resumo", ""), conteudo.get("gancho", ""), grafico_txt,
             art.get("doi", ""), art.get("fonte", ""), art.get("url", ""),
             datetime.now().isoformat()),
        )


def listar_digests():
    """Todo o arquivo do portal. Usado pela limpeza (correção retroativa do texto)."""
    with _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM digests").fetchall()]


def atualizar_digest_resumo(data, tema_slug, resumo):
    """Reescreve o resumo de UM digest publicado. A chave é (data, tema_slug), a mesma
    do upsert em `registrar_digest`."""
    with _conn() as c:
        c.execute("UPDATE digests SET resumo=? WHERE data=? AND tema_slug=?",
                  (resumo, data, tema_slug))


def digest_do_dia(data):
    """O digest ENVIADO numa data (tema/título do que saiu). 1/dia; se houver mais de um,
    retorna o mais recente. Usado p/ mostrar o histórico nos dias passados da agenda."""
    with _conn() as c:
        r = c.execute("SELECT * FROM digests WHERE data=? ORDER BY criado_em DESC LIMIT 1",
                      (data,)).fetchone()
    return dict(r) if r else None


def listar_temas():
    """Temas COM digest, ordenados como no temas_config, com contagem + rotulo/emoji/cor."""
    with _conn() as c:
        rows = c.execute("SELECT tema_slug, COUNT(*) n FROM digests GROUP BY tema_slug").fetchall()
    counts = {r["tema_slug"]: r["n"] for r in rows}
    stored_tema = {}
    with _conn() as c:
        for r in c.execute("SELECT tema_slug, tema FROM digests"):
            stored_tema.setdefault(r["tema_slug"], r["tema"])
    out = []
    seen = set()
    for nome, meta in _temas_cfg().items():
        s = slug(nome)
        if s in counts:
            out.append({"slug": s, "tema": nome, "rotulo": meta.get("rotulo", nome),
                        "emoji": meta.get("emoji", ""), "cor": meta.get("cor", "#14332a"),
                        "total": counts[s]})
            seen.add(s)
    # temas que existem no banco mas não no config (renomeados/removidos)
    for s, n in counts.items():
        if s not in seen:
            nome = stored_tema.get(s, s)
            out.append({"slug": s, "tema": nome, "rotulo": nome, "emoji": "", "cor": "#14332a", "total": n})
    return out


def _meta_por_slug(s):
    for nome, meta in _temas_cfg().items():
        if slug(nome) == s:
            return {"slug": s, "tema": nome, "rotulo": meta.get("rotulo", nome),
                    "emoji": meta.get("emoji", ""), "cor": meta.get("cor", "#14332a")}
    return {"slug": s, "tema": s, "rotulo": s, "emoji": "", "cor": "#14332a"}


def meta_tema(s):
    """Metadados do tema pelo slug (para o cabeçalho da lista/digest)."""
    return _meta_por_slug(s)


def listar_por_tema(s):
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM digests WHERE tema_slug=? ORDER BY data DESC, criado_em DESC", (s,)
        ).fetchall()
    return [dict(r) for r in rows]


def obter(s, data):
    with _conn() as c:
        r = c.execute("SELECT * FROM digests WHERE tema_slug=? AND data=?", (s, data)).fetchone()
    return dict(r) if r else None


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


def trilha_listar_pecas():
    """Todas as peças, em ordem. Alimenta a prévia do admin."""
    with _conn() as c:
        rows = c.execute("SELECT * FROM trilha_pecas ORDER BY numero").fetchall()
    return [dict(r) for r in rows]
