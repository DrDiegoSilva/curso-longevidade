"""Testes das rotas da trilha: página do assinante, '✅ fiz' e download. Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPaginaTrilha(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        for m in ("config", "db", "subscribers", "trilha", "site_web"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, subscribers, trilha, site_web
        for m in (config, db, subscribers, trilha, site_web):
            importlib.reload(m)
        subscribers._migrado = False
        db.init()
        self.cfg, self.db, self.subs, self.t, self.w = config, db, subscribers, trilha, site_web
        self.t.semear()

    def test_pagina_mostra_a_peca_e_o_botao(self):
        itens = [{"numero": 1, "titulo": "O custo real da sua hora", "feito": False,
                  "ferramenta_slug": ""}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens)
        self.assertIn("O custo real da sua hora", h)
        self.assertIn("fiz", h.lower())

    def test_peca_feita_nao_mostra_botao_de_novo(self):
        itens = [{"numero": 1, "titulo": "X", "feito": True, "ferramenta_slug": ""}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens)
        self.assertNotIn('value="marcar_feito"', h)

    def test_ferramenta_vira_link_de_download(self):
        itens = [{"numero": 1, "titulo": "X", "feito": False, "ferramenta_slug": "planilha-x"}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens)
        self.assertIn("/ferramentas/planilha-x", h)

    def test_escapa_titulo(self):
        itens = [{"numero": 1, "titulo": "<script>x</script>", "feito": False,
                  "ferramenta_slug": ""}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens)
        self.assertNotIn("<script>x", h)

    def test_lista_vazia_mostra_mensagem_de_fallback(self):
        # Minor 4 da revisão: função pura, mesmo estilo dos demais testes desta classe.
        h = self.w.pagina_trilha({"nome": "Diego"}, [])
        self.assertIn("chega no próximo sábado", h)

    def test_peca_ainda_nao_entregue_nao_mostra_botao(self):
        # Important 3 da revisão (defeito do plano, não da execução): o item de
        # prévia que `serve._pagina_trilha` insere quando a peça atual ainda não foi
        # enviada por WhatsApp vem com `entregue=False`. Antes desta correção, esse
        # item tinha o mesmo botão "✅ Fiz" dos itens já entregues — clicar chamava
        # `trilha_marcar_feito`, que devolve False em silêncio (não existe linha em
        # trilha_envios pra essa peça ainda), e a página só recarregava sem avisar
        # nada. Um botão que não faz nada é pior que nenhum botão.
        itens = [{"numero": 1, "titulo": "X", "feito": False, "ferramenta_slug": "",
                  "entregue": False}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens)
        self.assertNotIn('value="marcar_feito"', h)
        self.assertIn("sábado", h.lower())

    def test_item_sem_a_chave_entregue_continua_mostrando_o_botao(self):
        # Compatibilidade: item sem a chave `entregue` (formato usado pelos testes
        # mais antigos desta classe, acima) é tratado como já entregue -- não
        # queremos quebrar chamador nenhum que ainda não passe essa chave.
        itens = [{"numero": 1, "titulo": "X", "feito": False, "ferramenta_slug": ""}]
        h = self.w.pagina_trilha({"nome": "Diego"}, itens)
        self.assertIn('value="marcar_feito"', h)

    def test_saudacao_usa_o_nome_do_assinante(self):
        # Minor 5 da revisão: `sub` estava no assinatura mas não era usado no corpo
        # da página. Escolhi usar pra saudação (mesmo padrão de `pagina_minha`,
        # que faz `Olá, {nome}.`) em vez de remover o parâmetro -- justificativa no
        # relatório desta rodada.
        h = self.w.pagina_trilha({"nome": "Diego"}, [])
        self.assertIn("Diego", h)


class TestFerramentaSegura(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["DSCURSO_TRILHA_DIR"] = self.tmp
        for m in ("config", "db", "trilha"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, trilha
        for m in (config, db, trilha):
            importlib.reload(m)
        db.init()
        self.cfg, self.t = config, trilha
        os.makedirs(os.path.join(self.tmp, "ferramentas"), exist_ok=True)
        with open(os.path.join(self.tmp, "ferramentas", "planilha-x.csv"), "w") as f:
            f.write("a,b\n")

    def test_acha_a_ferramenta_existente(self):
        self.assertTrue(self.t.caminho_ferramenta("planilha-x"))

    def test_slug_inexistente_devolve_none(self):
        self.assertIsNone(self.t.caminho_ferramenta("nao-existe"))

    def test_path_traversal_e_barrado(self):
        for mau in ("../db.py", "..%2Fdb.py", "a/../../etc/passwd", "/etc/passwd",
                    "..", ".", "a\\..\\b"):
            self.assertIsNone(self.t.caminho_ferramenta(mau), f"passou: {mau}")


class TestTrilhaNumeroValido(unittest.TestCase):
    """Achado Important 2 da revisão: um `numero` com dezenas de dígitos no form de
    POST /trilha chegava direto em `db.trilha_marcar_feito`, que estoura
    `OverflowError: Python int too large to convert to SQLite INTEGER` (o sqlite3
    não converte um Python int de precisão arbitrária pra INTEGER de 64 bits) --
    sem try/except no caminho, e qualquer assinante logado conseguia disparar.
    `serve._trilha_numero_valido` filtra a faixa (1..config.TRILHA_TOTAL) ANTES de
    qualquer valor chegar no banco. Função pura, mesmo padrão de
    test_destino_seguro.py (TestDestinoSeguro)."""

    def setUp(self):
        import serve
        self.f = serve._trilha_numero_valido

    def test_numero_valido_passa(self):
        self.assertEqual(self.f("1"), 1)
        self.assertEqual(self.f("12"), 12)

    def test_numero_fora_da_faixa_vira_zero(self):
        self.assertEqual(self.f("0"), 0)
        self.assertEqual(self.f("13"), 0)
        self.assertEqual(self.f("-1"), 0)

    def test_numero_nao_numerico_vira_zero(self):
        self.assertEqual(self.f("abc"), 0)
        self.assertEqual(self.f(""), 0)
        self.assertEqual(self.f(None), 0)

    def test_numero_gigante_nao_estoura_e_vira_zero(self):
        # ~90 dígitos: bem além de qualquer INTEGER de 64 bits do SQLite.
        self.assertEqual(self.f("9" * 90), 0)


class _TrilhaPostStub:
    """Stub mínimo pro `self` de `_trilha_post`: só o que o método usa, sem abrir
    socket real -- mesmo padrão do `_AceitarTermosStub` de test_destino_seguro.py.
    `_pagina_trilha` aqui devolve só `msg` como marcador: esta classe testa
    roteamento (gate de aceite + validação de `numero`), não a renderização da
    página, que já está coberta em TestPaginaTrilha."""

    def __init__(self, sub):
        self._sub = sub
        self.redirects = []

    def _sub_logado(self):
        return self._sub

    def _html(self, s, code=200):
        return s

    def _redirect(self, location, token=None, clear=False):
        self.redirects.append(location)
        return f"<redirect {location}>"

    def _pagina_trilha(self, sub, msg=""):
        return f"<pagina msg={msg!r}>"


class TestTrilhaPostRota(unittest.TestCase):
    """Achado Important 1 da revisão: POST /trilha mutava (`marcar_feito`) sem
    checar o gate de aceite de termos que `_meus_dados_post` já respeita (o próprio
    repo documenta a regra lá: sem a checagem, "continuava gravando normalmente
    mesmo com o aceite pendente"). `db.trilha_marcar_feito` é exatamente esse tipo
    de mutação.

    Testa o MÉTODO real `serve.Handler._trilha_post`, chamado com um stub no lugar
    de `self` -- mesmo padrão de `TestAceitarTermosSanitizaDestinoDeVerdade` em
    test_destino_seguro.py. Não é teste de rota HTTP (não abre socket nem usa
    request real); é possível porque a Rodada de correção 1 extraiu a lógica de
    POST /trilha, antes inline em `do_POST`, para o método `_trilha_post` (mesma
    forma que `/meus-dados` já usava com `_meus_dados_post`)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        for m in ("config", "db", "subscribers", "trilha", "site_web", "legal", "serve"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, subscribers, trilha, site_web, legal, serve
        for m in (config, db, subscribers, trilha, site_web, legal, serve):
            importlib.reload(m)
        subscribers._migrado = False
        db.init()
        self.subs, self.legal, self.serve = subscribers, legal, serve
        self.sub = subscribers.criar_de_pagamento(
            {"nome": "T", "whatsapp": "43999990000", "email": "t@e.com", "plano": "anual"}, {})

    def _post(self, sub, acao="marcar_feito", numero="1"):
        stub = _TrilhaPostStub(sub)
        g = lambda k: {"acao": acao, "numero": numero}.get(k, "")
        return self.serve.Handler._trilha_post(stub, g)

    def test_aceite_pendente_bloqueia_marcar_feito(self):
        # assinante recém-criado nunca aceitou (termos_versao vazio) -> o gate tem
        # que barrar ANTES de qualquer chamada a trilha_marcar_feito/_pagina_trilha.
        html = self._post(self.sub)
        self.assertIn("aceit", html.lower())    # caiu na tela de aceite dos termos
        self.assertNotIn("pagina msg=", html)   # não chegou em _pagina_trilha

    def test_aceite_em_dia_deixa_a_rota_seguir(self):
        self.subs.registrar_aceite(self.sub["id"], self.legal.VERSAO, "203.0.113.7")
        sub2 = [s for s in self.subs.listar() if s["id"] == self.sub["id"]][0]
        html = self._post(sub2)
        self.assertIn("pagina msg=", html)      # passou do gate, chegou no final da rota

    def test_numero_gigante_no_form_nao_derruba_a_rota(self):
        # prova end-to-end do achado Important 2: sem a validação de faixa, este
        # cenário levantaria OverflowError dentro de db.trilha_marcar_feito.
        self.subs.registrar_aceite(self.sub["id"], self.legal.VERSAO, "203.0.113.7")
        sub2 = [s for s in self.subs.listar() if s["id"] == self.sub["id"]][0]
        html = self._post(sub2, numero="9" * 90)
        self.assertIn("pagina msg=", html)


if __name__ == "__main__":
    unittest.main()
