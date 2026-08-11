"""Item 36, fatia 1 — corrigir a ÁREA do estudo na tela do /revisar.

Nasceu do estudo de 2026-08-10, subido à mão antes da detecção automática de área:
saiu com "MEUS ESTUDOS" na capa e não havia NENHUM lugar no sistema pra corrigir.

O que faz isto valer: `daily.enviar_slot` monta o PDF na HORA do envio (08h) lendo
`artigo["tema"]` do rascunho. Então corrigir a área no rascunho conserta de uma vez a
capa do PDF, o texto do WhatsApp e a página do portal.
"""
import importlib
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DSCURSO_DATA", tempfile.mkdtemp())

AREAS = ["Obesidade", "Hormonal", "Lipedema", "Performance", "Longevidade"]


def _rascunho(tema="Meus estudos", pdf_path="/data/drafts/2026-08-11-preview.pdf",
              reserva_id="res_1"):
    return {"data": "2026-08-11", "status": "DRAFT", "review_token": "tok",
            "artigo": {"titulo": "T", "tema": tema, "fonte": "NEJM", "doi": "", "url": "",
                       "data": "2026-08-01"},
            "resumo": "resumo", "pdf_path": pdf_path, "reserva_id": reserva_id}


class TestAreasEValida(unittest.TestCase):
    """A guarda: /revisar é rota pública protegida só pelo token — um POST forjado não
    pode carimbar área arbitrária na capa do PDF do assinante."""

    def setUp(self):
        import area_estudo
        importlib.reload(area_estudo)
        self.ae = area_estudo

    def test_areas_sao_as_do_temas_config(self):
        self.assertEqual(sorted(self.ae.areas()), sorted(AREAS))

    def test_area_da_lista_passa(self):
        self.assertEqual(self.ae.valida("Obesidade", "Meus estudos"), "Obesidade")

    def test_area_inventada_e_ignorada(self):
        self.assertEqual(self.ae.valida("Cardiologia", "Obesidade"), "Obesidade")

    def test_area_vazia_e_no_op(self):
        self.assertEqual(self.ae.valida("", "Obesidade"), "Obesidade")

    def test_area_ausente_e_no_op(self):
        self.assertEqual(self.ae.valida(None, "Obesidade"), "Obesidade")

    def test_nao_normaliza_caixa_nem_espaco(self):
        """'obesidade' minúsculo NÃO vira 'Obesidade' de graça: a chave tem que bater com
        a do temas_config, senão `_tema_meta` devolve o nome cru como rótulo da capa —
        exatamente o bug do 'MEUS ESTUDOS'. Espaço em volta, sim, é aparado."""
        self.assertEqual(self.ae.valida("  Obesidade  ", "Hormonal"), "Obesidade")
        self.assertEqual(self.ae.valida("obesidade", "Hormonal"), "Hormonal")


