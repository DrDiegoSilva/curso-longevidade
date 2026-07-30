"""Task 1 (spec 2026-07-29-cupom-previa): limite de tentativas de cupom por IP.

Fecha um oráculo já exposto: POST /assinar aceitava chutar códigos de cupom sem
nenhum limite, e um cupom de CORTESIA acertado cria assinante ATIVO na hora, sem
passar pelo Asaas (serve.py:1356) — acesso de graça, não desconto."""
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRateLimit(unittest.TestCase):
    def setUp(self):
        import ratelimit
        ratelimit.zerar()          # estado limpo entre testes
        self.rl = ratelimit

    def test_permite_ate_o_limite_e_barra_depois(self):
        for i in range(5):
            self.assertTrue(self.rl.permitir("ip-1", limite=5, janela_s=600),
                            f"tentativa {i+1} devia passar")
            self.rl.registrar_falha("ip-1", janela_s=600)
        self.assertFalse(self.rl.permitir("ip-1", limite=5, janela_s=600),
                         "a 6a tentativa depois de 5 falhas tem que barrar")

    def test_chaves_independentes(self):
        for _ in range(5):
            self.rl.registrar_falha("ip-1", janela_s=600)
        self.assertFalse(self.rl.permitir("ip-1", limite=5, janela_s=600))
        self.assertTrue(self.rl.permitir("ip-2", limite=5, janela_s=600),
                        "um IP nao pode bloquear outro")

    def test_janela_expira(self):
        for _ in range(5):
            self.rl.registrar_falha("ip-1", janela_s=1)
        self.assertFalse(self.rl.permitir("ip-1", limite=5, janela_s=1))
        time.sleep(1.1)
        self.assertTrue(self.rl.permitir("ip-1", limite=5, janela_s=1),
                        "passada a janela, libera")

    def test_eviccao_nao_deixa_o_dict_crescer_sem_limite(self):
        for i in range(500):
            self.rl.registrar_falha(f"ip-{i}", janela_s=1)
        time.sleep(1.1)
        self.rl.permitir("gatilho", limite=5, janela_s=1)   # a chamada faz a limpeza
        self.assertLess(self.rl.tamanho(), 500,
                        "entradas vencidas tem que ser removidas, senao vaza memoria")

    def test_concorrencia_nao_corrompe_a_contagem(self):
        import threading
        def bate():
            for _ in range(20):
                self.rl.registrar_falha("ip-x", janela_s=600)
        ts = [threading.Thread(target=bate) for _ in range(10)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        # 10 threads x 20 = 200 falhas; sem lock a contagem se perde
        self.assertFalse(self.rl.permitir("ip-x", limite=199, janela_s=600),
                         "200 falhas registradas -> limite 199 tem que barrar")


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
    """Exercita `serve.Handler._post_assinar` de verdade (não só `ratelimit.py`
    isolado) — mesmo harness de test_precos_lancamento.py::TestCupomLancamentoNaRotaAssinar
    e test_aceite_checkout.py::TestGateDeAceiteNoPostAssinar (`_AssinarStub` + `g` como
    o `form.get(k, [""])[0]` do POST real)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        os.environ.pop("DATABASE_URL", None)
        for m in ("config", "db", "subscribers", "serve", "site_legal", "site_web",
                  "legal", "asaas", "pricing", "ratelimit"):
            sys.modules.pop(m, None)
        import db, subscribers, legal, serve, ratelimit
        db._INITED = False
        db.init()
        ratelimit.zerar()
        self.db, self.subscribers, self.legal = db, subscribers, legal
        self.serve, self.ratelimit = serve, ratelimit

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.ratelimit.zerar()

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


if __name__ == "__main__":
    unittest.main()
