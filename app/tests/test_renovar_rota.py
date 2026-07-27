"""Testes da tela de renovação. Standalone."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PLANO = {"slug": "anual", "nome": "Anual", "cycle": "YEARLY", "base": 1099.0,
         "pix_desconto_pct": 5}


class TestPaginaRenovar(unittest.TestCase):
    def setUp(self):
        import site_web
        self.sw = site_web

    def test_mostra_plano_preco_e_vencimento(self):
        html = self.sw.pagina_renovar({"nome": "Teste"}, PLANO, 1044.05, 1099.0,
                                      "2026-08-01", bonus=False)
        self.assertIn("Anual", html)
        self.assertIn("1.044,05", html)
        self.assertIn("1.099,00", html)
        # site_web._data_br formata por extenso ("1 ago 2026"), não DD/MM/AAAA —
        # usamos o helper existente em vez de reimplementar formatação de data.
        self.assertIn("1 ago 2026", html)

    def test_nao_tem_campo_de_cupom(self):
        # cupom de afiliado é só na 1ª venda — a tela de renovação não pode oferecer
        html = self.sw.pagina_renovar({"nome": "T"}, PLANO, 1044.05, 1099.0,
                                      "2026-08-01", bonus=False)
        self.assertNotIn('name="cupom"', html)

    def test_bonus_aparece_so_quando_expirado(self):
        com = self.sw.pagina_renovar({"nome": "T"}, PLANO, 1044.05, 1099.0,
                                     "2026-08-01", bonus=True)
        sem = self.sw.pagina_renovar({"nome": "T"}, PLANO, 1044.05, 1099.0,
                                     "2026-08-01", bonus=False)
        self.assertIn("1 mês extra", com)
        self.assertNotIn("1 mês extra", sem)

    def test_form_posta_o_metodo_escolhido(self):
        html = self.sw.pagina_renovar({"nome": "T"}, PLANO, 1044.05, 1099.0,
                                      "2026-08-01", bonus=False)
        self.assertIn('action="/renovar"', html)
        self.assertIn('name="metodo"', html)


class _RenovarStub:
    """Stub mínimo pro `self` de `_post_renovar`: implementa só o que o método usa
    (`_sub_logado`, `_html`, `_redirect`) — não abre socket, não é uma requisição HTTP
    real. Mesmo padrão do `_AssinarStub` (test_aceite_checkout.py) e do `_RotaStub`
    (test_reaceite.py)."""

    def __init__(self, sub):
        self._sub = sub

    def _sub_logado(self):
        return self._sub

    def _html(self, s, code=200):
        return s

    def _redirect(self, location, token=None, clear=False):
        return f"<redirect {location}>"


class TestPostRenovarHandler(unittest.TestCase):
    """ACHADO (revisão): os 4 testes acima chamam só `site_web.pagina_renovar`, que é
    apresentação. Ninguém exercitava `serve.Handler._post_renovar`, que é onde o
    preço é CALCULADO e o checkout do Asaas é montado — uma implementação que lesse
    o preço do formulário, reintroduzisse `cupom`, ou parasse de normalizar `metodo`
    passaria batida pela suíte inteira sem quebrar nada. Chamamos o método de rota de
    verdade, com um stub mínimo de `self` (mesmo formato do `_AssinarStub` de
    test_aceite_checkout.py)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "subscribers", "serve", "site_web", "renovacao", "pricing", "asaas"):
            sys.modules.pop(m, None)
        import db, config, subscribers, serve, renovacao, pricing, asaas
        db._INITED = False
        db.init()
        self.db, self.config, self.subs = db, config, subscribers
        self.serve, self.renovacao, self.pricing, self.asaas = serve, renovacao, pricing, asaas
        self.plano = config.plano_por_slug("anual")
        # valor_contratado != plano["base"] (997 vs 1099) de propósito: se o handler
        # cair no preço de TABELA em vez do contratado, os testes abaixo pegam.
        self.sub = {"id": "sub1", "nome": "Cliente Teste", "email": "cliente@example.com",
                    "cpf": "11144477735", "whatsapp": "43999990000", "plano": "anual",
                    "valor_contratado": 997.0, "proximo_vencimento": "2026-08-01",
                    "status": "ATIVO"}

    def _g(self, **over):
        """Monta o `g` como o do POST real (`form.get(k, [""])[0]`). Os campos default
        tentam forçar outro valor/plano/parcelas/cupom — nenhum é lido por
        `_post_renovar`, então devem ser ignorados por completo."""
        base = {"metodo": "PIX", "valor": "1.00", "preco": "1.00", "plano": "mensal",
                "parcelas": "12", "cupom": "CUPOM100"}
        base.update(over)
        return lambda k: base.get(k, "")

    def _fakes(self):
        """Substitui banco e Asaas por fakes que só registram o que receberam —
        nenhuma chamada de rede real. Retorna (pendings, montagens, restaurar); o
        chamador deve invocar `restaurar()` num `finally`."""
        pendings, montagens = [], []
        orig_criar_pending = self.db.criar_pending
        orig_montar = self.asaas.montar_checkout
        orig_criar_checkout = self.asaas.criar_checkout

        def fake_criar_pending(dados):
            pendings.append(dados)
            return "TOKEN-FAKE"

        def fake_montar(plano, metodo, parcelas, dados, token, base_url, base=None):
            montagens.append({"plano": plano, "metodo": metodo, "parcelas": parcelas,
                              "dados": dados, "token": token, "base_url": base_url, "base": base})
            return {"fake": "payload"}

        def fake_criar_checkout(payload):
            return {"url": "https://checkout.asaas.example/x", "id": "chk_1"}

        self.db.criar_pending = fake_criar_pending
        self.asaas.montar_checkout = fake_montar
        self.asaas.criar_checkout = fake_criar_checkout

        def restaurar():
            self.db.criar_pending = orig_criar_pending
            self.asaas.montar_checkout = orig_montar
            self.asaas.criar_checkout = orig_criar_checkout

        return pendings, montagens, restaurar

    def test_preco_nao_vem_do_formulario(self):
        # O POST tenta forçar valor=1.00, preco=1.00, plano=mensal, parcelas=12 e um
        # cupom — o preço que deve chegar ao pending e ao checkout é o CONTRATADO
        # (renovacao.preco_renovacao), com o desconto Pix por cima, nunca o do form
        # nem o de tabela do plano (1099.0).
        pendings, montagens, restaurar = self._fakes()
        stub = _RenovarStub(self.sub)
        try:
            html = self.serve.Handler._post_renovar(stub, self._g())
        finally:
            restaurar()
        self.assertEqual(html, "<redirect https://checkout.asaas.example/x>")
        self.assertEqual(len(pendings), 1)

        preco_esperado = self.renovacao.preco_renovacao(self.sub, self.plano)
        base_esperada = self.pricing.base_cobrada(self.plano, "PIX", preco_esperado, 0.0)
        base_tabela = self.pricing.base_cobrada(self.plano, "PIX", self.plano["base"], 0.0)
        self.assertNotEqual(base_esperada, base_tabela)          # contratado != tabela, nesta massa

        self.assertEqual(pendings[0]["valor"], base_esperada)
        self.assertNotEqual(pendings[0]["valor"], 1.00)           # não veio de "valor"/"preco" do form
        self.assertEqual(pendings[0]["plano"], "anual")           # não veio de "plano" do form ("mensal")
        self.assertEqual(pendings[0]["parcelas"], 1)              # não veio de "parcelas" do form (12)
        self.assertEqual(pendings[0]["afiliado_codigo"], "")      # cupom do form ignorado
        self.assertEqual(montagens[0]["base"], base_esperada)     # o checkout do Asaas recebe o mesmo valor

    def test_metodo_invalido_cai_em_pix(self):
        # O normalizador de `_post_renovar` só aceita CARTAO ou PIX — qualquer outra
        # coisa (typo, valor idiota do form) tem que virar PIX, nunca vazar direto.
        pendings, montagens, restaurar = self._fakes()
        stub = _RenovarStub(self.sub)
        try:
            self.serve.Handler._post_renovar(stub, self._g(metodo="boleto"))
        finally:
            restaurar()
        self.assertEqual(pendings[0]["metodo"], "PIX")
        self.assertEqual(montagens[0]["metodo"], "PIX")

    def test_sem_sessao_redireciona_para_entrar(self):
        # Sem assinante logado, a rota tem que mandar pro /entrar e não pode ter
        # nenhum efeito colateral — nem um pending criado.
        pendings, montagens, restaurar = self._fakes()
        stub = _RenovarStub(None)
        try:
            html = self.serve.Handler._post_renovar(stub, self._g())
        finally:
            restaurar()
        self.assertEqual(html, "<redirect /entrar>")
        self.assertEqual(pendings, [])

    def test_falha_no_checkout_reapresenta_tela_com_erro(self):
        # Se o Asaas falhar (rede, HTTP, o que for), o handler tem que capturar e
        # devolver a própria tela de renovação com mensagem de erro — nunca estourar
        # a exceção pro cliente.
        pendings, montagens, restaurar = self._fakes()

        def fake_criar_checkout_falha(payload):
            raise RuntimeError("timeout simulado")

        self.asaas.criar_checkout = fake_criar_checkout_falha
        stub = _RenovarStub(self.sub)
        try:
            html = self.serve.Handler._post_renovar(stub, self._g())
        finally:
            restaurar()
        self.assertIn("Não conseguimos iniciar o pagamento", html)
        self.assertEqual(len(pendings), 1)   # pending já tinha sido criado antes da falha no checkout


if __name__ == "__main__":
    unittest.main()
