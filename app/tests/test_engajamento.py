"""Testes do rastreio de leitura no banco (mensagens_enviadas): registrar envio, aplicar
status do webhook (sem retroceder), agregar por assinante. Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _recarregar(tmp):
    os.environ["DSCURSO_DATA"] = tmp
    os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(tmp, "t.db")
    for m in ("config", "db"):
        if m in sys.modules:
            importlib.reload(sys.modules[m])
    import config, db
    importlib.reload(config); importlib.reload(db)
    db.init()
    return db


class TestRegistrarMensagemEnviada(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = _recarregar(self.tmp)

    def test_registra_e_comeca_como_enviado(self):
        self.db.registrar_mensagem_enviada("M1", "sub-a", "estudo_texto")
        resumo = self.db.resumo_engajamento()
        self.assertEqual(resumo["sub-a"]["enviado"], 1)

    def test_sem_msg_id_nao_registra(self):
        self.db.registrar_mensagem_enviada("", "sub-a", "estudo_texto")
        self.db.registrar_mensagem_enviada(None, "sub-a", "estudo_texto")
        self.assertEqual(self.db.resumo_engajamento(), {})

    def test_id_repetido_nao_duplica(self):
        self.db.registrar_mensagem_enviada("M1", "sub-a", "estudo_texto")
        self.db.registrar_mensagem_enviada("M1", "sub-a", "estudo_texto")   # ex.: retry de envio
        resumo = self.db.resumo_engajamento()
        self.assertEqual(resumo["sub-a"]["enviado"], 1)


class TestAtualizarStatusMensagem(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = _recarregar(self.tmp)
        self.db.registrar_mensagem_enviada("M1", "sub-a", "estudo_texto")

    def test_avanca_de_enviado_pra_lida(self):
        self.db.atualizar_status_mensagem("M1", "lida")
        resumo = self.db.resumo_engajamento()
        self.assertEqual(resumo["sub-a"], {"enviado": 0, "entregue": 0, "lida": 1, "reproduzida": 0})

    def test_nao_retrocede_de_lida_pra_entregue(self):
        """Webhooks de provedor podem chegar fora de ordem -- `entregue` depois de `lida`
        não pode apagar que a mensagem já foi lida."""
        self.db.atualizar_status_mensagem("M1", "lida")
        self.db.atualizar_status_mensagem("M1", "entregue")
        resumo = self.db.resumo_engajamento()
        self.assertEqual(resumo["sub-a"]["lida"], 1)
        self.assertEqual(resumo["sub-a"]["entregue"], 0)

    def test_id_desconhecido_nao_quebra(self):
        self.db.atualizar_status_mensagem("NAO-EXISTE", "lida")   # não levanta
        self.assertEqual(self.db.resumo_engajamento()["sub-a"]["lida"], 0)

    def test_status_fora_do_vocabulario_nao_quebra(self):
        self.db.atualizar_status_mensagem("M1", "reagiu-com-emoji")
        self.assertEqual(self.db.resumo_engajamento()["sub-a"]["enviado"], 1)


class TestResumoEngajamento(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = _recarregar(self.tmp)

    def test_agrega_por_assinante(self):
        self.db.registrar_mensagem_enviada("M1", "sub-a", "estudo_texto")
        self.db.registrar_mensagem_enviada("M2", "sub-a", "estudo_pdf")
        self.db.registrar_mensagem_enviada("M3", "sub-b", "estudo_texto")
        self.db.atualizar_status_mensagem("M1", "lida")
        resumo = self.db.resumo_engajamento()
        self.assertEqual(resumo["sub-a"]["lida"], 1)
        self.assertEqual(resumo["sub-a"]["enviado"], 1)
        self.assertEqual(resumo["sub-b"]["enviado"], 1)

    def test_filtro_desde_ignora_envios_antigos(self):
        self.db.registrar_mensagem_enviada("M1", "sub-a", "estudo_texto")
        with self.db._conn() as c:
            c.execute("UPDATE mensagens_enviadas SET enviado_em='2020-01-01' WHERE id='M1'")
        self.db.registrar_mensagem_enviada("M2", "sub-a", "estudo_texto")
        resumo = self.db.resumo_engajamento(desde="2026-01-01")
        self.assertEqual(resumo["sub-a"]["enviado"], 1)   # só M2 entra

    def test_vazio_nao_quebra(self):
        self.assertEqual(self.db.resumo_engajamento(), {})


if __name__ == "__main__":
    unittest.main()
