"""O corpus é MEMÓRIA — não pode virar o estudo que sai pro assinante.

Achado de revisão no commit `f1f46b1` (fatia 1 do item 33), reproduzido: `montar_alternativas`
(`daily.py:442`) chama `db.listar_candidatos("novo")` **sem filtro de `tipo`**, então todo
candidato de backfill (`tipo='corpus'`) aparece no picker do 🔁 "Trocar estudo" do /revisar.
Escolhido ali, `_preparar_de_candidato` gera o resumo e ele vira o estudo de amanhã — sai às
08h se o Diego não mexer. Um estudo de até 6 meses atrás, que nunca passou pela triagem
semanal, publicado na base paga.

Duas notas de escopo, verificadas no código:

- **A agenda NÃO tem esse buraco**: `materializar_agenda` (`daily.py:171`) já filtra
  `tipo="varredura"`. Nada entra sozinho; o vazamento exige o Diego escolher no picker.
- **O buraco é PRÉ-EXISTENTE e já valia pro `tipo='classico'`**: clássicos aparecem no
  picker rotulados como "candidato" e seriam preparados pelo caminho errado
  (`_preparar_de_candidato` regenera da abstract em vez de usar o resumo pronto). O
  backfill não criou o buraco — tornou-o perigoso em escala (cap 4x × 6 meses).
"""
import importlib
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DSCURSO_DATA", tempfile.mkdtemp())


def _cand(cid, tipo, tema="Obesidade", score=9):
    return {"id": cid, "tipo": tipo, "tema": tema, "titulo": f"Estudo {cid}",
            "fonte": "NEJM", "score": score, "abstract": "abs", "doi": "", "url": "", "data": ""}


class TestPickerSoOfereceVarredura(unittest.TestCase):
    def setUp(self):
        import daily
        importlib.reload(daily)
        self.daily = daily

    def _alts(self, candidatos):
        import db
        r = {"reserva_id": None, "candidato_id": None, "artigo": {"tema": "Obesidade"}}
        with mock.patch.object(db, "listar_reserva", return_value=[]), \
             mock.patch.object(db, "listar_candidatos",
                               side_effect=lambda *a, **k: [c for c in candidatos
                                                           if not k.get("tipo") or c["tipo"] == k["tipo"]]):
            return self.daily.montar_alternativas(r)

    def test_candidato_de_backfill_nao_aparece_no_picker(self):
        alts = self._alts([_cand("c1", "varredura"), _cand("bk", "corpus")])
        self.assertEqual([a["id"] for a in alts], ["c1"])

    def test_classico_tambem_nao_aparece_como_candidato(self):
        """Vazamento pré-existente: clássico tem caminho próprio (_preparar_de_classico)."""
        alts = self._alts([_cand("c1", "varredura"), _cand("cl", "classico")])
        self.assertEqual([a["id"] for a in alts], ["c1"])

    def test_o_candidato_normal_continua_sendo_oferecido(self):
        """A guarda não pode esvaziar o picker — ele é o item 23, que está no ar."""
        alts = self._alts([_cand("c1", "varredura"), _cand("c2", "varredura")])
        self.assertEqual(sorted(a["id"] for a in alts), ["c1", "c2"])

    def test_picker_so_com_corpus_fica_vazio_em_vez_de_oferecer_lixo(self):
        self.assertEqual(self._alts([_cand("bk", "corpus")]), [])


class TestGuardaDeValidacao(unittest.TestCase):
    """`alternativa_valida` é o portão que o serve.py consulta antes de trocar."""

    def setUp(self):
        import daily
        importlib.reload(daily)
        self.daily = daily

    def test_id_de_corpus_e_recusado_mesmo_forjado_no_form(self):
        import db
        r = {"reserva_id": None, "candidato_id": None, "artigo": {"tema": "Obesidade"}}
        with mock.patch.object(db, "listar_reserva", return_value=[]), \
             mock.patch.object(db, "listar_candidatos",
                               side_effect=lambda *a, **k: [_cand("bk", "corpus")]
                               if not k.get("tipo") else []):
            self.assertFalse(self.daily.alternativa_valida(r, "candidato", "bk"))


class TestPreparoRecusaCorpus(unittest.TestCase):
    """Defesa em profundidade: mesmo que alguém chame direto, o preparo recusa."""

    def setUp(self):
        import daily
        importlib.reload(daily)
        self.daily = daily

    def test_preparar_de_candidato_ignora_corpus(self):
        import db
        with mock.patch.object(db, "listar_candidatos",
                               side_effect=lambda *a, **k: [_cand("bk", "corpus")]
                               if not k.get("tipo") else []):
            self.assertIsNone(self.daily._preparar_de_candidato("bk"))

    def test_preparar_de_candidato_aceita_varredura(self):
        import db
        with mock.patch.object(db, "listar_candidatos",
                               side_effect=lambda *a, **k: [_cand("c1", "varredura")]), \
             mock.patch.object(self.daily, "_preparar_de_artigo", return_value={"x": 1}), \
             mock.patch.object(self.daily.draft_store, "salvar"):
            self.assertIsNotNone(self.daily._preparar_de_candidato("c1"))