class TestAplicarNoRascunho(unittest.TestCase):
    def setUp(self):
        import area_estudo
        importlib.reload(area_estudo)
        self.ae = area_estudo

    def test_grava_no_rascunho_e_na_reserva(self):
        r = _rascunho(tema="Meus estudos")
        with mock.patch("db.atualizar_reserva") as m_upd:
            mudou = self.ae.aplicar_no_rascunho(r, "Obesidade")
        self.assertTrue(mudou)
        self.assertEqual(r["artigo"]["tema"], "Obesidade")
        m_upd.assert_called_once_with("res_1", tema="Obesidade")

    def test_area_invalida_nao_toca_em_nada(self):
        r = _rascunho(tema="Obesidade")
        with mock.patch("db.atualizar_reserva") as m_upd:
            mudou = self.ae.aplicar_no_rascunho(r, "Cardiologia")
        self.assertFalse(mudou)
        self.assertEqual(r["artigo"]["tema"], "Obesidade")
        self.assertEqual(r["pdf_path"], "/data/drafts/2026-08-11-preview.pdf")
        m_upd.assert_not_called()

    def test_mudar_area_limpa_o_pdf_preview(self):
        """O preview das 18h já está no disco com a capa ERRADA. Sem invalidar, o Diego
        clica em 'Ver PDF', vê 'MEUS ESTUDOS' de novo e conclui que não funcionou.
        O serve.py já regenera sob demanda quando pdf_path está vazio."""
        r = _rascunho(tema="Meus estudos")
        with mock.patch("db.atualizar_reserva"):
            self.ae.aplicar_no_rascunho(r, "Longevidade")
        self.assertEqual(r["pdf_path"], "")

    def test_mesma_area_preserva_o_pdf_preview(self):
        """Aprovar sem mexer na área não pode jogar fora um PDF bom e pagar Chromium à toa."""
        r = _rascunho(tema="Obesidade")
        with mock.patch("db.atualizar_reserva") as m_upd:
            mudou = self.ae.aplicar_no_rascunho(r, "Obesidade")
        self.assertFalse(mudou)
        self.assertEqual(r["pdf_path"], "/data/drafts/2026-08-11-preview.pdf")
        m_upd.assert_not_called()

    def test_rascunho_sem_reserva_nao_explode(self):
        """Rascunho vindo de candidato/clássico não tem reserva_id."""
        r = _rascunho(tema="Meus estudos", reserva_id=None)
        with mock.patch("db.atualizar_reserva") as m_upd:
            mudou = self.ae.aplicar_no_rascunho(r, "Performance")
        self.assertTrue(mudou)
        self.assertEqual(r["artigo"]["tema"], "Performance")
        m_upd.assert_not_called()

    def test_falha_do_banco_nao_derruba_a_correcao(self):
        """Gravar na reserva é acabamento; o que sai amanhã é o rascunho. Se o banco
        falhar, a capa do PDF ainda tem que sair certa."""
        r = _rascunho(tema="Meus estudos")
        with mock.patch("db.atualizar_reserva", side_effect=RuntimeError("supabase off")):
            mudou = self.ae.aplicar_no_rascunho(r, "Hormonal")
        self.assertTrue(mudou)
        self.assertEqual(r["artigo"]["tema"], "Hormonal")

    def test_rascunho_sem_artigo_nao_explode(self):
        r = {"data": "2026-08-11", "resumo": "x"}
        with mock.patch("db.atualizar_reserva"):
            self.assertFalse(self.ae.aplicar_no_rascunho(r, "Obesidade"))


class TestDraftStoreAplica(unittest.TestCase):
    """A área viaja junto com Aprovar/Salvar edição (decisão do Diego): um passo só."""

    def setUp(self):
        import draft_store
        importlib.reload(draft_store)
        self.ds = draft_store

    def _com_rascunho(self, r):
        return (mock.patch.object(self.ds, "carregar", return_value=r),
                mock.patch.object(self.ds, "salvar"))

    def test_aprovar_com_area_grava_o_tema_novo(self):
        r = _rascunho(tema="Meus estudos")
        p1, p2 = self._com_rascunho(r)
        with p1, p2 as m_salvar, mock.patch("db.atualizar_reserva"):
            out = self.ds.aplicar("2026-08-11", "aprovar", area="Obesidade")
        self.assertEqual(out["status"], "APPROVED")
        self.assertEqual(out["artigo"]["tema"], "Obesidade")
        self.assertEqual(m_salvar.call_args[0][0]["artigo"]["tema"], "Obesidade")

    def test_editar_grava_texto_e_area(self):
        r = _rascunho(tema="Meus estudos")
        p1, p2 = self._com_rascunho(r)
        with p1, p2, mock.patch("db.atualizar_reserva"):
            out = self.ds.aplicar("2026-08-11", "editar", texto="novo texto", area="Lipedema")
        self.assertEqual(out["status"], "EDITED")
        self.assertEqual(out["resumo"], "novo texto")
        self.assertEqual(out["artigo"]["tema"], "Lipedema")

    def test_sem_area_continua_funcionando_como_antes(self):
        """Compatibilidade: nao_enviar/regerar_audio não mandam área."""
        r = _rascunho(tema="Obesidade")
        p1, p2 = self._com_rascunho(r)
        with p1, p2:
            out = self.ds.aplicar("2026-08-11", "nao_enviar")
        self.assertEqual(out["status"], "SKIPPED")
        self.assertEqual(out["artigo"]["tema"], "Obesidade")

    def test_nao_enviar_ignora_a_area_do_formulario(self):
        """Vetar o dia não é hora de mexer na área — e o form manda o campo assim mesmo."""
        r = _rascunho(tema="Obesidade")
        p1, p2 = self._com_rascunho(r)
        with p1, p2, mock.patch("db.atualizar_reserva") as m_upd:
            out = self.ds.aplicar("2026-08-11", "nao_enviar", area="Lipedema")
        self.assertEqual(out["artigo"]["tema"], "Obesidade")
        m_upd.assert_not_called()

    def test_acao_invalida_continua_levantando(self):
        r = _rascunho()
        p1, p2 = self._com_rascunho(r)
        with p1, p2, self.assertRaises(ValueError):
            self.ds.aplicar("2026-08-11", "sei_la", area="Obesidade")


