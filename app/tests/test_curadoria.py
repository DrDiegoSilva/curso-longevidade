"""Testes da lógica de curadoria (varredura + geração de resumo com fns injetáveis,
sem rede/IA). Standalone: python3 app/tests/test_curadoria.py"""
import os
import sys
import hashlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import curadoria


def _fake_buscar(query, desde, ate):
    """5 artigos ÚNICOS por tema (a chave varia com a query do tema)."""
    h = hashlib.md5(query.encode()).hexdigest()[:4]
    return [{"titulo": f"T-{h}-{i}", "doi": f"10.1/{h}{i}", "resumo": "z" * 200,
             "fonte": "NEJM", "data": f"2026-02-{i+1:02d}"} for i in range(5)]


def _fake_triar(arts, tema):
    out = []
    for i, a in enumerate(arts):
        a = dict(a); a["tema"] = tema; a["score"] = 10 - i     # já em ordem desc
        out.append(a)
    return out


class TestVarrer(unittest.TestCase):
    def test_cap_por_tema_com_peso_obesidade(self):
        caps = {"Obesidade": 3, "Hormonal": 1, "Lipedema": 1, "Performance": 1, "Longevidade": 1}
        cands = curadoria.varrer("2026-01-01", "2026-07-19", caps=caps,
                                 buscar_fn=_fake_buscar, triar_fn=_fake_triar)
        por_tema = {}
        for c in cands:
            por_tema[c["tema"]] = por_tema.get(c["tema"], 0) + 1
        self.assertEqual(por_tema.get("Obesidade"), 3)   # peso maior respeitado
        self.assertEqual(por_tema.get("Hormonal"), 1)
        self.assertEqual(len(cands), 3 + 1 + 1 + 1 + 1)

    def test_ordena_por_score_dentro_do_tema(self):
        caps = {k: 2 for k in ("Obesidade", "Hormonal", "Lipedema", "Performance", "Longevidade")}
        cands = curadoria.varrer("2026-01-01", "2026-07-19", caps=caps,
                                 buscar_fn=_fake_buscar, triar_fn=_fake_triar)
        obes = [c for c in cands if c["tema"] == "Obesidade"]
        self.assertEqual([c["score"] for c in obes], [10.0, 9.0])   # pegou os 2 de maior score

    def test_dedup_global_por_chave(self):
        # busca que devolve SEMPRE os mesmos 2 artigos p/ todo tema -> dedup entre temas
        def buscar_igual(q, d, a):
            return [{"titulo": "X", "doi": "10.1/x", "resumo": "z" * 200, "fonte": "BMJ", "data": "2026-03-01"},
                    {"titulo": "Y", "doi": "10.1/y", "resumo": "z" * 200, "fonte": "BMJ", "data": "2026-03-02"}]
        cands = curadoria.varrer("2026-01-01", "2026-07-19", caps={k: 9 for k in
                                 ("Obesidade", "Hormonal", "Lipedema", "Performance", "Longevidade")},
                                 buscar_fn=buscar_igual, triar_fn=_fake_triar)
        self.assertEqual(len(cands), 2)   # x e y aparecem uma vez só, apesar dos 5 temas

    def test_normalizacao_campos(self):
        cands = curadoria.varrer("2026-01-01", "2026-07-19", caps={"Obesidade": 1},
                                 buscar_fn=_fake_buscar, triar_fn=_fake_triar)
        c = cands[0]
        for campo in ("tema", "titulo", "fonte", "data", "doi", "url", "abstract", "score", "chave"):
            self.assertIn(campo, c)
        self.assertTrue(c["chave"])                         # chave de dedup não vazia
        self.assertIsInstance(c["score"], float)

    def test_chave_normaliza(self):
        self.assertEqual(curadoria._chave({"doi": "10.1/AbC"}), "10.1/abc")
        self.assertEqual(curadoria._chave({"url": "http://X"}), "http://x")
        self.assertEqual(curadoria._chave({"titulo": " Um Título "}), "um título")
        self.assertEqual(curadoria._chave({}), "")


