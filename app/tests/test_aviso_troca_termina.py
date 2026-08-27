"""Item 43 (parte A) — a tela "Trocando..." avisa sozinha quando a troca do estudo de
amanhã termina (sucesso com link novo, ou erro), sem precisar checar o WhatsApp.

O estado mora no MESMO rascunho já persistido em `daily_drafts` (`erro_troca`), sem
tabela nova: o token antigo SUMIR (sobrescrito pelo novo, upsert por `data`) é o sinal
de sucesso — mesmo mecanismo que já causa "Link inválido/expirado" hoje.
"""
import importlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DSCURSO_DATA", tempfile.mkdtemp())

_NODE = shutil.which("node")


class TestStatusTroca(unittest.TestCase):
    def setUp(self):
        import draft_store
        importlib.reload(draft_store)
        self.ds = draft_store

    def test_andamento_quando_rascunho_antigo_existe_sem_erro(self):
        with mock.patch.object(self.ds, "por_token", return_value={"data": "2026-08-27"}):
            r = self.ds.status_troca("tok-velho", "2026-08-27")
        self.assertEqual(r, {"status": "andamento"})

    def test_erro_quando_rascunho_antigo_tem_erro_troca(self):
        rascunho = {"data": "2026-08-27",
                    "erro_troca": "Não consegui trocar o estudo; o anterior segue valendo."}
        with mock.patch.object(self.ds, "por_token", return_value=rascunho):
            r = self.ds.status_troca("tok-velho", "2026-08-27")
        self.assertEqual(r, {"status": "erro",
                             "msg": "Não consegui trocar o estudo; o anterior segue valendo.",
                             "voltar": "/revisar/tok-velho"})

    def test_pronto_quando_rascunho_antigo_sumiu_e_ha_um_novo_na_data(self):
        atual = {"review_token": "tok-novo", "data": "2026-08-27"}
        with mock.patch.object(self.ds, "por_token", return_value=None), \
             mock.patch.object(self.ds, "carregar", return_value=atual):
            r = self.ds.status_troca("tok-velho", "2026-08-27")
        self.assertEqual(r, {"status": "pronto", "link": "/revisar/tok-novo"})

    def test_andamento_quando_nao_ha_rascunho_nenhum_ainda(self):
        """Caso extremo, praticamente inatingível pelo fluxo real (serve.py só chega
        aqui depois de confirmar que o rascunho existe) — nunca finge sucesso ou erro
        sem ter certeza."""
        with mock.patch.object(self.ds, "por_token", return_value=None), \
             mock.patch.object(self.ds, "carregar", return_value=None):
            r = self.ds.status_troca("tok-velho", "2026-08-27")
        self.assertEqual(r, {"status": "andamento"})

    def test_token_ou_data_vazios_nao_estouram(self):
        with mock.patch.object(self.ds, "por_token", return_value=None), \
             mock.patch.object(self.ds, "carregar", return_value=None):
            r = self.ds.status_troca("", "")
        self.assertEqual(r, {"status": "andamento"})


class TestIniciarTroca(unittest.TestCase):
    def setUp(self):
        import draft_store
        importlib.reload(draft_store)
        self.ds = draft_store

    def test_limpa_erro_anterior_e_salva(self):
        r = {"data": "2026-08-27", "erro_troca": "erro de uma tentativa anterior"}
        with mock.patch.object(self.ds, "salvar") as m_salvar:
            self.ds.iniciar_troca(r)
        self.assertEqual(r["erro_troca"], "")
        m_salvar.assert_called_once_with(r)

    def test_funciona_sem_erro_anterior(self):
        r = {"data": "2026-08-27"}
        with mock.patch.object(self.ds, "salvar") as m_salvar:
            self.ds.iniciar_troca(r)
        self.assertEqual(r["erro_troca"], "")
        m_salvar.assert_called_once_with(r)


class TestFalharTroca(unittest.TestCase):
    def setUp(self):
        import draft_store
        importlib.reload(draft_store)
        self.ds = draft_store

    def test_grava_mensagem_e_salva(self):
        r = {"data": "2026-08-27"}
        with mock.patch.object(self.ds, "salvar") as m_salvar:
            self.ds.falhar_troca(r, "deu ruim")
        self.assertEqual(r["erro_troca"], "deu ruim")
        m_salvar.assert_called_once_with(r)


if __name__ == "__main__":
    unittest.main()
