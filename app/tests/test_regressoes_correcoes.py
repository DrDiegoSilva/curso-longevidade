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


class TestC2bRecompraDeQuemCancelou(_Base):
    """Revisão #4: o C5 abriu o /renovar para quem cancelou no cartão e mudou de ideia
    dentro do período pago — direto para dentro de um buraco. O pagamento traz uma
    assinatura NOVA, então `por_subscription` não acha ninguém e cai no ATIVAR; o ramo de
    recompra repassava `existente["status"]` (ainda CANCELADO) e gravava `acesso_ate=None`
    porque há `sid`. Resultado: pagava e ficava SEM ACESSO no mesmo instante, em silêncio,
    sem alerta nenhum — e o RENOVAR seguinte batia em `cancelado_em` e não consertava."""

    def test_cancelado_dentro_do_periodo_que_paga_de_novo_volta_a_ter_acesso(self):
        sub = self._antigo(acesso_ate="2027-08-01", cancelado_em="2026-07-01T10:00:00")
        self.s.marcar_status(sub["id"], "CANCELADO", asaas_subscription_id="sub_velho")
        antes = self.s.por_id(sub["id"])
        self.assertTrue(self.s.tem_acesso(antes))          # cancelou mas ainda tem acesso

        body = {"event": "PAYMENT_CONFIRMED",
                "payment": {"id": "pay_novo", "externalReference": "", "customer": "cus_1",
                            "subscription": "sub_novo", "dueDate": "2026-07-19",
                            "value": 1099.0, "cpfCnpj": self.CPF}}
        st, msg = self.w.processar(body, "segredo", enviar_fn=self.envfn)
        self.assertEqual(st, 200)
        atual = self.s.por_id(sub["id"])
        self.assertEqual(atual["status"], "ATIVO")
        self.assertIsNone(atual["cancelado_em"])
        self.assertTrue(self.s.tem_acesso(atual))
        self.assertEqual(atual["asaas_subscription_id"], "sub_novo")


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
        # Guarda o ambiente ANTERIOR e restaura no tearDown: dar `pop` cegamente
        # apagava variáveis que outros módulos de teste (ordem alfabética) esperam
        # encontrar — foi assim que o test_preparar_pdf passou a cair em '/data'.
        self._env0 = {k: os.environ.get(k) for k in
                      ("DSCURSO_DATA", "DSCURSO_ARTIGOS_DB", "ASAAS_WEBHOOK_TOKEN")}
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
        for _k, _v in self._env0.items():
            if _v is None:
                os.environ.pop(_k, None)
            else:
                os.environ[_k] = _v

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
        # Guarda o ambiente ANTERIOR e restaura no tearDown: dar `pop` cegamente
        # apagava variáveis que outros módulos de teste (ordem alfabética) esperam
        # encontrar — foi assim que o test_preparar_pdf passou a cair em '/data'.
        self._env0 = {k: os.environ.get(k) for k in
                      ("DSCURSO_DATA", "DSCURSO_ARTIGOS_DB", "ASAAS_WEBHOOK_TOKEN")}
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "subscribers", "serve", "site_web"):
            sys.modules.pop(m, None)
        import db, subscribers, serve
        db._INITED = False
        db.init()
        self.serve = serve

    def tearDown(self):
        for _k, _v in self._env0.items():
            if _v is None:
                os.environ.pop(_k, None)
            else:
                os.environ[_k] = _v

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

    def test_quem_cancelou_com_sucesso_consegue_recontratar(self):
        """Cancelamento que deu certo no Asaas LIMPA o `asaas_subscription_id` — é assim que
        o /renovar sabe que não há recorrência viva. Sem sid, a porta abre."""
        sub = self._sub("2026-07-01T10:00:00")
        sub["asaas_subscription_id"] = None
        out = self.serve.Handler._get_rota_renovar(self._Stub(sub))
        self.assertIn('action="/renovar"', str(out))

    def test_quem_tem_recorrencia_ativa_continua_barrado(self):
        out = self.serve.Handler._get_rota_renovar(self._Stub(self._sub(None)))
        self.assertNotIn('action="/renovar"', str(out))

    def test_cancelamento_que_falhou_no_asaas_continua_barrado(self):
        """Se o cancelamento no Asaas FALHOU, o sid é preservado de propósito: a assinatura
        pode seguir cobrando, e deixar esse cliente montar um segundo checkout RECURRENT
        seria cobrança em dobro — exatamente o que o B4 existe para evitar."""
        out = self.serve.Handler._get_rota_renovar(self._Stub(self._sub("2026-07-01T10:00:00")))
        self.assertNotIn('action="/renovar"', str(out))


