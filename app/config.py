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

# Banco do site artigos (landing + arquivo protegido). Env sobrescreve → testável em /tmp.
def artigos_db():
    return os.environ.get("DSCURSO_ARTIGOS_DB") or os.path.join(DATA, "artigos.db")

ADMIN_TOKEN = os.environ.get("DSCURSO_ADMIN_TOKEN")
PUBLIC_URL = (os.environ.get("DSCURSO_PUBLIC_URL") or "https://curso.drdiegosilva.com.br").rstrip("/")
SEND_DELAY_SEC = float(os.environ.get("DSCURSO_SEND_DELAY_SEC") or "4.0")

# CTA "Quero assinar" da landing → página de assinatura. Env sobrescreve.
def cta_url():
    return os.environ.get("DSCURSO_CTA_URL") or "/assinar"

# Planos. base = valor cheio (Pix); cycle = ciclo Asaas; recorrente_pix = mensal (Pix Automático).
# preco/nota/periodo = exibição na landing. maiores => cartão recorrente OU Pix à vista.
PLANOS = [
    {"slug": "mensal",      "nome": "Mensal",     "periodo": "por mês",        "base": 99.0,  "cycle": "MONTHLY",      "recorrente_pix": True,  "preco": "R$ 99",  "nota": ""},
    {"slug": "trimestral",  "nome": "Trimestral", "periodo": "a cada 3 meses", "base": 269.0, "cycle": "QUARTERLY",    "recorrente_pix": False, "preco": "R$ 269", "nota": "≈ R$ 90/mês"},
    {"slug": "semestral",   "nome": "Semestral",  "periodo": "a cada 6 meses", "base": 499.0, "cycle": "SEMIANNUALLY", "recorrente_pix": False, "preco": "R$ 499", "nota": "≈ R$ 83/mês"},
    {"slug": "anual",       "nome": "Anual",      "periodo": "por ano",        "base": 960.0, "cycle": "YEARLY",       "recorrente_pix": False, "preco": "R$ 960", "nota": "≈ R$ 80/mês · melhor preço"},
]

def plano_por_slug(slug):
    for p in PLANOS:
        if p["slug"] == slug:
            return p
    return None

# ── Asaas (checkout hospedado + webhook) ──
ASAAS_BASE_URL = (os.environ.get("ASAAS_BASE_URL") or "https://api-sandbox.asaas.com/v3").rstrip("/")
ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY")
ASAAS_WEBHOOK_TOKEN = os.environ.get("ASAAS_WEBHOOK_TOKEN")

# Taxas de cartão (defaults Asaas; Diego troca pelas reais). gross-up embute a taxa no preço.
TAXA_CARTAO = {"avista": 0.0299, "ate6": 0.0349, "ate12": 0.0399}
TAXA_FIXA = float(os.environ.get("DSCURSO_TAXA_FIXA") or "0.49")

# Cupons de cortesia (cadastro grátis, sem Asaas): csv em DSCURSO_CUPONS.
def cupons_seed():
    return [c.strip().upper() for c in (os.environ.get("DSCURSO_CUPONS") or "").split(",") if c.strip()]

# ── E-mail (Resend — já usado no ecossistema do Diego). Sem chave => só loga. ──
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
EMAIL_FROM = os.environ.get("DSCURSO_EMAIL_FROM") or "Atualização Científica <nao-responda@drdiegosilva.com.br>"
EMAIL_BACKEND = (os.environ.get("DSCURSO_EMAIL_BACKEND") or ("resend" if RESEND_API_KEY else "none")).lower()

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
