"""B9 da revisão final #2: os 7 dias de arrependimento para quem COMPRA DE NOVO.

`serve.py` mede a janela do art. 49 a partir de `subscribers.criado_em`, que só era
escrito em `criar_de_pagamento` — na primeira compra da vida do assinante. Nem a recompra
(comprou outro período antes de vencer) nem a recontratação (voltou depois de perder o
acesso) atualizavam o campo.

Cada uma dessas é um contrato à distância NOVO, com direito de arrependimento próprio.
Quem voltou e cancelava no 3º dia não recebia estorno nenhum e ninguém era avisado.

E na recontratação o `asaas_payment_id` também não era regravado: mesmo com a data
corrigida, o estorno miraria a cobrança da compra ANTERIOR.

`criado_em` tem exatamente um leitor (a janela de arrependimento) e não é exibido em
lugar nenhum — o docstring de `refunds.dentro_arrependimento` já define o campo como
"a data da contratação efetiva, que é o marco do art. 49". Atualizá-lo num contrato novo
é o significado documentado, não um desvio.
"""
import os
import sys
import importlib
import tempfile
import unittest
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestJanelaDeArrependimentoEmContratoNovo(unittest.TestCase):
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
        deliver.enviar_texto = lambda w, m: None      # confirmação de recompra vai por WhatsApp
        self.deliver = deliver

    def tearDown(self):
        self.deliver.enviar_texto = self._orig_wa
        for _k, _v in self._env0.items():
            if _v is None:
                os.environ.pop(_k, None)
            else:
                os.environ[_k] = _v

    def _body(self, pid, value=1044.05, installment=None, ext="tok_nao_existe"):
        pay = {"id": pid, "externalReference": ext, "customer": "cus_1",
               "subscription": None, "dueDate": "2026-07-19", "value": value,
               "cpfCnpj": self.CPF}
        if installment:
            pay["installment"] = installment
        return {"event": "PAYMENT_CONFIRMED", "payment": pay}

    def _assinante_antigo(self, acesso_ate):
        """Assinante cuja compra original foi há 60 dias — a janela dele já fechou."""
        reg = self.s.criar_de_pagamento(
            {"nome": "Dr. A", "whatsapp": self.WPP, "email": "a@x.com", "cpf": self.CPF,
             "plano": "anual", "valor_contratado": 1099.0},
            {"customer": "cus_1", "payment": "pay_velho", "installment": "inst_12x",
             "proximo_vencimento": acesso_ate})
        antigo = (datetime.now() - timedelta(days=60)).isoformat()
        self.s.marcar_status(reg["id"], "ATIVO", acesso_ate=acesso_ate, criado_em=antigo)
        sub = self.s.por_id(reg["id"])
        # pré-condição: a janela da compra ORIGINAL está fechada
        self.assertFalse(self.refunds.dentro_arrependimento(sub["criado_em"], date.today()))
        return sub

    def test_recompra_antes_de_vencer_abre_nova_janela_de_7_dias(self):
        sub = self._assinante_antigo("2027-07-19")
        st, msg = self.w.processar(self._body("pay_novo"), "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "pix-recomprado-estendido"))
        atual = self.s.por_id(sub["id"])
        self.assertTrue(self.refunds.dentro_arrependimento(atual["criado_em"], date.today()))
        self.assertEqual(atual["asaas_payment_id"], "pay_novo")

    def test_recontratacao_abre_nova_janela_e_mira_o_pagamento_novo(self):
        sub = self._assinante_antigo("2025-07-01")           # acesso já expirado
        tok = self.db.criar_pending({"nome": "Dr. A", "whatsapp": self.WPP,
                                     "email": "a@x.com", "cpf": self.CPF, "plano": "anual",
                                     "metodo": "PIX", "valor": 1044.05, "valor_base": 1099.0})
        st, msg = self.w.processar(self._body("pay_recontrat", ext=tok),
                                   "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "ativado"))
        atual = self.s.por_id(sub["id"])
        self.assertTrue(self.refunds.dentro_arrependimento(atual["criado_em"], date.today()))
        # sem isto, o estorno automático miraria "pay_velho" — a cobrança da compra anterior
        self.assertEqual(atual["asaas_payment_id"], "pay_recontrat")

    def test_parcela_nao_reabre_a_janela(self):
        """A parcela não é contrato novo: o contrato começou na parcela 1. Se cada parcela
        reabrisse a janela, o anual em 12x teria 12 direitos de estorno INTEGRAL ao longo
        do ano — um em cada mês."""
        sub = self._assinante_antigo("2027-07-19")
        st, msg = self.w.processar(self._body("pay_parc2", value=91.58, installment="inst_12x"),
                                   "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "parcela-registrada"))
        atual = self.s.por_id(sub["id"])
        self.assertFalse(self.refunds.dentro_arrependimento(atual["criado_em"], date.today()))
