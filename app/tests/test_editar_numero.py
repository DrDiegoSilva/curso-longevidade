import os, sys, unittest, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestEditarNumero(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ.pop("DATABASE_URL", None)
        import importlib, config as _c; importlib.reload(_c)
        import db as _db; importlib.reload(_db)
        import subscribers as _s; importlib.reload(_s)
        self.db, self.subs = _db, _s; _db.init()

    def tearDown(self):
        import shutil; shutil.rmtree(self.tmp, ignore_errors=True)

    def test_atualiza_para_numero_eua(self):
        s = self.subs.adicionar("Irmão", "5511999998888")   # cadastrado (BR mangled p/ simular)
        import phone
        novo = phone.montar_e164("1", "(305) 555-1234")      # +13055551234
        self.subs.atualizar_whatsapp(s["id"], novo)
        got = self.subs.por_whatsapp("+1 305 555 1234")
        self.assertIsNotNone(got)
        self.assertEqual(got["id"], s["id"])                 # casa pelo internacional
        self.assertEqual(phone.para_api(got["whatsapp"]), "13055551234")

    def test_colisao_nao_atualiza_para_numero_de_outro_assinante(self):
        import phone
        a = self.subs.adicionar("Assinante A", "5511999998888")
        b = self.subs.adicionar("Assinante B", "5521988887777")
        novo = phone.montar_e164("55", "21988887777")         # já é o número de B
        outro = self.subs.por_whatsapp(novo)
        self.assertIsNotNone(outro)
        self.assertEqual(outro["id"], b["id"])
        self.assertNotEqual(outro["id"], a["id"])
        # a rota HTTP não deve chamar atualizar_whatsapp(a) nesse caso — a mecânica
        # de detecção de colisão é esta consulta; o handler decide com base nela.


if __name__ == "__main__":
    unittest.main()
