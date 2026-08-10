"""Parser de tabela de cano compartilhado (`tabela_pipe`).

Ele nasceu duplicado: o `pdf_trilha.py` sabia ler tabela e o `pdf.py` do estudo
diário não -- e o modelo escolheu tabela num estudo real, então o assinante
recebeu `| População | Proteína/dia |` impresso literal no PDF. Estes testes
travam o contrato do módulo único que os dois passam a usar.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _inline_asterisco_duplo(texto):
    """Marcação da trilha: `**negrito**`."""
    import html
    import re
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html.escape(texto, quote=True))


class TestDeteccao(unittest.TestCase):
    def setUp(self):
        import tabela_pipe
        self.t = tabela_pipe

    def test_linha_entre_canos_e_linha_de_tabela(self):
        self.assertTrue(self.t.eh_linha("| a | b |"))
        self.assertTrue(self.t.eh_linha("  | a | b |  "))

    def test_texto_comum_nao_e_linha_de_tabela(self):
        self.assertFalse(self.t.eh_linha("Populações especiais:"))
        self.assertFalse(self.t.eh_linha("| falta o cano final"))
        self.assertFalse(self.t.eh_linha(""))

    def test_bloco_com_separadora_na_segunda_linha_e_tabela(self):
        self.assertTrue(self.t.eh_tabela(["| a | b |", "|---|---|", "| 1 | 2 |"]))
        self.assertTrue(self.t.eh_tabela(["| a | b |", "| --- | :-: |"]))

    def test_bloco_sem_linha_separadora_nao_e_tabela(self):
        """Uma frase entre canos não pode virar tabela -- senão texto comum some
        dentro de um <table> de uma célula só."""
        self.assertFalse(self.t.eh_tabela(["| isto é só uma frase |"]))
        self.assertFalse(self.t.eh_tabela(["| a | b |", "| 1 | 2 |"]))


class TestRender(unittest.TestCase):
    LINHAS = ["| Item | Valor |", "| --- | --- |", "| Aluguel | R$ 100 |"]

    def setUp(self):
        import tabela_pipe
        self.t = tabela_pipe

    def test_vira_table_com_thead_e_tbody(self):
        h = self.t.html(self.LINHAS, _inline_asterisco_duplo)
        self.assertIn("<table>", h)
        self.assertIn("<thead>", h)
        self.assertIn("<tbody>", h)
        self.assertIn("<th>Item</th>", h)
        self.assertIn("<td>Aluguel</td>", h)

    def test_nenhum_cano_sobra_no_html(self):
        self.assertNotIn("|", self.t.html(self.LINHAS, _inline_asterisco_duplo))

    def test_marcacao_inline_entra_por_parametro(self):
        linhas = ["| Item | Valor |", "| --- | --- |", "| **Total** | R$ 100 |"]
        h = self.t.html(linhas, _inline_asterisco_duplo)
        self.assertIn("<strong>Total</strong>", h)
        self.assertNotIn("**", h)

    def test_escapa_html_dentro_da_celula(self):
        linhas = ["| Item | Valor |", "| --- | --- |",
                  "| <script>alert(1)</script> | R$ 1 |"]
        h = self.t.html(linhas, _inline_asterisco_duplo)
        self.assertNotIn("<script>", h)
        self.assertIn("&lt;script&gt;", h)

    def test_celula_numerica_alinha_a_direita_quando_ha_regra(self):
        h = self.t.html(self.LINHAS, _inline_asterisco_duplo,
                        num=lambda c: c.strip().startswith("R$"))
        self.assertIn('<td class="num">R$ 100</td>', h)
        self.assertIn("<td>Aluguel</td>", h)

    def test_sem_regra_de_numero_nenhuma_celula_ganha_classe(self):
        self.assertNotIn('class="num"', self.t.html(self.LINHAS, _inline_asterisco_duplo))

    def test_linha_com_menos_celulas_que_o_cabecalho_nao_explode(self):
        """Modelo às vezes emite linha torta; a tabela degrada em vez de levantar."""
        linhas = ["| a | b | c |", "|---|---|---|", "| 1 | 2 |"]
        h = self.t.html(linhas, _inline_asterisco_duplo)
        self.assertIn("<td>1</td>", h)
        self.assertIn("<td>2</td>", h)


if __name__ == "__main__":
    unittest.main()
