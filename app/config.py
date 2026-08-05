"""
config.py — Configuração central e PORTÁVEL (Windows agora, Linux/VPS depois).

Cada valor é resolvido nesta ordem: variável de ambiente  >  arquivo local atual (Windows).
- No Windows deste PC: continua tudo igual (cai no fallback dos arquivos/paths de hoje).
- No VPS (Linux): basta exportar as variáveis de ambiente abaixo; nenhum path de Windows é usado.

Variáveis no VPS:
  DSCURSO_BASE            -> pasta da base de conhecimento (aulas do curso). ex: /opt/dscurso/base
  DSCURSO_ANTHROPIC_KEY  -> chave Anthropic dedicada (sk-ant-...)
  ZAPI_INSTANCE_ID / ZAPI_INSTANCE_TOKEN / ZAPI_CLIENT_TOKEN / ZAPI_DESTINO  -> credenciais Z-API
(Opcional, se preferir manter em arquivo: DSCURSO_ANTHROPIC_FILE e DSCURSO_ZAPI_FILE apontando p/ um JSON.)
"""
import os, json

DIR = os.path.dirname(os.path.abspath(__file__))

def _json_get(path, key):
    try:
        return json.load(open(path, encoding="utf-8")).get(key)
    except Exception:
        return None

# ── Base de conhecimento (aulas do curso + destilados; fonte do ebook) ──
BASE = os.environ.get("DSCURSO_BASE") or r"D:\SSD Secundário\_BaseConhecimento"

# ── Chave Anthropic dedicada (resumos/aulas) ──
_ANTHROPIC_FILE = os.environ.get("DSCURSO_ANTHROPIC_FILE", r"C:\Users\edson\.anthropic-resumos.json")
ANTHROPIC_KEY = os.environ.get("DSCURSO_ANTHROPIC_KEY") or _json_get(_ANTHROPIC_FILE, "apiKey")

# ── Estado persistente (volume /data) ──
DATA = os.environ.get("DSCURSO_DATA") or "/data"
def drafts_dir():
    return os.path.join(DATA, "drafts")
def subscribers_path():
    return os.path.join(DATA, "subscribers.json")

# Banco do site artigos. Produção = Postgres/Supabase (DATABASE_URL);
# testes locais = SQLite (sem DATABASE_URL) — não precisa de banco no Mac.
DATABASE_URL = os.environ.get("DATABASE_URL")

def artigos_db():
    return os.environ.get("DSCURSO_ARTIGOS_DB") or os.path.join(DATA, "artigos.db")

ADMIN_TOKEN = os.environ.get("DSCURSO_ADMIN_TOKEN")
# WhatsApps de admin (Diego): logados, veem os atalhos de admin sem token. CSV na env
# (default = o número do Diego; sobrescreve com DSCURSO_ADMIN_WHATSAPP).
ADMIN_WHATSAPPS = [w for w in (os.environ.get("DSCURSO_ADMIN_WHATSAPP") or "5543996578534").replace(" ", "").split(",") if w]
PUBLIC_URL = (os.environ.get("DSCURSO_PUBLIC_URL") or "https://curso.drdiegosilva.com.br").rstrip("/")
# URL absoluta do PORTAL de assinantes (host "artigos."). Usada em links de e-mail/WhatsApp
# (webhook e recuperação de senha rodam fora de uma request → não dá pra derivar do Host).
ARTIGOS_URL = (os.environ.get("DSCURSO_ARTIGOS_URL") or "https://artigos.drdiegosilva.com.br").rstrip("/")
PRODUTO = "Atualização Científica"
SEND_DELAY_SEC = float(os.environ.get("DSCURSO_SEND_DELAY_SEC") or "4.0")

# CTA "Quero assinar" da landing → página de assinatura. Env sobrescreve.
def cta_url():
    return os.environ.get("DSCURSO_CTA_URL") or "/assinar"

