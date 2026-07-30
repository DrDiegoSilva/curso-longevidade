"""Task 1 (spec 2026-07-29-cupom-previa): limite de tentativas de cupom por IP.

Fecha um oráculo já exposto: POST /assinar aceitava chutar códigos de cupom sem
nenhum limite, e um cupom de CORTESIA acertado cria assinante ATIVO na hora, sem
passar pelo Asaas (serve.py:1356) — acesso de graça, não desconto."""
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# `TestRateLimit` (testava `ratelimit.py` isolado: limite/janela/chaves
# independentes/evicção/concorrência) foi removida na consolidação dos dois módulos
# de rate-limit (2026-07-29): `ratelimit.py` foi apagado, e as asserções de
# limite/janela/chaves independentes já estavam duplicadas em
# tests/test_rate_limit_peek.py::TestLimitadoComportamentoExistenteInalterado (o
# mesmo comportamento, testado contra `rate_limit.py`, que virou o módulo único). A
# evicção e a concorrência — cobertura genuína que `rate_limit.py` nunca tinha —
# migraram pra tests/test_rate_limit_peek.py::TestRateLimitEviccaoEConcorrencia,
# com relógio injetado no lugar de `time.sleep` onde dava. Ver
# .superpowers/sdd/2026-07-29-cupom-previa/consolidacao-report.md.


class _AssinarStub:
    """Stub mínimo pro `self` de `_post_assinar` — mesmo padrão de
    test_aceite_checkout.py e test_precos_lancamento.py::_AssinarStub (implementa só o
    que o método usa: `headers`, `client_address`, `_html`, `_redirect`; não abre
    socket, não é uma requisição HTTP real)."""

    def __init__(self, ip="203.0.113.9"):
        self.headers = {}
        self.client_address = (ip, 54321)

    def _html(self, s, code=200):
        return s

    def _redirect(self, location, token=None, clear=False):
        return f"<redirect {location}>"

    def _ip_cliente(self):
        # `_post_assinar` resolve o IP via `Handler._ip_cliente` — este stub não
        # herda de `Handler`, então só encaminha pra implementação real (um único
        # ponto de verdade) em vez de duplicá-la.
        import serve
        return serve.Handler._ip_cliente(self)


