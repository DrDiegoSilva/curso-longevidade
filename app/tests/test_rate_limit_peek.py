"""Cobre duas coisas da consolidação rate_limit/ratelimit (2026-07-29):

1) A extensão de `rate_limit.limitado` com o modo peek (`registrar=False`) e o par
   `registrar_tentativa` — precisos pro caminho de cupom, onde checar e contar têm
   que ser separáveis (cupom válido não pode gastar cota). Também prova que o modo
   `registrar=True` (o único que login/OTP/recuperação usam) continua byte-a-byte
   igual ao de antes da extensão.

2) O fix de `_rate_ok` (Item 2): antes chaveava por `client_address`, que atrás do
   proxy reverso deste deploy é IDÊNTICO pra todo visitante — um bucket global.
   Agora chaveia por `self._ip_cliente()` (último elemento não-vazio do
   X-Forwarded-For, escrito pelo proxy, não forjável pelo cliente).

Standalone: python3 app/tests/test_rate_limit_peek.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rate_limit


class _RateOkStub:
    """Stub mínimo pro `self` de `_rate_ok`: só `headers`/`client_address`/`_html`
    (mesmo padrão dos outros stubs da suíte — não abre socket, não é request real)."""

    def __init__(self, ip_proxy="10.0.0.1", xff=None):
        self.client_address = (ip_proxy, 54321)
        self.headers = {} if xff is None else {"X-Forwarded-For": xff}
        self.html_calls = []

    def _html(self, s, code=200):
        self.html_calls.append((s, code))

    def _ip_cliente(self):
        # `_rate_ok` resolve o IP via `Handler._ip_cliente` — este stub não herda de
        # `Handler`, então só encaminha pra implementação real (mesmo padrão de
        # `_AssinarStub._ip_cliente` em test_cupom_previa.py) em vez de duplicá-la.
        import serve
        return serve.Handler._ip_cliente(self)


class TestLimitadoPeekMode(unittest.TestCase):
    """`registrar=False` tem que ser um peek puro: a chamada em si nunca conta."""

    def setUp(self):
        rate_limit.resetar()

    def test_peek_nunca_estoura_sozinho(self):
        t = 1000.0
        for _ in range(50):
            self.assertFalse(
                rate_limit.limitado("k", 3, 60, agora=t, registrar=False),
                "peek nao pode contar - nunca deveria estourar sozinho, por mais "
                "vezes que for chamado")

    def test_peek_reflete_o_que_ja_foi_registrado_antes(self):
        t = 1000.0
        rate_limit.limitado("k", 3, 60, agora=t)          # 1a (conta)
        rate_limit.limitado("k", 3, 60, agora=t + 1)       # 2a (conta)
        self.assertFalse(
            rate_limit.limitado("k", 3, 60, agora=t + 2, registrar=False),
            "so 2 tentativas reais registradas, limite 3 - ainda nao estourou")
        rate_limit.limitado("k", 3, 60, agora=t + 2)       # 3a (conta)
        self.assertTrue(
            rate_limit.limitado("k", 3, 60, agora=t + 3, registrar=False),
            "3 tentativas reais registradas, limite 3 - o peek tem que ver que estourou")

    def test_peeks_repetidos_nao_deixam_residuo_pro_registrar_real_seguinte(self):
        t = 1000.0
        for i in range(20):
            rate_limit.limitado("k", 3, 60, agora=t + i, registrar=False)
        # se o peek tivesse contado qualquer coisa, as 3 tentativas REAIS abaixo já
        # estourariam antes da hora
        self.assertFalse(rate_limit.limitado("k", 3, 60, agora=t))
        self.assertFalse(rate_limit.limitado("k", 3, 60, agora=t + 1))
        self.assertFalse(rate_limit.limitado("k", 3, 60, agora=t + 2))
        self.assertTrue(rate_limit.limitado("k", 3, 60, agora=t + 3),
                        "3 tentativas reais registradas -> 4a estoura, apesar dos "
                        "20 peeks antes")


class TestRegistrarTentativa(unittest.TestCase):
    """`registrar_tentativa` é o par do peek: conta 1 tentativa sem checar limite
    nenhum — chamado só depois que quem chama já decidiu que a tentativa falhou
    (ex.: cupom inválido)."""

    def setUp(self):
        rate_limit.resetar()

    def test_registra_sem_checar_limite_nenhum(self):
        t = 1000.0
        rate_limit.registrar_tentativa("k", 60, agora=t)
        rate_limit.registrar_tentativa("k", 60, agora=t)
        rate_limit.registrar_tentativa("k", 60, agora=t)
        # 3 registradas -> um peek com limite 3 tem que ver que estourou
        self.assertTrue(rate_limit.limitado("k", 3, 60, agora=t, registrar=False))

    def test_janela_expira_tambem_pro_que_foi_registrado_assim(self):
        t = 1000.0
        rate_limit.registrar_tentativa("k", 1, agora=t)
        self.assertTrue(rate_limit.limitado("k", 1, 1, agora=t, registrar=False))
        self.assertFalse(
            rate_limit.limitado("k", 1, 1, agora=t + 5, registrar=False),
            "janela de 1s passou -> peek com agora=t+5 tem que liberar de novo")

    def test_nao_atrapalha_chave_diferente(self):
        t = 1000.0
        for _ in range(5):
            rate_limit.registrar_tentativa("a", 60, agora=t)
        self.assertFalse(rate_limit.limitado("b", 3, 60, agora=t, registrar=False),
                         "chave diferente nao pode ser afetada")


class TestLimitadoComportamentoExistenteInalterado(unittest.TestCase):
    """Regressão: `registrar=True` (o default — o único modo que login/OTP/
    recuperação usam) tem que se comportar EXATAMENTE como antes da extensão do
    peek. Espelha os testes originais em tests/test_rate_limit.py (legado, fora de
    app/), aqui dentro da suíte oficial."""

    def setUp(self):
        rate_limit.resetar()

    def test_libera_ate_o_maximo_e_barra_depois(self):
        t = 1000.0
        self.assertFalse(rate_limit.limitado("k", 3, 60, agora=t))
        self.assertFalse(rate_limit.limitado("k", 3, 60, agora=t + 1))
        self.assertFalse(rate_limit.limitado("k", 3, 60, agora=t + 2))
        self.assertTrue(rate_limit.limitado("k", 3, 60, agora=t + 3))

    def test_janela_desliza_e_libera_de_novo(self):
        t = 1000.0
        for i in range(3):
            rate_limit.limitado("k", 3, 60, agora=t + i)
        self.assertTrue(rate_limit.limitado("k", 3, 60, agora=t + 4))
        self.assertFalse(rate_limit.limitado("k", 3, 60, agora=t + 200))

    def test_chaves_independentes(self):
        t = 1000.0
        for _ in range(3):
            rate_limit.limitado("a", 3, 60, agora=t)
        self.assertTrue(rate_limit.limitado("a", 3, 60, agora=t))
        self.assertFalse(rate_limit.limitado("b", 3, 60, agora=t))

    def test_nao_conta_a_tentativa_que_foi_barrada(self):
        t = 1000.0
        for i in range(3):
            rate_limit.limitado("k", 3, 60, agora=t + i)
        self.assertTrue(rate_limit.limitado("k", 3, 60, agora=t + 3))    # barrada
        self.assertTrue(rate_limit.limitado("k", 3, 60, agora=t + 3.1))  # continua barrada


class TestRateOkChavePorClienteReal(unittest.TestCase):
    """Item 2: `_rate_ok` tinha que chavear pelo IP do CLIENTE, não pelo
    `client_address` — atrás do proxy reverso deste deploy (Traefik), TODO
    visitante chega com o MESMO `client_address` (o do proxy), então chavear por
    ele juntava todo mundo num balde só: os 5 códigos de OTP por 10 min viravam 5
    códigos pro SITE INTEIRO, e uma pessoa exaurindo a cota trancava o login de
    todo mundo."""

    def setUp(self):
        rate_limit.resetar()
        import serve
        self.serve = serve

    def _rate_ok(self, stub, nome="otp", maximo=5, janela_seg=600):
        return self.serve.Handler._rate_ok(stub, nome, maximo, janela_seg)

    def test_dois_clientes_atras_do_mesmo_proxy_tem_baldes_independentes(self):
        proxy_ip = "10.0.0.1"    # client_address (o TCP peer da app) - o proxy, IDÊNTICO
        # `client_address` (acima) é o do proxy pros dois; o XFF é que carrega o IP
        # real de CADA cliente, no ÚLTIMO elemento (o que o proxy anexa, não forjável).
        a = _RateOkStub(ip_proxy=proxy_ip, xff="1.1.1.1, 203.0.113.10")
        b = _RateOkStub(ip_proxy=proxy_ip, xff="1.1.1.1, 203.0.113.20")
        for i in range(5):
            self.assertTrue(self._rate_ok(a, maximo=5),
                            f"cliente A tentativa {i+1}/5 ainda devia passar")
        self.assertFalse(self._rate_ok(a, maximo=5), "cliente A estourou a própria cota")
        # cliente B, atrás do MESMO proxy (mesmo client_address), tem que seguir livre
        self.assertTrue(
            self._rate_ok(b, maximo=5),
            "cliente B não pode ser barrado só por compartilhar o client_address "
            "(IP do proxy) com o A — o bucket tem que ser por cliente real (XFF)")

    def test_um_cliente_exaurindo_a_cota_nao_bloqueia_o_outro(self):
        proxy_ip = "10.0.0.1"
        a = _RateOkStub(ip_proxy=proxy_ip, xff="1.1.1.1, 198.51.100.5")
        b = _RateOkStub(ip_proxy=proxy_ip, xff="1.1.1.1, 198.51.100.6")
        for _ in range(5):
            self._rate_ok(a, maximo=5)
        self.assertFalse(self._rate_ok(a, maximo=5), "cliente A esgotou a cota")
        for i in range(5):
            self.assertTrue(self._rate_ok(b, maximo=5),
                            f"cliente B tentativa {i+1}/5 bloqueada pelo consumo do A")

    def test_sem_xff_cai_no_client_address_e_ainda_bloqueia_o_proprio_ip(self):
        stub = _RateOkStub(ip_proxy="203.0.113.99", xff=None)
        for i in range(5):
            self.assertTrue(self._rate_ok(stub, maximo=5),
                            f"tentativa {i+1}/5 sem XFF ainda devia passar")
        self.assertFalse(self._rate_ok(stub, maximo=5),
                         "sem XFF, cai no client_address, que ainda tem que ser limitado")


class TestRateLimitEviccaoEConcorrencia(unittest.TestCase):
    """Migrado de test_cupom_previa.py::TestRateLimit — testava `ratelimit.py`
    (deletado nesta consolidação) diretamente. As asserções de limite/janela/chaves
    independentes daquela classe já estavam duplicadas em
    TestLimitadoComportamentoExistenteInalterado (mesmo comportamento, `rate_limit.py`
    já era testado assim) e foram descartadas como cobertura repetida da FORMA do
    módulo apagado. Estas duas são comportamento genuíno que `rate_limit.py` nunca
    tinha testado (evicção por teto de memória, thread-safety do `_lock`) — migradas
    de verdade, preferindo `agora=` injetado a `time.sleep` onde dava (a evicção usa
    relógio injetado; a concorrência precisa de threads reais, que não dá pra
    mockar, então usa o relógio de verdade só ali)."""

    def setUp(self):
        rate_limit.resetar()

    def test_eviccao_nao_deixa_o_dict_crescer_sem_limite(self):
        # rate_limit.py só poda quando o dicionário passa de _MAX_CHAVES (5000) —
        # mais preguiçoso que o ratelimit.py original (que podava a CADA chamada de
        # `permitir`), então precisa passar do teto de verdade pra provar a evicção.
        t = 1000.0
        for i in range(5100):
            rate_limit.registrar_tentativa(f"ip-{i}", 1, agora=t)
        # janela de 1s já vencida em t+2; uma escrita nova dispara a poda preguiçosa
        rate_limit.registrar_tentativa("gatilho", 1, agora=t + 2)
        self.assertLess(rate_limit.tamanho(), 5100,
                        "entradas vencidas tem que ser removidas quando o teto estoura, "
                        "senao vaza memoria")

    def test_concorrencia_nao_corrompe_a_contagem(self):
        # Usa `limitado(..., registrar=True)` (não `registrar_tentativa`) de propósito:
        # o caminho de escrita dele é ler-copiar-regravar a lista inteira
        # (`xs = [...]` novo objeto, depois `_hits[chave] = xs`) — um read-modify-write
        # de verdade, que perde incrementos sem lock. `registrar_tentativa` só faz
        # `.append()` na MESMA lista compartilhada, que o GIL do CPython já serializa
        # sozinho — não provaria que o lock importa.
        import threading
        def bate():
            for _ in range(20):
                rate_limit.limitado("ip-x", 1000, 600)   # alto o bastante p/ nunca barrar
        ts = [threading.Thread(target=bate) for _ in range(10)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        # 10 threads x 20 = 200 tentativas; sem lock a contagem se perde
        self.assertTrue(rate_limit.limitado("ip-x", 199, 600, registrar=False),
                        "200 tentativas registradas -> limite 199 tem que barrar")


if __name__ == "__main__":
    unittest.main()
