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


if __name__ == "__main__":
    unittest.main()
