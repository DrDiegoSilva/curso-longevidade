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


def _destino_seguro(destino):
    """Valida o `destino` do form de /aceitar-termos antes de usá-lo num redirect.

    Só aceita caminho relativo ao próprio site (começa com "/" e não sai dele). Cai
    no padrão "/minha" quando `destino`:
    - não começa com "/";
    - começa com "//" ou "/\\" — o navegador trata "\\" como "/" na resolução de URL,
      então "/\\evil.com" também resolve pro host evil.com (mesma família de bug do
      "//evil.com", só que com barra invertida);
    - contém "\\r", "\\n" ou "\\t" — CR/LF é response splitting (`send_header` do
      `http.server` não valida CRLF no valor do header, então injetaria headers/corpo
      extras, ex.: um Set-Cookie forjado). O TAB entra na mesma regra porque o parser
      de URL do WHATWG REMOVE tab/CR/LF de qualquer posição antes de resolver: sem
      isso, "/\\t/evil.com" passaria aqui e o navegador leria "//evil.com";
    - tem caractere fora de latin-1 — `send_header` codifica o valor em latin-1
      estrito, e um caractere fora dessa faixa derrubava a resposta inteira com
      UnicodeEncodeError em vez de cair no padrão.
    """
    destino = destino or "/minha"
    if not destino.startswith("/"):
        return "/minha"
    if len(destino) > 1 and destino[1] in ("/", "\\"):
        return "/minha"
    if "\r" in destino or "\n" in destino or "\t" in destino:
        return "/minha"
    try:
        destino.encode("latin-1")
    except UnicodeEncodeError:
        return "/minha"
    return destino


def _pct_str(pct):
    """Percentual pra exibição: 10.0 -> "10%", 7.5 -> "7,5%" (vírgula decimal, sem
    zeros à direita). Usado na mensagem da prévia do cupom de AFILIADO, cujo desconto
    é % (o promocional é R$ e usa `pricing.fmt_brl`)."""
    return ("%g" % float(pct)).replace(".", ",") + "%"


def _trilha_numero_valido(numero_str):
    """Converte um `numero` (form do POST /trilha OU segmento de URL da rota GET
    /admin/trilha/peca/<n>) num inteiro de peça válido (1..config.TRILHA_TOTAL), ou
    devolve 0 se não for. Único ponto de verdade pras duas rotas -- nenhuma delas
    tem permissão de validar `numero` por conta própria.

    A faixa é checada AQUI, antes de qualquer valor chegar em `db.trilha_marcar_feito`
    ou `db.trilha_peca`: `int()` do Python não estoura com uma string de dezenas de
    dígitos (inteiro de precisão arbitrária), mas o `sqlite3` estoura ao tentar
    converter esse Python int pra INTEGER de 64 bits do SQLite (`OverflowError:
    Python int too large to convert to SQLite INTEGER`), sem try/except no caminho do
    banco — qualquer requisição (form OU URL) conseguiria derrubar a resposta só
    mandando um número gigante. Preferimos rejeitar aqui (peça inválida vira 0,
    silenciosamente ignorada) a deixar a exceção subir."""
    import config
    try:
        numero = int(numero_str or 0)
    except ValueError:
        return 0
    return numero if 1 <= numero <= config.TRILHA_TOTAL else 0


def agendador():
    """Dispara o envio em CADA slot (config.SLOTS) + prepara às 18h. Fuso TZ.
    08h: pré-renovação + envio do slot 08h. 18h: prepara amanhã + envia o slot 18h."""
    import daily, config, trilha

    def _trilha_tick(sl):
        """Sábado: manda a peça da trilha nesse slot. Dia útil: no-op.
        Fica FORA de daily.enviar_slot de propósito — o motor do estudo não muda."""
        try:
            trilha.enviar_slot(sl)
        except Exception as e:
            print(f"[trilha] slot {sl} erro: {e}", flush=True)

    def _rotina08():
        daily.rotina_08h()      # régua + estudo (o estudo é no-op no sábado)
        _trilha_tick("08h")

    def _prep_e_18h():
        daily.enviar_slot("18h")   # envia HOJE 1º (independente da preparação de amanhã, que pode falhar)
        _trilha_tick("18h")
        daily.preparar_18h()       # prepara amanhã (o try/except do loop do agendador cobre se falhar)
    tarefas = {"rotina08": _rotina08, "prep18": _prep_e_18h,
               "varredura_semanal": daily.varredura_semanal,
               "gerar_curadoria": daily.gerar_selecionados_noturno}
    for s in config.SLOTS:
        if s not in ("08h", "18h"):
            tarefas[f"slot:{s}"] = (lambda sl=s: (daily.enviar_slot(sl), _trilha_tick(sl)))
    # (hora, nome) — 08h e 18h têm tarefas especiais; os demais slots enviam direto.
    horarios = []
    for s in config.SLOTS:
        h = config.SLOT_HORA[s]
        if s == "08h":
            horarios.append((h, "rotina08"))
        elif s == "18h":
            horarios.append((h, "prep18"))
        else:
            horarios.append((h, f"slot:{s}"))
    horarios.append((config.HORA_VARREDURA, "varredura_semanal"))   # self-gate: só domingo, 1x/semana
    horarios.append((config.HORA_CURADORIA, "gerar_curadoria"))   # gera os priorizados
    while True:
        now = _now().replace(tzinfo=None)
        alvo, nome = proximo_disparo(now, horarios)
        espera = max(60, (alvo - now).total_seconds())
        print(f"[agendador] próximo: {nome} {alvo:%Y-%m-%d %H:%M} (em {int(espera)}s)", flush=True)
        time.sleep(espera)
        try:
            print(f"[agendador] rodando {nome} {_now():%Y-%m-%d %H:%M}", flush=True)
            tarefas[nome]()
        except Exception as e:
            print(f"[agendador] {nome} erro: {e}", flush=True)

AVISO_JA_RECORRENTE = ("Sua assinatura já renova automaticamente no cartão — não há "
                       "nada a pagar aqui. Na data do vencimento a cobrança sai sozinha. "
                       "Se quiser interromper, use a opção de cancelar a renovação.")


