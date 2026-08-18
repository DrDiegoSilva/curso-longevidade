"""Item 36 fatia 2 — ver o estudo e corrigir a ÁREA pela /agenda."""
import os
import sys
import tempfile
import unittest
import urllib.parse as up
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class _RotaStub:
    """Stub mínimo pro `self` de do_GET/do_POST — a rota /agenda vive INLINE no handler,
    não é método próprio."""

    def __init__(self, path, body=b""):
        import io
        self.path = path
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.headers = {"Content-Length": str(len(body)),
                        "Content-Type": "application/x-www-form-urlencoded"}

    def _html(self, s, code=200):
        return {"code": code, "body": s}

    def _redirect(self, url):
        return {"code": 302, "location": url}

    def _sessao(self):
        return None

    def send_response(self, code):
        self.code = code

    def send_header(self, *a):
        pass

    def end_headers(self):
        pass


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


class TestAplicarNoDigest(unittest.TestCase):
    """A camada de domínio: valida a área e delega. Sem banco — o db é dublê."""

    def test_area_valida_delega_pro_db(self):
        import area_estudo
        with mock.patch("area_estudo.areas", return_value=["Obesidade", "Longevidade"]), \
             mock.patch("db.mover_digest_tema", return_value="movido") as m:
            got = area_estudo.aplicar_no_digest("2026-08-10", "meus-estudos", "Obesidade")
        self.assertEqual(got, "movido")
        self.assertEqual(m.call_args.args, ("2026-08-10", "meus-estudos", "Obesidade"))

    def test_area_fora_do_config_nao_chega_no_banco(self):
        """Falha fechada, igual ao `valida`: é assim que 'MEUS ESTUDOS' foi parar num PDF."""
        import area_estudo
        with mock.patch("area_estudo.areas", return_value=["Obesidade"]), \
             mock.patch("db.mover_digest_tema") as m:
            got = area_estudo.aplicar_no_digest("2026-08-10", "meus-estudos", "obesidade")
        self.assertEqual(got, "invalida")
        m.assert_not_called()

    def test_area_vazia_nao_chega_no_banco(self):
        import area_estudo
        with mock.patch("area_estudo.areas", return_value=["Obesidade"]), \
             mock.patch("db.mover_digest_tema") as m:
            self.assertEqual(
                area_estudo.aplicar_no_digest("2026-08-10", "meus-estudos", ""), "invalida")
        m.assert_not_called()

    def test_repassa_o_codigo_do_banco_sem_traduzir(self):
        import area_estudo
        for codigo in ("ocupado", "inexistente", "mesmo"):
            with mock.patch("area_estudo.areas", return_value=["Obesidade"]), \
                 mock.patch("db.mover_digest_tema", return_value=codigo):
                self.assertEqual(
                    area_estudo.aplicar_no_digest("2026-08-10", "x", "Obesidade"), codigo)


