"""Regerar o KIT dos estudos parados na reserva.

Diego, 2026-08-11, sobre o PDF do dia: *"ele voltou pro padrão dos ganchos anteriores"*.

Não é bug de renderização: o kit inteiro (frase, bloco do paciente, pautas com roteiro)
fica gravado no campo `gancho` do estudo, no dia em que ele entrou na reserva. Estudo
gerado ANTES das melhorias do kit carrega o kit velho pra sempre — o `parse_gancho` até
documenta isso: *"o estoque de reserva_resumos está cheio destes"* (formato com `angulo`,
**sem roteiro**).

Limpeza não resolve: não é texto sobrando, é conteúdo que nunca foi gerado. Só regerando.

Custa uma chamada Sonnet por estudo (~50 na fila), então:
- só regenera o que está DESATUALIZADO de fato (o discriminador é o roteiro/paciente);
- preserva `resumo`, `titulo_pt` e `grafico` — o Diego já curou esse texto;
- roda em thread com trava, como o backfill do corpus.
"""
import importlib
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

KIT_VELHO = json.dumps({"frase": "uma frase", "reels": [{"titulo": "T", "angulo": "A"}]})
KIT_NOVO = json.dumps({
    "frase": "uma frase", "paciente": "explico assim ao paciente", "limites": ["x"],
    "reels": [{"titulo": "T", "gancho": "G", "roteiro": ["a", "b"], "apoio": "NEJM"}]})


class TestDiscriminador(unittest.TestCase):
    """Sem isto o botão gasta ~50 chamadas Sonnet regerando kit que já está bom."""

    def setUp(self):
        import curadoria
        importlib.reload(curadoria)
        self.c = curadoria

    def test_kit_sem_roteiro_e_desatualizado(self):
        self.assertTrue(self.c.kit_desatualizado(KIT_VELHO))

    def test_kit_completo_nao_e_desatualizado(self):
        self.assertFalse(self.c.kit_desatualizado(KIT_NOVO))

    def test_kit_vazio_ou_texto_legado_e_desatualizado(self):
        for bruto in ("", None, "null", "gancho em texto puro do legado"):
            with self.subTest(bruto=bruto):
                self.assertTrue(self.c.kit_desatualizado(bruto))

    def test_kit_com_paciente_mas_SEM_roteiro_e_desatualizado(self):
        """O formato #2 do `parse_gancho` — o que o docstring diz que enche o estoque:
        pauta com `angulo` no lugar do roteiro. Como pode vir COM bloco do paciente, é a
        checagem do roteiro que precisa pegá-lo (o `KIT_VELHO` dos outros testes falha nas
        duas checagens e mascarava esta)."""
        so_angulo = json.dumps({"frase": "f", "paciente": "explico assim", "limites": [],
                                "reels": [{"titulo": "T", "angulo": "A"}]})
        self.assertTrue(self.c.kit_desatualizado(so_angulo))

    def test_kit_com_roteiro_mas_sem_bloco_do_paciente_e_desatualizado(self):
        """O bloco do paciente entrou junto do roteiro; faltando um, o PDF sai capenga."""
        meio = json.dumps({"frase": "f", "reels": [
            {"titulo": "T", "gancho": "G", "roteiro": ["a"], "apoio": ""}]})
        self.assertTrue(self.c.kit_desatualizado(meio))

    def test_json_quebrado_nao_explode(self):
        """Roda sobre o estoque inteiro — um registro podre não pode abortar o lote."""
        self.assertTrue(self.c.kit_desatualizado('{"reels": [{'))