class TestLimiteCupomNaRotaAssinar(unittest.TestCase):
    """Exercita `serve.Handler._post_assinar` de verdade (não só `rate_limit.py`
    isolado) — mesmo harness de test_precos_lancamento.py::TestCupomLancamentoNaRotaAssinar
    e test_aceite_checkout.py::TestGateDeAceiteNoPostAssinar (`_AssinarStub` + `g` como
    o `form.get(k, [""])[0]` do POST real)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        os.environ.pop("DATABASE_URL", None)
        for m in ("config", "db", "subscribers", "serve", "site_legal", "site_web",
                  "legal", "asaas", "pricing", "rate_limit"):
            sys.modules.pop(m, None)
        import db, subscribers, legal, serve, rate_limit
        db._INITED = False
        db.init()
        rate_limit.resetar()
        self.db, self.subscribers, self.legal = db, subscribers, legal
        self.serve, self.rate_limit = serve, rate_limit

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.rate_limit.resetar()

    def _g(self, **over):
        base = {"plano": "mensal", "nome": "Cliente Teste", "email": "cliente@example.com",
                "cpf": "11144477735", "whatsapp": "43999990000", "metodo": "PIX",
                "parcelas": "1", "cupom": "", "aceito": "1"}
        base.update(over)
        return lambda k: base.get(k, "")

    def _mock_asaas(self):
        import asaas
        checkouts = []
        orig_criar = asaas.criar_checkout
        asaas.criar_checkout = lambda payload: checkouts.append(payload) or {
            "url": "https://checkout.asaas.example/x", "id": "chk_x"}
        return asaas, checkouts, orig_criar

    def test_5_cupons_invalidos_seguidos_e_o_6o_e_barrado(self):
        asaas, checkouts, orig_criar = self._mock_asaas()
        stub = _AssinarStub(ip="198.51.100.1")
        try:
            for i in range(5):
                html = self.serve.Handler._post_assinar(stub, self._g(cupom=f"CHUTE-{i}"))
                self.assertTrue(html.startswith("<redirect https://checkout.asaas.example"),
                                f"tentativa {i+1}: cupom invalido nao pode ser barrado, "
                                f"so nao aplica desconto")
            bloqueado = self.serve.Handler._post_assinar(stub, self._g(cupom="CHUTE-6"))
        finally:
            asaas.criar_checkout = orig_criar
        self.assertNotIn("checkout.asaas.example", bloqueado)
        self.assertIn("Muitas tentativas", bloqueado)
        self.assertEqual(len(checkouts), 5, "a 6a tentativa nao pode ter chegado no Asaas")

    def test_compra_sem_cupom_nunca_e_barrada_mesmo_com_ip_bloqueado(self):
        asaas, checkouts, orig_criar = self._mock_asaas()
        stub = _AssinarStub(ip="198.51.100.2")
        try:
            for i in range(5):
                self.serve.Handler._post_assinar(stub, self._g(cupom=f"CHUTE-{i}"))
            bloqueado = self.serve.Handler._post_assinar(stub, self._g(cupom="CHUTE-6"))
            self.assertIn("Muitas tentativas", bloqueado)   # confirma que o IP esta bloqueado
            sem_cupom = self.serve.Handler._post_assinar(stub, self._g(cupom=""))
        finally:
            asaas.criar_checkout = orig_criar
        self.assertTrue(sem_cupom.startswith("<redirect https://checkout.asaas.example"),
                        "compra sem cupom nao pode ser afetada pelo limite do IP")

    def test_cupom_valido_nao_gasta_cota(self):
        self.db.criar_cupom(codigo="PROMOBOA", desconto_valor=50, plano_slug="",
                            uso_unico=False)
        asaas, checkouts, orig_criar = self._mock_asaas()
        stub = _AssinarStub(ip="198.51.100.3")
        try:
            for i in range(10):   # mais que o limite (5) — se consumisse cota, travaria
                html = self.serve.Handler._post_assinar(stub, self._g(cupom="PROMOBOA"))
                self.assertTrue(html.startswith("<redirect https://checkout.asaas.example"),
                                f"tentativa {i+1} com cupom valido nao pode ser barrada")
        finally:
            asaas.criar_checkout = orig_criar
        self.assertEqual(len(checkouts), 10)

    def test_rotacionar_prefixo_do_xff_nao_da_cota_nova(self):
        """Prova do Achado (Important) da revisão: um proxy reverso tipo Traefik
        ANEXA o IP real ao fim do X-Forwarded-For que o cliente mandar — um cliente
        que envia 'X-Forwarded-For: 1.2.3.4' chega no servidor como
        '1.2.3.4, <ip-real>'. Antes do fix (`.split(",")[0]`), o limite lia sempre o
        PRIMEIRO elemento — o valor que o próprio atacante escolhe — então rotacionar
        esse prefixo a cada request dava cota nova pra sempre (o teste todo virava
        teatro). O IP real (último elemento, escrito pelo proxy, fora do controle do
        cliente) é constante nas 6 tentativas abaixo — tem que barrar igual a um
        ataque sem spoofing nenhum."""
        asaas, checkouts, orig_criar = self._mock_asaas()
        ip_real = "198.51.100.50"
        stub = _AssinarStub(ip=ip_real)   # client_address é só o fallback; não deve
                                           # ser o que decide aqui, pois há XFF
        try:
            for i in range(5):
                stub.headers["X-Forwarded-For"] = f"10.{i}.0.1, {ip_real}"
                html = self.serve.Handler._post_assinar(stub, self._g(cupom=f"CHUTE-{i}"))
                self.assertTrue(html.startswith("<redirect https://checkout.asaas.example"),
                                f"tentativa {i+1} nao pode ser barrada ainda")
            stub.headers["X-Forwarded-For"] = f"10.99.0.1, {ip_real}"
            bloqueado = self.serve.Handler._post_assinar(stub, self._g(cupom="CHUTE-6"))
        finally:
            asaas.criar_checkout = orig_criar
        self.assertIn("Muitas tentativas", bloqueado,
                      "rotacionar o prefixo do XFF nao pode conceder cota nova — o IP "
                      "real (ultimo elemento) e constante nas 6 tentativas")


class _IpClienteStub:
    """Stub mínimo pro `self` de `_ip_cliente`: só `headers`/`client_address`, mesmo
    padrão dos outros stubs deste arquivo."""

    def __init__(self, xff=None, ip_real="203.0.113.50"):
        self.headers = {} if xff is None else {"X-Forwarded-For": xff}
        self.client_address = (ip_real, 54321)


class TestIpCliente(unittest.TestCase):
    """`_ip_cliente()` é o helper compartilhado (Task 1, fix pós-revisão) que
    substitui as DUAS cópias divergentes de parsing de X-Forwarded-For que existiam
    em serve.py (limite de cupom em `_post_assinar` e registro de aceite de termos em
    `_aceitar_termos`). Atrás de um proxy reverso que ANEXA (Traefik, a config deste
    deploy), o [0] do XFF é um valor que o CLIENTE escolhe — só o ÚLTIMO elemento
    não-vazio é o hop que ele não controla."""

    def setUp(self):
        import serve
        self.serve = serve

    def test_proxy_que_anexa_pega_o_ultimo_elemento(self):
        stub = _IpClienteStub(xff="1.2.3.4, 10.0.0.1")
        self.assertEqual(self.serve.Handler._ip_cliente(stub), "10.0.0.1")

    def test_proxy_que_substitui_pega_o_unico_elemento(self):
        stub = _IpClienteStub(xff="1.2.3.4")
        self.assertEqual(self.serve.Handler._ip_cliente(stub), "1.2.3.4")

    def test_sem_cabecalho_cai_no_client_address(self):
        stub = _IpClienteStub(xff=None, ip_real="203.0.113.77")
        self.assertEqual(self.serve.Handler._ip_cliente(stub), "203.0.113.77")

    def test_cabecalho_vazio_cai_no_client_address(self):
        stub = _IpClienteStub(xff="", ip_real="203.0.113.78")
        self.assertEqual(self.serve.Handler._ip_cliente(stub), "203.0.113.78")

    def test_cabecalho_so_espaco_cai_no_client_address(self):
        stub = _IpClienteStub(xff="   ", ip_real="203.0.113.79")
        self.assertEqual(self.serve.Handler._ip_cliente(stub), "203.0.113.79")

    def test_duas_LINHAS_de_xff_ainda_pegam_o_ultimo_hop(self):
        """Minor da revisão final: `headers.get()` devolve só a PRIMEIRA ocorrência do
        cabeçalho. Um cliente que manda o X-Forwarded-For dele em linha própria fazia o
        valor ESCOLHIDO por ele voltar a ser o resultado (o do proxy ficava na 2ª linha,
        ignorada) — bypass do limite de cupom e IP forjável gravado como prova de aceite
        dos Termos. Pelo RFC 9110 várias linhas equivalem a uma lista separada por
        vírgula, na ordem recebida: o último hop é o último elemento da ÚLTIMA linha.
        Usa `email.message.Message` porque é a base do `HTTPMessage` real do
        `http.server` (é ele que tem `get_all`; os outros stubs usam `dict`)."""
        from email.message import Message
        h = Message()
        h["X-Forwarded-For"] = "1.2.3.4"        # forjado pelo cliente, 1a linha
        h["X-Forwarded-For"] = "198.51.100.70"  # anexado pelo proxy, 2a linha
        stub = _IpClienteStub(ip_real="203.0.113.1")
        stub.headers = h
        self.assertEqual(self.serve.Handler._ip_cliente(stub), "198.51.100.70")

    def test_tres_linhas_com_lista_na_ultima(self):
        from email.message import Message
        h = Message()
        h["X-Forwarded-For"] = "9.9.9.9"
        h["X-Forwarded-For"] = "8.8.8.8, 198.51.100.71"
        stub = _IpClienteStub()
        stub.headers = h
        self.assertEqual(self.serve.Handler._ip_cliente(stub), "198.51.100.71")

    def test_sem_client_address_degrada_em_vez_de_derrubar(self):
        """Minor da revisão final: o guard `if self.client_address else "?"` que o
        `_rate_ok` tinha se perdeu na mudança pro helper. Sem XFF e com o socket já
        derrubado, `client_address` vem vazio e o acesso `[0]` derrubaria a resposta."""
        stub = _IpClienteStub(xff=None)
        stub.client_address = ()
        self.assertEqual(self.serve.Handler._ip_cliente(stub), "?")
        stub.client_address = None
        self.assertEqual(self.serve.Handler._ip_cliente(stub), "?")

    def test_virgula_final_nao_vira_string_vazia(self):
        # "1.2.3.4, 10.0.0.1, " (trailing comma / elemento final vazio) tem que
        # devolver "10.0.0.1" — "" como chave de rate-limit juntaria todo mundo num
        # balde só, e "" como IP de aceite de termos não prova nada.
        stub = _IpClienteStub(xff="1.2.3.4, 10.0.0.1, ")
        self.assertEqual(self.serve.Handler._ip_cliente(stub), "10.0.0.1")


class _AceitarTermosStub:
    """Stub mínimo pro `self` de `_aceitar_termos` — mesma forma de
    test_destino_seguro.py::_AceitarTermosStub (headers/client_address pro IP do
    aceite; _sub_logado/_html/_redirect pro resto do método)."""

    def __init__(self, sub, ip_real="203.0.113.9"):
        self._sub = sub
        self.headers = {}
        self.client_address = (ip_real, 0)
        self.redirects = []

    def _sub_logado(self):
        return self._sub

    def _html(self, s, code=200):
        return s

    def _redirect(self, location, token=None, clear=False):
        self.redirects.append(location)
        return f"<redirect {location}>"

    def _ip_cliente(self):
        # `_aceitar_termos` resolve o IP via `Handler._ip_cliente` — este stub não
        # herda de `Handler`, então só encaminha pra implementação real (um único
        # ponto de verdade) em vez de duplicá-la.
        import serve
        return serve.Handler._ip_cliente(self)


class TestIpClienteNoAceiteDeTermos(unittest.TestCase):
    """A revisão apontou uma segunda consequência do mesmo bug: `_aceitar_termos`
    grava o X-Forwarded-For mal-interpretado como EVIDÊNCIA LEGAL de aceite dos
    Termos (`termos_ip`, usado num contexto de direito do consumidor com prazo de
    arrependimento). Confere que a rota real usa o `_ip_cliente()` compartilhado —
    não uma segunda cópia do parsing errado — e ainda grava algo sensato."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        os.environ.pop("DATABASE_URL", None)
        for m in ("config", "db", "subscribers", "serve", "legal"):
            sys.modules.pop(m, None)
        import db, subscribers, legal, serve
        db._INITED = False
        db.init()
        self.db, self.subs, self.legal, self.serve = db, subscribers, legal, serve
        self.reg = self.subs.criar_de_pagamento(
            {"nome": "T", "whatsapp": "43999990000", "email": "t@e.com", "plano": "anual"}, {})

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _aceitar(self, stub):
        g = lambda k: {"aceito": "1", "destino": ""}.get(k, "")
        self.serve.Handler._aceitar_termos(stub, g)
        return self.subs.por_whatsapp("43999990000")["termos_ip"]

    def test_grava_o_ultimo_elemento_do_xff_nao_o_primeiro_forjavel(self):
        stub = _AceitarTermosStub(self.reg)
        stub.headers["X-Forwarded-For"] = "1.2.3.4, 198.51.100.60"   # forjado, real
        self.assertEqual(self._aceitar(stub), "198.51.100.60",
                         "prova de aceite tem que gravar o IP real (ultimo hop), nao "
                         "o valor que o proprio cliente escolheu mandar")

    def test_sem_xff_ainda_cai_no_client_address(self):
        stub = _AceitarTermosStub(self.reg, ip_real="203.0.113.44")
        self.assertEqual(self._aceitar(stub), "203.0.113.44")


