"""Regressão: gerar_pdf tenta de novo quando o Chromium crasha transitoriamente."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPdfRetry(unittest.TestCase):
    def test_retry_ate_dar_certo(self):
        import pdf
        out = os.path.join(tempfile.mkdtemp(), "o.pdf")
        calls = {"n": 0}

        def fake_run(cmd, **k):
            calls["n"] += 1
            if calls["n"] >= 2:                 # 1ª falha (não gera), 2ª gera o arquivo
                with open(out, "wb") as f:
                    f.write(b"x" * 2000)
            return None

        with mock.patch.object(pdf, "_chromium_bin", return_value="chromium"), \
             mock.patch.object(pdf.subprocess, "run", side_effect=fake_run):
            r = pdf.gerar_pdf("<html></html>", out, tentativas=3)
        self.assertEqual(r, out)
        self.assertGreaterEqual(calls["n"], 2)   # precisou tentar de novo

    def test_desiste_apos_tentativas(self):
        import pdf
        out = os.path.join(tempfile.mkdtemp(), "o.pdf")
        with mock.patch.object(pdf, "_chromium_bin", return_value="chromium"), \
             mock.patch.object(pdf.subprocess, "run", side_effect=RuntimeError("crash")):
            with self.assertRaises(RuntimeError):
                pdf.gerar_pdf("<html></html>", out, tentativas=2)


if __name__ == "__main__":
    unittest.main()
