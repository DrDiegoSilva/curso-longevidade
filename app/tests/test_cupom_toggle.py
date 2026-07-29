"""Toggle admin de cupons (ativar/desativar) + as duas ressurreições silenciosas que o
fechavam: o re-seed do LANCAMENTO forçando ativo=1 em todo boot, e `consumir_cupom`
escrevendo ativo=1 em todo uso de um cupom multi-uso. Standalone:
python3 app/tests/test_cupom_toggle.py"""
import io
import os
import sys
import tempfile
import unittest
import urllib.parse as _urlp

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


class TestToggleCupomDb(unittest.TestCase):
    """`db.toggle_cupom(codigo, ativo)` — set explícito (não flip), no mesmo molde de
    `toggle_afiliado(id, ativo)`."""

    def setUp(self):
        self.snap = _snapshot_env()
        self.tmp = tempfile.mkdtemp()
        self.db = _reload_db(self.tmp)

    def tearDown(self):
        import shutil
        _restore_db(self.snap)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_desativar_derruba_cupom_valido_e_desconto(self):
        # Comportamento REAL (não só a coluna): depois de desativado, cupom_valido() e
        # cupom_desconto() (usados pelo checkout) deixam de honrar o cupom.
        self.db.criar_cupom(codigo="PROMO1", desconto_valor=200, uso_unico=False, plano_slug="")
        self.assertTrue(self.db.cupom_valido("promo1"))
        self.assertEqual(self.db.cupom_desconto("PROMO1", "anual"), 200.0)

        self.db.toggle_cupom("promo1", False)   # normaliza como consumir_cupom (strip+upper)

        self.assertFalse(self.db.cupom_valido("PROMO1"))
        self.assertEqual(self.db.cupom_desconto("PROMO1", "anual"), 0.0)

    def test_reativar_funciona_de_novo(self):
        self.db.criar_cupom(codigo="PROMO2", desconto_valor=150, uso_unico=False, plano_slug="")
        self.db.toggle_cupom("PROMO2", False)
        self.assertFalse(self.db.cupom_valido("PROMO2"))

        self.db.toggle_cupom("PROMO2", True)

        self.assertTrue(self.db.cupom_valido("PROMO2"))
        self.assertEqual(self.db.cupom_desconto("PROMO2", "anual"), 150.0)

    def test_set_explicito_dobro_desativar_idempotente(self):
        # É exatamente por isso que a assinatura é (codigo, ativo) e não um flip: chamar
        # desativar duas vezes seguidas (double-submit) tem que continuar desativado.
        self.db.criar_cupom(codigo="PROMO3", desconto_valor=50, uso_unico=False)
        self.db.toggle_cupom("PROMO3", False)
        self.db.toggle_cupom("PROMO3", False)
        self.assertFalse(self.db.cupom_valido("PROMO3"))

    def test_desativar_lancamento_sobrevive_ao_reseed(self):
        """Item 2: `_seed_cupons` roda em TODO boot (não só na primeira vez) e o DO UPDATE
        antigo forçava `ativo=1` — uma desativação não sobrevivia a um restart/deploy.
        Simula o 2º boot chamando `_seed_cupons()` de novo (mesmo padrão de
        test_precos_lancamento.test_seed_lancamento_autocorrige_cortesia_preexistente)."""
        self.assertTrue(self.db.obter_cupom("LANCAMENTO")["ativo"])   # nasce ativo (seed)

        self.db.toggle_cupom("LANCAMENTO", False)
        self.assertFalse(self.db.obter_cupom("LANCAMENTO")["ativo"])

        self.db._seed_cupons()   # <-- simula um SEGUNDO boot/deploy

        info = self.db.obter_cupom("LANCAMENTO")
        self.assertFalse(info["ativo"])                                    # continua desligado
        self.assertEqual(self.db.cupom_desconto("LANCAMENTO", "anual"), 0.0)
        # a "forma" continua sendo corrigida pelo seed (mesma proteção contra a cortesia
        # pré-existente) — só o ativo é que não é mais pisado.
        self.assertEqual(float(info["desconto_valor"]), 500.0)
        self.assertEqual(info["plano_slug"], "anual")

    def test_desativar_multiuso_sobrevive_a_um_consumo(self):
        """Item 3: `consumir_cupom` escrevia `ativo = 0 if uso_unico else 1` — um cupom
        MULTI-uso desativado que fosse consumido (ex.: uma corrida entre o admin
        desativando e um checkout em voo) reativava sozinho."""
        self.db.criar_cupom(codigo="MULTIX", desconto_valor=80, uso_unico=False)
        self.db.toggle_cupom("MULTIX", False)
        self.assertFalse(self.db.obter_cupom("MULTIX")["ativo"])

        self.db.consumir_cupom("MULTIX")

        info = self.db.obter_cupom("MULTIX")
        self.assertFalse(info["ativo"])              # continua desligado
        self.assertEqual(info["usos"], 1)            # mas o uso foi contado normalmente
        self.assertEqual(self.db.cupom_desconto("MULTIX", "anual"), 0.0)

    def test_multiuso_ativo_continua_ativo_apos_consumo(self):
        # Não regride o comportamento normal: multi-uso ATIVO continua ativo após uso.
        self.db.criar_cupom(codigo="MULTIY", desconto_valor=80, uso_unico=False)
        self.db.consumir_cupom("MULTIY")
        info = self.db.obter_cupom("MULTIY")
        self.assertTrue(info["ativo"])
        self.assertEqual(info["usos"], 1)

    def test_uso_unico_continua_desativando_sozinho_ao_consumir(self):
        # Não regride o outro comportamento normal: uso único desativa ao consumir.
        self.db.criar_cupom(codigo="UNICOX", uso_unico=True, dias_acesso=7)
        self.db.consumir_cupom("UNICOX")
        info = self.db.obter_cupom("UNICOX")
        self.assertFalse(info["ativo"])
        self.assertEqual(info["usos"], 1)


