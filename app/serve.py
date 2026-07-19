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
    # host começa com "artigos" -> modo site (produto); senão -> ebook (curso.)
    def _site(self):
        return self.headers.get("Host", "").lower().startswith("artigos")

    def _sessao(self):
        import auth_web
        return auth_web.sessao(self.headers.get("Cookie", ""))

    def _cookie(self, token):
        return f"sid={token}; HttpOnly; Path=/; Max-Age=2592000; SameSite=Lax; Secure"

    def _redirect(self, location, token=None, clear=False):
        self.send_response(302)
        self.send_header("Location", location)
        if token is not None:
            self.send_header("Set-Cookie", self._cookie(token))
        if clear:
            self.send_header("Set-Cookie", "sid=; HttpOnly; Path=/; Max-Age=0; SameSite=Lax; Secure")
        self.end_headers()

    def do_GET(self):
        import urllib.parse as up
        path = up.urlparse(self.path).path
        if path in ("/health", "/healthz"):
            self.send_response(200); self.send_header("Content-Type", "text/plain"); self.end_headers()
            self.wfile.write(b"ok"); return
        if path == "/robots.txt":
            import site_web
            body = site_web.robots_txt() if self._site() else "User-agent: *\nAllow: /\n"
            self.send_response(200); self.send_header("Content-Type", "text/plain; charset=utf-8"); self.end_headers()
            self.wfile.write(body.encode("utf-8")); return
        if path.startswith("/revisar/"):
            import draft_store, review_web
            tok = path.split("/revisar/", 1)[1]
            r = draft_store.por_token(tok)
            return self._html(review_web.pagina_revisao(r) if r else "<h3>Link inválido/expirado</h3>", 200 if r else 404)
        if path.startswith("/pdf/"):
            import config, draft_store
            parts = [p for p in path.split("/pdf/", 1)[1].split("/") if p]
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
        if path.startswith("/admin"):
            import config, subscribers, review_web
            q = up.parse_qs(up.urlparse(self.path).query)
            if not config.ADMIN_TOKEN or q.get("token", [""])[0] != config.ADMIN_TOKEN:
                return self._html("<h3>Acesso negado</h3>", 403)
            return self._html(review_web.pagina_admin(subscribers.listar(), config.ADMIN_TOKEN), 200)
        if self._site():
            return self._site_get(path)
        # fallback: ebook (host curso./demais) — comportamento original
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

    def _site_get(self, path):
        import site_web, db
        if path == "/":
            return self._html(site_web.landing())
        if path == "/assinar":
            import urllib.parse as up
            plano = up.parse_qs(up.urlparse(self.path).query).get("plano", [None])[0]
            return self._html(site_web.pagina_assinar(plano))
        if path == "/obrigado":
            return self._html(site_web.pagina_obrigado())
        if path == "/entrar":
            return self._html(site_web.pagina_entrar("numero"))
        if path == "/sair":
            import auth_web
            auth_web.logout(auth_web._parse_cookie(self.headers.get("Cookie", "")).get("sid"))
            return self._redirect("/", clear=True)
        if path == "/minha":
            sub = self._sessao()
            if not sub:
                return self._redirect("/entrar")
            return self._html(site_web.pagina_minha(sub))
        parts = [p for p in path.split("/") if p]
        if parts and parts[0] == "artigos":
            sub = self._sessao()
            if not sub:
                return self._redirect("/entrar")
            if len(parts) == 1:
                return self._html(site_web.hub_temas(db.listar_temas()))
            slug = parts[1]
            if len(parts) == 2:
                return self._html(site_web.lista_tema(db.meta_tema(slug), db.listar_por_tema(slug)))
            d = db.obter(slug, parts[2])
            if not d:
                return self._html("<h3>Edição não encontrada</h3>", 404)
            return self._html(site_web.pagina_digest(db.meta_tema(slug), d))
        return self._html("<h3>Página não encontrada</h3>", 404)

    def _html(self, s, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(s.encode("utf-8"))

    def do_POST(self):
        import urllib.parse as up
        path = up.urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b""
        if path == "/webhook/asaas":       # Asaas envia JSON (não form-urlencoded)
            import webhook_asaas, json as _json
            try:
                body = _json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                return self._html("bad json", 400)
            st, msg = webhook_asaas.processar(body, self.headers.get("asaas-access-token"))
            return self._html(msg, st)
        form = up.parse_qs(raw.decode("utf-8"))
        g = lambda k: form.get(k, [""])[0]
        if path.startswith("/revisar/"):
            import draft_store
            tok = path.split("/revisar/", 1)[1]
            r = draft_store.por_token(tok)
            if not r:
                return self._html("<h3>Link inválido</h3>", 404)
            draft_store.aplicar(r["data"], g("acao"), g("texto"))
            return self._html("<h3>Feito ✅ Pode fechar.</h3>")
        if path == "/admin":
            import config, subscribers
            if not config.ADMIN_TOKEN or g("token") != config.ADMIN_TOKEN:
                return self._html("<h3>Acesso negado</h3>", 403)
            if g("acao") == "adicionar":
                subscribers.adicionar(g("nome"), g("whatsapp"))
            elif g("acao") == "remover":
                subscribers.remover(g("id"))
            return self._html("<meta http-equiv='refresh' content='0;url=/admin?token=" + config.ADMIN_TOKEN + "'>")
        if path == "/entrar":
            import site_web, auth_web
            wpp = g("whatsapp")
            if g("etapa") == "codigo":
                token = auth_web.verificar(wpp, g("codigo"))
                if token:
                    return self._redirect("/artigos", token=token)
                return self._html(site_web.pagina_entrar("codigo", whatsapp=wpp,
                                  erro="Código inválido ou expirado. Tente novamente."))
            auth_web.iniciar_login(wpp)  # neutro: só envia se for assinante ATIVO
            return self._html(site_web.pagina_entrar("codigo", whatsapp=wpp))
        if path == "/assinar":
            return self._post_assinar(g)
        return self._html("<h3>rota inválida</h3>", 404)

    def _post_assinar(self, g):
        import site_web, config, db, subscribers, pricing, asaas
        plano = config.plano_por_slug(g("plano"))
        if not plano:
            return self._html(site_web.pagina_assinar(None, "Plano inválido — escolha de novo."), 400)
        dados = {"nome": g("nome").strip(), "email": g("email").strip(),
                 "cpf": g("cpf").strip(), "whatsapp": g("whatsapp").strip()}
        if not (dados["nome"] and dados["whatsapp"] and dados["email"]):
            return self._html(site_web.pagina_assinar(plano["slug"], "Preencha nome, e-mail e WhatsApp."))
        metodo = "CARTAO" if g("metodo").upper() == "CARTAO" else "PIX"
        try:
            parcelas = max(1, min(12, int(g("parcelas") or "1")))
        except ValueError:
            parcelas = 1
        cupom = g("cupom").strip()
        # Cupom de cortesia: ativa na hora, sem Asaas
        if cupom and db.cupom_valido(cupom):
            subscribers.criar_de_pagamento({**dados, "plano": plano["slug"], "metodo": "CUPOM"}, {}, status="ATIVO")
            try:
                import deliver
                deliver.enviar_texto(subscribers._norm(dados["whatsapp"]),
                    f"✅ Cadastro liberado (cortesia)! Bem-vindo(a) à Atualização Científica.\n\n"
                    f"Entre em {config.PUBLIC_URL}/entrar com este WhatsApp e peça o código.")
            except Exception as e:
                print(f"[assinar] boas-vindas cupom falhou: {e}", flush=True)
            return self._redirect("/obrigado")
        # Pagamento via checkout Asaas
        valor = pricing.valor_cartao(plano["base"], parcelas) if metodo == "CARTAO" else float(plano["base"])
        token = db.criar_pending({**dados, "plano": plano["slug"], "metodo": metodo,
                                  "parcelas": parcelas, "valor": valor})
        try:
            payload = asaas.montar_checkout(plano, metodo, parcelas, dados, token, config.PUBLIC_URL)
            res = asaas.criar_checkout(payload)
            if not res.get("url"):
                raise RuntimeError("checkout sem url")
            return self._redirect(res["url"])
        except Exception as e:
            print(f"[assinar] checkout falhou: {e}", flush=True)
            return self._html(site_web.pagina_assinar(plano["slug"],
                "Não conseguimos iniciar o pagamento agora. Tente novamente em instantes."))

    def log_message(self, *a):
        pass

class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

if __name__ == "__main__":
    try:
        import db
        db.init()
    except Exception as e:
        print(f"[web] db.init falhou: {e}", flush=True)
    threading.Thread(target=agendador, daemon=True).start()
    print(f"[web] servindo ebook (curso.) + site artigos (artigos.) em :{PORT}", flush=True)
    Server(("0.0.0.0", PORT), Handler).serve_forever()