class TestPaginaRevisao(unittest.TestCase):
    def setUp(self):
        import review_web
        importlib.reload(review_web)
        self.rw = review_web

    def test_select_traz_as_areas_com_a_atual_marcada(self):
        html = self.rw.pagina_revisao(_rascunho(tema="Obesidade"), areas=AREAS)
        self.assertIn('name="area"', html)
        for a in AREAS:
            self.assertIn(f'value="{a}"', html)
        self.assertIn('<option value="Obesidade" selected>', html)
        self.assertNotIn('<option value="Hormonal" selected>', html)

    def test_tema_fora_da_lista_aparece_como_opcao_extra(self):
        """Sem isto, abrir a tela e apertar Aprovar sem tocar em nada trocaria a área
        silenciosamente pro primeiro item da lista."""
        html = self.rw.pagina_revisao(_rascunho(tema="Meus estudos"), areas=AREAS)
        self.assertIn('<option value="Meus estudos" selected>', html)
        self.assertIn('value="Obesidade"', html)

    def test_tema_vazio_vira_opcao_de_sem_area(self):
        html = self.rw.pagina_revisao(_rascunho(tema=""), areas=AREAS)
        self.assertIn('<option value="" selected>', html)

    def test_escapa_o_tema(self):
        html = self.rw.pagina_revisao(_rascunho(tema='x"><script>'), areas=AREAS)
        self.assertNotIn("<script>", html)

    def test_o_select_esta_dentro_do_formulario(self):
        """Fora do <form> o campo não é postado e a correção some sem avisar."""
        html = self.rw.pagina_revisao(_rascunho(), areas=AREAS)
        corpo = html.split("<form", 1)[1].split("</form>", 1)[0]
        self.assertIn('name="area"', corpo)

    def test_sem_areas_nao_quebra_a_pagina(self):
        html = self.rw.pagina_revisao(_rascunho())
        self.assertIn("Aprovar", html)


class TestChegaNoEnvio(unittest.TestCase):
    """Integração: a área corrigida tem que virar a capa/badge do que sai às 08h."""

    def setUp(self):
        import daily
        importlib.reload(daily)
        self.daily = daily

    def test_tema_do_rascunho_vira_o_tmeta_do_envio(self):
        r = _rascunho(tema="Longevidade")
        r["titulo_pt"] = "Título PT"
        with mock.patch.object(self.daily, "_audio_master", return_value=None), \
             mock.patch.object(self.daily, "_pdf_master", return_value=None):
            ctx = self.daily._montar_ctx("2026-08-11", r)
        self.assertEqual(ctx["tmeta"]["rotulo"], "Longevidade")
        self.assertEqual(ctx["tmeta"]["emoji"], "🧬")

    def test_area_errada_e_o_que_produzia_MEUS_ESTUDOS_na_capa(self):
        """Guarda de regressão do bug de origem: tema desconhecido vira rótulo cru."""
        r = _rascunho(tema="Meus estudos")
        r["titulo_pt"] = "Título PT"
        with mock.patch.object(self.daily, "_audio_master", return_value=None), \
             mock.patch.object(self.daily, "_pdf_master", return_value=None):
            ctx = self.daily._montar_ctx("2026-08-11", r)
        self.assertEqual(ctx["tmeta"]["rotulo"], "Meus estudos")