class _CupomPreviaStub:
    """Stub mínimo pro `self` de `do_POST` quando `path == '/assinar/cupom'`. A rota
    vive INLINE em `do_POST` (não é um método próprio como `_post_assinar`), então o
    padrão certo pra exercitá-la de verdade é o de `_SeriesRotaStub`/`_make_stub_cls`
    (test_series.py::TestRotaSeries): herdar de `serve.Handler` pra rodar o `do_POST`
    real, e sobrescrever só o que dependeria de socket — `path`/`headers`/`rfile` na
    entrada, e agora também `_json` na saída (a rota nova escreve JSON, não HTML/
    redirect, então este stub estende o mesmo padrão com o único método de saída que
    faltava, em vez de inventar uma terceira forma de stub)."""

    def __init__(self, path, body=b"", ip="203.0.113.9", extra=None):
        self.path = path
        self.headers = {"Content-Length": str(len(body)),
                        "Content-Type": "application/x-www-form-urlencoded"}
        # `extra` (Origin/Referer/Host) só pros testes do gate de mesma origem — os
        # outros seguem sem esses cabeçalhos de propósito: ausência dos dois libera
        # (fail-open), então nada abaixo mudou de comportamento por causa do gate.
        self.headers.update(extra or {})
        self.rfile = io.BytesIO(body)
        self.client_address = (ip, 54321)

    def _json(self, obj, code=200):
        # devolve o dict puro em vez de escrever bytes num socket — o `do_POST` real
        # faz `return self._json(...)`, então `stub.do_POST()` já devolve o dict.
        return obj

    def _html(self, s, code=200):
        # mesmo padrão de `_SeriesRotaStub._html`: se `do_POST` cair no fallback
        # (rota não bateu), devolve algo inspecionável em vez de tentar escrever
        # num socket que não existe (`BaseHTTPRequestHandler.send_response` crash
        # com AttributeError confuso — `requestline` etc.).
        return (code, s)

    def _redirect(self, location, token=None, clear=False):
        return ("REDIRECT", location)


def _make_cupom_previa_stub_cls():
    """Mesma justificativa de `_make_stub_cls` (test_series.py): `_CupomPreviaStub`
    precisa herdar de `serve.Handler` (não `object`) pra ter o `do_POST` de verdade,
    mas `serve` só existe depois do `import` dentro de cada teste. `_CupomPreviaStub`
    PRIMEIRO na MRO pra que `_json` sobrescrito vença a resolução de nome."""
    import serve
    return type("_CupomPreviaStubHandler", (_CupomPreviaStub, serve.Handler), {})


