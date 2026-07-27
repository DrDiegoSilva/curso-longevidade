"""Regressões introduzidas pelas próprias correções da revisão #2 (achadas na revisão #3).

C1 — `28715d1` içou a guarda de parcela para valer em QUALQUER assinante existente. Mas ela
     não distingue uma parcela ATRASADA do contrato antigo da PARCELA 1 DE UM CONTRATO NOVO.
     Um ex-assinante que volta e compra o anual em 12x pagava R$ 1.099 e recebia ZERO acesso,
     sem boas-vindas e sem alerta — e as 11 parcelas seguintes faziam o mesmo. É exatamente a
     coorte que as mensagens de resgate do Projeto F trazem de volta.
     Correção: guardar o id do GRUPO de parcelamento (`asaas_installment_id`) e só tratar como
     parcela quando ela pertence ao contrato que já está em arquivo.

C2 — a recontratação nunca atualizava o `plano` do assinante, e o `4208285` passou a gravar a
     base do plano NOVO nesse registro do plano VELHO. Ex-mensal que volta comprando o anual
     ficava "mensal" com valor_contratado 1099 -> renovação cobrava R$ 1.099 POR MÊS, e o
     acesso vinha com o ciclo do mensal (30 dias) por um ano pago.
     Correção: gravar o plano nos dois ramos e preferir o plano do PENDING (o que o cliente
     acabou de escolher) ao do cadastro antigo.

C3 — `8077679` alargou o casamento por CPF/pagamento, e `PAYMENT_DELETED` mora no mesmo grupo
     de REFUNDED/CHARGEBACK. Mas "cobrança apagada" não é "dinheiro devolvido": apagar no
     painel do Asaas uma cobrança de renovação NÃO PAGA cancelava um assinante com um ano
     pago. O mesmo caminho negava a promessa central do Projeto E (cancelar a renovação mantém
     o acesso até o fim do período), porque cancelar a assinatura apaga as cobranças futuras.
     Correção: DELETED só corta acesso quando a cobrança apagada é a que o assinante PAGOU.
"""
import os
import sys
import importlib
import tempfile
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class _Base(unittest.TestCase):
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
        import deliver
        self._orig_wa = deliver.enviar_texto
        deliver.enviar_texto = lambda w, m: None
        self.deliver = deliver

    def tearDown(self):
        self.deliver.enviar_texto = self._orig_wa
        os.environ.pop("DSCURSO_DATA", None)
        os.environ.pop("DSCURSO_ARTIGOS_DB", None)

    def _antigo(self, plano="anual", acesso_ate="2025-07-01", pid="pay_velho", **extra):
        reg = self.s.criar_de_pagamento(
            {"nome": "Dr. A", "whatsapp": self.WPP, "email": "a@x.com", "cpf": self.CPF,
             "plano": plano, "valor_contratado": 99.0 if plano == "mensal" else 1099.0},
            {"customer": "cus_1", "payment": pid, "proximo_vencimento": acesso_ate})
        self.s.marcar_status(reg["id"], "ATIVO", acesso_ate=acesso_ate, **extra)
        return self.s.por_id(reg["id"])

    def _pending(self, plano, metodo, valor, valor_base, parcelas=1):
        return self.db.criar_pending({"nome": "Dr. A", "whatsapp": self.WPP, "email": "a@x.com",
                                      "cpf": self.CPF, "plano": plano, "metodo": metodo,
                                      "parcelas": parcelas, "valor": valor,
                                      "valor_base": valor_base})

    def _body(self, tok, pid, value, installment=None):
        pay = {"id": pid, "externalReference": tok, "customer": "cus_1", "subscription": None,
               "dueDate": "2026-07-19", "value": value, "cpfCnpj": self.CPF}
        if installment:
            pay["installment"] = installment
        return {"event": "PAYMENT_CONFIRMED", "payment": pay}