class TestAgendaSegueFiltrando(unittest.TestCase):
    """A agenda escolhe SOZINHA, sem o Diego no meio — se ela deixar de filtrar, o corpus
    vira estudo do dia sem ninguém ver. É o caminho mais perigoso dos três.

    Teste de COMPORTAMENTO, não grep de fonte: `daily.py` tem duas chamadas
    `listar_candidatos(status="novo", tipo="varredura")` (linhas 144 e 172), então um grep
    passa mesmo com uma delas quebrada — foi assim que uma mutação sobreviveu.
    """

    def setUp(self):
        import importlib
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ.pop("DATABASE_URL", None)
        for m in ("config", "db", "queue_store", "daily"):
            importlib.reload(importlib.import_module(m))
        import daily, db
        self.daily, self.db = daily, db
        self.db.init()
        self.daily.reabastecer = lambda: 0          # sem rede no teste

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_candidato_de_corpus_nunca_e_agendado(self):
        from datetime import datetime, timedelta
        import agenda_plan as ap
        self.db.salvar_candidatos([{
            "tema": "Obesidade", "titulo": "BACKFILL ANTIGO", "fonte": "NEJM",
            "data": "2026-02-01", "doi": "10.1/bk", "url": "", "abstract": "abs",
            "pergunta": "", "score": 10, "chave": "bk-1", "citacoes": 0, "tipo": "corpus"}])
        datas = ap.dias_uteis_desde(datetime.now() + timedelta(days=1), 5,
                                    self.daily._dias_envio())
        self.daily.materializar_agenda(datas=datas)
        agendados = [a for d in datas for a in [self.db.agenda_slot(d)] if a]
        self.assertFalse([a for a in agendados if "BACKFILL" in (a.get("titulo") or "")])

    def test_corpus_nao_conta_como_estoque_pro_reabastecimento(self):
        """`cand_n` decide se a máquina sai pra buscar estudos novos. Contando o corpus,
        ela veria "estoque cheio" e PARARIA de reabastecer — a fila secaria em silêncio
        com centenas de abstracts que não servem pro envio diário."""
        from datetime import datetime, timedelta
        import agenda_plan as ap
        self.db.salvar_candidatos([{
            "tema": "Obesidade", "titulo": f"Backfill {i}", "fonte": "NEJM",
            "data": "2026-02-01", "doi": f"10.1/bk{i}", "url": "", "abstract": "abs",
            "pergunta": "", "score": 9, "chave": f"bk-{i}", "citacoes": 0, "tipo": "corpus"}
            for i in range(30)])
        chamou = []
        self.daily.reabastecer = lambda: chamou.append(1) or 0
        datas = ap.dias_uteis_desde(datetime.now() + timedelta(days=1), 5,
                                    self.daily._dias_envio())
        self.daily.materializar_agenda(datas=datas)
        self.assertTrue(chamou, "com a reserva vazia, 30 itens de corpus não podem "
                                "fazer a máquina achar que há estoque")

    def test_candidato_de_varredura_continua_sendo_agendado(self):
        """A guarda não pode esvaziar a agenda — é ela que sustenta o envio diário."""
        from datetime import datetime, timedelta
        import agenda_plan as ap
        self.db.salvar_candidatos([{
            "tema": "Obesidade", "titulo": "FRESCO DA SEMANA", "fonte": "NEJM",
            "data": "2026-08-01", "doi": "10.1/fr", "url": "", "abstract": "abs",
            "pergunta": "", "score": 10, "chave": "fr-1", "citacoes": 0, "tipo": "varredura"}])
        datas = ap.dias_uteis_desde(datetime.now() + timedelta(days=1), 5,
                                    self.daily._dias_envio())
        self.daily.materializar_agenda(datas=datas)
        agendados = [a for d in datas for a in [self.db.agenda_slot(d)] if a]
        self.assertTrue([a for a in agendados if "FRESCO" in (a.get("titulo") or "")])


class TestTravaDeReentrancia(unittest.TestCase):
    """Cada clique refaz busca + triagem (~100-150 chamadas Haiku). O dedup do banco
    protege os DADOS, não o custo — dois cliques gastavam dobrado."""

    def setUp(self):
        import curadoria
        importlib.reload(curadoria)
        self.c = curadoria

    def test_segunda_chamada_enquanto_a_primeira_roda_nao_faz_nada(self):
        """Reentra na própria função de dentro do `varrer_fn` — a trava é não-bloqueante,
        então isso reproduz o 2º clique sem depender de thread nem de tempo."""
        dentro = {}

        def varrer_fn(desde, ate, caps=None):
            if "r2" not in dentro:                  # só na 1ª janela
                dentro["r2"] = self.c.encorpar_corpus(
                    2, ate="2026-08-10", varrer_fn=lambda *a, **k: [],
                    salvar_fn=lambda c: 99)
            return []

        r1 = self.c.encorpar_corpus(2, ate="2026-08-10", varrer_fn=varrer_fn,
                                    salvar_fn=lambda c: 0)
        self.assertTrue(dentro["r2"]["ja_rodando"])
        self.assertEqual(dentro["r2"]["novos"], 0)   # não gravou nada
        self.assertFalse(r1.get("ja_rodando"))       # a 1ª seguiu normal

    def test_depois_de_terminar_pode_rodar_de_novo(self):
        """A trava é de concorrência, não do dia: se o container reiniciar no meio,
        o Diego tem que conseguir tentar de novo."""
        kw = dict(ate="2026-08-10", varrer_fn=lambda d, a, caps=None: [], salvar_fn=lambda c: 0)
        self.assertFalse(self.c.encorpar_corpus(1, **kw).get("ja_rodando"))
        self.assertFalse(self.c.encorpar_corpus(1, **kw).get("ja_rodando"))

    def test_a_trava_e_liberada_mesmo_se_explodir(self):
        def bomba(desde, ate, caps=None):
            raise KeyboardInterrupt("morreu feio")

        with self.assertRaises(KeyboardInterrupt):
            self.c.encorpar_corpus(1, ate="2026-08-10", varrer_fn=bomba, salvar_fn=lambda c: 0)
        r = self.c.encorpar_corpus(1, ate="2026-08-10",
                                   varrer_fn=lambda d, a, caps=None: [], salvar_fn=lambda c: 0)
        self.assertFalse(r.get("ja_rodando"))


if __name__ == "__main__":
    unittest.main()
