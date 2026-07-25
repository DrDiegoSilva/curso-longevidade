"""Testes do horário de envio por assinante (slots). Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestSlotBasico(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        for m in ("config", "db", "subscribers"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, subscribers
        importlib.reload(config); importlib.reload(db); importlib.reload(subscribers)
        self.cfg, self.db, self.s = config, db, subscribers
        self.s._migrado = False
        db.init()

    def test_slot_de_default(self):
        self.assertEqual(self.s.slot_de({}), self.cfg.SLOT_DEFAULT)
        self.assertEqual(self.s.slot_de({"slot_envio": None}), self.cfg.SLOT_DEFAULT)
        self.assertEqual(self.s.slot_de({"slot_envio": "xx"}), self.cfg.SLOT_DEFAULT)  # inválido
        self.assertEqual(self.s.slot_de({"slot_envio": "12h"}), "12h")

    def test_definir_slot(self):
        reg = self.s.adicionar("Fulano", "5543999990000")
        self.s.definir_slot(reg["id"], "18h")
        self.assertEqual(self.s.por_id(reg["id"])["slot_envio"], "18h")
        self.s.definir_slot(reg["id"], "zz")   # inválido -> não muda
        self.assertEqual(self.s.por_id(reg["id"])["slot_envio"], "18h")

    def test_registrar_envio_slot_idempotente(self):
        self.assertTrue(self.db.registrar_envio_slot("2026-07-24", "08h"))    # 1ª vez
        self.assertFalse(self.db.registrar_envio_slot("2026-07-24", "08h"))   # repetido
        self.assertTrue(self.db.registrar_envio_slot("2026-07-24", "12h"))    # outro slot
        self.assertTrue(self.db.registrar_envio_slot("2026-07-25", "08h"))    # outro dia


class TestVaga(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        for m in ("config", "db", "subscribers"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, subscribers
        importlib.reload(config); importlib.reload(db); importlib.reload(subscribers)
        self.cfg, self.db, self.s = config, db, subscribers
        self.s._migrado = False
        db.init()

    def test_contar_por_slot_default(self):
        a = self.s.adicionar("A", "5543000000001")   # sem slot -> 08h
        self.s.definir_slot(self.s.adicionar("B", "5543000000002")["id"], "12h")
        cont = self.s.contar_por_slot()
        self.assertEqual(cont["08h"], 1)
        self.assertEqual(cont["12h"], 1)
        self.assertEqual(cont["20h"], 0)

    def test_slots_com_vaga_esconde_cheio_mas_mantem_atual(self):
        for i in range(3):
            self.s.definir_slot(self.s.adicionar(f"C{i}", f"554300001000{i}")["id"], "07h")
        vaga = self.s.slots_com_vaga(teto=3)          # 07h cheio (3/3)
        self.assertNotIn("07h", vaga)
        self.assertIn("08h", vaga)
        # mesmo cheio, o slot_atual do assinante é ofertado (pra ele manter)
        vaga2 = self.s.slots_com_vaga(teto=3, slot_atual="07h")
        self.assertIn("07h", vaga2)
        self.assertEqual(vaga2, [s for s in self.cfg.SLOTS if s in vaga2])  # ordem preservada


class TestEnviarSlot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        for m in ("config", "db", "subscribers", "draft_store", "daily"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, subscribers, draft_store, daily
        for mod in (config, db, subscribers, draft_store, daily):
            importlib.reload(mod)
        self.cfg, self.db, self.s, self.ds, self.daily = config, db, subscribers, draft_store, daily
        self.s._migrado = False
        db.init()
        # rascunho aprovado de hoje
        hoje = self.daily._hoje_iso()
        r = self.ds.novo_rascunho(hoje, {"tema": "Obesidade", "titulo": "T", "doi": "10.1/x"}, "resumo", None)
        r["status"] = "APPROVED"; self.ds.salvar(r)
        # captura destinatários (mocka o envio pesado)
        self.enviados = []
        self.daily.deliver.distribuir = lambda r, subs, delay, fn: (
            self.enviados.extend(subs) or {"ok": len(subs), "falhas": []})
        self.daily.deliver.enviar_curador = lambda msg: None
        self.daily._audio_master = lambda *a, **k: None
        self.daily._pdf_master = lambda *a, **k: None
        self.daily._e_dia_util = lambda dt: True
        self.daily._enviar_estudo_para = lambda w, n, ctx: self.enviados.append({"whatsapp": w, "nome": n})
        # 2 assinantes: um no 12h, um no default (08h)
        self.s.definir_slot(self.s.adicionar("A", "5543000000001")["id"], "12h")
        self.s.adicionar("B", "5543000000002")   # 08h default

    def test_envia_so_do_slot(self):
        self.daily.enviar_slot("12h")
        self.assertEqual(len(self.enviados), 1)
        self.assertEqual(self.s.slot_de(self.enviados[0]), "12h")

    def test_idempotente_por_slot(self):
        self.daily.enviar_slot("12h")
        self.enviados.clear()
        self.daily.enviar_slot("12h")             # 2ª vez no mesmo dia/slot
        self.assertEqual(self.enviados, [])       # não reenvia

    def test_default_recebe_no_08h(self):
        self.daily.enviar_slot("08h")
        self.assertEqual(len(self.enviados), 1)
        self.assertEqual(self.enviados[0]["nome"], "B")

    def test_sent_nao_bloqueia_outro_slot_e_finaliza_1x(self):
        import db
        chamadas = {"digest": 0}
        orig = db.registrar_digest
        db.registrar_digest = lambda *a, **k: chamadas.__setitem__("digest", chamadas["digest"] + 1)
        try:
            self.daily.enviar_slot("12h")            # 1º slot: envia + finaliza (status->SENT)
            self.assertEqual(len(self.enviados), 1)   # A (12h)
            self.enviados.clear()
            self.daily.enviar_slot("08h")            # 2º slot: SENT não bloqueia -> ainda envia
            self.assertEqual(len(self.enviados), 1)   # B (08h)
            self.assertEqual(self.enviados[0]["nome"], "B")
        finally:
            db.registrar_digest = orig
        self.assertEqual(chamadas["digest"], 1)       # finalização rodou 1x só (guardada)

    def test_troca_de_slot_nao_reenvia(self):
        self.daily.enviar_slot("12h")                 # A (12h) recebe
        self.assertEqual(len(self.enviados), 1)
        a_id = self.enviados[0]["id"]
        self.enviados.clear()
        self.s.definir_slot(a_id, "20h")              # A troca de horário no meio do dia
        self.daily.enviar_slot("20h")                 # 20h dispara depois
        self.assertEqual(self.enviados, [])           # claim já usado -> NÃO reenvia

    def test_catch_up_envia_uma_vez(self):
        reg = self.s.adicionar("C", "5543000000003")
        self.s.definir_slot(reg["id"], "20h")
        c = self.s.por_id(reg["id"])
        self.assertTrue(self.daily.enviar_catch_up(c))              # envia
        self.assertEqual([e["nome"] for e in self.enviados], ["C"])
        self.enviados.clear()
        self.assertFalse(self.daily.enviar_catch_up(c))            # já recebeu -> não repete
        self.assertEqual(self.enviados, [])

    def test_catch_up_sem_rascunho_nao_envia(self):
        self.daily._ctx_do_dia = lambda hoje: None                 # simula dia sem rascunho / não útil
        reg = self.s.adicionar("D", "5543000000004")
        d = self.s.por_id(reg["id"])
        self.assertFalse(self.daily.enviar_catch_up(d))
        self.assertEqual(self.enviados, [])


class TestMeusDadosHorario(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("DSCURSO_DATA", tempfile.mkdtemp())
        import site_web
        importlib.reload(site_web)
        self.sw = site_web

    def test_seletor_horario_render(self):
        sub = {"nome": "A", "email": "a@x.com", "whatsapp": "5543", "slot_envio": "12h"}
        h = self.sw.pagina_meus_dados(sub, slots=["07h", "08h", "12h"], slot_atual="12h")
        self.assertIn("salvar_horario", h)
        self.assertIn('value="12h"', h)
        self.assertIn("07h", h)


class TestLedgerDia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        for m in ("config", "db", "subscribers"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, subscribers
        importlib.reload(config); importlib.reload(db); importlib.reload(subscribers)
        self.cfg, self.db, self.s = config, db, subscribers
        self.s._migrado = False
        db.init()

    def test_registrar_envio_assinante_idempotente(self):
        self.assertTrue(self.db.registrar_envio_assinante("2026-07-24", "sub_1"))    # 1ª vez
        self.assertFalse(self.db.registrar_envio_assinante("2026-07-24", "sub_1"))   # repetido
        self.assertTrue(self.db.registrar_envio_assinante("2026-07-24", "sub_2"))    # outro sub
        self.assertTrue(self.db.registrar_envio_assinante("2026-07-25", "sub_1"))    # outro dia

    def test_ja_enviou_hoje(self):
        self.assertFalse(self.db.ja_enviou_hoje("2026-07-24", "sub_1"))
        self.db.registrar_envio_assinante("2026-07-24", "sub_1")
        self.assertTrue(self.db.ja_enviou_hoje("2026-07-24", "sub_1"))

    def test_slot_ja_enviou(self):
        self.assertFalse(self.db.slot_ja_enviou("2026-07-24", "08h"))
        self.db.registrar_envio_slot("2026-07-24", "08h")
        self.assertTrue(self.db.slot_ja_enviou("2026-07-24", "08h"))
        self.assertFalse(self.db.slot_ja_enviou("2026-07-24", "12h"))


if __name__ == "__main__":
    unittest.main()
