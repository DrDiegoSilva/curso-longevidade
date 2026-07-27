"""Smoke test do render (site_web). Standalone: python3 app/tests/test_site_web.py"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DSCURSO_DATA", tempfile.mkdtemp())


class TestRender(unittest.TestCase):
    def setUp(self):
        import site_web
        self.s = site_web

    def test_landing(self):
        h = self.s.landing()
        self.assertIn("<!doctype html>", h)
        self.assertIn("melhor preço", h)   # badge do anual (D1)
        self.assertNotIn("20% OFF", h)     # badge antiga removida

    def test_landing_founder_vagas(self):
        import subscribers
        orig = subscribers.ativos
        subscribers.ativos = lambda: []                 # 0 ativos -> founder
        try:
            h = self.s.landing()
            self.assertIn("de 20 vagas", h)             # selo de lançamento
            self.assertIn("R$ 997", h)
        finally:
            subscribers.ativos = orig
        subscribers.ativos = lambda: [{}] * 20          # 20 ativos -> pós-founder
        try:
            h = self.s.landing()
            self.assertIn("R$ 1.497", h)
            self.assertNotIn("de 20 vagas", h)
        finally:
            subscribers.ativos = orig
        self.assertIn("Quero assinar", h)
        self.assertIn("CRM-PR 54310", h)
        self.assertIn("Obesidade", h)

    def test_entrar(self):
        self.assertIn("Enviar código", self.s.pagina_entrar("numero"))
        self.assertIn("Digite o código", self.s.pagina_entrar("codigo", whatsapp="55x"))
        self.assertIn("noindex", self.s.pagina_entrar("numero"))

    def test_hub_vazio_e_cheio(self):
        # hub_temas hoje é só o estado vazio do arquivo (redesign em 00443c7): quando
        # há temas, o serve.py abre direto no 1º tema via lista_tema (abas + agrupamento
        # por mês/semana fazem o papel do antigo "hub" de temas).
        self.assertIn("Ainda não há", self.s.hub_temas([]))
        meta = {"slug": "obesidade", "rotulo": "Obesidade", "emoji": "⚖️", "cor": "#14332a"}
        temas = [{"slug": "obesidade", "rotulo": "Obesidade", "emoji": "⚖️", "cor": "#14332a", "total": 2}]
        digs = [{"data": "2026-07-01", "titulo_pt": "Estudo A"}, {"data": "2026-07-08", "titulo_pt": "Estudo B"}]
        h = self.s.lista_tema(meta, digs, temas)
        self.assertIn("2 edições", h)
        self.assertIn("/artigos/obesidade", h)

    def test_lista_e_digest(self):
        meta = {"slug": "obesidade", "rotulo": "Obesidade", "emoji": "⚖️", "cor": "#14332a"}
        digs = [{"data": "2026-07-19", "titulo_pt": "Estudo X"}]
        self.assertIn("Estudo X", self.s.lista_tema(meta, digs))
        d = {"data": "2026-07-19", "titulo_pt": "Estudo X <b>", "resumo": "Linha *forte*",
             "gancho": "dica", "grafico": '{"barras":[{"rotulo":"A","valor":5}]}', "doi": "10/x", "fonte": "NEJM", "url": "http://x"}
        html = self.s.pagina_digest(meta, d)
        self.assertIn("Estudo X &lt;b&gt;", html)   # escapado
        self.assertIn("<strong>forte</strong>", html)
        self.assertIn("bar-fill", html)             # gráfico renderizado
        self.assertIn("Ver o estudo original", html)

    def test_assinar_pick(self):
        h = self.s.pagina_assinar(None)
        self.assertIn("Escolha seu plano", h)
        self.assertIn("/assinar?plano=anual", h)

    def test_assinar_form_mensal(self):
        h = self.s.pagina_assinar("mensal")
        # redesign do checkout (fdb4898) separou nome/descrição em tiles: "Pix" +
        # "R$ 99,00 à vista" (antes era um rótulo único "Pix à vista · ...").
        self.assertIn('<span class="pt-nome">Pix</span>', h)
        self.assertIn("à vista", h)
        self.assertIn("/mês · renova", h)                 # cartão mensal recorre (texto encurtado no redesign)
        self.assertIn('name="metodo"', h)
        self.assertIn('name="cupom"', h)
        self.assertNotIn('<select name="parcelas"', h)    # mensal não parcela

    def test_assinar_form_anual_parcelas(self):
        h = self.s.pagina_assinar("anual")
        self.assertIn('<select name="parcelas">', h)
        self.assertIn("12x de", h)

    def test_obrigado(self):
        self.assertIn("Quase lá", self.s.pagina_obrigado())

    def test_cancelar_fluxo(self):
        self.assertIn("Por que está cancelando", self.s.pagina_cancelar())
        self.assertIn("erro-teste", self.s.pagina_cancelar("erro-teste"))
        of = self.s.pagina_cancelar_oferta("caro demais")
        self.assertIn("mais um mês", of)
        self.assertIn('value="caro demais"', of)          # motivo preservado
        self.assertIn('name="acao" value="aceitar"', of)
        self.assertIn("cancelada", self.s.pagina_cancelado("2026-08-19"))

    def test_robots(self):
        self.assertIn("Disallow: /artigos", self.s.robots_txt())
        self.assertIn("Disallow: /assinar", self.s.robots_txt())

    def test_minha_enxuta_e_cards(self):
        html = self.s.pagina_minha({"nome": "Diego"}, admin=True)
        self.assertNotIn("Ir para o arquivo", html)     # não duplica o topo
        self.assertNotIn("Sair desta conta", html)
        self.assertIn("Meus dados", html)               # novo caminho
        self.assertIn("curbtn", html)                   # painel em botões-card
        self.assertIn("Agenda", html)                   # atalho novo incluído
        self.assertNotIn("Cancelar assinatura", html)   # cancelar saiu daqui

    def test_topbar_omite_minha_conta_na_propria(self):
        self.assertNotIn(">Minha conta<", self.s._topbar(True, atual="/minha"))
        self.assertIn(">Minha conta<", self.s._topbar(True, atual="/artigos"))

    def test_chip_score_faixas(self):
        # 3 scores cobrindo as 3 faixas de _chip_score (hi >=7, md >=4, lo <4).
        # markup EXATO — falha se os limiares ou o formato "{v:g}" mudarem.
        self.assertEqual(self.s._chip_score(8.5), '<span class="scorechip hi">★ 8.5</span>')
        self.assertEqual(self.s._chip_score(5.3), '<span class="scorechip md">5.3</span>')
        self.assertEqual(self.s._chip_score(2.7), '<span class="scorechip lo">2.7</span>')

    def test_meus_dados_blocos(self):
        html = self.s.pagina_meus_dados({"nome": "D", "email": "d@x.com", "whatsapp": "5543999990000"})
        self.assertIn("salvar_contato", html)     # form de nome/e-mail
        self.assertIn("iniciar_troca", html)      # trocar número
        self.assertIn("Cancelar assinatura", html)  # cancelar vive aqui agora
        # etapa de código aparece quando pedido
        self.assertIn("confirmar_troca", self.s.pagina_meus_dados(
            {"nome": "D", "whatsapp": "x"}, etapa_troca="codigo", novo_num="5541988887777"))

    def test_admin_dupla_confirmacao_remover(self):
        assin = [{"id": "abc", "nome": "Fulano", "whatsapp": "5543999990000", "status": "ATIVO"}]
        normal = self.s.pagina_admin(assin, token="tk")
        self.assertNotIn("remover_confirmar", normal)         # sem confirmar_id: nada apaga direto
        self.assertIn('name="acao" value="remover"', normal)  # botão da linha = pedir confirmação
        conf = self.s.pagina_admin(assin, token="tk", confirmar_id="abc")
        self.assertIn("remover_confirmar", conf)              # banner de confirmação
        self.assertIn("Fulano", conf)                          # nomeia quem será removido
        self.assertIn("Cancelar", conf)

    def test_pagina_admin_afiliados(self):
        afs = [{"id": "a1", "nome": "Dra. Maria", "contato": "maria@x.com", "codigo": "DRAMARIA",
                "pct_desconto": 10, "pct_comissao": 3, "ativo": 1,
                "n_vendas": 2, "comissao_total": 29.59, "comissao_pendente": 2.67}]
        comis = [{"id": "c1", "afiliado_id": "a1", "subscriber_id": "s1", "plano": "anual",
                  "valor_venda": 897.30, "valor_comissao": 26.92, "pago": 0}]
        h = self.s.pagina_admin_afiliados(afs, comis, token="tk")
        self.assertIn("<!doctype html>", h)
        self.assertIn("DRAMARIA", h)
        self.assertIn("Afiliados", h)
        self.assertIn("criar_afiliado", h)          # form de cadastro
        self.assertIn("marcar_comissao_paga", h)     # botão de baixa
        self.assertIn("26,92", h)                    # comissão formatada BRL

    def test_admin_nav_tem_afiliados(self):
        self.assertIn("/admin/afiliados", self.s._admin_nav("tk", "afiliados"))

    def test_pagina_admin_afiliados_editar(self):
        afs = [{"id": "a1", "nome": "Ana", "contato": "ana@x.com", "codigo": "ANA95",
                "pct_desconto": 95, "pct_comissao": 3, "ativo": 1,
                "n_vendas": 0, "comissao_total": 0, "comissao_pendente": 0}]
        # sem editar_id: cada linha tem o link "editar"
        h = self.s.pagina_admin_afiliados(afs, [], token="tk")
        self.assertIn("editar=a1", h)
        # com editar_id: painel de edição pré-preenchido
        he = self.s.pagina_admin_afiliados(afs, [], token="tk", editar_id="a1")
        self.assertIn("editar_afiliado", he)
        self.assertIn('value="ANA95"', he)
        self.assertIn('value="95"', he)
        self.assertIn("Salvar alterações", he)

    def test_pagina_admin_envio(self):
        h = self.s.pagina_admin_envio({"segunda", "domingo"}, token="tk")
        self.assertIn('value="segunda" checked', h)      # dia ativo marcado
        self.assertIn('value="domingo" checked', h)
        self.assertIn('value="terca"', h)                # dia existe
        self.assertNotIn('value="terca" checked', h)     # mas não marcado
        self.assertIn("salvar_dias", h)
        self.assertIn("/admin/envio", self.s._admin_nav("tk", "envio"))

    def test_pagina_admin_mensagens(self):
        h = self.s.pagina_admin_mensagens("WA TEXTO {link}", "Assunto X", "CORPO {nome}", token="tk")
        self.assertIn("WA TEXTO", h)
        self.assertIn("Assunto X", h)
        self.assertIn("CORPO", h)
        self.assertIn('name="wa"', h)
        self.assertIn('name="email_corpo"', h)
        self.assertIn("salvar_mensagens", h)
        self.assertIn("/admin/mensagens", self.s._admin_nav("tk", "mensagens"))

    def test_assinar_cadastro_padronizado(self):
        h = self.s.pagina_assinar("mensal")
        self.assertIn('name="nome" style="text-transform:uppercase"', h)   # nome visual maiúsculo
        self.assertIn('name="cupom" style="text-transform:uppercase"', h)  # cupom maiúsculo
        self.assertIn('placeholder="000.000.000-00"', h)                   # CPF padronizado


class TestCheckoutSeletor(unittest.TestCase):
    def setUp(self):
        import site_web
        self.s = site_web

    def test_pagina_assinar_tem_seletor(self):
        html = self.s.pagina_assinar("anual")
        self.assertIn('name="pais_dial"', html)
        self.assertIn('name="cpf"', html)        # CPF continua no form


class TestSeletorPais(unittest.TestCase):
    def test_renderiza_com_br_selecionado(self):
        import site_web
        html = site_web._seletor_pais()
        self.assertIn('name="pais_dial"', html)
        self.assertIn("Brasil", html)
        self.assertIn('value="55" selected', html)
        self.assertIn("Estados Unidos", html)   # tem opção internacional

    def test_pagina_admin_traz_seletor_no_form_de_cortesia(self):
        import site_web
        h = site_web.pagina_admin([], token="tk")
        self.assertIn('name="pais_dial"', h)
        self.assertIn("Adicionar cortesia", h)


class TestCuradoriaCabecalho(unittest.TestCase):
    def setUp(self):
        import site_web
        self.s = site_web

    def test_faixa_mostra_envios_e_data(self):
        html = self.s._curadoria_faixa({"envios": 14, "ate": "2026-08-14", "baixo": False})
        self.assertIn("14/08", html)
        self.assertIn("14 envios", html)
        self.assertNotIn("baixo", html)

    def test_faixa_alerta_quando_baixo(self):
        html = self.s._curadoria_faixa({"envios": 3, "ate": "2026-07-29", "baixo": True})
        self.assertIn("baixo", html)

    def test_faixa_sem_estoque(self):
        html = self.s._curadoria_faixa({"envios": 0, "ate": None, "baixo": True})
        self.assertIn("Sem estoque", html)

    def test_amanha_mostra_titulo_e_link_de_revisao(self):
        html = self.s._curadoria_amanha(
            {"titulo": "Tirzepatida 72 semanas", "status": "DRAFT", "review_token": "abc123"})
        self.assertIn("Tirzepatida 72 semanas", html)
        self.assertIn("/revisar/abc123", html)
        self.assertIn("aguardando sua revisão", html)

    def test_amanha_reflete_status_aprovado(self):
        html = self.s._curadoria_amanha(
            {"titulo": "X", "status": "APPROVED", "review_token": "t"})
        self.assertIn("aprovado", html)

    def test_amanha_vazio_nao_renderiza(self):
        self.assertEqual(self.s._curadoria_amanha(None), "")

    def test_abas_marcam_a_ativa_e_mostram_contador(self):
        html = self.s._curadoria_abas(
            "triagem", {"triagem": 12, "reserva": 8, "classicos": 0}, "tok")
        self.assertEqual(html.count('class="tab on"'), 1)   # só UMA aba ativa, não todas
        self.assertIn('class="tab" href="/curadoria?token=tok&aba=reserva"', html)
        self.assertIn('class="tab" href="/curadoria?token=tok&aba=classicos"', html)
        self.assertIn(">12<", html)

    def test_abas_codifica_tema_apenas_no_link_da_triagem(self):
        html = self.s._curadoria_abas(
            "triagem", {"triagem": 1, "reserva": 1, "classicos": 1}, "tok",
            tema="Perda & peso")
        self.assertIn("tema=Perda%20%26%20peso", html)   # percent-encoded no link da triagem
        self.assertNotIn("Perda & peso", html)           # '&' cru não pode vazar pro href
        self.assertNotIn("Perda&peso", html)              # nem o espaço cru


class TestCuradoriaItem(unittest.TestCase):
    def setUp(self):
        import site_web
        self.s = site_web
        self.c = {"id": "c1", "titulo": "Tirzepatida 72 semanas", "pergunta": "Sustenta a perda?",
                  "score": 8, "fonte": "Lancet", "data": "2026-07-12",
                  "doi": "10.1016/x", "url": "", "status": "novo"}

    def test_mostra_titulo_pergunta_e_meta(self):
        html = self.s._curadoria_item(self.c, "tok")
        self.assertIn("Tirzepatida 72 semanas", html)
        self.assertIn("Sustenta a perda?", html)
        self.assertIn("Lancet", html)
        self.assertIn("2026-07-12", html)

    def test_titulo_vira_link_pelo_doi(self):
        html = self.s._curadoria_item(self.c, "tok")
        self.assertIn('href="https://doi.org/10.1016/x"', html)
        self.assertIn('target="_blank"', html)

    def test_titulo_prefere_url_quando_existe(self):
        html = self.s._curadoria_item({**self.c, "url": "https://ex.com/a"}, "tok")
        self.assertIn('href="https://ex.com/a"', html)

    def test_href_escapa_caracteres_perigosos_da_url(self):
        # url vem de API externa (Europe PMC/OpenAlex) — dado não-confiável indo pro atributo href.
        perigoso = 'https://ex.com/a?x=1&y=2"onmouseover=alert(1)'
        html = self.s._curadoria_item({**self.c, "url": perigoso}, "tok")
        self.assertIn('href="https://ex.com/a?x=1&amp;y=2&quot;onmouseover=alert(1)"', html)
        self.assertNotIn('href="https://ex.com/a?x=1&y=2"onmouseover=alert(1)"', html)
        self.assertNotIn('2"onmouseover', html)   # a aspa crua quebraria o atributo href

    def test_sem_doi_e_sem_url_nao_vira_link(self):
        html = self.s._curadoria_item({**self.c, "doi": "", "url": ""}, "tok")
        self.assertNotIn("<a class=\"ctitle\"", html)
        self.assertIn("Tirzepatida 72 semanas", html)

    def test_novo_oferece_priorizar_e_descartar(self):
        html = self.s._curadoria_item(self.c, "tok")
        self.assertIn('value="priorizar"', html)
        self.assertIn('value="descartar"', html)
        self.assertNotIn('value="desfazer"', html)

    def test_selecionado_mostra_badge_e_desfazer(self):
        html = self.s._curadoria_item({**self.c, "status": "selecionado"}, "tok")
        self.assertIn("gera hoje à noite", html)
        self.assertIn('value="desfazer"', html)
        self.assertNotIn('value="priorizar"', html)

    def test_ancora_do_item(self):
        self.assertIn('id="cand-c1"', self.s._curadoria_item(self.c, "tok"))

    def test_preserva_aba_e_tema_no_form(self):
        html = self.s._curadoria_item(self.c, "tok", aba="triagem", tema="Obesidade")
        self.assertIn('name="tema" value="Obesidade"', html)

    def test_nao_tem_mais_checkbox(self):
        self.assertNotIn("<input type=\"checkbox\"", self.s._curadoria_item(self.c, "tok"))


class TestPaginaCuradoria(unittest.TestCase):
    def setUp(self):
        import site_web
        self.s = site_web
        self.estado = {"envios": 12, "ate": "2026-08-12", "baixo": False}
        self.cand = {"id": "c1", "titulo": "Estudo A", "pergunta": "P?", "score": 8,
                     "fonte": "Lancet", "data": "2026-07-12", "doi": "10.1/a",
                     "url": "", "status": "novo", "tema": "Obesidade", "tipo": "varredura"}
        self.classicos = {"candidatos": [], "banco": []}

    def _render(self, **kw):
        base = dict(estado=self.estado, amanha=None, candidatos=[self.cand], reserva=[],
                    classicos=self.classicos, token="tok")
        base.update(kw)
        return self.s.pagina_curadoria(**base)

    def test_renderiza_triagem_por_padrao(self):
        html = self._render()
        self.assertIn("Estudo A", html)
        self.assertIn('class="tab on"', html)

    def test_nao_tem_mais_salvar_selecao(self):
        html = self._render()
        self.assertNotIn("Salvar seleção", html)
        self.assertNotIn('type="checkbox"', html)

    def test_aba_invalida_da_querystring_cai_em_triagem(self):
        # `aba` vem cru da querystring — um valor lixo não pode deixar nenhuma
        # aba destacada nem quebrar o corpo (cai no default: triagem).
        html = self._render(aba="<script>lixo")
        self.assertEqual(html.count('class="tab on"'), 1)
        self.assertIn("Estudo A", html)

    def test_filtro_por_tema_esconde_os_outros(self):
        outro = {**self.cand, "id": "c2", "titulo": "Estudo B", "tema": "Hormonal"}
        html = self._render(candidatos=[self.cand, outro], tema="Obesidade")
        self.assertIn("Estudo A", html)
        self.assertNotIn("Estudo B", html)

    def test_aba_reserva_lista_os_prontos(self):
        reserva = [{"id": "r1", "tema": "Obesidade", "status": "pronto",
                    "titulo_pt": "Resumo pronto", "resumo": "txt", "prioridade": 0}]
        html = self._render(reserva=reserva, aba="reserva")
        self.assertIn("Resumo pronto", html)

    def test_aba_reserva_separa_prontos_de_enviados(self):
        # o contador da aba conta só "pronto"; "enviado" segue listado abaixo, como
        # histórico, separado por um cabeçalho — não misturado na mesma lista.
        reserva = [
            {"id": "r1", "tema": "Obesidade", "status": "enviado",
             "titulo_pt": "Enviado Um", "resumo": "txt", "prioridade": 0},
            {"id": "r2", "tema": "Obesidade", "status": "pronto",
             "titulo_pt": "Pronto Um", "resumo": "txt", "prioridade": 0},
        ]
        html = self._render(reserva=reserva, aba="reserva")
        self.assertIn("Já enviados", html)
        self.assertLess(html.index("Pronto Um"), html.index("Já enviados"))
        self.assertLess(html.index("Já enviados"), html.index("Enviado Um"))

    def test_aba_classicos_lista_candidatos_classicos(self):
        cl = {**self.cand, "id": "k1", "titulo": "Clássico X", "tipo": "classico"}
        html = self._render(classicos={"candidatos": [cl], "banco": []}, aba="classicos")
        self.assertIn("Clássico X", html)

    def test_classico_nao_vaza_pra_triagem(self):
        # simula o cenário real do bug: um item tipo="classico" chegando MISTURADO
        # dentro de `candidatos` (o que acontecia quando a rota montava a lista sem
        # filtrar por tipo). O filtro defensivo em pagina_curadoria precisa barrá-lo
        # mesmo aqui, sem depender de `classicos` estar corretamente separado.
        cl = {**self.cand, "id": "k1", "titulo": "Clássico X", "tipo": "classico"}
        html = self._render(candidatos=[self.cand, cl])
        self.assertIn("Estudo A", html)
        self.assertNotIn("Clássico X", html)

    def test_ferramentas_tem_meu_estudo_e_varreduras(self):
        html = self._render()
        self.assertIn("Adicionar meu estudo", html)
        self.assertIn('value="varrer"', html)
        self.assertIn('value="varrer_classicos"', html)

    def test_faixa_e_amanha_aparecem(self):
        html = self._render(amanha={"titulo": "Amanhã X", "status": "DRAFT",
                                    "review_token": "tk9"})
        self.assertIn("Conteúdo garantido até", html)
        self.assertIn("Amanhã X", html)


if __name__ == "__main__":
    unittest.main()
