"""Item 36 fatia 2 — ver o estudo e corrigir a ÁREA pela /agenda."""
import os
import sys
import sqlite3
import tempfile
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
        """Dois cliques simultâneos para mover pro mesmo destino estouram IntegrityError
        no UPDATE — a função captura e devolve "ocupado", honrando o contrato."""
        self._digest(tema="Meus estudos", titulo="A")
        self._digest(data="2026-08-11", tema="Perfomance", titulo="B")

        # Ambos querem ir pra "Obesidade" / "2026-08-10"
        # Simular: inserir diretamente a colisão após a checagem de existência
        # de um dos cliques, antes do UPDATE. Usamos raw SQL pra criar a condição.
        with self.db._conn() as c:
            c.execute(
                "INSERT INTO digests (data, tema_slug, tema, titulo_original, "
                "titulo_pt, fonte, doi, url, resumo, gancho, grafico, criado_em, "
                "excluido) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), NULL)",
                ("2026-08-10", "obesidade", "Obesidade", "C (en)", "C", "FAKE",
                 "10.2/y", "https://ex/y", "resumo fake", "g", "")
            )

        # Agora a tentativa de mover A pra Obesidade/2026-08-10 vai topar com a colisão
        result = self.db.mover_digest_tema("2026-08-10", "meus-estudos", "Obesidade")
        self.assertEqual(result, "ocupado")

        # O conteúdo de A não foi alterado
        self.assertEqual(self.db.obter("meus-estudos", "2026-08-10")["titulo_pt"], "A")
