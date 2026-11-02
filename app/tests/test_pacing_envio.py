"""Pausa entre as mensagens de um MESMO envio (texto -> PDF -> áudio), não só entre
assinantes diferentes -- achado do Diego (2026-11-02): "as msgs estão saindo tudo em
conjunto de uma vez" é exatamente o padrão de rajada que provedores de WhatsApp tratam
como automação suspeita e pode derrubar o número. Standalone."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPacingEstudoDiario(unittest.TestCase):
    def setUp(self):
        import importlib
        import config, daily
        importlib.reload(config)
        importlib.reload(daily)
        self.cfg, self.daily = config, daily

    def _ctx(self, master_pdf="estudo.pdf", audio_bytes=b"mp3"):
        return {
            "r": {"resumo": "resumo"},
            "art": {"url": "https://doi.org/10.1/x", "tema": "Obesidade"},
            "titulo": "Título",
            "tmeta": {},
            "fresco": False,
            "master_pdf": master_pdf,
            "audio_bytes": audio_bytes,
        }

    def test_pausa_entre_texto_pdf_e_audio(self):
        with mock.patch.object(self.daily.deliver, "enviar_texto", return_value=None), \
             mock.patch.object(self.daily.deliver, "enviar_pdf", return_value=None), \
             mock.patch.object(self.daily.deliver, "enviar_audio", return_value=None), \
             mock.patch("time.sleep") as m_sleep:
            self.daily._enviar_estudo_para("5543999990000", "Fulano", self._ctx())
        # texto -> (pausa) -> pdf -> (pausa) -> áudio = 2 pausas.
        self.assertEqual(m_sleep.call_count, 2)
        for chamada in m_sleep.call_args_list:
            self.assertEqual(chamada.args[0], self.cfg.SEND_DELAY_SEC)

    def test_sem_pdf_nem_audio_nao_pausa(self):
        with mock.patch.object(self.daily.deliver, "enviar_texto", return_value=None), \
             mock.patch("time.sleep") as m_sleep:
            self.daily._enviar_estudo_para("5543999990000", "Fulano",
                                           self._ctx(master_pdf=None, audio_bytes=None))
        m_sleep.assert_not_called()

    def test_pausa_usa_o_mesmo_atraso_configurado(self):
        os.environ["DSCURSO_SEND_DELAY_SEC"] = "7"
        try:
            import importlib
            importlib.reload(self.cfg)
            importlib.reload(self.daily)
            with mock.patch.object(self.daily.deliver, "enviar_texto", return_value=None), \
                 mock.patch.object(self.daily.deliver, "enviar_pdf", return_value=None), \
                 mock.patch.object(self.daily.deliver, "enviar_audio", return_value=None), \
                 mock.patch("time.sleep") as m_sleep:
                self.daily._enviar_estudo_para("5543999990000", "Fulano", self._ctx())
            self.assertTrue(all(c.args[0] == 7.0 for c in m_sleep.call_args_list))
        finally:
            os.environ.pop("DSCURSO_SEND_DELAY_SEC", None)


class TestPacingTrilha(unittest.TestCase):
    def setUp(self):
        import importlib
        import tempfile
        import config, db, subscribers, trilha
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        for m in (config, db, subscribers, trilha):
            importlib.reload(m)
        db.init()
        self.cfg, self.db, self.subs, self.t = config, db, subscribers, trilha
        self.t.semear()
        self.t.definir_produto_ativo("empreendedorismo")

    def _sub(self):
        reg = self.subs.adicionar("Fulano", "5543999990000")
        self.subs.definir_slot(reg["id"], "08h")
        return self.subs.por_id(reg["id"])

    def _fake_enviar(self, w, p, caption=""):
        return None

    def _fake_render(self, html, out):
        open(out, "w").write("pdf")
        return out

    def _fake_texto(self, w, msg):
        return None

    def test_pausa_entre_texto_e_pdf_da_mesma_peca(self):
        sub = self._sub()
        with mock.patch("time.sleep") as m_sleep:
            ok = self.t.enviar_para(sub, enviar_fn=self._fake_enviar,
                                    render_fn=self._fake_render, texto_fn=self._fake_texto)
        self.assertTrue(ok)
        # 1 peça (empreendedorismo = 1 por envio): só a pausa intra-envio, texto -> pdf.
        self.assertEqual(m_sleep.call_count, 1)
        self.assertEqual(m_sleep.call_args_list[0].args[0], self.cfg.SEND_DELAY_SEC)


if __name__ == "__main__":
    unittest.main()
