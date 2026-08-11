"""O resumo do assinante saiu com "*Mensagem prática para Dr. Diego:*".

Diego, 2026-08-10, mostrando o texto que foi pro PDF e pra tela de aprovação:
`*Mensagem prática para Dr. Diego:* Para pacientes em GLP-1RA, a perda de massa magra...`

**Causa:** o `SYS_ESTUDO` abre com "Você escreve o resumo de UM estudo científico para o
Dr. Diego (médico)". O modelo juntou isso com a seção "O que muda na prática" e criou um
cabeçalho endereçado a ele. Como o texto é gerado UMA vez e enviado idêntico a todos
(`daily._pdf_master` é o "PDF único do dia"), TODO assinante lê o nome do Diego.

**Por que precisa de teste e não só do conserto:** o vazamento é silencioso. Nada quebra,
nenhum log acusa, a suíte fica verde — só um assinante reparando. E o nome é fácil de
voltar sem querer, porque descrever o leitor como "o Dr. Diego" é o jeito natural de
escrever o prompt.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Prompts que produzem texto LIDO PELO ASSINANTE.
_PROMPTS_DE_CONTEUDO = ("SYS_ESTUDO", "SYS_APROF", "SYS_CURSO", "SYS_MENC")

# "Dr. Fulano" / "Dra. Fulana" — nome próprio endereçando o leitor.
_TITULO_E_NOME = re.compile(r"\bDra?\.?\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+")


class TestPromptsNaoNomeiamPessoa(unittest.TestCase):
    def setUp(self):
        import resumo_diario
        self.rd = resumo_diario

    def test_nenhum_prompt_de_conteudo_cita_o_diego(self):
        for nome in _PROMPTS_DE_CONTEUDO:
            with self.subTest(prompt=nome):
                self.assertNotIn("Diego", getattr(self.rd, nome))

    def test_nenhum_prompt_de_conteudo_endereca_um_doutor_pelo_nome(self):
        """Guarda genérica: trocar 'Dr. Diego' por 'Dr. Silva' não pode passar."""
        for nome in _PROMPTS_DE_CONTEUDO:
            with self.subTest(prompt=nome):
                achado = _TITULO_E_NOME.search(getattr(self.rd, nome))
                self.assertIsNone(achado, f"{nome} endereça {achado.group(0) if achado else ''}")

    def test_o_prompt_diario_diz_que_o_publico_e_plural(self):
        """Só tirar o nome perderia a calibragem de tom (é texto de médico p/ médico).
        O prompt tem que descrever o PÚBLICO no lugar da pessoa."""
        self.assertIn("médicos", self.rd.SYS_ESTUDO.lower())

    def test_o_prompt_diario_proibe_endereçar_o_leitor_pelo_nome(self):
        """A trava explícita: sem ela o modelo volta a inventar 'Mensagem para Dr. X'
        a partir de qualquer outra pista do material."""
        p = self.rd.SYS_ESTUDO.lower()
        self.assertIn("nome", p)
        self.assertTrue("não se dirija" in p or "nunca se dirija" in p or "não enderece" in p,
                        "SYS_ESTUDO precisa proibir explicitamente endereçar o leitor")

    def test_o_prompt_da_triagem_tambem_nao_cita_o_nome(self):
        """A saída é só ENTRA/LIXO, então não vaza — mas o nome ali é a mesma tentação,
        e alguém pode copiar essa linha pra um prompt que vaza."""
        fonte = open(os.path.join(os.path.dirname(__file__), "..", "resumo_diario.py"),
                     encoding="utf-8").read()
        self.assertNotIn("prática clínica do Dr. Diego", fonte)


class TestCapaDoEbookFalaComQuemLe(unittest.TestCase):
    """A capa do ebook dizia "Compilado para o Dr. Diego Silva" — e quem lê é o assinante.

    Mesma classe do bug do resumo, achada no mesmo grep. A distinção que importa:
    assinatura/marca no rodapé é CORRETA (o produto é dele); dizer que o material foi
    feito PARA outra pessoa, na capa de quem pagou, não é.
    """

    def _capa(self):
        import ebook_curso
        return ebook_curso.capa_html(0, 12, "ago/2026") if hasattr(ebook_curso, "capa_html") else None

    def test_a_capa_nao_diz_que_foi_compilado_pra_outra_pessoa(self):
        fonte = open(os.path.join(os.path.dirname(__file__), "..", "ebook_curso.py"),
                     encoding="utf-8").read()
        # a linha da capa; a marca do rodapé/título continua valendo
        self.assertNotIn("Compilado para o Dr. Diego", fonte)

    def test_a_marca_do_rodape_continua(self):
        """Tirar o nome da capa não pode levar junto a assinatura, que é a marca."""
        fonte = open(os.path.join(os.path.dirname(__file__), "..", "ebook_curso.py"),
                     encoding="utf-8").read()
        self.assertIn("Dr. Diego Silva", fonte)


class TestAsAreasDeInteresseContinuamNoPrompt(unittest.TestCase):
    """Tirar o nome não pode levar junto o que o nome carregava de útil."""

    def setUp(self):
        import resumo_diario
        self.rd = resumo_diario

    def test_a_triagem_mantem_os_temas_da_pratica(self):
        fonte = open(os.path.join(os.path.dirname(__file__), "..", "resumo_diario.py"),
                     encoding="utf-8").read()
        for termo in ("GLP-1", "TRT", "lipedema", "performance"):
            self.assertIn(termo, fonte)

    def test_o_prompt_diario_mantem_a_estrutura_das_secoes(self):
        for secao in ("RESUMO DIRETO", "Vieses e limitações", "O que muda na prática"):
            self.assertIn(secao, self.rd.SYS_ESTUDO)


if __name__ == "__main__":
    unittest.main()