class TestPerguntas(unittest.TestCase):
    """Haiku (barato) gera, p/ cada candidato, a PERGUNTA clínica que ele responde."""
    def test_atribui_pergunta_por_indice(self):
        cands = [{"titulo": "A", "abstract": "x" * 50}, {"titulo": "B", "abstract": "y" * 50}]
        fake = lambda p: '[{"i":0,"pergunta":"A dose alta funciona?"},{"i":1,"pergunta":"O exercício ajuda?"}]'
        out = curadoria.gerar_perguntas(cands, llm_fn=fake)
        self.assertEqual(out[0]["pergunta"], "A dose alta funciona?")
        self.assertEqual(out[1]["pergunta"], "O exercício ajuda?")

    def test_json_ruim_nao_explode(self):
        cands = [{"titulo": "A", "abstract": "x" * 50}]
        out = curadoria.gerar_perguntas(cands, llm_fn=lambda p: "sem json aqui")
        self.assertEqual(out[0]["pergunta"], "")            # falha graciosa

    def test_lista_vazia(self):
        self.assertEqual(curadoria.gerar_perguntas([], llm_fn=lambda p: "[]"), [])


class TestGerarResumo(unittest.TestCase):
    """Resumo final dos SELECIONADOS segue o padrão de qualidade do app (gerador normal)."""
    def test_gera_estrutura_padrao(self):
        c = curadoria.gerar_resumo(
            {"titulo": "Study", "abstract": "abstract " * 30, "fonte": "NEJM", "doi": "10.1/z", "data": "2026-02-01"},
            gerar_resumo=lambda a: "🗓️ *fev/2026* · resumo clínico",
            gerar_gancho=lambda a: "Gancho de rede",
            gerar_grafico_json=lambda a: '{"titulo":"Perda","unidade":"%","barras":[{"rotulo":"A","valor":10},{"rotulo":"B","valor":3}]}',
            gerar_titulo=lambda a: "Título em português")
        self.assertEqual(c["titulo_pt"], "Título em português")
        self.assertIn("resumo clínico", c["resumo"])
        self.assertEqual(c["gancho"], "Gancho de rede")
        self.assertEqual(c["grafico"]["barras"][0]["rotulo"], "A")

    def test_mapeia_abstract_para_resumo(self):
        # o gerador recebe o artigo com 'resumo' preenchido a partir do 'abstract' do candidato
        visto = {}
        curadoria.gerar_resumo(
            {"titulo": "S", "abstract": "TEXTO-DO-ABSTRACT", "fonte": "BMJ"},
            gerar_resumo=lambda a: visto.setdefault("resumo_in", a.get("resumo")) or "ok",
            gerar_gancho=lambda a: "g", gerar_grafico_json=lambda a: "null", gerar_titulo=lambda a: "t")
        self.assertEqual(visto["resumo_in"], "TEXTO-DO-ABSTRACT")