class TestSlotViewCarregaOEstudo(unittest.TestCase):
    """O `digest_do_dia` já faz SELECT * — o `_slot_view` é que jogava fora tudo menos
    tema/título. Sem estes campos o painel não tem o que mostrar."""

    def _slot_view(self, dia, digest):
        """Roda o GET da /agenda com o banco dublado e devolve o slot daquele dia.

        A janela é dublada com uma data FIXA no passado. Usar "ontem" faria o teste pular
        sozinho toda segunda-feira (ontem = domingo, não é dia de envio) — teste que não
        roda é teste que não existe.
        """
        import serve, config
        capturado = {}

        def _fake_pagina(semanas, estoque, token, msg=""):
            capturado["slots"] = [s for sem in semanas for s in sem]
            return "<html></html>"

        with mock.patch("db.init"), \
             mock.patch("db.digest_do_dia", return_value=digest), \
             mock.patch("db.agenda_listar", return_value={}), \
             mock.patch("db.contar_reserva_pronto", return_value=0), \
             mock.patch("daily.materializar_agenda"), \
             mock.patch("daily._dias_envio",
                        return_value={"segunda", "terca", "quarta", "quinta", "sexta"}), \
             mock.patch("agenda_plan.semanas_do_mes", return_value=[dia]), \
             mock.patch("site_web.pagina_agenda", side_effect=_fake_pagina), \
             mock.patch.object(config, "ADMIN_TOKEN", "tok"):
            serve.Handler.do_GET(_RotaStub("/agenda?token=tok"))
        return [s for s in capturado["slots"] if s["data"] == dia]

    def test_dia_passado_carrega_resumo_fonte_doi_e_slug(self):
        digest = {"tema": "Meus estudos", "tema_slug": "meus-estudos",
                  "titulo_pt": "Tirzepatida", "titulo_original": "Tirzepatide",
                  "resumo": "resumo longo", "fonte": "JAMA", "doi": "10.1/x"}
        achados = self._slot_view("2026-08-10", digest)   # data fixa, sempre no passado
        self.assertEqual(len(achados), 1)
        s = achados[0]
        self.assertEqual(s["tema_slug"], "meus-estudos")
        self.assertEqual(s["resumo"], "resumo longo")
        self.assertEqual(s["fonte"], "JAMA")
        self.assertEqual(s["doi"], "10.1/x")
        self.assertEqual(s["titulo_original"], "Tirzepatide")
        self.assertTrue(s["passado"])


class TestJanelaRecuada(unittest.TestCase):
    def test_o_get_da_agenda_pede_a_semana_anterior(self):
        """Sem `semanas_atras=1`, numa segunda-feira a tela não tem dia passado nenhum."""
        import serve, config
        with mock.patch("db.init"), \
             mock.patch("db.digest_do_dia", return_value=None), \
             mock.patch("db.agenda_listar", return_value={}), \
             mock.patch("db.contar_reserva_pronto", return_value=0), \
             mock.patch("daily.materializar_agenda"), \
             mock.patch("daily._dias_envio",
                        return_value={"segunda", "terca", "quarta", "quinta", "sexta"}), \
             mock.patch("site_web.pagina_agenda", return_value="<html></html>"), \
             mock.patch("agenda_plan.semanas_do_mes",
                        return_value=["2026-08-10"]) as m_janela, \
             mock.patch.object(config, "ADMIN_TOKEN", "tok"):
            serve.Handler.do_GET(_RotaStub("/agenda?token=tok"))
        self.assertEqual(m_janela.call_args.kwargs.get("semanas_atras"), 1)

    def test_materializar_nao_recua(self):
        """`daily.materializar_agenda` decide que dias PREENCHER — recuar criaria slot no
        passado. Teste de comportamento, não grep de fonte: o mesmo trecho aparece em mais
        de um lugar e o grep passa com uma chamada quebrada."""
        import daily
        with mock.patch("agenda_plan.semanas_do_mes", return_value=[]) as m, \
             mock.patch("daily._dias_envio",
                        return_value={"segunda", "terca", "quarta", "quinta", "sexta"}), \
             mock.patch("db.init"):
            try:
                daily.materializar_agenda()
            except Exception:
                pass                      # a janela vazia pode abortar cedo; o que importa
        self.assertTrue(m.called)         # é COMO ela foi pedida
        self.assertEqual(m.call_args.kwargs.get("semanas_atras", 0), 0)


