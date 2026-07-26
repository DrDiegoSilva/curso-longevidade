"""Testes do preço cobrado no /assinar quando quem compra é um ex-assinante voltando
(recontratação), vs. um cliente novo de verdade. Standalone.

Cenário: /assinar é a porta pública de quem já perdeu o acesso (webhook reconhece o
mesmo CPF/WhatsApp e reativa o registro). Antes desta correção, o preço vinha sempre de
`pricing.preco_vigente` (tabela do momento) — um founder que pagou 1099 e deixou vencer
pagaria o preço novo ao voltar, contrariando a promessa da cláusula 2 dos termos.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class _AssinarStub:
    """Stub mínimo pro `self` de `_post_assinar`: implementa só o que o método usa
    (`headers`, `client_address`, `_html`, `_redirect`). Mesmo padrão do `_AssinarStub`
    de test_aceite_checkout.py — duplicado aqui pra manter o arquivo standalone."""

    def __init__(self, ip="203.0.113.10"):
        self.headers = {}
        self.client_address = (ip, 54321)

    def _html(self, s, code=200):
        return s

    def _redirect(self, location, token=None, clear=False):
        return f"<redirect {location}>"


class TestPrecoRecontratacao(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        # NÃO inclui "renovacao": este arquivo não a importa nem precisa dela fresca
        # (é stateless), e popar/reimportar quebraria a checagem de identidade de
        # test_renovacao.py (webhook_asaas guarda uma referência ao módulo antigo) —
        # a ordem alfabética faz este arquivo rodar antes daquele.
        for m in ("config", "db", "subscribers", "serve", "site_legal", "site_web",
                  "legal", "pricing", "asaas"):
            sys.modules.pop(m, None)
        import db, subscribers, legal, serve, pricing, asaas
        db._INITED = False
        db.init()
        self.db, self.subs, self.legal, self.serve = db, subscribers, legal, serve
        self.pricing, self.asaas = pricing, asaas
        self.stub = _AssinarStub()

        # Preço de tabela fixo e propositalmente diferente do valor contratado (1099) —
        # assim, qualquer cenário de founder/pós-founder não interfere: o teste só
        # precisa distinguir "veio da tabela" (1497, o mock) de "veio do contratado".
        self._preco_vigente_orig = pricing.preco_vigente
        pricing.preco_vigente = lambda plano, n_ativos: 1497.0
        self._checkout_orig = asaas.criar_checkout
        asaas.criar_checkout = lambda payload: {"url": "https://checkout.asaas.example/x", "id": "chk_1"}

    def tearDown(self):
        self.pricing.preco_vigente = self._preco_vigente_orig
        self.asaas.criar_checkout = self._checkout_orig

    def _g(self, **over):
        # metodo=CARTAO 1x (não PIX): o plano anual tem pix_desconto_pct, que empilharia
        # mais uma conta em cima do valor — CARTAO 1x é `valor_cartao` = a própria base,
        # sem desconto nem gross-up, então o teste compara o número exato sem ruído.
        base = {"plano": "anual", "nome": "Cliente Teste", "email": "cliente@example.com",
                "cpf": "11144477735", "whatsapp": "43999990000", "metodo": "CARTAO",
                "parcelas": "1", "cupom": "", "aceito": "1"}
        base.update(over)
        return lambda k: base.get(k, "")

    def _post_espiando_pending(self, g):
        """Executa `_post_assinar` espionando o token gerado por `db.criar_pending`
        (deixa o `db.criar_pending` real rodar — precisamos do token de verdade pra
        depois reler o pending do banco). Mesmo padrão de test_aceite_checkout.py."""
        tokens = []
        orig_criar_pending = self.db.criar_pending

        def _espiao(dados):
            token = orig_criar_pending(dados)
            tokens.append(token)
            return token

        self.db.criar_pending = _espiao
        try:
            html = self.serve.Handler._post_assinar(self.stub, g)
        finally:
            self.db.criar_pending = orig_criar_pending
        self.assertEqual(len(tokens), 1)
        return html, self.db.obter_pending(tokens[0])

    def test_ex_assinante_sem_acesso_paga_o_valor_contratado_nao_o_de_tabela(self):
        reg = self.subs.criar_de_pagamento(
            {"nome": "Ex Assinante", "whatsapp": "43999990000", "email": "ex@e.com",
             "cpf": "11144477735", "plano": "anual", "valor_contratado": 1099.0},
            {"proximo_vencimento": "2025-07-01"})
        # CANCELADO com acesso_ate vencido = sem acesso vigente (ex-assinante de verdade)
        self.subs.marcar_status(reg["id"], "CANCELADO", cancelado_em="2025-07-01T00:00:00",
                                 acesso_ate="2025-07-01T00:00:00")
        self.assertFalse(self.subs.tem_acesso(self.subs.por_id(reg["id"])))

        html, pending = self._post_espiando_pending(self._g())

        self.assertEqual(html, "<redirect https://checkout.asaas.example/x>")
        self.assertEqual(pending["valor"], 1099.0)      # contratado, não os 1497 da tabela

    def test_cliente_novo_continua_pagando_o_preco_de_tabela(self):
        # Nenhum registro com esse CPF/WhatsApp -> `ja` é None -> segue o preço de tabela.
        html, pending = self._post_espiando_pending(
            self._g(cpf="12345678909", whatsapp="43988887777"))

        self.assertEqual(html, "<redirect https://checkout.asaas.example/x>")
        self.assertEqual(pending["valor"], 1497.0)      # preço de tabela (mock), sem mudança

    def test_assinante_com_acesso_ativo_continua_bloqueado(self):
        self.subs.criar_de_pagamento(
            {"nome": "Ativo", "whatsapp": "43999990000", "email": "ativo@e.com",
             "cpf": "11144477735", "plano": "anual", "valor_contratado": 1099.0},
            {"proximo_vencimento": "2027-08-01"})     # status ATIVO sem acesso_ate = sempre vigente
        html = self.serve.Handler._post_assinar(self.stub, self._g())
        self.assertIn("já existe uma assinatura ativa", html.lower())


if __name__ == "__main__":
    unittest.main()
