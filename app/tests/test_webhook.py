"""Testes do webhook Asaas (decidir puro + processar). Standalone."""
import os
import sys
import tempfile
import importlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDecidir(unittest.TestCase):
    def setUp(self):
        import webhook_asaas
        self.w = webhook_asaas

    def test_matriz(self):
        self.assertEqual(self.w.decidir("PAYMENT_CONFIRMED", False), "ATIVAR")
        self.assertEqual(self.w.decidir("PAYMENT_RECEIVED", True), "RENOVAR")
        self.assertEqual(self.w.decidir("PAYMENT_OVERDUE", True), "INADIMPLENTE")
        self.assertEqual(self.w.decidir("PAYMENT_REFUNDED", True), "SUSPENDER")
        self.assertEqual(self.w.decidir("PAYMENT_DELETED", True), "SUSPENDER")
        self.assertEqual(self.w.decidir("PAYMENT_CREATED", False), "IGNORAR")


class TestProcessar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["ASAAS_WEBHOOK_TOKEN"] = "segredo"
        for m in ("config", "db", "subscribers", "webhook_asaas"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, subscribers, webhook_asaas
        for mod in (config, db, subscribers, webhook_asaas):
            importlib.reload(mod)
        self.cfg, self.db, self.s, self.w = config, db, subscribers, webhook_asaas
        self.s._migrado = False
        db.init()
        self.enviados = []
        self.envfn = lambda wpp, msg: self.enviados.append((wpp, msg))

    def _body(self, event="PAYMENT_CONFIRMED", ext="tok", pid="pay_1", sub=None, installment=None):
        pay = {"id": pid, "externalReference": ext, "customer": "cus_1",
               "subscription": sub, "dueDate": "2026-07-19"}
        if installment:
            pay["installment"] = installment      # marca de parcela de cartão (Asaas)
        return {"event": event, "payment": pay}

    def test_token_invalido(self):
        st, _ = self.w.processar(self._body(), "errado", enviar_fn=self.envfn)
        self.assertEqual(st, 401)

    def test_ativar_cria_assinante(self):
        tok = self.db.criar_pending({"nome": "Dr. A", "whatsapp": "5543999990000",
                                     "email": "a@x.com", "plano": "anual", "metodo": "CARTAO"})
        st, msg = self.w.processar(self._body(ext=tok), "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "ativado"))
        self.assertEqual(len(self.s.ativos()), 1)
        self.assertEqual(len(self.enviados), 1)      # boas-vindas

    def test_ativar_novo_assinante_grava_valor_contratado(self):
        # ACHADO 1 (revisão): valor_contratado precisa refletir o que o assinante de
        # fato pagou (não o preço de tabela) — renovacao.preco_renovacao lê esse campo
        # pra cobrar certo na renovação seguinte. Caminho de assinante 100% novo.
        tok = self.db.criar_pending({"nome": "Dr. V1", "whatsapp": "5543999990010",
                                     "email": "v1@x.com", "plano": "anual", "metodo": "PIX"})
        st, msg = self.w.processar(self._body_valor(ext=tok, value=947.00), "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "ativado"))
        reg = self.s.por_whatsapp("5543999990010")
        self.assertEqual(reg["valor_contratado"], 947.00)

    def test_ativar_pix_grava_acesso_ate_no_vencimento(self):
        # CORREÇÃO 1: Pix é pagamento avulso (DETACHED) — não existe assinatura
        # recorrente que gere um PAYMENT_OVERDUE quando o período acabar, e não há
        # rotina que expire ninguém. Sem acesso_ate, ATIVO sem acesso_ate = acesso PRA
        # SEMPRE (subscribers.tem_acesso). Grava o mesmo vencimento já calculado (prox)
        # pra expirar no fim do período pago (evento sem "subscription" = Pix avulso).
        tok = self.db.criar_pending({"nome": "Dr. Pix", "whatsapp": "5543999994444",
                                     "email": "pix@x.com", "plano": "anual", "metodo": "PIX"})
        st, msg = self.w.processar(self._body(ext=tok, sub=None), "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "ativado"))
        reg = self.s.por_whatsapp("5543999994444")
        self.assertEqual(reg["acesso_ate"], "2027-07-19")     # dueDate 2026-07-19 + 365d (YEARLY)
        self.assertFalse(self.s.tem_acesso(reg, agora=__import__("datetime").datetime(2027, 8, 1)))

    def test_ativar_cartao_nao_grava_acesso_ate(self):
        # Cartão tem assinatura recorrente (sid presente): ela renova sozinha, então
        # gravar acesso_ate cortaria o acesso na virada do ciclo antes da próxima
        # cobrança confirmar. Só o Pix avulso (sem subscription) precisa da expiração.
        tok = self.db.criar_pending({"nome": "Dr. Cartao", "whatsapp": "5543999995555",
                                     "email": "cartao@x.com", "plano": "anual", "metodo": "CARTAO"})
        st, msg = self.w.processar(self._body(ext=tok, sub="sub_cartao"), "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "ativado"))
        reg = self.s.por_whatsapp("5543999995555")
        self.assertIsNone(reg["acesso_ate"])
        self.assertTrue(self.s.tem_acesso(reg))

    def test_idempotente(self):
        tok = self.db.criar_pending({"nome": "Dr. A", "whatsapp": "5543", "plano": "mensal"})
        self.w.processar(self._body(ext=tok), "segredo", enviar_fn=self.envfn)
        st, msg = self.w.processar(self._body(ext=tok), "segredo", enviar_fn=self.envfn)
        self.assertEqual(msg, "duplicado")
        self.assertEqual(len(self.s.listar()), 1)    # não duplicou

    def test_inadimplente_e_renova(self):
        reg = self.s.criar_de_pagamento({"nome": "B", "whatsapp": "5543", "plano": "mensal"},
                                         {"subscription": "sub_9"})
        self.w.processar(self._body(event="PAYMENT_OVERDUE", pid="p2", sub="sub_9"), "segredo", enviar_fn=self.envfn)
        self.assertEqual(self.s.por_subscription("sub_9")["status"], "INADIMPLENTE")
        self.w.processar(self._body(event="PAYMENT_RECEIVED", pid="p3", sub="sub_9"), "segredo", enviar_fn=self.envfn)
        self.assertEqual(self.s.por_subscription("sub_9")["status"], "ATIVO")

    def test_renovar_limpa_as_marcas_de_cancelamento(self):
        # Reativação LEGÍTIMA (sem cancelado_em): ex. estorno/chargeback que reverteu
        # (SUSPENDER marca CANCELADO sem gravar cancelado_em) e um novo pagamento
        # confirma. Sem isso, um assinante nesse caso ficaria PERMANENTEMENTE impedido
        # de cancelar: db.claim_cancelamento só grava quando cancelado_em está vazio,
        # então todo claim dele perderia. E o acesso_ate herdado (data passada) zeraria
        # o acesso de quem está pagando.
        reg = self.s.criar_de_pagamento({"nome": "C", "whatsapp": "5543", "plano": "mensal"},
                                         {"subscription": "sub_rc"})
        self.s.marcar_status(reg["id"], "CANCELADO", acesso_ate="2026-01-01T00:00:00")
        self.w.processar(self._body(event="PAYMENT_RECEIVED", pid="p9", sub="sub_rc"),
                         "segredo", enviar_fn=self.envfn)
        atual = self.s.por_subscription("sub_rc")
        self.assertEqual(atual["status"], "ATIVO")
        self.assertFalse(atual["cancelado_em"])       # dá pra cancelar de novo
        self.assertFalse(atual["cancel_motivo"])
        self.assertIsNone(atual["acesso_ate"])
        self.assertTrue(self.s.tem_acesso(atual))
        self.assertTrue(self.db.claim_cancelamento(reg["id"], "de novo", None))

    def test_renovar_sobre_cancelado_nao_reativa(self):
        # CORREÇÃO 2: parcela do anual em 12x confirmada para quem JÁ cancelou a
        # renovação (cancelado_em preenchido via claim_cancelamento) é só a quitação do
        # que já estava contratado — não uma reativação. Sem esta trava, o RENOVAR
        # reabriria a assinatura, apagaria o cancelamento (cancelado_em/cancel_motivo)
        # e empurraria vencimento/acesso — reativando de graça quem quis sair.
        reg = self.s.criar_de_pagamento(
            {"nome": "C", "whatsapp": "5543", "plano": "mensal"},
            {"subscription": "sub_rc", "proximo_vencimento": "2026-02-01"})
        self.db.claim_cancelamento(reg["id"], "caro demais", "2026-01-01T00:00:00")
        antes = self.s.por_subscription("sub_rc")
        self.w.processar(self._body(event="PAYMENT_RECEIVED", pid="p9", sub="sub_rc"),
                         "segredo", enviar_fn=self.envfn)
        depois = self.s.por_subscription("sub_rc")
        self.assertEqual(depois["status"], "CANCELADO")                       # não reativou
        self.assertEqual(depois["cancelado_em"], antes["cancelado_em"])       # marca intacta
        self.assertEqual(depois["cancel_motivo"], "caro demais")              # motivo intacto
        self.assertEqual(depois["acesso_ate"], "2026-01-01T00:00:00")         # não mudou
        self.assertEqual(depois["proximo_vencimento"], "2026-02-01")          # não empurrou

    def test_renovar_sobre_cancelado_alerta_admin(self):
        # O Asaas cobrou (e confirmou) alguém que já tinha cancelado — cenário real no
        # anual em 12x, em que as parcelas seguem sendo cobradas mesmo depois do
        # cancelamento no nosso lado. Pode ser parcela legítima OU o cancelamento da
        # assinatura no Asaas ter falhado (cliente cobrado indevidamente) — só o Diego
        # distingue, por isso o alerta é sempre disparado.
        reg = self.s.criar_de_pagamento({"nome": "D", "whatsapp": "5543", "plano": "mensal"},
                                         {"subscription": "sub_rc2"})
        self.db.claim_cancelamento(reg["id"], "caro demais", "2026-01-01T00:00:00")
        alertas = []
        orig_alert = self.w._alertar_admin
        self.w._alertar_admin = lambda pid, sid, motivo: alertas.append(motivo)
        try:
            self.w.processar(self._body(event="PAYMENT_RECEIVED", pid="p10", sub="sub_rc2"),
                             "segredo", enviar_fn=self.envfn)
        finally:
            self.w._alertar_admin = orig_alert
        self.assertEqual(self.s.por_subscription("sub_rc2")["status"], "CANCELADO")  # não reativou
        self.assertEqual(len(alertas), 1)
        self.assertIn("cancel", alertas[0].lower())

    def _body_valor(self, event="PAYMENT_CONFIRMED", ext="tok", pid="pay_af", value=897.30, sub=None):
        return {"event": event, "payment": {"id": pid, "externalReference": ext, "value": value,
                "customer": "cus_af", "subscription": sub, "dueDate": "2026-07-19"}}

    def test_ativar_com_afiliado_registra_comissao(self):
        self.db.criar_afiliado("Dra. Maria", "", "dramaria", 10, 3)
        tok = self.db.criar_pending({"nome": "Dr. Novo", "whatsapp": "5543999991111",
                                     "email": "n@x.com", "plano": "anual", "metodo": "PIX",
                                     "afiliado_codigo": "DRAMARIA", "valor": 897.30})
        st, msg = self.w.processar(self._body_valor(ext=tok), "segredo", enviar_fn=self.envfn)
        self.assertEqual((st, msg), (200, "ativado"))
        comis = self.db.listar_comissoes()
        self.assertEqual(len(comis), 1)
        self.assertAlmostEqual(comis[0]["valor_venda"], 897.30, places=2)
        self.assertAlmostEqual(comis[0]["valor_comissao"], 26.92, places=2)  # 3% de 897.30

    def test_renovar_nao_registra_comissao(self):
        reg = self.s.criar_de_pagamento({"nome": "B", "whatsapp": "5543", "plano": "mensal"},
                                         {"subscription": "sub_af"})
        self.w.processar(self._body_valor(event="PAYMENT_RECEIVED", pid="pr1", sub="sub_af"),
                         "segredo", enviar_fn=self.envfn)
        self.assertEqual(self.db.listar_comissoes(), [])

    def test_ativar_afiliado_comissao_falha_alerta_admin(self):
        # se registrar_comissao falhar: ativação segue, comissão não entra, admin é avisado.
        self.db.criar_afiliado("Dra. Maria", "", "dramaria", 10, 3)
        tok = self.db.criar_pending({"nome": "Dr. N", "whatsapp": "5543999992222",
                                     "email": "n@x.com", "plano": "anual", "metodo": "PIX",
                                     "afiliado_codigo": "DRAMARIA", "valor": 897.30})
        alertas = []
        orig_reg, orig_alert = self.db.registrar_comissao, self.w._alertar_admin
        self.db.registrar_comissao = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down"))
        self.w._alertar_admin = lambda pid, sid, motivo: alertas.append(motivo)
        try:
            st, msg = self.w.processar(self._body_valor(ext=tok), "segredo", enviar_fn=self.envfn)
        finally:
            self.db.registrar_comissao, self.w._alertar_admin = orig_reg, orig_alert
        self.assertEqual((st, msg), (200, "ativado"))       # ativação não quebra
        self.assertEqual(self.db.listar_comissoes(), [])    # comissão não entrou
        self.assertTrue(any("comissão" in m for m in alertas))  # admin avisado

    def test_ativar_atribui_por_cpf_quando_externalref_nao_bate(self):
        # Asaas não propaga o externalReference -> o pending é recuperado pelo CPF do cliente.
        import asaas
        self.db.criar_afiliado("Dra. Maria", "", "dramaria", 10, 3)
        self.db.criar_pending({"nome": "Dr. N", "whatsapp": "5543999993333", "cpf": "11144477735",
                               "email": "n@x.com", "plano": "anual", "metodo": "CARTAO",
                               "afiliado_codigo": "DRAMARIA", "valor": 897.30})
        self.cfg.ASAAS_API_KEY = "k"   # liga o branch que busca o cliente Asaas
        orig_cli, orig_ass = asaas.obter_cliente, asaas.obter_assinatura
        asaas.obter_cliente = lambda cid: {"name": "Dr. N", "mobilePhone": "5543999993333",
                                           "email": "n@x.com", "cpfCnpj": "111.444.777-35"}
        asaas.obter_assinatura = lambda sid: {"cycle": "YEARLY"}
        try:
            body = self._body_valor(ext="TOKEN_INEXISTENTE", value=897.30, sub=None)
            st, msg = self.w.processar(body, "segredo", enviar_fn=self.envfn)
        finally:
            asaas.obter_cliente, asaas.obter_assinatura = orig_cli, orig_ass
            self.cfg.ASAAS_API_KEY = None
        self.assertEqual((st, msg), (200, "ativado"))
        comis = self.db.listar_comissoes()
        self.assertEqual(len(comis), 1)                       # atribuiu via CPF, sem externalReference
        self.assertAlmostEqual(comis[0]["valor_comissao"], 26.92, places=2)

    def test_ativar_parcela_do_anual_mesmo_cpf_nao_duplica(self):
        # BUG: no Asaas, cartão parcelado NÃO cria assinatura recorrente (subscription
        # vem vazio em toda parcela confirmada) -> cada parcela do anual em 12x cai
        # no ramo ATIVAR de novo (por_subscription nunca acha nada). Sem checar se o
        # CPF já é assinante com acesso vigente, a 2ª parcela criaria um 2º registro,
        # reenviaria boas-vindas, mandaria "nova venda" de novo e duplicaria comissão.
        reg = self.s.criar_de_pagamento(
            {"nome": "Dr. Parcelado", "whatsapp": "5543999996666", "email": "p@x.com",
             "cpf": "11144477735", "plano": "anual"},
            {"customer": "cus_1", "payment": "pay_1parc", "proximo_vencimento": "2026-08-19"})
        import asaas
        self.cfg.ASAAS_API_KEY = "k"
        orig_cli = asaas.obter_cliente
        asaas.obter_cliente = lambda cid: {"name": "Dr. Parcelado", "mobilePhone": "5543999996666",
                                           "email": "p@x.com", "cpfCnpj": "111.444.777-35"}
        chamadas_comissao = []
        orig_reg_comissao = self.db.registrar_comissao
        self.db.registrar_comissao = lambda *a, **k: chamadas_comissao.append((a, k))
        import email_send
        emails = []
        orig_email = email_send.enviar
        email_send.enviar = lambda to, assunto, html: emails.append((to, assunto))
        try:
            st, msg = self.w.processar(self._body(ext="outro_tok", pid="pay_2parc", sub=None,
                                                   installment="inst_anual12x"),
                                       "segredo", enviar_fn=self.envfn)
        finally:
            asaas.obter_cliente = orig_cli
            self.cfg.ASAAS_API_KEY = None
            self.db.registrar_comissao = orig_reg_comissao
            email_send.enviar = orig_email
        self.assertEqual((st, msg), (200, "parcela-registrada"))
        self.assertEqual(len(self.s.listar()), 1)          # não duplicou o assinante
        self.assertEqual(len(self.enviados), 0)            # não reenviou boas-vindas (WhatsApp)
        self.assertEqual(emails, [])                        # nem boas-vindas nem "nova venda" por e-mail
        self.assertEqual(chamadas_comissao, [])              # não registrou comissão de novo
        atual = self.s.por_id(reg["id"])
        self.assertEqual(atual["asaas_payment_id"], "pay_2parc")   # referência p/ estorno atualizada
        self.assertEqual(atual["proximo_vencimento"], "2026-08-19")  # não empurrou (mesmo período)
        self.assertIsNone(atual["acesso_ate"])              # CORREÇÃO 2: parcela não estende acesso

    def test_ativar_parcela_do_anual_casa_por_whatsapp(self):
        # Mesmo cenário, mas sem CPF disponível no evento (Asaas não devolveu cpfCnpj)
        # -> a guarda tem que casar pelo WhatsApp como fallback.
        reg = self.s.criar_de_pagamento(
            {"nome": "Dr. W", "whatsapp": "5543999997777", "email": "w@x.com", "plano": "anual"},
            {"customer": "cus_2", "payment": "pay_1w", "proximo_vencimento": "2026-08-20"})
        import asaas, email_send
        self.cfg.ASAAS_API_KEY = "k"
        orig_cli = asaas.obter_cliente
        asaas.obter_cliente = lambda cid: {"name": "Dr. W", "mobilePhone": "5543999997777",
                                           "email": "w@x.com", "cpfCnpj": ""}
        chamadas_comissao = []
        orig_reg_comissao = self.db.registrar_comissao
        self.db.registrar_comissao = lambda *a, **k: chamadas_comissao.append((a, k))
        emails = []
        orig_email = email_send.enviar
        email_send.enviar = lambda to, assunto, html: emails.append((to, assunto))
        try:
            st, msg = self.w.processar(self._body(ext="outro_tok_w", pid="pay_2w", sub=None,
                                                   installment="inst_anual12x_w"),
                                       "segredo", enviar_fn=self.envfn)
        finally:
            asaas.obter_cliente = orig_cli
            self.cfg.ASAAS_API_KEY = None
            self.db.registrar_comissao = orig_reg_comissao
            email_send.enviar = orig_email
        self.assertEqual((st, msg), (200, "parcela-registrada"))
        self.assertEqual(len(self.s.listar()), 1)
        self.assertEqual(len(self.enviados), 0)
        self.assertEqual(chamadas_comissao, [])
        self.assertEqual(emails, [])                        # parcela de cartão não manda e-mail
        atual = self.s.por_id(reg["id"])
        self.assertEqual(atual["asaas_payment_id"], "pay_2w")
        self.assertEqual(atual["proximo_vencimento"], "2026-08-20")
        self.assertIsNone(atual["acesso_ate"])

    def test_ativar_recontratacao_apos_acesso_expirar_reativa_mesmo_id(self):
        # Pix anual que venceu (acesso_ate no passado) e o cliente comprou de novo:
        # recontratação legítima -> reativa o MESMO registro em vez de criar outro.
        # TESTE 3/4 (spec renovação): a conta já existe e já tem senha, então NÃO manda
        # as boas-vindas de cliente novo (link de criar senha) — manda a confirmação de
        # renovação por e-mail (link de entrar), texto único com a de RENOVAR.
        reg = self.s.criar_de_pagamento(
            {"nome": "Dr. Expirado", "whatsapp": "5543999998888", "email": "e@x.com",
             "cpf": "11144477735", "plano": "anual"},
            {"customer": "cus_3", "payment": "pay_velho", "proximo_vencimento": "2025-07-01"})
        self.s.marcar_status(reg["id"], "ATIVO", acesso_ate="2025-07-01T00:00:00")
        self.assertFalse(self.s.tem_acesso(self.s.por_id(reg["id"])))
        import asaas, email_send
        self.cfg.ASAAS_API_KEY = "k"
        orig_cli = asaas.obter_cliente
        asaas.obter_cliente = lambda cid: {"name": "Dr. Expirado", "mobilePhone": "5543999998888",
                                           "email": "e@x.com", "cpfCnpj": "111.444.777-35"}
        emails = []
        orig_email = email_send.enviar
        email_send.enviar = lambda to, assunto, html: emails.append((to, assunto, html))
        try:
            st, msg = self.w.processar(self._body(ext="tok_novo", pid="pay_novo", sub=None),
                                       "segredo", enviar_fn=self.envfn)
        finally:
            asaas.obter_cliente = orig_cli
            self.cfg.ASAAS_API_KEY = None
            email_send.enviar = orig_email
        self.assertEqual((st, msg), (200, "ativado"))
        self.assertEqual(len(self.s.listar()), 1)           # reativou, não duplicou
        atual = self.s.por_id(reg["id"])
        self.assertEqual(atual["id"], reg["id"])              # mesmo registro
        self.assertEqual(atual["status"], "ATIVO")
        self.assertTrue(self.s.tem_acesso(atual, agora=__import__("datetime").datetime(2026, 8, 1)))
        self.assertEqual(len(self.enviados), 0)               # NÃO reenviou boas-vindas (WhatsApp)
        # emails[*] pode incluir o aviso de "nova venda" pro admin (config.ADMIN_EMAIL);
        # o que importa aqui é o que o CLIENTE recebeu.
        do_cliente = [e for e in emails if e[0] == "e@x.com"]
        self.assertEqual(len(do_cliente), 1)                  # e-mail de renovação, não boas-vindas
        assunto, html = do_cliente[0][1], do_cliente[0][2]
        import mensagens
        self.assertNotEqual(assunto, mensagens.EMAIL_ASSUNTO_DEFAULT)   # não é o de boas-vindas
        self.assertIn("/entrar", html)                        # link de ENTRAR, não de criar senha
        self.assertNotIn("Criar minha senha", html)

    def test_recontratacao_apos_expirar_atualiza_valor_contratado(self):
        # ACHADO 1 (revisão): recontratação depois do acesso expirar também é
        # assinante EXISTENTE — mesma razão da recompra de Pix acima.
        reg = self.s.criar_de_pagamento(
            {"nome": "Dr. VC3", "whatsapp": "5543999990012", "email": "vc3@x.com",
             "cpf": "11144477735", "plano": "anual", "valor_contratado": 897.30},
            {"customer": "cus_vc3", "payment": "pay_vc3_velho", "proximo_vencimento": "2025-07-01"})
        self.s.marcar_status(reg["id"], "ATIVO", acesso_ate="2025-07-01T00:00:00")   # expirado
        import asaas
        self.cfg.ASAAS_API_KEY = "k"
        orig_cli = asaas.obter_cliente
        asaas.obter_cliente = lambda cid: {"name": "Dr. VC3", "mobilePhone": "5543999990012",
                                           "email": "vc3@x.com", "cpfCnpj": "111.444.777-35"}
        try:
            st, msg = self.w.processar(self._body_valor(ext="tokvc3", pid="pay_vc3_novo", value=497.00),
                                       "segredo", enviar_fn=self.envfn)
        finally:
            asaas.obter_cliente = orig_cli
            self.cfg.ASAAS_API_KEY = None
        self.assertEqual((st, msg), (200, "ativado"))
        atual = self.s.por_id(reg["id"])
        self.assertEqual(atual["valor_contratado"], 497.00)      # atualizado, não ficou 897.30

    def test_renovar_normal_envia_email_de_renovacao_em_pt_br(self):
        # TESTE 1 (spec renovação): cartão à vista renovando sozinho cobra o cliente
        # de novo sem avisar nada hoje — cobrança muda é exatamente o que gera "não
        # reconheço essa cobrança" e chargeback. Data no e-mail em PT-BR (site_web.
        # _data_br), não ISO. Boas-vindas (cliente novo) não é enviada.
        self.s.criar_de_pagamento(
            {"nome": "Dr. Renov", "whatsapp": "5543999990002", "email": "renov@x.com", "plano": "mensal"},
            {"subscription": "sub_renov1"})
        import email_send
        emails = []
        orig_email = email_send.enviar
        email_send.enviar = lambda to, assunto, html: emails.append((to, assunto, html))
        try:
            st, msg = self.w.processar(self._body(event="PAYMENT_RECEIVED", pid="pr_renov1", sub="sub_renov1"),
                                       "segredo", enviar_fn=self.envfn)
        finally:
            email_send.enviar = orig_email
        self.assertEqual((st, msg), (200, "renovado"))
        self.assertEqual(len(emails), 1)
        to, assunto, html = emails[0]
        self.assertEqual(to, "renov@x.com")
        self.assertIn("18 ago 2026", html)      # dueDate 2026-07-19 + 30d (MONTHLY) = 18 ago, em PT-BR
        self.assertNotIn("2026-08-18", html)    # não é ISO
        import mensagens
        self.assertNotEqual(assunto, mensagens.EMAIL_ASSUNTO_DEFAULT)   # não é o de boas-vindas
        self.assertEqual(len(self.enviados), 0)                          # boas-vindas (WhatsApp) não enviada

    def test_renovar_sobre_cancelado_nao_envia_email_ao_cliente(self):
        # TESTE 2 (spec renovação): parcela confirmada pra quem já cancelou a
        # renovação só alerta o admin (o caso é ambíguo — pode ser parcela legítima do
        # anual em 12x ou cancelamento que falhou no Asaas). O CLIENTE não recebe
        # nada: ele já sabe que cancelou.
        reg = self.s.criar_de_pagamento(
            {"nome": "D2", "whatsapp": "5543", "email": "d2@x.com", "plano": "mensal"},
            {"subscription": "sub_rc3"})
        self.db.claim_cancelamento(reg["id"], "caro demais", "2026-01-01T00:00:00")
        import email_send
        emails = []
        orig_email = email_send.enviar
        email_send.enviar = lambda to, assunto, html: emails.append((to, assunto))
        try:
            st, msg = self.w.processar(self._body(event="PAYMENT_RECEIVED", pid="p11", sub="sub_rc3"),
                                       "segredo", enviar_fn=self.envfn)
        finally:
            email_send.enviar = orig_email
        self.assertEqual(msg, "parcela-pos-cancelamento")
        self.assertEqual(emails, [])     # nenhum e-mail ao CLIENTE

    def test_ativar_primeira_compra_envia_boas_vindas_nao_renovacao(self):
        # TESTE 4 (spec renovação): cliente novo -> boas-vindas normais (link de criar
        # senha), NUNCA a confirmação de renovação (o assinante não tem conta ainda).
        tok = self.db.criar_pending({"nome": "Dr. Novo2", "whatsapp": "5543999990003",
                                     "email": "novo2@x.com", "plano": "mensal", "metodo": "PIX"})
        import email_send
        emails = []
        orig_email = email_send.enviar
        email_send.enviar = lambda to, assunto, html: emails.append((to, assunto, html))
        try:
            st, msg = self.w.processar(self._body(ext=tok, pid="pay_novo2"), "segredo", enviar_fn=self.envfn)
        finally:
            email_send.enviar = orig_email
        self.assertEqual((st, msg), (200, "ativado"))
        self.assertEqual(len(self.enviados), 1)          # boas-vindas por WhatsApp
        # emails[*] pode incluir o aviso de "nova venda" pro admin; o que importa aqui
        # é o que o CLIENTE recebeu.
        do_cliente = [e for e in emails if e[0] == "novo2@x.com"]
        self.assertEqual(len(do_cliente), 1)
        to, assunto, html = do_cliente[0]
        import mensagens
        self.assertEqual(assunto, mensagens.EMAIL_ASSUNTO_DEFAULT)   # é o de boas-vindas
        self.assertIn("Criar minha senha", html)
        self.assertNotIn("Acessar minha conta", html)

    def test_pix_recomprado_com_acesso_vigente_estende_do_fim_atual(self):
        # TESTE 5 (protege dinheiro): Pix não tem parcelamento — se o mesmo CPF paga
        # de novo com acesso ainda vigente, NÃO é parcela (como no cartão): é um NOVO
        # período comprado antes de vencer. Sem isso o pagamento seria engolido em
        # silêncio. Estende a partir do FIM do acesso ATUAL (não de hoje), senão o
        # assinante perde os dias que ainda tinha.
        reg = self.s.criar_de_pagamento(
            {"nome": "Dr. Pix5", "whatsapp": "5543999990006", "email": "pix5@x.com",
             "cpf": "11144477735", "plano": "mensal"},
            {"customer": "cus_5", "payment": "pay_5_1", "proximo_vencimento": "2026-08-01"})
        self.s.marcar_status(reg["id"], "ATIVO", acesso_ate="2026-08-01")   # ainda no futuro
        import asaas, email_send
        self.cfg.ASAAS_API_KEY = "k"
        orig_cli = asaas.obter_cliente
        asaas.obter_cliente = lambda cid: {"name": "Dr. Pix5", "mobilePhone": "5543999990006",
                                           "email": "pix5@x.com", "cpfCnpj": "111.444.777-35"}
        emails = []
        orig_email = email_send.enviar
        email_send.enviar = lambda to, assunto, html: emails.append((to, assunto, html))
        try:
            st, msg = self.w.processar(self._body(ext="tok5", pid="pay_5_2", sub=None),
                                       "segredo", enviar_fn=self.envfn)
        finally:
            asaas.obter_cliente = orig_cli
            self.cfg.ASAAS_API_KEY = None
            email_send.enviar = orig_email
        self.assertEqual((st, msg), (200, "pix-recomprado-estendido"))
        atual = self.s.por_id(reg["id"])
        self.assertEqual(atual["acesso_ate"], "2026-08-31")          # 01 ago + 30d, a partir do FIM ATUAL
        self.assertEqual(atual["proximo_vencimento"], "2026-08-31")
        self.assertEqual(atual["asaas_payment_id"], "pay_5_2")        # referência atualizada
        self.assertEqual(len(emails), 1)                              # e-mail de confirmação enviado
        self.assertEqual(len(self.enviados), 0)                       # sem boas-vindas por WhatsApp

    def test_pix_recomprado_atualiza_valor_contratado(self):
        # ACHADO 1 (revisão): recompra de Pix ANTES de vencer é assinante EXISTENTE —
        # sem regravar valor_contratado aqui, um assinante que volta pagando um preço
        # diferente ficaria com o valor antigo, e a renovação seguinte cobraria errado.
        reg = self.s.criar_de_pagamento(
            {"nome": "Dr. VC2", "whatsapp": "5543999990011", "email": "vc2@x.com",
             "cpf": "11144477735", "plano": "mensal", "valor_contratado": 97.00},
            {"customer": "cus_vc2", "payment": "pay_vc2_1", "proximo_vencimento": "2026-08-01"})
        self.s.marcar_status(reg["id"], "ATIVO", acesso_ate="2026-08-01")   # ainda no futuro
        import asaas
        self.cfg.ASAAS_API_KEY = "k"
        orig_cli = asaas.obter_cliente
        asaas.obter_cliente = lambda cid: {"name": "Dr. VC2", "mobilePhone": "5543999990011",
                                           "email": "vc2@x.com", "cpfCnpj": "111.444.777-35"}
        try:
            st, msg = self.w.processar(self._body_valor(ext="tokvc2", pid="pay_vc2_2", value=147.00),
                                       "segredo", enviar_fn=self.envfn)
        finally:
            asaas.obter_cliente = orig_cli
            self.cfg.ASAAS_API_KEY = None
        self.assertEqual((st, msg), (200, "pix-recomprado-estendido"))
        atual = self.s.por_id(reg["id"])
        self.assertEqual(atual["valor_contratado"], 147.00)      # atualizado, não ficou 97.00

    def test_parcela_cartao_com_acesso_vigente_nao_estende_nem_envia_email(self):
        # TESTE 6 (protege dinheiro): parcela de um cartão parcelado (`installment`
        # preenchido) NÃO é um novo período — é a MESMA compra sendo paga aos poucos.
        # Mesmo que o assinante já tenha uma data de acesso no futuro (edge case),
        # a parcela não pode estender nem mandar e-mail de renovação.
        reg = self.s.criar_de_pagamento(
            {"nome": "Dr. Parc6", "whatsapp": "5543999990005", "email": "parc6@x.com",
             "cpf": "11144477735", "plano": "anual"},
            {"customer": "cus_6", "payment": "pay_6_1", "proximo_vencimento": "2026-08-19"})
        self.s.marcar_status(reg["id"], "ATIVO", acesso_ate="2026-08-19")   # data no futuro (edge case)
        import asaas, email_send
        self.cfg.ASAAS_API_KEY = "k"
        orig_cli = asaas.obter_cliente
        asaas.obter_cliente = lambda cid: {"name": "Dr. Parc6", "mobilePhone": "5543999990005",
                                           "email": "parc6@x.com", "cpfCnpj": "111.444.777-35"}
        emails = []
        orig_email = email_send.enviar
        email_send.enviar = lambda to, assunto, html: emails.append((to, assunto))
        try:
            st, msg = self.w.processar(self._body(ext="tok6", pid="pay_6_2", sub=None, installment="inst_6"),
                                       "segredo", enviar_fn=self.envfn)
        finally:
            asaas.obter_cliente = orig_cli
            self.cfg.ASAAS_API_KEY = None
            email_send.enviar = orig_email
        self.assertEqual((st, msg), (200, "parcela-registrada"))
        atual = self.s.por_id(reg["id"])
        self.assertEqual(atual["acesso_ate"], "2026-08-19")     # NÃO estendeu
        self.assertEqual(atual["asaas_payment_id"], "pay_6_2")   # só a referência do pagamento avançou
        self.assertEqual(emails, [])                             # nenhum e-mail

    def test_falha_no_email_de_renovacao_nao_derruba_renovacao(self):
        # TESTE 8a (spec renovação): falha no envio nunca pode derrubar a renovação.
        self.s.criar_de_pagamento(
            {"nome": "E1", "whatsapp": "5543", "email": "e1@x.com", "plano": "mensal"},
            {"subscription": "sub_fail1"})
        import email_send
        orig_email = email_send.enviar
        email_send.enviar = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("smtp down"))
        try:
            st, msg = self.w.processar(self._body(event="PAYMENT_RECEIVED", pid="pfail1", sub="sub_fail1"),
                                       "segredo", enviar_fn=self.envfn)
        finally:
            email_send.enviar = orig_email
        self.assertEqual((st, msg), (200, "renovado"))

    def test_falha_no_email_de_recontratacao_nao_derruba_ativacao(self):
        # TESTE 8b (spec renovação): idem, no caminho de recontratação (ATIVAR).
        reg = self.s.criar_de_pagamento(
            {"nome": "Dr. F", "whatsapp": "5543999990004", "email": "f@x.com",
             "cpf": "11144477735", "plano": "anual"},
            {"customer": "cus_f", "payment": "pay_f_velho", "proximo_vencimento": "2025-07-01"})
        self.s.marcar_status(reg["id"], "ATIVO", acesso_ate="2025-07-01T00:00:00")
        import asaas, email_send
        self.cfg.ASAAS_API_KEY = "k"
        orig_cli = asaas.obter_cliente
        asaas.obter_cliente = lambda cid: {"name": "Dr. F", "mobilePhone": "5543999990004",
                                           "email": "f@x.com", "cpfCnpj": "111.444.777-35"}
        orig_email = email_send.enviar
        email_send.enviar = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("smtp down"))
        try:
            st, msg = self.w.processar(self._body(ext="tok_f", pid="pay_f_novo", sub=None),
                                       "segredo", enviar_fn=self.envfn)
        finally:
            asaas.obter_cliente = orig_cli
            self.cfg.ASAAS_API_KEY = None
            email_send.enviar = orig_email
        self.assertEqual((st, msg), (200, "ativado"))   # não quebrou a ativação


class TestAvisarVenda(unittest.TestCase):
    def test_avisar_venda_monta_email(self):
        import webhook_asaas, email_send
        chamado = {}
        orig = email_send.enviar
        email_send.enviar = lambda to, assunto, html: chamado.update(to=to, assunto=assunto, html=html)
        try:
            webhook_asaas._avisar_venda("Fulano", "Anual", "960", "f@x.com", 37)
        finally:
            email_send.enviar = orig
        self.assertIn("Anual", chamado["assunto"])
        self.assertIn("Fulano", chamado["html"])
        self.assertIn("37", chamado["html"])

    def test_avisar_venda_com_afiliado_mostra_comissao(self):
        import webhook_asaas, email_send
        chamado = {}
        orig = email_send.enviar
        email_send.enviar = lambda to, assunto, html: chamado.update(to=to, assunto=assunto, html=html)
        try:
            webhook_asaas._avisar_venda("Fulano", "Anual", "960", "f@x.com", 37,
                                        afiliado="Dra. Maria", comissao=26.92)
        finally:
            email_send.enviar = orig
        self.assertIn("Dra. Maria", chamado["html"])
        self.assertIn("26.92", chamado["html"])

    def test_avisar_venda_afiliado_sem_comissao_nao_mostra_valor(self):
        import webhook_asaas, email_send
        chamado = {}
        orig = email_send.enviar
        email_send.enviar = lambda to, assunto, html: chamado.update(html=html)
        try:
            webhook_asaas._avisar_venda("Fulano", "Anual", "897.30", "x", 1,
                                        afiliado="Dra. Maria", comissao=None)
        finally:
            email_send.enviar = orig
        self.assertIn("Dra. Maria", chamado["html"])       # afiliado ainda aparece
        self.assertNotIn("R$ None", chamado["html"])       # mas sem valor de comissão fantasma

    def test_avisar_venda_nao_propaga_erro(self):
        import webhook_asaas, email_send
        orig = email_send.enviar
        email_send.enviar = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("smtp down"))
        try:
            webhook_asaas._avisar_venda("F", "Mensal", "99", "x", 1)  # não pode levantar
        finally:
            email_send.enviar = orig


if __name__ == "__main__":
    unittest.main()
