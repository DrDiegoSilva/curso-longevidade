"""Preços de lançamento + cupom LANCAMENTO (valor fixo). Standalone."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _reload_db(tmp):
    os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(tmp, "t.db")
    os.environ.pop("DATABASE_URL", None)
    import importlib, db as _db
    importlib.reload(_db)
    _db.init()
    return _db


class TestCupomFixo(unittest.TestCase):
    def setUp(self):
        self.snap = (os.environ.get("DSCURSO_ARTIGOS_DB"), os.environ.get("DATABASE_URL"))
        self.tmp = tempfile.mkdtemp()
        self.db = _reload_db(self.tmp)

    def tearDown(self):
        import shutil, importlib
        a, d = self.snap
        os.environ["DSCURSO_ARTIGOS_DB"] = a if a is not None else ""
        if a is None:
            os.environ.pop("DSCURSO_ARTIGOS_DB", None)
        if d is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = d
        import db as _db
        importlib.reload(_db)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_seed_lancamento_existe(self):
        info = self.db.obter_cupom("LANCAMENTO")
        self.assertIsNotNone(info)
        self.assertEqual(float(info["desconto_valor"]), 500.0)
        self.assertEqual(info["plano_slug"], "anual")
        self.assertEqual(info["uso_unico"], 0)          # multi-uso
        self.assertEqual(info["ativo"], 1)

    def test_cupom_desconto_escopo(self):
        self.assertEqual(self.db.cupom_desconto("LANCAMENTO", "anual"), 500.0)
        self.assertEqual(self.db.cupom_desconto("LANCAMENTO", "mensal"), 0.0)   # fora do escopo
        self.assertEqual(self.db.cupom_desconto("INEXISTENTE", "anual"), 0.0)

    def test_cupom_desconto_ignora_cortesia(self):
        self.db.criar_cupom(codigo="CORTESIA30", dias_acesso=30)               # cortesia, sem desconto_valor
        self.assertEqual(self.db.cupom_desconto("CORTESIA30", "anual"), 0.0)

    def test_cupom_desconto_inativo(self):
        self.db.criar_cupom(codigo="PROMO2", desconto_valor=200, plano_slug="", uso_unico=True)
        self.assertEqual(self.db.cupom_desconto("PROMO2", "anual"), 200.0)     # escopo vazio = qualquer plano
        self.db.consumir_cupom("PROMO2")                                       # uso único -> desativa
        self.assertEqual(self.db.cupom_desconto("PROMO2", "anual"), 0.0)       # inativo -> 0

    def test_seed_lancamento_autocorrige_cortesia_preexistente(self):
        """Footgun (MEDIUM, revisão final): se uma linha 'LANCAMENTO' já existe como
        CORTESIA (desconto_valor=0, dias_acesso>0 — ex. veio do env DSCURSO_CUPONS, cujo
        loop roda antes deste seed) o re-seed tem que CORRIGIR a linha pro formato
        promocional, não deixá-la como está (o antigo ON CONFLICT DO NOTHING deixava, o
        que dava assinatura anual grátis pra quem usasse LANCAMENTO)."""
        # `db.init()` (chamado no setUp) já rodou `_seed_cupons()` uma vez, então a linha
        # 'LANCAMENTO' já existe no formato promocional. `criar_cupom` usa DO NOTHING, então
        # não sobrescreve — força a forma CORTESIA direto (é o que o env DSCURSO_CUPONS ou
        # uma linha antiga de produção deixariam) pra simular o footgun antes de re-rodar o seed.
        with self.db._conn() as c:
            c.execute("UPDATE cupons SET desconto_valor=0, dias_acesso=30, plano_slug='' "
                      "WHERE codigo='LANCAMENTO'")
        cortesia = self.db.obter_cupom("LANCAMENTO")
        self.assertEqual(float(cortesia["desconto_valor"]), 0.0)
        self.assertEqual(cortesia["dias_acesso"], 30)

        self.db._seed_cupons()   # re-roda o seed (init() é guardado por _INITED)

        info = self.db.obter_cupom("LANCAMENTO")
        self.assertEqual(float(info["desconto_valor"]), 500.0)
        self.assertEqual(info["dias_acesso"], 0)
        self.assertEqual(info["plano_slug"], "anual")
        self.assertEqual(info["ativo"], 1)
        self.assertEqual(info["uso_unico"], 0)
        # E o efeito prático: não dá mais acesso grátis, sempre desconta no checkout pago.
        self.assertEqual(self.db.cupom_desconto("LANCAMENTO", "anual"), 500.0)


class TestBaseCobradaFixo(unittest.TestCase):
    def setUp(self):
        import pricing, config
        self.p, self.cfg = pricing, config
        self.anual = self.cfg.plano_por_slug("anual")

    def test_cupom_fixo_cartao(self):
        # 1497 - 500 = 997 (cartão não tem desconto Pix)
        self.assertEqual(self.p.base_cobrada(self.anual, "CARTAO", 1497.0, 0.0, 500.0), 997.0)

    def test_cupom_fixo_pix_empilha(self):
        # 1497 - 500 = 997, depois Pix 5% -> 947.15
        self.assertEqual(self.p.base_cobrada(self.anual, "PIX", 1497.0, 0.0, 500.0), 947.15)

    def test_retrocompat_sem_cupom_valor(self):
        # chamada antiga (4 args) inalterada
        self.assertEqual(self.p.base_cobrada(self.anual, "CARTAO", 1497.0, 0.0), 1497.0)
        self.assertEqual(self.p.base_cobrada(self.anual, "PIX", 1497.0, 0.0), round(1497.0 * 0.95, 2))

    def test_nao_fica_negativo(self):
        self.assertEqual(self.p.base_cobrada(self.anual, "CARTAO", 300.0, 0.0, 500.0), 0.0)


class _AssinarStub:
    """Stub mínimo pro `self` de `_post_assinar` — mesmo padrão de
    `test_aceite_checkout.py::_AssinarStub`: implementa só o que o método usa
    (`headers`, `client_address`, `_html`, `_redirect`), não abre socket."""

    def __init__(self, ip="203.0.113.9"):
        self.headers = {}
        self.client_address = (ip, 54321)

    def _html(self, s, code=200):
        return s

    def _redirect(self, location, token=None, clear=False):
        return f"<redirect {location}>"


class TestCupomLancamentoNaRotaAssinar(unittest.TestCase):
    """Trava a propriedade de segurança do dinheiro do cupom LANCAMENTO na rota de
    verdade (`serve.Handler._post_assinar`), não só nas funções puras acima: o cupom
    promocional (desconto_valor>0) tem que SEMPRE cair no caminho pago do Asaas, nunca
    no caminho de cortesia (`subscribers.criar_de_pagamento` com status ATIVO direto,
    sem pagamento). Mesmo harness de `test_aceite_checkout.py::TestGateDeAceiteNoPostAssinar`
    (stub mínimo + `g` como o `form.get(k, [""])[0]` do POST real) — reaproveitado aqui
    porque LANCAMENTO já é semeado por `db.init()`."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        os.environ.pop("DATABASE_URL", None)
        for m in ("config", "db", "subscribers", "serve", "site_legal", "site_web", "legal", "asaas", "pricing"):
            sys.modules.pop(m, None)
        import db, subscribers, legal, serve
        db._INITED = False
        db.init()
        self.db, self.subscribers, self.legal, self.serve = db, subscribers, legal, serve
        self.stub = _AssinarStub()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _g(self, **over):
        base = {"plano": "anual", "nome": "Cliente Lancamento", "email": "lancamento@example.com",
                "cpf": "11144477735", "whatsapp": "43999991111", "metodo": "CARTAO",
                "parcelas": "1", "cupom": "LANCAMENTO", "aceito": "1"}
        base.update(over)
        return lambda k: base.get(k, "")

    def _mock_asaas(self):
        import asaas
        checkouts = []
        orig_criar = asaas.criar_checkout
        asaas.criar_checkout = lambda payload: checkouts.append(payload) or {
            "url": "https://checkout.asaas.example/lancamento", "id": "chk_lanc"}
        return asaas, checkouts, orig_criar

    def test_cupom_lancamento_nao_cria_assinante_gratis_cartao(self):
        """Propriedade crítica: LANCAMENTO no cartão NÃO pode passar pelo ramo de
        cortesia (`subscribers.criar_de_pagamento` -> assinante ATIVO sem pagar)."""
        asaas, checkouts, orig_criar = self._mock_asaas()
        criacoes = []
        orig_criar_de_pagamento = self.subscribers.criar_de_pagamento
        self.subscribers.criar_de_pagamento = lambda *a, **k: criacoes.append((a, k)) or {"id": "fake"}
        try:
            g = self._g()
            html = self.serve.Handler._post_assinar(self.stub, g)
        finally:
            asaas.criar_checkout = orig_criar
            self.subscribers.criar_de_pagamento = orig_criar_de_pagamento
        self.assertEqual(criacoes, [])   # caminho de cortesia (grátis) NUNCA foi tomado
        self.assertEqual(html, "<redirect https://checkout.asaas.example/lancamento>")
        self.assertEqual(len(checkouts), 1)

    def test_cupom_lancamento_cobra_997_no_cartao_pending_com_valor_base_1497(self):
        """Caminho pago: pending gravado com valor=997 (1497-500) e valor_base=1497
        (preço de tabela preservado p/ renovação)."""
        asaas, checkouts, orig_criar = self._mock_asaas()
        tokens = []
        orig_criar_pending = self.db.criar_pending

        def _espiao(dados):
            token = orig_criar_pending(dados)
            tokens.append(token)
            return token

        self.db.criar_pending = _espiao
        try:
            g = self._g()
            html = self.serve.Handler._post_assinar(self.stub, g)
        finally:
            asaas.criar_checkout = orig_criar
            self.db.criar_pending = orig_criar_pending
        self.assertEqual(html, "<redirect https://checkout.asaas.example/lancamento>")
        self.assertEqual(len(tokens), 1)
        pending = self.db.obter_pending(tokens[0])
        self.assertEqual(pending["valor"], 997.0)
        self.assertEqual(pending["valor_base"], 1497.0)
        self.assertEqual(len(checkouts), 1)

    def test_cupom_lancamento_pix_cobra_947_15(self):
        """Variante Pix: 1497 - 500 = 997, depois 5% off Pix -> 947.15."""
        asaas, checkouts, orig_criar = self._mock_asaas()
        tokens = []
        orig_criar_pending = self.db.criar_pending

        def _espiao(dados):
            token = orig_criar_pending(dados)
            tokens.append(token)
            return token

        self.db.criar_pending = _espiao
        try:
            g = self._g(metodo="PIX", whatsapp="43999992222", cpf="52998224725")
            html = self.serve.Handler._post_assinar(self.stub, g)
        finally:
            asaas.criar_checkout = orig_criar
            self.db.criar_pending = orig_criar_pending
        self.assertEqual(html, "<redirect https://checkout.asaas.example/lancamento>")
        self.assertEqual(len(tokens), 1)
        pending = self.db.obter_pending(tokens[0])
        self.assertEqual(pending["valor"], 947.15)
        self.assertEqual(pending["valor_base"], 1497.0)
