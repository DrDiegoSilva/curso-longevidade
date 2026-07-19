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

def proximo_disparo(now, horarios):
    """horarios: lista de (hora_int, nome_tarefa). Retorna (alvo_datetime, nome) mais próximo."""
    candidatos = []
    for h, nome in horarios:
        alvo = now.replace(hour=h, minute=0, second=0, microsecond=0)
        if now >= alvo:
            alvo += timedelta(days=1)
        candidatos.append((alvo, nome))
    return min(candidatos, key=lambda x: x[0])


def agendador():
    """Dois disparos diários (fuso TZ): 18h prepara+avisa o curador; 08h envia à lista."""
    import daily
    tarefas = {"preparar": daily.preparar_18h, "enviar": daily.enviar_08h}
    while True:
        now = _now().replace(tzinfo=None)
        alvo, nome = proximo_disparo(now, [(8, "enviar"), (18, "preparar")])
        espera = max(60, (alvo - now).total_seconds())
        print(f"[agendador] próximo: {nome} {alvo:%Y-%m-%d %H:%M} (em {int(espera)}s)", flush=True)
        time.sleep(espera)
        try:
            print(f"[agendador] rodando {nome} {_now():%Y-%m-%d %H:%M}", flush=True)
            tarefas[nome]()
        except Exception as e:
            print(f"[agendador] {nome} erro: {e}", flush=True)

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/health", "/healthz"):
            self.send_response(200); self.send_header("Content-Type", "text/plain"); self.end_headers()
            self.wfile.write(b"ok"); return
        if self.path.startswith("/revisar/"):
            import draft_store, review_web
            tok = self.path.split("/revisar/", 1)[1]
            r = draft_store.por_token(tok)
            return self._html(review_web.pagina_revisao(r) if r else "<h3>Link inválido/expirado</h3>", 200 if r else 404)
        if self.path.startswith("/pdf/"):
            import config, draft_store
            parts = [p for p in self.path.split("/pdf/", 1)[1].split("/") if p]
            data_iso = parts[0] if parts else ""
            if len(parts) >= 2:  # /pdf/<data>/<whatsapp> -> PDF personalizado
                fpath = os.path.join(config.drafts_dir(), f"{data_iso}-{parts[1]}.pdf")
            else:                # /pdf/<data> -> prévia do rascunho
                r = draft_store.carregar(data_iso)
                fpath = r.get("pdf_path", "") if r else ""
            if fpath and os.path.exists(fpath):
                body = open(fpath, "rb").read()
                self.send_response(200); self.send_header("Content-Type", "application/pdf"); self.end_headers()
                return self.wfile.write(body)
            return self._html("<h3>PDF não encontrado</h3>", 404)
        if self.path.startswith("/admin"):
            import urllib.parse as up, config, subscribers, review_web
            q = up.parse_qs(up.urlparse(self.path).query)
            if not config.ADMIN_TOKEN or q.get("token", [""])[0] != config.ADMIN_TOKEN:
                return self._html("<h3>Acesso negado</h3>", 403)
            return self._html(review_web.pagina_admin(subscribers.listar(), config.ADMIN_TOKEN), 200)
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
    def _html(self, s, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(s.encode("utf-8"))

    def do_POST(self):
        import urllib.parse as up
        length = int(self.headers.get("Content-Length", "0"))
        form = up.parse_qs(self.rfile.read(length).decode("utf-8"))
        g = lambda k: form.get(k, [""])[0]
        if self.path.startswith("/revisar/"):
            import draft_store
            tok = self.path.split("/revisar/", 1)[1]
            r = draft_store.por_token(tok)
            if not r:
                return self._html("<h3>Link inválido</h3>", 404)
            draft_store.aplicar(r["data"], g("acao"), g("texto"))
            return self._html("<h3>Feito ✅ Pode fechar.</h3>")
        if self.path == "/admin":
            import config, subscribers
            if not config.ADMIN_TOKEN or g("token") != config.ADMIN_TOKEN:
                return self._html("<h3>Acesso negado</h3>", 403)
            if g("acao") == "adicionar":
                subscribers.adicionar(g("nome"), g("whatsapp"))
            elif g("acao") == "remover":
                subscribers.remover(g("id"))
            return self._html("<meta http-equiv='refresh' content='0;url=/admin?token=" + config.ADMIN_TOKEN + "'>")
        return self._html("<h3>rota inválida</h3>", 404)

    def log_message(self, *a):
        pass

class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

if __name__ == "__main__":
    threading.Thread(target=agendador, daemon=True).start()
    print(f"[web] servindo o ebook em :{PORT}", flush=True)
    Server(("0.0.0.0", PORT), Handler).serve_forever()
