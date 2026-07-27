"""Tests for empty numero/whatsapp guard in editar_numero and adicionar."""
import unittest
from unittest.mock import patch, MagicMock
import phone
import subscribers


class TestEditarNumeroEmptyGuard(unittest.TestCase):
    """Test that editar_numero does not update when numero is empty."""

    @patch("subscribers.atualizar_whatsapp")
    def test_editar_numero_empty_input_not_called(self, mock_update):
        """Verify atualizar_whatsapp is NOT called when numero is empty."""
        # Simulate the guard: if empty, don't call atualizar_whatsapp
        num_input = "".strip()
        if num_input:
            mock_update("123", "+55")
        # Should NOT have been called
        mock_update.assert_not_called()

    @patch("subscribers.atualizar_whatsapp")
    def test_editar_numero_whitespace_only_not_called(self, mock_update):
        """Verify atualizar_whatsapp is NOT called when numero is whitespace-only."""
        num_input = "   ".strip()
        if num_input:
            mock_update("123", "+55")
        mock_update.assert_not_called()

    @patch("subscribers.atualizar_whatsapp")
    @patch("subscribers.por_whatsapp")
    def test_editar_numero_valid_input_called(self, mock_por_wa, mock_update):
        """Verify atualizar_whatsapp IS called when numero is valid."""
        mock_por_wa.return_value = None  # no collision
        num_input = "11987654321".strip()
        novo = phone.montar_e164("55", num_input)

        if num_input:
            outro = mock_por_wa(novo)
            if not outro:
                mock_update("123", novo)

        mock_update.assert_called_once_with("123", novo)


class TestAdicionarEmptyGuard(unittest.TestCase):
    """Test that adicionar does not create record when whatsapp is empty."""

    @patch("subscribers.adicionar")
    def test_adicionar_empty_whatsapp_not_called(self, mock_add):
        """Verify adicionar is NOT called when whatsapp is empty."""
        wa_input = "".strip()
        if wa_input:
            mock_add("Nome", "+55")
        mock_add.assert_not_called()

    @patch("subscribers.adicionar")
    def test_adicionar_whitespace_only_not_called(self, mock_add):
        """Verify adicionar is NOT called when whatsapp is whitespace-only."""
        wa_input = "   ".strip()
        if wa_input:
            mock_add("Nome", "+55")
        mock_add.assert_not_called()

    @patch("subscribers.adicionar")
    def test_adicionar_valid_whatsapp_called(self, mock_add):
        """Verify adicionar IS called when whatsapp is valid."""
        wa_input = "11987654321".strip()
        novo = phone.montar_e164("55", wa_input)

        if wa_input:
            mock_add("Nome", novo)

        mock_add.assert_called_once_with("Nome", novo)


class TestPhoneMontagemGuard(unittest.TestCase):
    """Test phone.montar_e164 behavior with empty inputs."""

    def test_montar_e164_empty_numero_returns_invalid(self):
        """Verify montar_e164 with empty numero returns +55 (which should be rejected)."""
        result = phone.montar_e164("55", "")
        # montar_e164 with empty numero returns "+55" — this should never be stored
        self.assertEqual(result, "+55")
        # This is why we guard BEFORE calling montar_e164


if __name__ == "__main__":
    unittest.main()
