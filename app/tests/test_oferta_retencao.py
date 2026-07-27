"""B11 e B8 da revisão final #2: a oferta de retenção ("+30 dias" para não cancelar).

B11 — o ramo de aceite gravava só `proximo_vencimento`, nunca `acesso_ate`. O commit
      dbb6dde ("Pix expira no fim do período pago") fez de `acesso_ate` o campo que de
      fato controla o acesso de quem NÃO tem `asaas_subscription_id` — ou seja, Pix e
      cartão parcelado. Resultado: a tela dizia "Você ganhou +30 dias", o cliente
      recebia ZERO e perdia o acesso na data original — tendo desistido do cancelamento
      e deixado a janela de 7 dias de arrependimento correr nesse meio-tempo.
      Para cartão à vista (com assinatura recorrente) `acesso_ate` é NULL de propósito e
      quem controla o acesso é o ciclo do Asaas — lá o certo é não gravar a data.

B8 —  a checagem de `oferta_retencao_em` existia só em `_cancelar_motivo`, que decide
      EXIBIR a oferta. Um POST repetido de `acao=aceitar` empurrava +30 dias a CADA
      chamada, sem limite.
"""
import os
import sys
import importlib
import tempfile
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class _CancelarStub:
    """Stub mínimo pro `self` de `_cancelar_confirmar` — mesmo padrão do _RenovarStub
    (test_renovar_rota.py) e do _AssinarStub (test_aceite_checkout.py)."""

    def __init__(self, sub):
        self._sub = sub

    def _sub_logado(self):
        return self._sub

    def _html(self, s, code=200):
        return s

    def _redirect(self, location, token=None, clear=False):
        return f"<redirect {location}>"


class TestOfertaRetencao(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # Guarda o ambiente ANTERIOR e restaura no tearDown: dar `pop` cegamente
        # apagava variáveis que outros módulos de teste (ordem alfabética) esperam
        # encontrar — foi assim que o test_preparar_pdf passou a cair em '/data'.
        self._env0 = {k: os.environ.get(k) for k in
                      ("DSCURSO_DATA", "DSCURSO_ARTIGOS_DB", "ASAAS_WEBHOOK_TOKEN")}
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        # NÃO despejar `renovacao` daqui: `webhook_asaas._CICLO_DIAS` é o MESMO objeto que
        # `renovacao.CICLO_DIAS` (test_renovacao.TestCicloDias trava isso com assertIs), e
        # recarregar um sem o outro quebra essa identidade para os testes seguintes.
        for m in ("config", "db", "subscribers", "serve", "site_web"):
            sys.modules.pop(m, None)
        import db, config, subscribers, serve, asaas
        db._INITED = False
        db.init()
        self.db, self.config, self.s, self.serve, self.asaas = db, config, subscribers, serve, asaas
        self.s._migrado = False
        self._orig_adiar = asaas.adiar_vencimento
        asaas.adiar_vencimento = lambda sid, dias: {"ok": True}

    def tearDown(self):
        self.asaas.adiar_vencimento = self._orig_adiar
        for _k, _v in self._env0.items():
            if _v is None:
                os.environ.pop(_k, None)
            else:
                os.environ[_k] = _v

    def _g(self, **over):
        base = {"acao": "aceitar", "motivo": "caro"}
        base.update(over)
        return lambda k: base.get(k, "")

    def _assinante(self, sid=None, acesso_ate="2026-08-01", oferta_em=None):
        reg = self.s.criar_de_pagamento(
            {"nome": "Dr. A", "whatsapp": "5543999990000", "email": "a@x.com",
             "cpf": "11144477735", "plano": "anual"},
            {"customer": "cus_1", "subscription": sid, "payment": "pay_1",
             "proximo_vencimento": acesso_ate})
        extra = {"oferta_retencao_em": oferta_em} if oferta_em else {}
        self.s.marcar_status(reg["id"], "ATIVO", acesso_ate=acesso_ate, **extra)
        return self.s.por_id(reg["id"])

    def _aceitar(self, sub):
        stub = _CancelarStub(sub)
        return self.serve.Handler._cancelar_confirmar(stub, self._g())

    # ── B11 ──
    def test_pix_ganha_os_30_dias_no_campo_que_controla_o_acesso(self):
        sub = self._assinante(sid=None, acesso_ate="2026-08-01")
        self._aceitar(sub)
        atual = self.s.por_id(sub["id"])
        self.assertEqual(atual["acesso_ate"], "2026-08-31")
        self.assertEqual(atual["proximo_vencimento"], "2026-08-31")

    def test_cartao_recorrente_nao_ganha_acesso_ate_gravado(self):
        """Com assinatura recorrente quem controla o acesso é o ciclo do Asaas —
        `acesso_ate` preenchido no passado cortaria o acesso de quem está pagando."""
        sub = self._assinante(sid="sub_asaas_1", acesso_ate=None)
        self._aceitar(sub)
        atual = self.s.por_id(sub["id"])
        self.assertIsNone(atual["acesso_ate"])
        self.assertEqual(atual["proximo_vencimento"], self._mais_30(None))

    def _mais_30(self, base):
        ref = datetime.fromisoformat(base) if base else datetime.now()
        return (ref + timedelta(days=30)).date().isoformat()

    def test_pix_estende_a_partir_do_acesso_ate_nao_do_proximo_vencimento(self):
        """Os dois campos podem divergir (o `proximo_vencimento` fica para trás quando o
        acesso é estendido por bônus/cortesia). Quem governa o acesso do Pix é o
        `acesso_ate` — extender do outro entregaria menos de 30 dias reais de presente."""
        sub = self._assinante(sid=None, acesso_ate="2026-08-01")
        self.s.marcar_status(sub["id"], "ATIVO", proximo_vencimento="2026-07-01")
        self._aceitar(self.s.por_id(sub["id"]))
        atual = self.s.por_id(sub["id"])
        self.assertEqual(atual["acesso_ate"], "2026-08-31")     # 2026-08-01 + 30
        self.assertNotEqual(atual["acesso_ate"], "2026-07-31")  # não veio de 2026-07-01

    def test_pix_sem_acesso_ate_usa_o_proximo_vencimento_como_base(self):
        sub = self._assinante(sid=None, acesso_ate=None)
        self.s.marcar_status(sub["id"], "ATIVO", proximo_vencimento="2026-09-10")
        self._aceitar(self.s.por_id(sub["id"]))
        self.assertEqual(self.s.por_id(sub["id"])["acesso_ate"], "2026-10-10")

    # ── B8 ──
    def test_aceitar_duas_vezes_nao_empilha_mais_30_dias(self):
        sub = self._assinante(sid=None, acesso_ate="2026-08-01")
        self._aceitar(sub)
        depois_do_1 = self.s.por_id(sub["id"])["acesso_ate"]
        self.assertEqual(depois_do_1, "2026-08-31")

        # 2ª chamada: o assinante já tem oferta_retencao_em preenchido
        self._aceitar(self.s.por_id(sub["id"]))
        self.assertEqual(self.s.por_id(sub["id"])["acesso_ate"], depois_do_1)

    def test_replay_nao_cancela_o_assinante_por_engano(self):
        """Um duplo-submit do 'aceitar' não pode virar cancelamento — o cliente clicou
        justamente para NÃO cancelar."""
        sub = self._assinante(sid=None, acesso_ate="2026-08-01",
                              oferta_em="2026-07-01T10:00:00")
        self._aceitar(sub)
        atual = self.s.por_id(sub["id"])
        self.assertEqual(atual["status"], "ATIVO")
        self.assertIsNone(atual["cancelado_em"])
