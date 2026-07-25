"""Task 9: preparar_18h a partir de CANDIDATO (JIT) e de CLÁSSICO (bancado) +
_finalizar_dia marcando os dois. Banco temp; mocks de rede/IA (resumo + WhatsApp)."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class _BaseTmpDb(unittest.TestCase):
    def setUp(self):   # padrão do repo (ver test_agenda_materializar.py)
        # guarda o ambiente anterior — outros arquivos de teste (ex.: test_site_web.py)
        # rodam sem inicializar o próprio banco e dependem do que sobrou no ambiente
        # de um teste anterior; restaurar no tearDown evita quebrar essa ordem alheia.
        self._env_antes = {k: os.environ.get(k) for k in ("DSCURSO_ARTIGOS_DB", "DSCURSO_DATA", "DATABASE_URL")}
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ.pop("DATABASE_URL", None)
        import importlib, config as _cfg; importlib.reload(_cfg)
        import db as _db; importlib.reload(_db)
        _db.init()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        for k, v in self._env_antes.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class TestPrepararClassico(_BaseTmpDb):
    def test_preparar_de_classico_usa_resumo_bancado(self):
        import daily, db
        cid = db.salvar_classico({"tema": "Obesidade", "titulo_pt": "STEP", "resumo": "resumo-bancado",
                                  "data": "2021-01-01", "citacoes": 4000})
        with mock.patch.object(daily.deliver, "enviar_curador"), \
             mock.patch.object(daily, "enviar_audio_preview"), \
             mock.patch.object(daily.content, "gerar_conteudo") as m_gc:
            r = daily._preparar_de_classico(cid)
            m_gc.assert_not_called()  # prova que usa o resumo bancado, não regenera
        self.assertEqual(r["resumo"], "resumo-bancado")     # NÃO regenerou (usa o banco)
        self.assertEqual(r.get("classico_id"), cid)

    def test_preparar_de_classico_none_se_sumiu(self):
        import daily
        with mock.patch.object(daily.deliver, "enviar_curador"), \
             mock.patch.object(daily, "enviar_audio_preview"):
            self.assertIsNone(daily._preparar_de_classico("id-que-nao-existe"))


class TestPrepararCandidato(_BaseTmpDb):
    def test_preparar_de_candidato_gera_resumo_jit(self):
        import daily, db
        db.salvar_candidatos([{"tema": "Obesidade", "titulo": "Estudo X", "chave": "k1",
                               "fonte": "NEJM", "doi": "10.1/x", "url": "http://x",
                               "data": "2026-01-01", "abstract": "abstract cru do artigo"}])
        cand_id = db.listar_candidatos(status="novo")[0]["id"]
        with mock.patch.object(daily.deliver, "enviar_curador"), \
             mock.patch.object(daily, "enviar_audio_preview"), \
             mock.patch.object(daily.content, "gerar_conteudo",
                               return_value={"titulo_pt": "Título PT", "resumo": "resumo-jit",
                                             "gancho": "gancho", "grafico": None}) as m_gc:
            r = daily._preparar_de_candidato(cand_id)
            m_gc.assert_called_once()
        art_passado = m_gc.call_args[0][0]
        self.assertEqual(art_passado["resumo"], "abstract cru do artigo")  # abstract -> resumo de entrada
        self.assertEqual(r["resumo"], "resumo-jit")          # veio do gerador (JIT), não do banco
        self.assertEqual(r.get("candidato_id"), cand_id)

    def test_preparar_de_candidato_none_se_sumiu(self):
        import daily
        with mock.patch.object(daily.deliver, "enviar_curador"), \
             mock.patch.object(daily, "enviar_audio_preview"):
            self.assertIsNone(daily._preparar_de_candidato("id-que-nao-existe"))


class TestFinalizarDiaCandidatoClassico(_BaseTmpDb):
    def _finalizar(self, hoje, r, tema="Obesidade"):
        import daily
        art = {"doi": "", "tema": tema}
        conteudo = {"titulo_pt": r.get("titulo_pt", "T"), "resumo": r.get("resumo", ""),
                    "gancho": "", "grafico": None}
        tmeta = {"rotulo": tema}
        # isola o teste do resto do pipeline de fechamento (fila local + aviso de estoque,
        # que por padrão chamaria deliver.enviar_admin — rede real)
        with mock.patch.object(daily.queue_store, "confirmar_envio"), \
             mock.patch.object(daily, "avisar_estoque_baixo"):
            daily._finalizar_dia(hoje, r, art, conteudo, tmeta)

    def test_finalizar_dia_marca_candidato_resumido(self):
        import db
        db.salvar_candidatos([{"tema": "Obesidade", "titulo": "Estudo X", "chave": "k2",
                               "abstract": "a"}])
        cand_id = db.listar_candidatos(status="novo")[0]["id"]
        hoje = "2026-01-02"
        self._finalizar(hoje, {"data": hoje, "candidato_id": cand_id, "resumo": "r"})
        self.assertEqual(db.listar_candidatos()[0]["status"], "resumido")

    def test_finalizar_dia_marca_classico_enviado(self):
        import db
        cid = db.salvar_classico({"tema": "Obesidade", "titulo_pt": "STEP", "resumo": "r",
                                  "data": "2021-01-01", "citacoes": 100})
        hoje = "2026-01-02"
        self._finalizar(hoje, {"data": hoje, "classico_id": cid, "resumo": "r"})
        cl = db.obter_classico(cid)
        self.assertEqual(cl["ultimo_envio"], hoje)   # NÃO deleta — só marca (reusável no próximo ciclo)
        self.assertIsNotNone(db.obter_classico(cid))


if __name__ == "__main__":
    unittest.main()
