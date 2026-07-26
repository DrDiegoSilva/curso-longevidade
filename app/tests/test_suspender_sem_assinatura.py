"""B10 da revisão final #2: estorno e chargeback em Pix e cartão parcelado.

`_executar` resolvia o assinante SÓ por `subscribers.por_subscription(sid)`, e os ramos
SUSPENDER/INADIMPLENTE eram guardados por `and sub`. Pix (DETACHED) e cartão parcelado
nunca trazem `subscription` — então:

  - um estorno feito no painel do Asaas deixava o acesso ATIVO;
  - a comissão do afiliado continuava a pagar, por uma venda que deixou de existir;
  - o evento caía no `(200, "ignorado")` genérico, indistinguível de um PAYMENT_CREATED
    que a gente ignora de propósito — ninguém era avisado.

Agora o assinante é procurado pelo `asaas_payment_id` do próprio pagamento e, se
necessário, pelo CPF; e quando NADA casa, o admin é alertado em vez de o evento sumir.
"""
import os
import sys
import importlib
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestSuspenderSemSubscription(unittest.TestCase):
    CPF = "11144477735"
    WPP = "5543999990000"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["ASAAS_WEBHOOK_TOKEN"] = "segredo"
        for m in ("config", "db", "subscribers", "webhook_asaas"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, subscribers, webhook_asaas
        for mod in (config, db, subscribers, webhook_asaas):
            importlib.reload(mod)
        self.cfg, self.db, self.s, self.w = config, db, subscribers, webhook_asaas
        self.s._migrado = False
        db.init()
        self.envfn = lambda wpp, msg: None
        self.alertas = []
        self._orig_alertar = webhook_asaas._alertar_admin
        webhook_asaas._alertar_admin = lambda pid, sid, msg: self.alertas.append(msg)

    def tearDown(self):
        self.w._alertar_admin = self._orig_alertar
        os.environ.pop("DSCURSO_DATA", None)
        os.environ.pop("DSCURSO_ARTIGOS_DB", None)

    def _assinante_pix(self, pid="pay_pix_1"):
        """Assinante de Pix: SEM asaas_subscription_id, como o Asaas de fato entrega."""
        reg = self.s.criar_de_pagamento(
            {"nome": "Dr. A", "whatsapp": self.WPP, "email": "a@x.com", "cpf": self.CPF,
             "plano": "anual", "valor_contratado": 1099.0},
            {"customer": "cus_1", "subscription": None, "payment": pid,
             "proximo_vencimento": "2027-07-19"})
        self.s.marcar_status(reg["id"], "ATIVO", acesso_ate="2027-07-19")
        return self.s.por_id(reg["id"])

    def _body(self, event, pid, cpf=""):
        return {"event": event,
                "payment": {"id": pid, "customer": "cus_1", "subscription": None,
                            "dueDate": "2026-07-19", "value": 1044.05, "cpfCnpj": cpf}}

    def test_estorno_de_pix_corta_o_acesso(self):
        sub = self._assinante_pix()
        st, msg = self.w.processar(self._body("PAYMENT_REFUNDED", "pay_pix_1"),
                                   "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "suspenso"))
        atual = self.s.por_id(sub["id"])
        self.assertEqual(atual["status"], "CANCELADO")
        self.assertFalse(self.s.tem_acesso(atual))

    def test_chargeback_de_pix_corta_o_acesso(self):
        sub = self._assinante_pix()
        st, msg = self.w.processar(self._body("PAYMENT_CHARGEBACK_REQUESTED", "pay_pix_1"),
                                   "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "suspenso"))
        self.assertFalse(self.s.tem_acesso(self.s.por_id(sub["id"])))

    def test_estorno_acha_pelo_cpf_quando_o_pagamento_e_outro(self):
        """Estorno de uma parcela antiga: o `asaas_payment_id` em arquivo já é o da parcela
        mais recente, então o casamento por pagamento não serve — sobra o CPF."""
        sub = self._assinante_pix(pid="pay_parcela_5")
        st, msg = self.w.processar(self._body("PAYMENT_REFUNDED", "pay_parcela_1", cpf=self.CPF),
                                   "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "suspenso"))
        self.assertFalse(self.s.tem_acesso(self.s.por_id(sub["id"])))

    def test_estorno_baixa_a_comissao_do_afiliado(self):
        self.db.criar_afiliado("Parceiro", "p@x.com", "PARC10")
        af = self.db.afiliado_por_codigo("PARC10")
        sub = self._assinante_pix()
        self.db.registrar_comissao(af["id"], sub["id"], "anual", 1044.05, 31.32)
        self.assertEqual(len(self.db.listar_comissoes(af["id"], pago=False)), 1)

        self.w.processar(self._body("PAYMENT_REFUNDED", "pay_pix_1"), "segredo",
                        enviar_fn=self.envfn)
        # venda devolvida -> comissão não é mais devida, sai da fila de pagamento
        self.assertEqual(len(self.db.listar_comissoes(af["id"], pago=False)), 0)

    def test_estorno_sem_assinante_nenhum_alerta_em_vez_de_sumir(self):
        st, msg = self.w.processar(self._body("PAYMENT_REFUNDED", "pay_fantasma"),
                                   "segredo", enviar_fn=self.envfn)
        self.assertEqual(st, 200)
        self.assertNotEqual(msg, "ignorado")     # não se confunde com um evento ignorado
        self.assertEqual(len(self.alertas), 1)

    def test_payment_created_continua_ignorado_em_silencio(self):
        """A rede de segurança acima não pode transformar todo evento sem assinante em
        alerta — PAYMENT_CREATED é ignorado de propósito e não é problema de ninguém."""
        st, msg = self.w.processar(self._body("PAYMENT_CREATED", "pay_qualquer"),
                                   "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "ignorado"))
        self.assertEqual(self.alertas, [])

    def test_overdue_de_pix_nao_encurta_o_acesso_ja_pago(self):
        """O fallback vale só para SUSPENDER. Em INADIMPLENTE o `tem_acesso` passa a olhar
        só o `carencia_ate` (3 dias) e IGNORA o `acesso_ate` — marcar um assinante de Pix
        assim por causa de uma cobrança de renovação não paga truncaria para 3 dias um
        acesso que ele já pagou até 2027. Pix vencido é assunto da régua."""
        sub = self._assinante_pix()
        st, msg = self.w.processar(self._body("PAYMENT_OVERDUE", "pay_pix_1"),
                                   "segredo", enviar_fn=self.envfn)
        self.assertEqual(st, 200)
        atual = self.s.por_id(sub["id"])
        self.assertEqual(atual["status"], "ATIVO")
        self.assertEqual(atual["acesso_ate"], "2027-07-19")
        self.assertTrue(self.s.tem_acesso(atual))
