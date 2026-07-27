"""O que `valor_contratado` significa — e o que a renovação cobra por causa dele.

ACHADOS DA REVISÃO FINAL #2 (3 bloqueadores de dinheiro, todos neste campo):

B1 — no cartão PARCELADO, `payment.value` é UMA parcela (o próprio refunds.py documenta:
     "estornar só o payment da parcela 1 devolveria 1/12"). Gravar isso em
     `valor_contratado` fazia o anual em 12x renovar por R$ 91,58 em vez de R$ 1.099 —
     justamente a coorte que a régua do Projeto F existe para atender.

B2 — `valor_contratado` guardava o valor PAGO (pós-desconto de 5% do Pix), e a renovação
     reaplica o desconto sobre ele (`pricing.base_cobrada`). O preço derretia a cada
     ciclo: 1099 -> 1044,05 -> 991,85 -> 942,26 -> ...

B3 — `preco_renovacao` ignorava o `plano`. As mensagens de resgate mandam para o
     `/assinar` público, onde o cliente ESCOLHE o plano — então um ex-mensal (99) levava
     o ANUAL por R$ 94,05, e o plano `teste` (R$ 5, oculto mas alcançável por
     /assinar?plano=teste) virava trava de preço vitalícia.

DECISÃO: `valor_contratado` guarda a BASE CONTRATADA do plano (pré-desconto de método,
pré-cupom de afiliado). Assim `base_cobrada` aplica o desconto do método UMA vez, a cada
renovação, sobre um número estável — e o campo nunca vem de `payment.value`.
"""
import os
import sys
import importlib
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPrecoRenovacaoPorPlano(unittest.TestCase):
    """B3: a base contratada vale só para o plano em que foi contratada."""

    def setUp(self):
        import config, renovacao
        self.config, self.renovacao = config, renovacao
        self.anual = config.plano_por_slug("anual")
        self.mensal = config.plano_por_slug("mensal")

    def test_honra_o_contratado_quando_o_plano_e_o_mesmo(self):
        sub = {"plano": "anual", "valor_contratado": 997.0}
        self.assertEqual(self.renovacao.preco_renovacao(sub, self.anual), 997.0)

    def test_ignora_o_contratado_quando_o_cliente_escolhe_outro_plano(self):
        # Ex-mensal (99) escolhendo ANUAL no /assinar: tem que pagar o anual, não 99.
        sub = {"plano": "mensal", "valor_contratado": 99.0}
        self.assertEqual(self.renovacao.preco_renovacao(sub, self.anual),
                         float(self.anual["base"]))

    def test_plano_teste_nao_vira_trava_de_preco_no_anual(self):
        # /assinar?plano=teste custa R$5 e é publicamente alcançável (oculto != bloqueado).
        # Deixar lapsar e voltar no ANUAL não pode cobrar R$ 5.
        sub = {"plano": "teste", "valor_contratado": 5.0}
        self.assertEqual(self.renovacao.preco_renovacao(sub, self.anual),
                         float(self.anual["base"]))

    def test_sem_plano_no_cadastro_cai_na_tabela(self):
        sub = {"plano": "", "valor_contratado": 997.0}
        self.assertEqual(self.renovacao.preco_renovacao(sub, self.anual),
                         float(self.anual["base"]))

    def test_pix_renovado_duas_vezes_cobra_o_mesmo_valor(self):
        """B2: com a BASE guardada, o desconto do Pix é aplicado uma vez por ciclo.
        Guardando o valor pago, cada ciclo descontava de novo (erosão composta)."""
        import pricing
        base = float(self.anual["base"])
        sub = {"plano": "anual", "valor_contratado": base}
        c1 = pricing.base_cobrada(self.anual, "PIX", self.renovacao.preco_renovacao(sub, self.anual), 0.0)
        # o assinante renovou: `valor_contratado` continua sendo a BASE, não o que ele pagou
        c2 = pricing.base_cobrada(self.anual, "PIX", self.renovacao.preco_renovacao(sub, self.anual), 0.0)
        self.assertEqual(c1, c2)
        self.assertLess(c1, base)                    # o desconto existe
        self.assertEqual(c1, pricing.valor_com_desconto(base, self.anual["pix_desconto_pct"]))


