"""Guardas do ramo ATIVAR do webhook — bloqueadores B5/B6/B7 da revisão final #2.

O ATIVAR é reentrante por natureza: o Asaas manda PAYMENT_CONFIRMED e PAYMENT_RECEIVED
para o MESMO pagamento, e no cartão parcelado cada parcela chega como um pagamento novo
sem `subscription` (então `por_subscription` não acha ninguém e cai aqui de novo).

B5 — os dois eventos do mesmo pagamento eram processados (a idempotência é por
     (payment_id, event)). No Pix, o 2º achava o assinante com acesso vigente e caía no
     ramo de RECOMPRA, estendendo um ciclo inteiro: um ano pago virava dois anos.
     Regressão introduzida pelo 83466dd deste próprio branch — antes dele o 2º evento
     era absorvido como "parcela-registrada", inofensivo.

B6 — a guarda de parcela existia SÓ dentro do ramo "ainda tem acesso". Uma parcela que
     chegasse depois do acesso vencer caía na RECONTRATAÇÃO: comprava um ciclo anual
     inteiro + o bônus de resgate por R$ 91,58.

B7 — e, no mesmo ramo, o `cancelado_em=None` incondicional (95b8495) ressuscitava quem
     tinha cancelado a renovação e apagava a marca do cancelamento — reabrindo em ATIVAR
     exatamente o buraco que o 4f670b4 fechou no RENOVAR (que exige `subscription`,
     coisa que cartão parcelado nunca tem).
"""
import os
import sys
import importlib
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestGuardasAtivar(unittest.TestCase):
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
        self.enviados = []
        self.envfn = lambda wpp, msg: self.enviados.append((wpp, msg))

    def tearDown(self):
        os.environ.pop("DSCURSO_DATA", None)
        os.environ.pop("DSCURSO_ARTIGOS_DB", None)

    CPF = "11144477735"
    WPP = "5543999990000"

    def _body(self, event="PAYMENT_CONFIRMED", pid="pay_1", value=1044.05,
              installment=None, ext="tok_nao_existe"):
        """cpfCnpj DIRETO no pagamento (como o Pix avulso do Asaas manda) — evita ter de
        mockar asaas.obter_cliente e ligar ASAAS_API_KEY só pra achar o assinante."""
        pay = {"id": pid, "externalReference": ext, "customer": "cus_1",
               "subscription": None, "dueDate": "2026-07-19", "value": value,
               "cpfCnpj": self.CPF}
        if installment:
            pay["installment"] = installment
        return {"event": event, "payment": pay}

    def _assinante(self, acesso_ate, valor_contratado=1099.0, cancelado_em=None,
                   plano="anual", pid="pay_velho", installment="inst_12x"):
        # `installment` = grupo de parcelamento do contrato em arquivo. Em produção o
        # assinante de cartão parcelado NASCE da parcela 1, que grava esse id — sem ele no
        # fixture, uma parcela do mesmo contrato pareceria contrato novo (C1 da revisão #3).
        reg = self.s.criar_de_pagamento(
            {"nome": "Dr. A", "whatsapp": self.WPP, "email": "a@x.com", "cpf": self.CPF,
             "plano": plano, "valor_contratado": valor_contratado},
            {"customer": "cus_1", "payment": pid, "installment": installment,
             "proximo_vencimento": acesso_ate})
        extra = {"cancelado_em": cancelado_em} if cancelado_em else {}
        self.s.marcar_status(reg["id"], "ATIVO", acesso_ate=acesso_ate, **extra)
        return self.s.por_id(reg["id"])

    # ── B5: o mesmo pagamento entregue duas vezes ──
    def test_confirmed_e_received_do_mesmo_pagamento_nao_estendem_duas_vezes(self):
        tok = self.db.criar_pending({"nome": "Dr. A", "whatsapp": self.WPP,
                                     "email": "a@x.com", "cpf": self.CPF, "plano": "anual",
                                     "metodo": "PIX", "valor": 1044.05, "valor_base": 1099.0})
        st, msg = self.w.processar(self._body(event="PAYMENT_CONFIRMED", pid="pay_1", ext=tok),
                                   "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "ativado"))
        depois_do_1 = self.s.por_cpf(self.CPF)["acesso_ate"]

        st2, msg2 = self.w.processar(self._body(event="PAYMENT_RECEIVED", pid="pay_1", ext=tok),
                                     "segredo", enviar_fn=self.envfn)
        self.assertEqual(st2, 200)
        self.assertEqual(self.s.por_cpf(self.CPF)["acesso_ate"], depois_do_1)

    def test_recompra_de_verdade_com_pagamento_novo_ainda_estende(self):
        """A guarda do B5 é por identidade do pagamento — não pode matar a recompra
        legítima (outro pagamento, antes de vencer), que o 83466dd existe pra atender."""
        sub = self._assinante("2027-07-19", pid="pay_1")
        st, msg = self.w.processar(self._body(pid="pay_2", value=1044.05),
                                   "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "pix-recomprado-estendido"))
        self.assertGreater(self.s.por_id(sub["id"])["acesso_ate"], "2027-07-19")

    # ── B6: parcela depois do acesso vencer ──
    def test_parcela_apos_o_acesso_vencer_nao_compra_ciclo_novo(self):
        sub = self._assinante("2025-07-01", valor_contratado=1099.0)
        st, msg = self.w.processar(self._body(pid="pay_parc2", value=91.58,
                                             installment="inst_12x"),
                                   "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "parcela-registrada"))
        atual = self.s.por_id(sub["id"])
        self.assertEqual(atual["acesso_ate"], "2025-07-01")          # não estendeu
        self.assertEqual(float(atual["valor_contratado"]), 1099.0)   # não virou 91.58
        self.assertEqual(atual["asaas_payment_id"], "pay_parc2")     # só a referência anda

    def test_parcela_com_acesso_vigente_continua_sendo_so_registrada(self):
        sub = self._assinante("2027-07-19")
        st, msg = self.w.processar(self._body(pid="pay_parc1", value=91.58,
                                             installment="inst_12x"),
                                   "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "parcela-registrada"))
        self.assertEqual(self.s.por_id(sub["id"])["acesso_ate"], "2027-07-19")

    # ── B7: parcela de quem cancelou a renovação ──
    def test_parcela_nao_ressuscita_quem_cancelou_nem_apaga_o_cancelamento(self):
        sub = self._assinante("2025-07-01", cancelado_em="2025-06-01T10:00:00")
        st, msg = self.w.processar(self._body(pid="pay_parc3", value=91.58,
                                             installment="inst_12x"),
                                   "segredo", enviar_fn=self.envfn)
        self.assertEqual(st, 200)
        atual = self.s.por_id(sub["id"])
        self.assertEqual(atual["cancelado_em"], "2025-06-01T10:00:00")  # marca preservada
        self.assertEqual(atual["acesso_ate"], "2025-07-01")             # sem período novo
        self.assertFalse(self.s.tem_acesso(atual))

    def test_recontratacao_de_verdade_por_pix_ainda_reativa(self):
        """A guarda do B6/B7 é sobre PARCELA. Quem perdeu o acesso e volta pagando um Pix
        avulso (sem `installment`) continua sendo recontratação legítima: reativa, limpa o
        cancelamento e ganha o bônus de resgate."""
        sub = self._assinante("2025-07-01", cancelado_em="2025-06-01T10:00:00")
        tok = self.db.criar_pending({"nome": "Dr. A", "whatsapp": self.WPP,
                                     "email": "a@x.com", "cpf": self.CPF, "plano": "anual",
                                     "metodo": "PIX", "valor": 1044.05, "valor_base": 1099.0})
        st, msg = self.w.processar(self._body(pid="pay_novo", value=1044.05, ext=tok),
                                   "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "ativado"))
        atual = self.s.por_id(sub["id"])
        self.assertIsNone(atual["cancelado_em"])
        self.assertTrue(self.s.tem_acesso(atual))
