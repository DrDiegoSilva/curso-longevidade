"""Testes do reenvio de boas-vindas (WhatsApp only) do admin. Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestReenviarBoasVindas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import db as _db
        importlib.reload(_db)
        import auth_web as _aw
        importlib.reload(_aw)
        self.db, self.aw = _db, _aw
        self.db.init()

    def test_sucesso_envia_so_whatsapp_com_link(self):
        enviados = []
        assinante = {"id": 1, "nome": "Gleidson", "whatsapp": "5544999998888"}
        ok, detalhe = self.aw.reenviar_boas_vindas_wa(
            assinante, enviar_fn=lambda num, msg: enviados.append((num, msg)))
        self.assertTrue(ok)
        self.assertEqual(detalhe, "")
        self.assertEqual(len(enviados), 1)               # exatamente 1 envio (WhatsApp)
        self.assertEqual(enviados[0][0], "5544999998888")
        self.assertIn("/criar-senha?token=", enviados[0][1])   # link novo no texto

    def test_falha_de_envio_retorna_motivo(self):
        def boom(num, msg):
            raise RuntimeError("evolution 500")
        ok, detalhe = self.aw.reenviar_boas_vindas_wa(
            {"id": 1, "nome": "X", "whatsapp": "5544999998888"}, enviar_fn=boom)
        self.assertFalse(ok)
        self.assertIn("evolution 500", detalhe)

    def test_sem_whatsapp_nao_envia(self):
        chamados = []
        ok, detalhe = self.aw.reenviar_boas_vindas_wa(
            {"id": 1, "nome": "SemZap", "whatsapp": ""},
            enviar_fn=lambda num, msg: chamados.append(num))
        self.assertFalse(ok)
        self.assertEqual(chamados, [])                    # não tentou enviar


if __name__ == "__main__":
    unittest.main()
