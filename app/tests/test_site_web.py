"""Smoke test do render (site_web). Standalone: python3 app/tests/test_site_web.py"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DSCURSO_DATA", tempfile.mkdtemp())


class TestRender(unittest.TestCase):
    def setUp(self):
        import site_web
        self.s = site_web

    def test_landing(self):
        h = self.s.landing()
        self.assertIn("<!doctype html>", h)
        self.assertIn("Quero assinar", h)
        self.assertIn("CRM-PR 54310", h)
        self.assertIn("Obesidade", h)

    def test_entrar(self):
        self.assertIn("Enviar código", self.s.pagina_entrar("numero"))
        self.assertIn("Digite o código", self.s.pagina_entrar("codigo", whatsapp="55x"))
        self.assertIn("noindex", self.s.pagina_entrar("numero"))

    def test_hub_vazio_e_cheio(self):
        # hub_temas hoje é só o estado vazio do arquivo (redesign em 00443c7): quando
        # há temas, o serve.py abre direto no 1º tema via lista_tema (abas + agrupamento
        # por mês/semana fazem o papel do antigo "hub" de temas).
        self.assertIn("Ainda não há", self.s.hub_temas([]))
        meta = {"slug": "obesidade", "rotulo": "Obesidade", "emoji": "⚖️", "cor": "#14332a"}
        temas = [{"slug": "obesidade", "rotulo": "Obesidade", "emoji": "⚖️", "cor": "#14332a", "total": 2}]
        digs = [{"data": "2026-07-01", "titulo_pt": "Estudo A"}, {"data": "2026-07-08", "titulo_pt": "Estudo B"}]
        h = self.s.lista_tema(meta, digs, temas)
        self.assertIn("2 edições", h)
        self.assertIn("/artigos/obesidade", h)

    def test_lista_e_digest(self):
        meta = {"slug": "obesidade", "rotulo": "Obesidade", "emoji": "⚖️", "cor": "#14332a"}
        digs = [{"data": "2026-07-19", "titulo_pt": "Estudo X"}]
        self.assertIn("Estudo X", self.s.lista_tema(meta, digs))
        d = {"data": "2026-07-19", "titulo_pt": "Estudo X <b>", "resumo": "Linha *forte*",
             "gancho": "dica", "grafico": '{"barras":[{"rotulo":"A","valor":5}]}', "doi": "10/x", "fonte": "NEJM", "url": "http://x"}
        html = self.s.pagina_digest(meta, d)
        self.assertIn("Estudo X &lt;b&gt;", html)   # escapado
        self.assertIn("<strong>forte</strong>", html)
        self.assertIn("bar-fill", html)             # gráfico renderizado
        self.assertIn("Ver o estudo original", html)

    def test_assinar_pick(self):
        h = self.s.pagina_assinar(None)
        self.assertIn("Escolha seu plano", h)
        self.assertIn("/assinar?plano=anual", h)

    def test_assinar_form_mensal(self):
        h = self.s.pagina_assinar("mensal")
        # redesign do checkout (fdb4898) separou nome/descrição em tiles: "Pix" +
        # "R$ 99,00 à vista" (antes era um rótulo único "Pix à vista · ...").
        self.assertIn('<span class="pt-nome">Pix</span>', h)
        self.assertIn("à vista", h)
        self.assertIn("/mês · renova", h)                 # cartão mensal recorre (texto encurtado no redesign)
        self.assertIn('name="metodo"', h)
        self.assertIn('name="cupom"', h)
        self.assertNotIn('<select name="parcelas"', h)    # mensal não parcela

    def test_assinar_form_anual_parcelas(self):
        h = self.s.pagina_assinar("anual")
        self.assertIn('<select name="parcelas">', h)
        self.assertIn("12x de", h)

    def test_obrigado(self):
        self.assertIn("Quase lá", self.s.pagina_obrigado())

    def test_cancelar_fluxo(self):
        self.assertIn("Por que está cancelando", self.s.pagina_cancelar())
        self.assertIn("erro-teste", self.s.pagina_cancelar("erro-teste"))
        of = self.s.pagina_cancelar_oferta("caro demais")
        self.assertIn("mais um mês", of)
        self.assertIn('value="caro demais"', of)          # motivo preservado
        self.assertIn('name="acao" value="aceitar"', of)
        self.assertIn("cancelada", self.s.pagina_cancelado("2026-08-19"))

    def test_robots(self):
        self.assertIn("Disallow: /artigos", self.s.robots_txt())
        self.assertIn("Disallow: /assinar", self.s.robots_txt())

    def test_minha_enxuta_e_cards(self):
        html = self.s.pagina_minha({"nome": "Diego"}, admin=True)
        self.assertNotIn("Ir para o arquivo", html)     # não duplica o topo
        self.assertNotIn("Sair desta conta", html)
        self.assertIn("Meus dados", html)               # novo caminho
        self.assertIn("curbtn", html)                   # painel em botões-card
        self.assertIn("Agenda", html)                   # atalho novo incluído
        self.assertNotIn("Cancelar assinatura", html)   # cancelar saiu daqui

    def test_topbar_omite_minha_conta_na_propria(self):
        self.assertNotIn(">Minha conta<", self.s._topbar(True, atual="/minha"))
        self.assertIn(">Minha conta<", self.s._topbar(True, atual="/artigos"))

    def test_estoque_cards_e_chip(self):
        cont = {"novo": 12, "selecionado": 4, "resumido": 31}
        reserva = [{"status": "pronto", "tema": "Obesidade", "titulo_pt": "X"}]
        # 3 candidatos cobrindo as 3 faixas de _chip_score (hi >=7, md >=4, lo <4).
        # Scores escolhidos para NÃO colidir com os exemplos fixos da legenda
        # estática (8, 5, 2) — senão a asserção passa mesmo com _chip_score quebrado.
        cand = [
            {"id": "1", "tema": "Obesidade", "titulo": "Alto", "pergunta": "P",
             "fonte": "NEJM", "data": "2026-01-01", "score": 8.5, "doi": ""},
            {"id": "2", "tema": "Obesidade", "titulo": "Medio", "pergunta": "P",
             "fonte": "NEJM", "data": "2026-01-01", "score": 5.3, "doi": ""},
            {"id": "3", "tema": "Obesidade", "titulo": "Baixo", "pergunta": "P",
             "fonte": "NEJM", "data": "2026-01-01", "score": 2.7, "doi": ""},
        ]
        html = self.s.pagina_curadoria(cand, reserva, cont, "tok")
        self.assertIn("statcard", html)        # números viraram cartões
        self.assertIn("importância clínica", html)  # legenda do score
        # markup EXATO produzido por _chip_score (não a legenda estática) — falha
        # se os limiares (>=7 hi, >=4 md, <4 lo) ou o formato "{v:g}" mudarem.
        self.assertIn('<span class="scorechip hi">★ 8.5</span>', html)   # 8.5 -> hi, com estrela
        self.assertIn('<span class="scorechip md">5.3</span>', html)     # 5.3 -> md, sem estrela
        self.assertIn('<span class="scorechip lo">2.7</span>', html)     # 2.7 -> lo, sem estrela
        self.assertNotIn("· score ", html)     # regressão: formato textual antigo não deve voltar


if __name__ == "__main__":
    unittest.main()