class TestCupomRowLabel(unittest.TestCase):
    """`_cupom_row` (dentro de `pagina_admin`) — distingue ATIVO / DESATIVADO (pelo
    admin) / USADO (uso único consumido)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import site_web as _sw
        import importlib
        importlib.reload(_sw)
        self.sw = _sw

    def _cup(self, **kw):
        base = {"codigo": "TESTE1", "descricao": "desc", "uso_unico": 0, "usos": 0,
                "dias_acesso": 0, "ativo": 1}
        base.update(kw)
        return base

    def _html(self, **kw):
        return self.sw.pagina_admin([], token="tk", cupons=[self._cup(**kw)])

    def test_ativo_mostra_ativo(self):
        h = self._html(ativo=1)
        self.assertIn(">ATIVO<", h)
        self.assertNotIn(">USADO<", h)
        self.assertNotIn(">DESATIVADO<", h)

    def test_multiuso_desativado_pelo_admin_nao_diz_usado(self):
        # O bug de rótulo: cupom multi-uso, desativado manualmente, nunca foi "usado" no
        # sentido de uso-único — dizer USADO engana o Diego, que lê esta tela pra saber o
        # que está no ar.
        h = self._html(ativo=0, uso_unico=0, usos=12)
        self.assertIn(">DESATIVADO<", h)
        self.assertNotIn(">USADO<", h)

    def test_uso_unico_consumido_diz_usado(self):
        h = self._html(ativo=0, uso_unico=1, usos=1)
        self.assertIn(">USADO<", h)
        self.assertNotIn(">DESATIVADO<", h)

    def test_uso_unico_desativado_antes_de_ser_usado_nao_diz_usado(self):
        # Caso de borda: uso único desativado pelo admin ANTES de qualquer uso (usos=0)
        # não pode dizer "USADO" — ninguém usou ainda.
        h = self._html(ativo=0, uso_unico=1, usos=0)
        self.assertIn(">DESATIVADO<", h)
        self.assertNotIn(">USADO<", h)

    def test_botao_toggle_presente_com_valor_oposto(self):
        h = self._html(ativo=1, codigo="ABC123")
        self.assertIn('value="toggle_cupom"', h)
        self.assertIn('name="codigo" value="ABC123"', h)
        self.assertIn('name="on" value="0"', h)   # ativo agora -> próxima ação desativa

        h2 = self._html(ativo=0, codigo="ABC123")
        self.assertIn('name="on" value="1"', h2)  # inativo agora -> próxima ação ativa

    def test_escapa_codigo_e_descricao(self):
        h = self._html(codigo="<script>x</script>", descricao="<b>y</b>")
        self.assertNotIn("<script>x</script>", h)
        self.assertNotIn("<b>y</b>", h)
        self.assertIn("&lt;script&gt;", h)


class _RouteStub:
    """Mesmo stub mínimo de test_admin_precos.py (`_RouteStub`) — path/headers/rfile +
    `_html`/`_redirect`, sem abrir socket. `/admin` também chama `self._sessao()`, que
    funciona aqui porque `auth_web.sessao("")` (Cookie ausente) retorna None."""

    def __init__(self, path, body=b""):
        self.path = path
        self.rfile = io.BytesIO(body)
        self.headers = {"Content-Length": str(len(body)),
                         "Content-Type": "application/x-www-form-urlencoded"}
        self.client_address = ("127.0.0.1", 0)

    def _html(self, s, code=200):
        return {"code": code, "body": s}

    def _redirect(self, location, token=None, clear=False):
        return {"redirect": location}

    def _sessao(self):
        return None


class TestRotaAdminToggleCupom(unittest.TestCase):
    """Rota /admin POST acao=toggle_cupom — mesma gate de token do resto de /admin
    (ver toggle_afiliado em /admin/afiliados)."""

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
        self.db.criar_cupom(codigo="ROTAX", desconto_valor=90, uso_unico=False)

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
        stub = _RouteStub("/admin", body)
        return self.serve.Handler.do_POST(stub)

    def test_sem_token_403_nao_altera(self):
        r = self._post({"acao": "toggle_cupom", "codigo": "ROTAX", "on": "0"})
        self.assertEqual(r["code"], 403)
        self.assertTrue(self.db.obter_cupom("ROTAX")["ativo"])   # continua ativo

    def test_com_token_desativa_e_redireciona(self):
        r = self._post({"token": "tok123", "acao": "toggle_cupom", "codigo": "ROTAX", "on": "0"})
        self.assertIn("redirect", r)
        self.assertFalse(self.db.obter_cupom("ROTAX")["ativo"])

    def test_com_token_reativa(self):
        self.db.toggle_cupom("ROTAX", False)
        r = self._post({"token": "tok123", "acao": "toggle_cupom", "codigo": "ROTAX", "on": "1"})
        self.assertIn("redirect", r)
        self.assertTrue(self.db.obter_cupom("ROTAX")["ativo"])


if __name__ == "__main__":
    unittest.main()
