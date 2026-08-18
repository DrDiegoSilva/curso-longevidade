"""Item 36 fatia 2 — ver o estudo e corrigir a ÁREA pela /agenda."""
import os
import sys
import tempfile
import unittest
from unittest import mock

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
        """Corrida real entre dois cliques: a checagem prévia de destino livre não
        vê nada, mas o UPDATE estoura erro de integridade porque OUTRA transação
        inseriu a linha colidente nesse meio-tempo. `mover_digest_tema` (a função
        de PRODUÇÃO, sem cópia) precisa reconferir em conexão nova e devolver
        "ocupado" — sem o `try/except _integrity_error()` em volta do UPDATE em
        `app/db.py`, a exceção sobe crua e quebra o contrato de 4 estados.

        Reproduz a corrida sem threads (determinístico, sem depender de
        escalonamento): dublamos só o `execute` da conexão para que, no exato
        instante em que a função de produção for rodar o UPDATE, uma conexão
        SEPARADA e real grave a linha destino primeiro — pela própria
        `registrar_digest`, não por SQL reinventado à mão. O dublê decide QUANDO
        a segunda escrita acontece; quem decide o que fazer com isso continua
        sendo `mover_digest_tema` de verdade.
        """
        self._digest(tema="Meus estudos", titulo="A")

        sql_update = "UPDATE digests SET tema=?, tema_slug=? WHERE data=? AND tema_slug=?"
        real_execute = self.db._Wrap.execute

        def execute_dublado(wrap_self, sql, params=()):
            if sql == sql_update:
                # É agora — bem antes de deixar o UPDATE prosseguir — que o
                # "segundo clique" vence a corrida: grava o destino por uma
                # conexão de verdade, distinta da que mover_digest_tema segura
                # aberta (senão não haveria erro de integridade nenhum pra pegar).
                self.db.registrar_digest(
                    {"tema": "Obesidade", "titulo": "B", "titulo_original": "B (en)",
                     "doi": "10.2/y", "fonte": "NEJM", "url": "https://ex/y"},
                    {"titulo_pt": "B", "resumo": "outro resumo", "gancho": "g", "grafico": ""},
                    data="2026-08-10")
            return real_execute(wrap_self, sql, params)

        with mock.patch.object(self.db._Wrap, "execute", execute_dublado):
            resultado = self.db.mover_digest_tema("2026-08-10", "meus-estudos", "Obesidade")

        self.assertEqual(resultado, "ocupado")
        # Origem intacta e destino com o que a "outra transação" gravou —
        # nada foi movido nem sobrescrito por causa da corrida.
        self.assertEqual(self.db.obter("meus-estudos", "2026-08-10")["titulo_pt"], "A")
        self.assertEqual(self.db.obter("obesidade", "2026-08-10")["titulo_pt"], "B")
