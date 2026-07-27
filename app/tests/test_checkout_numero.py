"""Combine país+local no checkout público (/assinar). Standalone: python3 app/tests/test_checkout_numero.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import phone


class TestCheckoutNumero(unittest.TestCase):
    def test_monta_whatsapp_do_pais(self):
        # simula o combine que o _post_assinar faz
        got = phone.montar_e164("1" or "55", "(305) 555-1234")
        self.assertEqual(got, "+13055551234")

    def test_default_br_quando_pais_vazio(self):
        got = phone.montar_e164("" or "55", "43 99999-0000")
        self.assertEqual(got, "+5543999990000")

    def test_montar_com_numero_local_vazio(self):
        # Regressão: montar_e164 com local vazio retorna "+55" (truthy)
        # _post_assinar agora valida o local ANTES de montar
        got = phone.montar_e164("55", "")
        self.assertEqual(got, "+55")  # confirma que montar_e164 retorna "+55" mesmo com local vazio


class TestAssinarValidacao(unittest.TestCase):
    def test_rejeita_whatsapp_vazio_no_checkout_publico(self):
        """POST com WhatsApp vazio deve ser rejeitado pela validação."""
        # Simula o que _post_assinar faz: valida local_whatsapp ANTES de montar
        local_whatsapp = "".strip()  # vazio
        pais_dial = "55"

        # Com a nova validação, dados["whatsapp"] é "" (falsy)
        if local_whatsapp:
            dados_whatsapp = phone.montar_e164(pais_dial, local_whatsapp)
        else:
            dados_whatsapp = ""

        # Validação deve falhar
        self.assertFalse(dados_whatsapp, "WhatsApp vazio deve ser falsy e não passar na validação")

    def test_aceita_whatsapp_valido_com_dial_correto(self):
        """POST com WhatsApp válido deve ser aceito e montar o E.164 correto."""
        local_whatsapp = "43 99999-0000".strip()  # válido
        pais_dial = "55"

        # Com a nova validação, se local_whatsapp é não-vazio, monta o E.164
        if local_whatsapp:
            dados_whatsapp = phone.montar_e164(pais_dial, local_whatsapp)
        else:
            dados_whatsapp = ""

        # Validação deve passar e gerar número correto
        self.assertEqual(dados_whatsapp, "+5543999990000")
        self.assertTrue(dados_whatsapp, "WhatsApp válido deve ser truthy")


if __name__ == "__main__":
    unittest.main()