class TestC6TextoSeed0EmBancoExistente(unittest.TestCase):
    """O seed usa ON CONFLICT DO NOTHING com id fixo, então a correção do texto do dia do
    vencimento nunca alcançaria produção sem uma migração explícita."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # Guarda o ambiente ANTERIOR e restaura no tearDown: dar `pop` cegamente
        # apagava variáveis que outros módulos de teste (ordem alfabética) esperam
        # encontrar — foi assim que o test_preparar_pdf passou a cair em '/data'.
        self._env0 = {k: os.environ.get(k) for k in
                      ("DSCURSO_DATA", "DSCURSO_ARTIGOS_DB", "ASAAS_WEBHOOK_TOKEN")}
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db"):
            sys.modules.pop(m, None)
        import db
        db._INITED = False
        db.init()
        self.db = db

    def tearDown(self):
        for _k, _v in self._env0.items():
            if _v is None:
                os.environ.pop(_k, None)
            else:
                os.environ[_k] = _v

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


class TestC7CancelarNaoQuebra(unittest.TestCase):
    """A guarda do C4 foi escrita usando `subscribers` num método que não importa esse
    módulo — `_cancelar_motivo` só importa `site_web`. Como `serve` não tem `subscribers`
    no escopo do módulo, a linha levantava NameError em TODA tentativa de cancelamento, e
    `do_POST` não tem try/except: o cliente ficava sem página nenhuma. Nada na suíte
    exercitava o passo 1 do cancelamento — daí os 497 verdes."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._env0 = {k: os.environ.get(k) for k in
                      ("DSCURSO_DATA", "DSCURSO_ARTIGOS_DB", "ASAAS_WEBHOOK_TOKEN")}
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "subscribers", "serve", "site_web"):
            sys.modules.pop(m, None)
        import db, subscribers, serve
        db._INITED = False
        db.init()
        self.db, self.s, self.serve = db, subscribers, serve
        self.s._migrado = False

    def tearDown(self):
        for _k, _v in self._env0.items():
            if _v is None:
                os.environ.pop(_k, None)
            else:
                os.environ[_k] = _v

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
            self.cancelou = True
            return "<cancelado>"

    def _sub(self, acesso_ate):
        reg = self.s.criar_de_pagamento(
            {"nome": "A", "whatsapp": "5543999990000", "email": "a@x.com",
             "cpf": "11144477735", "plano": "anual"},
            {"customer": "c1", "payment": "p1", "proximo_vencimento": acesso_ate})
        self.s.marcar_status(reg["id"], "ATIVO", acesso_ate=acesso_ate)
        return self.s.por_id(reg["id"])

    def test_passo_1_do_cancelamento_roda_para_quem_tem_acesso(self):
        futuro = (datetime.now() + timedelta(days=30)).date().isoformat()
        stub = self._Stub(self._sub(futuro))
        out = self.serve.Handler._cancelar_motivo(stub, lambda k: {"motivo": "caro"}.get(k, ""))
        self.assertFalse(stub.cancelou)                 # mostrou a oferta
        self.assertIn("mês", str(out).lower())

    def test_passo_1_do_cancelamento_roda_para_quem_ja_venceu(self):
        stub = self._Stub(self._sub("2020-01-01"))
        self.serve.Handler._cancelar_motivo(stub, lambda k: {"motivo": "caro"}.get(k, ""))
        self.assertTrue(stub.cancelou)                  # sem acesso -> cancela direto


class TestC8PisoDaExtensao(TestC4OfertaSoParaQuemTemAcesso):
    """O `max(ref, agora)` não tinha teste (mutante sobrevivia). O caso real é o assinante
    INADIMPLENTE dentro da carência: `tem_acesso` é True, mas o `proximo_vencimento` já
    passou — sem o piso, o "+30 dias" contaria de uma data velha e entregaria menos que os
    30 dias prometidos na tela."""

    def test_inadimplente_na_carencia_ganha_30_dias_de_verdade(self):
        reg = self.s.criar_de_pagamento(
            {"nome": "A", "whatsapp": "5543999990000", "email": "a@x.com",
             "cpf": "11144477735", "plano": "anual"},
            {"customer": "c1", "payment": "p1", "proximo_vencimento": "2020-01-01"})
        carencia = (datetime.now() + timedelta(days=2)).isoformat()
        self.s.marcar_status(reg["id"], "INADIMPLENTE", carencia_ate=carencia,
                             proximo_vencimento="2020-01-01", acesso_ate=None)
        sub = self.s.por_id(reg["id"])
        self.assertTrue(self.s.tem_acesso(sub))
        self.serve.Handler._cancelar_confirmar(self._Stub(sub), self._g())
        novo = self.s.por_id(reg["id"])["acesso_ate"]
        self.assertGreater(novo, datetime.now().date().isoformat())


class TestC9MigracaoLigadaNoInit(TestC6TextoSeed0EmBancoExistente):
    """O mutante que removia a chamada de `_migrar_texto_seed0()` do `init()` sobrevivia:
    os testes chamavam a função direto. Uma migração que não está ligada no init é
    exatamente o defeito que o C6 existe para corrigir."""

    def test_init_aplica_a_migracao(self):
        a = next(x for x in self.db.listar_automacoes() if x["dias"] == 0)
        self.db.salvar_automacao(a["id"], 0, "whatsapp", self.db._TEXTO_SEED0_ANTIGO, 1)
        self.db._INITED = False
        self.db.init()
        atual = next(x for x in self.db.listar_automacoes() if x["dias"] == 0)
        self.assertNotIn("A partir de amanhã", atual["texto"])
