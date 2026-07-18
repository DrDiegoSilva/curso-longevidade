"""
serve.py — servidor web mínimo do ebook + agendador diário (08:00 BRT).
Um processo só: serve o ebook em / e roda resumo_diario.py todo dia às 08h.
Sem dependências externas (só stdlib).
"""
import http.server, socketserver, os, sys, time, threading, subprocess
from datetime import datetime, timedelta
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo(os.environ.get("TZ", "America/Sao_Paulo"))
except Exception:
    TZ = None
import ebook_curso

PORT = int(os.environ.get("PORT", "3000"))
APPDIR = os.path.dirname(os.path.abspath(__file__))

def _now():
    return datetime.now(TZ) if TZ else datetime.now()

def agendador():
    """Dispara resumo_diario.py todo dia às 08:00 (fuso TZ). Loop simples e robusto."""
    while True:
        now = _now()
        alvo = now.replace(hour=8, minute=0, second=0, microsecond=0)
        if now >= alvo:
            alvo += timedelta(days=1)
        espera = max(60, (alvo - now).total_seconds())
        print(f"[agendador] proximo disparo {alvo:%Y-%m-%d %H:%M %Z} (em {int(espera)}s)", flush=True)
        time.sleep(espera)
        try:
            print(f"[agendador] rodando resumo_diario {_now():%Y-%m-%d %H:%M}", flush=True)
            subprocess.run([sys.executable, "resumo_diario.py"], cwd=APPDIR, timeout=1500)
        except Exception as e:
            print("[agendador] erro:", e, flush=True)

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/health", "/healthz"):
            self.send_response(200); self.send_header("Content-Type", "text/plain"); self.end_headers()
            self.wfile.write(b"ok"); return
        try:
            data = open(ebook_curso.OUT, "rb").read()
        except Exception:
            try:
                ebook_curso.gerar(); data = open(ebook_curso.OUT, "rb").read()
            except Exception as e:
                self.send_response(500); self.end_headers(); self.wfile.write(str(e).encode()); return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)
    def log_message(self, *a):
        pass

class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

if __name__ == "__main__":
    threading.Thread(target=agendador, daemon=True).start()
    print(f"[web] servindo o ebook em :{PORT}", flush=True)
    Server(("0.0.0.0", PORT), Handler).serve_forever()
