"""Jornadas de cartão PARCELADO conduzidas ponta a ponta pelo `processar`.

A revisão #4 mostrou que a suíte inteira criava assinante de parcelado por fixture
(`criar_de_pagamento` com `installment` na mão) — caminho que a produção NÃO usa. O webhook
cria o assinante na PARCELA 1, e ali o `installment` não estava sendo gravado: a parcela 2
então não casava com o contrato em arquivo e caía na recompra, dando UM ANO EXTRA de acesso
e reabrindo a janela de arrependimento ~30 dias depois da compra.

Estes testes usam só `processar`, sem fixture de assinante — é o formato que pega esse buraco.
"""
import os
import sys
import importlib
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestJornadaParcelado(unittest.TestCase):
    CPF = "11144477735"
    WPP = "5543999990000"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # Guarda o ambiente ANTERIOR e restaura no tearDown: dar `pop` cegamente
        # apagava variáveis que outros módulos de teste (ordem alfabética) esperam
        # encontrar — foi assim que o test_preparar_pdf passou a cair em '/data'.
        self._env0 = {k: os.environ.get(k) for k in
                      ("DSCURSO_DATA", "DSCURSO_ARTIGOS_DB", "ASAAS_WEBHOOK_TOKEN")}
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["ASAAS_WEBHOOK_TOKEN"] = "segredo"
        for m in ("config", "db", "subscribers", "webhook_asaas", "refunds"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, subscribers, webhook_asaas, refunds
        for mod in (config, db, subscribers, webhook_asaas, refunds):
            importlib.reload(mod)
        self.cfg, self.db, self.s, self.w, self.refunds = config, db, subscribers, webhook_asaas, refunds
        self.s._migrado = False
        db.init()
        self.envfn = lambda wpp, msg: None
        import deliver
        self._orig_wa = deliver.enviar_texto
        deliver.enviar_texto = lambda w, m: None
        self.deliver = deliver

    def tearDown(self):
        self.deliver.enviar_texto = self._orig_wa
        for _k, _v in self._env0.items():
            if _v is None:
                os.environ.pop(_k, None)
            else:
                os.environ[_k] = _v

    def _parcela(self, tok, pid, n_grupo="inst_12x", value=91.58):
        return {"event": "PAYMENT_CONFIRMED",
                "payment": {"id": pid, "externalReference": tok, "customer": "cus_1",
                            "subscription": None, "dueDate": "2026-07-19", "value": value,
                            "installment": n_grupo, "cpfCnpj": self.CPF}}

    def _tok(self):
        return self.db.criar_pending({"nome": "Dr. A", "whatsapp": self.WPP, "email": "a@x.com",
                                      "cpf": self.CPF, "plano": "anual", "metodo": "CARTAO",
                                      "parcelas": 12, "valor": 1099.0, "valor_base": 1099.0})

    def test_cliente_novo_no_12x_recebe_um_ano_nao_dois(self):
        tok = self._tok()
        st, msg = self.w.processar(self._parcela(tok, "pay_p1"), "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "ativado"))
        sub = self.s.por_cpf(self.CPF)
        fim_apos_p1 = sub["acesso_ate"]
        criado_apos_p1 = sub["criado_em"]

        st2, msg2 = self.w.processar(self._parcela(tok, "pay_p2"), "segredo", enviar_fn=self.envfn)
        self.assertEqual((st2, msg2), (200, "parcela-registrada"))
        atual = self.s.por_cpf(self.CPF)
        self.assertEqual(atual["acesso_ate"], fim_apos_p1)      # NÃO ganhou outro ano
        self.assertEqual(atual["criado_em"], criado_apos_p1)    # janela de 7 dias NÃO reabriu

    def test_parcela_3_tambem_so_registra(self):
        tok = self._tok()
        self.w.processar(self._parcela(tok, "pay_p1"), "segredo", enviar_fn=self.envfn)
        fim = self.s.por_cpf(self.CPF)["acesso_ate"]
        self.w.processar(self._parcela(tok, "pay_p2"), "segredo", enviar_fn=self.envfn)
        st, msg = self.w.processar(self._parcela(tok, "pay_p3"), "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "parcela-registrada"))
        self.assertEqual(self.s.por_cpf(self.CPF)["acesso_ate"], fim)

    def test_grupo_de_parcelamento_e_gravado_na_criacao(self):
        tok = self._tok()
        self.w.processar(self._parcela(tok, "pay_p1"), "segredo", enviar_fn=self.envfn)
        self.assertEqual(self.s.por_cpf(self.CPF)["asaas_installment_id"], "inst_12x")

    def test_parcela_de_quem_cancelou_nao_da_ano_extra(self):
        """Contrato criado pelo webhook (não por fixture) e depois cancelado: as parcelas
        seguintes continuam sendo cobradas, mas não podem comprar período novo."""
        tok = self._tok()
        self.w.processar(self._parcela(tok, "pay_p1"), "segredo", enviar_fn=self.envfn)
        sub = self.s.por_cpf(self.CPF)
        self.db.claim_cancelamento(sub["id"], "achei caro", sub["acesso_ate"])
        fim = self.s.por_id(sub["id"])["acesso_ate"]

        st, msg = self.w.processar(self._parcela(tok, "pay_p2"), "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "parcela-registrada"))
        atual = self.s.por_id(sub["id"])
        self.assertEqual(atual["acesso_ate"], fim)
        self.assertTrue(atual["cancelado_em"])          # cancelamento preservado


class TestPendingVelhoNaoRoubaOPlano(TestJornadaParcelado):
    """`obter_pending_por_cpf` devolve o pending MAIS RECENTE do CPF e pendings nunca são
    consumidos. Com o pending à frente do cadastro na cascata, um checkout abandonado do
    plano `teste` (R$5, alcançável por /assinar?plano=teste) fazia um pagamento de
    R$ 1.044,05 virar 30 dias com renovação de R$ 5."""

    def test_pending_abandonado_de_outro_valor_e_ignorado(self):
        import renovacao
        # assinante anual que já venceu
        reg = self.s.criar_de_pagamento(
            {"nome": "Dr. A", "whatsapp": self.WPP, "email": "a@x.com", "cpf": self.CPF,
             "plano": "anual", "valor_contratado": 1099.0},
            {"customer": "cus_1", "payment": "pay_velho", "proximo_vencimento": "2025-07-01"})
        self.s.marcar_status(reg["id"], "ATIVO", acesso_ate="2025-07-01")
        # ele espiou o plano de teste em algum momento e abandonou
        self.db.criar_pending({"nome": "Dr. A", "whatsapp": self.WPP, "email": "a@x.com",
                               "cpf": self.CPF, "plano": "teste", "metodo": "PIX",
                               "parcelas": 1, "valor": 5.0, "valor_base": 5.0})
        # agora paga o ANUAL de verdade (sem externalReference, como o Asaas entrega)
        body = {"event": "PAYMENT_CONFIRMED",
                "payment": {"id": "pay_anual", "externalReference": "", "customer": "cus_1",
                            "subscription": None, "dueDate": "2026-07-19", "value": 1044.05,
                            "cpfCnpj": self.CPF}}
        st, msg = self.w.processar(body, "segredo", enviar_fn=self.envfn)
        self.assertEqual(st, 200)
        atual = self.s.por_id(reg["id"])
        self.assertEqual(atual["plano"], "anual")
        self.assertNotEqual(float(atual["valor_contratado"] or 0), 5.0)
        self.assertGreater(atual["acesso_ate"], "2027-01-01")   # um ano, não 30 dias

    def test_pending_que_bate_com_o_pagamento_ainda_manda(self):
        """A correção não pode matar o C2: o pending do checkout que o cliente ACABOU de
        fazer (valor casando com a cobrança) continua definindo o plano."""
        reg = self.s.criar_de_pagamento(
            {"nome": "Dr. A", "whatsapp": self.WPP, "email": "a@x.com", "cpf": self.CPF,
             "plano": "mensal", "valor_contratado": 99.0},
            {"customer": "cus_1", "payment": "pay_velho", "proximo_vencimento": "2025-07-01"})
        self.s.marcar_status(reg["id"], "ATIVO", acesso_ate="2025-07-01")
        self.db.criar_pending({"nome": "Dr. A", "whatsapp": self.WPP, "email": "a@x.com",
                               "cpf": self.CPF, "plano": "anual", "metodo": "PIX",
                               "parcelas": 1, "valor": 1044.05, "valor_base": 1099.0})
        body = {"event": "PAYMENT_CONFIRMED",
                "payment": {"id": "pay_anual", "externalReference": "", "customer": "cus_1",
                            "subscription": None, "dueDate": "2026-07-19", "value": 1044.05,
                            "cpfCnpj": self.CPF}}
        self.w.processar(body, "segredo", enviar_fn=self.envfn)
        atual = self.s.por_id(reg["id"])
        self.assertEqual(atual["plano"], "anual")
        self.assertEqual(float(atual["valor_contratado"]), 1099.0)
