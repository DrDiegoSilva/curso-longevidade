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

# ── Z-API (WhatsApp) ──
_ZAPI_FILE = os.environ.get("DSCURSO_ZAPI_FILE", r"C:\Users\edson\.zapi-config.json")
def zapi():
    return {
        "instanceId":    os.environ.get("ZAPI_INSTANCE_ID")    or _json_get(_ZAPI_FILE, "instanceId"),
        "instanceToken": os.environ.get("ZAPI_INSTANCE_TOKEN") or _json_get(_ZAPI_FILE, "instanceToken"),
        "clientToken":   os.environ.get("ZAPI_CLIENT_TOKEN")   or _json_get(_ZAPI_FILE, "clientToken"),
        "destinoNumero": os.environ.get("ZAPI_DESTINO")        or _json_get(_ZAPI_FILE, "destinoNumero"),
    }
