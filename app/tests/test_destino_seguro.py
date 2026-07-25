"""ACHADO 3: valida o `destino` de POST /aceitar-termos contra CRLF injection (response
splitting) e open redirect. Standalone: python3 app/tests/test_destino_seguro.py"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDestinoSeguro(unittest.TestCase):
    def setUp(self):
        import serve
        self.f = serve._destino_seguro

    def test_destino_valido_passa_direto(self):
        self.assertEqual(self.f("/minha"), "/minha")
        self.assertEqual(self.f("/meus-dados"), "/meus-dados")

    def test_destino_vazio_ou_none_cai_no_padrao(self):
        self.assertEqual(self.f(""), "/minha")
        self.assertEqual(self.f(None), "/minha")

    def test_destino_sem_barra_inicial_cai_no_padrao(self):
        self.assertEqual(self.f("evil.com"), "/minha")
        self.assertEqual(self.f("https://evil.com"), "/minha")

    def test_open_redirect_protocolo_relativo_barra_dupla(self):
        self.assertEqual(self.f("//evil.com"), "/minha")

    def test_open_redirect_barra_invertida(self):
        # navegadores tratam "\" como "/" ao resolver URL -> "/\evil.com" vira
        # "https://evil.com" do mesmo jeito que "//evil.com"
        self.assertEqual(self.f("/\\evil.com"), "/minha")

    def test_crlf_injection_com_r_n_literais(self):
        self.assertEqual(self.f("/x\r\nX-Injected: 1"), "/minha")

    def test_crlf_injection_so_com_lf(self):
        self.assertEqual(self.f("/x\nSet-Cookie: sid=forjado"), "/minha")

    def test_crlf_injection_so_com_cr(self):
        self.assertEqual(self.f("/x\rSet-Cookie: sid=forjado"), "/minha")

    def test_caractere_fora_de_latin1_nao_derruba_e_cai_no_padrao(self):
        # antes disso, `send_header` levantava UnicodeEncodeError (latin-1 estrito) e
        # a resposta inteira quebrava em vez de só cair no destino padrão.
        self.assertEqual(self.f("/x☃"), "/minha")  # ☃ fora da faixa latin-1

    def test_destino_com_apenas_uma_barra_nao_quebra_a_validacao(self):
        # len(destino) == 1 não pode estourar IndexError ao checar destino[1]
        self.assertEqual(self.f("/"), "/")


class _AceitarTermosStub:
    """Stub mínimo pro `self` de `_aceitar_termos`: só implementa o que o método usa
    (não abre socket, não é requisição HTTP real). Mesmo padrão do `_RotaStub` de
    test_reaceite.py, com `headers`/`client_address` a mais (usados pro IP do aceite)."""

    def __init__(self, sub):
        self._sub = sub
        self.headers = {}
        self.client_address = ("203.0.113.9", 0)
        self.redirects = []

    def _sub_logado(self):
        return self._sub

    def _html(self, s, code=200):
        return s

    def _redirect(self, location, token=None, clear=False):
        self.redirects.append(location)
        return f"<redirect {location}>"


class TestAceitarTermosSanitizaDestinoDeVerdade(unittest.TestCase):
    """Garante que o gate real (`_aceitar_termos`, não só a função pura) sanitiza o
    destino antes do redirect -- é onde o Achado 3 mora de fato."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "subscribers", "serve", "legal"):
            sys.modules.pop(m, None)
        import db, subscribers, legal, serve
        db._INITED = False
        db.init()
        self.subs, self.legal, self.serve = subscribers, legal, serve
        self.reg = self.subs.criar_de_pagamento(
            {"nome": "T", "whatsapp": "43999990000", "email": "t@e.com", "plano": "anual"}, {})

    def _aceitar(self, destino):
        stub = _AceitarTermosStub(self.reg)
        g = lambda k: {"aceito": "1", "destino": destino}.get(k, "")
        self.serve.Handler._aceitar_termos(stub, g)
        return stub.redirects[0]

    def test_redirect_com_destino_malicioso_cai_no_padrao(self):
        self.assertEqual(self._aceitar("/\\evil.com"), "/minha")
        self.assertEqual(self._aceitar("/x\r\nX-Injected: 1"), "/minha")
        self.assertEqual(self._aceitar("//evil.com"), "/minha")

    def test_redirect_com_destino_legitimo_preserva(self):
        self.assertEqual(self._aceitar("/meus-dados"), "/meus-dados")


if __name__ == "__main__":
    unittest.main()
