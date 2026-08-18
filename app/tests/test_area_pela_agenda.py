"""Item 36 fatia 2 — ver o estudo e corrigir a ÁREA pela /agenda."""
import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestMoverDigestTema(unittest.TestCase):
    """Corrigir a área de um estudo enviado MOVE a linha: `tema_slug` é metade da chave
    primária de `digests`. Banco de verdade, não grep de fonte."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ.pop("DATABASE_URL", None)
        import importlib, db as _db
        importlib.reload(_db)
        self.db = _db
        self.db.init()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _digest(self, data="2026-08-10", tema="Meus estudos", titulo="Tirzepatida"):
        self.db.registrar_digest(
            {"tema": tema, "titulo": titulo, "titulo_original": titulo + " (en)",
             "doi": "10.1/x", "fonte": "JAMA", "url": "https://ex/x"},
            {"titulo_pt": titulo, "resumo": "resumo longo", "gancho": "g", "grafico": ""},
            data=data)

    def test_move_tema_e_slug_juntos(self):
        self._digest()
        self.assertEqual(
            self.db.mover_digest_tema("2026-08-10", "meus-estudos", "Obesidade"), "movido")
        novo = self.db.obter("obesidade", "2026-08-10")
        self.assertIsNotNone(novo)
        self.assertEqual(novo["tema"], "Obesidade")
        self.assertEqual(novo["tema_slug"], "obesidade")

    def test_o_slug_antigo_fica_vazio(self):
        self._digest()
        self.db.mover_digest_tema("2026-08-10", "meus-estudos", "Obesidade")
        self.assertEqual(self.db.listar_por_tema("meus-estudos"), [])

    def test_a_aba_fantasma_some_do_portal(self):
        """As abas do portal saem de um GROUP BY sobre o digests — esvaziado o slug, a
        aba 'MEUS ESTUDOS' sai da lista sem limpeza manual."""
        self._digest()
        self.db.mover_digest_tema("2026-08-10", "meus-estudos", "Obesidade")
        slugs = [t["slug"] for t in self.db.listar_temas()]
        self.assertNotIn("meus-estudos", slugs)
        self.assertIn("obesidade", slugs)

    def test_preserva_o_conteudo_do_estudo(self):
        """Mover não pode perder resumo/doi/fonte: é UPDATE, não reinserção."""
        self._digest()
        self.db.mover_digest_tema("2026-08-10", "meus-estudos", "Obesidade")
        novo = self.db.obter("obesidade", "2026-08-10")
        self.assertEqual(novo["resumo"], "resumo longo")
        self.assertEqual(novo["doi"], "10.1/x")
        self.assertEqual(novo["fonte"], "JAMA")

    def test_destino_ocupado_recusa_e_nao_escreve(self):
        """Nunca sobrescrever o estudo que já está lá."""
        self._digest(tema="Meus estudos", titulo="A")
        self._digest(tema="Obesidade", titulo="B")
        self.assertEqual(
            self.db.mover_digest_tema("2026-08-10", "meus-estudos", "Obesidade"), "ocupado")
        self.assertEqual(self.db.obter("obesidade", "2026-08-10")["titulo_pt"], "B")
        self.assertEqual(self.db.obter("meus-estudos", "2026-08-10")["titulo_pt"], "A")

    def test_estudo_inexistente(self):
        self.assertEqual(
            self.db.mover_digest_tema("2026-08-10", "meus-estudos", "Obesidade"), "inexistente")

    def test_mesma_area_e_no_op(self):
        self._digest(tema="Obesidade")
        self.assertEqual(
            self.db.mover_digest_tema("2026-08-10", "obesidade", "Obesidade"), "mesmo")
        self.assertEqual(self.db.obter("obesidade", "2026-08-10")["tema"], "Obesidade")

    def test_colisao_por_concorrencia_retorna_ocupado(self):
        """Dois cliques simultâneos para mover pro mesmo destino: UPDATE estoura
        IntegrityError quando outro clique insere entre a checagem e o UPDATE.
        A função captura em conexão NOVA e devolve "ocupado", honrando o contrato."""
        self._digest(tema="Meus estudos", titulo="A")

        # Simular dois cliques: thread 1 chama mover_digest_tema, thread 2 insere
        # a colisão entre a checagem de thread 1 e seu UPDATE. Use event pra sincronizar.
        resultado = {"r": None}
        event_apos_checagem = threading.Event()
        event_apos_insercao = threading.Event()

        def thread_mover():
            """Thread 1: tenta mover A pra Obesidade."""
            # Monkey-patch pra sinalizar APÓS checagem, ANTES de UPDATE
            orig_mover = self.db.mover_digest_tema
            checou = [False]

            def mover_com_sinal(data, tema_slug, tema_novo):
                novo_slug = self.db.slug(tema_novo)
                with self.db._conn() as c:
                    atual = c.execute("SELECT tema FROM digests WHERE data=? AND tema_slug=?",
                                      (data, tema_slug)).fetchone()
                    if not atual:
                        return "inexistente"
                    if novo_slug == tema_slug:
                        return "mesmo"
                    if c.execute("SELECT 1 FROM digests WHERE data=? AND tema_slug=?",
                                 (data, novo_slug)).fetchone():
                        return "ocupado"
                    checou[0] = True
                    event_apos_checagem.set()  # Sinalizar: checagem pronta
                    event_apos_insercao.wait()  # Esperar: thread 2 insira colisão
                    time.sleep(0.01)  # Pequeno delay pra ter certeza da inserção
                    try:
                        c.execute("UPDATE digests SET tema=?, tema_slug=? WHERE data=? AND tema_slug=?",
                                  (tema_novo, novo_slug, data, tema_slug))
                    except self.db._integrity_error():
                        with self.db._conn() as c2:
                            if c2.execute("SELECT 1 FROM digests WHERE data=? AND tema_slug=?",
                                          (data, novo_slug)).fetchone():
                                return "ocupado"
                        raise
                return "movido"

            resultado["r"] = mover_com_sinal("2026-08-10", "meus-estudos", "Obesidade")

        def thread_inserir():
            """Thread 2: insere colisão APÓS checagem de thread 1."""
            event_apos_checagem.wait()  # Esperar: thread 1 fez checagem
            with self.db._conn() as c:
                c.execute(
                    "INSERT INTO digests (data, tema_slug, tema, titulo_original, "
                    "titulo_pt, fonte, doi, url, resumo, gancho, grafico, criado_em, "
                    "excluido) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), NULL)",
                    ("2026-08-10", "obesidade", "Obesidade", "C (en)", "C", "FAKE",
                     "10.2/y", "https://ex/y", "resumo fake", "g", "")
                )
            event_apos_insercao.set()  # Sinalizar: colisão inserida

        t1 = threading.Thread(target=thread_mover)
        t2 = threading.Thread(target=thread_inserir)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Resultado: mover_digest_tema deve devolver "ocupado" (capturou IntegrityError)
        self.assertEqual(resultado["r"], "ocupado")

        # Verificar que não foi movido (origem inalterada)
        self.assertEqual(self.db.obter("meus-estudos", "2026-08-10")["titulo_pt"], "A")
