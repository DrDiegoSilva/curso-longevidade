"""Testes do rastreio de leitura (webhook_whatsapp): extração de id no envio + tradução
do webhook de status (Z-API e Evolution), puro/testável, sem rede. Standalone."""
import os
import sys
import json
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import webhook_whatsapp as w


class TestExtrairIdZapi(unittest.TestCase):
    def test_pega_messageId(self):
        resp = json.dumps({"zaapId": "Z1", "messageId": "M1", "id": "M1"})
        self.assertEqual(w.extrair_id_zapi(resp), "M1")

    def test_sem_messageId_cai_pro_id(self):
        resp = json.dumps({"id": "M2"})
        self.assertEqual(w.extrair_id_zapi(resp), "M2")

    def test_json_invalido_nao_quebra(self):
        self.assertIsNone(w.extrair_id_zapi("nao e json"))

    def test_vazio_nao_quebra(self):
        self.assertIsNone(w.extrair_id_zapi(""))
        self.assertIsNone(w.extrair_id_zapi(None))


class TestExtrairIdEvolution(unittest.TestCase):
    def test_pega_key_id(self):
        resp = json.dumps({"key": {"id": "3EB0X", "fromMe": True}, "status": "PENDING"})
        self.assertEqual(w.extrair_id_evolution(resp), "3EB0X")

    def test_sem_key_nao_quebra(self):
        self.assertIsNone(w.extrair_id_evolution(json.dumps({"status": "PENDING"})))

    def test_json_invalido_nao_quebra(self):
        self.assertIsNone(w.extrair_id_evolution("nao e json"))


class TestDecidirStatusZapi(unittest.TestCase):
    def test_lida_singular(self):
        out = w.decidir_status_zapi({"status": "READ", "messageId": "M1"})
        self.assertEqual(out, [("M1", "lida")])

    def test_entregue_em_lote(self):
        out = w.decidir_status_zapi({"status": "RECEIVED", "ids": ["M1", "M2"]})
        self.assertEqual(sorted(out), [("M1", "entregue"), ("M2", "entregue")])

    def test_reproduzida_audio(self):
        out = w.decidir_status_zapi({"status": "PLAYED", "messageId": "M9"})
        self.assertEqual(out, [("M9", "reproduzida")])

    def test_status_desconhecido_nao_quebra(self):
        self.assertEqual(w.decidir_status_zapi({"status": "ALGO_NOVO", "messageId": "M1"}), [])

    def test_sem_status_nao_quebra(self):
        self.assertEqual(w.decidir_status_zapi({}), [])

    def test_sem_id_nenhum_nao_quebra(self):
        self.assertEqual(w.decidir_status_zapi({"status": "READ"}), [])


class TestDecidirStatusEvolution(unittest.TestCase):
    def test_ack_4_e_lida(self):
        payload = {"data": {"key": {"id": "3EB0X"}, "update": {"status": 4}}}
        self.assertEqual(w.decidir_status_evolution(payload), [("3EB0X", "lida")])

    def test_ack_3_e_entregue(self):
        payload = {"data": {"key": {"id": "3EB0X"}, "update": {"status": 3}}}
        self.assertEqual(w.decidir_status_evolution(payload), [("3EB0X", "entregue")])

    def test_ack_5_e_reproduzida(self):
        payload = {"data": {"key": {"id": "3EB0X"}, "update": {"status": 5}}}
        self.assertEqual(w.decidir_status_evolution(payload), [("3EB0X", "reproduzida")])

    def test_ack_desconhecido_nao_quebra(self):
        payload = {"data": {"key": {"id": "3EB0X"}, "update": {"status": 0}}}
        self.assertEqual(w.decidir_status_evolution(payload), [])

    def test_payload_vazio_nao_quebra(self):
        self.assertEqual(w.decidir_status_evolution({}), [])
        self.assertEqual(w.decidir_status_evolution(None), [])


class _FakeDb:
    def __init__(self):
        self.chamadas = []

    def atualizar_status_mensagem(self, msg_id, status):
        self.chamadas.append((msg_id, status))


