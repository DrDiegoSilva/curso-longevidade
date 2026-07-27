"""Testes de render da coluna/resumo de horário no admin. Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAdminHorarioUI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import site_web as _sw
        importlib.reload(_sw)
        self.sw = _sw

    def _sub(self, **kw):
        base = {"id": 7, "nome": "X", "whatsapp": "5544999998888",
                "email": "", "plano": "mensal", "status": "ATIVO", "slot_envio": "12h"}
        base.update(kw)
        return base

    def _cont(self, **kw):
        base = {"07h": 0, "08h": 0, "12h": 0, "18h": 0, "20h": 0}
        base.update(kw)
        return base

    def test_coluna_horario_select_com_todos_e_atual(self):
        html = self.sw.pagina_admin([self._sub(slot_envio="12h")], token="tk",
                                     contagem_slots=self._cont(**{"12h": 1}))
        self.assertIn('name="acao" value="definir_slot"', html)
        self.assertIn('<option value="07h"', html)     # oferece todos os slots
        self.assertIn('<option value="20h"', html)
        self.assertIn('<option value="12h" selected', html)   # atual selecionado

    def test_resumo_por_horario(self):
        html = self.sw.pagina_admin([self._sub()], token="tk",
                                     contagem_slots=self._cont(**{"08h": 12}))
        self.assertIn("08h: 12", html)

    def test_sub_sem_slot_usa_default(self):
        html = self.sw.pagina_admin([self._sub(slot_envio=None)], token="tk",
                                     contagem_slots=self._cont())
        self.assertIn('<option value="08h" selected', html)   # SLOT_DEFAULT


if __name__ == "__main__":
    unittest.main()
