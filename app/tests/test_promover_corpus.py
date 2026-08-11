"""O corpus não pode ENGOLIR um estudo que depois vira clássico ou fresco da semana.

Diego, 2026-08-11, depois de apertar os botões: *"pedi pra ele varrer os clássicos tbm"* —
e na ordem em que ele clicou (backfill do corpus ANTES da varredura de clássicos), o
problema aparece.

As três varreduras escrevem na MESMA tabela (`curadoria_candidatos`) e o dedup é por
`chave` (doi→url→título) com `ON CONFLICT DO NOTHING`. Um paper que o backfill já guardou
como `tipo='corpus'` faz a varredura seguinte ser silenciosamente ignorada — o registro
fica como corpus e **nunca aparece na aba Clássicos nem na Triagem**
(`montar_candidatos_triagem` filtra por tipo).

`corpus` é a classificação de MENOR valor: é só memória, não passou por triagem semanal
nem por ranking de citações. Achado posterior como `varredura` (fresco, triado) ou
`classico` (marco, muito citado) vale mais e tem que promover o registro.

O caminho contrário NÃO vale: um backfill posterior não pode rebaixar um clássico já
aprovado a mera memória.
"""
import importlib
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _cand(tipo, titulo="Estudo X", pergunta="", score=5, citacoes=0):
    return {"tema": "Obesidade", "titulo": titulo, "fonte": "NEJM", "data": "2026-03-01",
            "doi": "10.1/mesmo", "url": "", "abstract": "abs", "pergunta": pergunta,
            "score": score, "chave": "10.1/mesmo", "citacoes": citacoes, "tipo": tipo}


class TestPromocaoDoCorpus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import db as _db
        importlib.reload(_db)
        self.db = _db
        self.db.init()

    def _tipo(self):
        return self.db.listar_candidatos()[0]["tipo"]

    def test_classico_promove_um_registro_de_corpus(self):
        """O caso do Diego: backfill primeiro, clássicos depois."""
        self.db.salvar_candidatos([_cand("corpus")])
        self.db.salvar_candidatos([_cand("classico", citacoes=900)])
        self.assertEqual(self._tipo(), "classico")

    def test_varredura_semanal_tambem_promove(self):
        self.db.salvar_candidatos([_cand("corpus")])
        self.db.salvar_candidatos([_cand("varredura", score=9)])
        self.assertEqual(self._tipo(), "varredura")

    def test_promover_traz_os_dados_da_varredura_que_valem(self):
        """O backfill NÃO gera pergunta (economia). Sem trazer a da varredura, o estudo
        aparece na aba sem a pergunta que serve pro Diego decidir rápido."""
        self.db.salvar_candidatos([_cand("corpus")])
        self.db.salvar_candidatos([_cand("classico", pergunta="Vale mudar conduta?",
                                         score=8, citacoes=900)])
        r = self.db.listar_candidatos()[0]
        self.assertEqual(r["pergunta"], "Vale mudar conduta?")
        self.assertEqual(r["citacoes"], 900)
        self.assertEqual(r["score"], 8)

    def test_backfill_nao_rebaixa_um_classico(self):
        """Caminho contrário: quem já é clássico não vira mera memória."""
        self.db.salvar_candidatos([_cand("classico", citacoes=900)])
        self.db.salvar_candidatos([_cand("corpus")])
        self.assertEqual(self._tipo(), "classico")

    def test_backfill_nao_rebaixa_uma_varredura(self):
        self.db.salvar_candidatos([_cand("varredura", score=9)])
        self.db.salvar_candidatos([_cand("corpus")])
        self.assertEqual(self._tipo(), "varredura")

    def test_varredura_nao_vira_classico_nem_o_contrario(self):
        """Só o corpus é promovível. Entre os outros dois, o primeiro manda — mexer aí
        embaralharia a aba Triagem com a aba Clássicos."""
        self.db.salvar_candidatos([_cand("varredura", score=9)])
        self.db.salvar_candidatos([_cand("classico", citacoes=900)])
        self.assertEqual(self._tipo(), "varredura")

    def test_backfill_repetido_nao_apaga_as_tags_que_custaram_IA(self):
        """Corpus→corpus não é promoção: não pode sobrescrever nada.

        `curadoria.backfill_tags` usa `listar_candidatos()` SEM filtro de tipo, então o
        botão "🏷️ Etiquetar estudos" também etiqueta o corpus. Um segundo "Encorpar a
        base" manda `tags: []` — sem a guarda de `excluded.tipo<>'corpus'`, ele apagaria
        etiquetas que já custaram chamadas de IA."""
        import json
        self.db.salvar_candidatos([_cand("corpus")])
        cid = self.db.listar_candidatos()[0]["id"]
        self.db.atualizar_tags("candidato", cid, ["glp1", "massa magra"])
        self.db.salvar_candidatos([_cand("corpus")])          # 2º backfill, tags vazias
        self.assertEqual(json.loads(self.db.listar_candidatos()[0]["tags"]),
                         ["glp1", "massa magra"])

    def test_nao_duplica_o_registro(self):
        self.db.salvar_candidatos([_cand("corpus")])
        self.db.salvar_candidatos([_cand("classico")])
        self.assertEqual(len(self.db.listar_candidatos()), 1)

    def test_promocao_nao_conta_como_novo(self):
        """A contagem que vai pra tela é "quantos NOVOS entraram" — promover não é novo,
        e inflar o número faria o Diego achar que a varredura trouxe mais do que trouxe."""
        self.db.salvar_candidatos([_cand("corpus")])
        self.assertEqual(self.db.salvar_candidatos([_cand("classico")]), 0)

    def test_estudo_inedito_continua_entrando_normalmente(self):
        n = self.db.salvar_candidatos([_cand("varredura", titulo="Novo em folha")])
        self.assertEqual(n, 1)
        self.assertEqual(self._tipo(), "varredura")

    def test_promover_nao_mexe_no_status(self):
        """Se o registro já foi triado (selecionado/agendado), promover o tipo não pode
        jogá-lo de volta pra fila de novos."""
        self.db.salvar_candidatos([_cand("corpus")])
        cid = self.db.listar_candidatos()[0]["id"]
        self.db.marcar_candidatos([cid], "selecionado")
        self.db.salvar_candidatos([_cand("classico")])
        self.assertEqual(self.db.listar_candidatos()[0]["status"], "selecionado")


if __name__ == "__main__":
    unittest.main()
