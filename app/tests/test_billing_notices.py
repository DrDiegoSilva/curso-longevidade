"""Testes do billing_notices (seleção de quem avisar). Standalone."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAvisar(unittest.TestCase):
    def setUp(self):
        import billing_notices
        self.b = billing_notices
        self.hoje = date(2026, 7, 19)

    def _s(self, pv, status="ATIVO", aviso=None, email="a@x.com", asaas_subscription_id="sub_1"):
        return {"id": "1", "status": status, "proximo_vencimento": pv, "aviso_renov_em": aviso,
                "email": email, "asaas_subscription_id": asaas_subscription_id}

    def test_dentro_da_janela(self):
        pv = (self.hoje + timedelta(days=2)).isoformat()
        self.assertEqual(len(self.b.assinantes_a_avisar([self._s(pv)], 3, self.hoje)), 1)

    def test_fora_da_janela(self):
        pv = (self.hoje + timedelta(days=10)).isoformat()
        self.assertEqual(self.b.assinantes_a_avisar([self._s(pv)], 3, self.hoje), [])

    def test_ja_avisado_nao_reavisa(self):
        pv = (self.hoje + timedelta(days=1)).isoformat()
        self.assertEqual(self.b.assinantes_a_avisar([self._s(pv, aviso=pv)], 3, self.hoje), [])

    def test_novo_ciclo_reavisa(self):
        pv = (self.hoje + timedelta(days=1)).isoformat()
        velho = (self.hoje - timedelta(days=360)).isoformat()
        self.assertEqual(len(self.b.assinantes_a_avisar([self._s(pv, aviso=velho)], 3, self.hoje)), 1)

    def test_cancelado_nao_avisa(self):
        pv = (self.hoje + timedelta(days=1)).isoformat()
        self.assertEqual(self.b.assinantes_a_avisar([self._s(pv, status="CANCELADO")], 3, self.hoje), [])

    def test_sem_assinatura_recorrente_nao_avisa(self):
        # Pix à vista / cartão parcelado não tem asaas_subscription_id — quem avisa
        # esse público agora é a régua (regua.py), não este e-mail de pré-renovação.
        pv = (self.hoje + timedelta(days=1)).isoformat()
        self.assertEqual(
            self.b.assinantes_a_avisar([self._s(pv, asaas_subscription_id=None)], 3, self.hoje), [])


class TestEnvioPreRenovacao(unittest.TestCase):
    """O ENVIO do aviso (a seleção é a classe acima).

    Passou pro WhatsApp em 2026-08-01: o canal de e-mail nunca funcionou em produção
    (ver `canal-email-morto`) e o Resend do Diego só tem `clinicdspro.com.br` verificado —
    mandar cobrança da Atualização Científica de um domínio de outra marca é pedir spam.
    O WhatsApp é onde o assinante já recebe o produto todo dia.
    """

    def setUp(self):
        import billing_notices, subscribers
        self.b, self.s = billing_notices, subscribers
        self.marcados, self.enviados = [], []
        self._orig = (subscribers.listar, subscribers.marcar_status)
        subscribers.marcar_status = lambda sid, status, **kw: self.marcados.append((sid, kw))

    def tearDown(self):
        self.s.listar, self.s.marcar_status = self._orig

    def _sub(self, **over):
        hoje = date.today()
        base = {"id": "s1", "nome": "Dr. Fulano", "status": "ATIVO",
                "proximo_vencimento": (hoje + timedelta(days=2)).isoformat(),
                "aviso_renov_em": None, "email": "a@x.com",
                "whatsapp": "5543999990000", "asaas_subscription_id": "sub_1"}
        base.update(over)
        return base

    def _espiao(self):
        return lambda w, m: self.enviados.append((w, m))

    def test_aviso_vai_por_whatsapp_em_texto_puro(self):
        self.s.listar = lambda: [self._sub()]
        n = self.b.avisar_pre_renovacao(enviar_fn=self._espiao())
        self.assertEqual(len(self.enviados), 1)
        destino, texto = self.enviados[0]
        self.assertEqual(destino, "5543999990000")
        self.assertNotIn("<", texto)              # WhatsApp entrega tag crua na cara
        self.assertIn("vence em", texto)
        self.assertEqual(n, 1)

    def test_sem_whatsapp_nao_marca_como_avisado(self):
        """O BUG que estava aqui: `aviso_renov_em` era gravado FORA do if do canal, então
        quem não tinha como ser avisado ficava registrado como avisado — e não recebia
        mais nada naquele ciclo. Com o e-mail morto, isso valia pra todo mundo."""
        self.s.listar = lambda: [self._sub(whatsapp="")]
        n = self.b.avisar_pre_renovacao(enviar_fn=self._espiao())
        self.assertEqual(self.enviados, [])
        self.assertEqual(self.marcados, [])       # não pode dizer que avisou
        self.assertEqual(n, 0)

    def test_falha_no_envio_nao_marca(self):
        """Falhou o envio: não marca, pra tentar de novo amanhã."""
        self.s.listar = lambda: [self._sub()]

        def explode(w, m):
            raise RuntimeError("evolution fora do ar")

        n = self.b.avisar_pre_renovacao(enviar_fn=explode)
        self.assertEqual(self.marcados, [])
        self.assertEqual(n, 0)

    def test_marca_o_ciclo_de_quem_foi_avisado(self):
        sub = self._sub()
        self.s.listar = lambda: [sub]
        self.b.avisar_pre_renovacao(enviar_fn=self._espiao())
        self.assertEqual(len(self.marcados), 1)
        sid, kw = self.marcados[0]
        self.assertEqual(sid, "s1")
        self.assertEqual(kw.get("aviso_renov_em"), sub["proximo_vencimento"])

    def test_falha_em_um_nao_derruba_os_outros(self):
        self.s.listar = lambda: [self._sub(id="s1", whatsapp="5543999990001"),
                                 self._sub(id="s2", whatsapp="5543999990002")]

        def so_o_segundo(w, m):
            if w.endswith("1"):
                raise RuntimeError("numero invalido")
            self.enviados.append((w, m))

        n = self.b.avisar_pre_renovacao(enviar_fn=so_o_segundo)
        self.assertEqual(n, 1)
        self.assertEqual(len(self.marcados), 1)
        self.assertEqual(self.marcados[0][0], "s2")


if __name__ == "__main__":
    unittest.main()
