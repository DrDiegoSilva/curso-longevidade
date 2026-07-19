"""Testes do auth_web.py (login OTP + sessão). Standalone: python3 app/tests/test_auth_web.py"""
import os
import re
import sys
import json
import tempfile
import importlib
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAuth(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        # assinantes: um ATIVO, um inativo
        with open(os.path.join(self.tmp, "subscribers.json"), "w", encoding="utf-8") as f:
            json.dump([
                {"id": "1", "nome": "Dr. Ativo", "whatsapp": "5543999990000", "status": "ATIVO"},
                {"id": "2", "nome": "Dr. Fora", "whatsapp": "5543888880000", "status": "CANCELADO"},
            ], f)
        for m in ("config", "db", "subscribers", "auth_web"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, subscribers, auth_web
        importlib.reload(config); importlib.reload(db)
        importlib.reload(subscribers); importlib.reload(auth_web)
        self.db = db
        self.auth = auth_web
        self.db.init()
        self.enviados = []
        self.enviar_fn = lambda wpp, msg: self.enviados.append((wpp, msg))

    def _codigo_enviado(self):
        return re.search(r"\b(\d{6})\b", self.enviados[-1][1]).group(1)

    def test_parse_cookie(self):
        self.assertEqual(self.auth._parse_cookie("a=1; sid=xyz; b=2").get("sid"), "xyz")
        self.assertEqual(self.auth._parse_cookie(""), {})

    def test_iniciar_so_ativo(self):
        self.assertTrue(self.auth.iniciar_login("55 43 99999-0000", enviar_fn=self.enviar_fn))
        self.assertEqual(len(self.enviados), 1)
        # inativo: nada enviado, mas retorno neutro (False)
        self.assertFalse(self.auth.iniciar_login("5543888880000", enviar_fn=self.enviar_fn))
        # desconhecido: nada enviado
        self.assertFalse(self.auth.iniciar_login("5511000000000", enviar_fn=self.enviar_fn))
        self.assertEqual(len(self.enviados), 1)

    def test_verificar_acerto_cria_sessao(self):
        self.auth.iniciar_login("5543999990000", enviar_fn=self.enviar_fn)
        cod = self._codigo_enviado()
        tok = self.auth.verificar("5543999990000", cod)
        self.assertTrue(tok)
        sess = self.auth.sessao(f"sid={tok}")
        self.assertEqual(sess["whatsapp"], "5543999990000")
        self.assertEqual(sess["nome"], "Dr. Ativo")

    def test_verificar_codigo_errado(self):
        self.auth.iniciar_login("5543999990000", enviar_fn=self.enviar_fn)
        self.assertIsNone(self.auth.verificar("5543999990000", "000000"))

    def test_trava_apos_5_tentativas(self):
        self.auth.iniciar_login("5543999990000", enviar_fn=self.enviar_fn)
        cod = self._codigo_enviado()
        for _ in range(5):
            self.auth.verificar("5543999990000", "999999")
        # mesmo com o código certo, travou
        self.assertIsNone(self.auth.verificar("5543999990000", cod))

    def test_codigo_expirado(self):
        self.auth.iniciar_login("5543999990000", enviar_fn=self.enviar_fn)
        cod = self._codigo_enviado()
        # força expiração no banco
        with self.db._conn() as c:
            c.execute("UPDATE login_codes SET expira=? WHERE whatsapp=?",
                      ((datetime.now() - timedelta(minutes=1)).isoformat(), "5543999990000"))
        self.assertIsNone(self.auth.verificar("5543999990000", cod))

    def test_sessao_expirada_e_logout(self):
        self.auth.iniciar_login("5543999990000", enviar_fn=self.enviar_fn)
        tok = self.auth.verificar("5543999990000", self._codigo_enviado())
        self.assertIsNotNone(self.auth.sessao(f"sid={tok}"))
        self.auth.logout(tok)
        self.assertIsNone(self.auth.sessao(f"sid={tok}"))

    # ── Login por senha ──
    def _token_link(self):
        return re.search(r"token=([0-9a-f]+)", self.enviados[-1][1]).group(1)

    def test_login_senha_sem_senha_ainda(self):
        status, tok = self.auth.login_senha("5543999990000", "qualquer")
        self.assertEqual(status, "sem_senha")
        self.assertIsNone(tok)

    def test_login_senha_inativo(self):
        self.assertEqual(self.auth.login_senha("5543888880000", "x")[0], "inativo")   # CANCELADO
        self.assertEqual(self.auth.login_senha("5511000000000", "x")[0], "inativo")   # desconhecido

    def test_precisa_criar_senha(self):
        self.assertTrue(self.auth.precisa_criar_senha("5543999990000"))

    def test_definir_senha_e_login_completo(self):
        self.assertTrue(self.auth.iniciar_definir_senha("5543999990000", "primeiro", enviar_fn=self.enviar_fn))
        token = self._token_link()
        status, sess = self.auth.definir_senha(token, "abc123", "abc123")
        self.assertEqual(status, "ok")
        self.assertTrue(sess)
        self.assertEqual(self.auth.sessao(f"sid={sess}")["whatsapp"], "5543999990000")
        self.assertFalse(self.auth.precisa_criar_senha("5543999990000"))
        # login por senha agora funciona (sem WhatsApp no caminho)
        self.assertEqual(self.auth.login_senha("5543999990000", "abc123")[0], "ok")
        self.assertEqual(self.auth.login_senha("5543999990000", "errada")[0], "credenciais")
        # token é de uso único
        self.assertEqual(self.auth.definir_senha(token, "abc123", "abc123")[0], "token_invalido")

    def test_definir_senha_fraca_e_nao_confere(self):
        self.auth.iniciar_definir_senha("5543999990000", "primeiro", enviar_fn=self.enviar_fn)
        token = self._token_link()
        self.assertEqual(self.auth.definir_senha(token, "abc", "abc")[0], "fraca")        # sem número/curta
        self.assertEqual(self.auth.definir_senha(token, "abc123", "xyz999")[0], "nao_confere")
        self.assertEqual(self.auth.definir_senha(token, "abc123", "abc123")[0], "ok")     # token não foi consumido antes

    def test_definir_senha_token_invalido(self):
        self.assertEqual(self.auth.definir_senha("naoexiste", "abc123", "abc123")[0], "token_invalido")
        self.assertEqual(self.auth.definir_senha("", "abc123", "abc123")[0], "token_invalido")

    def test_reset_token_expirado(self):
        self.auth.iniciar_definir_senha("5543999990000", "esqueci", enviar_fn=self.enviar_fn)
        token = self._token_link()
        with self.db._conn() as c:
            c.execute("UPDATE senha_tokens SET expira=? WHERE token=?",
                      ((datetime.now() - timedelta(minutes=1)).isoformat(), token))
        self.assertEqual(self.auth.definir_senha(token, "abc123", "abc123")[0], "token_invalido")

    def test_iniciar_definir_senha_neutro_desconhecido(self):
        self.assertFalse(self.auth.iniciar_definir_senha("5511000000000", "esqueci", enviar_fn=self.enviar_fn))
        self.assertEqual(len(self.enviados), 0)


if __name__ == "__main__":
    unittest.main()