class Handler(http.server.BaseHTTPRequestHandler):
    timeout = 20          # tempo-limite de socket: conexão lenta/pendurada cai em vez de segurar a thread

    # host começa com "artigos" -> modo site (produto); senão -> ebook (curso.)
    def _site(self):
        return self.headers.get("Host", "").lower().startswith("artigos")

    def _rate_ok(self, nome, maximo, janela_seg):
        """Rate-limit por IP nos endpoints sensíveis (login/OTP/recuperação). Se estourar,
        já responde 429 e retorna False -> o handler deve dar `return`.
        Chaveia por `_ip_cliente()` (não por `client_address`): atrás do proxy
        reverso deste deploy, `client_address` é o IP do PRÓPRIO PROXY, idêntico pra
        todo visitante — chavear por ele juntava todo mundo num balde só (os 5
        códigos de OTP por 10 min viravam 5 códigos pro site inteiro, e uma pessoa
        exaurindo a cota trancava o login de todo mundo). `_ip_cliente()` lê o
        último elemento do X-Forwarded-For (escrito pelo proxy, não forjável pelo
        cliente), com fallback pro `client_address` se o cabeçalho vier ausente."""
        import rate_limit
        ip = self._ip_cliente()
        if rate_limit.limitado(f"{nome}:{ip}", maximo, janela_seg):
            self._html("<h3>Muitas tentativas. Aguarde alguns minutos e tente de novo.</h3>", 429)
            return False
        return True

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

    def _ip_cliente(self):
        """IP real do cliente, mesmo atrás do proxy reverso (Traefik, neste deploy).
        O proxy ANEXA o IP real ao fim do X-Forwarded-For que o cliente mandar: um
        cliente que envia 'X-Forwarded-For: 1.2.3.4' chega aqui como
        '1.2.3.4, <ip-real>'. Pegar o PRIMEIRO elemento (bug corrigido aqui) devolve
        um valor que o próprio cliente escolhe — forjável à vontade, request a
        request. Só o ÚLTIMO elemento não-vazio é o hop que o cliente não controla;
        correto tanto com proxy que ANEXA quanto com proxy que SUBSTITUI (cabeçalho
        de 1 elemento só) e cai no `client_address` se o cabeçalho vier ausente,
        vazio, só espaço, ou com um elemento final vazio (vírgula sobrando).
        Único ponto de verdade: usado tanto pelo limite de tentativas de cupom
        (`_post_assinar`) quanto pelo registro de aceite dos Termos
        (`_aceitar_termos`, onde o IP é evidência legal do aceite).

        Lê TODAS as linhas do cabeçalho, não só a primeira (Minor da revisão final):
        `headers.get()` devolve só a 1ª ocorrência, então um cliente que manda
        'X-Forwarded-For: 1.2.3.4' numa linha própria fazia o valor ESCOLHIDO por ele
        voltar a ser o resultado (o valor do proxy ficava na 2ª linha, ignorada) — o
        limite e o IP do aceite voltavam a ser forjáveis. Pelo RFC 9110, várias linhas
        do mesmo cabeçalho equivalem a uma só lista separada por vírgula, na ordem
        recebida: concatenar as linhas e pegar o último elemento não-vazio é o mesmo
        último hop nos dois formatos. `get_all` só existe no `HTTPMessage` real —
        stubs de teste usam `dict`, daí o fallback pro `get`."""
        get_all = getattr(self.headers, "get_all", None)
        linhas = (get_all("X-Forwarded-For") if get_all else None) or \
            [self.headers.get("X-Forwarded-For", "")]
        partes = [p.strip() for linha in linhas for p in (linha or "").split(",")]
        validas = [p for p in partes if p]
        if validas:
            return validas[-1]
        # guard restaurado (Minor da revisão final): perdido na mudança de `_rate_ok`
        # pra cá. `client_address` é vazio/None quando o socket já caiu — sem o guard,
        # um IndexError/TypeError derruba a resposta em vez de degradar pra "?".
        return self.client_address[0] if self.client_address else "?"

    def _mesma_origem(self):
        """False quando a requisição veio declaradamente de OUTRA origem.

        Usado só na prévia do cupom (`POST /assinar/cupom`), que existe exclusivamente
        pro fetch da própria página /assinar. Fecha o amplificador apontado na revisão
        final: o endpoint aceita `application/x-www-form-urlencoded`, que não dispara
        preflight, então QUALQUER página de terceiro conseguia — do navegador do
        visitante, em silêncio — queimar a cota de tentativas de cupom DELE e fazer o
        cupom bom dele ser recusado no fechamento. `Origin` é setado pelo navegador em
        todo POST via fetch (inclusive same-origin) e não é forjável por script.

        NÃO afeta o caminho sem JS: sem JS o formulário inteiro vai pro `/assinar`
        normal, que não passa por aqui (e continua sem checagem de origem — mudar o
        gate da rota de compra é decisão do dono, não efeito colateral deste fix).

        Ausência dos DOIS cabeçalhos libera (fail-open) DE PROPÓSITO: se algum proxy
        removesse `Origin` e `Referer`, fail-closed desligaria a prévia pra todo mundo,
        e um atacante sem navegador (curl) nunca precisou do IP da vítima — o ataque
        que este gate fecha é justamente o que EXIGE o navegador dela."""
        import urllib.parse as up
        host = (self.headers.get("Host") or "").strip().lower()
        for cab in ("Origin", "Referer"):
            valor = (self.headers.get(cab) or "").strip()
            if valor:
                # "Origin: null" (iframe sandbox, alguns redirects) tem netloc "" ->
                # não casa com host nenhum -> recusado, que é o certo.
                return up.urlparse(valor).netloc.lower() == host
        return True

    def do_GET(self):
        import urllib.parse as up
        path = up.urlparse(self.path).path
        if path in ("/health", "/healthz"):
            self.send_response(200); self.send_header("Content-Type", "text/plain"); self.end_headers()
            self.wfile.write(b"ok"); return
        if path in ("/favicon.ico", "/favicon.svg"):
            import site_web
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
            self.send_header("Cache-Control", "public, max-age=604800")
            self.end_headers()
            self.wfile.write(site_web.FAVICON_SVG.encode("utf-8")); return
        if path == "/robots.txt":
            import site_web
            body = site_web.robots_txt() if self._site() else "User-agent: *\nAllow: /\n"
            self.send_response(200); self.send_header("Content-Type", "text/plain; charset=utf-8"); self.end_headers()
            self.wfile.write(body.encode("utf-8")); return
        if path.startswith("/revisar/"):
            import area_estudo, config, draft_store, review_web
            tok = path.split("/revisar/", 1)[1]
            r = draft_store.por_token(tok)
            if not r:
                return self._html("<h3>Link inválido/expirado</h3>", 404)
            return self._html(review_web.pagina_revisao(r, audio_on=config.audio_ligado(),
                                                        areas=area_estudo.areas()), 200)
        if path.startswith("/pdf/"):
            import config, draft_store
            parts = [p for p in path.split("/pdf/", 1)[1].split("/") if p]
            data_iso = parts[0] if parts else ""
            if len(parts) >= 2:  # /pdf/<data>/<whatsapp> -> PDF personalizado
                fpath = os.path.join(config.drafts_dir(), f"{data_iso}-{parts[1]}.pdf")
            else:                # /pdf/<data> -> prévia do rascunho
                r = draft_store.carregar(data_iso)
                fpath = r.get("pdf_path", "") if r else ""
                if r and (not fpath or not os.path.exists(fpath)):
                    try:                # /data é efêmero: regenera a prévia do rascunho persistido
                        import pdf as pdfmod, daily
                        art = r["artigo"]
                        conteudo = {"titulo_pt": r.get("titulo_pt") or art.get("titulo", ""),
                                    "resumo": r.get("resumo", ""), "gancho": r.get("gancho", ""),
                                    "grafico": r.get("grafico")}
                        fpath = os.path.join(config.drafts_dir(), f"{data_iso}-preview.pdf")
                        os.makedirs(config.drafts_dir(), exist_ok=True)
                        pdfmod.gerar_pdf(pdfmod.montar_html(art, conteudo,
                                         daily._tema_meta(art.get("tema", ""))), fpath)
                        # Grava o caminho: sem isto o rascunho fica "sempre inválido" e cada
                        # clique em "Ver PDF" paga um Chromium. Vira o estado normal de todo
                        # rascunho com a área corrigida (`area_estudo` zera o pdf_path).
                        r["pdf_path"] = fpath
                        draft_store.salvar(r)
                    except Exception as e:
                        print(f"[pdf] regen preview falhou: {e}", flush=True)
            if fpath and os.path.exists(fpath):
                body = open(fpath, "rb").read()
                self.send_response(200); self.send_header("Content-Type", "application/pdf"); self.end_headers()
                return self.wfile.write(body)
            return self._html("<h3>PDF não encontrado</h3>", 404)
        if path == "/admin/whatsapp":
            import config, site_web, auth_web, evolution_admin
            q = up.parse_qs(up.urlparse(self.path).query)
            sess = self._sessao()
            token_ok = bool(config.ADMIN_TOKEN) and q.get("token", [""])[0] == config.ADMIN_TOKEN
            if not (token_ok or (sess and auth_web.eh_admin(sess["whatsapp"]))):
                return self._html("<h3>Acesso negado</h3>", 403)
            inf = evolution_admin.info()
            conn = evolution_admin.conectar() if inf.get("estado") != "open" else None
            return self._html(site_web.pagina_whatsapp(inf, conn, config.ADMIN_TOKEN or ""), 200)
        if path == "/admin/reenviar-pdf":
            import config, auth_web, daily, db
            q = up.parse_qs(up.urlparse(self.path).query)
            sess = self._sessao()
            token_ok = config.ADMIN_TOKEN and q.get("token", [""])[0] == config.ADMIN_TOKEN
            if not (token_ok or (sess and auth_web.eh_admin(sess["whatsapp"]))):
                return self._html("<h3>Acesso negado</h3>", 403)
            db.init()
            try:
                r = daily.reenviar_pdf_do_dia(q.get("data", [None])[0])
                icone = "✅" if r.get("ok") else "⚠️"
                return self._html(f"<h3>{icone} {r.get('msg','')}</h3>"
                                  f"<p><a href='/admin?token={config.ADMIN_TOKEN or ''}'>← voltar ao painel</a></p>", 200)
            except Exception as e:
                return self._html(f"<h3>⚠️ Erro no reenvio do PDF: {e}</h3>"
                                  f"<p><a href='/admin?token={config.ADMIN_TOKEN or ''}'>← voltar</a></p>", 500)
        if path == "/admin/afiliados":
            import config, site_web, auth_web, db
            q = up.parse_qs(up.urlparse(self.path).query)
            sess = self._sessao()
            token_ok = config.ADMIN_TOKEN and q.get("token", [""])[0] == config.ADMIN_TOKEN
            if not (token_ok or (sess and auth_web.eh_admin(sess["whatsapp"]))):
                return self._html("<h3>Acesso negado</h3>", 403)
            db.init()
            return self._html(site_web.pagina_admin_afiliados(
                db.listar_afiliados(), db.listar_comissoes(pago=False, incluir_estornadas=True),
                config.ADMIN_TOKEN or "", editar_id=q.get("editar", [""])[0] or None), 200)
        if path == "/admin/mensagens":
            import config, site_web, auth_web, db, mensagens
            q = up.parse_qs(up.urlparse(self.path).query)
            sess = self._sessao()
            token_ok = config.ADMIN_TOKEN and q.get("token", [""])[0] == config.ADMIN_TOKEN
            if not (token_ok or (sess and auth_web.eh_admin(sess["whatsapp"]))):
                return self._html("<h3>Acesso negado</h3>", 403)
            db.init()
            return self._html(site_web.pagina_admin_mensagens(
                db.get_config(mensagens.K_WA, mensagens.WA_DEFAULT),
                db.get_config(mensagens.K_EMAIL_ASSUNTO, mensagens.EMAIL_ASSUNTO_DEFAULT),
                db.get_config(mensagens.K_EMAIL_CORPO, mensagens.EMAIL_CORPO_DEFAULT),
                db.get_config(mensagens.K_EMAIL_RENOV_ASSUNTO, mensagens.EMAIL_RENOV_ASSUNTO_DEFAULT),
                db.get_config(mensagens.K_EMAIL_RENOV_CORPO, mensagens.EMAIL_RENOV_CORPO_DEFAULT),
                config.ADMIN_TOKEN or "", msg=q.get("msg", [""])[0],
                automacoes=db.listar_automacoes(),
                bonus_resgate_dias=mensagens.bonus_resgate_dias()), 200)
        if path == "/admin/envio":
            import config, site_web, auth_web, db, daily
            q = up.parse_qs(up.urlparse(self.path).query)
            sess = self._sessao()
            token_ok = config.ADMIN_TOKEN and q.get("token", [""])[0] == config.ADMIN_TOKEN
            if not (token_ok or (sess and auth_web.eh_admin(sess["whatsapp"]))):
                return self._html("<h3>Acesso negado</h3>", 403)
            db.init()
            return self._html(site_web.pagina_admin_envio(
                daily._dias_envio(), config.ADMIN_TOKEN or "", msg=q.get("msg", [""])[0]), 200)
        if path == "/admin/precos":
            import config, site_web
            q = up.parse_qs(up.urlparse(self.path).query)
            token_ok = config.ADMIN_TOKEN and q.get("token", [""])[0] == config.ADMIN_TOKEN
            if not token_ok:
                return self._html("<h3>Acesso negado</h3>", 403)
            visiveis = {p["slug"]: p for p in config.planos_venda()}
            planos = [visiveis[s] for s in ("mensal", "anual") if s in visiveis]
            return self._html(site_web.pagina_precos(planos, config.ADMIN_TOKEN or "",
                                                      msg=q.get("msg", [""])[0]), 200)
        if path == "/admin/custos":
            import config, db, ia_custo, site_web, subscribers
            from datetime import datetime, timedelta
            q = up.parse_qs(up.urlparse(self.path).query)
            if not config.ADMIN_TOKEN or q.get("token", [""])[0] != config.ADMIN_TOKEN:
                return self._html("<h3>Acesso negado</h3>", 403)
            db.init()
            hoje = datetime.now()
            mes = hoje.strftime("%Y-%m")
            # Uma consulta só: a janela do mês corrente (no máximo 31 dias) é sempre um
            # subconjunto da janela de 30 dias, então derivamos o mês filtrando em Python
            # em vez de bater no banco duas vezes pela mesma tabela.
            desde30 = (hoje - timedelta(days=30)).strftime("%Y-%m-%d")
            l30 = db.resumo_ia_uso(desde30)
            linhas_mes = [l for l in l30 if (l.get("dia") or "").startswith(mes)]
            usd = ia_custo.total_usd(linhas_mes)
            nosso = ia_custo.por_dia(l30)
            total_ledger = ia_custo.total_usd(l30)
            fatura = {"estado": "erro", "dias": {}, "parcial": False}
            try:
                import anthropic_admin
                fatura = anthropic_admin.custo_por_dia(desde30)
            except Exception as e:      # a parte opcional não pode levar a tela junto
                print(f"[custos] fatura falhou: {e}", flush=True)
            # Dia a dia mostra só o NOSSO lado: nós carimbamos em horário de São Paulo
            # (Dockerfile fixa TZ=America/Sao_Paulo) e a Admin API bate em UTC, então uma
            # geração perto da meia-noite cai num dia pra nós e no dia seguinte pra ela --
            # comparar dia a dia seria uma gangorra sem significado. A conferência com a
            # fatura, por isso, é por período (30 dias) — ver `total_fatura` abaixo.
            dias = [{"dia": d, "ledger": nosso.get(d, 0.0)} for d in sorted(nosso, reverse=True)]
            total_fatura = (sum(fatura["dias"].values())
                             if fatura["estado"] == "ok" else None)
            dados = {"mes": mes, "ate": hoje.strftime("%Y-%m-%d"),
                     "usd": usd, "brl": ia_custo.em_brl(usd),
                     "cotacao": config.USD_BRL,
                     "assinantes": len(subscribers.ativos()),
                     "por_acao": ia_custo.por_acao(linhas_mes), "dias": dias,
                     "fatura": fatura["estado"],
                     "parcial": fatura.get("parcial", False),
                     "total_ledger": total_ledger,
                     "total_fatura": total_fatura}
            return self._html(site_web.pagina_custos(dados, config.ADMIN_TOKEN or "",
                                                     msg=q.get("msg", [""])[0]), 200)
        if path.startswith("/admin/trilha/peca/"):
            import config, db as _db, pdf_trilha, trilha as _trilha_mod
            q = up.parse_qs(up.urlparse(self.path).query)
            token_ok = config.ADMIN_TOKEN and q.get("token", [""])[0] == config.ADMIN_TOKEN
            if not token_ok:
                return self._html("<h3>Acesso negado</h3>", 403)
            _db.init()
            # mesmo helper do POST /trilha (linha ~1251): rejeita fora da faixa
            # 1..TRILHA_TOTAL ANTES de tocar o banco -- um `numero` gigante na URL
            # não pode virar OverflowError do sqlite3 dentro de `db.trilha_peca`
            # (duas validações paralelas pra mesma entrada é como a 2ª volta fura).
            numero = _trilha_numero_valido(path.rsplit("/", 1)[1])
            if not numero:
                return self._html("<h3>Peça inválida</h3>", 404)
            peca = _db.trilha_peca(numero)
            if not peca:
                return self._html("<h3>Peça não encontrada</h3>", 404)
            peca["numero"] = numero
            # só afirma o link se o ARQUIVO existir -- mesma correção do envio real
            # (app/trilha.py, enviar_para): a prévia não pode divergir do que sai no
            # WhatsApp, e mostrar aqui um botão que dá 404 seria exatamente isso.
            slug = peca.get("ferramenta_slug")
            # ARTIGOS_URL, igual ao envio real (ver comentário em trilha.enviar_para):
            # /ferramentas/ só existe no portal do assinante; no host do ebook a rota
            # cai no fallback e devolve o ebook com 200.
            link = (f"{config.ARTIGOS_URL}/ferramentas/{slug}"
                    if slug and _trilha_mod.caminho_ferramenta(slug) else "")
            # mesma função que gera o PDF: a prévia não pode divergir do que é enviado
            return self._html(pdf_trilha.montar_html(
                peca, "(prévia)", abertura="", link_ferramenta=link), 200)
        if path == "/admin/trilha":
            import config, site_web, db as _db, subscribers as _subs, trilha as _trilha
            q = up.parse_qs(up.urlparse(self.path).query)
            token_ok = config.ADMIN_TOKEN and q.get("token", [""])[0] == config.ADMIN_TOKEN
            if not token_ok:
                return self._html("<h3>Acesso negado</h3>", 403)
            _db.init()
            linhas = []
            for l in _db.trilha_painel():
                reg = _subs.por_id(l["subscriber_id"]) or {}
                linhas.append({"nome": reg.get("nome") or l["subscriber_id"],
                               "proxima_peca": l["proxima_peca"],
                               "enviadas": l["enviadas"], "feitas": l["feitas"],
                               "concluiu": l["proxima_peca"] > config.TRILHA_TOTAL})
            return self._html(site_web.pagina_admin_trilha(
                linhas, config.ADMIN_TOKEN or "", pecas=_db.trilha_listar_pecas(),
                ativa=_trilha.ativa(), msg=q.get("msg", [""])[0]), 200)
        if path.startswith("/admin"):
            import config, subscribers, site_web, auth_web, db
            q = up.parse_qs(up.urlparse(self.path).query)
            sess = self._sessao()
            token_ok = config.ADMIN_TOKEN and q.get("token", [""])[0] == config.ADMIN_TOKEN
            if not (token_ok or (sess and auth_web.eh_admin(sess["whatsapp"]))):
                return self._html("<h3>Acesso negado</h3>", 403)
            db.init()
            return self._html(site_web.pagina_admin(
                subscribers.listar(), config.ADMIN_TOKEN or "", db.listar_cupons(),
                confirmar_id=q.get("confirmar", [""])[0] or None,
                erro=q.get("erro", [""])[0],
                reenviar_id=q.get("reenviar", [""])[0] or None,
                sucesso=q.get("sucesso", [""])[0],
                contagem_slots=subscribers.contar_por_slot()), 200)
        if path.startswith("/agenda"):
            import config, db, daily, agenda_plan, site_web, auth_web
            from datetime import datetime, timedelta
            q = up.parse_qs(up.urlparse(self.path).query)
            sess = self._sessao()
            token_ok = config.ADMIN_TOKEN and q.get("token", [""])[0] == config.ADMIN_TOKEN
            if not (token_ok or (sess and auth_web.eh_admin(sess["whatsapp"]))):
                return self._html("<h3>Acesso negado</h3>", 403)
            db.init()
            try:
                daily.materializar_agenda()
            except Exception as e:
                print(f"[agenda] materializar no GET falhou: {e}", flush=True)
            # A semana passada fica à vista pra dar onde corrigir a área de um estudo já
            # enviado. Numa SEGUNDA, sem recuar, não há dia passado nenhum na tela.
            janela = agenda_plan.semanas_do_mes(datetime.now(), daily._dias_envio(), 4,
                                                semanas_atras=1)
            mapa = db.agenda_listar(janela[0], janela[-1]) if janela else {}
            amanha_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            vazio = lambda d: {"data": d, "tipo": "vazio", "tema": "", "titulo": "", "fixado": 0}
            def _slot_view(d):
                if d < amanha_str:                       # passado -> o que REALMENTE foi enviado (arquivo)
                    dg = db.digest_do_dia(d)
                    if dg:
                        return {"data": d, "tipo": "enviado", "tema": dg.get("tema", ""),
                                "titulo": dg.get("titulo_pt", ""), "fixado": 0, "passado": True,
                                # o painel do card precisa disto; `digest_do_dia` já faz SELECT *
                                "tema_slug": dg.get("tema_slug", ""),
                                "titulo_original": dg.get("titulo_original", ""),
                                "resumo": dg.get("resumo", ""), "fonte": dg.get("fonte", ""),
                                "doi": dg.get("doi", "")}
                    s = mapa.get(d)
                    if s and s.get("titulo"):             # sem registro no arquivo, mas há slot
                        return dict(s, passado=True)
                    return dict(vazio(d), passado=True)
                return dict(mapa.get(d, vazio(d)), passado=False)
            slots = [_slot_view(d) for d in janela]
            semanas = agenda_plan.agrupar_por_semana(slots)
            msg = q.get("msg", [""])[0]
            return self._html(site_web.pagina_agenda(semanas, db.contar_reserva_pronto(), config.ADMIN_TOKEN, msg))
        if path.startswith("/curadoria"):
            import config, db, site_web, auth_web, agenda_plan, daily, draft_store, curadoria
            from datetime import datetime, timedelta
            q = up.parse_qs(up.urlparse(self.path).query)
            sess = self._sessao()
            token_ok = config.ADMIN_TOKEN and q.get("token", [""])[0] == config.ADMIN_TOKEN
            if not (token_ok or (sess and auth_web.eh_admin(sess["whatsapp"]))):
                return self._html("<h3>Acesso negado</h3>", 403)
            db.init()
            novos, cands, classicos = curadoria.montar_candidatos_triagem(db)
            reserva_pronto_n = db.contar_reserva_pronto()
            classico_elegivel_n = len(db.listar_classicos(elegiveis=True))
            estado = agenda_plan.estado_estoque(
                reserva_pronto_n, len(novos), classico_elegivel_n,
                datetime.now(), daily._dias_envio(), daily.ESTOQUE_MINIMO)
            amanha = None
            try:
                d = draft_store.carregar((datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"))
                if d:
                    amanha = {"titulo": d.get("titulo_pt") or (d.get("artigo") or {}).get("titulo", ""),
                              "status": d.get("status", ""), "review_token": d.get("review_token", "")}
            except Exception as e:
                print(f"[curadoria] rascunho de amanhã falhou: {e}", flush=True)
            aba_atual = q.get("aba", ["triagem"])[0]
            painel = None
            if aba_atual == "dossie":
                try:
                    import dossie
                    painel = dossie.painel()
                except Exception as e:          # a aba tem que abrir mesmo sem o painel
                    print(f"[curadoria] painel do dossiê falhou: {e}", flush=True)
                # Backfill dos ids: dossiê gravado antes desta entrega não tem `id` nos
                # blocos, e sem id a tela não oferece ✏️ Editar (sem nenhuma pista disso).
                # Idempotente — na segunda abertura não escreve nada.
                for d in db.listar_dossies():
                    try:
                        db.dossie_backfill_ids(d.get("tema"))
                    except Exception as e:      # a aba tem que abrir mesmo se falhar
                        print(f"[curadoria] backfill de ids do dossiê falhou "
                              f"({d.get('tema')}): {e}", flush=True)
            return self._html(site_web.pagina_curadoria(
                estado, amanha, cands, db.listar_reserva(), classicos, config.ADMIN_TOKEN,
                aba=aba_atual, tema=q.get("tema", [""])[0],
                msg=q.get("msg", [""])[0], dossies=db.listar_dossies(), painel=painel), 200)
        if path == "/series":
            import config, series, site_web, auth_web
            q = up.parse_qs(up.urlparse(self.path).query)
            sess = self._sessao()
            token_ok = config.ADMIN_TOKEN and q.get("token", [""])[0] == config.ADMIN_TOKEN
            if not (token_ok or (sess and auth_web.eh_admin(sess["whatsapp"]))):
                return self._html("<h3>Acesso negado</h3>", 403)
            sid = q.get("serie", [""])[0] or None
            termo = q.get("termo", [""])[0]
            ctx = series.contexto_pagina(serie_aberta_id=sid, termo=termo)
            dia_min = series.dia_minimo_inicio()
            return self._html(site_web.pagina_series(
                ctx, config.ADMIN_TOKEN or "", serie_aberta_id=sid or "",
                dia_min=dia_min, msg=q.get("msg", [""])[0],
                confirmar_cancelar=q.get("confirmar_cancelar", [""])[0]))
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
            return self._html(site_web.pagina_login())
        if path == "/entrar-codigo":
            return self._html(site_web.pagina_entrar("numero"))
        if path == "/entrar-cpf":
            return self._html(site_web.pagina_login(via="cpf"))
        if path == "/entrar-cpf-codigo":
            return self._html(site_web.pagina_entrar("numero", via="cpf"))
        if path == "/primeiro-acesso":
            return self._html(site_web.pagina_recuperar("primeiro"))
        if path == "/esqueci":
            return self._html(site_web.pagina_recuperar("esqueci"))
        if path == "/criar-senha":
            import urllib.parse as up
            tok = up.parse_qs(up.urlparse(self.path).query).get("token", [""])[0]
            if not db.obter_token_senha(tok):
                return self._html(site_web.pagina_msg("Link inválido ou expirado",
                    "Peça um novo link em 'Primeiro acesso' ou 'Esqueci minha senha'."))
            return self._html(site_web.pagina_criar_senha(tok))
        if path == "/sair":
            # logout NUNCA passa pelo gate de aceite: só encerra a sessão, não muta
            # dados do assinante, e é a única saída de quem ficaria preso na tela de
            # aceite se este endpoint também exigisse aceitar primeiro.
            import auth_web
            auth_web.logout(auth_web._parse_cookie(self.headers.get("Cookie", "")).get("sid"))
            return self._redirect("/", clear=True)
        if path == "/termos":
            import site_legal
            return self._html(site_legal.pagina_termos())
        if path == "/privacidade":
            import site_legal
            return self._html(site_legal.pagina_privacidade())
        if path == "/minha":
            sub = self._sessao()
            if not sub:
                return self._redirect("/entrar")
            import subscribers as _subs
            reg = self._sub_logado()
            if reg is None:
                # sessão viva mas sem assinante correspondente (removido/órfã) -> sessão
                # inválida. Sem este `return`, o `if reg and ...` abaixo pulava a checagem
                # de aceite em silêncio e caía direto em pagina_minha(sub, ...) usando só o
                # dict raso da sessão (sem os campos do cadastro).
                return self._redirect("/entrar")
            if _subs.precisa_aceitar(reg):
                import site_legal
                return self._html(site_legal.pagina_aceite_termos("/minha"))
            import auth_web
            return self._html(site_web.pagina_minha(sub, admin=auth_web.eh_admin(sub["whatsapp"])))
        if path == "/cancelar":
            # exceção deliberada ao gate de aceite: quem quer sair da assinatura não
            # pode ser obrigado a aceitar termos novos antes — ver docstring de
            # _cancelar_motivo/_cancelar_confirmar (POST) para o mesmo raciocínio.
            if not self._sessao():
                return self._redirect("/entrar")
            return self._html(site_web.pagina_cancelar())
        if path == "/meus-dados":
            sub = self._sub_logado()
            if not sub:
                return self._redirect("/entrar")
            import subscribers as _subs
            if _subs.precisa_aceitar(sub):
                import site_legal
                return self._html(site_legal.pagina_aceite_termos("/meus-dados"))
            import db as _db, config as _cfg
            atual = _subs.slot_de(sub)
            teto = int(_db.get_config("slot_teto", str(_cfg.SLOT_TETO_DEFAULT)) or _cfg.SLOT_TETO_DEFAULT)
            return self._html(site_web.pagina_meus_dados(
                sub, slots=_subs.slots_com_vaga(teto, atual), slot_atual=atual))
        if path == "/renovar":
            return self._get_rota_renovar()
        if path == "/trilha":
            sub = self._sub_logado()
            if not sub:
                return self._redirect("/entrar")
            return self._html(self._pagina_trilha(sub))
        if path.startswith("/ferramentas/"):
            if not self._sub_logado():          # download é fechado: só assinante logado
                return self._redirect("/entrar")
            import mimetypes
            import trilha as _trilha
            caminho = _trilha.caminho_ferramenta(path[len("/ferramentas/"):])
            if not caminho:
                return self._html("<h3>Arquivo não encontrado</h3>", 404)
            tipo = mimetypes.guess_type(caminho)[0] or "application/octet-stream"
            body = open(caminho, "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Disposition",
                             f'attachment; filename="{os.path.basename(caminho)}"')
            self.end_headers()
            return self.wfile.write(body)
        parts = [p for p in path.split("/") if p]
        if parts and parts[0] == "artigos":
            # /artigos só LÊ conteúdo (não muta dado nenhum do assinante) — o critério
            # do gate de aceite é mutação, então esta rota fica de fora de propósito.
            # Gateá-la também bloquearia o acesso ao conteúdo já pago, na prática igual
            # a parar o envio diário, que é uma restrição global deste projeto.
            sub = self._sessao()
            if not sub:
                return self._redirect("/entrar")
            temas = db.listar_temas()
            if len(parts) == 1:                      # arquivo: abre no 1º tema (com abas)
                if not temas:
                    return self._html(site_web.hub_temas([]))
                slug = temas[0]["slug"]
                return self._html(site_web.lista_tema(db.meta_tema(slug), db.listar_por_tema(slug), temas))
            slug = parts[1]
            if len(parts) == 2:
                return self._html(site_web.lista_tema(db.meta_tema(slug), db.listar_por_tema(slug), temas))
            lst = db.listar_por_tema(slug)           # ordenado por data DESC
            i = next((k for k, x in enumerate(lst) if x["data"] == parts[2]), None)
            if i is None:
                return self._html("<h3>Edição não encontrada</h3>", 404)
            ant = lst[i + 1] if i + 1 < len(lst) else None   # edição mais antiga
            prox = lst[i - 1] if i - 1 >= 0 else None         # edição mais recente
            return self._html(site_web.pagina_digest(db.meta_tema(slug), lst[i], (ant, prox)))
        return self._html("<h3>Página não encontrada</h3>", 404)

    def _html(self, s, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(s.encode("utf-8"))

    def _json(self, obj, code=200):
        import json
        corpo = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_POST(self):
        import urllib.parse as up
        path = up.urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        if length > 30_000_000:            # PDFs de estudo são pequenos; corta abuso
            return self._html("<h3>Arquivo muito grande (máx 30MB)</h3>", 413)
        raw = self.rfile.read(length) if length > 0 else b""
        if path == "/webhook/asaas":       # Asaas envia JSON (não form-urlencoded)
            import webhook_asaas, json as _json
            try:
                body = _json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                return self._html("bad json", 400)
            st, msg = webhook_asaas.processar(body, self.headers.get("asaas-access-token"))
            return self._html(msg, st)
        ctype = self.headers.get("Content-Type", "")
        if path == "/curadoria" and ctype.startswith("multipart/form-data"):
            return self._curadoria_upload(raw, ctype)   # upload de PDF do estudo
        if path == "/series" and ctype.startswith("multipart/form-data"):
            return self._series_upload(raw, ctype)       # upload do meu estudo p/ a série
        form = up.parse_qs(raw.decode("utf-8"))
        g = lambda k: form.get(k, [""])[0]
        if path.startswith("/revisar/"):
            import area_estudo, config, draft_store, review_web
            tok = path.split("/revisar/", 1)[1]
            r = draft_store.por_token(tok)
            if not r:
                return self._html("<h3>Link inválido</h3>", 404)
            areas = area_estudo.areas()
            if g("acao") == "regerar_audio":
                import daily
                # salva o texto (e a área) atuais antes de gerar o áudio novo
                r2 = draft_store.aplicar(r["data"], "editar", g("texto"), area=g("area"))
                ok = daily.enviar_audio_preview(r2)
                aviso = ("🎧 Novo áudio enviado no seu WhatsApp. Escute e, se aprovar, clique em Aprovar."
                         if ok else "Não consegui gerar o áudio agora — tente de novo em instantes.")
                return self._html(review_web.pagina_revisao(r2, aviso=aviso, audio_on=config.audio_ligado(),
                                                            areas=areas))
            if g("acao") == "trocar":
                import daily
                return self._html(review_web.pagina_trocar_estudo(
                    daily.montar_alternativas(r), r, tok, areas=areas))
            if g("acao") == "trocar_confirmar":
                import daily, threading
                tipo, cid = g("tipo"), g("id")
                if not daily.alternativa_valida(r, tipo, cid):
                    return self._html(review_web.pagina_revisao(
                        r, aviso="Esse estudo saiu da lista — escolha outro.",
                        audio_on=config.audio_ligado(), areas=areas))
                threading.Thread(target=daily.trocar_estudo_amanha,
                                 args=(tok, tipo, cid), daemon=True).start()
                return self._html(review_web.pagina_trocando())
            if area_estudo.correcao_bloqueada(r, g("area")):
                # "Feito ✅" numa correção que não corrige é a armadilha que criou o item 36.
                return self._html(review_web.pagina_revisao(
                    r, aviso="Esse estudo já foi enviado — a área não muda mais por aqui.",
                    audio_on=config.audio_ligado(), areas=areas))
            # Volta pra tela COM o texto (decisão do Diego): ele vê o que ficou salvo,
            # segue editando se quiser e confere o PDF sem reabrir o link do WhatsApp.
            import content
            r2 = draft_store.aplicar(r["data"], g("acao"), g("texto"), area=g("area"),
                                     kit=content.kit_do_form(form))
            return self._html(review_web.pagina_revisao(
                r2, aviso=review_web.aviso_do_feito(g("acao"), r.get("status", "")),
                audio_on=config.audio_ligado(), areas=areas))
        if path == "/admin/whatsapp":
            import config, auth_web, evolution_admin
            sess = self._sessao()
            token_ok = bool(config.ADMIN_TOKEN) and g("token") == config.ADMIN_TOKEN
            if not (token_ok or (sess and auth_web.eh_admin(sess["whatsapp"]))):
                return self._html("<h3>Acesso negado</h3>", 403)
            acao = g("acao")
            if acao == "reiniciar":
                evolution_admin.reiniciar()
            elif acao == "desconectar":
                evolution_admin.desconectar()
            return self._redirect(f"/admin/whatsapp?token={config.ADMIN_TOKEN}" if token_ok else "/admin/whatsapp")
        if path == "/admin/afiliados":
            import config, auth_web, db
            sess = self._sessao()
            token_ok = bool(config.ADMIN_TOKEN) and g("token") == config.ADMIN_TOKEN
            if not (token_ok or (sess and auth_web.eh_admin(sess["whatsapp"]))):
                return self._html("<h3>Acesso negado</h3>", 403)
            db.init()
            acao = g("acao")
            try:
                pdesc = float(g("pct_desconto") or "10")
                pcom = float(g("pct_comissao") or "3")
            except ValueError:
                pdesc, pcom = 10.0, 3.0
            if acao == "criar_afiliado":
                db.criar_afiliado(g("nome"), g("contato"), g("codigo"), pdesc, pcom)
            elif acao == "editar_afiliado":
                db.atualizar_afiliado(g("id"), g("nome"), g("contato"), g("codigo"), pdesc, pcom)
            elif acao == "toggle_afiliado":
                db.toggle_afiliado(g("id"), g("on") == "1")
            elif acao == "marcar_comissao_paga":
                db.marcar_comissao_paga(g("id"))
            return self._redirect(f"/admin/afiliados?token={config.ADMIN_TOKEN}" if token_ok else "/admin/afiliados")
        if path == "/admin/mensagens":
            import config, auth_web, db, mensagens
            sess = self._sessao()
            token_ok = bool(config.ADMIN_TOKEN) and g("token") == config.ADMIN_TOKEN
            if not (token_ok or (sess and auth_web.eh_admin(sess["whatsapp"]))):
                return self._html("<h3>Acesso negado</h3>", 403)
            db.init()
            if g("acao") == "salvar_mensagens":
                db.set_config(mensagens.K_WA, g("wa"))
                db.set_config(mensagens.K_EMAIL_ASSUNTO, g("email_assunto"))
                db.set_config(mensagens.K_EMAIL_CORPO, g("email_corpo"))
                db.set_config(mensagens.K_EMAIL_RENOV_ASSUNTO, g("email_renov_assunto"))
                db.set_config(mensagens.K_EMAIL_RENOV_CORPO, g("email_renov_corpo"))
            if g("acao") == "salvar_automacao":
                try:
                    db.salvar_automacao(g("id"), int(g("dias") or 0), g("canal") or "whatsapp",
                                        g("texto"), 1 if g("ativo") == "1" else 0)
                except (TypeError, ValueError):
                    pass          # dias não numérico: ignora em vez de derrubar a tela
            if g("acao") == "remover_automacao":
                db.remover_automacao(g("id"))
            if g("acao") == "salvar_bonus_resgate":
                try:
                    dias = int(g("bonus_resgate_dias") or 0)
                    if dias >= 0:
                        db.set_config(mensagens.K_BONUS_RESGATE_DIAS, str(dias))
                except (TypeError, ValueError):
                    pass          # valor não numérico: ignora, mantém o que já estava salvo
            return self._redirect(f"/admin/mensagens?token={config.ADMIN_TOKEN}&msg=Mensagens+salvas"
                                  if token_ok else "/admin/mensagens?msg=Mensagens+salvas")
        if path == "/admin/envio":
            import config, auth_web, db
            sess = self._sessao()
            token_ok = bool(config.ADMIN_TOKEN) and g("token") == config.ADMIN_TOKEN
            if not (token_ok or (sess and auth_web.eh_admin(sess["whatsapp"]))):
                return self._html("<h3>Acesso negado</h3>", 403)
            db.init()
            if g("acao") == "salvar_dias":
                db.set_config("dias_envio", ",".join(form.get("dia", [])))
            return self._redirect(f"/admin/envio?token={config.ADMIN_TOKEN}&msg=Dias+salvos"
                                  if token_ok else "/admin/envio?msg=Dias+salvos")
        if path == "/admin/trilha":
            import config, db, trilha as _trilha
            token_ok = bool(config.ADMIN_TOKEN) and g("token") == config.ADMIN_TOKEN
            if not token_ok:
                return self._html("<h3>Acesso negado</h3>", 403)
            db.init()
            ligar = g("acao") == "ligar"
            _trilha.definir_ativa(ligar)
            msg = ("Trilha LIGADA — a partir do próximo sábado os assinantes recebem."
                   if ligar else "Trilha desligada. Nenhum assinante recebe.")
            return self._redirect(f"/admin/trilha?token={config.ADMIN_TOKEN}&msg={up.quote(msg)}")
        if path == "/admin/precos":
            import config, db
            token_ok = bool(config.ADMIN_TOKEN) and g("token") == config.ADMIN_TOKEN
            if not token_ok:
                return self._html("<h3>Acesso negado</h3>", 403)
            db.init()
            slug, acao = g("slug"), g("acao")
            msg = ""
            if slug not in ("mensal", "anual"):
                msg = "Plano inválido."
            elif acao == "resetar_preco":
                db.set_config(f"preco_base_{slug}", "")
                pl = config.plano_por_slug(slug) or {}
                msg = f"{slug.capitalize()} voltou ao padrão ({pl.get('preco','')})."
            elif acao == "salvar_preco":
                valor = config.parse_preco(g("preco"))
                if valor is None:
                    msg = "Preço inválido — use um número maior que zero (ex.: 1600)."
                else:
                    db.set_config(f"preco_base_{slug}", str(valor))
                    msg = f"✅ {slug.capitalize()}: {config._preco_str(valor)}."
            return self._redirect(f"/admin/precos?token={config.ADMIN_TOKEN}&msg={up.quote(msg)}")
        if path == "/admin":
            import config, subscribers, auth_web, db, phone
            sess = self._sessao()
            token_ok = bool(config.ADMIN_TOKEN) and g("token") == config.ADMIN_TOKEN
            if not (token_ok or (sess and auth_web.eh_admin(sess["whatsapp"]))):
                return self._html("<h3>Acesso negado</h3>", 403)
            acao = g("acao")
            if acao == "adicionar":
                wa_input = g("whatsapp").strip()
                if not wa_input:
                    erro = up.quote("Número de WhatsApp é obrigatório.")
                    return self._redirect(f"/admin?token={config.ADMIN_TOKEN}&erro={erro}"
                                          if token_ok else f"/admin?erro={erro}")
                novo = phone.montar_e164(g("pais_dial") or "55", wa_input)
                subscribers.adicionar(g("nome"), novo)
            elif acao == "remover":
                return self._redirect(f"/admin?token={config.ADMIN_TOKEN}&confirmar={g('id')}" if token_ok else "/admin")
            elif acao == "remover_confirmar":
                subscribers.remover(g("id"))
            elif acao == "editar_numero":
                num_input = g("numero").strip()
                if not num_input:
                    erro = up.quote("Número é obrigatório.")
                    return self._redirect(f"/admin?token={config.ADMIN_TOKEN}&erro={erro}"
                                          if token_ok else f"/admin?erro={erro}")
                novo = phone.montar_e164(g("pais_dial") or "55", num_input)
                outro = subscribers.por_whatsapp(novo)
                if outro and str(outro["id"]) != str(g("id")):
                    erro = up.quote("Esse número já é de outro assinante.")
                    return self._redirect(f"/admin?token={config.ADMIN_TOKEN}&erro={erro}"
                                          if token_ok else f"/admin?erro={erro}")
                subscribers.atualizar_whatsapp(g("id"), novo)
            elif acao == "reenviar":
                return self._redirect(f"/admin?token={config.ADMIN_TOKEN}&reenviar={g('id')}"
                                      if token_ok else f"/admin?reenviar={g('id')}")
            elif acao == "reenviar_confirmar":
                sub = subscribers.por_id(g("id"))
                if not sub:
                    erro = up.quote("Assinante não encontrado.")
                    return self._redirect(f"/admin?token={config.ADMIN_TOKEN}&erro={erro}"
                                          if token_ok else f"/admin?erro={erro}")
                ok, detalhe = auth_web.reenviar_boas_vindas_wa(sub)
                if ok:
                    msg = up.quote("✅ Boas-vindas reenviadas por WhatsApp.")
                    return self._redirect(f"/admin?token={config.ADMIN_TOKEN}&sucesso={msg}"
                                          if token_ok else f"/admin?sucesso={msg}")
                erro = up.quote(f"❌ Falha ao reenviar: {detalhe}")
                return self._redirect(f"/admin?token={config.ADMIN_TOKEN}&erro={erro}"
                                      if token_ok else f"/admin?erro={erro}")
            elif acao == "definir_slot":
                import daily as _daily
                sub = subscribers.por_id(g("id"))
                if not sub:
                    erro = up.quote("Assinante não encontrado.")
                    return self._redirect(f"/admin?token={config.ADMIN_TOKEN}&erro={erro}"
                                          if token_ok else f"/admin?erro={erro}")
                novo = g("slot")
                subscribers.definir_slot(sub["id"], novo)   # valida ∈ SLOTS; SEM teto (admin fura)
                if novo in config.SLOTS and db.slot_ja_enviou(_daily._hoje_iso(), novo):
                    try:
                        _daily.enviar_catch_up(subscribers.por_id(sub["id"]))
                    except Exception as e:
                        print(f"[admin] catch-up de slot falhou: {e}", flush=True)
                msg = up.quote("✅ Horário atualizado.")
                return self._redirect(f"/admin?token={config.ADMIN_TOKEN}&sucesso={msg}"
                                      if token_ok else f"/admin?sucesso={msg}")
            elif acao == "curador":
                subscribers.definir_curador(g("id"), g("on") == "1")
            elif acao == "gerar_cupom":
                try:
                    dias = max(0, int(g("dias") or "0"))
                except ValueError:
                    dias = 0
                db.init(); db.criar_cupom(descricao=g("descricao"), uso_unico=True, dias_acesso=dias)
            elif acao == "toggle_cupom":
                db.init(); db.toggle_cupom(g("codigo"), g("on") == "1")
            return self._redirect(f"/admin?token={config.ADMIN_TOKEN}" if token_ok else "/admin")
        if path == "/agenda":
            import config, db, daily, agenda_plan, auth_web
            from datetime import datetime, timedelta
            sess = self._sessao()
            token_ok = bool(config.ADMIN_TOKEN) and g("token") == config.ADMIN_TOKEN
            if not (token_ok or (sess and auth_web.eh_admin(sess["whatsapp"]))):
                return self._html("<h3>Acesso negado</h3>", 403)
            db.init()
            acao, data, msg = g("acao"), g("data"), ""
            if acao == "mover":
                dest = g("dest")
                amanha_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                validos = set(d for d in agenda_plan.semanas_do_mes(datetime.now(), daily._dias_envio(), 4)
                              if d >= amanha_str)   # só dias futuros são editáveis
                if data not in validos or dest not in validos:
                    msg = "Data inválida — mover ignorado."
                else:
                    ok = db.agenda_mover(data, dest)
                    msg = "Trocado." if ok else "Destino fixado — não trocado."
            elif acao == "fixar":
                db.agenda_fixar(data, True); msg = "Fixado."
            elif acao == "desafixar":
                db.agenda_fixar(data, False); msg = "Solto."
            elif acao == "pular":
                db.agenda_pular(data, True); msg = "Dia marcado como folga."
            elif acao == "despular":
                db.agenda_pular(data, False); msg = "Dia reativado."
            elif acao == "corrigir_area_digest":
                # Estudo JÁ ENVIADO: a área é gravada no `digests`, não no rascunho. Não
                # passa pela lista `validos` do `mover` — aquela guarda existe pra manter
                # o passado imexível, e aqui o passado é justamente o alvo.
                import area_estudo
                area = g("area")
                try:
                    r = area_estudo.aplicar_no_digest(data, g("slug"), area)
                    if r == "movido":
                        msg = f"Área corrigida para {area}."
                    elif r == "ocupado":
                        outro = db.obter(db.slug(area), data) or {}
                        msg = (f"Já existe estudo nesse dia em {area}: "
                               f"{outro.get('titulo_pt') or 'sem título'}. Não mexi em nada.")
                    elif r == "invalida":
                        msg = "Não reconheci essa área."
                    elif r == "inexistente":
                        msg = "Não achei o estudo desse dia."
                    else:
                        msg = "A área já era essa."
                except Exception as e:
                    # Banco fora do ar não pode devolver 500 numa tela que ele abre todo
                    # dia — a agenda continua servindo pro resto.
                    print(f"[agenda] corrigir área de {data} falhou: {e}", flush=True)
                    msg = "Não consegui guardar a área agora — tente de novo."
            elif acao == "rematerializar":
                n = daily.materializar_agenda(); msg = f"{n} dia(s) preenchido(s)."
            return self._redirect((f"/agenda?token={config.ADMIN_TOKEN}&msg={up.quote(msg)}")
                                  if token_ok else f"/agenda?msg={up.quote(msg)}")
        if path == "/curadoria":
            import config, db, curadoria
            if not config.ADMIN_TOKEN or g("token") != config.ADMIN_TOKEN:
                return self._html("<h3>Acesso negado</h3>", 403)
            db.init()
            acao, msg = g("acao"), ""
            aba, tema = g("aba") or "triagem", g("tema")
            ancora = ""
            if acao in ("priorizar", "descartar", "desfazer"):
                novo = {"priorizar": "selecionado", "descartar": "descartado",
                        "desfazer": "novo"}[acao]
                cid = g("id")
                db.marcar_candidatos([cid], novo)
                msg = {"priorizar": "Priorizado — o resumo é gerado hoje à noite.",
                       "descartar": "Estudo descartado.",
                       "desfazer": "Prioridade removida."}[acao]
                ancora = f"#cand-{up.quote(cid)}" if acao in ("desfazer", "priorizar") else ""
            elif acao == "varrer":
                try:
                    msg = f"Varredura concluída: {curadoria.rodar_varredura()} novos candidatos."
                except Exception as e:
                    print(f"[curadoria] varredura erro: {e}", flush=True); msg = "Falha na varredura (ver logs)."
            elif acao == "varrer_classicos":
                try:
                    msg = f"Varredura de clássicos: {curadoria.rodar_varredura_classicos()} novos candidatos."
                except Exception as e:
                    print(f"[classicos] varredura erro: {e}", flush=True); msg = "Falha na varredura de clássicos (ver logs)."
            elif acao == "varrer_presos":
                try:
                    msg = f"Candidatos presos: {curadoria.varrer_presos()} liberado(s) de volta ao pool."
                except Exception as e:
                    print(f"[presos] varredura erro: {e}", flush=True); msg = "Falha ao liberar candidatos presos (ver logs)."
            elif acao == "encorpar_corpus":
                # Minutos de trabalho (janelas x temas x IA): numa request síncrona o
                # navegador desiste antes. Thread + aviso no WhatsApp, como o 🔁 trocar estudo.
                import threading

                def _encorpar():
                    try:
                        r = curadoria.encorpar_corpus(6)
                        if r.get("ja_rodando"):
                            return              # 2º clique: a 1ª rodada é que vai avisar
                        import deliver
                        deliver.enviar_curador(
                            f"📚 Base encorpada: {r['novos']} estudos novos na memória "
                            f"({r['janelas']} meses varridos"
                            + (f", {r['falhas']} janela(s) falharam" if r["falhas"] else "") + ").")
                    except Exception as e:
                        print(f"[corpus] backfill explodiu: {e}", flush=True)
                        try:                    # sem isto o Diego fica esperando um aviso que nunca vem
                            import deliver
                            deliver.enviar_curador("📚 O backfill da base falhou — dá pra tentar de novo.")
                        except Exception:
                            pass

                threading.Thread(target=_encorpar, daemon=True).start()
                msg = "📚 Encorpando a base em segundo plano — te aviso no WhatsApp quando terminar."
            elif acao == "construir_dossie":
                import threading

                def _dossies():
                    try:
                        import dossie
                        r = dossie.reconstruir_todos()
                        if r.get("ja_rodando"):
                            return
                        import deliver
                        total = sum(v for k, v in r.items() if k != "ja_rodando")
                        deliver.enviar_curador(
                            f"🧠 Dossiê refeito em {len(r)} tema(s), a partir de {total} "
                            f"estudos. Abra a Curadoria › 🧠 Dossiê pra ler.")
                    except Exception as e:
                        print(f"[dossie] reconstrução explodiu: {e}", flush=True)
                        try:
                            import deliver
                            deliver.enviar_curador("🧠 A construção do dossiê falhou — dá pra tentar de novo.")
                        except Exception:
                            pass

                threading.Thread(target=_dossies, daemon=True).start()
                msg = "🧠 Construindo o dossiê em segundo plano — te aviso no WhatsApp quando terminar."
            elif acao == "confirmar_exclusao":
                # O título vem do dossiê — é o que a IA ESCREVEU. Resolve contra o corpus
                # e mostra o estudo real antes de tirar; sem casamento, avisa em vez de
                # fingir que excluiu (a próxima reconstrução traria o estudo de volta).
                import dossie, site_web
                t = g("tema")
                achado = dossie.casar_titulo(g("titulo"), dossie.corpus_do_tema(t))
                if achado:
                    return self._html(site_web.pagina_confirmar_exclusao(
                        achado, t, config.ADMIN_TOKEN), 200)
                aba, msg = "dossie", ("Não achei este estudo na base com esse título "
                                      "(a IA pode ter reescrito). Abra Estudos lidos "
                                      "e tire de lá.")
            elif acao in ("excluir_corpus", "devolver_corpus"):
                escopo = "" if acao == "devolver_corpus" else g("escopo")
                origem, ref = g("origem"), g("ref")
                aba = "dossie"
                try:
                    if origem == "digest":
                        slug, _, data = ref.partition("|")
                        db.excluir_digest(slug, data, escopo)
                    else:
                        db.excluir_candidato(ref, escopo)
                    msg = ("Estudo devolvido à memória." if not escopo else
                           "Fora da memória — refaça o dossiê (🧠) pra ver o efeito "
                           "nas afirmações." if escopo == "memoria" else
                           "Fora da memória e da fila — refaça o dossiê (🧠) pra ver o "
                           "efeito nas afirmações.")
                except ValueError as e:         # escopo vindo do navegador é entrada suja
                    print(f"[curadoria] exclusão recusada: {e}", flush=True)
                    msg = "Não entendi o que era pra tirar — tente de novo pela lista."
            elif acao == "refazer_dossie_tema":
                # Mesmo desenho do botão que refaz tudo (thread + aviso no WhatsApp): são
                # ~10 chamadas Sonnet e o navegador desistiria antes.
                import threading
                tema_alvo = g("tema")

                def _um_tema(t=tema_alvo):
                    try:
                        import dossie
                        r = dossie.reconstruir_todos(temas=[t])
                        if r.get("ja_rodando"):
                            return
                        import deliver
                        deliver.enviar_curador(
                            f"🧠 Dossiê de {t} refeito a partir de {r.get(t, 0)} estudos.")
                    except Exception as e:
                        print(f"[dossie] refazer {t} explodiu: {e}", flush=True)
                        try:
                            import deliver
                            deliver.enviar_curador(f"🧠 Refazer o dossiê de {t} falhou — "
                                                   "dá pra tentar de novo.")
                        except Exception:
                            pass

                threading.Thread(target=_um_tema, daemon=True).start()
                aba = "dossie"
                msg = (f"🧠 Refazendo o dossiê de {tema_alvo} em segundo plano — te aviso "
                       "no WhatsApp quando terminar.")
            elif acao in ("editar_bloco", "soltar_bloco"):
                aba = "dossie"
                tema_b, bloco = g("tema"), g("bloco")
                try:
                    if acao == "soltar_bloco":
                        ok = db.dossie_soltar_bloco(tema_b, bloco)
                        msg = ("Bloco solto — a próxima reconstrução pode reescrevê-lo."
                               if ok else "Não achei esse bloco no dossiê.")
                    else:
                        ok = db.dossie_editar_bloco(tema_b, bloco, g("afirmacao"))
                        msg = ("Afirmação salva e bloco fixado — a reconstrução não mexe "
                               "mais nele." if ok else "Não achei esse bloco no dossiê.")
                except ValueError:
                    # Texto vazio. Falha aberta: sem a mensagem ele clica, nada acontece
                    # e não sabe por quê.
                    msg = "A afirmação não pode ficar vazia — o bloco não foi alterado."
            elif acao == "regerar_kit":
                import threading

                def _kits():
                    try:
                        r = curadoria.regerar_kits()
                        if r.get("ja_rodando"):
                            return
                        import deliver
                        deliver.enviar_curador(
                            f"🎬 Kit refeito em {r['regerados']} estudo(s) da reserva"
                            + (f" · {r['falhas']} sem sucesso (kit antigo preservado)"
                               if r["falhas"] else "") + ".")
                    except Exception as e:
                        print(f"[kit] regeração explodiu: {e}", flush=True)
                        try:
                            import deliver
                            deliver.enviar_curador("🎬 A regeração dos kits falhou — dá pra tentar de novo.")
                        except Exception:
                            pass

                threading.Thread(target=_kits, daemon=True).start()
                msg = "🎬 Refazendo os kits em segundo plano — te aviso no WhatsApp quando terminar."
            elif acao == "limpar_nome":
                try:
                    import limpeza
                    r = limpeza.limpar_estoque()
                    msg = (f"Nome removido: {r['reserva']} na reserva, {r['rascunho']} no "
                           f"rascunho do dia, {r['portal']} no portal.")
                except Exception as e:
                    print(f"[limpeza] erro: {e}", flush=True); msg = "Falha ao limpar o estoque (ver logs)."
            elif acao == "backfill_tags":
                try:
                    import curadoria
                    msg = f"Tags: {curadoria.backfill_tags()} estudo(s) etiquetado(s)."
                except Exception as e:
                    print(f"[tags] backfill erro: {e}", flush=True)
                    msg = "Falha no backfill de tags (ver logs)."
            elif acao == "gerar":
                try:
                    msg = f"Resumos gerados: {curadoria.gerar_selecionados()}."
                except Exception as e:
                    print(f"[curadoria] gerar erro: {e}", flush=True); msg = "Falha ao gerar resumos (ver logs)."
            elif acao == "editar_reserva":
                db.atualizar_reserva(g("id"), titulo_pt=g("titulo_pt"), resumo=g("resumo"))
                msg = "Item da reserva atualizado."
            elif acao == "remover_reserva":
                db.remover_reserva(g("id"))
                msg = "Item removido da reserva."
            destino = (f"/curadoria?token={config.ADMIN_TOKEN}&aba={up.quote(aba)}"
                       f"&tema={up.quote(tema)}&msg={up.quote(msg)}{ancora}")
            return self._redirect(destino)
        if path == "/series":
            import config, db, series, auth_web
            sess = self._sessao()
            token_ok = bool(config.ADMIN_TOKEN) and g("token") == config.ADMIN_TOKEN
            if not (token_ok or (sess and auth_web.eh_admin(sess["whatsapp"]))):
                return self._html("<h3>Acesso negado</h3>", 403)
            db.init()
            acao, sid, msg = g("acao"), g("serie"), ""
            if acao == "criar":
                sid = db.criar_serie(g("nome"))
            elif acao == "buscar":
                import urllib.parse as _up
                return self._redirect(
                    f"/series?serie={_up.quote(sid)}&token={config.ADMIN_TOKEN}"
                    f"&termo={_up.quote(g('termo'))}")
            elif acao == "add_item":
                tipo, rid = g("tipo"), g("id")
                ja_na_serie = db.serie_item_existe(sid, tipo, rid)
                db.adicionar_serie_item(sid, tipo, rid, titulo=g("titulo"), tema=g("tema"))
                msg = "Este estudo já está na série." if ja_na_serie else "Adicionado."
            elif acao == "remover_item":
                db.remover_serie_item(g("item"))
                msg = "Removido."
            elif acao == "reordenar":
                db.reordenar_serie_item(g("item"), g("direcao"))
            elif acao == "ativar":
                ok, msg = series.ativar_serie(sid, g("data_inicio"), dia_min=series.dia_minimo_inicio())
            elif acao == "cancelar":
                import urllib.parse as _up
                return self._redirect(
                    f"/series?serie={_up.quote(sid)}&token={config.ADMIN_TOKEN}"
                    f"&confirmar_cancelar={_up.quote(sid)}")
            elif acao == "cancelar_confirmar":
                ok, msg = series.cancelar_serie(sid)
            import urllib.parse as _up
            alvo = f"/series?serie={_up.quote(sid)}&token={config.ADMIN_TOKEN}"
            if msg:
                alvo += f"&msg={_up.quote(msg)}"
            return self._redirect(alvo)
        if path == "/entrar":
            if not self._rate_ok("login", 15, 300):   # 15 tentativas / 5 min por IP
                return
            import site_web, auth_web
            wpp = g("whatsapp")
            status, token = auth_web.login_senha(wpp, g("senha"))
            if status == "ok":
                return self._redirect("/artigos", token=token)
            if status == "sem_senha":
                return self._html(site_web.pagina_login(sem_senha=True, whatsapp=wpp))
            return self._html(site_web.pagina_login(erro="WhatsApp ou senha incorretos.", whatsapp=wpp))
        if path == "/entrar-codigo":
            if not self._rate_ok("otp", 5, 600):       # 5 envios/verificações / 10 min por IP
                return
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
        if path == "/entrar-cpf":
            if not self._rate_ok("login", 15, 300):
                return
            import site_web, auth_web
            doc = g("cpf")
            status, token = auth_web.login_senha_cpf(doc, g("senha"))
            if status == "ok":
                return self._redirect("/artigos", token=token)
            if status == "sem_senha":
                return self._html(site_web.pagina_login(sem_senha=True, whatsapp=doc, via="cpf"))
            return self._html(site_web.pagina_login(erro="CPF ou senha incorretos.", whatsapp=doc, via="cpf"))
        if path == "/entrar-cpf-codigo":
            if not self._rate_ok("otp", 5, 600):
                return
            import site_web, auth_web
            doc = g("cpf")
            if g("etapa") == "codigo":
                token = auth_web.verificar_cpf(doc, g("codigo"))
                if token:
                    return self._redirect("/artigos", token=token)
                return self._html(site_web.pagina_entrar("codigo", whatsapp=doc, via="cpf",
                                  erro="Código inválido ou expirado. Tente novamente."))
            auth_web.iniciar_login_cpf(doc)  # neutro: só envia se achar assinante ativo
            return self._html(site_web.pagina_entrar("codigo", whatsapp=doc, via="cpf"))
        if path in ("/primeiro-acesso", "/esqueci"):
            if not self._rate_ok("recover", 5, 600):   # 5 pedidos / 10 min por IP
                return
            import site_web, auth_web
            motivo = "primeiro" if path == "/primeiro-acesso" else "esqueci"
            auth_web.iniciar_definir_senha(g("whatsapp"), motivo)  # neutro (anti-enumeração)
            return self._html(site_web.pagina_msg("Verifique seu e-mail",
                "Se houver uma assinatura com esse WhatsApp, enviamos um link para você "
                + ("criar sua senha." if motivo == "primeiro" else "redefinir sua senha.")
                + " O link também segue pelo seu WhatsApp."))
        if path == "/criar-senha":
            import site_web, auth_web
            tok = g("token")
            status, sess = auth_web.definir_senha(tok, g("senha"), g("senha2"))
            if status == "ok":
                return self._redirect("/artigos", token=sess)
            if status == "token_invalido":
                return self._html(site_web.pagina_msg("Link inválido ou expirado",
                    "Peça um novo link em 'Primeiro acesso' ou 'Esqueci minha senha'."))
            msgs = {"nao_confere": "As senhas não conferem. Digite a mesma senha nos dois campos.",
                    "fraca": "Senha fraca. Use pelo menos 6 caracteres, com letra e número."}
            return self._html(site_web.pagina_criar_senha(tok, erro=msgs.get(status, "Tente novamente.")))
        if path == "/assinar/cupom":
            # Registrada ANTES do bloco "/assinar" pra não ser engolida por ele.
            # Prévia LEITURA-ONLY: nunca escreve no banco (não consome cupom, não
            # cria assinante) — só devolve o que o fechamento cobraria. Reusa
            # `pricing.base_cobrada` (o mesmo cálculo do checkout) de propósito: uma
            # cópia divergente prometeria um preço na tela e cobraria outro no Asaas.
            import config, db, pricing, rate_limit, subscribers
            ip = self._ip_cliente()
            if not self._mesma_origem():
                return self._json({"ok": False, "msg": "Requisição inválida."}, 403)
            plano = config.plano_por_slug(g("plano"))
            if not plano:
                return self._json({"ok": False, "msg": "Plano inválido."}, 400)
            cupom = g("cupom").strip().upper()
            if not cupom:
                # Campo em branco NÃO é tentativa e nem chega a consultar nada (Important
                # da revisão final): antes, "" caía em `cupom_desconto("")` -> 0.0 ->
                # contava tentativa, então 5 cliques no Aplicar com o campo vazio
                # esgotavam a cota do PRÓPRIO visitante e o cupom BOM dele passava a ser
                # recusado — na prévia e no fechamento.
                return self._json({"ok": False, "msg": "Digite um cupom."})
            chave = f"cupom:{ip}"
            # CONTAR-E-PERDOA (fix do CRITICAL da revisão final). Antes: PEEK aqui +
            # `registrar_tentativa` depois do lookup -> sob ThreadingHTTPServer a
            # rajada inteira lia contagem 0 e passava (50/50 medidos, teto 5). Agora
            # `limitado` conta e checa na MESMA seção crítica, e a cota é DEVOLVIDA
            # (`perdoar_tentativa`) se o cupom se revelar válido — as duas propriedades
            # juntas, sem janela entre checar e contar.
            # Mesma chave ("cupom:<ip>") do checkout (`_post_assinar`) DE PROPÓSITO: as
            # duas rotas compartilham UM balde de cota — senão um atacante ganharia 5
            # tentativas grátis aqui (a prévia, mais barata/rápida) e mais 5 no
            # checkout, dobrando o orçamento de chute.
            if rate_limit.limitado(chave, 5, 600):
                return self._json({"ok": False, "bloqueado": True,
                                   "msg": "Muitas tentativas. Tente de novo em alguns minutos."})
            db.init()
            metodo = "PIX" if (g("metodo") or "").upper() == "PIX" else "CARTAO"
            # AS DUAS consultas, SEMPRE, na MESMA ordem, pra qualquer código — inclusive
            # quando a primeira já resolveu. É o que mantém indistinguíveis as classes de
            # falha (inexistente / inativo / CORTESIA / escopo de outro plano): mesmo
            # status, mesmo corpo, mesma mensagem e MESMO TEMPO (2 lookups indexados).
            # Consultar afiliado só quando `desconto <= 0` daria o mesmo tempo entre as 4
            # falhas, mas criaria diferença entre válido e inválido; incondicional não
            # cria diferença nenhuma. `cupom_desconto` devolve 0.0 pras 4 classes e
            # `afiliado_por_codigo` devolve None pra inexistente E inativo.
            desconto = db.cupom_desconto(cupom, plano["slug"])
            af = db.afiliado_por_codigo(cupom)
            if desconto <= 0 and not af:
                return self._json({"ok": False, "msg": "Cupom inválido."})
            # Código bom não gasta cota de quem o digitou (a tentativa contada acima é
            # devolvida aqui, depois de a validade estar decidida).
            rate_limit.perdoar_tentativa(chave)
            # Base VIGENTE, do mesmo jeito que o fechamento (`_post_assinar`): preço
            # pós-founder quando o limite de ativos já passou, override do admin quando
            # existe (`config.plano_por_slug` já resolve o override). `plano["base"]`
            # cru coincide hoje, mas divergiria justamente na classe de bug que esta
            # tela existe pra impedir: mostrar um valor e cobrar outro.
            base_vig = pricing.preco_vigente(plano, len(subscribers.ativos()))
            # Cupom de AFILIADO (D3, no ar) é desconto % e o fechamento o HONRA — a
            # prévia consultava só os promocionais, então respondia "Cupom inválido"
            # (e queimava cota) pra um código de afiliado válido. Mesma `base_cobrada`
            # do checkout, com o argumento certo: `cupom_pct` pro %, `cupom_valor` pro R$.
            # TODAS as figuras que a tela mostra, não só o resumo (fix do bug ao vivo de
            # 2026-07-29): a página exibe dinheiro em três lugares — resumo, tile do Pix
            # e dropdown de parcelas. A prévia atualizava um só, então o tile do Pix
            # ficava com o valor SEM o cupom e o dropdown chegou a oferecer o valor do
            # PIX parcelado (que não existe: Pix é à vista). `figuras_assinar` calcula as
            # três pela MESMA `base_cobrada` do fechamento, e as parcelas sempre sobre a
            # base do CARTÃO — é a única forma de as três nunca discordarem entre si.
            figs = pricing.figuras_assinar(plano, metodo, base_vig,
                                           af["pct_desconto"] if af else 0.0, desconto)
            partes = ([pricing.fmt_brl(desconto)] if desconto > 0 else []) + \
                     ([_pct_str(af["pct_desconto"])] if af else [])
            return self._json({"ok": True,
                               "msg": "−" + " −".join(partes) + " aplicado", **figs})
        if path == "/assinar":
            return self._post_assinar(g)
        if path == "/cancelar":
            return self._cancelar_motivo(g)
        if path == "/cancelar/confirmar":
            return self._cancelar_confirmar(g)
        # /aceitar-termos e o fluxo de /cancelar (+ /cancelar/confirmar) são as
        # exceções deliberadas ao gate de aceite dos termos: /aceitar-termos é o
        # próprio caminho de aceitar (bloqueá-lo prenderia o assinante sem conseguir
        # aceitar nunca), e quem quer cancelar não pode ser obrigado a aceitar termos
        # novos primeiro — ver comentário em _cancelar_motivo/_cancelar_confirmar.
        if path == "/aceitar-termos":
            return self._aceitar_termos(g)
        if path == "/meus-dados":
            return self._meus_dados_post(g)
        if path == "/renovar":
            return self._post_renovar(g)
        if path == "/trilha":
            return self._trilha_post(g)
        return self._html("<h3>rota inválida</h3>", 404)

    def _meus_dados_post(self, g):
        """POST /meus-dados: as quatro ações daqui (salvar_contato, salvar_horario,
        iniciar_troca, confirmar_troca) MUTAM dados do assinante — por isso passam
        pelo mesmo gate de aceite (`subscribers.precisa_aceitar`) que os GETs de
        /minha e /meus-dados já tinham.

        PORQUÊ: sem esta checagem aqui, um form de /meus-dados já aberto no navegador
        antes do deploy do re-aceite (ou uma requisição POST direta, sem passar pelo
        GET) continuava gravando normalmente mesmo com o aceite pendente — o bloqueio
        da área de conta valia só pra quem clicava em links, não pra quem já tinha a
        página aberta ou usava a API diretamente. Com aceite pendente, NENHUMA ação é
        executada: devolve a mesma tela de aceite que o GET devolveria."""
        import site_web, subscribers, auth_web
        sub = self._sub_logado()
        if not sub:
            return self._redirect("/entrar")
        if subscribers.precisa_aceitar(sub):
            import site_legal
            return self._html(site_legal.pagina_aceite_termos("/meus-dados"))
        acao = g("acao")
        if acao == "salvar_contato":
            subscribers.atualizar_contato(sub["id"], g("nome"), g("email"))
            return self._html(site_web.pagina_meus_dados(subscribers.por_id(sub["id"]), msg="Dados salvos."), 200)
        if acao == "salvar_horario":
            import db as _db, config as _cfg, daily as _daily
            novo = g("slot")
            atual = subscribers.slot_de(sub)
            teto = int(_db.get_config("slot_teto", str(_cfg.SLOT_TETO_DEFAULT)) or _cfg.SLOT_TETO_DEFAULT)
            if novo != atual and novo in subscribers.slots_com_vaga(teto):
                subscribers.definir_slot(sub["id"], novo)
                hoje = _daily._hoje_iso()
                if _db.slot_ja_enviou(hoje, novo):     # novo horário já disparou hoje -> catch-up
                    try:
                        _daily.enviar_catch_up(subscribers.por_id(sub["id"]))
                    except Exception as e:
                        print(f"[meus-dados] catch-up falhou: {e}", flush=True)  # não derruba a página
            sub2 = subscribers.por_id(sub["id"])
            atual2 = subscribers.slot_de(sub2)
            return self._html(site_web.pagina_meus_dados(
                sub2, msg="Horário salvo.",
                slots=subscribers.slots_com_vaga(teto, atual2), slot_atual=atual2), 200)
        if acao == "iniciar_troca":
            if not self._rate_ok("otp", 5, 600):
                return
            r = auth_web.iniciar_troca_numero(sub["id"], g("novo_numero"))
            if r == "enviado":
                return self._html(site_web.pagina_meus_dados(sub, etapa_troca="codigo", novo_num=g("novo_numero")), 200)
            msg = "Número inválido." if r == "invalido" else "Esse número já é de outro assinante."
            return self._html(site_web.pagina_meus_dados(sub, msg=msg), 200)
        if acao == "confirmar_troca":
            if not self._rate_ok("otp", 5, 600):
                return
            st = auth_web.confirmar_troca_numero(sub["id"], g("novo_numero"), g("codigo"))
            if st == "ok":
                return self._html(site_web.pagina_meus_dados(subscribers.por_id(sub["id"]), msg="Número atualizado."), 200)
            erros = {"codigo_errado": "Código errado.", "expirado": "Código expirado, tente de novo.",
                     "bloqueado": "Muitas tentativas, peça um novo código."}
            return self._html(site_web.pagina_meus_dados(sub, etapa_troca="codigo",
                              novo_num=g("novo_numero"), msg=erros.get(st, "Não deu.")), 200)
        return self._redirect("/meus-dados")

    def _trilha_post(self, g):
        """POST /trilha: `marcar_feito` MUTA dado do assinante (trilha_envios.feito_em)
        — mesmo gate de aceite que `_meus_dados_post` usa, pelo mesmo motivo: sem esta
        checagem aqui, aceite pendente não impede a mutação, só o link direto pra cá
        (ver docstring de `_meus_dados_post` pro cenário completo)."""
        import subscribers
        sub = self._sub_logado()
        if not sub:
            return self._redirect("/entrar")
        if subscribers.precisa_aceitar(sub):
            import site_legal
            return self._html(site_legal.pagina_aceite_termos("/trilha"))
        msg = ""
        if g("acao") == "marcar_feito":
            numero = _trilha_numero_valido(g("numero"))
            if numero:
                import db as _db
                if _db.trilha_marcar_feito(sub["id"], numero):
                    msg = "Marcado. Bom trabalho."
        return self._html(self._pagina_trilha(sub, msg=msg))

    def _sub_logado(self):
        import subscribers
        sess = self._sessao()
        if not sess:
            return None
        return subscribers.por_whatsapp(sess["whatsapp"])

    def _pagina_trilha(self, sub, msg=""):
        """Monta os itens da trilha do assinante (peça atual + anteriores)."""
        import db as _db, site_web as _sw, trilha as _trilha

        def _slug_disponivel(slug):
            # só afirma a ferramenta se o ARQUIVO existir -- a peça pode declarar
            # `ferramenta:` no cabeçalho antes do arquivo ser subido em
            # seed/trilha/ferramentas/ (Important 4 da revisão: 7 das 12 peças
            # declaram ferramenta e o diretório só tinha .gitkeep). Sem esta
            # checagem, `pagina_trilha` mostra "📎 Baixar" e a rota /ferramentas/
            # devolve 404.
            return slug if slug and _trilha.caminho_ferramenta(slug) else ""

        itens = []
        atual = _trilha.proxima_peca(sub["id"])
        vistos = set()
        for env in _db.trilha_historico(sub["id"]):
            p = _db.trilha_peca(env["numero"]) or {}
            itens.append({"numero": env["numero"], "titulo": p.get("titulo", ""),
                          "feito": bool(env.get("feito_em")),
                          "ferramenta_slug": _slug_disponivel(p.get("ferramenta_slug", "")),
                          "entregue": True})
            vistos.add(env["numero"])
        if atual and atual["numero"] not in vistos:
            # ainda não recebeu por WhatsApp (entrou hoje): mostra o que vem aí, mas
            # `entregue=False` — marcar "fiz" antes do envio real sempre devolveria
            # False em silêncio (não existe linha em trilha_envios pra essa peça
            # ainda), e o botão viraria decoração morta. `pagina_trilha` usa essa
            # chave pra trocar o botão por um aviso de "chega no sábado".
            itens.insert(0, {"numero": atual["numero"], "titulo": atual.get("titulo", ""),
                             "feito": False,
                             "ferramenta_slug": _slug_disponivel(atual.get("ferramenta_slug", "")),
                             "entregue": False})
        return _sw.pagina_trilha(sub, itens, msg=msg)

    def _parse_multipart(self, ctype, body):
        """Parser mínimo de multipart/form-data. Retorna (campos:dict, arquivos:{nome:(filename,bytes)})."""
        import re
        m = re.search(r'boundary=([^;]+)', ctype)
        if not m:
            return {}, {}
        boundary = ("--" + m.group(1).strip().strip('"')).encode()
        campos, arquivos = {}, {}
        for parte in body.split(boundary):
            parte = parte.strip(b"\r\n")
            if not parte or parte == b"--" or b"\r\n\r\n" not in parte:
                continue
            cab, dados = parte.split(b"\r\n\r\n", 1)
            cab_s = cab.decode("utf-8", "replace")
            nome = re.search(r'name="([^"]*)"', cab_s)
            if not nome:
                continue
            fnm = re.search(r'filename="([^"]*)"', cab_s)
            if fnm and fnm.group(1):
                arquivos[nome.group(1)] = (fnm.group(1), dados)
            else:
                campos[nome.group(1)] = dados.decode("utf-8", "replace")
        return campos, arquivos

    def _curadoria_upload(self, raw, ctype):
        """POST /curadoria com PDF (ou texto colado) -> gera resumo -> fila com prioridade."""
        import config, db, curadoria
        campos, arquivos = self._parse_multipart(ctype, raw)
        if not config.ADMIN_TOKEN or campos.get("token") != config.ADMIN_TOKEN:
            return self._html("<h3>Acesso negado</h3>", 403)
        db.init()
        msg = ""
        try:
            texto = ""
            _, pdf = arquivos.get("pdf", (None, None))
            if pdf:
                texto = curadoria.extrair_texto_pdf(pdf)
            if not (texto or "").strip():
                texto = campos.get("texto", "")     # fallback: colado
            if not (texto or "").strip():
                msg = "Envie um PDF com texto selecionável, ou cole o resumo do estudo."
            else:
                _, tit = curadoria.adicionar_meu_estudo(
                    texto, titulo=campos.get("titulo", ""), fonte=campos.get("fonte", ""),
                    doi=campos.get("doi", ""))
                msg = f"✅ Adicionado à fila (prioridade): {tit}"
        except ValueError as e:
            msg = str(e)                            # motivo claro p/ o Diego (ex.: PDF sem texto)
        except Exception as e:
            print(f"[curadoria] adicionar meu estudo erro: {e}", flush=True)
            msg = "Falha ao processar o estudo (ver logs)."
        import urllib.parse as _up
        return self._redirect(f"/curadoria?token={config.ADMIN_TOKEN}&msg={_up.quote(msg)}")

    def _series_upload(self, raw, ctype):
        """POST /series (multipart) -> adicionar meu estudo à reserva e à série aberta."""
        import config, db, curadoria, auth_web
        campos, arquivos = self._parse_multipart(ctype, raw)
        sess = self._sessao()
        token_ok = bool(config.ADMIN_TOKEN) and campos.get("token") == config.ADMIN_TOKEN
        if not (token_ok or (sess and auth_web.eh_admin(sess["whatsapp"]))):
            return self._html("<h3>Acesso negado</h3>", 403)
        db.init()
        sid = campos.get("serie", "")
        msg = ""
        try:
            texto = ""
            _, pdf = arquivos.get("pdf", (None, None))
            if pdf:
                texto = curadoria.extrair_texto_pdf(pdf)
            if not (texto or "").strip():
                texto = campos.get("texto", "")     # fallback: colado
            if not (texto or "").strip():
                msg = "Envie um PDF com texto selecionável, ou cole o resumo do estudo."
            else:
                rid, tit = curadoria.adicionar_meu_estudo(texto, titulo=campos.get("titulo", ""))
                db.adicionar_serie_item(sid, "reserva", rid, titulo=tit, tema="Meus estudos")
                msg = f"✅ Adicionado à série: {tit}"
        except ValueError as e:
            msg = str(e)                            # motivo claro p/ o Diego (ex.: PDF sem texto)
        except Exception as e:
            print(f"[series] add meu estudo erro: {e}", flush=True)
            msg = "Falha ao processar o estudo (ver logs)."
        import urllib.parse as _up
        return self._redirect(f"/series?serie={_up.quote(sid)}&token={config.ADMIN_TOKEN}&msg={_up.quote(msg)}")

    # B4 (revisão final #2): `asaas.montar_checkout` monta TODO checkout de cartão como
    # `chargeTypes: ["RECURRENT"]`. Quem já tem `asaas_subscription_id` (cartão à vista) já é
    # cobrado sozinho pelo Asaas — passar por /renovar criava uma SEGUNDA assinatura
    # recorrente, cobrando duas vezes para sempre. É o mesmo estrago que o c6b7466 evita do
    # lado do webhook (gravar o subscription_id para a régua NÃO chamar esse assinante para
    # renovar); a rota é a outra porta do mesmo problema.
    def _get_rota_renovar(self):
        """Tela de renovação do próprio assinante. Preço é sempre o CONTRATADO
        (renovacao.preco_renovacao), nunca o de tabela, e sem campo de cupom: o desconto de
        afiliado vale só na 1ª venda.

        Existe porque o checkout de /assinar recusa quem ainda TEM acesso — sem esta rota os
        avisos da régua mandavam o cliente para uma tela que o bloqueava."""
        import site_web, subscribers as _s, config as _c, renovacao as _r, pricing as _p
        sub = self._sub_logado()
        if not sub:
            return self._redirect("/entrar")
        if sub.get("asaas_subscription_id"):
            return self._html(site_web.pagina_msg("Renovação automática",
                                                  AVISO_JA_RECORRENTE, logado=True))
        plano = _c.plano_por_slug(sub.get("plano", "")) or {}
        if not plano:
            return self._redirect("/minha")
        preco = _r.preco_renovacao(sub, plano)
        expirado = not _s.tem_acesso(sub)
        return self._html(site_web.pagina_renovar(
            sub, plano,
            _p.base_cobrada(plano, "PIX", preco, 0.0),
            _p.base_cobrada(plano, "CARTAO", preco, 0.0),
            sub.get("proximo_vencimento"), bonus=expirado))

    def _post_renovar(self, g):
        """Monta o checkout da renovação. Sem cupom: o desconto de afiliado é só na 1ª venda.
        Preço vem de `renovacao.preco_renovacao` (o CONTRATADO), nunca do preço de tabela."""
        import site_web, config, db, subscribers, pricing, renovacao, asaas
        sub = self._sub_logado()
        if not sub:
            return self._redirect("/entrar")
        if sub.get("asaas_subscription_id"):
            # Mesma guarda do GET, no POST: sem ela, um form antigo em cache ou um POST
            # direto ainda criaria a 2ª assinatura recorrente.
            return self._html(site_web.pagina_msg("Renovação automática",
                                                  AVISO_JA_RECORRENTE, logado=True))
        plano = config.plano_por_slug(sub.get("plano", "")) or {}
        if not plano:
            return self._redirect("/minha")
        metodo = "CARTAO" if g("metodo").upper() == "CARTAO" else "PIX"
        preco = renovacao.preco_renovacao(sub, plano)
        base_final = pricing.base_cobrada(plano, metodo, preco, 0.0)
        dados = {"nome": sub.get("nome", ""), "email": sub.get("email", ""),
                 "cpf": sub.get("cpf", ""), "whatsapp": sub.get("whatsapp", "")}
        token = db.criar_pending({**dados, "plano": plano["slug"], "metodo": metodo,
                                  "parcelas": 1, "valor": base_final, "valor_base": preco,
                                  "afiliado_codigo": ""})
        try:
            payload = asaas.montar_checkout(plano, metodo, 1, dados, token,
                                            config.PUBLIC_URL, base=base_final)
            res = asaas.criar_checkout(payload)
            if not res.get("url"):
                raise RuntimeError("checkout sem url")
            return self._redirect(res["url"])
        except Exception as e:
            print(f"[renovar] checkout falhou: {e}", flush=True)
            expirado = not subscribers.tem_acesso(sub)
            return self._html(site_web.pagina_renovar(
                sub, plano, pricing.base_cobrada(plano, "PIX", preco, 0.0),
                pricing.base_cobrada(plano, "CARTAO", preco, 0.0),
                sub.get("proximo_vencimento"), bonus=expirado,
                erro="Não conseguimos iniciar o pagamento agora. Tente novamente em instantes."))

    def _aceitar_termos(self, g):
        """Exceção deliberada ao gate: esta rota É o próprio caminho de aceitar os
        termos, então não pode exigir `precisa_aceitar` == False como pré-condição —
        isso prenderia o assinante pendente num loop sem saída."""
        import subscribers, legal, site_legal
        sub = self._sub_logado()
        if not sub:
            return self._redirect("/entrar")
        if g("aceito") != "1":
            return self._html(site_legal.pagina_aceite_termos(_destino_seguro(g("destino"))))
        ip = self._ip_cliente()
        subscribers.registrar_aceite(sub["id"], legal.VERSAO, ip)
        return self._redirect(_destino_seguro(g("destino")))

    def _cancelar_motivo(self, g):
        """Passo 1 do cancelamento. Exceção deliberada ao gate de aceite dos termos:
        `sub` vem de `_sub_logado()` sem checar `subscribers.precisa_aceitar` — quem
        quer sair da assinatura não pode ficar preso tendo que aceitar termos novos
        primeiro. Isso vale pra todo o fluxo de cancelamento (aqui e em
        `_cancelar_confirmar`), que é o único jeito de sair sem depender do suporte."""
        import site_web, subscribers
        sub = self._sub_logado()
        if not sub:
            return self._redirect("/entrar")
        motivo = g("motivo").strip()
        if not motivo:
            return self._html(site_web.pagina_cancelar("Conta pra gente o motivo — é obrigatório."))
        if sub.get("oferta_retencao_em"):          # já usou a oferta -> cancela direto
            return self._executar_cancelamento(sub, motivo)
        if not subscribers.tem_acesso(sub):
            # Revisão #3: a oferta de retenção é "fique mais 30 dias" — só faz sentido para
            # quem TEM acesso a manter. Sem esta guarda ela era exibida (e aceita) por quem
            # já tinha o acesso cortado, inclusive por estorno/chargeback (SUSPENDER grava
            # CANCELADO sem `cancelado_em`, e a sessão continua válida): virava reativação
            # self-service de graça. E para quem simplesmente venceu, o "+30 dias" contava de
            # uma data já passada e entregava ZERO — a mesma promessa vazia do B11 —
            # queimando de vez a única oferta a que ele tinha direito.
            return self._executar_cancelamento(sub, motivo)
        return self._html(site_web.pagina_cancelar_oferta(motivo))

    def _cancelar_confirmar(self, g):
        """Passo 2 do cancelamento (aceitar oferta de retenção OU confirmar de vez).
        Mesma exceção deliberada de `_cancelar_motivo`: sem gate de aceite — quem está
        cancelando não pode ser barrado por termos pendentes."""
        import site_web, subscribers, asaas
        from datetime import datetime, timedelta
        sub = self._sub_logado()
        if not sub:
            return self._redirect("/entrar")
        motivo = g("motivo").strip()
        if g("acao") == "aceitar":
            if sub.get("oferta_retencao_em"):
                # B8: a oferta é uma vez por assinante. A checagem existia só em
                # `_cancelar_motivo`, que decide EXIBIR — um POST repetido empurrava +30 dias
                # a cada chamada, sem limite (acesso grátis ilimitado no cartão à vista).
                # Idempotente de propósito: mostra a mesma página, não concede de novo e NÃO
                # cancela — o cliente clicou justamente para não cancelar.
                return self._html(site_web.pagina_oferta_aceita())
            if not subscribers.tem_acesso(sub):
                # Mesma guarda do passo 1, aqui no POST que de fato concede — senão um POST
                # direto (ou o botão Voltar do navegador sobre o form antigo) contornava.
                # NÃO cancela: este ramo é o do botão "Quero meu mês grátis", e cancelar aqui
                # faria exatamente o contrário do que o cliente pediu — com `cancelado_em`
                # gravado (que trava qualquer cancelamento futuro), e-mail de cancelamento e,
                # dentro dos 7 dias, estorno automático. Alcançável quando o acesso vence
                # entre a tela e o clique, ou quando um chargeback cai no meio do fluxo.
                return self._html(site_web.pagina_msg(
                    "Oferta indisponível",
                    "Esta oferta vale enquanto a assinatura está ativa, e o seu acesso já "
                    "terminou. Para voltar, é só refazer a assinatura — o valor é o mesmo "
                    "que você já contratava.", logado=True))
            sid = sub.get("asaas_subscription_id")
            try:
                if sid:
                    asaas.adiar_vencimento(sid, 30)
            except Exception as e:
                print(f"[cancelar] adiar vencimento falhou: {e}", flush=True)
            # B11: `acesso_ate` é o campo que controla o acesso de quem NÃO tem assinatura
            # recorrente (Pix e cartão parcelado, desde o dbb6dde). Gravar só o
            # `proximo_vencimento` fazia a tela prometer "+30 dias" e entregar ZERO: o
            # cliente desistia do cancelamento, deixava a janela de arrependimento correr e
            # perdia o acesso na data original. Com assinatura recorrente é o contrário —
            # `acesso_ate` fica NULL de propósito e quem manda é o ciclo do Asaas.
            base = (sub.get("acesso_ate") if not sid else None) or sub.get("proximo_vencimento")
            try:
                ref = datetime.fromisoformat(base) if base else datetime.now()
            except Exception:
                ref = datetime.now()
            # Piso em hoje: estender a partir de uma data já passada devolveria menos de 30
            # dias — ou nenhum — enquanto a tela promete "+30 dias".
            ref = max(ref, datetime.now())
            novo = (ref + timedelta(days=30)).date().isoformat()
            extra = {} if sid else {"acesso_ate": novo}
            subscribers.marcar_status(sub["id"], "ATIVO",
                                      oferta_retencao_em=datetime.now().isoformat(),
                                      proximo_vencimento=novo, **extra)
            return self._html(site_web.pagina_oferta_aceita())
        return self._executar_cancelamento(sub, motivo)

    def _executar_cancelamento(self, sub, motivo):
        """Cancela a assinatura. A gravação do cancelamento vem PRIMEIRO e inteira
        (db.claim_cancelamento), e é ela mesma o claim contra corrida; o estorno é um
        ajuste posterior.

        PORQUÊ nesta ordem: duplo clique em /cancelar/confirmar (servidor
        ThreadingMixIn) ou um re-submit sequencial (a sessão continua válida depois de
        cancelar) chamam este método mais de uma vez para o mesmo assinante. Enquanto
        o claim era só uma marca prévia e o estado final era gravado no fim, existia
        uma janela entre "reservei" e "existe": toda falha dentro dela deixava o
        assinante marcado (logo, incapaz de cancelar de novo) e sem cancelamento
        registrado. Agora ou o cancelamento está inteiro no banco, ou nada aconteceu.
        """
        import site_web, asaas, db, subscribers
        acesso_ate = sub.get("proximo_vencimento")   # padrão: acesso até o fim do período pago
        estado = _gravar_cancelamento(sub, motivo, acesso_ate)
        if estado == "perdeu":
            # Outra chamada já cancelou este assinante (e já estornou/emailou, se era o
            # caso). Nada a repetir: só mostra o que está PERSISTIDO — relendo do banco,
            # porque o `sub` em memória é anterior ao cancelamento da outra chamada e
            # traria o acesso_ate errado.
            return self._html(site_web.pagina_cancelado(_acesso_ate_persistido(sub)))
        sid = sub.get("asaas_subscription_id")
        if sid:
            asaas_ok = False
            try:
                asaas.cancelar_assinatura(sid)
                asaas_ok = True
            except Exception as e:
                # Alerta, não só log: a assinatura pode seguir cobrando em silêncio e o
                # cliente não consegue mais tentar (o cancelamento já está gravado, então
                # uma nova tentativa dele perderia o claim e não chamaria o Asaas de novo).
                print(f"[cancelar] cancelar assinatura Asaas falhou: {e}", flush=True)
                _alertar(sub, f"cancelamento de {sub.get('nome') or sub.get('id')} gravado, mas a "
                              f"assinatura NÃO foi cancelada no Asaas ({e}) — cancele manualmente, "
                              f"senão ela continua cobrando")
            if asaas_ok:
                # A recorrência não existe mais, então o campo não pode continuar apontando
                # pra ela: é esse id que diz "já renova sozinho", e tanto `regua.na_regua`
                # quanto o guard do /renovar leem exatamente ele. Mantê-lo deixava quem
                # cancelou fora dos avisos de vencimento PARA SEMPRE e ouvindo "sua assinatura
                # já renova automaticamente" ao tentar voltar. Quando o cancelamento no Asaas
                # FALHA o campo é preservado de propósito: a assinatura pode seguir cobrando,
                # e deixar esse cliente montar um segundo checkout RECURRENT seria cobrança em
                # dobro — o estrago que o B4 existe para evitar.
                # Fora do try do Asaas de propósito: uma falha AQUI não é "não cancelei no
                # Asaas" e não pode disparar aquele alerta, que diria o contrário do ocorrido.
                # "CANCELADO" literal e não `sub["status"]`: `sub` é o dicionário de ANTES do
                # claim, e repassá-lo desfaria o cancelamento recém-gravado.
                try:
                    subscribers.marcar_status(sub["id"], "CANCELADO", asaas_subscription_id=None)
                except Exception as e:
                    print(f"[cancelar] limpar subscription_id falhou: {e}", flush=True)
        # Estorno só quando temos CERTEZA do estado gravado. Em "incerto" (banco falhou e
        # não deu pra confirmar) o dinheiro não se move — regra global.
        resultado = estornar_arrependimento(sub) if estado == "venceu" else None
        estornado, tipo_estorno = resultado if resultado is not None else (None, None)
        if estornado is not None:              # 0.0 é estorno válido, não "sem estorno"
            acesso_ate = None                   # reembolsou integral -> acesso cessa agora
            try:
                db.encerrar_acesso(sub["id"])
            except Exception as e:
                # O cancelamento já está gravado e correto; só o ajuste do acesso ficou
                # pendente. Nunca pode derrubar a resposta — vira alerta.
                print(f"[cancelar] encerrar_acesso falhou após estorno OK: {e}", flush=True)
                _alertar(sub, f"estorno de {sub.get('nome') or sub.get('id')} CONCLUÍDO, mas não "
                              f"consegui encerrar o acesso no cadastro ({e}) — zere o 'acesso até' "
                              f"manualmente")
        _avisar_cancelamento(sub, estornado, tipo_estorno, acesso_ate)
        return self._html(site_web.pagina_cancelado(acesso_ate))

    def _post_assinar(self, g):
        import site_web, config, db, subscribers, pricing, asaas, legal, renovacao, cpf as cpfval, phone, rate_limit
        plano = config.plano_por_slug(g("plano"))
        if not plano:
            return self._html(site_web.pagina_assinar(None, "Plano inválido — escolha de novo."), 400)
        # Validar número local antes de montar E.164 (evita que "+55" vazio passe)
        local_whatsapp = g("whatsapp").strip()
        dados = {"nome": g("nome").strip(), "email": g("email").strip(),
                 "cpf": g("cpf").strip(),
                 "whatsapp": phone.montar_e164(g("pais_dial") or "55", local_whatsapp) if local_whatsapp else ""}
        if not (dados["nome"] and dados["whatsapp"] and dados["email"] and dados["cpf"]):
            return self._html(site_web.pagina_assinar(plano["slug"], "Preencha nome, e-mail, WhatsApp e CPF."))
        if not cpfval.valida(dados["cpf"]):
            return self._html(site_web.pagina_assinar(plano["slug"], "CPF inválido — confira os números."))
        if g("aceito") != "1":
            # Gate ANTES de qualquer criação (pending ou assinante direto via cupom de
            # cortesia, logo abaixo) — sem aceite não existe cadastro, em caminho nenhum.
            return self._html(site_web.pagina_assinar(
                plano["slug"], "É preciso aceitar os Termos e a Política de Privacidade."))
        # Mesmo padrão de _aceitar_termos: atrás de proxy, o IP real vem no cabeçalho.
        ip_cliente = self._ip_cliente()
        dados["cpf"] = cpfval.so_digitos(dados["cpf"])          # guarda só os dígitos
        ja = subscribers.por_cpf(dados["cpf"]) or subscribers.por_whatsapp(dados["whatsapp"])
        if ja and subscribers.tem_acesso(ja):                   # já tem assinatura ativa -> não duplica
            return self._html(site_web.pagina_assinar(plano["slug"],
                "Já existe uma assinatura ativa com esse CPF ou WhatsApp. Se for você, entre em /entrar."))
        metodo = "CARTAO" if g("metodo").upper() == "CARTAO" else "PIX"
        try:
            parcelas = max(1, min(12, int(g("parcelas") or "1")))
        except ValueError:
            parcelas = 1
        cupom = g("cupom").strip()
        chave_cupom = f"cupom:{ip_cliente}"
        # Fecha o oráculo de força-bruta: um cupom não-vazio só é avaliado se o IP
        # ainda tem cota. Cupom vazio (a maioria das compras) nunca passa por aqui —
        # não é tentativa, não pode ser barrado.
        # CONTAR-E-PERDOA (fix do CRITICAL da revisão final): `limitado` conta e checa
        # ATOMICAMENTE, na mesma seção crítica, e a cota é devolvida
        # (`perdoar_tentativa`) nos dois caminhos de cupom VÁLIDO abaixo (cortesia e
        # promocional/afiliado) — um código bom continua não gastando cota de quem o
        # digitou. Antes era PEEK aqui + registro depois do lookup: sob
        # ThreadingHTTPServer a rajada inteira lia contagem 0 e passava (40/40 medidos,
        # teto 5), e este é o caminho em que um cupom de CORTESIA acertado vira
        # assinante ATIVO na hora, sem Asaas — acesso de graça.
        # Mesma chave ("cupom:<ip>") da prévia em /assinar/cupom (do_POST) DE PROPÓSITO:
        # as duas rotas compartilham UM balde — senão um atacante ganharia 5
        # tentativas na prévia (mais barata) e mais 5 aqui, dobrando de graça o
        # orçamento de chute.
        if cupom and rate_limit.limitado(chave_cupom, 5, 600):
            return self._html(site_web.pagina_assinar(
                plano["slug"], "Muitas tentativas com código de cupom. Aguarde alguns "
                                "minutos e tente novamente."))
        _cup = db.obter_cupom(cupom) if cupom else None
        # Cortesia = cupom ATIVO sem desconto_valor (dias grátis, sem Asaas). Um cupom
        # PROMOCIONAL (desconto_valor>0, ex.: LANCAMENTO) também é "válido" mas NUNCA pode
        # cair aqui — senão vira acesso grátis no plano pago. Só o caminho pago abaixo
        # aplica o desconto fixo do promocional.
        _eh_cortesia = bool(_cup and _cup.get("ativo") and float(_cup.get("desconto_valor") or 0) == 0)
        # Cupom de cortesia: ativa na hora, sem Asaas
        if cupom and _eh_cortesia:
            # Cortesia é cupom VÁLIDO: devolve a cota contada acima (quem recebeu uma
            # cortesia legítima não pode gastar tentativa por usá-la).
            rate_limit.perdoar_tentativa(chave_cupom)
            info = _cup
            reg = subscribers.criar_de_pagamento(
                {**dados, "plano": plano["slug"], "metodo": "CUPOM",
                 "termos_versao": legal.VERSAO, "termos_ip": ip_cliente}, {}, status="ATIVO")
            dias = int(info.get("dias_acesso") or 0)
            if dias > 0:                       # cortesia com prazo -> define o fim do acesso
                from datetime import datetime, timedelta
                subscribers.marcar_status(reg["id"], "ATIVO",
                                          acesso_ate=(datetime.now() + timedelta(days=dias)).isoformat())
            db.consumir_cupom(cupom)          # gasta o cupom (uso único desativa)
            try:
                import deliver
                deliver.enviar_texto(subscribers._norm(dados["whatsapp"]),
                    f"✅ Cadastro liberado (cortesia)! Bem-vindo(a) à Atualização Científica.\n\n"
                    f"Entre em {config.PUBLIC_URL}/entrar com este WhatsApp e peça o código.")
            except Exception as e:
                print(f"[assinar] boas-vindas cupom falhou: {e}", flush=True)
            return self._redirect("/obrigado")
        # Pagamento via checkout Asaas
        n_ativos = len(subscribers.ativos())
        # `ja` truthy e chegou até aqui = existe, mas SEM acesso vigente (quem tem
        # acesso já foi bloqueado acima) — é recontratação, não venda nova. Cobra o
        # valor que o assinante CONTRATOU (renovacao.preco_renovacao), não o de tabela
        # do momento: é a mesma promessa da cláusula 2 dos termos ("pelo mesmo valor
        # contratado"), só que pela porta pública em vez da /renovar autenticada.
        base_vig = renovacao.preco_renovacao(ja, plano) if ja else pricing.preco_vigente(plano, n_ativos)
        # Cupom promocional (ex.: LANCAMENTO): desconto FIXO em R$, escopado por plano — não
        # gera comissão (só afiliado gera). Cupom de afiliado: 10% off na 1ª venda + atribuição.
        # Mutuamente exclusivos na prática (mesmo campo `cupom`), mas base_cobrada aceita os dois.
        promo_valor = db.cupom_desconto(cupom, plano["slug"]) if cupom else 0.0
        af = db.afiliado_por_codigo(cupom) if cupom else None
        af_codigo = af["codigo"] if af else ""
        if cupom and (promo_valor > 0 or af):
            # Código bom (promocional ou afiliado): devolve a cota contada lá em cima —
            # um cupom válido nunca gasta tentativa de quem o digitou. O caminho de
            # cupom que não serve pra nada (nem cortesia, nem promocional, nem afiliado)
            # é justamente o que NÃO perdoa: a tentativa fica contada.
            rate_limit.perdoar_tentativa(chave_cupom)
        base_final = pricing.base_cobrada(plano, metodo, base_vig,
                                          af["pct_desconto"] if af else 0.0, promo_valor)
        valor = pricing.valor_cartao(base_final, parcelas) if metodo == "CARTAO" else base_final
        # `valor_base` é a BASE contratada (pré-desconto de método, pré-cupom): é ela que o
        # webhook grava em `valor_contratado` e que a renovação usa como preço — continua
        # `base_vig` (preço de tabela) tanto pro cupom de afiliado quanto pro promocional, então
        # a renovação cobra o valor cheio (o desconto de lançamento não se repete no ciclo 2).
        # `valor` (o que o cliente paga) não serve: no parcelado o Asaas confirma parcela por
        # parcela e no Pix já vem com 5% off, que a renovação reaplicaria a cada ciclo.
        token = db.criar_pending({**dados, "plano": plano["slug"], "metodo": metodo,
                                  "parcelas": parcelas, "valor": valor, "valor_base": base_vig,
                                  "afiliado_codigo": af_codigo,
                                  "termos_versao": legal.VERSAO, "termos_ip": ip_cliente})
        if promo_valor > 0:
            try:
                db.consumir_cupom(cupom)      # marca uso (multi-uso segue ativo; uso único desativa)
            except Exception as e:
                print(f"[assinar] consumir cupom promo falhou: {e}", flush=True)
        try:
            payload = asaas.montar_checkout(plano, metodo, parcelas, dados, token, config.PUBLIC_URL, base=base_final)
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


def _alertar(sub, motivo):
    """Avisa o admin sobre um cancelamento que precisa de mão humana. À prova de
    exceção: alerta é aviso, nunca pode derrubar o cancelamento de quem está na tela."""
    try:
        import webhook_asaas
        webhook_asaas._alertar_admin(sub.get("asaas_payment_id"), sub.get("asaas_subscription_id"), motivo)
    except Exception as e:
        print(f"[cancelar] alerta admin falhou: {e}", flush=True)


def _gravar_cancelamento(sub, motivo, acesso_ate):
    """Grava o cancelamento inteiro (claim atômico) e classifica o resultado:

      "venceu"  -> esta chamada gravou agora; é dona do fluxo (estorno + e-mail).
      "perdeu"  -> outra chamada já cancelou este assinante; não há nada a repetir.
      "incerto" -> o banco falhou e não deu pra confirmar o que ficou gravado.

    PORQUÊ existe o "incerto": uma exceção no claim pode ter estourado ANTES ou DEPOIS
    do commit. Assumir "venceu" estornaria em cima de um cancelamento que talvez já
    tenha estornado (dinheiro devolvido duas vezes); assumir "perdeu" deixaria o
    cliente sem cancelamento nenhum. Então relê o banco: se o cancelamento está lá, foi
    "perdeu"; se não está e o banco responde, tenta gravar de novo (o UPDATE é
    condicional, repetir é seguro); só quando nem isso resolve é que vira "incerto" —
    e aí o cancelamento SEGUE (nunca travar o cliente), mas sem mover dinheiro.
    """
    import db
    try:
        return "venceu" if db.claim_cancelamento(sub["id"], motivo, acesso_ate) else "perdeu"
    except Exception as e:
        print(f"[cancelar] claim_cancelamento falhou: {e}", flush=True)
    try:
        import subscribers
        atual = subscribers.por_id(sub["id"]) or {}
    except Exception as e:
        print(f"[cancelar] releitura do assinante após falha do claim falhou: {e}", flush=True)
        _alertar(sub, f"cancelamento de {sub.get('nome') or sub.get('id')} seguiu SEM confirmação do "
                      f"banco ({e}) — confira o cadastro e, se ele estiver dentro dos 7 dias, avalie "
                      f"o estorno manualmente (não estornei para não devolver em dobro)")
        return "incerto"
    if atual.get("cancelado_em") or (atual.get("status") or "") == "CANCELADO":
        # Daqui pra frente há duas causas possíveis, e não dá pra distinguir qual foi:
        # (a) outra chamada ganhou a corrida e já tratou tudo (Asaas cancelado, e-mail
        # enviado) — nada a fazer; ou (b) foi o UPDATE desta PRÓPRIA chamada que
        # commitou e a exceção estourou DEPOIS — nesse caso ninguém cancelou no Asaas,
        # ninguém mandou e-mail, e o cliente vê "cancelado" na tela mas SEGUE sendo
        # cobrado. O custo de alertar à toa no caso (a) é bem menor que o de deixar
        # (b) passar em silêncio — por isso alerta sempre, não só quando a 2ª
        # tentativa também falha.
        _alertar(sub, f"cancelamento de {sub.get('nome') or sub.get('id')} caiu numa exceção "
                      f"no claim mas já aparece gravado no banco — pode ter sido corrida "
                      f"perdida (nada a fazer) OU o próprio UPDATE desta chamada que commitou "
                      f"antes da exceção estourar (Asaas NÃO cancelado, e-mail NÃO enviado, "
                      f"cliente pode seguir sendo cobrado) — confira o cadastro e o Asaas "
                      f"manualmente")
        return "perdeu"           # o UPDATE tinha gravado (ou outra chamada ganhou a corrida)
    try:
        return "venceu" if db.claim_cancelamento(sub["id"], motivo, acesso_ate) else "perdeu"
    except Exception as e:
        print(f"[cancelar] 2ª tentativa do claim falhou: {e}", flush=True)
        _alertar(sub, f"NÃO consegui gravar o cancelamento de {sub.get('nome') or sub.get('id')} "
                      f"({e}) — cancele no cadastro manualmente; não estornei porque o estado do "
                      f"banco não pôde ser confirmado")
        return "incerto"


def _acesso_ate_persistido(sub):
    """acesso_ate que está GRAVADO no banco (o do vencedor da corrida), não o do `sub`
    em memória — que é anterior ao cancelamento e mostraria data futura para quem já
    foi reembolsado. À prova de exceção: no pior caso mostra o que temos em memória."""
    try:
        import subscribers
        return (subscribers.por_id(sub["id"]) or sub).get("acesso_ate")
    except Exception as e:
        print(f"[cancelar] releitura p/ a página de cancelado falhou: {e}", flush=True)
        return sub.get("acesso_ate")


def _avisar_cancelamento(sub, estornado, tipo_estorno, acesso_ate):
    """Confirmação do cancelamento por WHATSAPP: versão com reembolso ou versão comum.
    À prova de exceção — o cancelamento já está gravado, um problema de envio não pode
    virar erro na tela.

    Era e-mail até 2026-08-01, e nunca chegou a ninguém: sem `RESEND_API_KEY` o
    `email_send.enviar` só logava e devolvia `skipped`, e ninguém olhava o retorno. Este
    era o ÚNICO aviso do sistema sem WhatsApp em paralelo, então quem cancelava (e às
    vezes recebia estorno) não tinha confirmação nenhuma. O corpo continua sendo montado
    em HTML porque o texto é revisado e jurídico; `site_web._sem_html` converte pra texto
    na saída, igual faz a confirmação de renovação (`webhook_asaas._confirmar_renovacao`).

    `tipo_estorno` (o mesmo de `refunds.alvo_estorno`, vindo de `estornar_arrependimento`)
    decide se o valor entra no e-mail. No cartão parcelado o Asaas estorna o
    PARCELAMENTO inteiro (ex.: R$ 997), mas `estornado` aqui é o valor de UMA parcela
    (ex.: R$ 83,08) — é o único número que a API do Asaas devolve pra essa cobrança, e
    ele não representa o total reembolsado. Imprimir esse número como "reembolso
    integral" mentiria por um fator de N parcelas. Quando `tipo_estorno == "installment"`
    o e-mail não imprime NENHUM valor — só confirma que o reembolso integral foi pedido."""
    if not sub.get("whatsapp"):
        return
    try:
        import site_web, deliver, pricing
        if estornado is not None:            # 0.0 é estorno válido, não "sem estorno"
            if tipo_estorno == "installment":
                linha_valor = "O reembolso integral do valor pago foi solicitado"
            else:
                linha_valor = (f"O reembolso integral de <strong>{pricing.fmt_brl(estornado)}"
                               f"</strong> foi solicitado")
            corpo = (f"<p>Confirmamos o cancelamento da sua assinatura da Atualização "
                     f"Científica dentro do prazo de arrependimento.</p>"
                     f"<p>{linha_valor} e aparece em até 10 dias úteis, conforme o meio de "
                     f"pagamento utilizado.</p>")
        else:
            ate = f" Seu acesso segue até {acesso_ate}." if acesso_ate else ""
            corpo = (f"<p>Confirmamos o cancelamento da sua assinatura da Atualização "
                     f"Científica. Não haverá novas cobranças.{site_web._esc(ate)}</p>")
        html = (f"<p>Olá {site_web._esc(sub.get('nome') or '')},</p>{corpo}"
                f"<p>Se mudar de ideia, é só assinar de novo quando quiser.</p>"
                f"<p>— Dr. Diego Silva · CRM-PR 54310</p>")
        deliver.enviar_texto(sub["whatsapp"], site_web._sem_html(html))
    except Exception as e:
        print(f"[cancelar] confirmação de cancelamento falhou: {e}", flush=True)


# Status do Asaas que significam "o estorno existe" numa re-consulta. PARTIALLY_REFUNDED
# fica DE FORA de propósito: nosso estorno é sempre integral, então devolução parcial é
# sinal de que algo diferente aconteceu e precisa de olho humano.
_STATUS_ESTORNADO = ("REFUNDED", "REFUND_REQUESTED", "REFUND_IN_PROGRESS")


def _estorno_confirmado_no_asaas(pid):
    """Re-consulta o pagamento depois de uma falha AMBÍGUA do estorno.

    PORQUÊ: um timeout de rede pode estourar DEPOIS de o Asaas já ter processado o
    estorno. Tratar isso como "não estornou" gera o pior par possível — alerta pedindo
    estorno manual (devolução em dobro) e cliente sem o acesso que já foi pago de volta.

    Devolve `(valor, tipo, pendente)` quando o Asaas confirma o estorno (mesmo que
    ainda em andamento); None quando ele diz que não houve, ou quando a própria
    re-consulta falha (sem certeza, não afirmamos que o dinheiro saiu).

    `pendente` é True para REFUND_REQUESTED/REFUND_IN_PROGRESS — status que ainda
    podem falhar depois (ex.: Pix sem saldo na conta Asaas), então mesmo tratados como
    sucesso aqui, o chamador precisa alertar pedindo confirmação humana. É False só
    para REFUNDED, que é definitivo."""
    import asaas, refunds
    try:
        atual = asaas.obter_pagamento(pid) or {}
        status = str(atual.get("status") or "").upper()
        if status not in _STATUS_ESTORNADO:
            return None
        tipo, _ = refunds.alvo_estorno(atual)
        valor = float(atual.get("value") or 0)
        return (valor, tipo, status != "REFUNDED")
    except Exception as e:
        print(f"[cancelar] re-consulta do pagamento após falha do estorno falhou: {e}", flush=True)
        return None


def estornar_arrependimento(sub):
    """Estorno INTEGRAL quando o cancelamento cai dentro dos 7 dias (CDC art. 49).

    Devolve `(valor, tipo)` quando o estorno sai (ou já tinha saído — falha ambígua
    confirmada no Asaas), ou None quando não havia direito, não havia cobrança
    (cortesia por cupom) ou o estorno no Asaas falhou de verdade. `tipo` vem de
    `refunds.alvo_estorno`: "installment" quando o alvo foi o parcelamento inteiro, ou
    "payment" quando foi um pagamento avulso — quem avisa o cliente (`_avisar_cancelamento`)
    usa isso pra saber se pode imprimir `valor` (no parcelado ele é só o de UMA
    parcela, não o total estornado). Falha aqui NUNCA bloqueia o cancelamento: o
    assinante não pode ficar preso por um problema nosso — vira alerta pro admin.

    NÃO faz claim de corrida (duplo clique / retry concorrente). Isso é
    responsabilidade de quem chama: db.claim_cancelamento grava o cancelamento inteiro
    de forma atômica ANTES daqui, e só o vencedor desse claim chega a esta função — um
    claim aqui dentro protegeria só a chamada ao Asaas e deixaria o resto do fluxo
    exposto à mesma corrida.

    O estorno no Asaas e a baixa da comissão do afiliado rodam em try/except
    SEPARADOS de propósito: é o estorno no Asaas que decide o retorno da função,
    porque é ele que move dinheiro de verdade. Se ele der certo, a função SEMPRE
    devolve o valor, mesmo que a baixa de comissão falhe em seguida (ex.: "database
    is locked" no servidor multi-thread) — senão o chamador acha que não houve
    estorno, mantém o acesso do cliente e ainda manda alerta dizendo que o dinheiro
    não saiu, quando na verdade já saiu.
    """
    from datetime import date
    import asaas, db, refunds, webhook_asaas
    if not refunds.dentro_arrependimento(sub.get("criado_em"), date.today()):
        return None
    pid = sub.get("asaas_payment_id")
    if not pid:                       # cortesia por cupom: não houve cobrança pra estornar
        return None
    try:
        pagamento = asaas.obter_pagamento(pid)
        # valor fica DENTRO do try, antes de mover dinheiro (Achado 3): se "value"
        # vier não-numérico, falha aqui — sem ter chamado o Asaas ainda — em vez de
        # explodir depois do estorno já ter saído (o que travaria o cancelamento
        # inteiro com o dinheiro já fora e o cliente ainda ATIVO).
        valor = float(pagamento.get("value") or 0)
        tipo, alvo = refunds.alvo_estorno(pagamento)
        if tipo == "installment":
            asaas.estornar_parcelamento(alvo)
        else:
            asaas.estornar_pagamento(alvo)
    except Exception as e:
        print(f"[cancelar] estorno de arrependimento falhou: {e}", flush=True)
        # Falha AMBÍGUA: o erro pode ter vindo depois de o Asaas já ter estornado
        # (timeout de rede na resposta). Pergunta ao Asaas antes de concluir que o
        # dinheiro não saiu — senão pediríamos estorno manual em cima de um estorno já
        # feito (devolução em dobro) e ainda manteríamos o acesso do reembolsado.
        resultado = _estorno_confirmado_no_asaas(pid)
        if resultado is None:
            webhook_asaas._alertar_admin(
                pid, sub.get("asaas_subscription_id"),
                f"ESTORNO de arrependimento FALHOU para {sub.get('nome') or sub.get('id')} "
                f"({e}) — estorne manualmente no painel do Asaas")
            return None
        valor, tipo, pendente = resultado
        print(f"[cancelar] apesar do erro ({e}), o Asaas confirma o estorno de {pid} "
              f"— seguindo como sucesso", flush=True)
        if pendente:
            # REFUND_REQUESTED/REFUND_IN_PROGRESS: o Asaas ainda não terminou de
            # processar. Continuamos tratando como sucesso (não re-estornar, evita
            # duplicidade), mas se isso falhar depois (ex.: Pix sem saldo na conta
            # Asaas) o cliente fica sem o dinheiro E sem acesso, e ninguém saberia —
            # por isso pede confirmação humana mesmo seguindo em frente.
            webhook_asaas._alertar_admin(
                pid, sub.get("asaas_subscription_id"),
                f"Estorno de arrependimento de {sub.get('nome') or sub.get('id')} ainda está em "
                f"processamento no Asaas (status != REFUNDED) — confirme manualmente que ele "
                f"conclui")
    try:
        db.estornar_comissao(sub["id"])
    except Exception as e:
        # O estorno no Asaas JÁ deu certo (dinheiro já saiu) — isso nunca pode virar
        # None pro chamador. Só a baixa de comissão do afiliado ficou pendente.
        print(f"[cancelar] baixa de comissão falhou após estorno OK: {e}", flush=True)
        webhook_asaas._alertar_admin(
            pid, sub.get("asaas_subscription_id"),
            f"Estorno de arrependimento CONCLUÍDO para {sub.get('nome') or sub.get('id')} — "
            f"mas a baixa da comissão do afiliado FALHOU ({e}) — ajuste manualmente no "
            f"painel de afiliados")
    return (valor, tipo)


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

if __name__ == "__main__":
    try:
        import db
        db.init()
    except Exception as e:
        print(f"[web] db.init falhou: {e}", flush=True)
    try:
        import trilha as _trilha
        _trilha.semear()          # idempotente: upsert por número
    except Exception as e:
        print(f"[trilha] seed falhou: {e}", flush=True)
    threading.Thread(target=agendador, daemon=True).start()
    print(f"[web] servindo ebook (curso.) + site artigos (artigos.) em :{PORT}", flush=True)
    Server(("0.0.0.0", PORT), Handler).serve_forever()