class TestPainelDoDiaPassado(unittest.TestCase):
    """Âncoras com a FRASE INTEIRA — trecho curto casa por acidente (a lição das sete
    asserções falsas da tela de custos)."""

    def _card(self, **extra):
        import site_web
        s = {"data": "2026-08-10", "tipo": "enviado", "tema": "MEUS ESTUDOS",
             "titulo": "Tirzepatida e massa magra", "fixado": 0, "passado": True,
             "tema_slug": "meus-estudos", "titulo_original": "Tirzepatide and lean mass",
             "resumo": "Ensaio randomizado com 342 participantes.",
             "fonte": "JAMA", "doi": "10.1001/jama.2026.123"}
        s.update(extra)
        with mock.patch("area_estudo.areas",
                        return_value=["Obesidade", "Longevidade", "Performance"]):
            return site_web._slot_card(s, "tok", "")

    def test_mostra_o_estudo(self):
        h = self._card()
        self.assertIn("Ensaio randomizado com 342 participantes.", h)
        self.assertIn("JAMA", h)
        self.assertIn("10.1001/jama.2026.123", h)
        self.assertIn("Tirzepatide and lean mass", h)

    def test_a_area_atual_fora_do_config_vem_selecionada(self):
        """'MEUS ESTUDOS' não é chave do temas_config. Sem entrar como opção selecionada,
        o form mandaria uma área diferente sem o curador ter pedido nada."""
        h = self._card()
        self.assertIn('<option value="MEUS ESTUDOS" selected>MEUS ESTUDOS</option>', h)

    def test_traz_as_areas_do_config(self):
        h = self._card()
        for a in ("Obesidade", "Longevidade", "Performance"):
            self.assertIn(f'<option value="{a}">{a}</option>', h)

    def test_area_atual_do_config_nao_duplica(self):
        h = self._card(tema="Obesidade")
        self.assertEqual(h.count('value="Obesidade"'), 1)
        self.assertIn('<option value="Obesidade" selected>Obesidade</option>', h)

    def test_a_fiacao_do_form(self):
        h = self._card()
        self.assertIn('<input type="hidden" name="acao" value="corrigir_area_digest">', h)
        self.assertIn('<input type="hidden" name="slug" value="meus-estudos">', h)
        self.assertIn('<input type="hidden" name="data" value="2026-08-10">', h)
        self.assertIn('name="area"', h)

    def test_avisa_que_o_pdf_entregue_nao_muda(self):
        """Aviso que promete efeito que não acontece foi o erro pego na revisão do bloco
        fixado do dossiê."""
        h = self._card()
        self.assertIn("O PDF que já foi enviado não muda", h)

    def test_dia_passado_sem_estudo_nao_ganha_painel(self):
        h = self._card(titulo="", tema="", tema_slug="", resumo="")
        self.assertNotIn("corrigir_area_digest", h)
        self.assertIn('class="slot passado"', h)

    def test_dia_passado_com_titulo_mas_sem_tema_slug_nao_ganha_painel(self):
        """Correção ao brief: existe dia passado com `titulo` (slot da tabela `agenda`,
        sem envio confirmado) mas SEM `tema_slug`/resumo/fonte/doi — esse é o caso (b)
        que a Task 4 não preenche a partir do `digests`. Usar `titulo` como porteiro
        abriria um painel vazio cujo form posta `slug=""`: um botão Salvar que não faz
        nada. O porteiro certo é `tema_slug`, que só existe quando o estudo saiu de
        verdade (caso (a))."""
        h = self._card(tema_slug="", resumo="", fonte="", doi="")
        self.assertNotIn("corrigir_area_digest", h)
        self.assertIn('class="slot passado"', h)

    def test_dia_futuro_continua_sem_painel(self):
        import site_web
        s = {"data": "2026-08-20", "tipo": "reserva", "tema": "Obesidade",
             "titulo": "T", "fixado": 0}
        h = site_web._slot_card(s, "tok", "")
        self.assertNotIn("corrigir_area_digest", h)
        self.assertIn("📌 Fixar", h)


