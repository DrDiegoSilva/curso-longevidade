"""Sweep de recuperação one-off: candidatos travados em status='agendado' sem slot
correspondente na agenda — órfãos do bug histórico do `agenda_devolver` que não tratava
tipo='candidato' (o slot sumia, mas o candidato ficava 'agendado' pra sempre e some do
pool). Cobre `curadoria.varrer_presos` (db.py) e a rota admin POST /curadoria
acao=varrer_presos (serve.py)."""
import io
import os
import sys
import tempfile
import unittest
import urllib.parse as _urlp
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _reload_db(tmp):
    os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(tmp, "t.db")
    os.environ.pop("DATABASE_URL", None)
    import importlib, db as _db
    importlib.reload(_db)
    _db.init()
    return _db


def _snapshot_env():
    """Guarda o ambiente ANTERIOR (antes de _reload_db mexer nele)."""
    return {k: os.environ.get(k) for k in ("DSCURSO_ARTIGOS_DB", "DATABASE_URL")}


def _restore_db(snap):
    for k, v in snap.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    import importlib, db as _db
    importlib.reload(_db)


class TestVarrerPresos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.snap = _snapshot_env()
        self.db = _reload_db(self.tmp)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        _restore_db(self.snap)

    def _candidato(self, titulo="X", chave=None):
        import secrets
        chave = chave or secrets.token_hex(6)
        self.db.salvar_candidatos([{"tema": "Obesidade", "titulo": titulo, "chave": chave}])
        achado = [c for c in self.db.listar_candidatos() if c["chave"] == chave][0]
        return achado["id"]

    def test_preso_sem_slot_e_liberado_pro_pool(self):
        cid = self._candidato()
        self.db.marcar_candidato_agendado(cid)                    # 'agendado', sem slot -> preso
        import curadoria
        n = curadoria.varrer_presos(db_mod=self.db)
        self.assertEqual(n, 1)
        self.assertEqual(self.db.obter_candidato(cid)["status"], "novo")

    def test_agendado_com_slot_na_agenda_fica_intocado(self):
        cid = self._candidato()
        self.db.marcar_candidato_agendado(cid)
        self.db.agenda_upsert("2026-08-01", tipo="candidato", ref_id=cid,
                              tema="Obesidade", titulo="X")
        import curadoria
        n = curadoria.varrer_presos(db_mod=self.db)
        self.assertEqual(n, 0)
        self.assertEqual(self.db.obter_candidato(cid)["status"], "agendado")

    def test_outros_status_ficam_intocados(self):
        cid_novo = self._candidato(titulo="Novo")
        cid_desc = self._candidato(titulo="Descartado")
        self.db.marcar_candidatos([cid_desc], "descartado")
        import curadoria
        n = curadoria.varrer_presos(db_mod=self.db)
        self.assertEqual(n, 0)
        self.assertEqual(self.db.obter_candidato(cid_novo)["status"], "novo")
        self.assertEqual(self.db.obter_candidato(cid_desc)["status"], "descartado")

    def test_idempotente_segunda_rodada_libera_zero(self):
        cid = self._candidato()
        self.db.marcar_candidato_agendado(cid)
        import curadoria
        primeiro = curadoria.varrer_presos(db_mod=self.db)
        segundo = curadoria.varrer_presos(db_mod=self.db)
        self.assertEqual(primeiro, 1)
        self.assertEqual(segundo, 0)

    def test_uma_falha_isolada_nao_aborta_o_resto(self):
        cid1 = self._candidato(titulo="A")
        cid2 = self._candidato(titulo="B")
        self.db.marcar_candidato_agendado(cid1)
        self.db.marcar_candidato_agendado(cid2)
        real_marcar = self.db.marcar_candidato_pronto

        def quebra_no_primeiro(cid):
            if cid == cid1:
                raise RuntimeError("boom")
            return real_marcar(cid)

        fake_db = mock.Mock(wraps=self.db)
        fake_db.marcar_candidato_pronto.side_effect = quebra_no_primeiro
        import curadoria
        n = curadoria.varrer_presos(db_mod=fake_db)
        self.assertEqual(n, 1)                                     # só cid2 foi liberado
        self.assertEqual(self.db.obter_candidato(cid1)["status"], "agendado")   # falhou, segue preso
        self.assertEqual(self.db.obter_candidato(cid2)["status"], "novo")


class _RouteStub:
    """Stub mínimo pro `self` de do_POST: mesmo padrão de test_admin_precos.py
    (não abre socket, não é uma requisição HTTP real)."""

    def __init__(self, path, body=b""):
        self.path = path
        self.rfile = io.BytesIO(body)
        self.headers = {"Content-Length": str(len(body)),
                         "Content-Type": "application/x-www-form-urlencoded"}

    def _html(self, s, code=200):
        return {"code": code, "body": s}

    def _redirect(self, location, token=None, clear=False):
        return {"redirect": location}


class TestRotaVarrerPresos(unittest.TestCase):
    """Rota POST /curadoria acao=varrer_presos, mesmo gate admin de varrer/varrer_classicos."""

    def setUp(self):
        self.snap = _snapshot_env()
        self.snap_token = os.environ.get("DSCURSO_ADMIN_TOKEN")
        self.tmp = tempfile.mkdtemp()
        self.db = _reload_db(self.tmp)
        os.environ["DSCURSO_ADMIN_TOKEN"] = "tok123"
        import importlib, config, serve
        importlib.reload(config)
        importlib.reload(serve)
        self.cfg, self.serve = config, serve

    def tearDown(self):
        import shutil, importlib, config
        if self.snap_token is None:
            os.environ.pop("DSCURSO_ADMIN_TOKEN", None)
        else:
            os.environ["DSCURSO_ADMIN_TOKEN"] = self.snap_token
        importlib.reload(config)
        _restore_db(self.snap)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _post(self, campos):
        body = _urlp.urlencode(campos).encode("utf-8")
        stub = _RouteStub("/curadoria", body)
        return self.serve.Handler.do_POST(stub)

    def test_sem_token_403_nao_libera(self):
        import secrets
        self.db.salvar_candidatos([{"tema": "Obesidade", "titulo": "Preso",
                                    "chave": secrets.token_hex(6)}])
        cid = self.db.listar_candidatos()[0]["id"]
        self.db.marcar_candidato_agendado(cid)
        r = self._post({"acao": "varrer_presos"})
        self.assertEqual(r["code"], 403)
        self.assertEqual(self.db.obter_candidato(cid)["status"], "agendado")   # não mexeu

    def test_com_token_libera_e_reporta_a_contagem(self):
        import secrets
        self.db.salvar_candidatos([{"tema": "Obesidade", "titulo": "Preso",
                                    "chave": secrets.token_hex(6)}])
        cid = self.db.listar_candidatos()[0]["id"]
        self.db.marcar_candidato_agendado(cid)
        r = self._post({"token": "tok123", "acao": "varrer_presos"})
        self.assertIn("redirect", r)
        self.assertIn("msg=", r["redirect"])
        msg = _urlp.parse_qs(_urlp.urlsplit(r["redirect"]).query).get("msg", [""])[0]
        self.assertIn("1", msg)                                    # relatou 1 liberado
        self.assertEqual(self.db.obter_candidato(cid)["status"], "novo")


if __name__ == "__main__":
    unittest.main()