class TestDbAtualizarReservaTema(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        import db as _db
        importlib.reload(_db)
        self.db = _db
        self.db.init()

    def test_atualiza_o_tema(self):
        rid = self.db.salvar_reserva({"tema": "Meus estudos", "titulo_pt": "T", "resumo": "r"})
        self.db.atualizar_reserva(rid, tema="Obesidade")
        self.assertEqual(self.db.obter_reserva(rid)["tema"], "Obesidade")

    def test_tema_nao_apaga_titulo_nem_resumo(self):
        rid = self.db.salvar_reserva({"tema": "Meus estudos", "titulo_pt": "T", "resumo": "r"})
        self.db.atualizar_reserva(rid, tema="Hormonal")
        res = self.db.obter_reserva(rid)
        self.assertEqual(res["titulo_pt"], "T")
        self.assertEqual(res["resumo"], "r")

    def test_continua_editando_titulo_e_resumo_sem_tema(self):
        rid = self.db.salvar_reserva({"tema": "Obesidade", "titulo_pt": "T", "resumo": "r"})
        self.db.atualizar_reserva(rid, titulo_pt="T2", resumo="r2")
        res = self.db.obter_reserva(rid)
        self.assertEqual((res["titulo_pt"], res["resumo"], res["tema"]), ("T2", "r2", "Obesidade"))


class TestJaEnviadoNaoCorrige(unittest.TestCase):
    """Depois das 08h a correção de área é um NO-OP silencioso — e silencioso é o pior
    jeito de falhar aqui, porque o item 36 nasceu exatamente de "corrigi e não mudou".

    Por que não muda: `_pdf_master` cacheia `{hoje}-master.pdf` no 1º slot, então um slot
    posterior reusa o PDF com a capa velha; só o badge do WhatsApp mudaria, e o estudo
    sairia inconsistente. O arquivo do portal (`digests`) já foi escrito em `_finalizar_dia`.
    Corrigir estudo já enviado é a fatia 2 do item 36.
    """

    def setUp(self):
        import area_estudo
        importlib.reload(area_estudo)
        self.ae = area_estudo

    def test_rascunho_enviado_nao_aceita_area_nova(self):
        r = _rascunho(tema="Meus estudos")
        r["status"] = "SENT"
        with mock.patch("db.atualizar_reserva") as m_upd:
            mudou = self.ae.aplicar_no_rascunho(r, "Obesidade")
        self.assertFalse(mudou)
        self.assertEqual(r["artigo"]["tema"], "Meus estudos")
        self.assertEqual(r["pdf_path"], "/data/drafts/2026-08-11-preview.pdf")
        m_upd.assert_not_called()

    def test_pode_corrigir_diz_nao_pro_enviado(self):
        self.assertFalse(self.ae.pode_corrigir({"status": "SENT"}))
        self.assertTrue(self.ae.pode_corrigir({"status": "DRAFT"}))
        self.assertTrue(self.ae.pode_corrigir({"status": "APPROVED"}))
        self.assertTrue(self.ae.pode_corrigir({}))

    def test_draft_store_tambem_barra(self):
        import draft_store
        importlib.reload(draft_store)
        r = _rascunho(tema="Meus estudos")
        r["status"] = "SENT"
        with mock.patch.object(draft_store, "carregar", return_value=r), \
             mock.patch.object(draft_store, "salvar"), \
             mock.patch("db.atualizar_reserva"):
            out = draft_store.aplicar("2026-08-11", "aprovar", area="Obesidade")
        self.assertEqual(out["artigo"]["tema"], "Meus estudos")


class TestConfigQuebradaNaoDerrubaAprovar(unittest.TestCase):
    """Aprovar/editar agora PASSA pelo temas_config em toda chamada (antes só o envio
    das 18h/08h lia esse arquivo). Config ilegível não pode impedir o curador de aprovar
    o estudo de amanhã."""

    def setUp(self):
        import area_estudo
        importlib.reload(area_estudo)
        self.ae = area_estudo

    def test_config_ilegivel_devolve_lista_vazia(self):
        with mock.patch("builtins.open", side_effect=OSError("sumiu")):
            self.assertEqual(self.ae.areas(), [])

    def test_config_ilegivel_nao_derruba_a_aprovacao(self):
        r = _rascunho(tema="Obesidade")
        with mock.patch("builtins.open", side_effect=OSError("sumiu")):
            self.assertFalse(self.ae.aplicar_no_rascunho(r, "Hormonal"))
        self.assertEqual(r["artigo"]["tema"], "Obesidade")   # sem lista, ninguém muda nada


class _RotaStub:
    """Stub mínimo pro `self` de do_GET/do_POST — a rota /revisar vive INLINE no
    do_POST, não é método próprio. Mesmo padrão do `_RouteStub` de test_admin_precos."""

    def __init__(self, path, body=b""):
        import io
        self.path = path
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.headers = {"Content-Length": str(len(body)),
                        "Content-Type": "application/x-www-form-urlencoded"}

    def _html(self, s, code=200):
        return {"code": code, "body": s}

    def send_response(self, code):
        self.code = code

    def send_header(self, *a):
        pass

    def end_headers(self):
        pass


class TestPdfPreviewNaoRegeneraSempre(unittest.TestCase):
    """Zerar o `pdf_path` invalida o preview velho — mas o /pdf tem que GRAVAR o caminho
    regenerado, senão o rascunho fica "sempre inválido" e cada clique em "📄 Ver PDF"
    paga um Chromium (até 3 tentativas x 120s). Era raro antes; a correção de área
    tornaria isso o estado normal de todo rascunho corrigido."""

    def setUp(self):
        import serve
        self.serve = serve
        self.tmp = tempfile.mkdtemp()

    def _get_pdf(self, r):
        import config
        with mock.patch.object(config, "drafts_dir", return_value=self.tmp), \
             mock.patch("draft_store.carregar", return_value=r), \
             mock.patch("draft_store.salvar") as m_salvar, \
             mock.patch("pdf.gerar_pdf", side_effect=lambda h, out: open(out, "wb").write(b"%PDF")) as m_gen:
            self.serve.Handler.do_GET(_RotaStub("/pdf/2026-08-11"))
        return m_gen, m_salvar

    def test_regenera_e_grava_o_caminho_no_rascunho(self):
        r = _rascunho(tema="Obesidade", pdf_path="")
        m_gen, m_salvar = self._get_pdf(r)
        self.assertEqual(m_gen.call_count, 1)
        self.assertTrue(r["pdf_path"].endswith("2026-08-11-preview.pdf"))
        m_salvar.assert_called_once()

    def test_segundo_clique_reusa_o_pdf_em_vez_de_chamar_chromium(self):
        r = _rascunho(tema="Obesidade", pdf_path="")
        self._get_pdf(r)                       # 1º clique: regenera e grava
        m_gen, _ = self._get_pdf(r)            # 2º clique: arquivo existe e pdf_path está gravado
        self.assertEqual(m_gen.call_count, 0)


class TestFiacaoDaRota(unittest.TestCase):
    """A fiação do serve.py: sem isto, um campo com nome errado passaria em todos os
    testes de unidade e a correção de área simplesmente não chegaria no rascunho."""

    def setUp(self):
        import serve
        self.serve = serve

    def _post(self, campos):
        import urllib.parse as up
        return self.serve.Handler.do_POST(
            _RotaStub("/revisar/tok", up.urlencode(campos).encode("utf-8")))

    def test_post_aprovar_leva_a_area_ate_o_draft_store(self):
        r = _rascunho(tema="Meus estudos")
        with mock.patch("draft_store.por_token", return_value=r), \
             mock.patch("draft_store.aplicar") as m_aplicar:
            self._post({"acao": "aprovar", "texto": "t", "area": "Obesidade"})
        self.assertEqual(m_aplicar.call_args.kwargs.get("area"), "Obesidade")

    def test_estudo_ja_enviado_avisa_em_vez_de_dizer_feito(self):
        """"Feito ✅" numa correção que não corrige é a armadilha que criou o item 36."""
        r = _rascunho(tema="Meus estudos")
        r["status"] = "SENT"
        with mock.patch("draft_store.por_token", return_value=r), \
             mock.patch("draft_store.aplicar", return_value=r):
            out = self._post({"acao": "aprovar", "texto": "t", "area": "Obesidade"})
        self.assertNotIn("Feito", out["body"])
        self.assertIn("já foi enviado", out["body"])

    def test_nao_enviar_continua_valendo_depois_do_1o_slot(self):
        """Freio de emergência: o estudo saiu no slot das 08h e o Diego quer barrar os
        slots seguintes (`enviar_slot` só respeita SKIPPED). Barrar o POST inteiro num
        rascunho SENT tiraria isso dele."""
        r = _rascunho(tema="Obesidade")
        r["status"] = "SENT"
        with mock.patch("draft_store.por_token", return_value=r), \
             mock.patch("draft_store.aplicar") as m_aplicar:
            out = self._post({"acao": "nao_enviar"})
        m_aplicar.assert_called_once()
        self.assertNotIn("já foi enviado", out["body"])   # não caiu na guarda de área

    def test_get_manda_as_areas_pra_pagina(self):
        r = _rascunho(tema="Meus estudos")
        with mock.patch("draft_store.por_token", return_value=r):
            out = self.serve.Handler.do_GET(_RotaStub("/revisar/tok"))
        self.assertIn('name="area"', out["body"])
        self.assertIn('value="Obesidade"', out["body"])
        self.assertIn('<option value="Meus estudos" selected>', out["body"])


if __name__ == "__main__":
    unittest.main()
