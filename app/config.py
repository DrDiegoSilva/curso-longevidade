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

# Número do CTA "Quero assinar" da landing (wa.me). Fallback = número do curador.
def contato_whatsapp():
    return os.environ.get("DSCURSO_CONTATO_WHATSAPP") or whatsapp_destino()

# Planos exibidos na landing. preco vazio => "sob consulta" (Diego preenche depois).
PLANOS = [
    {"nome": "Mensal",     "periodo": "por mês",       "preco": os.environ.get("DSCURSO_PRECO_MENSAL", "")},
    {"nome": "Trimestral", "periodo": "a cada 3 meses", "preco": os.environ.get("DSCURSO_PRECO_TRIMESTRAL", "")},
    {"nome": "Semestral",  "periodo": "a cada 6 meses", "preco": os.environ.get("DSCURSO_PRECO_SEMESTRAL", "")},
    {"nome": "Anual",      "periodo": "por ano",        "preco": os.environ.get("DSCURSO_PRECO_ANUAL", "")},
]

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
