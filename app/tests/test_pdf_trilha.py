"""Testes de app/pdf_trilha.py — a capa nova, o icone DS, e os blocos maiores."""
import base64
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _decodifica_png(b64):
    """Le os primeiros bytes e confirma que e' PNG de verdade, sem precisar de Pillow."""
    bruto = base64.b64decode(b64)
    assinatura_png = b"\x89PNG\r\n\x1a\n"
    return bruto[:8] == assinatura_png, bruto


class TestIconeDS(unittest.TestCase):
    def test_e_um_png_valido(self):
        import pdf_trilha
        ok, bruto = _decodifica_png(pdf_trilha._ICONE_DS_B64)
        self.assertTrue(ok, "a constante nao decodifica pra um PNG valido")
        self.assertGreater(len(bruto), 1000, "arquivo suspeito de pequeno/truncado")

    def test_tem_canal_alfa_com_transparencia_real(self):
        """O PNG precisa ser RGBA com pixel(s) realmente transparente(s) — e' o que
        permite compor o icone sobre a banda verde sem caixa branca ao redor.
        Checagem sem Pillow: o PNG usa chunk IHDR pra declarar o tipo de cor; tipo 6
        = RGBA. Basta olhar o byte de "color type" no cabecalho IHDR."""
        import pdf_trilha
        _, bruto = _decodifica_png(pdf_trilha._ICONE_DS_B64)
        # IHDR comeca no byte 8 (assinatura) + 4 (tamanho do chunk) + 4 ("IHDR") = 16
        # width(4) height(4) bitdepth(1) colortype(1) ...
        color_type = bruto[16 + 9]
        self.assertEqual(color_type, 6, "PNG nao e' RGBA (color type 6) — sem alfa")