class TestC1ContratoNovoEmParcelas(_Base):
    def test_ex_assinante_que_volta_no_anual_12x_recebe_acesso(self):
        sub = self._antigo()
        tok = self._pending("anual", "CARTAO", 1099.0, 1099.0, parcelas=12)
        st, msg = self.w.processar(self._body(tok, "pay_novo_1", 91.58,
                                              installment="inst_CONTRATO_NOVO"),
                                   "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "ativado"))
        atual = self.s.por_id(sub["id"])
        self.assertTrue(self.s.tem_acesso(atual))
        self.assertEqual(float(atual["valor_contratado"]), 1099.0)

    def test_parcelas_seguintes_do_mesmo_contrato_nao_compram_periodo_novo(self):
        """A guarda do B6 continua valendo — mas só para o contrato que está em arquivo."""
        sub = self._antigo()
        tok = self._pending("anual", "CARTAO", 1099.0, 1099.0, parcelas=12)
        self.w.processar(self._body(tok, "pay_novo_1", 91.58, installment="inst_X"),
                        "segredo", enviar_fn=self.envfn)
        fim = self.s.por_id(sub["id"])["acesso_ate"]

        st, msg = self.w.processar(self._body(tok, "pay_novo_2", 91.58, installment="inst_X"),
                                   "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "parcela-registrada"))
        self.assertEqual(self.s.por_id(sub["id"])["acesso_ate"], fim)

    def test_parcela_atrasada_do_contrato_antigo_nao_ressuscita_cancelado(self):
        """B7 preservado: a parcela do contrato JÁ EM ARQUIVO não limpa o cancelamento."""
        sub = self._antigo(cancelado_em="2025-06-01T10:00:00")
        self.s.marcar_status(sub["id"], "ATIVO", asaas_installment_id="inst_ANTIGO")
        st, msg = self.w.processar(self._body("tok_nao_existe", "pay_p9", 91.58,
                                              installment="inst_ANTIGO"),
                                   "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "parcela-registrada"))
        atual = self.s.por_id(sub["id"])
        self.assertEqual(atual["cancelado_em"], "2025-06-01T10:00:00")
        self.assertFalse(self.s.tem_acesso(atual))


class TestC2PlanoNaRecontratacao(_Base):
    def test_ex_mensal_que_compra_o_anual_fica_no_anual(self):
        sub = self._antigo(plano="mensal")
        tok = self._pending("anual", "PIX", 1044.05, 1099.0)
        st, msg = self.w.processar(self._body(tok, "pay_n", 1044.05),
                                   "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "ativado"))
        atual = self.s.por_id(sub["id"])
        self.assertEqual(atual["plano"], "anual")
        # 1 ano (365) + bônus de resgate, não o ciclo do mensal
        self.assertGreater(atual["acesso_ate"], "2027-01-01")

    def test_preco_de_renovacao_bate_com_o_plano_gravado(self):
        """O estrago do C2 era a combinação: plano velho + base do plano novo = R$ 1.099/mês."""
        import renovacao
        sub = self._antigo(plano="mensal")
        tok = self._pending("anual", "PIX", 1044.05, 1099.0)
        self.w.processar(self._body(tok, "pay_n", 1044.05), "segredo", enviar_fn=self.envfn)
        atual = self.s.por_id(sub["id"])
        plano = self.cfg.plano_por_slug(atual["plano"])
        self.assertEqual(plano["cycle"], "YEARLY")
        self.assertEqual(renovacao.preco_renovacao(atual, plano), 1099.0)   # por ANO


class TestC3CobrancaApagada(_Base):
    def _deleted(self, pid):
        return {"event": "PAYMENT_DELETED",
                "payment": {"id": pid, "customer": "cus_1", "subscription": None,
                            "dueDate": "2027-07-19", "value": 1044.05, "cpfCnpj": self.CPF}}

    def test_apagar_cobranca_nao_paga_nao_corta_acesso(self):
        sub = self._antigo(acesso_ate="2027-07-19", pid="pay_pago")
        st, msg = self.w.processar(self._deleted("pay_abandonado"), "segredo", enviar_fn=self.envfn)
        self.assertEqual(st, 200)
        atual = self.s.por_id(sub["id"])
        self.assertEqual(atual["status"], "ATIVO")
        self.assertEqual(atual["acesso_ate"], "2027-07-19")
        self.assertTrue(self.s.tem_acesso(atual))

    def test_apagar_a_cobranca_que_foi_paga_corta_acesso(self):
        sub = self._antigo(acesso_ate="2027-07-19", pid="pay_pago")
        st, msg = self.w.processar(self._deleted("pay_pago"), "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "suspenso"))
        self.assertFalse(self.s.tem_acesso(self.s.por_id(sub["id"])))

    def test_estorno_continua_cortando_mesmo_de_pagamento_antigo(self):
        """REFUNDED/CHARGEBACK são dinheiro DE VOLTA — cortam independente de qual cobrança."""
        sub = self._antigo(acesso_ate="2027-07-19", pid="pay_pago")
        body = {"event": "PAYMENT_REFUNDED",
                "payment": {"id": "pay_parcela_1", "customer": "cus_1", "subscription": None,
                            "dueDate": "2027-07-19", "value": 91.58, "cpfCnpj": self.CPF}}
        st, msg = self.w.processar(body, "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "suspenso"))
        self.assertFalse(self.s.tem_acesso(self.s.por_id(sub["id"])))


class TestC4OfertaSoParaQuemTemAcesso(unittest.TestCase):
    """Revisão #3, achados do 2º revisor sobre a correção do B11.

    Tornar `acesso_ate` gravável transformou um caminho ANTES INÓCUO em reativação de graça:
    quem teve o acesso cortado por estorno/chargeback (SUSPENDER grava CANCELADO sem
    `cancelado_em`, e a sessão continua válida por 30 dias) era convidado a "ganhar +30 dias"
    e recebia 30 dias REAIS. E quem só venceu recebia a promessa de +30 dias calculada de uma
    data já passada — zero acesso — queimando de vez a única oferta a que tinha direito.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "subscribers", "serve", "site_web"):
            sys.modules.pop(m, None)
        import db, config, subscribers, serve, asaas
        db._INITED = False
        db.init()
        self.db, self.s, self.serve, self.asaas = db, subscribers, serve, asaas
        self.s._migrado = False
        self._orig = asaas.adiar_vencimento
        asaas.adiar_vencimento = lambda sid, dias: {"ok": True}

    def tearDown(self):
        self.asaas.adiar_vencimento = self._orig
        os.environ.pop("DSCURSO_ARTIGOS_DB", None)

    class _Stub:
        def __init__(self, sub):
            self._sub = sub
            self.cancelou = False

        def _sub_logado(self):
            return self._sub

        def _html(self, s, code=200):
            return s

        def _redirect(self, location, token=None, clear=False):
            return f"<redirect {location}>"

        def _executar_cancelamento(self, sub, motivo):
            # o que interessa aqui é que a OFERTA não foi concedida; o cancelamento em si
            # tem cobertura própria em test_cancelamento_estorno.py
            self.cancelou = True
            return "<cancelado>"

    def _g(self, **over):
        base = {"acao": "aceitar", "motivo": "caro"}
        base.update(over)
        return lambda k: base.get(k, "")

    def _sub(self, status, acesso_ate, cancelado_em=None):
        reg = self.s.criar_de_pagamento(
            {"nome": "A", "whatsapp": "5543999990000", "email": "a@x.com",
             "cpf": "11144477735", "plano": "anual"},
            {"customer": "c1", "payment": "p1", "proximo_vencimento": "2027-08-01"})
        extra = {"cancelado_em": cancelado_em} if cancelado_em else {}
        self.s.marcar_status(reg["id"], status, acesso_ate=acesso_ate, **extra)
        return self.s.por_id(reg["id"])

    def test_quem_teve_estorno_nao_ganha_30_dias_de_volta(self):
        # exatamente o que o SUSPENDER do webhook grava
        sub = self._sub("CANCELADO", datetime.now().isoformat())
        self.assertFalse(self.s.tem_acesso(sub))
        self.serve.Handler._cancelar_confirmar(self._Stub(sub), self._g())
        self.assertFalse(self.s.tem_acesso(self.s.por_id(sub["id"])))

    def test_quem_ja_venceu_nao_queima_a_oferta_a_troco_de_nada(self):
        sub = self._sub("ATIVO", "2026-06-01")          # venceu antes de hoje
        self.assertFalse(self.s.tem_acesso(sub))
        self.serve.Handler._cancelar_confirmar(self._Stub(sub), self._g())
        atual = self.s.por_id(sub["id"])
        self.assertFalse(self.s.tem_acesso(atual))
        self.assertFalse(atual.get("oferta_retencao_em"))   # oferta preservada

    def test_quem_tem_acesso_continua_ganhando_os_30_dias(self):
        futuro = (datetime.now() + timedelta(days=10)).date().isoformat()
        sub = self._sub("ATIVO", futuro)
        self.serve.Handler._cancelar_confirmar(self._Stub(sub), self._g())
        atual = self.s.por_id(sub["id"])
        self.assertTrue(self.s.tem_acesso(atual))
        self.assertGreater(atual["acesso_ate"], futuro)
        self.assertTrue(atual.get("oferta_retencao_em"))


class TestC5RenovarDeQuemCancelou(unittest.TestCase):
    """O guard do /renovar olhava só `asaas_subscription_id`, que NUNCA é limpo. Quem
    cancelou a renovação no cartão e mudou de ideia dentro do período pago ouvia "sua
    assinatura já renova automaticamente" — falso, foi cancelada no Asaas — e o /assinar
    recusa quem ainda tem acesso. Ficava sem porta nenhuma."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "subscribers", "serve", "site_web"):
            sys.modules.pop(m, None)
        import db, subscribers, serve
        db._INITED = False
        db.init()
        self.serve = serve

    def tearDown(self):
        os.environ.pop("DSCURSO_ARTIGOS_DB", None)

    class _Stub:
        def __init__(self, sub):
            self._sub = sub

        def _sub_logado(self):
            return self._sub

        def _html(self, s, code=200):
            return s

        def _redirect(self, location, token=None, clear=False):
            return f"<redirect {location}>"

    def _sub(self, cancelado_em=None):
        return {"id": "s1", "nome": "A", "email": "a@x.com", "cpf": "11144477735",
                "whatsapp": "5543999990000", "plano": "anual", "status": "ATIVO",
                "valor_contratado": 1099.0, "proximo_vencimento": "2027-08-01",
                "acesso_ate": "2027-08-01", "asaas_subscription_id": "sub_1",
                "cancelado_em": cancelado_em}

    def test_quem_cancelou_no_cartao_consegue_recontratar(self):
        out = self.serve.Handler._get_rota_renovar(self._Stub(self._sub("2026-07-01T10:00:00")))
        self.assertIn('action="/renovar"', str(out))

    def test_quem_tem_recorrencia_ativa_continua_barrado(self):
        out = self.serve.Handler._get_rota_renovar(self._Stub(self._sub(None)))
        self.assertNotIn('action="/renovar"', str(out))


class TestC6TextoSeed0EmBancoExistente(unittest.TestCase):
    """O seed usa ON CONFLICT DO NOTHING com id fixo, então a correção do texto do dia do
    vencimento nunca alcançaria produção sem uma migração explícita."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db"):
            sys.modules.pop(m, None)
        import db
        db._INITED = False
        db.init()
        self.db = db

    def tearDown(self):
        os.environ.pop("DSCURSO_ARTIGOS_DB", None)

    def test_texto_antigo_e_corrigido_no_banco_existente(self):
        a = next(x for x in self.db.listar_automacoes() if x["dias"] == 0)
        self.db.salvar_automacao(a["id"], 0, "whatsapp", self.db._TEXTO_SEED0_ANTIGO, 1)
        self.db._migrar_texto_seed0()
        atual = next(x for x in self.db.listar_automacoes() if x["dias"] == 0)
        self.assertNotIn("A partir de amanhã", atual["texto"])

    def test_edicao_do_admin_e_preservada(self):
        a = next(x for x in self.db.listar_automacoes() if x["dias"] == 0)
        self.db.salvar_automacao(a["id"], 0, "whatsapp", "Texto que o Diego escreveu", 1)
        self.db._migrar_texto_seed0()
        atual = next(x for x in self.db.listar_automacoes() if x["dias"] == 0)
        self.assertEqual(atual["texto"], "Texto que o Diego escreveu")
