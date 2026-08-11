"""O picker do 🔁 "Trocar estudo" agrupado por tema, igual à aba Reserva.

Diego, 2026-08-11: *"na troca de estudos do dia, ele aparece parece que uma lista fixa
somente, qual lista que aparece lá?"* — e depois: *"pode fazer, agrupa por tema igual a
reserva"*.

**Por que parecia fixa:** a lista é reserva (`pronto`) + candidatos crus da varredura,
cortada em 20. A reserva tem ~50 itens e come as 20 vagas sozinha, então **os candidatos
crus nunca apareciam** — e como a reserva gira 1 estudo por dia, o topo era literalmente
o mesmo todo dia.

Agrupando por tema o corte deixa de ser decisão de UX e vira só rede de segurança: o
Diego abre o tema que quer e vê o que há nele.
"""
import importlib
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DSCURSO_DATA", tempfile.mkdtemp())

AREAS = ["Obesidade", "Hormonal", "Lipedema", "Performance", "Longevidade"]


def _alt(tipo, id_, tema, titulo, score=5):
    return {"tipo": tipo, "id": id_, "tema": tema, "titulo": titulo,
            "fonte": "NEJM", "score": score}


class TestEmojiVemDaConfig(unittest.TestCase):
    """O mapa de emoji estava duplicado no `site_web`; a fonte é o `temas_config.json`,
    que o `area_estudo` já lê. Duplicata é onde os dois divergem sem ninguém ver."""

    def setUp(self):
        import area_estudo
        importlib.reload(area_estudo)
        self.ae = area_estudo

    def test_cada_area_tem_o_emoji_QUE_ESTA_na_config(self):
        """`assertTrue` não bastava: o fallback "•" também é truthy, então uma função que
        ignorasse a config passava no teste."""
        import json
        import os
        caminho = os.path.join(os.path.dirname(__file__), "..", "temas_config.json")
        with open(caminho, encoding="utf-8") as f:
            temas = json.load(f)["temas"]
        for a in AREAS:
            self.assertEqual(self.ae.emoji(a), temas[a]["emoji"], f"{a} com emoji errado")
            self.assertNotEqual(self.ae.emoji(a), "•")

    def test_tema_desconhecido_ganha_marcador_neutro(self):
        self.assertEqual(self.ae.emoji("Meus estudos"), "•")

    def test_config_ilegivel_nao_derruba(self):
        with mock.patch("builtins.open", side_effect=OSError("sumiu")):
            self.assertEqual(self.ae.emoji("Obesidade"), "•")


class TestPickerAgrupado(unittest.TestCase):
    def setUp(self):
        import review_web
        importlib.reload(review_web)
        self.rw = review_web

    def _html(self, alts):
        r = {"artigo": {"titulo": "Atual", "tema": "Obesidade"}}
        return self.rw.pagina_trocar_estudo(alts, r, "tok", areas=AREAS)

    def _card(self, html, tema):
        for parte in html.split('<details name="troca-tema"')[1:]:
            if tema in parte.split("</summary>", 1)[0]:
                return parte
        raise AssertionError(f"card do tema {tema} não está na página")

    def test_cada_tema_vira_um_card(self):
        html = self._html([_alt("reserva", "r1", "Obesidade", "A"),
                           _alt("candidato", "c1", "Hormonal", "B")])
        for t in AREAS:
            self._card(html, t)

    def test_acordeao_exclusivo_sem_javascript(self):
        html = self._html([_alt("reserva", "r1", "Obesidade", "A")])
        self.assertGreaterEqual(html.count('name="troca-tema"'), len(AREAS))

    def test_o_card_mostra_quantos_tem_no_tema(self):
        html = self._html([_alt("reserva", f"r{i}", "Obesidade", f"E{i}") for i in range(4)])
        self.assertIn("4", self._card(html, "Obesidade").split("</summary>", 1)[0])

    def test_o_botao_de_usar_continua_em_cada_item(self):
        """Sem isso o picker vira vitrine e o Diego não consegue trocar nada."""
        card = self._card(self._html([_alt("reserva", "r1", "Obesidade", "A")]), "Obesidade")
        self.assertIn('name="acao" value="trocar_confirmar"', card)
        self.assertIn('value="reserva"', card)
        self.assertIn('value="r1"', card)

    def test_o_tema_de_amanha_abre_sozinho(self):
        """O estudo de amanhã é de Obesidade — é esse card que ele quer ver primeiro."""
        html = self._html([_alt("reserva", "r1", "Obesidade", "A")])
        self.assertIn("open", self._card(html, "Obesidade").split("</summary>", 1)[0])

    def test_tema_sem_alternativa_aparece_vazio_em_vez_de_sumir(self):
        html = self._html([_alt("reserva", "r1", "Obesidade", "A")])
        self.assertIn("Lipedema", html)

    def test_tema_fora_da_lista_padrao_ganha_card(self):
        html = self._html([_alt("reserva", "r1", "Meus estudos", "Upload")])
        self.assertIn("Meus estudos", html)

    def test_sem_alternativa_nenhuma_mantem_a_mensagem(self):
        self.assertIn("Sem outros estudos", self._html([]))

    def test_diz_a_origem_de_cada_item(self):
        """Reserva já tem resumo pronto; candidato cru vai ser gerado na hora. São coisas
        diferentes e o Diego precisa distinguir antes de escolher."""
        card = self._card(self._html([_alt("reserva", "r1", "Obesidade", "Pronto"),
                                      _alt("candidato", "c1", "Obesidade", "Cru")]),
                          "Obesidade")
        self.assertIn("Pronto", card)
        self.assertIn("Cru", card)
        self.assertIn("reserva", card)
        self.assertIn("candidato", card)


class TestOCorteNaoEscondeMaisOsCandidatos(unittest.TestCase):
    def setUp(self):
        import daily
        importlib.reload(daily)
        self.daily = daily

    def test_candidato_cru_aparece_mesmo_com_a_reserva_cheia(self):
        """O bug do "lista fixa": 50 na reserva x corte em 20 = candidato nunca aparecia."""
        import db
        reserva = [{"id": f"r{i}", "titulo_pt": f"Reserva {i}", "fonte": "NEJM",
                    "tema": "Obesidade", "prioridade": 0, "score": 5} for i in range(50)]
        cands = [{"id": "c1", "titulo": "Candidato cru", "fonte": "Lancet",
                  "tema": "Hormonal", "score": 9}]
        r = {"reserva_id": None, "candidato_id": None, "artigo": {"tema": "Obesidade"}}
        with mock.patch.object(db, "listar_reserva", return_value=reserva), \
             mock.patch.object(db, "listar_candidatos", return_value=cands):
            alts = self.daily.montar_alternativas(r)
        self.assertIn("c1", [a["id"] for a in alts])

    def test_ainda_ha_um_teto_de_seguranca(self):
        import db
        reserva = [{"id": f"r{i}", "titulo_pt": f"R{i}", "fonte": "N", "tema": "Obesidade",
                    "prioridade": 0, "score": 5} for i in range(999)]
        r = {"reserva_id": None, "candidato_id": None, "artigo": {"tema": "Obesidade"}}
        with mock.patch.object(db, "listar_reserva", return_value=reserva), \
             mock.patch.object(db, "listar_candidatos", return_value=[]):
            alts = self.daily.montar_alternativas(r)
        self.assertLess(len(alts), 999)


if __name__ == "__main__":
    unittest.main()
