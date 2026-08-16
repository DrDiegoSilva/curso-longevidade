"""Conferência do nosso ledger contra a fatura real (Admin API da Anthropic).

Este é o único ponto da entrega que não dá pra testar contra o serviço real — eu não tenho
a chave de admin do Diego. Por isso ele é um módulo isolado, com o contrato copiado da
documentação, e a tela nomeia em qual estado ele está.
Standalone: python3 app/tests/test_anthropic_admin.py"""
import importlib
import os
import sys
import unittest
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _bucket(dia, *amounts):
    """Um balde diário como a API devolve. `amount` vem em CENTAVOS, como string."""
    return {"starting_at": f"{dia}T00:00:00Z", "ending_at": f"{dia}T23:59:59Z",
            "results": [{"amount": a, "currency": "USD"} for a in amounts]}


def _resposta(buckets, has_more=False, next_page=None):
    return {"data": buckets, "has_more": has_more, "next_page": next_page}


class _Base(unittest.TestCase):
    def setUp(self):
        self.snap = os.environ.get("DSCURSO_ANTHROPIC_ADMIN_KEY")
        os.environ["DSCURSO_ANTHROPIC_ADMIN_KEY"] = "sk-ant-admin-teste"
        import config, anthropic_admin
        importlib.reload(config)
        importlib.reload(anthropic_admin)
        self.aa = anthropic_admin

    def tearDown(self):
        if self.snap is None:
            os.environ.pop("DSCURSO_ANTHROPIC_ADMIN_KEY", None)
        else:
            os.environ["DSCURSO_ANTHROPIC_ADMIN_KEY"] = self.snap
        import config
        importlib.reload(config)


class TestCentavos(_Base):
    def test_amount_vem_em_CENTAVOS_e_vira_dolar(self):
        """A doc diz: "123.45" em USD representa US$ 1,23. Sem dividir por 100 a tela
        mostraria 100x o gasto real — plausível o bastante pro Diego acreditar."""
        self.aa._get = lambda url, chave: _resposta([_bucket("2026-08-14", "123.45")])
        r = self.aa.custo_por_dia("2026-08-01")
        self.assertEqual(r["estado"], "ok")
        self.assertAlmostEqual(r["dias"]["2026-08-14"], 1.2345)

    def test_varios_itens_no_mesmo_dia_somam(self):
        self.aa._get = lambda url, chave: _resposta(
            [_bucket("2026-08-14", "100.00", "50.00")])
        r = self.aa.custo_por_dia("2026-08-01")
        self.assertAlmostEqual(r["dias"]["2026-08-14"], 1.5)

    def test_dia_com_custo_zero_aparece_na_tabela_com_a_chave(self):
        """O dia foi lido (a API devolveu o balde, mesmo sem `results`) e custou zero —
        diferente de um dia que nunca apareceu na fatura. A chave PRECISA existir com 0.0;
        ausência de chave significaria 'não temos leitura desse dia', que é outra coisa."""
        self.aa._get = lambda url, chave: _resposta([_bucket("2026-08-14")])
        r = self.aa.custo_por_dia("2026-08-01")
        self.assertIn("2026-08-14", r["dias"])
        self.assertEqual(r["dias"]["2026-08-14"], 0.0)

    def test_amount_invalido_nao_derruba_o_resto_mas_marca_parcial(self):
        self.aa._get = lambda url, chave: _resposta(
            [_bucket("2026-08-14", "nao-e-numero", "100.00")])
        r = self.aa.custo_por_dia("2026-08-01")
        self.assertAlmostEqual(r["dias"]["2026-08-14"], 1.0)
        self.assertEqual(r["estado"], "ok")
        self.assertTrue(r["parcial"], "amount descartado precisa avisar leitura incompleta")


