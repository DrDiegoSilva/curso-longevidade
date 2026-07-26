"""Mensal passa a ser só cartão; confirmação de renovação vai por canal. Standalone."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestMensalSemPix(unittest.TestCase):
    def test_plano_mensal_nao_aceita_pix(self):
        import config
        mensal = config.plano_por_slug("mensal")
        self.assertFalse(mensal.get("aceita_pix", True))

    def test_plano_anual_aceita_pix(self):
        import config
        self.assertTrue(config.plano_por_slug("anual").get("aceita_pix", True))

    def test_checkout_do_mensal_nao_mostra_tile_de_pix(self):
        import site_web
        html = site_web.pagina_assinar("mensal")
        self.assertNotIn('value="PIX"', html)
        self.assertIn('value="CARTAO"', html)

    def test_checkout_do_anual_mostra_os_dois(self):
        import site_web
        html = site_web.pagina_assinar("anual")
        self.assertIn('value="PIX"', html)
        self.assertIn('value="CARTAO"', html)


class TestConfirmacaoPorCanal(unittest.TestCase):
    def setUp(self):
        import webhook_asaas, deliver, email_send
        self.w = webhook_asaas
        self.wa, self.mail = [], []
        self._ow, self._om = deliver.enviar_texto, email_send.enviar
        deliver.enviar_texto = lambda w, m: self.wa.append((w, m))
        email_send.enviar = lambda d, a, c: self.mail.append((d, a))

    def tearDown(self):
        import deliver, email_send
        deliver.enviar_texto, email_send.enviar = self._ow, self._om

    def _sub(self):
        return {"id": "s1", "nome": "Teste", "email": "t@e.com", "whatsapp": "43999990000"}

    def test_renovacao_automatica_vai_por_email(self):
        self.w._confirmar_renovacao(self._sub(), "2027-08-01", automatica=True)
        self.assertEqual(len(self.mail), 1)
        self.assertEqual(self.wa, [])

    def test_renovacao_manual_vai_por_whatsapp(self):
        self.w._confirmar_renovacao(self._sub(), "2027-08-01", automatica=False)
        self.assertEqual(len(self.wa), 1)
        self.assertEqual(self.mail, [])


if __name__ == "__main__":
    unittest.main()
