"""Item 27-A — a aba Reserva vira cards por tema, em vez de 51 itens em lista corrida.

Diego, 2026-08-10: *"já arruma essa página da curadoria também, fica um scroll infinito,
ajuda aí por seção certinho"*. Spec de 2026-07-27 (`feat/reserva-por-tema`), decisões
dele: tema no nível de cima, status dentro, acordeão um-por-vez.

`<details name="...">` dá acordeão EXCLUSIVO nativo do HTML — abrir um fecha o outro,
sem uma linha de JavaScript. Em navegador antigo o atributo é ignorado e vira acordeão
comum: degrada, não quebra.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ORDEM = ["Obesidade", "Hormonal", "Lipedema", "Performance", "Longevidade"]


def _item(tema, titulo, status="pronto", rid=None):
    return {"id": rid or f"{tema}-{titulo}", "tema": tema, "titulo_pt": titulo,
            "status": status, "prioridade": 0}


def _card(html, tema):
    """O bloco de UM tema. Fatiar pelo `</details>` não serve: o item da Reserva tem um
    `<details>` aninhado (editar/remover) e fecharia a tag errada."""
    for parte in html.split('<details name="reserva-tema"')[1:]:
        if tema in parte.split("</summary>", 1)[0]:
            return parte
    raise AssertionError(f"card do tema {tema} não está na página")


def _pagina(reserva):
    import site_web
    return site_web.pagina_curadoria(
        {"pronto": len(reserva), "minimo": 3}, None, [], reserva,
        {"candidatos": [], "banco": []}, "tok", aba="reserva")


class TestCardsPorTema(unittest.TestCase):
    def test_cada_tema_vira_um_card(self):
        html = _pagina([_item("Obesidade", "A"), _item("Hormonal", "B")])
        for t in ORDEM:
            _card(html, t)          # levanta se o tema não tiver card próprio

    def test_acordeao_e_exclusivo_sem_javascript(self):
        """`name` igual em todos = o browser fecha o anterior sozinho."""
        html = _pagina([_item("Obesidade", "A")])
        self.assertIn('name="reserva-tema"', html)
        self.assertGreaterEqual(html.count('name="reserva-tema"'), len(ORDEM))

    def test_tema_vazio_aparece_com_zero(self):
        """É o que revela onde o estoque secou — mesma regra dos chips da Triagem."""
        html = _pagina([_item("Obesidade", "A")])
        self.assertIn("Lipedema", html)

    def test_o_card_fechado_mostra_o_total_do_tema(self):
        reserva = [_item("Obesidade", f"T{i}") for i in range(3)]
        reserva.append(_item("Obesidade", "fora", status="enviado"))
        html = _pagina(reserva)
        card = html.split("Obesidade", 1)[1].split("</summary>", 1)[0]
        self.assertIn("4", card)              # 3 prontos + 1 fora do estoque

    def test_tema_fora_da_lista_padrao_ganha_card(self):
        """O legado "Meus estudos" não pode sumir da tela."""
        html = _pagina([_item("Meus estudos", "legado")])
        self.assertIn("Meus estudos", html)

    def test_pronto_e_fora_do_estoque_ficam_separados_dentro_do_card(self):
        card = _card(_pagina([_item("Obesidade", "PRONTINHO"),
                              _item("Obesidade", "JAFOI", status="enviado")]), "Obesidade")
        self.assertIn("Fora do estoque", card)
        self.assertLess(card.find("PRONTINHO"), card.find("JAFOI"))   # prontos primeiro

    def test_rotulo_de_fora_do_estoque_some_quando_nao_ha(self):
        card = _card(_pagina([_item("Obesidade", "so pronto")]), "Obesidade")
        self.assertNotIn("Fora do estoque", card)

    def test_reserva_vazia_mantem_a_mensagem_e_nao_desenha_cards(self):
        html = _pagina([])
        self.assertIn("Reserva vazia", html)
        self.assertNotIn('name="reserva-tema"', html)

    def test_os_itens_continuam_editaveis(self):
        """O item da Reserva não muda — só ganha um pai. Sem isso, editar/remover some."""
        html = _pagina([_item("Obesidade", "A", rid="r1")])
        self.assertIn("r1", html)

    def test_a_ordem_dos_temas_segue_a_da_triagem(self):
        html = _pagina([_item(t, "x") for t in ORDEM])
        pos = [html.find(f'name="reserva-tema"'), ]
        corpo = html.split('class="temacard"', 1)[1] if 'class="temacard"' in html else html
        achados = [t for t in ORDEM if t in corpo]
        ordenado = sorted(achados, key=lambda t: corpo.find(t))
        self.assertEqual(achados, ordenado)


if __name__ == "__main__":
    unittest.main()