# Founder pricing (D2): enquanto houver < FOUNDER_LIMITE assinantes ATIVOS, valem os preços
# de lançamento (base/preco); a partir do limite, os pós-founder (base_pos/preco_pos). Env-ajustável.
FOUNDER_LIMITE = int(os.environ.get("DSCURSO_FOUNDER_LIMITE") or 20)

# Horário de envio por assinante (slots). Assinante escolhe 1 no /meus-dados; NULL/vazio => SLOT_DEFAULT.
SLOTS = ["07h", "08h", "12h", "18h", "20h"]
SLOT_HORA = {"07h": 7, "08h": 8, "12h": 12, "18h": 18, "20h": 20}
SLOT_DEFAULT = "08h"
SLOT_TETO_DEFAULT = 100

# Trilha semanal de empreendedorismo médico (sábado, drip por assinante).
# TRILHA_NOME é provisório: o nome do produto ainda vai ser decidido. Mora aqui,
# e não espalhado no código, justamente pra troca ser um campo e não uma varredura.
TRILHA_NOME = os.environ.get("DSCURSO_TRILHA_NOME") or "Trilha do Consultório"
TRILHA_DIA = "sabado"
TRILHA_TOTAL = 12
TRILHA_DIR = os.environ.get("DSCURSO_TRILHA_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seed", "trilha")

# ── Máquina de conteúdo ──
FRESCO_DIAS = int(os.environ.get("DSCURSO_FRESCO_DIAS") or 30)   # ≤ N dias = "Estudo recente"
CLASSICO_REUSO_MESES = int(os.environ.get("DSCURSO_CLASSICO_REUSO_MESES") or 6)   # piso p/ repetir um clássico
HORA_VARREDURA = int(os.environ.get("DSCURSO_HORA_VARREDURA") or 6)   # domingo de manhã
DIA_VARREDURA = os.environ.get("DSCURSO_DIA_VARREDURA") or "domingo"

# Piso de qualidade da varredura: candidato com nota abaixo de SCORE_PISO não entra na
# curadoria. Válvula: tema que não alcançar MIN_POR_TEMA acima do piso afrouxa e entrega
# os melhores que tiver — tema seco não pode zerar.
SCORE_PISO = float(os.environ.get("DSCURSO_SCORE_PISO") or 6)
MIN_POR_TEMA = int(os.environ.get("DSCURSO_MIN_POR_TEMA") or 3)
HORA_CURADORIA = int(os.environ.get("DSCURSO_HORA_CURADORIA") or 21)   # gera os priorizados

# Planos. base = valor cheio (Pix); cycle = ciclo Asaas; recorrente_pix = mensal (Pix Automático).
# preco/nota/periodo = exibição na landing. maiores => cartão recorrente OU Pix à vista.
PLANOS = [
    # aceita_pix=False (2026-07-26): no Asaas cartão à vista recorre e cartão parcelado não —
    # mensal é sempre 1x (parcelas travado), logo é RECURRENT puro e renova sozinho; já o Pix
    # mensal nunca renovaria (cobrança mensal manual/WhatsApp todo mês). Tirar o Pix tira o
    # mensal inteiro da régua. Diego confirmou: não existe assinante mensal pago via Pix hoje.
    {"slug": "mensal",      "nome": "Mensal",     "periodo": "por mês",        "base": 147.0,  "cycle": "MONTHLY",      "recorrente_pix": True,  "preco": "R$ 147",  "nota": "", "base_pos": 147.0, "preco_pos": "R$ 147", "aceita_pix": False},
    # Trimestral/Semestral OCULTOS da venda (decisão do Diego 2026-07-20: só Mensal e Anual).
    # Mantidos na lista p/ o backend ainda resolver esses ciclos de assinantes antigos (plano_por_cycle/base).
    {"slug": "trimestral",  "nome": "Trimestral", "periodo": "a cada 3 meses", "base": 269.0, "cycle": "QUARTERLY",    "recorrente_pix": False, "preco": "R$ 269", "nota": "≈ R$ 90/mês", "oculto": True},
    {"slug": "semestral",   "nome": "Semestral",  "periodo": "a cada 6 meses", "base": 499.0, "cycle": "SEMIANNUALLY", "recorrente_pix": False, "preco": "R$ 499", "nota": "≈ R$ 83/mês", "oculto": True},
    {"slug": "anual",       "nome": "Anual",      "periodo": "por ano",        "base": 1497.0, "cycle": "YEARLY",       "recorrente_pix": False, "preco": "R$ 1.497", "nota": "≈ R$ 125/mês · em até 12x sem juros", "pix_desconto_pct": 5, "base_pos": 1497.0, "preco_pos": "R$ 1.497", "nota_pos": "≈ R$ 125/mês · em até 12x sem juros"},
    # Plano de TESTE (R$5) — OCULTO da landing; só via link direto /assinar?plano=teste. Pagar por Pix (à vista).
    {"slug": "teste",       "nome": "Teste",      "periodo": "pagamento único", "base": 5.0,  "cycle": "MONTHLY",      "recorrente_pix": False, "preco": "R$ 5",   "nota": "plano de teste", "oculto": True},
]

