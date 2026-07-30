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

    def __init__(self, path, body=b"", ip="203.0.113.9"):
        self.path = path
        self.headers = {"Content-Length": str(len(body)),
                        "Content-Type": "application/x-www-form-urlencoded"}
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
        self.assertTrue(r["parcelas"], "o dropdown de parcelas tem que vir atualizado")

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
