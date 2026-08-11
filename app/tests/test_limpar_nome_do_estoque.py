"""Consertar o prompt não conserta o ESTOQUE já gerado.

Os estudos que já estão na fila (`reserva_resumos`) e os já enviados (`digests`) têm
"*Mensagem prática para Dr. Diego:*" gravado dentro do texto. O conserto do `SYS_ESTUDO`
só vale pras próximas gerações — sem uma limpeza, o Diego vê o mesmo bug amanhã.

Mesma lição do kit de MKT: *"estoque antigo sai degradado até girar"*.

A limpeza é CIRÚRGICA: tira o endereçamento, preserva a conduta clínica. Não regenera
com IA — o conteúdo já foi curado, e regenerar custaria caro e mudaria texto aprovado.
"""
import importlib
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# O texto real que o Diego mostrou em 2026-08-10.
REAL = ("*Mensagem prática para Dr. Diego:*\n"
        "Para pacientes em GLP-1RA, a perda de massa magra é real mas modesta (~3,3% em 2 anos).")


class TestTirarONome(unittest.TestCase):
    def setUp(self):
        import limpeza
        importlib.reload(limpeza)
        self.lp = limpeza

    def test_o_caso_real_do_diego(self):
        out = self.lp.sem_endereçamento(REAL)
        self.assertNotIn("Diego", out)
        self.assertIn("*Mensagem prática:*", out)
        self.assertIn("~3,3% em 2 anos", out)      # a conduta clínica fica intacta

    def test_variantes_de_escrita(self):
        for antes, depois in [
            ("Mensagem prática para Dr. Diego:", "Mensagem prática:"),
            ("Mensagem prática para o Dr. Diego:", "Mensagem prática:"),
            ("Mensagem prática para Dr. Diego Silva:", "Mensagem prática:"),
            ("Conduta para o Dr. Diego Silva:", "Conduta:"),
            ("Recado para a Dra. Diego:", "Recado:"),
        ]:
            with self.subTest(antes=antes):
                self.assertEqual(self.lp.sem_endereçamento(antes), depois)

    def test_texto_limpo_nao_e_tocado(self):
        """Idempotência importa: a ferramenta pode ser apertada mais de uma vez."""
        limpo = "*O que muda na prática:*\nExercício resistido desde o início."
        self.assertEqual(self.lp.sem_endereçamento(limpo), limpo)
        self.assertEqual(self.lp.sem_endereçamento(self.lp.sem_endereçamento(REAL)),
                         self.lp.sem_endereçamento(REAL))

    def test_a_assinatura_da_marca_nao_e_removida(self):
        """"Dr. Diego Silva · CRM-PR 54310" no rodapé é a MARCA — tem que ficar."""
        marca = "Estudo revisado por Dr. Diego Silva · CRM-PR 54310"
        self.assertEqual(self.lp.sem_endereçamento(marca), marca)

    def test_nome_no_meio_de_frase_nao_e_mutilado(self):
        """Só o padrão 'para <o> Dr. Nome:' de CABEÇALHO sai. Prosa fica."""
        prosa = "O estudo foi apresentado por Dr. Diego Silva no congresso."
        self.assertEqual(self.lp.sem_endereçamento(prosa), prosa)

    def test_vazio_e_none_nao_explodem(self):
        self.assertEqual(self.lp.sem_endereçamento(""), "")
        self.assertEqual(self.lp.sem_endereçamento(None), "")


class TestLimparOEstoque(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import db as _db
        importlib.reload(_db)
        self.db = _db
        self.db.init()
        import limpeza
        importlib.reload(limpeza)
        self.lp = limpeza

    def test_limpa_a_reserva_e_conta(self):
        sujo = self.db.salvar_reserva({"tema": "Obesidade", "titulo_pt": "T", "resumo": REAL})
        limpo = self.db.salvar_reserva({"tema": "Obesidade", "titulo_pt": "T2",
                                        "resumo": "sem endereçamento"})
        n = self.lp.limpar_estoque()
        self.assertEqual(n, 1)                                   # só o sujo contou
        self.assertNotIn("Diego", self.db.obter_reserva(sujo)["resumo"])
        self.assertEqual(self.db.obter_reserva(limpo)["resumo"], "sem endereçamento")

    def test_preserva_titulo_e_tema(self):
        rid = self.db.salvar_reserva({"tema": "Obesidade", "titulo_pt": "Título", "resumo": REAL})
        self.lp.limpar_estoque()
        r = self.db.obter_reserva(rid)
        self.assertEqual(r["titulo_pt"], "Título")
        self.assertEqual(r["tema"], "Obesidade")

    def test_rodar_de_novo_nao_conta_nada(self):
        self.db.salvar_reserva({"tema": "Obesidade", "titulo_pt": "T", "resumo": REAL})
        self.assertEqual(self.lp.limpar_estoque(), 1)
        self.assertEqual(self.lp.limpar_estoque(), 0)             # idempotente

    def test_estoque_vazio_nao_explode(self):
        self.assertEqual(self.lp.limpar_estoque(), 0)


if __name__ == "__main__":
    unittest.main()
