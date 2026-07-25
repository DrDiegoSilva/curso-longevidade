"""Testes do estorno automático no cancelamento (7 dias). Sem rede. Standalone."""
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _sub(dias_atras, pid="pay_1", sid="sub_1"):
    return {"id": "s1", "nome": "Teste", "email": "t@e.com",
            "asaas_payment_id": pid, "asaas_subscription_id": sid,
            "criado_em": (datetime.now() - timedelta(days=dias_atras)).isoformat()}


class TestEstornoArrependimento(unittest.TestCase):
    def setUp(self):
        import serve, asaas, db
        self.serve, self.asaas, self.db = serve, asaas, db
        self.estornos = []
        self.comissoes = []
        self.alertas = []

        self._orig = (asaas.obter_pagamento, asaas.estornar_pagamento,
                      asaas.estornar_parcelamento, db.estornar_comissao)
        asaas.obter_pagamento = lambda pid: {"id": pid, "value": 997.0}
        asaas.estornar_pagamento = lambda pid, valor=None: self.estornos.append(("payment", pid))
        asaas.estornar_parcelamento = lambda iid, valor=None: self.estornos.append(("installment", iid))
        db.estornar_comissao = lambda sid: self.comissoes.append(sid) or 1

        import webhook_asaas
        self._orig_alerta = webhook_asaas._alertar_admin
        webhook_asaas._alertar_admin = lambda pid, sid, motivo: self.alertas.append(motivo)

    def tearDown(self):
        (self.asaas.obter_pagamento, self.asaas.estornar_pagamento,
         self.asaas.estornar_parcelamento, self.db.estornar_comissao) = self._orig
        import webhook_asaas
        webhook_asaas._alertar_admin = self._orig_alerta

    def test_cancelou_no_dia_3_estorna_integral(self):
        valor = self.serve.estornar_arrependimento(_sub(3))
        self.assertEqual(valor, 997.0)
        self.assertEqual(self.estornos, [("payment", "pay_1")])
        self.assertEqual(self.comissoes, ["s1"])

    def test_cancelou_no_dia_30_nao_estorna(self):
        self.assertIsNone(self.serve.estornar_arrependimento(_sub(30)))
        self.assertEqual(self.estornos, [])

    def test_parcelado_estorna_o_parcelamento_inteiro(self):
        self.asaas.obter_pagamento = lambda pid: {"id": pid, "value": 83.08, "installment": "ins_9"}
        self.serve.estornar_arrependimento(_sub(2))
        self.assertEqual(self.estornos, [("installment", "ins_9")])

    def test_cortesia_sem_pagamento_nao_estorna_nem_alerta(self):
        # cupom de cortesia entra sem asaas_payment_id — não é falha, é ausência de cobrança
        self.assertIsNone(self.serve.estornar_arrependimento(_sub(2, pid=None)))
        self.assertEqual(self.estornos, [])
        self.assertEqual(self.alertas, [])

    def test_falha_no_estorno_alerta_e_devolve_none(self):
        def explode(pid, valor=None):
            raise RuntimeError("saldo insuficiente")
        self.asaas.estornar_pagamento = explode
        self.assertIsNone(self.serve.estornar_arrependimento(_sub(2)))
        self.assertEqual(len(self.alertas), 1)
        self.assertIn("estorno", self.alertas[0].lower())

    def test_estorno_ok_mas_baixa_de_comissao_falha_devolve_valor_e_alerta_diferente(self):
        # ACHADO 1: o estorno no Asaas já saiu — a falha é só na baixa da comissão do
        # afiliado. A função tem que devolver o valor (não None) e o alerta precisa
        # deixar claro que o estorno DEU CERTO, não usar a mensagem de "estorno falhou".
        def explode(sid):
            raise RuntimeError("database is locked")
        self.db.estornar_comissao = explode
        valor = self.serve.estornar_arrependimento(_sub(3))
        self.assertEqual(valor, 997.0)
        self.assertEqual(self.estornos, [("payment", "pay_1")])
        self.assertEqual(len(self.alertas), 1)
        msg = self.alertas[0].lower()
        self.assertIn("comiss", msg)
        self.assertNotIn("estorne manualmente no painel do asaas", msg)

    def test_valor_nao_numerico_falha_antes_de_mover_dinheiro(self):
        # ACHADO 3: "value" não-numérico tem que estourar DENTRO do try, antes de
        # chamar o Asaas — nunca depois do dinheiro já ter saído. Se a exceção
        # subisse depois do estorno, o chamador nunca rodaria registrar_cancelamento
        # (cliente reembolsado e ainda ATIVO).
        self.asaas.obter_pagamento = lambda pid: {"id": pid, "value": "NaN-inválido"}
        self.assertIsNone(self.serve.estornar_arrependimento(_sub(3)))
        self.assertEqual(self.estornos, [])          # dinheiro NUNCA saiu
        self.assertEqual(len(self.alertas), 1)
        self.assertIn("estorno", self.alertas[0].lower())


class _HandlerStub:
    """Stub mínimo pro `self` de _executar_cancelamento: o método só usa
    `self._html` (não abre socket nenhum — não é uma requisição HTTP real)."""

    def _html(self, s, code=200):
        return s