class TestWebhookGravaBaseContratada(unittest.TestCase):
    """B1/B2 no ponto onde o campo é escrito: o webhook."""

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

    def tearDown(self):
        for _k, _v in self._env0.items():
            if _v is None:
                os.environ.pop(_k, None)
            else:
                os.environ[_k] = _v

    def _pending(self, metodo, valor_pago, valor_base, parcelas=1):
        return self.db.criar_pending({"nome": "Dr. A", "whatsapp": "5543999990000",
                                      "email": "a@x.com", "cpf": "11144477735",
                                      "plano": "anual", "metodo": metodo,
                                      "parcelas": parcelas, "valor": valor_pago,
                                      "valor_base": valor_base})

    def _body(self, tok, value, pid="pay_1", installment=None):
        pay = {"id": pid, "externalReference": tok, "customer": "cus_1",
               "subscription": None, "dueDate": "2026-07-19", "value": value}
        if installment:
            pay["installment"] = installment
        return {"event": "PAYMENT_CONFIRMED", "payment": pay}

    def test_parcela_do_anual_grava_a_base_e_nao_a_parcela(self):
        # Anual R$1.099 em 12x -> o Asaas confirma a parcela 1 com value=91.58.
        tok = self._pending("CARTAO", 1099.0, 1099.0, parcelas=12)
        st, msg = self.w.processar(self._body(tok, 91.58, installment="inst_12x"),
                                   "segredo", enviar_fn=self.envfn)
        self.assertEqual(st, 200)
        sub = self.s.por_whatsapp("5543999990000")
        self.assertEqual(float(sub["valor_contratado"]), 1099.0)

    def test_pix_grava_a_base_e_nao_o_valor_com_desconto(self):
        # Pix anual: paga 1044,05 (5% off) mas contratou a base 1099.
        tok = self._pending("PIX", 1044.05, 1099.0)
        st, _ = self.w.processar(self._body(tok, 1044.05), "segredo", enviar_fn=self.envfn)
        self.assertEqual(st, 200)
        sub = self.s.por_whatsapp("5543999990000")
        self.assertEqual(float(sub["valor_contratado"]), 1099.0)

    def test_comissao_do_afiliado_e_sobre_a_venda_nao_sobre_a_parcela(self):
        """Mesma família do B1: a comissão saía de `pay["value"]`, que no anual em 12x é
        UMA parcela — o afiliado recebia 3% de R$ 91,58 em vez de 3% da venda inteira.
        A comissão é só na 1ª venda, então o erro nunca se corrigia nas parcelas seguintes."""
        self.db.criar_afiliado("Parceiro", "parceiro@x.com", "PARC10")
        af = self.db.afiliado_por_codigo("PARC10")
        tok = self.db.criar_pending({"nome": "Dr. A", "whatsapp": "5543999990000",
                                     "email": "a@x.com", "cpf": "11144477735",
                                     "plano": "anual", "metodo": "CARTAO", "parcelas": 12,
                                     "valor": 989.10, "valor_base": 1099.0,
                                     "afiliado_codigo": "PARC10"})
        st, _ = self.w.processar(self._body(tok, 82.43, installment="inst_12x"),
                                 "segredo", enviar_fn=self.envfn)
        self.assertEqual(st, 200)
        comis = self.db.listar_comissoes(af["id"])
        self.assertEqual(len(comis), 1)
        self.assertEqual(float(comis[0]["valor_venda"]), 989.10)
        esperado = self.db and round(989.10 * float(af["pct_comissao"]) / 100.0, 2)
        self.assertEqual(float(comis[0]["valor_comissao"]), esperado)

    def test_pending_antigo_sem_valor_base_nao_inventa_valor_a_partir_do_pago(self):
        """Pendings criados antes desta coluna existir não têm `valor_base`. Melhor
        deixar o campo vazio (a renovação cai no preço de tabela) do que gravar o valor
        pago, que reintroduz B1 (parcela) e B2 (desconto composto)."""
        tok = self.db.criar_pending({"nome": "Dr. A", "whatsapp": "5543999990000",
                                     "email": "a@x.com", "cpf": "11144477735",
                                     "plano": "anual", "metodo": "CARTAO",
                                     "parcelas": 12, "valor": 1099.0})   # sem valor_base
        st, _ = self.w.processar(self._body(tok, 91.58, installment="inst_12x"),
                                 "segredo", enviar_fn=self.envfn)
        self.assertEqual(st, 200)
        sub = self.s.por_whatsapp("5543999990000")
        self.assertFalse(sub.get("valor_contratado"))