def parse_preco(s):
    """Número > 0 com no máx. 2 casas (aceita vírgula ou ponto). None se inválido.
    Rejeita não-finitos ("inf", "Infinity", "1e400" etc.) — float()/round() não
    levantam erro nesses casos e float('inf') > 0 é True."""
    import math
    if s is None:
        return None
    try:
        v = round(float(str(s).replace(",", ".").strip()), 2)
    except (TypeError, ValueError):
        return None
    return v if v > 0 and math.isfinite(v) else None


def _preco_str(base):
    """Estilo 'R$ 1.497' (sem centavos, milhar com '.')."""
    return "R$ " + f"{float(base):,.0f}".replace(",", ".")


def _nota_derivada(slug, base):
    if slug == "anual":
        return f"≈ R$ {round(float(base) / 12)}/mês · em até 12x sem juros"
    return ""


def _preco_override(slug):
    """Override salvo em settings (float > 0) ou None. Defensivo: qualquer falha -> None."""
    try:
        import db
        return parse_preco(db.get_config(f"preco_base_{slug}", ""))
    except Exception:
        return None


def _aplicar_override(plano):
    """CÓPIA do plano com base/base_pos e textos derivados do override (se houver).
    Sem override -> cópia com os valores do código (nunca muta PLANOS).

    `base_padrao` guarda o preço de LANÇAMENTO (o `base` do código, antes de qualquer
    override) em toda cópia resolvida, com ou sem override ativo. É o que
    `renovacao.preco_renovacao` usa como fallback para assinantes legado — sem isso, um
    aumento de preço pelo admin vazaria pra renovação de quem já era assinante."""
    p = dict(plano)
    p["base_padrao"] = float(plano["base"])
    ov = _preco_override(plano["slug"])
    if ov is None:
        return p
    p["base"] = ov
    p["preco"] = _preco_str(ov)
    p["nota"] = _nota_derivada(plano["slug"], ov)
    if "base_pos" in plano:
        p["base_pos"] = ov
        p["preco_pos"] = _preco_str(ov)
    if "nota_pos" in plano:
        p["nota_pos"] = _nota_derivada(plano["slug"], ov)
    return p


def plano_por_slug(slug):
    for p in PLANOS:
        if p["slug"] == slug:
            return _aplicar_override(p)
    return None


def planos_venda():
    """Planos visíveis (não ocultos) com o preço vigente (override aplicado). P/ a landing."""
    return [_aplicar_override(p) for p in PLANOS if not p.get("oculto")]


def plano_por_cycle(cycle):
    for p in PLANOS:
        if p["cycle"] == cycle:
            return p
    return None


