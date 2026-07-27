"""Testes do redesign em cards da tela de Assinantes (layout + filtros + contador de plano). Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAdminCards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import site_web as _sw
        importlib.reload(_sw)
        self.sw = _sw

    def _sub(self, **kw):
        base = {"id": 1, "nome": "Ana", "whatsapp": "5544999998888", "email": "a@x.com",
                "plano": "mensal", "status": "ATIVO", "slot_envio": "08h",
                "proximo_vencimento": "2026-08-01"}
        base.update(kw)
        return base

    def _cont(self, **kw):
        base = {"07h": 0, "08h": 0, "12h": 0, "18h": 0, "20h": 0}
        base.update(kw)
        return base

    def test_cards_em_vez_de_tabela(self):
        html = self.sw.pagina_admin([self._sub()], token="tk", contagem_slots=self._cont(**{"08h": 1}))
        self.assertIn('class="subcard"', html)
        self.assertIn('class="subgrid"', html)
        self.assertIn("Ana", html)

    def test_editar_numero_atras_de_details(self):
        html = self.sw.pagina_admin([self._sub()], token="tk")
        self.assertIn("<details", html)
        self.assertIn("editar número", html)
        self.assertIn('value="editar_numero"', html)
        # o form de editar número vem DEPOIS de um <summary> (ou seja, está escondido no details)
        self.assertLess(html.find("<summary"), html.find('value="editar_numero"'))

    def test_horario_visivel_com_atual(self):
        html = self.sw.pagina_admin([self._sub(slot_envio="12h")], token="tk")
        self.assertIn('value="definir_slot"', html)
        self.assertIn('<option value="12h" selected', html)

    def test_contador_plano_mensal_anual(self):
        subs = [self._sub(id=1, plano="mensal"), self._sub(id=2, plano="mensal"),
                self._sub(id=3, plano="anual")]
        html = self.sw.pagina_admin(subs, token="tk")
        self.assertIn("Mensal: 2", html)
        self.assertIn("Anual: 1", html)

    def test_filtros_nome_e_horario(self):
        html = self.sw.pagina_admin([self._sub()], token="tk", contagem_slots=self._cont(**{"08h": 1}))
        self.assertIn('id="f-nome"', html)       # busca por nome
        self.assertIn('class="f-slot', html)     # chips de horário (filtro)
        self.assertIn("data-nome=", html)        # atributos p/ o filtro client-side
        self.assertIn("data-slot=", html)

    def test_filtro_status_e_contador(self):
        subs = [self._sub(id=1, status="ATIVO"), self._sub(id=2, status="INADIMPLENTE")]
        html = self.sw.pagina_admin(subs, token="tk")
        self.assertIn('id="f-count"', html)           # contador "mostrando X de Y"
        self.assertIn("mostrando 2 de 2", html)
        self.assertIn('class="f-status', html)        # chips de status
        self.assertIn('data-status="ATIVO"', html)    # chip de Ativos
        self.assertIn("Ativos (1)", html)             # contagem por status no rótulo
        self.assertIn('data-status="ATIVO"', html)
        self.assertIn("Inadimplentes (1)", html)

    def test_card_tem_data_status(self):
        html = self.sw.pagina_admin([self._sub(status="INADIMPLENTE")], token="tk")
        self.assertIn('data-status="INADIMPLENTE"', html)

    def test_vazio(self):
        html = self.sw.pagina_admin([], token="tk")
        self.assertIn("Nenhum assinante ainda", html)


if __name__ == "__main__":
    unittest.main()