class TestPreviaCupom(unittest.TestCase):
    """A prévia usa a MESMA `base_cobrada` do fechamento — os testes conferem contra
    ela, nunca contra aritmética duplicada aqui."""

    def setUp(self):
        # Divergência do brief: o `setUp` do Step 1 só fazia `ratelimit.zerar()`,
        # assumindo um `db` já inicializado e utilizável. Descoberto ao rodar a
        # suíte completa (não isolado): `TestLimiteCupomNaRotaAssinar`, que roda
        # ANTES desta classe em ordem alfabética (`dir(module)` — é assim que
        # `unittest` descobre classes dentro de um módulo), deixa
        # `DSCURSO_ARTIGOS_DB` apontando pra um tmpdir que o próprio `tearDown`
        # dela já apagou (`shutil.rmtree`), sem restaurar a env var. `db._INITED`
        # continua `True` no módulo `db` já carregado, então `db.init()` aqui
        # seria NO-OP; a próxima chamada real (`db.criar_cupom`/`cupom_desconto`)
        # abriria um sqlite NOVO E VAZIO no diretório recriado por `_conn()`
        # (`os.makedirs`) — sem tabela `cupons` (`no such table`). Uso o mesmo
        # padrão isolado de tmpdir+reimport das outras classes deste arquivo pra
        # não depender da ordem de execução.
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        os.environ.pop("DATABASE_URL", None)
        for m in ("config", "db", "subscribers", "serve", "site_web", "legal",
                  "asaas", "pricing", "rate_limit"):
            sys.modules.pop(m, None)
        import db, rate_limit
        db._INITED = False
        db.init()
        rate_limit.resetar()
        self.rate_limit = rate_limit

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.rate_limit.resetar()

    def _resp(self, plano="anual", cupom="LANCAMENTO", metodo="CARTAO", ip="ip-teste"):
        """POSTa em /assinar/cupom (via `do_POST` real, socket stubado) e devolve o
        dict do JSON."""
        import urllib.parse as up
        Stub = _make_cupom_previa_stub_cls()
        body = up.urlencode({"plano": plano, "cupom": cupom, "metodo": metodo}).encode("utf-8")
        stub = Stub("/assinar/cupom", body=body, ip=ip)
        return stub.do_POST()

    def test_cupom_valido_devolve_preco_e_parcelas_com_desconto(self):
        import config, pricing, db
        db.init()
        plano = config.plano_por_slug("anual")
        esperado = pricing.base_cobrada(plano, "CARTAO", float(plano["base"]),
                                        cupom_valor=db.cupom_desconto("LANCAMENTO", "anual"))
        r = self._resp(cupom="LANCAMENTO")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["preco"], pricing.fmt_brl(esperado))
        # FORMATO, não só truthiness (Important da revisão final): `assertTrue(r["parcelas"])`
        # passava com QUALQUER lista não-vazia — renomear uma chave que o JS lê deixava a
        # suíte verde e o dropdown renderizando "undefinedx de undefined".
        opcoes = pricing.opcoes_parcelas(esperado)
        self.assertEqual(len(r["parcelas"]), len(opcoes),
                         "o dropdown tem que vir com todas as opções")
        self.assertEqual(
            r["parcelas"],
            [{"parcelas": o["parcelas"], "por_parcela": pricing.fmt_brl(o["por_parcela"]),
              "total": pricing.fmt_brl(o["total"])} for o in opcoes],
            "as 3 chaves que o JS lê (parcelas/por_parcela/total), com os MESMOS valores "
            "de pricing.opcoes_parcelas e já formatados em R$")
        for item in r["parcelas"]:
            self.assertEqual(sorted(item), ["parcelas", "por_parcela", "total"])
            self.assertIsInstance(item["parcelas"], int)
            self.assertTrue(item["por_parcela"].startswith("R$ "), item)
            self.assertTrue(item["total"].startswith("R$ "), item)

    def test_cupom_valido_pix_empilha_desconto_via_base_cobrada(self):
        """Mutação (c) do Step 5: `base_cobrada` empilha o desconto Pix (5%) SOBRE o
        valor já reduzido pelo cupom; uma troca por `base - desconto` na mão não
        empilha nada. Sem este caso, uma regressão desse tipo passaria despercebida —
        o teste CARTAO acima não distingue as duas fórmulas quando o método não é Pix."""
        import config, pricing, db
        db.init()
        plano = config.plano_por_slug("anual")
        esperado = pricing.base_cobrada(plano, "PIX", float(plano["base"]),
                                        cupom_valor=db.cupom_desconto("LANCAMENTO", "anual"))
        r = self._resp(cupom="LANCAMENTO", metodo="PIX")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["preco"], pricing.fmt_brl(esperado))
        # o valor de hoje, escrito à mão: anual 1497 − 500 (LANCAMENTO) = 997, e o Pix
        # tira 5% POR CIMA disso -> 947,15. "R$ 997,00" aqui significaria que o
        # empilhamento do Pix se perdeu.
        self.assertEqual(r["preco"], "R$ 947,15")

    def test_cortesia_responde_invalido_generico(self):
        """Cortesia (desconto 0) daria acesso GRATIS no fechamento. A previa nao pode
        confirmar que o codigo existe, senao vira detector de jackpot."""
        import db
        db.init()
        db.criar_cupom(descricao="cortesia teste", uso_unico=False, dias_acesso=0,
                       codigo="CORTESIATESTE")
        r = self._resp(cupom="CORTESIATESTE")
        self.assertFalse(r["ok"])
        self.assertEqual(r["msg"], self._resp(cupom="NAOEXISTEZZZ")["msg"],
                         "cortesia e inexistente tem que ser INDISTINGUIVEIS")

    def test_cupom_de_outro_plano_invalido_generico(self):
        import db
        db.init()
        r = self._resp(plano="mensal", cupom="LANCAMENTO")   # LANCAMENTO e do anual
        self.assertFalse(r["ok"])
        self.assertEqual(r["msg"], self._resp(cupom="NAOEXISTEZZZ", plano="mensal")["msg"])

    def test_cupom_desativado_no_admin_invalido(self):
        import db
        db.init()
        db.toggle_cupom("LANCAMENTO", False)
        try:
            r = self._resp(cupom="LANCAMENTO")
            self.assertFalse(r["ok"])
        finally:
            db.toggle_cupom("LANCAMENTO", True)

    def test_previa_nao_escreve_nada_no_banco(self):
        """Nem consome cupom, nem cria assinante. Se a previa gastasse o cupom,
        conferir o preco queimaria o desconto."""
        import db, subscribers
        db.init()
        antes_usos = (db.obter_cupom("LANCAMENTO") or {}).get("usos", 0)
        antes_assin = len(subscribers.listar())
        self._resp(cupom="LANCAMENTO")
        self.assertEqual((db.obter_cupom("LANCAMENTO") or {}).get("usos", 0), antes_usos)
        self.assertEqual(len(subscribers.listar()), antes_assin)

    def test_bloqueia_depois_de_5_invalidos_e_valido_nao_gasta_cota(self):
        for _ in range(5):
            self.assertFalse(self._resp(cupom="NAOEXISTEZZZ", ip="ip-bloq")["ok"])
        r = self._resp(cupom="NAOEXISTEZZZ", ip="ip-bloq")
        self.assertTrue(r.get("bloqueado"), f"6a tentativa devia bloquear: {r}")

        import rate_limit
        rate_limit.resetar()
        for _ in range(5):
            self.assertTrue(self._resp(cupom="LANCAMENTO", ip="ip-ok")["ok"])
        self.assertTrue(self._resp(cupom="LANCAMENTO", ip="ip-ok")["ok"],
                        "cupom valido nao gasta cota")


