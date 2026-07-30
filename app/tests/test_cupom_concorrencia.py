"""CRITICAL da revisão final fatiada (2026-07-29): o limite de tentativas de cupom
não fazia NADA sob concorrência.

O desenho anterior era peek-then-count: `rate_limit.limitado(..., registrar=False)`
só ESPIAVA (não gravava), e o `registrar_tentativa` correspondente só rodava DEPOIS
do lookup do cupom — uma ida ao banco inteira depois. Sob `ThreadingHTTPServer`,
toda thread de uma rajada espia a contagem 0 e passa: 50/50 chutes avaliados na
prévia e 40/40 no `POST /assinar`, com teto pretendido de 5. O oráculo que o limite
existe pra fechar (um cupom de CORTESIA acertado cria assinante ATIVO na hora, sem
Asaas — acesso de graça, não desconto) seguia aberto pra qualquer script.

Estes testes são CONCORRENTES DE PROPÓSITO: a versão sequencial deles passa contra
o código quebrado (sequencialmente o `registrar_tentativa` do chute N já aconteceu
antes do peek do chute N+1). A janela de corrida é aberta de forma DETERMINÍSTICA,
sem `time.sleep`: o lookup do cupom é trocado por um portão (`_Portao`) que segura
cada thread lá dentro até que as N decisões de limite já tenham sido tomadas — é o
equivalente exato do "lookup de 50 ms" da prova do revisor, só que sem depender de
relógio nenhum.

Standalone: python3 app/tests/test_cupom_concorrencia.py
"""
import io
import os
import sys
import tempfile
import threading
import unittest
import urllib.parse as up

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TETO = 5            # mesmo teto das duas rotas (5 tentativas / 600 s por IP)
N_PREVIA = 50       # tamanho da rajada na prévia (o mesmo da prova do revisor)
N_CHECKOUT = 40     # tamanho da rajada no POST /assinar (idem)


