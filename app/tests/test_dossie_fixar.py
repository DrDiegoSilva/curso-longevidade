"""Item 33, parte B — o bloco do dossiê que o Diego corrige vira DELE.

A armadilha que define o desenho: o dossiê é reconstruído do zero, então edição manual
crua seria apagada na reconstrução seguinte, sem aviso. Por isso a preservação mora no
GRAVADOR (`salvar_dossie`), não em quem reconstrói — nenhum caminho futuro consegue perder
o texto dele escrevendo errado. Standalone: python3 app/tests/test_dossie_fixar.py"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _snapshot_env():
    return (os.environ.get("DSCURSO_ARTIGOS_DB"), os.environ.get("DATABASE_URL"))


def _reload_db(tmp):
    os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(tmp, "t.db")
    os.environ.pop("DATABASE_URL", None)
    import importlib, db as _db
    importlib.reload(_db)
    _db.init()
    return _db


def _restore_db(snap):
    import importlib
    a, d = snap
    if a is None:
        os.environ.pop("DSCURSO_ARTIGOS_DB", None)
    else:
        os.environ["DSCURSO_ARTIGOS_DB"] = a
    if d is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = d
    import db as _db
    importlib.reload(_db)


def _bloco(afirmacao, titulo="Estudo A"):
    return {"afirmacao": afirmacao,
            "estudos": [{"titulo": titulo, "fonte": "NEJM", "data": "2026-03"}]}


class _Base(unittest.TestCase):
    def setUp(self):
        self.snap = _snapshot_env()
        self.tmp = tempfile.mkdtemp()
        self.db = _reload_db(self.tmp)

    def tearDown(self):
        _restore_db(self.snap)
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestIdsNosBlocos(_Base):
    def test_bloco_sem_id_ganha_um_ao_salvar(self):
        self.db.salvar_dossie("Obesidade", {"blocos": [_bloco("GLP-1 reduz peso")]}, 10)
        b = self.db.blocos_do_dossie("Obesidade")
        self.assertEqual(len(b), 1)
        self.assertTrue(b[0].get("id"))

    def test_ids_sao_distintos_entre_blocos(self):
        self.db.salvar_dossie("Obesidade",
                              {"blocos": [_bloco("Um"), _bloco("Dois")]}, 10)
        ids = [b["id"] for b in self.db.blocos_do_dossie("Obesidade")]
        self.assertEqual(len(set(ids)), 2)

    def test_tema_sem_dossie_devolve_lista_vazia(self):
        self.assertEqual(self.db.blocos_do_dossie("Longevidade"), [])

    def test_conteudo_quebrado_devolve_lista_vazia_em_vez_de_explodir(self):
        self.db.salvar_dossie("Obesidade", {"blocos": [_bloco("X")]}, 1)
        with self.db._conn() as c:
            c.execute("UPDATE dossies SET conteudo=? WHERE tema=?", ("{quebrado", "Obesidade"))
        self.assertEqual(self.db.blocos_do_dossie("Obesidade"), [])


class TestBackfillIds(_Base):
    """Achado da revisão final: um dossiê gravado ANTES desta entrega não tem `id` nos
    blocos, e sem id a tela não oferece ✏️ Editar — sem nenhuma pista disso. O backfill
    destrava o botão sem custar minutos e reais de IA reconstruindo à toa."""

    def _tira_o_id(self, tema, indice=0):
        blocos = self.db.blocos_do_dossie(tema)
        blocos[indice].pop("id", None)
        self.db._gravar_blocos_cru(tema, blocos)

    def test_dossie_legado_ganha_ids(self):
        self.db.salvar_dossie("Obesidade", {"blocos": [_bloco("Texto da IA")]}, 10)
        self._tira_o_id("Obesidade")
        self.assertIsNone(self.db.blocos_do_dossie("Obesidade")[0].get("id"))

        n = self.db.dossie_backfill_ids("Obesidade")

        self.assertEqual(n, 1)
        self.assertTrue(self.db.blocos_do_dossie("Obesidade")[0].get("id"))

    def test_rodar_de_novo_a_segunda_vez_devolve_0_e_nao_reescreve(self):
        self.db.salvar_dossie("Obesidade", {"blocos": [_bloco("Texto da IA")]}, 10)
        self._tira_o_id("Obesidade")
        self.assertEqual(self.db.dossie_backfill_ids("Obesidade"), 1)
        antes = self.db.obter_dossie("Obesidade")

        n2 = self.db.dossie_backfill_ids("Obesidade")

        self.assertEqual(n2, 0)
        depois = self.db.obter_dossie("Obesidade")
        self.assertEqual(antes["conteudo"], depois["conteudo"])
        self.assertEqual(antes["atualizado_em"], depois["atualizado_em"],
                         "sem nada pra fazer, nem `atualizado_em` pode mudar — senão a "
                         "tela mostra 'atualizado agora' toda vez que a aba abre")

    def test_nao_altera_fixado_afirmacao_ou_estudos(self):
        self.db.salvar_dossie("Obesidade", {"blocos": [_bloco("Texto da IA")]}, 10)
        bid = self.db.blocos_do_dossie("Obesidade")[0]["id"]
        self.db.dossie_editar_bloco("Obesidade", bid, "Texto do Diego")
        blocos = self.db.blocos_do_dossie("Obesidade") + [
            {"afirmacao": "Órfão", "estudos": [{"titulo": "Y", "fonte": "", "data": ""}]}]
        self.db._gravar_blocos_cru("Obesidade", blocos)

        self.db.dossie_backfill_ids("Obesidade")

        fixado = next(b for b in self.db.blocos_do_dossie("Obesidade") if b["id"] == bid)
        self.assertTrue(fixado.get("fixado"))
        self.assertEqual(fixado["afirmacao"], "Texto do Diego")
        orfao = next(b for b in self.db.blocos_do_dossie("Obesidade")
                     if b["afirmacao"] == "Órfão")
        self.assertEqual(orfao["estudos"], [{"titulo": "Y", "fonte": "", "data": ""}])
        self.assertFalse(orfao.get("fixado"))
        self.assertTrue(orfao.get("id"))

    def test_tema_sem_dossie_nao_quebra(self):
        self.assertEqual(self.db.dossie_backfill_ids("Longevidade"), 0)


class TestGravadorPreservaOsFixados(_Base):
    """O teste que dá sentido ao desenho inteiro."""

    def setUp(self):
        super().setUp()
        self.db.salvar_dossie("Obesidade", {"blocos": [_bloco("Texto da IA")]}, 10)
        bid = self.db.blocos_do_dossie("Obesidade")[0]["id"]
        blocos = self.db.blocos_do_dossie("Obesidade")
        blocos[0].update({"afirmacao": "Texto do Diego", "fixado": True,
                          "editado_em": "2026-08-13T10:00:00"})
        self.db._gravar_blocos_cru("Obesidade", blocos)
        self.bid = bid

    def test_salvar_conteudo_novo_NAO_apaga_o_bloco_fixado(self):
        """Uma reconstrução manda blocos completamente diferentes — o do Diego fica."""
        self.db.salvar_dossie("Obesidade", {"blocos": [_bloco("Coisa nova da IA")]}, 20)
        afirmacoes = [b["afirmacao"] for b in self.db.blocos_do_dossie("Obesidade")]
        self.assertIn("Texto do Diego", afirmacoes)
        self.assertIn("Coisa nova da IA", afirmacoes)

    def test_o_id_do_fixado_nao_muda(self):
        self.db.salvar_dossie("Obesidade", {"blocos": [_bloco("Outra")]}, 20)
        fixado = [b for b in self.db.blocos_do_dossie("Obesidade") if b.get("fixado")][0]
        self.assertEqual(fixado["id"], self.bid)

    def test_salvar_dossie_VAZIO_tambem_preserva(self):
        """IA fora do ar devolvendo nada não pode levar o texto dele junto."""
        self.db.salvar_dossie("Obesidade", {"blocos": []}, 0)
        self.assertEqual([b["afirmacao"] for b in self.db.blocos_do_dossie("Obesidade")],
                         ["Texto do Diego"])

    def test_fixado_nao_duplica_quando_o_conteudo_devolvido_ja_o_contem(self):
        """Salvar de volta o que foi lido não pode gerar duas cópias do mesmo bloco."""
        atuais = self.db.blocos_do_dossie("Obesidade")
        self.db.salvar_dossie("Obesidade", {"blocos": atuais}, 10)
        ids = [b["id"] for b in self.db.blocos_do_dossie("Obesidade")]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 1)

    def test_o_fixado_vem_primeiro(self):
        self.db.salvar_dossie("Obesidade", {"blocos": [_bloco("Nova")]}, 20)
        self.assertTrue(self.db.blocos_do_dossie("Obesidade")[0].get("fixado"))

    def test_bloco_NAO_fixado_e_substituido_normalmente(self):
        """A preservação vale só pros fixados — o resto é da máquina."""
        self.db.salvar_dossie("Longevidade", {"blocos": [_bloco("Velha")]}, 5)
        self.db.salvar_dossie("Longevidade", {"blocos": [_bloco("Nova")]}, 5)
        self.assertEqual([b["afirmacao"] for b in self.db.blocos_do_dossie("Longevidade")],
                         ["Nova"])

    def test_fixado_sem_id_ganha_um_no_proximo_salvar_dossie(self):
        """Endurecimento (achado da revisão da Task 1): hoje todo fixado nasce com id, mas
        um que chegasse sem — linha legada, edição direta no banco, bug futuro — não pode
        ficar órfão pra sempre. `salvar_dossie` também passa os fixados por `_com_ids`.

        `_gravar_blocos_cru` é UPDATE puro (task 1): precisa da linha já existir, por isso
        o primeiro `salvar_dossie` só cria o dossiê antes de forçar o bloco sem id."""
        self.db.salvar_dossie("Longevidade", {"blocos": []}, 0)
        self.db._gravar_blocos_cru("Longevidade",
                                    [{"afirmacao": "Texto do Diego", "fixado": True}])
        self.db.salvar_dossie("Longevidade", {"blocos": [_bloco("Nova")]}, 5)
        blocos = self.db.blocos_do_dossie("Longevidade")
        fixado = [b for b in blocos if b.get("fixado")][0]
        self.assertTrue(fixado.get("id"))
        self.assertEqual(fixado["afirmacao"], "Texto do Diego")


class TestEditarEsoltar(_Base):
    def setUp(self):
        super().setUp()
        self.db.salvar_dossie("Obesidade",
                              {"blocos": [_bloco("Texto da IA"), _bloco("Outro")]}, 10)
        self.bid = self.db.blocos_do_dossie("Obesidade")[0]["id"]

    def _bloco_por_id(self, bid):
        return next(b for b in self.db.blocos_do_dossie("Obesidade") if b["id"] == bid)

    def test_editar_grava_o_texto(self):
        self.db.dossie_editar_bloco("Obesidade", self.bid, "Texto do Diego")
        self.assertEqual(self._bloco_por_id(self.bid)["afirmacao"], "Texto do Diego")

    def test_editar_FIXA_na_mesma_tacada(self):
        """Decisão do Diego: não existe editar sem fixar — senão a reconstrução seguinte
        apaga o que ele escreveu, calada."""
        self.db.dossie_editar_bloco("Obesidade", self.bid, "Texto do Diego")
        self.assertTrue(self._bloco_por_id(self.bid).get("fixado"))

    def test_editar_carimba_a_data(self):
        self.db.dossie_editar_bloco("Obesidade", self.bid, "Texto do Diego")
        self.assertTrue(self._bloco_por_id(self.bid).get("editado_em"))

    def test_editar_nao_mexe_nos_estudos_do_bloco(self):
        antes = self._bloco_por_id(self.bid)["estudos"]
        self.db.dossie_editar_bloco("Obesidade", self.bid, "Texto do Diego")
        self.assertEqual(self._bloco_por_id(self.bid)["estudos"], antes)

    def test_editar_nao_mexe_nos_outros_blocos(self):
        self.db.dossie_editar_bloco("Obesidade", self.bid, "Texto do Diego")
        outros = [b for b in self.db.blocos_do_dossie("Obesidade") if b["id"] != self.bid]
        self.assertEqual([b["afirmacao"] for b in outros], ["Outro"])
        self.assertFalse(outros[0].get("fixado"))

    def test_texto_vazio_levanta_e_nao_grava(self):
        """Afirmação em branco não é edição: é um bloco sem sentido — e como editar fixa,
        salvar vazio congelaria o nada."""
        for ruim in ("", "   ", "\n\t "):
            with self.subTest(ruim=ruim):
                with self.assertRaises(ValueError):
                    self.db.dossie_editar_bloco("Obesidade", self.bid, ruim)
        self.assertEqual(self._bloco_por_id(self.bid)["afirmacao"], "Texto da IA")

    def test_texto_com_espaco_nas_pontas_e_aparado(self):
        self.db.dossie_editar_bloco("Obesidade", self.bid, "  Texto do Diego  ")
        self.assertEqual(self._bloco_por_id(self.bid)["afirmacao"], "Texto do Diego")

    def test_bloco_inexistente_devolve_False_sem_gravar(self):
        self.assertFalse(self.db.dossie_editar_bloco("Obesidade", "nao-existe", "X"))
        self.assertEqual(len(self.db.blocos_do_dossie("Obesidade")), 2)

    def test_soltar_tira_o_fixado(self):
        self.db.dossie_editar_bloco("Obesidade", self.bid, "Texto do Diego")
        self.assertTrue(self.db.dossie_soltar_bloco("Obesidade", self.bid))
        self.assertFalse(self._bloco_por_id(self.bid).get("fixado"))

    def test_soltar_mantem_o_texto_ate_a_proxima_reconstrucao(self):
        self.db.dossie_editar_bloco("Obesidade", self.bid, "Texto do Diego")
        self.db.dossie_soltar_bloco("Obesidade", self.bid)
        self.assertEqual(self._bloco_por_id(self.bid)["afirmacao"], "Texto do Diego")

    def test_depois_de_soltar_a_reconstrucao_substitui(self):
        self.db.dossie_editar_bloco("Obesidade", self.bid, "Texto do Diego")
        self.db.dossie_soltar_bloco("Obesidade", self.bid)
        self.db.salvar_dossie("Obesidade", {"blocos": [_bloco("Só a nova")]}, 10)
        self.assertEqual([b["afirmacao"] for b in self.db.blocos_do_dossie("Obesidade")],
                         ["Só a nova"])

    def test_soltar_bloco_inexistente_devolve_False(self):
        self.assertFalse(self.db.dossie_soltar_bloco("Obesidade", "nao-existe"))

    def test_bloco_id_vazio_nao_edita_bloco_orfao(self):
        """Achado da revisão da Task 2: um bloco órfão sem id (`b.get("id")` devolve
        None) não pode ser casado quando `bloco_id` chega vazio ou None do formulário —
        senão a função editaria o bloco errado em vez de devolver False."""
        blocos = self.db.blocos_do_dossie("Obesidade") + [{"afirmacao": "Órfão"}]
        self.db._gravar_blocos_cru("Obesidade", blocos)
        self.assertFalse(self.db.dossie_editar_bloco("Obesidade", "", "X"))
        self.assertFalse(self.db.dossie_editar_bloco("Obesidade", None, "X"))
        orfao = next(b for b in self.db.blocos_do_dossie("Obesidade")
                     if b["afirmacao"] == "Órfão")
        self.assertFalse(orfao.get("fixado"))

    def test_bloco_id_vazio_nao_solta_bloco_orfao(self):
        blocos = self.db.blocos_do_dossie("Obesidade") + \
            [{"afirmacao": "Órfão", "fixado": True}]
        self.db._gravar_blocos_cru("Obesidade", blocos)
        self.assertFalse(self.db.dossie_soltar_bloco("Obesidade", ""))
        self.assertFalse(self.db.dossie_soltar_bloco("Obesidade", None))
        orfao = next(b for b in self.db.blocos_do_dossie("Obesidade")
                     if b["afirmacao"] == "Órfão")
        self.assertTrue(orfao.get("fixado"))


class TestReconstrucaoSabeDosFixados(_Base):
    """Sem isso o dossiê passa a dizer a mesma coisa duas vezes: uma com as palavras do
    Diego, outra com as da IA."""

    def setUp(self):
        super().setUp()
        import importlib, dossie
        importlib.reload(dossie)
        self.dossie = dossie

    def _estudos(self, n=3):
        return [{"titulo": f"Estudo {i}", "fonte": "NEJM", "data": "2026-03",
                 "abstract": "abstract " * 30} for i in range(n)]

    def test_a_afirmacao_fixada_vai_no_prompt_da_fusao(self):
        prompts = []

        def gerar_fn(p):
            prompts.append(p)
            return '{"blocos":[{"afirmacao":"a","estudos":[{"titulo":"Estudo 1"}]}]}'

        self.dossie.construir(self._estudos(), lote=2, gerar_fn=gerar_fn,
                              fixadas=["Uma afirmação que o Diego escreveu"])
        self.assertTrue(any("Uma afirmação que o Diego escreveu" in p for p in prompts))

    def test_o_aviso_fica_so_no_prompt_da_fusao_nao_nos_lotes(self):
        """Achado da revisão da Task 3: `any(... in prompts)` passaria mesmo se o aviso
        vazasse pros prompts dos LOTES também — gastaria tokens em toda chamada e
        poluiria a instrução de cada lote, sem que a suíte percebesse."""
        prompts = []

        def gerar_fn(p):
            prompts.append(p)
            return '{"blocos":[{"afirmacao":"a","estudos":[{"titulo":"Estudo 1"}]}]}'

        self.dossie.construir(self._estudos(), lote=2, gerar_fn=gerar_fn,
                              fixadas=["Uma afirmação que o Diego escreveu"])
        *prompts_lote, prompt_fusao = prompts
        self.assertTrue(prompts_lote)          # sanity: houve mais de um lote nesta chamada
        self.assertIn("Uma afirmação que o Diego escreveu", prompt_fusao)
        for p in prompts_lote:
            self.assertNotIn("Uma afirmação que o Diego escreveu", p)

    def test_sem_fixadas_o_prompt_nao_ganha_o_aviso(self):
        prompts = []

        def gerar_fn(p):
            prompts.append(p)
            return '{"blocos":[{"afirmacao":"a","estudos":[{"titulo":"Estudo 1"}]}]}'

        self.dossie.construir(self._estudos(), lote=2, gerar_fn=gerar_fn)
        self.assertFalse(any("FIXADAS" in p for p in prompts))

    def test_reconstruir_passa_as_fixadas_lidas_do_banco(self):
        self.db.salvar_dossie("Obesidade", {"blocos": [_bloco("Texto da IA")]}, 1)
        bid = self.db.blocos_do_dossie("Obesidade")[0]["id"]
        self.db.dossie_editar_bloco("Obesidade", bid, "Texto do Diego")
        self.db.salvar_candidatos([{
            "chave": "k1", "titulo": "Estudo A", "tema": "Obesidade", "tipo": "varredura",
            "fonte": "NEJM", "data": "2026-03-01", "doi": "10.1/k1", "url": "",
            "abstract": "abs " * 40, "pergunta": "", "score": 8, "citacoes": 0, "tags": []}])
        prompts = []

        def gerar_fn(p):
            prompts.append(p)
            return '{"blocos":[{"afirmacao":"nova","estudos":[{"titulo":"Estudo A"}]}]}'

        self.dossie.reconstruir_todos(temas=["Obesidade"], gerar_fn=gerar_fn, db_mod=self.db)
        self.assertTrue(any("Texto do Diego" in p for p in prompts))

    def test_reconstruir_ponta_a_ponta_preserva_o_bloco_do_Diego(self):
        """O caminho real: o botão 🧠 roda inteiro e o texto dele continua lá."""
        self.db.salvar_dossie("Obesidade", {"blocos": [_bloco("Texto da IA")]}, 1)
        bid = self.db.blocos_do_dossie("Obesidade")[0]["id"]
        self.db.dossie_editar_bloco("Obesidade", bid, "Texto do Diego")
        self.db.salvar_candidatos([{
            "chave": "k2", "titulo": "Estudo B", "tema": "Obesidade", "tipo": "varredura",
            "fonte": "NEJM", "data": "2026-03-01", "doi": "10.1/k2", "url": "",
            "abstract": "abs " * 40, "pergunta": "", "score": 8, "citacoes": 0, "tags": []}])
        self.dossie.reconstruir_todos(
            temas=["Obesidade"], db_mod=self.db,
            gerar_fn=lambda p: '{"blocos":[{"afirmacao":"tudo novo",'
                               '"estudos":[{"titulo":"Estudo B"}]}]}')
        afirmacoes = [b["afirmacao"] for b in self.db.blocos_do_dossie("Obesidade")]
        self.assertIn("Texto do Diego", afirmacoes)
        self.assertIn("tudo novo", afirmacoes)


if __name__ == "__main__":
    unittest.main()
