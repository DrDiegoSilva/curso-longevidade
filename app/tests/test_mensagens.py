"""Testes das mensagens de boas-vindas editáveis (+ settings do db). Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestMensagens(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import db as _db
        importlib.reload(_db)
        import mensagens as _m
        importlib.reload(_m)
        self.db, self.m = _db, _m
        self.db.init()

    def test_get_set_config(self):
        self.assertEqual(self.db.get_config("x", "padrao"), "padrao")
        self.db.set_config("x", "novo")
        self.assertEqual(self.db.get_config("x", "padrao"), "novo")

    def test_wa_default_substitui(self):
        out = self.m.wa_boas_vindas("http://senha", "Ana")
        self.assertIn("http://senha", out)
        self.assertNotIn("{link}", out)
        self.assertNotIn("{nome}", out)

    def test_wa_editado_persiste(self):
        self.db.set_config(self.m.K_WA, "Oi {nome}, senha: {link}")
        self.assertEqual(self.m.wa_boas_vindas("http://s", "Bia"), "Oi Bia, senha: http://s")

    def test_wa_sem_link_reanexado(self):
        self.db.set_config(self.m.K_WA, "Sem link aqui")   # admin removeu {link}
        self.assertIn("http://LINKSEGURO", self.m.wa_boas_vindas("http://LINKSEGURO", "X"))

    def test_email_assunto_e_html_com_botao(self):
        assunto, html = self.m.email_boas_vindas("Ana", "http://senha")
        self.assertTrue(assunto)                           # tem assunto
        self.assertIn('href="http://senha"', html)         # link vira botão
        self.assertIn("Ana", html)                         # {nome} substituído
        self.assertNotIn("{link}", html)
        self.assertNotIn("{nome}", html)

    def test_email_renovacao_default_substitui_marcadores(self):
        assunto, html = self.m.email_renovacao("Ana", "19 jul 2026", "http://entrar")
        self.assertTrue(assunto)
        self.assertIn('href="http://entrar"', html)        # link vira botão de entrar
        self.assertIn("Ana", html)                          # {nome} substituído
        self.assertIn("19 jul 2026", html)                  # {ate} substituído
        self.assertNotIn("{link}", html)
        self.assertNotIn("{nome}", html)
        self.assertNotIn("{ate}", html)

    def test_email_renovacao_editado_persiste(self):
        self.db.set_config(self.m.K_EMAIL_RENOV_ASSUNTO, "Assunto custom {nome}")
        self.db.set_config(self.m.K_EMAIL_RENOV_CORPO, "Oi {nome}, vale até {ate}. {link}")
        assunto, html = self.m.email_renovacao("Bia", "20 ago 2026", "http://s")
        self.assertEqual(assunto, "Assunto custom Bia")
        self.assertIn("Oi Bia, vale até 20 ago 2026.", html)
        self.assertIn('href="http://s"', html)

    def test_email_renovacao_sem_ate_reanexado(self):
        # Se o admin apagar {ate} do template, a data (informação essencial) é
        # re-anexada antes de enviar — senão a confirmação fica vazia.
        self.db.set_config(self.m.K_EMAIL_RENOV_CORPO, "Oi {nome}, tudo certo. {link}")
        assunto, html = self.m.email_renovacao("Bia", "20 ago 2026", "http://s")
        self.assertIn("20 ago 2026", html)

    def test_email_renovacao_sem_link_reanexado(self):
        self.db.set_config(self.m.K_EMAIL_RENOV_CORPO, "Oi {nome}, vale até {ate}.")
        assunto, html = self.m.email_renovacao("Bia", "20 ago 2026", "http://LINKSEGURO")
        self.assertIn("http://LINKSEGURO", html)

    # ── Bônus de resgate (Task 8/Projeto F) — configurável na tela de mensagens ──
    def test_bonus_resgate_default_e_30_sem_nada_salvo(self):
        self.assertEqual(self.m.bonus_resgate_dias(), 30)

    def test_bonus_resgate_le_valor_salvo(self):
        self.db.set_config(self.m.K_BONUS_RESGATE_DIAS, "15")
        self.assertEqual(self.m.bonus_resgate_dias(), 15)

    def test_bonus_resgate_zero_e_aceito_como_desligado(self):
        # 0 é um valor legítimo (Diego quer desligar o bônus) — não pode cair no default.
        self.db.set_config(self.m.K_BONUS_RESGATE_DIAS, "0")
        self.assertEqual(self.m.bonus_resgate_dias(), 0)

    def test_bonus_resgate_texto_invalido_cai_no_default(self):
        self.db.set_config(self.m.K_BONUS_RESGATE_DIAS, "abc")
        self.assertEqual(self.m.bonus_resgate_dias(), 30)

    def test_bonus_resgate_negativo_cai_no_default(self):
        self.db.set_config(self.m.K_BONUS_RESGATE_DIAS, "-5")
        self.assertEqual(self.m.bonus_resgate_dias(), 30)


if __name__ == "__main__":
    unittest.main()
