"""Regressão: PDF do preview (18h) falhando NÃO pode derrubar a preparação/revisão.
Bug real (2026-07-24): gerar_pdf sem try/except em _preparar_* abortava a preparação
e o curador não recebia a revisão -> nada era enviado às 08h."""
import importlib
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DSCURSO_DATA", tempfile.mkdtemp())


class TestPreparaPdfFalha(unittest.TestCase):
    def setUp(self):
        # reload p/ isolar da ordem de reloads dos outros testes do discover
        import daily
        importlib.reload(daily)
        self.daily = daily

    def test_pdf_falha_nao_derruba_preparo(self):
        daily = self.daily
        art = {"tema": "Obesidade", "titulo": "T", "fonte": "NEJM", "doi": "", "url": "", "data": "2026-01-01"}
        cap = {}

        def fake_novo(alvo, a, resumo, pdf_path):
            cap["pdf_path"] = pdf_path
            return {"review_token": "tok", "data": alvo}

        with mock.patch.object(daily.content, "gerar_conteudo",
                               return_value={"titulo_pt": "Tpt", "resumo": "r", "gancho": "g", "grafico": None}), \
             mock.patch.object(daily.pdfmod, "gerar_pdf", side_effect=RuntimeError("chromium crash")), \
             mock.patch.object(daily.draft_store, "novo_rascunho", side_effect=fake_novo), \
             mock.patch.object(daily.draft_store, "salvar"), \
             mock.patch.object(daily.deliver, "enviar_curador") as m_cur, \
             mock.patch.object(daily.subscribers, "ativos", return_value=[]), \
             mock.patch.object(daily, "enviar_audio_preview"):
            r = daily._preparar_de_artigo(art)          # NÃO deve levantar apesar do PDF quebrar

        self.assertIn("pdf_path", cap)                   # novo_rascunho foi chamado (mock pegou)
        self.assertIsNone(cap["pdf_path"])              # rascunho ficou sem PDF (preview=None)
        m_cur.assert_called_once()                       # curador AINDA foi avisado
        self.assertEqual(r["review_token"], "tok")


if __name__ == "__main__":
    unittest.main()