class TestPaginacao(_Base):
    def test_segue_o_next_page_ate_o_fim(self):
        """Fatura com muitos dias vem paginada; parar na 1ª página esconderia gasto."""
        paginas = [_resposta([_bucket("2026-08-14", "100.00")], has_more=True,
                             next_page="cursor2"),
                   _resposta([_bucket("2026-08-15", "200.00")])]
        vistos = []

        def _get(url, chave):
            vistos.append(url)
            return paginas.pop(0)

        self.aa._get = _get
        r = self.aa.custo_por_dia("2026-08-01")
        self.assertEqual(sorted(r["dias"]), ["2026-08-14", "2026-08-15"])
        self.assertIn("cursor2", vistos[1])
        self.assertFalse(r["parcial"], "leitura completa (a API disse has_more=False) não é parcial")

    def test_mesmo_dia_em_duas_paginas_soma_em_vez_de_sobrescrever(self):
        """Improvável pela paginação documentada (bucket_width=1d não deveria repetir dia
        entre páginas), mas se acontecer, perder o valor da 1ª página é a mesma classe de
        erro do amount ilegível: número silenciosamente errado."""
        paginas = [_resposta([_bucket("2026-08-14", "100.00")], has_more=True,
                             next_page="cursor2"),
                   _resposta([_bucket("2026-08-14", "50.00")])]
        self.aa._get = lambda url, chave: paginas.pop(0)
        r = self.aa.custo_por_dia("2026-08-01")
        self.assertAlmostEqual(r["dias"]["2026-08-14"], 1.5)

    def test_nao_gira_para_sempre_se_a_api_insistir_em_has_more(self):
        """Defesa contra laço infinito: a página de admin não pode travar o servidor. Mas o
        teto corta uma fatura de verdade quando ela tem mais de MAX_PAGINAS baldes — isso
        precisa avisar via `parcial`, não sair como se fosse a fatura inteira."""
        self.aa._get = lambda url, chave: _resposta([_bucket("2026-08-14", "1.00")],
                                                    has_more=True, next_page="sempre")
        r = self.aa.custo_por_dia("2026-08-01")
        self.assertEqual(r["estado"], "ok")
        self.assertTrue(r["parcial"], "teto de páginas com has_more ainda verdadeiro é leitura truncada")


class TestEstados(_Base):
    def test_sem_chave_configurada(self):
        os.environ.pop("DSCURSO_ANTHROPIC_ADMIN_KEY", None)
        import config
        importlib.reload(config)
        importlib.reload(self.aa)
        r = self.aa.custo_por_dia("2026-08-01")
        self.assertEqual(r["estado"], "sem_chave")
        self.assertEqual(r["dias"], {})
        self.assertFalse(r["parcial"], "sem leitura nenhuma, não houve leitura parcial")

    def test_401_vira_recusada(self):
        def _get(url, chave):
            raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)
        self.aa._get = _get
        r = self.aa.custo_por_dia("2026-08-01")
        self.assertEqual(r["estado"], "recusada")
        self.assertFalse(r["parcial"])

    def test_403_tambem_vira_recusada(self):
        def _get(url, chave):
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
        self.aa._get = _get
        self.assertEqual(self.aa.custo_por_dia("2026-08-01")["estado"], "recusada")

    def test_500_vira_erro(self):
        def _get(url, chave):
            raise urllib.error.HTTPError(url, 500, "Server Error", {}, None)
        self.aa._get = _get
        self.assertEqual(self.aa.custo_por_dia("2026-08-01")["estado"], "erro")

    def test_rede_fora_vira_erro_e_nao_levanta(self):
        def _get(url, chave):
            raise OSError("sem rede")
        self.aa._get = _get
        r = self.aa.custo_por_dia("2026-08-01")
        self.assertEqual(r["estado"], "erro")
        self.assertEqual(r["dias"], {})
        self.assertFalse(r["parcial"])

    def test_resposta_com_formato_inesperado_vira_erro_em_vez_de_explodir(self):
        """Se o contrato mudar (ou eu tiver lido errado), a tela precisa dizer isso."""
        self.aa._get = lambda url, chave: {"isso": "não é o contrato"}
        r = self.aa.custo_por_dia("2026-08-01")
        self.assertIn(r["estado"], ("ok", "erro"))
        self.assertEqual(r["dias"], {})
        self.assertFalse(r["parcial"])


class TestRequisicao(_Base):
    def test_manda_bucket_diario_e_a_data_inicial(self):
        vistos = []
        self.aa._get = lambda url, chave: vistos.append(url) or _resposta([])
        self.aa.custo_por_dia("2026-08-01")
        self.assertIn("bucket_width=1d", vistos[0])
        self.assertIn("2026-08-01", vistos[0])

    def test_chave_sk_ant_vai_no_header_x_api_key(self):
        h = self.aa._headers("sk-ant-admin-abc")
        self.assertEqual(h.get("x-api-key"), "sk-ant-admin-abc")
        self.assertNotIn("Authorization", h)

    def test_token_que_nao_e_sk_ant_vai_como_bearer(self):
        """A doc exemplifica com Bearer; chaves de admin históricas usam x-api-key. Sem a
        chave do Diego não dá pra saber qual é a dele — escolhemos pelo formato, e o estado
        'recusada' cobre o caso de termos escolhido errado."""
        h = self.aa._headers("oauth-abc")
        self.assertEqual(h.get("Authorization"), "Bearer oauth-abc")
        self.assertNotIn("x-api-key", h)

    def test_manda_a_versao_da_api(self):
        self.assertEqual(self.aa._headers("sk-ant-x").get("anthropic-version"), "2023-06-01")


if __name__ == "__main__":
    unittest.main()