class _FakeDbRegistrar:
    def __init__(self):
        self.chamadas = []

    def registrar_mensagem_enviada(self, msg_id, subscriber_id, tipo):
        self.chamadas.append((msg_id, subscriber_id, tipo))


class TestRegistrarEnvio(unittest.TestCase):
    def setUp(self):
        # Outros arquivos de teste reloadam `config` (isolamento de env var); sem
        # reloadar `w` (webhook_whatsapp) junto, seu `config` interno fica preso ao
        # objeto ANTIGO e mutar WHATSAPP_BACKEND aqui não teria efeito nenhum nele --
        # mesma armadilha documentada em test_series.py.
        import importlib
        import config
        importlib.reload(config)
        importlib.reload(w)
        self.cfg = config
        self._backend0 = config.WHATSAPP_BACKEND

    def tearDown(self):
        self.cfg.WHATSAPP_BACKEND = self._backend0

    def test_extrai_id_zapi_e_grava(self):
        self.cfg.WHATSAPP_BACKEND = "zapi"
        fake = _FakeDbRegistrar()
        resp = json.dumps({"messageId": "M1"})
        w.registrar_envio(resp, "sub-a", "estudo_texto", db_mod=fake)
        self.assertEqual(fake.chamadas, [("M1", "sub-a", "estudo_texto")])

    def test_extrai_id_evolution_e_grava(self):
        self.cfg.WHATSAPP_BACKEND = "evolution"
        fake = _FakeDbRegistrar()
        resp = json.dumps({"key": {"id": "M2"}})
        w.registrar_envio(resp, "sub-a", "trilha_pdf", db_mod=fake)
        self.assertEqual(fake.chamadas, [("M2", "sub-a", "trilha_pdf")])

    def test_sem_subscriber_id_nao_grava(self):
        fake = _FakeDbRegistrar()
        w.registrar_envio(json.dumps({"messageId": "M1"}), "", "estudo_texto", db_mod=fake)
        self.assertEqual(fake.chamadas, [])

    def test_resposta_none_nao_quebra(self):
        fake = _FakeDbRegistrar()
        w.registrar_envio(None, "sub-a", "estudo_texto", db_mod=fake)
        self.assertEqual(fake.chamadas, [(None, "sub-a", "estudo_texto")])

    def test_resposta_nao_string_nao_quebra(self):
        # deliver.enviar_audio (backend != evolution) devolve None; distribuir pode
        # passar qualquer coisa -- nunca deve levantar.
        fake = _FakeDbRegistrar()
        w.registrar_envio({"nao": "e string"}, "sub-a", "estudo_audio", db_mod=fake)
        self.assertEqual(fake.chamadas, [(None, "sub-a", "estudo_audio")])


class TestProcessar(unittest.TestCase):
    def setUp(self):
        import config, importlib
        importlib.reload(config)
        importlib.reload(w)
        self.cfg = config
        self._backend0 = config.WHATSAPP_BACKEND

    def tearDown(self):
        self.cfg.WHATSAPP_BACKEND = self._backend0

    def test_processa_pelo_backend_zapi(self):
        self.cfg.WHATSAPP_BACKEND = "zapi"
        fake = _FakeDb()
        w.processar({"status": "READ", "messageId": "M1"}, db_mod=fake)
        self.assertEqual(fake.chamadas, [("M1", "lida")])

    def test_processa_pelo_backend_evolution(self):
        self.cfg.WHATSAPP_BACKEND = "evolution"
        fake = _FakeDb()
        w.processar({"data": {"key": {"id": "M1"}, "update": {"status": 4}}}, db_mod=fake)
        self.assertEqual(fake.chamadas, [("M1", "lida")])

    def test_payload_maluco_nao_quebra(self):
        fake = _FakeDb()
        w.processar({"isto": ["nao", "e", "o", "formato", "esperado"]}, db_mod=fake)
        self.assertEqual(fake.chamadas, [])

    def test_none_nao_quebra(self):
        fake = _FakeDb()
        w.processar(None, db_mod=fake)
        self.assertEqual(fake.chamadas, [])


if __name__ == "__main__":
    unittest.main()