class _Portao:
    """Segura a PRIMEIRA chamada de cada thread dentro do lookup do cupom, abrindo
    a janela de corrida sem `time.sleep`.

    - `entrar()`: chamado de dentro do lookup falso. Registra a thread como
      "avaliada" (ela passou pelo limite) e dorme no `Event` até o teste liberar.
      Só a 1ª entrada de cada thread segura — `db.cupom_desconto` chama
      `db.obter_cupom` por dentro, então a mesma thread pode reentrar depois de
      liberada e não pode contar/segurar duas vezes.
    - `bloqueado()`: chamado pela thread que o limite barrou (ela nunca chega no
      lookup) — também é uma decisão tomada.
    - `esperar_decisoes(n)`: bloqueia até as n threads terem decidido. Usa
      `Semaphore.acquire` (bloqueante, sem polling e sem sleep).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._liberado = threading.Event()
        self._decidiu = threading.Semaphore(0)
        self.avaliados = set()          # ids das threads que passaram do limite

    def entrar(self):
        tid = threading.get_ident()
        with self._lock:
            primeira = tid not in self.avaliados
            self.avaliados.add(tid)
        if primeira:
            self._decidiu.release()
            self._liberado.wait(30.0)   # timeout só pra nunca pendurar a suíte

    def bloqueado(self):
        self._decidiu.release()

    def esperar_decisoes(self, n, timeout=30.0):
        return all(self._decidiu.acquire(timeout=timeout) for _ in range(n))

    def liberar(self):
        self._liberado.set()

    @property
    def avaliadas(self):
        return len(self.avaliados)


class _PreviaStub:
    """Mesmo padrão de `_CupomPreviaStub` (test_cupom_previa.py): herda de
    `serve.Handler` pra rodar o `do_POST` real e sobrescreve só entrada/saída."""

    def __init__(self, body=b"", ip="203.0.113.9"):
        self.path = "/assinar/cupom"
        self.headers = {"Content-Length": str(len(body)),
                        "Content-Type": "application/x-www-form-urlencoded"}
        self.rfile = io.BytesIO(body)
        self.client_address = (ip, 54321)

    def _json(self, obj, code=200):
        return obj

    def _html(self, s, code=200):
        return (code, s)

    def _redirect(self, location, token=None, clear=False):
        return ("REDIRECT", location)


class _AssinarStub:
    """Mesmo padrão de `_AssinarStub` (test_cupom_previa.py): só o que
    `_post_assinar` usa."""

    def __init__(self, ip="203.0.113.9"):
        self.headers = {}
        self.client_address = (ip, 54321)

    def _html(self, s, code=200):
        return s

    def _redirect(self, location, token=None, clear=False):
        return f"<redirect {location}>"

    def _ip_cliente(self):
        import serve
        return serve.Handler._ip_cliente(self)


class _BaseConcorrencia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        os.environ.pop("DATABASE_URL", None)
        for m in ("config", "db", "subscribers", "serve", "site_web", "site_legal",
                  "legal", "asaas", "pricing", "rate_limit", "renovacao"):
            sys.modules.pop(m, None)
        import db, rate_limit, serve
        db._INITED = False
        db.init()                       # já inicializado -> `db.init()` da rota é no-op
        rate_limit.resetar()
        self.db, self.rate_limit, self.serve = db, rate_limit, serve
        self.portao = _Portao()

    def tearDown(self):
        import shutil
        self.portao.liberar()           # nunca deixa thread pendurada
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.rate_limit.resetar()

    def _rodar(self, alvo, n):
        ts = [threading.Thread(target=alvo, args=(i,), daemon=True) for i in range(n)]
        for t in ts:
            t.start()
        self.assertTrue(self.portao.esperar_decisoes(n),
                        f"as {n} threads deviam ter decidido (passou do limite ou "
                        f"foi barrada) — timeout indica caminho de saída inesperado")
        self.portao.liberar()
        for t in ts:
            t.join(30.0)


class TestRajadaNaPrevia(_BaseConcorrencia):
    """`POST /assinar/cupom` — o oráculo mais barato dos dois."""

    def test_rajada_concorrente_nao_passa_do_teto(self):
        portao = self.portao
        respostas = []
        lk = threading.Lock()

        orig = self.db.cupom_desconto

        def gate_desconto(codigo, plano_slug):
            portao.entrar()
            return orig(codigo, plano_slug)

        self.db.cupom_desconto = gate_desconto

        def chuta(i):
            body = up.urlencode({"plano": "anual", "cupom": f"CHUTE-{i}",
                                 "metodo": "CARTAO"}).encode("utf-8")
            Stub = type("_S", (_PreviaStub, self.serve.Handler), {})
            r = Stub(body=body, ip="198.51.100.77").do_POST()
            with lk:
                respostas.append(r)
            if isinstance(r, dict) and r.get("bloqueado"):
                portao.bloqueado()

        try:
            self._rodar(chuta, N_PREVIA)
        finally:
            self.db.cupom_desconto = orig

        bloqueadas = sum(1 for r in respostas if isinstance(r, dict) and r.get("bloqueado"))
        self.assertLessEqual(
            portao.avaliadas, TETO,
            f"{portao.avaliadas} de {N_PREVIA} chutes CONCORRENTES foram avaliados "
            f"(teto {TETO}) — o limite tem que gravar a tentativa ATOMICAMENTE na "
            f"mesma chamada que checa, senão toda a rajada lê contagem 0 e passa")
        self.assertEqual(len(respostas), N_PREVIA)
        self.assertEqual(bloqueadas, N_PREVIA - portao.avaliadas,
                         "quem não foi avaliado tem que ter sido barrado explicitamente")


class TestRajadaNoCheckout(_BaseConcorrencia):
    """`POST /assinar` — o caminho que importa: é aqui que um cupom de CORTESIA
    acertado vira assinante ATIVO na hora, sem passar pelo Asaas."""

    def _g(self, i):
        base = {"plano": "anual", "nome": "Cliente Teste", "email": "c@example.com",
                "cpf": "11144477735", "whatsapp": "43999990000", "metodo": "PIX",
                "parcelas": "1", "cupom": f"CHUTE-{i}", "aceito": "1"}
        return lambda k: base.get(k, "")

    def test_rajada_concorrente_nao_passa_do_teto(self):
        import asaas
        portao = self.portao
        respostas = []
        lk = threading.Lock()

        orig_cupom = self.db.obter_cupom
        orig_asaas = asaas.criar_checkout
        asaas.criar_checkout = lambda payload: {"url": "https://checkout.asaas.example/x",
                                                "id": "chk_x"}

        def gate_obter(codigo):
            portao.entrar()
            return orig_cupom(codigo)

        self.db.obter_cupom = gate_obter

        def chuta(i):
            r = self.serve.Handler._post_assinar(_AssinarStub(ip="198.51.100.88"), self._g(i))
            with lk:
                respostas.append(r)
            if isinstance(r, str) and "Muitas tentativas" in r:
                portao.bloqueado()

        try:
            self._rodar(chuta, N_CHECKOUT)
        finally:
            self.db.obter_cupom = orig_cupom
            asaas.criar_checkout = orig_asaas

        bloqueadas = sum(1 for r in respostas
                         if isinstance(r, str) and "Muitas tentativas" in r)
        self.assertLessEqual(
            portao.avaliadas, TETO,
            f"{portao.avaliadas} de {N_CHECKOUT} chutes CONCORRENTES no checkout "
            f"foram avaliados (teto {TETO}) — este é o caminho do oráculo de "
            f"cortesia (acesso grátis), não só o da prévia")
        self.assertEqual(len(respostas), N_CHECKOUT)
        self.assertEqual(bloqueadas, N_CHECKOUT - portao.avaliadas)


if __name__ == "__main__":
    unittest.main()