class TestRotaCorrigirArea(unittest.TestCase):
    """A fiação: sem isto, um campo com nome errado passaria em todo teste de unidade e
    a correção simplesmente não chegaria no banco."""

    def _post(self, campos):
        """Manda o POST. Os dublês do domínio ficam no `with` de cada teste."""
        import urllib.parse as up, serve, config
        with mock.patch("db.init"), mock.patch.object(config, "ADMIN_TOKEN", "tok"), \
             mock.patch("daily._dias_envio",
                        return_value={"segunda", "terca", "quarta", "quinta", "sexta"}):
            return serve.Handler.do_POST(
                _RotaStub("/agenda", up.urlencode(campos).encode("utf-8")))

    def test_leva_data_slug_e_area_ate_o_dominio(self):
        with mock.patch("area_estudo.aplicar_no_digest", return_value="movido") as m:
            out = self._post({"token": "tok", "acao": "corrigir_area_digest",
                              "data": "2026-08-10", "slug": "meus-estudos",
                              "area": "Obesidade"})
        self.assertEqual(m.call_args.args, ("2026-08-10", "meus-estudos", "Obesidade"))
        self.assertIn("rea%20corrigida", out["location"])

    def test_destino_ocupado_nomeia_o_estudo_que_esta_la(self):
        with mock.patch("area_estudo.aplicar_no_digest", return_value="ocupado"), \
             mock.patch("db.slug", return_value="obesidade"), \
             mock.patch("db.obter", return_value={"titulo_pt": "Semaglutida e sono"}):
            out = self._post({"token": "tok", "acao": "corrigir_area_digest",
                              "data": "2026-08-10", "slug": "meus-estudos",
                              "area": "Obesidade"})
        self.assertIn("Semaglutida", up.unquote(out["location"]))

    def test_area_invalida_avisa(self):
        with mock.patch("area_estudo.aplicar_no_digest", return_value="invalida"):
            out = self._post({"token": "tok", "acao": "corrigir_area_digest",
                              "data": "2026-08-10", "slug": "x", "area": "lixo"})
        self.assertIn("reconheci", up.unquote(out["location"]))

    def test_dia_sem_estudo_nao_explode(self):
        with mock.patch("area_estudo.aplicar_no_digest", return_value="inexistente"):
            out = self._post({"token": "tok", "acao": "corrigir_area_digest",
                              "data": "2026-08-10", "slug": "x", "area": "Obesidade"})
        self.assertEqual(out["code"], 302)
        self.assertIn("achei", up.unquote(out["location"]))

    def test_sem_token_da_403(self):
        import urllib.parse as up_, serve, config
        with mock.patch("db.init"), mock.patch.object(config, "ADMIN_TOKEN", "tok"), \
             mock.patch("area_estudo.aplicar_no_digest") as m:
            out = serve.Handler.do_POST(_RotaStub(
                "/agenda", up_.urlencode({"token": "errado", "acao": "corrigir_area_digest",
                                          "data": "2026-08-10", "slug": "x",
                                          "area": "Obesidade"}).encode("utf-8")))
        self.assertEqual(out["code"], 403)
        m.assert_not_called()

    def test_banco_fora_do_ar_avisa_em_vez_de_derrubar(self):
        with mock.patch("area_estudo.aplicar_no_digest",
                        side_effect=RuntimeError("sem conexão")):
            out = self._post({"token": "tok", "acao": "corrigir_area_digest",
                              "data": "2026-08-10", "slug": "x", "area": "Obesidade"})
        self.assertEqual(out["code"], 302)
        self.assertIn("guardar", up.unquote(out["location"]))

    def test_mover_continua_recusando_dia_passado(self):
        """A guarda do `mover` (só dia futuro) não pode ter afrouxado junto com a janela
        recuada. Comportamento, não grep: mandar um `mover` com data de ontem."""
        from datetime import datetime, timedelta
        ontem = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        amanha = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        with mock.patch("db.agenda_mover") as m:
            out = self._post({"token": "tok", "acao": "mover",
                              "data": ontem, "dest": amanha})
        m.assert_not_called()
        self.assertIn("inv", up.unquote(out["location"]).lower())
