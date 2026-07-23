import os, re, sys, tempfile, importlib, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestTrocaNumero(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ.pop("DATABASE_URL", None)
        import db, subscribers, auth_web
        importlib.reload(db); importlib.reload(subscribers); importlib.reload(auth_web)
        self.db, self.subs, self.auth = db, subscribers, auth_web
        db.init()
        self.cap = {}
        self.fake = lambda num, msg: self.cap.update(
            num=num, code=re.search(r"\b(\d{6})\b", msg).group(1))

    def tearDown(self):
        import shutil; shutil.rmtree(self.tmp, ignore_errors=True)

    def test_troca_ok(self):
        s = self.subs.adicionar("Fulano", "5543999990000")
        self.assertEqual(self.auth.iniciar_troca_numero(s["id"], "5541988887777", self.fake), "enviado")
        self.assertEqual(self.cap["num"], "5541988887777")          # código foi pro número NOVO
        tok = self.auth._criar_sessao("5543999990000", "Fulano")     # sessão no número antigo
        st = self.auth.confirmar_troca_numero(s["id"], "5543999990000", "5541988887777", self.cap["code"])
        self.assertEqual(st, "ok")
        self.assertEqual(self.subs.por_id(s["id"])["whatsapp"], "5541988887777")
        self.assertEqual(self.auth.sessao(f"sid={tok}")["whatsapp"], "5541988887777")  # sessão migrada

    def test_codigo_errado(self):
        s = self.subs.adicionar("F", "5543999990000")
        self.auth.iniciar_troca_numero(s["id"], "5541988887777", self.fake)
        self.assertEqual(self.auth.confirmar_troca_numero(s["id"], "5543999990000", "5541988887777", "000000"), "codigo_errado")
        self.assertEqual(self.subs.por_id(s["id"])["whatsapp"], "5543999990000")  # não trocou

    def test_numero_de_outro_bloqueia(self):
        s = self.subs.adicionar("A", "5543999990000")
        self.subs.adicionar("B", "5541988887777")
        self.assertEqual(self.auth.iniciar_troca_numero(s["id"], "5541988887777", self.fake), "em_uso")


if __name__ == "__main__":
    unittest.main()
