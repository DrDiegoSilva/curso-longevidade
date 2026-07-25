"""Testes do re-aceite dos termos pela base atual. Standalone."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPrecisaAceitar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "subscribers"):
            sys.modules.pop(m, None)
        import db, subscribers, legal
        db._INITED = False
        db.init()
        self.subs, self.legal = subscribers, legal

    def test_assinante_sem_aceite_precisa_aceitar(self):
        self.assertTrue(self.subs.precisa_aceitar({"termos_versao": None}))
        self.assertTrue(self.subs.precisa_aceitar({}))

    def test_assinante_com_versao_antiga_precisa_aceitar(self):
        self.assertTrue(self.subs.precisa_aceitar({"termos_versao": "2020-01-01"}))

    def test_assinante_com_versao_atual_nao_precisa(self):
        self.assertFalse(self.subs.precisa_aceitar({"termos_versao": self.legal.VERSAO}))

    def test_registrar_aceite_grava_versao_data_e_ip(self):
        reg = self.subs.criar_de_pagamento(
            {"nome": "T", "whatsapp": "43999990000", "email": "t@e.com", "plano": "anual"}, {})
        self.subs.registrar_aceite(reg["id"], self.legal.VERSAO, "203.0.113.7")
        atual = [s for s in self.subs.listar() if s["id"] == reg["id"]][0]
        self.assertEqual(atual["termos_versao"], self.legal.VERSAO)
        self.assertTrue(atual["termos_aceito_em"])
        self.assertEqual(atual["termos_ip"], "203.0.113.7")
        self.assertFalse(self.subs.precisa_aceitar(atual))


class TestPaginaAceite(unittest.TestCase):
    def test_pagina_tem_checkbox_e_links(self):
        import site_legal
        html = site_legal.pagina_aceite_termos("/minha")
        self.assertIn('name="aceito"', html)
        self.assertIn('action="/aceitar-termos"', html)
        self.assertIn('href="/termos"', html)
        self.assertIn('href="/privacidade"', html)
        self.assertIn('value="/minha"', html)


class _RotaStub:
    """Stub mínimo pro `self` dos métodos de rota (`_site_get`/`_meus_dados_post`):
    implementa só o que esses métodos chamam — não abre socket, não é uma requisição
    HTTP real. Mesmo padrão do `_HandlerStub` de test_cancelamento_estorno.py."""

    def __init__(self, sub=None, sessao=None):
        self._sub = sub
        # sessão "existe" por padrão sempre que há assinante logado (dict raso, como
        # auth_web.sessao() devolveria); testes de sessão órfã passam `sessao=None`
        # explicitamente mesmo com `sub` presente não fazendo sentido aqui à toa.
        self._sess = sessao if sessao is not None else ({"whatsapp": sub["whatsapp"]} if sub else None)

    def _sub_logado(self):
        return self._sub

    def _sessao(self):
        return self._sess

    def _html(self, s, code=200):
        return s

    def _redirect(self, location, token=None, clear=False):
        return f"<redirect {location}>"

    def _rate_ok(self, nome, maximo, janela_seg):
        return True


class TestGateNasRotasDeVerdade(unittest.TestCase):
    """ACHADO 1/2 (Task 6): o gate de aceite precisa valer nas rotas de verdade
    (do_GET/_site_get e o POST /meus-dados), não só nas funções isoladas de
    subscribers/site_legal testadas acima — foi por faltar isso que o Critical (POST
    /meus-dados desprotegido) passava limpo pelos testes antigos."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "subscribers", "serve", "site_legal", "site_web", "legal"):
            sys.modules.pop(m, None)
        import db, subscribers, legal, serve, site_web
        db._INITED = False
        db.init()
        self.subs, self.legal, self.serve, self.site_web = subscribers, legal, serve, site_web
        self.reg = self.subs.criar_de_pagamento(
            {"nome": "T", "whatsapp": "43999990000", "email": "t@e.com", "plano": "anual"}, {})

    def _stub(self, aceito):
        """Assinante com aceite pendente (padrão) ou em dia, envolvido no stub de rota."""
        reg = self.subs.por_id(self.reg["id"])
        if aceito:
            self.subs.registrar_aceite(reg["id"], self.legal.VERSAO, "203.0.113.7")
            reg = self.subs.por_id(reg["id"])
        return _RotaStub(sub=reg), reg

    def test_post_meus_dados_aceite_pendente_nao_executa_acao(self):
        stub, _ = self._stub(aceito=False)
        chamadas = []
        orig = self.subs.atualizar_contato
        self.subs.atualizar_contato = lambda *a, **k: chamadas.append((a, k))
        try:
            g = lambda k: {"acao": "salvar_contato", "nome": "NOVO NOME",
                           "email": "novo@e.com"}.get(k, "")
            html = self.serve.Handler._meus_dados_post(stub, g)
        finally:
            self.subs.atualizar_contato = orig
        self.assertEqual(chamadas, [])                         # nenhuma ação executada
        self.assertIn('action="/aceitar-termos"', html)        # tela de aceite devolvida

    def test_post_meus_dados_aceite_em_dia_executa_acao(self):
        stub, reg = self._stub(aceito=True)
        g = lambda k: {"acao": "salvar_contato", "nome": "NOVO NOME",
                       "email": "novo@e.com"}.get(k, "")
        html = self.serve.Handler._meus_dados_post(stub, g)
        atual = self.subs.por_id(reg["id"])
        self.assertEqual(atual["nome"], "NOVO NOME")
        self.assertEqual(atual["email"], "novo@e.com")
        self.assertIn("Dados salvos", html)

    def test_get_minha_aceite_pendente_mostra_tela_aceite(self):
        stub, _ = self._stub(aceito=False)
        html = self.serve.Handler._site_get(stub, "/minha")
        self.assertIn('action="/aceitar-termos"', html)

    def test_get_meus_dados_aceite_pendente_mostra_tela_aceite(self):
        stub, _ = self._stub(aceito=False)
        html = self.serve.Handler._site_get(stub, "/meus-dados")
        self.assertIn('action="/aceitar-termos"', html)

    def test_get_minha_e_meus_dados_aceite_em_dia_passam_direto(self):
        stub, _ = self._stub(aceito=True)
        html_minha = self.serve.Handler._site_get(stub, "/minha")
        html_dados = self.serve.Handler._site_get(stub, "/meus-dados")
        self.assertNotIn('action="/aceitar-termos"', html_minha)
        self.assertNotIn('action="/aceitar-termos"', html_dados)
        self.assertIn("Minha assinatura", html_minha)
        self.assertIn("Meus dados", html_dados)

    def test_minha_com_sessao_orfa_redireciona_pro_login(self):
        # ACHADO 4: sessão viva (cookie válido) mas o assinante já não existe mais no
        # cadastro (removido) -> sessão inválida, não pode cair na tela de aceite nem
        # na área de conta usando só o dict raso da sessão.
        stub = _RotaStub(sub=None, sessao={"whatsapp": "43999990000"})
        html = self.serve.Handler._site_get(stub, "/minha")
        self.assertEqual(html, "<redirect /entrar>")

    def test_cancelar_continua_acessivel_com_aceite_pendente(self):
        # exceção deliberada: quem quer cancelar não pode ser barrado pelo aceite.
        stub, _ = self._stub(aceito=False)
        html = self.serve.Handler._site_get(stub, "/cancelar")
        self.assertNotIn('action="/aceitar-termos"', html)


if __name__ == "__main__":
    unittest.main()
