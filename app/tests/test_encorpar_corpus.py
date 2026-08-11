"""Item 33, fatia 1 — encorpar o corpus antes de pedir opinião a ele.

A varredura semanal entrou em 2026-07-25: são ~2-3 domingos, ~25-30 estudos por tema.
Pedir "o que a base sabe sobre Lipedema" com 25 abstracts nasce pobre — e aí o Diego
julga a IDEIA errada por causa do MATERIAL.

Dois achados que desenham esta fatia:

1. **O gargalo não é a janela de busca, são os CAPS.** `rodar_varredura` já busca desde
   `2026-01-01`, mas `varrer` guarda só `cap` por tema (Obesidade 20 … Lipedema 6). A
   triagem por IA JÁ RODOU em tudo que veio — o cap só decide o que é SALVO. Guardar mais
   do que já foi triado é quase de graça.

2. **Corpus não é fila de triagem.** A aba Triagem lista `tipo='varredura'`
   (`montar_candidatos_triagem`). Se o backfill entrasse como 'varredura', a tela que o
   Diego acabou de pedir pra desentulhar ganharia centenas de itens. Backfill entra como
   `tipo='corpus'`: alimenta a memória, não aparece na triagem.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _art(titulo, score=8):
    return {"titulo": titulo, "resumo": "abstract " * 40, "fonte": "NEJM",
            "doi": f"10.1/{titulo}", "url": "", "data": "2026-03-01", "score": score}


class TestJanelas(unittest.TestCase):
    def setUp(self):
        import curadoria
        self.c = curadoria

    def test_uma_janela_por_mes_para_tras(self):
        js = self.c._janelas_mensais(3, ate="2026-08-10")
        self.assertEqual(len(js), 3)
        for desde, ate in js:
            self.assertLess(desde, ate)

    def test_a_primeira_janela_termina_hoje(self):
        js = self.c._janelas_mensais(2, ate="2026-08-10")
        self.assertEqual(js[0][1], "2026-08-10")

    def test_as_janelas_nao_se_sobrepoem_nem_deixam_buraco(self):
        js = self.c._janelas_mensais(4, ate="2026-08-10")
        for mais_nova, mais_velha in zip(js, js[1:]):
            self.assertEqual(mais_velha[1], mais_nova[0])   # encosta, não sobrepõe

    def test_vao_do_mais_novo_pro_mais_velho(self):
        js = self.c._janelas_mensais(3, ate="2026-08-10")
        self.assertGreater(js[0][0], js[-1][0])

    def test_zero_ou_negativo_nao_gera_janela(self):
        self.assertEqual(self.c._janelas_mensais(0, ate="2026-08-10"), [])
        self.assertEqual(self.c._janelas_mensais(-3, ate="2026-08-10"), [])

    def test_atravessa_a_virada_do_ano(self):
        js = self.c._janelas_mensais(3, ate="2026-01-15")
        self.assertTrue(any(d.startswith("2025-") for d, _ in js))


class TestEncorpar(unittest.TestCase):
    def setUp(self):
        import curadoria
        self.c = curadoria

    def test_varre_uma_vez_por_janela(self):
        chamadas = []

        def varrer_fn(desde, ate, caps=None):
            chamadas.append((desde, ate))
            return [_art(f"a-{desde}")]

        r = self.c.encorpar_corpus(3, ate="2026-08-10", varrer_fn=varrer_fn,
                                   salvar_fn=lambda c: len(c))
        self.assertEqual(len(chamadas), 3)
        self.assertEqual(r["janelas"], 3)

    def test_tudo_que_entra_e_marcado_como_corpus(self):
        """Sem isto o backfill entope a aba Triagem, que lista tipo='varredura'."""
        salvos = []
        self.c.encorpar_corpus(2, ate="2026-08-10",
                               varrer_fn=lambda d, a, caps=None: [_art("x"), _art("y")],
                               salvar_fn=lambda c: salvos.extend(c) or len(c))
        self.assertTrue(salvos)
        self.assertTrue(all(s["tipo"] == "corpus" for s in salvos))

    def test_conta_os_novos_que_o_banco_aceitou(self):
        """O dedup mora no `salvar_candidatos` (ON CONFLICT DO NOTHING) — a contagem tem
        que vir de lá, não do que foi tentado."""
        r = self.c.encorpar_corpus(2, ate="2026-08-10",
                                   varrer_fn=lambda d, a, caps=None: [_art("x")] * 5,
                                   salvar_fn=lambda c: 1)      # banco só aceitou 1 por janela
        self.assertEqual(r["novos"], 2)

    def test_usa_caps_maiores_que_os_da_varredura_semanal(self):
        """A varredura semanal alimenta a FILA (1 estudo/dia). O corpus quer volume."""
        vistos = {}
        self.c.encorpar_corpus(1, ate="2026-08-10",
                               varrer_fn=lambda d, a, caps=None: vistos.update(caps or {}) or [],
                               salvar_fn=lambda c: 0)
        self.assertTrue(vistos)
        for tema, cap in vistos.items():
            self.assertGreater(cap, self.c.CAPS.get(tema, 0), f"{tema} não ganhou cap maior")

    def test_janela_que_explode_nao_derruba_as_outras(self):
        """Uma falha de rede em 1 mês não pode perder o backfill inteiro."""
        vezes = []

        def varrer_fn(desde, ate, caps=None):
            vezes.append(desde)
            if len(vezes) == 2:                 # a 2ª janela cai, seja qual for a data
                raise RuntimeError("epmc fora do ar")
            return [_art("ok")]

        r = self.c.encorpar_corpus(3, ate="2026-08-10", varrer_fn=varrer_fn,
                                   salvar_fn=lambda c: len(c))
        self.assertEqual(r["falhas"], 1)
        self.assertEqual(r["novos"], 2)

    def test_janela_sem_resultado_nao_chama_o_banco(self):
        chamou = []
        self.c.encorpar_corpus(2, ate="2026-08-10",
                               varrer_fn=lambda d, a, caps=None: [],
                               salvar_fn=lambda c: chamou.append(c) or 0)
        self.assertEqual(chamou, [])

    def test_nao_gasta_ia_gerando_pergunta_de_triagem(self):
        """A `pergunta` serve pra tela de triagem, e o corpus não passa por ela.
        Gerar seria pagar Haiku por texto que ninguém lê."""
        salvos = []
        self.c.encorpar_corpus(1, ate="2026-08-10",
                               varrer_fn=lambda d, a, caps=None: [_art("x")],
                               salvar_fn=lambda c: salvos.extend(c) or len(c))
        self.assertFalse(salvos[0].get("pergunta"))


if __name__ == "__main__":
    unittest.main()