class _BasePrevia(unittest.TestCase):
    """Mesmo isolamento de `TestPreviaCupom` (tmpdir + reimport por teste, sem
    depender da ordem de execução das classes)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        os.environ.pop("DATABASE_URL", None)
        self._limpar_modulos()
        import db, rate_limit
        db._INITED = False
        db.init()
        rate_limit.resetar()
        self.db, self.rate_limit = db, rate_limit

    def _limpar_modulos(self):
        for m in ("config", "db", "subscribers", "serve", "site_web", "legal",
                  "asaas", "pricing", "rate_limit", "renovacao"):
            sys.modules.pop(m, None)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.rate_limit.resetar()

    def _resp(self, plano="anual", cupom="LANCAMENTO", metodo="CARTAO", ip="ip-teste",
              extra=None):
        import urllib.parse as up
        Stub = _make_cupom_previa_stub_cls()
        body = up.urlencode({"plano": plano, "cupom": cupom, "metodo": metodo}).encode("utf-8")
        return Stub("/assinar/cupom", body=body, ip=ip, extra=extra).do_POST()


class TestPreviaCupomVazio(_BasePrevia):
    """Important da revisão final: `g("cupom").strip().upper()` == "" caía em
    `cupom_desconto("")` -> 0.0 -> CONTAVA tentativa. Provado: 5 cliques no Aplicar
    com o campo em branco esgotavam a cota do PRÓPRIO visitante, e depois disso o
    cupom BOM dele era recusado — na prévia E no fechamento. Campo vazio não é
    tentativa de chute nenhum: não pode custar cota."""

    def test_vinte_cliques_em_branco_nao_gastam_cota(self):
        ip = "203.0.113.30"
        for i in range(20):                      # 4x o teto
            r = self._resp(cupom="", ip=ip)
            self.assertFalse(r["ok"])
            self.assertFalse(r.get("bloqueado"), f"clique {i+1} em branco foi barrado")
        self.assertTrue(self._resp(cupom="LANCAMENTO", ip=ip)["ok"],
                        "o cupom BOM do visitante tem que continuar funcionando depois "
                        "de cliques com o campo em branco")

    def test_so_espacos_tambem_nao_gastam_cota(self):
        ip = "203.0.113.31"
        for _ in range(20):
            self.assertFalse(self._resp(cupom="   ", ip=ip).get("bloqueado"))
        self.assertTrue(self._resp(cupom="LANCAMENTO", ip=ip)["ok"])

    def test_campo_vazio_pede_o_codigo_em_vez_de_dizer_invalido(self):
        r = self._resp(cupom="", ip="203.0.113.32")
        self.assertFalse(r["ok"])
        self.assertNotEqual(r["msg"], "Cupom inválido.",
                            "campo em branco não é cupom inválido — é campo em branco")
        self.assertTrue(r["msg"].strip(), "tem que dizer alguma coisa ao visitante")

    def test_vazio_nem_consulta_o_banco(self):
        """Corolário: o caminho do campo vazio retorna ANTES de qualquer lookup — não
        é só "não conta", é "não chega a olhar cupom nenhum"."""
        chamadas = []
        orig = self.db.cupom_desconto
        self.db.cupom_desconto = lambda c, p: chamadas.append(c) or orig(c, p)
        try:
            self._resp(cupom="", ip="203.0.113.33")
        finally:
            self.db.cupom_desconto = orig
        self.assertEqual(chamadas, [])


class TestPreviaCupomAfiliado(_BasePrevia):
    """Important da revisão final (lacuna de SPEC, não do implementador): a prévia
    consultava só `db.cupom_desconto` e nunca `db.afiliado_por_codigo` — mas o
    fechamento HONRA códigos de afiliado (D3, no ar). Um código de afiliado válido
    respondia "Cupom inválido." e ainda queimava cota; depois de 5 tentativas o
    MESMO código era recusado no checkout."""

    def _afiliado(self, codigo="PARCEIRO1", pct=10):
        return self.db.criar_afiliado("Parceiro", "p@example.com", codigo,
                                      pct_desconto=pct, pct_comissao=3)

    def test_codigo_de_afiliado_valido_mostra_o_desconto(self):
        import config, pricing, subscribers
        self._afiliado()
        plano = config.plano_por_slug("anual")
        esperado = pricing.base_cobrada(
            plano, "CARTAO", pricing.preco_vigente(plano, len(subscribers.ativos())),
            10.0, 0.0)
        r = self._resp(cupom="PARCEIRO1")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["preco"], pricing.fmt_brl(esperado))
        self.assertIn("10%", r["msg"], f"a mensagem tem que mostrar o % do afiliado: {r}")

    def test_afiliado_valido_nao_gasta_cota(self):
        self._afiliado()
        ip = "203.0.113.40"
        for i in range(12):                      # mais que o dobro do teto
            self.assertTrue(self._resp(cupom="PARCEIRO1", ip=ip)["ok"],
                            f"tentativa {i+1} com código de afiliado válido foi barrada")

    def test_afiliado_inativo_cai_na_falha_generica(self):
        self._afiliado(codigo="PARCEIRO2")
        afs = [a for a in self.db.listar_afiliados() if a["codigo"] == "PARCEIRO2"]
        self.db.toggle_afiliado(afs[0]["id"], False)
        r = self._resp(cupom="PARCEIRO2", ip="203.0.113.41")
        self.assertFalse(r["ok"])
        self.assertEqual(r["msg"], self._resp(cupom="NAOEXISTEZZZ", ip="203.0.113.42")["msg"],
                         "afiliado INATIVO e código inexistente têm que ser indistinguíveis")

    def test_previa_promete_exatamente_o_que_o_checkout_cobra_com_afiliado(self):
        """A propriedade que a feature inteira existe pra garantir: mostrado == cobrado.
        Compara o `preco` da prévia com a `base` que o `_post_assinar` manda pro Asaas."""
        import asaas, pricing
        self._afiliado(codigo="PARCEIRO3", pct=10)
        previa = self._resp(cupom="PARCEIRO3", metodo="PIX", ip="203.0.113.43")
        self.assertTrue(previa["ok"], previa)

        import serve
        capt = {}
        orig_montar, orig_criar = asaas.montar_checkout, asaas.criar_checkout
        asaas.montar_checkout = (lambda plano, metodo, parcelas, dados, token, base_url,
                                 base=None: capt.update(base=base) or {"p": 1})
        asaas.criar_checkout = lambda payload: {"url": "https://checkout.asaas.example/x"}
        g = {"plano": "anual", "nome": "Cliente Teste", "email": "c@example.com",
             "cpf": "11144477735", "whatsapp": "43999990000", "metodo": "PIX",
             "parcelas": "1", "cupom": "PARCEIRO3", "aceito": "1"}
        try:
            serve.Handler._post_assinar(_AssinarStub(ip="203.0.113.43"),
                                        lambda k: g.get(k, ""))
        finally:
            asaas.montar_checkout, asaas.criar_checkout = orig_montar, orig_criar
        self.assertIn("base", capt, "o checkout não chegou a montar o payload")
        self.assertEqual(previa["preco"], pricing.fmt_brl(capt["base"]),
                         "a prévia mostrou um valor e o checkout cobraria outro")


class TestPreviaBaseVigente(_BasePrevia):
    """Important da revisão final: a prévia precificava sobre `plano["base"]` cru,
    enquanto o fechamento usa o preço VIGENTE (`pricing.preco_vigente`). Coincidem
    hoje, mas divergem com preço pós-founder — e divergir aqui é exatamente a classe
    de bug (mostrar um valor, cobrar outro) que esta tela existe pra impedir."""

    def setUp(self):
        super().setUp()
        import config, subscribers
        # Patch no MÓDULO (não em env var): `DSCURSO_FOUNDER_LIMITE` é lido no import de
        # `config`, então mexer no ambiente vazaria pra qualquer módulo que já tivesse
        # importado `config` e ficaria dependente da ordem dos testes.
        self.PLANOS_orig, self.LIMITE_orig = config.PLANOS, config.FOUNDER_LIMITE
        config.FOUNDER_LIMITE = 1
        # anual com preço pós-founder DIFERENTE do de lançamento
        config.PLANOS = [dict(p, base_pos=1997.0, preco_pos="R$ 1.997") if p["slug"] == "anual"
                         else p for p in config.PLANOS]
        subscribers.criar_de_pagamento(
            {"nome": "Ativo", "whatsapp": "43999991111", "email": "a@e.com",
             "plano": "anual"}, {}, status="ATIVO")   # 1 ativo >= FOUNDER_LIMITE=1

    def tearDown(self):
        import config
        config.PLANOS, config.FOUNDER_LIMITE = self.PLANOS_orig, self.LIMITE_orig
        super().tearDown()

    def test_previa_usa_o_preco_vigente_e_nao_o_de_lancamento(self):
        import config, pricing, subscribers
        plano = config.plano_por_slug("anual")
        n = len(subscribers.ativos())
        self.assertEqual(pricing.preco_vigente(plano, n), 1997.0,
                         "cenário do teste: tem que estar pós-founder")
        desconto = self.db.cupom_desconto("LANCAMENTO", "anual")
        vigente = pricing.base_cobrada(plano, "CARTAO", 1997.0, cupom_valor=desconto)
        lancamento = pricing.base_cobrada(plano, "CARTAO", float(plano["base"]),
                                          cupom_valor=desconto)
        self.assertNotEqual(vigente, lancamento, "cenário do teste: têm que divergir")
        r = self._resp(cupom="LANCAMENTO", ip="203.0.113.50")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["preco"], pricing.fmt_brl(vigente),
                         "a prévia tem que precificar sobre a base VIGENTE (a mesma do "
                         "fechamento), não sobre plano['base']")

    def test_parcelas_tambem_saem_da_base_vigente(self):
        import pricing
        r = self._resp(cupom="LANCAMENTO", ip="203.0.113.51")
        totais = {o["total"] for o in r["parcelas"]}
        self.assertEqual(totais, {r["preco"]},
                         "todas as opções somam o mesmo total (cartão sem juros) e esse "
                         "total é o preço mostrado")
        self.assertEqual(len(r["parcelas"]), len(pricing.opcoes_parcelas(1497.0)))


class TestPreviaTodasAsFiguras(_BasePrevia):
    """BUG AO VIVO (2026-07-29, achado dirigindo a página deployada): a tela mostra
    dinheiro em TRÊS lugares e a prévia atualizava um. Com LANCAMENTO no anual e Pix
    selecionado (o default), a página ficava assim:

        #sum-price          R$ 947,15                      (certo pro Pix)
        tile Pix .pt-desc   R$ 1.422,15 à vista            ERRADO (1497 − 5%, sem cupom)
        <select> parcelas   12x de R$ 78,93 → R$ 947,15    ERRADO (Pix parcelado não existe)

    A resposta da prévia passa a trazer TODAS as figuras que a página exibe, cada uma
    calculada por `pricing.figuras_assinar` (que por baixo é `base_cobrada`, a mesma do
    fechamento) — nenhuma conta no JS."""

    CHAVES = {"ok", "msg", "preco", "pix_desc", "cartao_desc", "parcelas"}

    def test_resposta_traz_todas_as_figuras_da_tela(self):
        r = self._resp(cupom="LANCAMENTO", ip="203.0.113.70")
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.CHAVES - set(r), set(),
                         f"a prévia tem que devolver toda figura que a tela mostra: {r}")

    def test_ancoras_do_anual_com_lancamento(self):
        """Os dois números que não podem mudar sem decisão do dono: cartão 997 (sem
        desconto de Pix) e Pix 947,15 (997 − 5%)."""
        self.assertEqual(self._resp(cupom="LANCAMENTO", metodo="CARTAO",
                                    ip="203.0.113.71")["preco"], "R$ 997,00")
        self.assertEqual(self._resp(cupom="LANCAMENTO", metodo="PIX",
                                    ip="203.0.113.72")["preco"], "R$ 947,15")

    def test_tile_do_pix_leva_o_cupom_mesmo_com_cartao_selecionado(self):
        """O tile do Pix é o à-vista do Pix SEMPRE — o bug era ele ignorar o cupom."""
        for metodo, ip in (("CARTAO", "203.0.113.73"), ("PIX", "203.0.113.74")):
            r = self._resp(cupom="LANCAMENTO", metodo=metodo, ip=ip)
            self.assertEqual(r["pix_desc"], "R$ 947,15 à vista",
                             f"com {metodo} selecionado o tile do Pix mentiu: {r}")
            self.assertNotIn("1.422,15", r["pix_desc"])

    def test_parcelas_nunca_saem_do_preco_do_pix(self):
        """Parcelamento existe só no cartão: a lista tem que vir da base do CARTÃO nos
        dois métodos (era "12x de R$ 78,93 — total R$ 947,15" ao vivo)."""
        for metodo, ip in (("CARTAO", "203.0.113.75"), ("PIX", "203.0.113.76")):
            r = self._resp(cupom="LANCAMENTO", metodo=metodo, ip=ip)
            self.assertEqual({o["total"] for o in r["parcelas"]}, {"R$ 997,00"}, metodo)
            doze = [o for o in r["parcelas"] if o["parcelas"] == 12][0]
            self.assertEqual(doze["por_parcela"], "R$ 83,08", metodo)

    def test_figuras_da_previa_sao_exatamente_as_do_pricing(self):
        """Contra aritmética duplicada: a rota só formata o que `figuras_assinar`
        devolve (que por baixo é `base_cobrada`, a do fechamento)."""
        import config, pricing, subscribers
        plano = config.plano_por_slug("anual")
        base_vig = pricing.preco_vigente(plano, len(subscribers.ativos()))
        esperado = pricing.figuras_assinar(
            plano, "PIX", base_vig, 0.0, self.db.cupom_desconto("LANCAMENTO", "anual"))
        r = self._resp(cupom="LANCAMENTO", metodo="PIX", ip="203.0.113.77")
        for chave in ("preco", "pix_desc", "cartao_desc", "parcelas"):
            self.assertEqual(r[chave], esperado[chave], chave)

    def test_tile_do_cartao_do_mensal_acompanha_o_desconto(self):
        """No mensal o tile do Cartão mostra dinheiro ("R$ X/mês · renova"); com um
        código de afiliado (10%) ele tem que acompanhar — senão promete 147 e cobra
        132,30."""
        self.db.criar_afiliado("Parceiro", "p@example.com", "AFIMENSAL",
                               pct_desconto=10, pct_comissao=3)
        r = self._resp(plano="mensal", cupom="AFIMENSAL", metodo="CARTAO",
                       ip="203.0.113.78")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["cartao_desc"], "R$ 132,30/mês · renova")
        self.assertEqual(r["preco"], "R$ 132,30")

    def test_pedido_pix_com_parcelas_no_form_cobra_a_vista(self):
        """A tela ESCONDE o campo de parcelas quando o método é Pix (Pix é à vista), mas
        deixa o campo habilitado pro `POST /assinar` continuar lendo `parcelas` como
        sempre — então um pedido Pix pode chegar com `parcelas=12`. Aqui está a prova de
        que o servidor ignora isso ponta a ponta: o payload que iria pro Asaas cobra o
        valor à vista, sem installmentCount."""
        import asaas, serve
        capt = []
        orig_criar = asaas.criar_checkout
        asaas.criar_checkout = lambda payload: capt.append(payload) or {
            "url": "https://checkout.asaas.example/x", "id": "chk"}
        g = {"plano": "anual", "nome": "Cliente Teste", "email": "c@example.com",
             "cpf": "11144477735", "whatsapp": "43999990000", "metodo": "PIX",
             "parcelas": "12", "cupom": "LANCAMENTO", "aceito": "1"}
        try:
            serve.Handler._post_assinar(_AssinarStub(ip="203.0.113.80"),
                                        lambda k: g.get(k, ""))
        finally:
            asaas.criar_checkout = orig_criar
        self.assertEqual(len(capt), 1, "o checkout não chegou a ser criado")
        self.assertEqual(capt[0]["billingTypes"], ["PIX"])
        self.assertNotIn("installmentCount", capt[0])
        self.assertEqual(capt[0]["items"][0]["value"], 947.15,
                         "Pix cobra o à-vista com desconto, não uma parcela")

    def test_parcelas_mostradas_no_pix_sao_o_que_o_cartao_cobraria(self):
        """A propriedade que a feature existe pra garantir, agora na figura que estava
        errada: o dropdown que o visitante lê (mesmo com Pix marcado, antes de trocar
        pro cartão) tem que casar com o valor que o checkout manda pro Asaas num cartão
        em 12x."""
        import asaas, pricing, serve
        previa = self._resp(cupom="LANCAMENTO", metodo="PIX", ip="203.0.113.79")
        self.assertTrue(previa["ok"], previa)
        doze = [o for o in previa["parcelas"] if o["parcelas"] == 12][0]

        capt = {}
        orig_montar, orig_criar = asaas.montar_checkout, asaas.criar_checkout
        asaas.montar_checkout = (lambda plano, metodo, parcelas, dados, token, base_url,
                                 base=None: capt.update(base=base, parcelas=parcelas) or {"p": 1})
        asaas.criar_checkout = lambda payload: {"url": "https://checkout.asaas.example/x"}
        g = {"plano": "anual", "nome": "Cliente Teste", "email": "c@example.com",
             "cpf": "11144477735", "whatsapp": "43999990000", "metodo": "CARTAO",
             "parcelas": "12", "cupom": "LANCAMENTO", "aceito": "1"}
        try:
            serve.Handler._post_assinar(_AssinarStub(ip="203.0.113.79"),
                                        lambda k: g.get(k, ""))
        finally:
            asaas.montar_checkout, asaas.criar_checkout = orig_montar, orig_criar
        self.assertIn("base", capt, "o checkout não chegou a montar o payload")
        self.assertEqual(capt["parcelas"], 12)
        self.assertEqual(doze["total"], pricing.fmt_brl(capt["base"]),
                         "o dropdown mostrou um total e o cartão cobraria outro")


class TestClassesDeFalhaIndistinguiveis(_BasePrevia):
    """A prévia não pode virar detector de cupom: um cupom de CORTESIA acertado dá
    acesso GRÁTIS no fechamento, então "existe mas não serve" tem que ser
    indistinguível de "não existe". Com a consulta de afiliado adicionada (Important
    3), as classes passaram de 4 pra 5 — todas continuam com o MESMO status, o MESMO
    corpo e a MESMA mensagem, e as duas consultas rodam SEMPRE, na mesma ordem, pra
    qualquer código (é o que mantém o tempo igual também)."""

    def _resp_com_status(self, cupom, plano="anual"):
        import urllib.parse as up
        Stub = _make_cupom_previa_stub_cls()
        # captura o código HTTP também (o `_json` do stub padrão devolve só o corpo)
        Stub = type("_ComStatus", (Stub,),
                    {"_json": lambda self, obj, code=200: (code, obj)})
        body = up.urlencode({"plano": plano, "cupom": cupom,
                             "metodo": "CARTAO"}).encode("utf-8")
        return Stub("/assinar/cupom", body=body, ip=f"ip-{cupom}").do_POST()

    def test_as_cinco_classes_de_falha_respondem_identico(self):
        self.db.criar_cupom(descricao="cortesia", uso_unico=False, dias_acesso=7,
                            codigo="CORTESIAX")
        self.db.criar_cupom(descricao="inativo", desconto_valor=100, codigo="INATIVOX")
        self.db.toggle_cupom("INATIVOX", False)
        self.db.criar_afiliado("Parceiro", "p@e.com", "AFOFFX", pct_desconto=10)
        afs = [a for a in self.db.listar_afiliados() if a["codigo"] == "AFOFFX"]
        self.db.toggle_afiliado(afs[0]["id"], False)

        classes = {
            "inexistente": self._resp_com_status("NAOEXISTEZZZ"),
            "inativo": self._resp_com_status("INATIVOX"),
            "cortesia": self._resp_com_status("CORTESIAX"),
            "outro_plano": self._resp_com_status("LANCAMENTO", plano="mensal"),
            "afiliado_inativo": self._resp_com_status("AFOFFX"),
        }
        esperado = (200, {"ok": False, "msg": "Cupom inválido."})
        for nome, r in classes.items():
            self.assertEqual(r, esperado, f"classe '{nome}' se distingue das outras")

    def test_as_duas_consultas_rodam_sempre_na_mesma_ordem(self):
        """O que garante o TEMPO igual: nem "afiliado só se o promocional falhou" (que
        separaria válido de inválido), nem uma consulta a menos em alguma classe."""
        ordem = []
        o_cup, o_af = self.db.cupom_desconto, self.db.afiliado_por_codigo
        self.db.cupom_desconto = lambda c, p: ordem.append("cupom") or o_cup(c, p)
        self.db.afiliado_por_codigo = lambda c: ordem.append("afiliado") or o_af(c)
        try:
            for cupom in ("NAOEXISTEZZZ", "LANCAMENTO"):     # inválido e VÁLIDO
                del ordem[:]
                self._resp_com_status(cupom)
                self.assertEqual(ordem, ["cupom", "afiliado"],
                                 f"'{cupom}' não fez as duas consultas na mesma ordem")
        finally:
            self.db.cupom_desconto, self.db.afiliado_por_codigo = o_cup, o_af


class TestPreviaMesmaOrigem(_BasePrevia):
    """Amplificador apontado na revisão: o endpoint aceita urlencoded (sem preflight)
    e não checava origem, então qualquer página de terceiro queimava, do navegador do
    visitante, a cota de cupom DELE. `Origin` é escrito pelo navegador e não é
    forjável por script."""

    SITE = {"Host": "curso.example", "Origin": "https://curso.example"}

    def test_pagina_de_terceiro_nao_queima_a_cota_do_visitante(self):
        ip = "203.0.113.60"
        alheio = {"Host": "curso.example", "Origin": "https://evil.example"}
        for _ in range(20):
            r = self._resp(cupom="CHUTE", ip=ip, extra=alheio)
            self.assertFalse(r["ok"])
        # a cota do visitante tem que estar intacta: 5 chutes DELE ainda passam
        for i in range(5):
            r = self._resp(cupom=f"CHUTE-{i}", ip=ip, extra=self.SITE)
            self.assertFalse(r.get("bloqueado"),
                             f"tentativa própria {i+1} barrada — a cota foi queimada "
                             f"por uma página de terceiro")

    def test_referer_de_terceiro_tambem_e_recusado(self):
        r = self._resp(cupom="LANCAMENTO", ip="203.0.113.61",
                       extra={"Host": "curso.example", "Referer": "https://evil.example/x"})
        self.assertFalse(r["ok"])

    def test_origem_do_proprio_site_funciona_normalmente(self):
        r = self._resp(cupom="LANCAMENTO", ip="203.0.113.62", extra=self.SITE)
        self.assertTrue(r["ok"], f"requisição legítima do próprio /assinar: {r}")

    def test_sem_origin_nem_referer_libera(self):
        """Fail-open deliberado: se um proxy remover os dois cabeçalhos, a prévia não
        pode desligar pra todo mundo."""
        r = self._resp(cupom="LANCAMENTO", ip="203.0.113.63",
                       extra={"Host": "curso.example"})
        self.assertTrue(r["ok"], r)


class TestCotaCompartilhadaEntrePreviaEcheckout(unittest.TestCase):
    """Decisão do dono na consolidação rate_limit.py/ratelimit.py (2026-07-29): as
    duas rotas de cupom — `/assinar` (checkout, `_post_assinar`) e `/assinar/cupom`
    (prévia, leitura-only) — têm que COMPARTILHAR um único balde de cota. Sharing é
    o comportamento correto de segurança: senão um atacante ganha 5 chutes na
    prévia (mais barata/rápida — é o oráculo mais barato dos dois) e mais 5 no
    checkout, dobrando de graça o orçamento de força-bruta. O repoint das duas rotas
    pro `rate_limit.py` usa a MESMA chave (`f"cupom:{ip}"`) nos dois pontos de
    chamada de propósito — é isso que este teste prova; sem ele, um repoint que
    desse chaves diferentes pra cada rota passaria despercebido (a suíte ficaria
    verde do mesmo jeito, só que com metade da proteção)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        os.environ.pop("DATABASE_URL", None)
        for m in ("config", "db", "subscribers", "serve", "site_web", "legal",
                  "asaas", "pricing", "rate_limit"):
            sys.modules.pop(m, None)
        import db, subscribers, legal, serve, rate_limit
        db._INITED = False
        db.init()
        rate_limit.resetar()
        self.db, self.subscribers, self.legal, self.serve = db, subscribers, legal, serve
        self.rate_limit = rate_limit

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.rate_limit.resetar()

    def _g(self, **over):
        base = {"plano": "mensal", "nome": "Cliente Teste", "email": "cliente@example.com",
                "cpf": "11144477735", "whatsapp": "43999990000", "metodo": "PIX",
                "parcelas": "1", "cupom": "", "aceito": "1"}
        base.update(over)
        return lambda k: base.get(k, "")

    def _mock_asaas(self):
        import asaas
        checkouts = []
        orig_criar = asaas.criar_checkout
        asaas.criar_checkout = lambda payload: checkouts.append(payload) or {
            "url": "https://checkout.asaas.example/x", "id": "chk_x"}
        return asaas, checkouts, orig_criar

    def _previa(self, ip, cupom="CHUTE"):
        import urllib.parse as up
        Stub = _make_cupom_previa_stub_cls()
        body = up.urlencode({"plano": "anual", "cupom": cupom, "metodo": "CARTAO"}).encode("utf-8")
        stub = Stub("/assinar/cupom", body=body, ip=ip)
        return stub.do_POST()

    def test_5_tentativas_na_previa_esgotam_a_cota_do_checkout(self):
        ip = "203.0.113.201"
        for i in range(5):
            r = self._previa(ip, cupom=f"CHUTE-{i}")
            self.assertFalse(r["ok"])
        # cota já gasta na prévia -> o checkout, MESMO ip, chega bloqueado
        asaas, checkouts, orig_criar = self._mock_asaas()
        stub = _AssinarStub(ip=ip)
        try:
            bloqueado = self.serve.Handler._post_assinar(stub, self._g(cupom="CHUTE-6"))
        finally:
            asaas.criar_checkout = orig_criar
        self.assertIn("Muitas tentativas", bloqueado,
                      "as duas rotas tem que compartilhar cota -- 5 chutes na "
                      "previa tem que esgotar tambem o checkout")
        self.assertEqual(len(checkouts), 0, "nao pode ter chegado no Asaas")

    def test_5_tentativas_no_checkout_esgotam_a_cota_da_previa(self):
        ip = "203.0.113.202"
        asaas, checkouts, orig_criar = self._mock_asaas()
        stub = _AssinarStub(ip=ip)
        try:
            for i in range(5):
                self.serve.Handler._post_assinar(stub, self._g(cupom=f"CHUTE-{i}"))
        finally:
            asaas.criar_checkout = orig_criar
        r = self._previa(ip, cupom="CHUTE-6")
        self.assertTrue(r.get("bloqueado"),
                        f"5 chutes no checkout tem que esgotar tambem a previa: {r}")

    def test_ips_diferentes_nao_compartilham_nada(self):
        # controle: a cota é POR IP -- não é um balde global disfarçado de
        # "compartilhado"
        self._previa("203.0.113.211", cupom="X")
        r = self._previa("203.0.113.212", cupom="Y")
        self.assertFalse(r.get("bloqueado"), "IP diferente nao pode herdar bloqueio nenhum")


if __name__ == "__main__":
    unittest.main()