class TestAdicionarMeuEstudo(unittest.TestCase):
    def setUp(self):
        import tempfile, importlib
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        for m in ("config", "db", "curadoria"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import db, curadoria as cur2
        importlib.reload(db); importlib.reload(cur2)
        self.db, self.cur = db, cur2
        db.init()

    def test_entra_na_fila_com_prioridade(self):
        rid, tit = self.cur.adicionar_meu_estudo(
            "texto integral do estudo em PDF...", titulo="Meu PDF", fonte="NEJM", doi="10.1/meu",
            triar_fn=lambda arts, tema: [],
            gerar_resumo=lambda a: "resumo clínico", gerar_gancho=lambda a: "gancho",
            gerar_grafico_json=lambda a: "null", gerar_titulo=lambda a: "Título PT do meu estudo")
        self.assertEqual(tit, "Título PT do meu estudo")
        fila = self.db.listar_reserva(status="pronto")
        self.assertEqual(len(fila), 1)
        self.assertEqual(fila[0]["prioridade"], 1)
        self.assertEqual(fila[0]["origem"], "manual")
        self.assertEqual(self.db.proximo_da_reserva()["id"], rid)     # fura a fila

    def test_abstract_do_texto_vai_pro_gerador(self):
        visto = {}
        self.cur.adicionar_meu_estudo(
            "CONTEUDO-DO-PDF", titulo="X", triar_fn=lambda arts, tema: [],
            gerar_resumo=lambda a: visto.setdefault("r", a.get("resumo")) or "ok",
            gerar_gancho=lambda a: "g", gerar_grafico_json=lambda a: "null", gerar_titulo=lambda a: "t")
        self.assertEqual(visto["r"], "CONTEUDO-DO-PDF")

    def test_triagem_pontua_o_manual(self):
        # a IA de triagem (mesma da varredura) dá a nota do manual — ele entra na
        # fila por qualidade, não só furando por prioridade cega.
        _, tit = self.cur.adicionar_meu_estudo(
            "texto integral do estudo em PDF...", titulo="Meu PDF", fonte="NEJM", doi="10.1/meu",
            triar_fn=lambda arts, tema: [{"score": 9}],
            gerar_resumo=lambda a: "resumo clínico", gerar_gancho=lambda a: "gancho",
            gerar_grafico_json=lambda a: "null", gerar_titulo=lambda a: "Título PT")
        self.assertEqual(tit, "Título PT")
        fila = self.db.listar_reserva(status="pronto")
        self.assertEqual(fila[0]["score"], 9.0)

    def test_triagem_lixo_usa_nota_padrao_7(self):
        # LIXO (ou triagem que não devolve nada) não pode zerar o manual — o Diego
        # escolheu 7 como piso padrão pra ele ainda competir na fila.
        self.cur.adicionar_meu_estudo(
            "texto integral do estudo em PDF...", titulo="Meu PDF",
            triar_fn=lambda arts, tema: [],
            gerar_resumo=lambda a: "resumo clínico", gerar_gancho=lambda a: "gancho",
            gerar_grafico_json=lambda a: "null", gerar_titulo=lambda a: "Título PT")
        fila = self.db.listar_reserva(status="pronto")
        self.assertEqual(fila[0]["score"], 7.0)


class TestVarrerClassicos(unittest.TestCase):
    def test_ordena_por_citacoes_e_marca_tipo(self):
        def fake_buscar(query, desde, ate):
            return [
                {"titulo": "Menos citado", "doi": "d1", "citacoes": 100, "resumo": "x" * 200},
                {"titulo": "Marco", "doi": "d2", "citacoes": 5000, "resumo": "y" * 200},
            ]
        def fake_triar(arts, tema):
            # tudo ENTRA, score fixo; preserva citacoes
            return [dict(a, tema=tema, score=7) for a in arts]
        got = curadoria.varrer_classicos(caps={"Obesidade": 20, "Hormonal": 0, "Performance": 0,
                                               "Longevidade": 0, "Lipedema": 0},
                                        buscar_fn=fake_buscar, triar_fn=fake_triar, anos=10)
        obes = [c for c in got if c["tema"] == "Obesidade"]
        self.assertEqual(obes[0]["titulo"], "Marco")          # mais citado primeiro
        self.assertEqual(obes[0]["tipo"], "classico")
        self.assertEqual(obes[0]["citacoes"], 5000)


class TestPiso(unittest.TestCase):
    def test_corta_abaixo_do_piso_quando_ha_fartura(self):
        bons = [{"score": 9}, {"score": 8}, {"score": 7}, {"score": 3}, {"score": 2}]
        out = curadoria.aplicar_piso(bons, piso=6, min_por_tema=3)
        self.assertEqual([b["score"] for b in out], [9, 8, 7])

    def test_valvula_afrouxa_quando_tema_seco(self):
        # só 1 acima do piso, mas min_por_tema=3 -> entrega os 3 melhores mesmo abaixo
        bons = [{"score": 9}, {"score": 4}, {"score": 3}]
        out = curadoria.aplicar_piso(bons, piso=6, min_por_tema=3)
        self.assertEqual([b["score"] for b in out], [9, 4, 3])

    def test_tema_vazio_continua_vazio(self):
        self.assertEqual(curadoria.aplicar_piso([], piso=6, min_por_tema=3), [])

    def test_score_ausente_conta_como_zero(self):
        out = curadoria.aplicar_piso([{"titulo": "x"}], piso=6, min_por_tema=0)
        self.assertEqual(out, [])

    def test_varrer_aplica_o_piso(self):
        # _fake_triar dá scores 10,9,8,7,6 por tema; piso=8 e min=1 deixa só 10,9,8
        out = curadoria.varrer("2026-01-01", "2026-03-01",
                               caps={"Obesidade": 99}, buscar_fn=_fake_buscar,
                               triar_fn=_fake_triar, piso=8, min_por_tema=1)
        obes = [c for c in out if c["tema"] == "Obesidade"]
        self.assertEqual(len(obes), 3)
        self.assertTrue(all(c["score"] >= 8 for c in obes))

    def test_varrer_classicos_ignora_o_piso(self):
        # clássicos ranqueiam por citações — o piso de nota não pode cortá-los.
        # Para provar isso, usamos um triar_fn que devolve scores **abaixo** do piso default (6).
        def fake_triar_com_score_baixo(arts, tema):
            """Mesma estrutura de _fake_triar, mas com score 2 (abaixo do piso=6)."""
            out = []
            for i, a in enumerate(arts):
                a = dict(a); a["tema"] = tema; a["score"] = 2; a["citacoes"] = 5000 - i * 100
                out.append(a)
            return out
        out = curadoria.varrer_classicos(caps={"Obesidade": 3}, buscar_fn=_fake_buscar,
                                         triar_fn=fake_triar_com_score_baixo)
        # Se o piso estivesse aplicado, todos os clássicos teriam sido cortados (score 2 < piso 6).
        # Mas varrer_classicos ignora o piso, então devem estar presentes.
        obes = [c for c in out if c["tema"] == "Obesidade"]
        self.assertEqual(len(obes), 3)
        self.assertTrue(all(c["score"] == 2 for c in obes))


class TestGerarRoteia(unittest.TestCase):
    def test_classico_vai_pro_banco(self):
        chamados = {"classico": 0, "reserva": 0}
        regs_reserva = []
        class FakeDB:
            def init(self): pass
            def listar_candidatos(self, status=None):
                return [{"id": "c1", "tema": "Obesidade", "tipo": "classico", "titulo": "STEP",
                         "abstract": "z" * 300, "citacoes": 4000, "doi": "d", "fonte": "f", "url": "u", "data": "2021-01-01"},
                        {"id": "c2", "tema": "Hormonal", "tipo": "varredura", "titulo": "Novo",
                         "abstract": "w" * 300, "doi": "d2", "fonte": "f", "url": "u", "data": "2026-07-01",
                         "score": 8.5}]
            def salvar_classico(self, reg): chamados["classico"] += 1; return "k"
            def salvar_reserva(self, reg): chamados["reserva"] += 1; regs_reserva.append(reg); return "r"
            def marcar_candidatos(self, ids, status): pass
        import curadoria
        curadoria.gerar_selecionados(db_mod=FakeDB(),
                                     gerar_resumo_fn=lambda c: {"titulo_pt": "T", "resumo": "R", "gancho": "", "grafico": None})
        self.assertEqual(chamados, {"classico": 1, "reserva": 1})
        # regressão: a nota (score) do candidato triado precisa chegar na reserva —
        # sem ela, a fila usava prioridade=0 pra todo mundo e a curadoria ficava soterrada.
        self.assertEqual(regs_reserva[0]["score"], 8.5)


if __name__ == "__main__":
    unittest.main()
