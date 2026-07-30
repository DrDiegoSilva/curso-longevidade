"""Testes do montador de payload do checkout Asaas (puro). Standalone.
Regras reais do Asaas: CARTÃO=RECURRENT (parcelável), PIX=DETACHED (à vista),
sem customerData (o checkout coleta), items com name<=30.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPayload(unittest.TestCase):
    def setUp(self):
        import config, asaas, pricing
        self.cfg, self.a, self.p = config, asaas, pricing
        self.dados = {"nome": "Dr. X", "cpf": "123.456.789-00", "email": "x@y.com", "whatsapp": "(43) 99999-0000"}

    def _plano(self, slug):
        return self.cfg.plano_por_slug(slug)

    def test_mensal_pix_avista(self):
        p = self.a.montar_checkout(self._plano("mensal"), "PIX", 1, self.dados, "tok1", "https://x")
        self.assertEqual(p["billingTypes"], ["PIX"])
        self.assertEqual(p["chargeTypes"], ["DETACHED"])          # Pix não recorre
        self.assertNotIn("subscription", p)
        self.assertEqual(p["items"][0]["value"], 147.0)
        self.assertEqual(p["externalReference"], "tok1")
        self.assertNotIn("customerData", p)                       # Asaas coleta

    def test_mensal_cartao_recorrente(self):
        p = self.a.montar_checkout(self._plano("mensal"), "CARTAO", 1, self.dados, "t", "https://x")
        self.assertEqual(p["billingTypes"], ["CREDIT_CARD"])
        self.assertEqual(p["chargeTypes"], ["RECURRENT"])
        self.assertEqual(p["subscription"]["cycle"], "MONTHLY")
        self.assertEqual(p["items"][0]["value"], self.p.valor_cartao(147.0, 1))
        self.assertNotIn("installmentCount", p)

    def test_anual_cartao_parcelado(self):
        """12x tem que virar PARCELAMENTO de verdade: `chargeTypes: ["INSTALLMENT"]`
        + objeto `installment`. O payload antigo mandava um `installmentCount` de 1º
        nível junto de `chargeTypes: ["RECURRENT"]` — campo que NÃO EXISTE no
        POST /checkouts: o Asaas ignorava o desconhecido, honrava o RECURRENT e
        cobrava o item CHEIO de uma vez. Venda real (2026-07-30): cliente escolheu
        12x e levou R$ 997 numa tacada em vez de 12x de R$ 83,08."""
        p = self.a.montar_checkout(self._plano("anual"), "CARTAO", 12, self.dados, "t", "https://x")
        self.assertEqual(p["chargeTypes"], ["INSTALLMENT"])
        self.assertEqual(p["installment"], {"maxInstallmentCount": 12})
        # Parcelado NÃO recorre — é o que a cláusula 3 dos termos promete.
        self.assertNotIn("subscription", p)
        base = self._plano("anual")["base"]
        self.assertEqual(p["items"][0]["value"], self.p.valor_cartao(base, 12))
        self.assertEqual(p["items"][0]["value"], base)             # sem juros: cobra o base

    def test_anual_cartao_avista_continua_assinatura(self):
        """1x é o ÚNICO cartão que recorre (cláusula 2 dos termos): segue RECURRENT
        com `subscription`, e sem objeto `installment` nenhum."""
        p = self.a.montar_checkout(self._plano("anual"), "CARTAO", 1, self.dados, "t", "https://x")
        self.assertEqual(p["chargeTypes"], ["RECURRENT"])
        self.assertEqual(p["subscription"]["cycle"], "YEARLY")
        self.assertNotIn("installment", p)

    def test_installment_count_nunca_sai_no_payload(self):
        """Trava de regressão do campo inventado. `installmentCount` de 1º nível não
        existe no POST /checkouts do Asaas; quem manda isso acha que parcelou e
        cobrou à vista, com a suíte verde. Não pode voltar em payload NENHUM."""
        for slug in ("mensal", "trimestral", "semestral", "anual"):
            for metodo in ("PIX", "CARTAO"):
                for n in (1, 6, 12):
                    p = self.a.montar_checkout(self._plano(slug), metodo, n, self.dados, "t", "https://x")
                    self.assertNotIn("installmentCount", p, f"{slug}/{metodo}/{n}x")

    def test_anual_pix_avista(self):
        p = self.a.montar_checkout(self._plano("anual"), "PIX", 1, self.dados, "t", "https://x")
        self.assertEqual(p["billingTypes"], ["PIX"])
        self.assertEqual(p["chargeTypes"], ["DETACHED"])
        self.assertEqual(p["items"][0]["value"], self._plano("anual")["base"])   # 1497 (PIX = base)
        self.assertNotIn("subscription", p)

    def test_pix_ignora_as_parcelas_que_chegarem(self):
        """Prova de que a tela pode ESCONDER o campo de parcelas no Pix sem desabilitar
        (2026-07-30): escondido-mas-habilitado, o campo continua submetendo `parcelas`
        junto de um pedido Pix. O payload do Pix tem que ser o MESMO com 1 ou 12 —
        nenhum installmentCount, valor à vista. Se algum dia o Pix passar a parcelar,
        este teste cai e a tela precisa voltar a mostrar o campo."""
        for slug in ("anual", "mensal"):
            um = self.a.montar_checkout(self._plano(slug), "PIX", 1, self.dados, "t", "https://x")
            doze = self.a.montar_checkout(self._plano(slug), "PIX", 12, self.dados, "t", "https://x")
            self.assertEqual(um, doze, slug)
            self.assertNotIn("installmentCount", doze)

    def test_item_nome_curto(self):
        for slug in ("mensal", "trimestral", "semestral", "anual"):
            p = self.a.montar_checkout(self._plano(slug), "PIX", 1, self.dados, "t", "https://x")
            self.assertLessEqual(len(p["items"][0]["name"]), 30)

    def test_success_url(self):
        p = self.a.montar_checkout(self._plano("mensal"), "PIX", 1, self.dados, "t", "https://artigos.x")
        self.assertEqual(p["callback"]["successUrl"], "https://artigos.x/obrigado")

    def test_montar_checkout_base_override(self):
        pix = self.a.montar_checkout(self._plano("anual"), "PIX", 1, self.dados, "t", "https://x", base=1497.0)
        self.assertEqual(pix["items"][0]["value"], 1497.0)
        card = self.a.montar_checkout(self._plano("anual"), "CARTAO", 12, self.dados, "t", "https://x", base=1497.0)
        self.assertEqual(card["items"][0]["value"], 1497.0)   # sem juros: cobra a base vigente

    def test_checkout_com_base_descontada(self):
        import asaas, config
        plano = config.plano_por_slug("anual")
        base_desc = 897.30
        # PIX (à vista): item sai com a base descontada
        p_pix = asaas.montar_checkout(plano, "PIX", 1, {}, "tok", "http://x", base=base_desc)
        self.assertEqual(p_pix["items"][0]["value"], 897.30)
        # CARTÃO (recorrente): 1ª cobrança com a base descontada
        p_card = asaas.montar_checkout(plano, "CARTAO", 1, {}, "tok", "http://x", base=base_desc)
        self.assertEqual(p_card["items"][0]["value"], 897.30)


if __name__ == "__main__":
    unittest.main()
