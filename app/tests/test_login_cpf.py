"""Testes do login por CPF (acha por CPF e delega pro login por WhatsApp). Standalone."""
import os
import re
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

CPF_A = "12345678901"   # só dígitos — validade não importa (compara por dígitos)
CPF_B = "98765432100"


class TestLoginCPF(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import db as _db; importlib.reload(_db)
        import subscribers as _s; importlib.reload(_s)
        import passwords as _p; importlib.reload(_p)
        import auth_web as _aw; importlib.reload(_aw)
        self.db, self.subs, self.pw, self.aw = _db, _s, _p, _aw
        self.db.init()

    def _criar(self, cpf, whatsapp="5544999998888", senha="Senha1"):
        reg = self.subs.criar_de_pagamento(
            {"nome": "Fulano", "whatsapp": whatsapp, "cpf": cpf, "email": "",
             "plano": "mensal", "metodo": "PIX"})
        if senha:
            self.subs.definir_senha(reg["id"], self.pw.hash_senha(senha))
        return reg

    # ── senha ──
    def test_senha_ok(self):
        self._criar(CPF_A, senha="Senha1")
        status, token = self.aw.login_senha_cpf(CPF_A, "Senha1")
        self.assertEqual(status, "ok")
        self.assertTrue(token)

    def test_senha_errada(self):
        self._criar(CPF_A, senha="Senha1")
        self.assertEqual(self.aw.login_senha_cpf(CPF_A, "errada")[0], "credenciais")

    def test_sem_senha(self):
        self._criar(CPF_A, senha=None)
        self.assertEqual(self.aw.login_senha_cpf(CPF_A, "qualquer")[0], "sem_senha")

    def test_cpf_desconhecido(self):
        self.assertEqual(self.aw.login_senha_cpf(CPF_B, "x")[0], "inativo")

    def test_cpf_com_pontuacao_casa(self):
        self._criar(CPF_A, senha="Senha1")
        status, token = self.aw.login_senha_cpf("123.456.789-01", "Senha1")
        self.assertEqual(status, "ok")
        self.assertTrue(token)

    def test_intl_loga_por_cpf(self):
        self._criar(CPF_A, whatsapp="+15555551234", senha="Senha1")
        status, token = self.aw.login_senha_cpf(CPF_A, "Senha1")
        self.assertEqual(status, "ok")
        self.assertTrue(token)

    # ── código (OTP) ──
    def test_iniciar_login_cpf_envia_ao_numero_salvo(self):
        self._criar(CPF_A, whatsapp="+15555551234", senha=None)
        enviados = []
        ok = self.aw.iniciar_login_cpf(CPF_A, enviar_fn=lambda num, msg: enviados.append((num, msg)))
        self.assertTrue(ok)
        self.assertEqual(len(enviados), 1)
        self.assertIn("15555551234", enviados[0][0])   # foi pro número SALVO, não digitado

    def test_iniciar_login_cpf_desconhecido(self):
        chamados = []
        ok = self.aw.iniciar_login_cpf(CPF_B, enviar_fn=lambda n, m: chamados.append(n))
        self.assertFalse(ok)
        self.assertEqual(chamados, [])

    def test_verificar_cpf_codigo_certo_e_errado(self):
        self._criar(CPF_A, whatsapp="5544999998888", senha=None)
        enviados = []
        self.aw.iniciar_login_cpf(CPF_A, enviar_fn=lambda num, msg: enviados.append(msg))
        codigo = re.search(r"\*(\d{6})\*", enviados[0]).group(1)
        errado = "000000" if codigo != "000000" else "111111"
        self.assertIsNone(self.aw.verificar_cpf(CPF_A, errado))   # erra 1x (< MAX_TENTATIVAS)
        self.assertTrue(self.aw.verificar_cpf(CPF_A, codigo))     # acerta -> token

    def test_verificar_cpf_desconhecido(self):
        self.assertIsNone(self.aw.verificar_cpf(CPF_B, "123456"))


if __name__ == "__main__":
    unittest.main()
