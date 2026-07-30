"""Testes do aceite no checkout: obrigatório no POST e propagado na ativação. Standalone."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAceiteNoCheckout(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "subscribers"):
            sys.modules.pop(m, None)
        import db, legal
        db._INITED = False
        db.init()
        self.db, self.legal = db, legal

    def test_pagina_assinar_tem_checkbox_obrigatorio(self):
        import site_web
        html = site_web.pagina_assinar("anual")
        self.assertIn('name="aceito"', html)
        self.assertIn('href="/termos"', html)
        self.assertIn('href="/privacidade"', html)

    def test_pending_guarda_a_versao_aceita(self):
        token = self.db.criar_pending({"nome": "T", "email": "t@e.com", "cpf": "1", "whatsapp": "43999990000",
                                       "plano": "anual", "metodo": "PIX", "parcelas": 1, "valor": 997.0,
                                       "termos_versao": self.legal.VERSAO, "termos_ip": "203.0.113.7"})
        p = self.db.obter_pending(token)
        self.assertEqual(p["termos_versao"], self.legal.VERSAO)
        self.assertEqual(p["termos_ip"], "203.0.113.7")

    def test_ativacao_copia_o_aceite_pro_assinante(self):
        import subscribers
        reg = subscribers.criar_de_pagamento(
            {"nome": "T", "whatsapp": "43999990000", "email": "t@e.com", "plano": "anual",
             "termos_versao": self.legal.VERSAO, "termos_ip": "203.0.113.7"}, {})
        atual = [s for s in subscribers.listar() if s["id"] == reg["id"]][0]
        self.assertEqual(atual["termos_versao"], self.legal.VERSAO)
        self.assertFalse(subscribers.precisa_aceitar(atual))


class _AssinarStub:
    """Stub mínimo pro `self` de `_post_assinar`: implementa só o que o método usa
    (`headers`, `client_address`, `_html`, `_redirect`) — não abre socket, não é uma
    requisição HTTP real. Mesmo padrão do `_HandlerStub`/`_RotaStub` das suítes de
    cancelamento (test_cancelamento_estorno.py) e reaceite (test_reaceite.py)."""

    def __init__(self, ip="203.0.113.9"):
        self.headers = {}
        self.client_address = (ip, 54321)

    def _html(self, s, code=200):
        return s

    def _redirect(self, location, token=None, clear=False):
        return f"<redirect {location}>"

    def _ip_cliente(self):
        # `_post_assinar` agora resolve o IP via `Handler._ip_cliente` (fix pós-revisão
        # do Task 1: X-Forwarded-For lido do lado errado) — este stub não herda de
        # `Handler`, então só encaminha pra implementação real em vez de duplicá-la.
        import serve
        return serve.Handler._ip_cliente(self)


class TestGateDeAceiteNoPostAssinar(unittest.TestCase):
    """ACHADO (revisão da Task 7): os testes acima chamam `pagina_assinar`,
    `db.criar_pending` e `subscribers.criar_de_pagamento` isolados, com dicts montados
    à mão — nenhum exercita `serve.Handler._post_assinar` de verdade. Se o
    `if g("aceito") != "1": ...` (~876) sumir, ou se `termos_versao`/`termos_ip`
    saírem de um dos dois dicts que chegam lá (cortesia ~899-900, Asaas ~924-925), a
    suíte inteira acima continua verde — o bug que a Task 7 existe pra evitar volta em
    silêncio. Estes testes chamam o método de rota de verdade, com um stub mínimo como
    `self` (mesmo padrão do `_HandlerStub`/`_RotaStub`)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "subscribers", "serve", "site_legal", "site_web", "legal"):
            sys.modules.pop(m, None)
        import db, subscribers, legal, serve
        db._INITED = False
        db.init()
        self.db, self.subscribers, self.legal, self.serve = db, subscribers, legal, serve
        self.stub = _AssinarStub()

    def _g(self, **over):
        """Monta o `g` como o do POST real (`form.get(k, [""])[0]`): dict com campos
        válidos de um checkout, sobrescrevíveis por teste."""
        base = {"plano": "mensal", "nome": "Cliente Teste", "email": "cliente@example.com",
                "cpf": "11144477735", "whatsapp": "43999990000", "metodo": "PIX",
                "parcelas": "1", "cupom": "", "aceito": "1"}
        base.update(over)
        return lambda k: base.get(k, "")

    # 1) Sem aceite -> nenhum efeito colateral, em NENHUM dos dois caminhos.

    def test_sem_aceite_nao_cria_pending_nem_chama_asaas(self):
        import asaas
        pendings, checkouts = [], []
        orig_criar_pending, orig_criar_checkout = self.db.criar_pending, asaas.criar_checkout
        self.db.criar_pending = lambda dados: pendings.append(dados) or "TOKEN-FAKE"
        asaas.criar_checkout = lambda payload: checkouts.append(payload) or {"url": "https://x/y", "id": "1"}
        try:
            for aceito_invalido in ("", "0"):        # ausente (default do g) e explicitamente "0"
                with self.subTest(aceito=aceito_invalido):
                    g = self._g(aceito=aceito_invalido)
                    html = self.serve.Handler._post_assinar(self.stub, g)
                    self.assertIn("aceitar os Termos", html)   # página devolvida traz o erro
        finally:
            self.db.criar_pending, asaas.criar_checkout = orig_criar_pending, orig_criar_checkout
        self.assertEqual(pendings, [])       # nenhum pending criado, nas duas chamadas
        self.assertEqual(checkouts, [])      # Asaas nunca foi acionado

    def test_sem_aceite_nao_consome_cupom_nem_cria_assinante(self):
        self.db.criar_cupom(descricao="cortesia teste", uso_unico=True, codigo="CORTESIA-GATE")
        criacoes = []
        orig_criar = self.subscribers.criar_de_pagamento
        self.subscribers.criar_de_pagamento = lambda *a, **k: criacoes.append((a, k)) or {"id": "fake"}
        try:
            g = self._g(cupom="CORTESIA-GATE", aceito="0")
            html = self.serve.Handler._post_assinar(self.stub, g)
        finally:
            self.subscribers.criar_de_pagamento = orig_criar
        self.assertEqual(criacoes, [])                          # nenhum assinante criado
        cupom = self.db.obter_cupom("CORTESIA-GATE")
        self.assertEqual(cupom["usos"], 0)                       # cupom intacto (não consumido)
        self.assertTrue(cupom["ativo"])
        self.assertIn("aceitar os Termos", html)

    # 2) Cupom de cortesia COM aceite -> o assinante criado carrega o aceite.

    def test_cupom_com_aceite_grava_termos_versao_no_assinante(self):
        import deliver
        orig_enviar = deliver.enviar_texto
        deliver.enviar_texto = lambda whatsapp, msg: None   # nunca bater na rede de WhatsApp
        self.db.criar_cupom(descricao="cortesia teste", uso_unico=True, codigo="CORTESIA-OK")
        try:
            g = self._g(cupom="CORTESIA-OK", aceito="1")
            html = self.serve.Handler._post_assinar(self.stub, g)
        finally:
            deliver.enviar_texto = orig_enviar
        self.assertEqual(html, "<redirect /obrigado>")
        novo = self.subscribers.por_whatsapp("43999990000")
        self.assertIsNotNone(novo)
        self.assertEqual(novo["termos_versao"], self.legal.VERSAO)
        self.assertFalse(self.subscribers.precisa_aceitar(novo))

    # 3) Caminho Asaas COM aceite -> o pending criado carrega termos_versao e termos_ip.

    def test_asaas_com_aceite_grava_termos_no_pending(self):
        import asaas
        orig_criar_checkout = asaas.criar_checkout
        asaas.criar_checkout = lambda payload: {"url": "https://checkout.asaas.example/x", "id": "chk_1"}
        tokens = []
        orig_criar_pending = self.db.criar_pending

        def _criar_pending_espiao(dados):
            # deixa o db.criar_pending real rodar (precisamos do token de verdade pra
            # depois ler o pending do banco) e só espiona o token gerado.
            token = orig_criar_pending(dados)
            tokens.append(token)
            return token

        self.db.criar_pending = _criar_pending_espiao
        try:
            g = self._g(aceito="1")
            html = self.serve.Handler._post_assinar(self.stub, g)
        finally:
            asaas.criar_checkout = orig_criar_checkout
            self.db.criar_pending = orig_criar_pending
        self.assertEqual(html, "<redirect https://checkout.asaas.example/x>")
        self.assertEqual(len(tokens), 1)
        pending = self.db.obter_pending(tokens[0])
        self.assertEqual(pending["termos_versao"], self.legal.VERSAO)
        self.assertEqual(pending["termos_ip"], "203.0.113.9")


if __name__ == "__main__":
    unittest.main()