class TestRegerarKits(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import db as _db
        importlib.reload(_db)
        self.db = _db
        self.db.init()
        import curadoria
        importlib.reload(curadoria)
        self.c = curadoria

    def _reserva(self, gancho, titulo="T", resumo="resumo curado"):
        return self.db.salvar_reserva({"tema": "Obesidade", "titulo_pt": titulo,
                                       "resumo": resumo, "gancho": gancho,
                                       "fonte": "NEJM", "doi": "10.1/x"})

    def test_so_regenera_o_que_esta_desatualizado(self):
        velho = self._reserva(KIT_VELHO, titulo="Velho")
        novo = self._reserva(KIT_NOVO, titulo="Novo")
        chamados = []
        r = self.c.regerar_kits(gerar_fn=lambda a: chamados.append(a) or KIT_NOVO)
        self.assertEqual(r["regerados"], 1)
        self.assertEqual(len(chamados), 1)                  # 1 chamada de IA, não 2
        self.assertIn("roteiro", self.db.obter_reserva(velho)["gancho"])
        self.assertEqual(self.db.obter_reserva(novo)["gancho"], KIT_NOVO)

    def test_preserva_o_texto_que_o_diego_curou(self):
        rid = self._reserva(KIT_VELHO, titulo="Título curado", resumo="RESUMO CURADO")
        self.c.regerar_kits(gerar_fn=lambda a: KIT_NOVO)
        r = self.db.obter_reserva(rid)
        self.assertEqual(r["titulo_pt"], "Título curado")
        self.assertEqual(r["resumo"], "RESUMO CURADO")

    def test_o_gerador_recebe_o_estudo_pra_trabalhar(self):
        self._reserva(KIT_VELHO, titulo="Tirzepatida e massa magra")
        vistos = []
        self.c.regerar_kits(gerar_fn=lambda a: vistos.append(a) or KIT_NOVO)
        self.assertIn("Tirzepatida", json.dumps(vistos[0], ensure_ascii=False))

    def test_um_estudo_que_falha_nao_derruba_o_lote(self):
        self._reserva(KIT_VELHO, titulo="A")
        self._reserva(KIT_VELHO, titulo="B")

        def gerar_fn(a):
            if "A" == a.get("titulo_pt"):
                raise RuntimeError("IA fora do ar")
            return KIT_NOVO

        r = self.c.regerar_kits(gerar_fn=gerar_fn)
        self.assertEqual(r["falhas"], 1)
        self.assertEqual(r["regerados"], 1)

    def test_resposta_inutil_da_ia_nao_apaga_o_kit_que_existia(self):
        """Kit velho é melhor que kit nenhum: gravar lixo pioraria o PDF."""
        rid = self._reserva(KIT_VELHO)
        r = self.c.regerar_kits(gerar_fn=lambda a: "desculpe, não consegui")
        self.assertEqual(r["regerados"], 0)
        self.assertEqual(self.db.obter_reserva(rid)["gancho"], KIT_VELHO)

    def test_rodar_de_novo_nao_regenera_nada(self):
        self._reserva(KIT_VELHO)
        self.assertEqual(self.c.regerar_kits(gerar_fn=lambda a: KIT_NOVO)["regerados"], 1)
        self.assertEqual(self.c.regerar_kits(gerar_fn=lambda a: KIT_NOVO)["regerados"], 0)

    def test_limite_segura_o_gasto(self):
        for i in range(5):
            self._reserva(KIT_VELHO, titulo=f"T{i}")
        r = self.c.regerar_kits(limite=2, gerar_fn=lambda a: KIT_NOVO)
        self.assertEqual(r["regerados"], 2)

    def test_reserva_vazia_nao_explode(self):
        self.assertEqual(self.c.regerar_kits(gerar_fn=lambda a: KIT_NOVO),
                         {"regerados": 0, "falhas": 0, "ja_rodando": False})

    def test_segunda_chamada_simultanea_nao_roda(self):
        """Mesma trava do backfill: cada disparo custa ~50 chamadas Sonnet."""
        self._reserva(KIT_VELHO)
        dentro = {}

        def gerar_fn(a):
            dentro.setdefault("r2", self.c.regerar_kits(gerar_fn=lambda x: KIT_NOVO))
            return KIT_NOVO

        self.c.regerar_kits(gerar_fn=gerar_fn)
        self.assertTrue(dentro["r2"]["ja_rodando"])
        self.assertEqual(dentro["r2"]["regerados"], 0)


if __name__ == "__main__":
    unittest.main()