class TestExecutarCancelamento(unittest.TestCase):
    """Cobre a bifurcação de acesso_ate/e-mail em _executar_cancelamento e o claim
    que guarda o fluxo inteiro (ACHADO 1 e ACHADO 4 da 2ª rodada) — não existia
    nenhum teste direto deste método antes, o que deixou passar o Critical: o
    perdedor da corrida regravando acesso_ate com data futura por cima do None do
    vencedor.

    Chama o método com um `self` stub — ele só usa `self._html` internamente."""

    def setUp(self):
        import serve, subscribers, asaas, email_send, site_web, db
        self.serve, self.subscribers, self.asaas = serve, subscribers, asaas
        self.email_send, self.site_web, self.db = email_send, site_web, db

        self.registros = []       # chamadas a subscribers.registrar_cancelamento
        self.emails = []          # chamadas a email_send.enviar
        self.paginas = []         # chamadas a site_web.pagina_cancelado

        self._orig = (subscribers.registrar_cancelamento, subscribers.por_id,
                      asaas.cancelar_assinatura, email_send.enviar,
                      site_web.pagina_cancelado, db.claim_cancelamento,
                      serve.estornar_arrependimento)

        subscribers.registrar_cancelamento = (
            lambda sid, motivo, acesso_ate=None: self.registros.append(
                {"id": sid, "motivo": motivo, "acesso_ate": acesso_ate}))
        subscribers.por_id = lambda sid: None      # sobrescrito nos testes que precisam
        asaas.cancelar_assinatura = lambda sid: None
        email_send.enviar = lambda to, assunto, html: self.emails.append(
            {"to": to, "assunto": assunto, "html": html})
        site_web.pagina_cancelado = lambda acesso_ate="": self.paginas.append(
            acesso_ate) or f"<pagina acesso_ate={acesso_ate!r}>"
        db.claim_cancelamento = lambda sid: True    # por padrão sempre vence o claim
        serve.estornar_arrependimento = lambda sub: None   # por padrão sem estorno

        self.stub = _HandlerStub()

    def tearDown(self):
        (self.subscribers.registrar_cancelamento, self.subscribers.por_id,
         self.asaas.cancelar_assinatura, self.email_send.enviar,
         self.site_web.pagina_cancelado, self.db.claim_cancelamento,
         self.serve.estornar_arrependimento) = self._orig

    def _sub(self, **over):
        base = {"id": "s1", "nome": "Teste", "email": "t@e.com",
                "asaas_subscription_id": "sub_1", "proximo_vencimento": "2026-12-31"}
        base.update(over)
        return base

    def _chamar(self, sub, motivo):
        # _executar_cancelamento é um método de instância de Handler; chamamos a
        # função "crua" da classe passando o stub como self (não dá pra
        # instanciar Handler de verdade sem uma conexão HTTP real).
        return self.serve.Handler._executar_cancelamento(self.stub, sub, motivo)

    def test_dentro_dos_7_dias_zera_acesso_e_email_de_reembolso(self):
        self.serve.estornar_arrependimento = lambda sub: 997.0
        self._chamar(self._sub(), "mudei de ideia")
        self.assertEqual(self.registros, [{"id": "s1", "motivo": "mudei de ideia", "acesso_ate": None}])
        self.assertEqual(len(self.emails), 1)
        self.assertIn("reembolso", self.emails[0]["html"].lower())

    def test_fora_dos_7_dias_mantem_proximo_vencimento_sem_reembolso_no_email(self):
        self.serve.estornar_arrependimento = lambda sub: None
        self._chamar(self._sub(), "não uso mais")
        self.assertEqual(self.registros, [{"id": "s1", "motivo": "não uso mais", "acesso_ate": "2026-12-31"}])
        self.assertEqual(len(self.emails), 1)
        self.assertNotIn("reembolso", self.emails[0]["html"].lower())

    def test_segunda_chamada_apos_estorno_nao_regrava_acesso_futuro(self):
        # ACHADO 1 (Critical): a 1ª chamada já cancelou COM estorno e gravou
        # acesso_ate=None no banco. A 2ª chamada (duplo clique/retry) perde o
        # claim — não pode recalcular e regravar a data futura de
        # proximo_vencimento por cima disso. É este teste que teria pego o bug.
        self.db.claim_cancelamento = lambda sid: False
        self.subscribers.por_id = lambda sid: self._sub(acesso_ate=None)
        self._chamar(self._sub(), "mudei de ideia")
        self.assertEqual(self.registros, [])            # não regravou nada
        self.assertEqual(self.emails, [])                # não mandou 2º e-mail
        self.assertEqual(self.paginas, [None])            # página usou o acesso_ate persistido (None)

    def test_falha_no_claim_por_excecao_trata_como_vencido_e_segue_o_fluxo(self):
        # ACHADO 2: falha de infra no claim (banco travado/timeout) NUNCA pode
        # travar o cancelamento — trata como se tivesse vencido e processa normal.
        def explode(sid):
            raise RuntimeError("database is locked")
        self.db.claim_cancelamento = explode
        self._chamar(self._sub(), "mudei de ideia")
        self.assertEqual(len(self.registros), 1)


if __name__ == "__main__":
    unittest.main()
