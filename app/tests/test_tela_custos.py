"""Item 40 — a tela que finalmente lê o ledger de custos.

O ledger grava desde 2026-08-14 e até aqui gravava no vazio. Esta entrega só LÊ.
Standalone: python3 app/tests/test_tela_custos.py"""
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


class _Base(unittest.TestCase):
    def setUp(self):
        self.snap = _snapshot_env()
        self.tmp = tempfile.mkdtemp()
        self.db = _reload_db(self.tmp)

    def tearDown(self):
        _restore_db(self.snap)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _uso(self, quando, acao="dossie", modelo="claude-sonnet-4-6",
             tin=1000, tout=100, chamadas=1):
        """Grava direto com o carimbo que eu quero — `registrar_ia_uso` usa `now()`."""
        import secrets
        with self.db._conn() as c:
            c.execute("""INSERT INTO ia_uso (id,quando,acao,modelo,tokens_in,tokens_out,chamadas)
                         VALUES (?,?,?,?,?,?,?)""",
                      (secrets.token_hex(8), quando, acao, modelo, tin, tout, chamadas))


class TestResumoIaUso(_Base):
    def test_agrupa_por_dia_acao_e_modelo(self):
        self._uso("2026-08-14T10:00:00", "dossie", tin=1000, tout=100)
        self._uso("2026-08-14T18:00:00", "dossie", tin=500, tout=50)
        self._uso("2026-08-14T19:00:00", "kit", tin=200, tout=20)
        r = self.db.resumo_ia_uso("2026-08-01")
        dossie = [x for x in r if x["acao"] == "dossie"]
        self.assertEqual(len(dossie), 1)                 # as duas viraram uma linha
        self.assertEqual(dossie[0]["tokens_in"], 1500)
        self.assertEqual(dossie[0]["tokens_out"], 150)
        self.assertEqual(dossie[0]["chamadas"], 2)
        self.assertEqual(dossie[0]["dia"], "2026-08-14")

    def test_dias_diferentes_nao_se_misturam(self):
        self._uso("2026-08-14T10:00:00", "dossie")
        self._uso("2026-08-15T10:00:00", "dossie")
        self.assertEqual(len(self.db.resumo_ia_uso("2026-08-01")), 2)

    def test_modelos_diferentes_nao_se_misturam(self):
        """O custo depende do modelo — somar Haiku com Opus perderia a informação."""
        self._uso("2026-08-14T10:00:00", "titulo", modelo="claude-haiku-4-5-20251001")
        self._uso("2026-08-14T11:00:00", "titulo", modelo="claude-opus-4-8")
        self.assertEqual(len(self.db.resumo_ia_uso("2026-08-01")), 2)

    def test_desde_e_inclusivo_com_carimbo_completo(self):
        """Prova inclusividade real: carimbo idêntico ao da linha deve ser incluído."""
        self._uso("2026-08-14T10:00:00", "dossie")
        # Chamar com carimbo COMPLETO e idêntico: deve incluir a linha
        self.assertEqual(len(self.db.resumo_ia_uso("2026-08-14T10:00:00")), 1)

    def test_desde_com_data_curta_como_uso_real(self):
        """Uso real: a tela chama com "2026-08-14" (data curta), esperando tudo aquele dia."""
        self._uso("2026-08-14T00:00:00", "dossie")
        self._uso("2026-08-14T23:59:59", "kit")
        # Chamar com data curta: deve incluir tudo que começar com "2026-08-14"
        r = self.db.resumo_ia_uso("2026-08-14")
        self.assertEqual(len(r), 2)

    def test_antes_do_desde_fica_de_fora(self):
        self._uso("2026-08-13T23:59:59", "dossie")
        self.assertEqual(self.db.resumo_ia_uso("2026-08-14"), [])

    def test_ate_e_exclusivo(self):
        self._uso("2026-08-14T10:00:00", "dossie")
        self._uso("2026-08-20T10:00:00", "dossie")
        r = self.db.resumo_ia_uso("2026-08-01", "2026-08-15")
        self.assertEqual([x["dia"] for x in r], ["2026-08-14"])

    def test_ordena_do_dia_mais_novo_para_o_mais_velho(self):
        self._uso("2026-08-14T10:00:00", "dossie")
        self._uso("2026-08-16T10:00:00", "kit")
        self.assertEqual([x["dia"] for x in self.db.resumo_ia_uso("2026-08-01")],
                         ["2026-08-16", "2026-08-14"])

    def test_janela_sem_nada_devolve_lista_vazia(self):
        self.assertEqual(self.db.resumo_ia_uso("2026-08-01"), [])


if __name__ == "__main__":
    unittest.main()
