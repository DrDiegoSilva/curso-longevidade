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


if __name__ == "__main__":
    unittest.main()
