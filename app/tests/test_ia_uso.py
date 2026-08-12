"""Ledger de uso de IA: a tabela e quem escreve nela.

Pedido do Diego (2026-08-12): saber quanto custa cada coisa pra repassar na precificação.
O sistema tem só DOIS pontos pagos — `resumo_diario.claude()` e `audio.narrar()` —, então
instrumentar os dois mede tudo. Standalone: python3 app/tests/test_ia_uso.py"""
import io
import json
import os
import re
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


class TestTabelaIaUso(unittest.TestCase):
    def setUp(self):
        self.snap = _snapshot_env()
        self.tmp = tempfile.mkdtemp()
        self.db = _reload_db(self.tmp)

    def tearDown(self):
        _restore_db(self.snap)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_registra_e_lista(self):
        self.db.registrar_ia_uso("dossie", "claude-sonnet-4-6", 10_000, 2_000, 3)
        linhas = self.db.listar_ia_uso()
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]["acao"], "dossie")
        self.assertEqual(linhas[0]["modelo"], "claude-sonnet-4-6")
        self.assertEqual(linhas[0]["tokens_in"], 10_000)
        self.assertEqual(linhas[0]["tokens_out"], 2_000)
        self.assertEqual(linhas[0]["chamadas"], 3)
        self.assertTrue(linhas[0]["quando"])

    def test_duas_linhas_nao_se_sobrescrevem(self):
        self.db.registrar_ia_uso("dossie", "claude-sonnet-4-6", 1, 1)
        self.db.registrar_ia_uso("kit", "claude-sonnet-4-6", 2, 2)
        self.assertEqual(len(self.db.listar_ia_uso()), 2)

    def test_chamadas_tem_padrao_um(self):
        self.db.registrar_ia_uso("kit", "claude-sonnet-4-6", 5, 5)
        self.assertEqual(self.db.listar_ia_uso()[0]["chamadas"], 1)


class TestTodaTabelaTemRls(unittest.TestCase):
    """`_TABELAS` dirige o ENABLE ROW LEVEL SECURITY no Supabase. Tabela criada e esquecida
    nessa lista fica exposta na Data API pública — e ninguém percebe, porque o app conecta
    direto e ignora RLS."""

    def test_toda_tabela_criada_no_init_esta_em_tabelas(self):
        import db
        fonte = open(os.path.join(os.path.dirname(__file__), "..", "db.py"),
                     encoding="utf-8").read()
        criadas = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", fonte))
        self.assertTrue(criadas)                       # a regex tem que achar algo
        self.assertEqual(criadas - set(db._TABELAS), set())


if __name__ == "__main__":
    unittest.main()