def plano_por_base(valor):
    """Casa o valor pago com a base VIGENTE do plano (override aplicado)."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    for p in PLANOS:
        pr = _aplicar_override(p)
        if abs(float(pr["base"]) - v) < 0.01:
            return pr
    return None

# ── Asaas (checkout hospedado + webhook) ──
ASAAS_BASE_URL = (os.environ.get("ASAAS_BASE_URL") or "https://api-sandbox.asaas.com/v3").rstrip("/")
ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY")
ASAAS_WEBHOOK_TOKEN = os.environ.get("ASAAS_WEBHOOK_TOKEN")

# [NÃO APLICADAS desde D1 2026-07-23 — cartão é SEM JUROS: pricing.valor_cartao cobra o valor base.]
# Mantidas p/ referência/reverter o gross-up. Taxas antigas do Diego: 3x=7%, 6x=10%, 12x=12%.
TAXA_CARTAO = {"avista": 0.0299, "ate3": 0.07, "ate6": 0.10, "ate12": 0.12}
TAXA_FIXA = float(os.environ.get("DSCURSO_TAXA_FIXA") or "0.49")

# Cupons de cortesia (cadastro grátis, sem Asaas): csv em DSCURSO_CUPONS.
def cupons_seed():
    return [c.strip().upper() for c in (os.environ.get("DSCURSO_CUPONS") or "").split(",") if c.strip()]

# ── Áudio (OpenAI TTS): roteiro falado + narração. Sem chave => áudio desligado. ──
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
TTS_MODEL = os.environ.get("DSCURSO_TTS_MODEL") or "tts-1-hd"
TTS_VOICE = os.environ.get("DSCURSO_TTS_VOICE") or "onyx"


def audio_ligado():
    """Envia áudio junto com o estudo? Precisa da chave OpenAI e não estar desligado."""
    return bool(OPENAI_API_KEY) and (os.environ.get("DSCURSO_AUDIO") or "1") != "0"


# ── E-mail (Resend — já usado no ecossistema do Diego). Sem chave => só loga. ──
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
EMAIL_FROM = os.environ.get("DSCURSO_EMAIL_FROM") or "Atualização Científica <nao-responda@drdiegosilva.com.br>"
EMAIL_BACKEND = (os.environ.get("DSCURSO_EMAIL_BACKEND") or ("resend" if RESEND_API_KEY else "none")).lower()

# E-mail do admin (Dr. Diego) para avisos de venda. Env sobrescreve.
ADMIN_EMAIL = os.environ.get("DSCURSO_ADMIN_EMAIL") or "contato@drdiegosilva.com.br"

# ── Z-API (WhatsApp) ──
_ZAPI_FILE = os.environ.get("DSCURSO_ZAPI_FILE", r"C:\Users\edson\.zapi-config.json")
def zapi():
    return {
        "instanceId":    os.environ.get("ZAPI_INSTANCE_ID")    or _json_get(_ZAPI_FILE, "instanceId"),
        "instanceToken": os.environ.get("ZAPI_INSTANCE_TOKEN") or _json_get(_ZAPI_FILE, "instanceToken"),
        "clientToken":   os.environ.get("ZAPI_CLIENT_TOKEN")   or _json_get(_ZAPI_FILE, "clientToken"),
        "destinoNumero": os.environ.get("ZAPI_DESTINO")        or _json_get(_ZAPI_FILE, "destinoNumero"),
    }

# ── WhatsApp backend (evolution | zapi) ──
WHATSAPP_BACKEND = (os.environ.get("WHATSAPP_BACKEND") or "zapi").lower()

def evolution():
    return {
        "url":      (os.environ.get("EVOLUTION_URL") or "").rstrip("/"),
        "instance": os.environ.get("EVOLUTION_INSTANCE"),
        "apikey":   os.environ.get("EVOLUTION_APIKEY"),
    }

def whatsapp_destino():
    """Número do curador (Dr. Diego) para o aviso das 18h."""
    return (os.environ.get("WHATSAPP_DESTINO")
            or os.environ.get("ZAPI_DESTINO")
            or _json_get(_ZAPI_FILE, "destinoNumero"))
