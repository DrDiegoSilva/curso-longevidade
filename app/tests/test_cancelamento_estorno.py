"""Testes do estorno automático no cancelamento (7 dias). Sem rede. Standalone."""
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _sub(dias_atras, pid="pay_1", sid="sub_1"):
    return {"id": "s1", "nome": "Teste", "email": "t@e.com",
            "asaas_payment_id": pid, "asaas_subscription_id": sid,
            "criado_em": (datetime.now() - timedelta(days=dias_atras)).isoformat()}


class TestEstornoArrependimento(unittest.TestCase):
    def setUp(self):
        import serve, asaas, db
        self.serve, self.asaas, self.db = serve, asaas, db
        self.estornos = []
        self.comissoes = []
        self.alertas = []

        self._orig = (asaas.obter_pagamento, asaas.estornar_pagamento,
                      asaas.estornar_parcelamento, db.estornar_comissao)
        asaas.obter_pagamento = lambda pid: {"id": pid, "value": 997.0}
        # Gravam também `valor` de propósito (ACHADO 5): a regra é estorno sempre
        # INTEGRAL, nunca parcial. Um mutante que passasse `asaas.estornar_pagamento(alvo,
        # valor)` (estorno PARCIAL) passaria verde se os fakes descartassem esse argumento.
        asaas.estornar_pagamento = lambda pid, valor=None: self.estornos.append(("payment", pid, valor))
        asaas.estornar_parcelamento = lambda iid, valor=None: self.estornos.append(("installment", iid, valor))
        db.estornar_comissao = lambda sid: self.comissoes.append(sid) or 1

        import webhook_asaas
        self._orig_alerta = webhook_asaas._alertar_admin
        webhook_asaas._alertar_admin = lambda pid, sid, motivo: self.alertas.append(motivo)

    def tearDown(self):
        (self.asaas.obter_pagamento, self.asaas.estornar_pagamento,
         self.asaas.estornar_parcelamento, self.db.estornar_comissao) = self._orig
        import webhook_asaas
        webhook_asaas._alertar_admin = self._orig_alerta

    def test_cancelou_no_dia_3_estorna_integral(self):
        valor = self.serve.estornar_arrependimento(_sub(3))
        self.assertEqual(valor, (997.0, "payment"))
        self.assertEqual(self.estornos, [("payment", "pay_1", None)])
        self.assertEqual(self.comissoes, ["s1"])

    def test_cancelou_no_dia_30_nao_estorna(self):
        self.assertIsNone(self.serve.estornar_arrependimento(_sub(30)))
        self.assertEqual(self.estornos, [])

    def test_parcelado_estorna_o_parcelamento_inteiro(self):
        # ACHADO 1 (bloqueante): "value" aqui é o de UMA parcela (83.08); quem chama
        # tem que saber, pelo `tipo`, que esse número NÃO é o total estornado (o
        # Asaas estorna o parcelamento inteiro) — daí o e-mail não poder imprimi-lo.
        self.asaas.obter_pagamento = lambda pid: {"id": pid, "value": 83.08, "installment": "ins_9"}
        valor, tipo = self.serve.estornar_arrependimento(_sub(2))
        self.assertEqual(tipo, "installment")
        self.assertEqual(self.estornos, [("installment", "ins_9", None)])

    def test_cortesia_sem_pagamento_nao_estorna_nem_alerta(self):
        # cupom de cortesia entra sem asaas_payment_id — não é falha, é ausência de cobrança
        self.assertIsNone(self.serve.estornar_arrependimento(_sub(2, pid=None)))
        self.assertEqual(self.estornos, [])
        self.assertEqual(self.alertas, [])

    def test_falha_no_estorno_alerta_e_devolve_none(self):
        def explode(pid, valor=None):
            raise RuntimeError("saldo insuficiente")
        self.asaas.estornar_pagamento = explode
        self.assertIsNone(self.serve.estornar_arrependimento(_sub(2)))
        self.assertEqual(len(self.alertas), 1)
        self.assertIn("estorno", self.alertas[0].lower())
        self.assertEqual(self.comissoes, [])   # estorno nunca saiu -> nada a dar baixa

    def test_estorno_ok_mas_baixa_de_comissao_falha_devolve_valor_e_alerta_diferente(self):
        # ACHADO 1: o estorno no Asaas já saiu — a falha é só na baixa da comissão do
        # afiliado. A função tem que devolver o valor (não None) e o alerta precisa
        # deixar claro que o estorno DEU CERTO, não usar a mensagem de "estorno falhou".
        def explode(sid):
            raise RuntimeError("database is locked")
        self.db.estornar_comissao = explode
        valor = self.serve.estornar_arrependimento(_sub(3))
        self.assertEqual(valor, (997.0, "payment"))
        self.assertEqual(self.estornos, [("payment", "pay_1", None)])
        self.assertEqual(len(self.alertas), 1)
        msg = self.alertas[0].lower()
        self.assertIn("comiss", msg)
        self.assertNotIn("estorne manualmente no painel do asaas", msg)

    def test_falha_ambigua_com_estorno_ja_processado_conta_como_sucesso(self):
        # IMPORTANT A: timeout de rede DEPOIS de o Asaas ter processado o estorno. Se
        # isso virasse "não estornou", o alerta pediria estorno manual em cima de um
        # estorno já feito (devolução em dobro) e o cliente ficaria com acesso pago de
        # volta. A re-consulta ao Asaas desfaz a ambiguidade. REFUNDED é definitivo:
        # nenhum alerta extra de confirmação (diferente de REFUND_IN_PROGRESS, abaixo).
        def timeout(pid, valor=None):
            raise RuntimeError("timed out")
        self.asaas.estornar_pagamento = timeout
        self.asaas.obter_pagamento = lambda pid: {"id": pid, "value": 997.0, "status": "REFUNDED"}
        valor = self.serve.estornar_arrependimento(_sub(3))
        self.assertEqual(valor, (997.0, "payment"))
        self.assertEqual(self.alertas, [])          # nada de "estorne manualmente"
        self.assertEqual(self.comissoes, ["s1"])     # e a comissão do afiliado cai junto

    def test_falha_ambigua_com_estorno_em_processamento_conta_como_sucesso_mas_alerta(self):
        # IMPORTANT 3: REFUND_REQUESTED/REFUND_IN_PROGRESS ainda NÃO terminaram no
        # Asaas. Continua tratado como sucesso (não re-estorna — evitaria duplicidade),
        # mas se isso falhar depois (ex.: Pix sem saldo na conta Asaas) o cliente fica
        # sem dinheiro E sem acesso, e ninguém saberia — por isso alerta pedindo
        # confirmação, mesmo seguindo como sucesso.
        def timeout(pid, valor=None):
            raise RuntimeError("timed out")
        self.asaas.estornar_pagamento = timeout
        self.asaas.obter_pagamento = lambda pid: {"id": pid, "value": 997.0,
                                                   "status": "REFUND_IN_PROGRESS"}
        valor = self.serve.estornar_arrependimento(_sub(3))
        self.assertEqual(valor, (997.0, "payment"))
        self.assertEqual(len(self.alertas), 1)
        self.assertIn("confir", self.alertas[0].lower())
        self.assertEqual(self.comissoes, ["s1"])     # segue dando baixa na comissão

    def test_falha_ambigua_com_pagamento_ainda_confirmado_alerta_e_devolve_none(self):
        # O Asaas diz que NÃO houve estorno: aí é falha de verdade — alerta e None.
        def timeout(pid, valor=None):
            raise RuntimeError("timed out")
        self.asaas.estornar_pagamento = timeout
        self.asaas.obter_pagamento = lambda pid: {"id": pid, "value": 997.0, "status": "CONFIRMED"}
        self.assertIsNone(self.serve.estornar_arrependimento(_sub(3)))
        self.assertEqual(len(self.alertas), 1)
        self.assertIn("estorne manualmente", self.alertas[0].lower())

    def test_falha_ambigua_com_reconsulta_tambem_falhando_devolve_none(self):
        # Sem conseguir confirmar nada, não afirmamos que o dinheiro saiu.
        chamadas = []

        def obter(pid):
            chamadas.append(pid)
            if len(chamadas) == 1:
                return {"id": pid, "value": 997.0}
            raise RuntimeError("asaas fora do ar")
        self.asaas.obter_pagamento = obter
        self.asaas.estornar_pagamento = lambda pid, valor=None: (_ for _ in ()).throw(RuntimeError("timeout"))
        self.assertIsNone(self.serve.estornar_arrependimento(_sub(3)))
        self.assertEqual(len(self.alertas), 1)

    def test_estorno_parcial_no_asaas_nao_conta_como_sucesso(self):
        # Nosso estorno é sempre INTEGRAL: devolução parcial significa que algo diferente
        # aconteceu e precisa de olho humano — não pode passar por sucesso.
        self.asaas.estornar_pagamento = lambda pid, valor=None: (_ for _ in ()).throw(RuntimeError("timeout"))
        self.asaas.obter_pagamento = lambda pid: {"id": pid, "value": 997.0, "status": "PARTIALLY_REFUNDED"}
        self.assertIsNone(self.serve.estornar_arrependimento(_sub(3)))
        self.assertEqual(len(self.alertas), 1)

    def test_valor_nao_numerico_falha_antes_de_mover_dinheiro(self):
        # ACHADO 3: "value" não-numérico tem que estourar DENTRO do try, antes de
        # chamar o Asaas — nunca depois do dinheiro já ter saído. Se a exceção
        # subisse depois do estorno, o chamador nunca rodaria registrar_cancelamento
        # (cliente reembolsado e ainda ATIVO).
        self.asaas.obter_pagamento = lambda pid: {"id": pid, "value": "NaN-inválido"}
        self.assertIsNone(self.serve.estornar_arrependimento(_sub(3)))
        self.assertEqual(self.estornos, [])          # dinheiro NUNCA saiu
        self.assertEqual(len(self.alertas), 1)
        self.assertIn("estorno", self.alertas[0].lower())


class _HandlerStub:
    """Stub mínimo pro `self` de _executar_cancelamento: o método só usa
    `self._html` (não abre socket nenhum — não é uma requisição HTTP real)."""

    def _html(self, s, code=200):
        return s


class TestExecutarCancelamento(unittest.TestCase):
    """Cobre o fluxo novo: o claim atômico GRAVA o cancelamento inteiro antes de
    qualquer trabalho, e o estorno é um ajuste posterior.

    O que os testes precisam provar (foi aqui que as duas rodadas anteriores
    vazaram): não existe mais janela entre "reservei o cancelamento" e "o
    cancelamento existe"; o perdedor da corrida não regrava nada; e nada se move em
    dinheiro quando o estado do banco não pôde ser confirmado.

    Chama o método com um `self` stub — ele só usa `self._html` internamente."""

    def setUp(self):
        import serve, subscribers, asaas, email_send, site_web, db, webhook_asaas
        self.serve, self.subscribers, self.asaas = serve, subscribers, asaas
        self.email_send, self.site_web, self.db = email_send, site_web, db
        self.webhook_asaas = webhook_asaas

        self.claims = []          # chamadas a db.claim_cancelamento (id, motivo, acesso_ate)
        self.encerrados = []      # chamadas a db.encerrar_acesso
        self.emails = []          # chamadas a email_send.enviar
        self.paginas = []         # chamadas a site_web.pagina_cancelado
        self.cancelados_asaas = []  # chamadas a asaas.cancelar_assinatura
        self.alertas = []         # chamadas a webhook_asaas._alertar_admin

        self._orig = (subscribers.por_id, asaas.cancelar_assinatura, email_send.enviar,
                      site_web.pagina_cancelado, db.claim_cancelamento, db.encerrar_acesso,
                      serve.estornar_arrependimento, webhook_asaas._alertar_admin)

        subscribers.por_id = lambda sid: None      # sobrescrito nos testes que precisam
        asaas.cancelar_assinatura = lambda sid: self.cancelados_asaas.append(sid)
        email_send.enviar = lambda to, assunto, html: self.emails.append(
            {"to": to, "assunto": assunto, "html": html})
        site_web.pagina_cancelado = lambda acesso_ate="": self.paginas.append(
            acesso_ate) or f"<pagina acesso_ate={acesso_ate!r}>"
        db.claim_cancelamento = lambda sid, motivo, acesso_ate: self.claims.append(
            {"id": sid, "motivo": motivo, "acesso_ate": acesso_ate}) or True   # vence por padrão
        db.encerrar_acesso = lambda sid: self.encerrados.append(sid) or True
        serve.estornar_arrependimento = lambda sub: None   # por padrão sem estorno
        webhook_asaas._alertar_admin = lambda pid, sid, motivo: self.alertas.append(motivo)

        self.stub = _HandlerStub()

    def tearDown(self):
        (self.subscribers.por_id, self.asaas.cancelar_assinatura, self.email_send.enviar,
         self.site_web.pagina_cancelado, self.db.claim_cancelamento, self.db.encerrar_acesso,
         self.serve.estornar_arrependimento, self.webhook_asaas._alertar_admin) = self._orig

    def _sub(self, **over):
        base = {"id": "s1", "nome": "Teste", "email": "t@e.com",
                "asaas_subscription_id": "sub_1", "proximo_vencimento": "2026-12-31"}
        base.update(over)
        return base

    def _chamar(self, sub, motivo):
        # _executar_cancelamento é um método de instância de Handler; chamamos a
        # função "crua" da classe passando o stub como self (não dá pra
        # instanciar Handler de verdade sem uma conexão HTTP real).
        return self.serve.Handler._executar_cancelamento(self.stub, sub, motivo)

    def test_grava_o_cancelamento_completo_antes_de_qualquer_trabalho(self):
        # O claim recebe o estado FINAL (motivo + acesso_ate padrão) e é gravado antes de
        # falar com o Asaas: se tudo explodir daqui pra frente, o cancelamento já existe
        # e está correto (acesso até o fim do período pago).
        ordem = []
        self.db.claim_cancelamento = lambda sid, motivo, acesso_ate: (
            ordem.append("claim") or self.claims.append(
                {"id": sid, "motivo": motivo, "acesso_ate": acesso_ate}) or True)
        self.asaas.cancelar_assinatura = lambda sid: ordem.append("asaas")
        self.serve.estornar_arrependimento = lambda sub: ordem.append("estorno") or None
        self._chamar(self._sub(), "não uso mais")
        self.assertEqual(ordem, ["claim", "asaas", "estorno"])
        self.assertEqual(self.claims, [{"id": "s1", "motivo": "não uso mais",
                                        "acesso_ate": "2026-12-31"}])

    def test_dentro_dos_7_dias_zera_acesso_e_email_de_reembolso(self):
        self.serve.estornar_arrependimento = lambda sub: (997.0, "payment")
        self._chamar(self._sub(), "mudei de ideia")
        # o claim grava o acesso padrão; o estorno é o AJUSTE que zera depois
        self.assertEqual(self.claims[0]["acesso_ate"], "2026-12-31")
        self.assertEqual(self.encerrados, ["s1"])
        self.assertEqual(self.paginas, [None])
        self.assertEqual(len(self.emails), 1)
        self.assertIn("reembolso", self.emails[0]["html"].lower())
        self.assertIn("997,00", self.emails[0]["html"])   # ACHADO 1: valor certo, em pt-BR

    def test_estorno_de_zero_ainda_conta_como_estorno(self):
        # `estornado is not None` importa: 0.0 é um estorno VÁLIDO (pagamento de valor
        # zero/cortesia paga). Com truthiness (`if estornado:`) este teste quebra — o
        # acesso não seria encerrado e o e-mail seria o comum, não o de reembolso.
        self.serve.estornar_arrependimento = lambda sub: (0.0, "payment")
        self._chamar(self._sub(), "mudei de ideia")
        self.assertEqual(self.encerrados, ["s1"])
        self.assertEqual(self.paginas, [None])
        self.assertIn("reembolso", self.emails[0]["html"].lower())

    def test_estorno_parcelado_nao_mostra_valor_da_parcela_no_email(self):
        # ACHADO 1 (bloqueante): no cartão parcelado o Asaas estorna o PARCELAMENTO
        # inteiro (ex.: R$ 997), mas o valor que `estornar_arrependimento` devolve é o
        # de UMA parcela (ex.: R$ 83,08) — não existe, aqui, o total certo pra mostrar.
        # Com tipo == "installment" o e-mail não pode imprimir NENHUM valor (nem o
        # errado), só confirmar que o reembolso integral foi pedido.
        self.serve.estornar_arrependimento = lambda sub: (83.08, "installment")
        self._chamar(self._sub(), "mudei de ideia")
        self.assertEqual(len(self.emails), 1)
        html = self.emails[0]["html"]
        self.assertIn("reembolso integral", html.lower())
        self.assertNotIn("83,08", html)
        self.assertNotIn("83.08", html)

    def test_fora_dos_7_dias_mantem_proximo_vencimento_sem_reembolso_no_email(self):
        self.serve.estornar_arrependimento = lambda sub: None
        self._chamar(self._sub(), "não uso mais")
        self.assertEqual(self.claims[0]["acesso_ate"], "2026-12-31")
        self.assertEqual(self.encerrados, [])         # nada a ajustar: o estado gravado já vale
        self.assertEqual(self.paginas, ["2026-12-31"])
        self.assertEqual(len(self.emails), 1)
        self.assertNotIn("reembolso", self.emails[0]["html"].lower())

    def test_falha_ao_encerrar_acesso_apos_estorno_nao_derruba_e_alerta(self):
        # O dinheiro já saiu e o cancelamento já está gravado — só o ajuste do acesso
        # ficou pendente. Não pode virar erro na tela do cliente.
        self.serve.estornar_arrependimento = lambda sub: (997.0, "payment")
        self.db.encerrar_acesso = lambda sid: (_ for _ in ()).throw(RuntimeError("database is locked"))
        self._chamar(self._sub(), "mudei de ideia")
        self.assertEqual(len(self.emails), 1)
        self.assertEqual(self.paginas, [None])
        self.assertEqual(len(self.alertas), 1)
        self.assertIn("acesso", self.alertas[0].lower())

    def test_perdeu_o_claim_nao_estorna_nao_regrava_e_rele_do_banco(self):
        # A 1ª chamada já cancelou (com ou sem estorno) e gravou o estado final. A 2ª
        # (duplo clique/retry) perde o claim: não repete estorno, não regrava, não manda
        # 2º e-mail. A página tem que mostrar o que está PERSISTIDO — por isso o stub
        # devolve um acesso_ate DIFERENTE do padrão em memória: se o código reusasse o
        # `sub` da sessão, mostraria "2026-12-31" e este teste quebraria.
        self.db.claim_cancelamento = lambda sid, motivo, acesso_ate: False
        self.subscribers.por_id = lambda sid: self._sub(acesso_ate="2026-08-15")
        self.serve.estornar_arrependimento = lambda sub: self.fail("não podia estornar de novo")
        self._chamar(self._sub(), "mudei de ideia")
        self.assertEqual(self.emails, [])
        self.assertEqual(self.cancelados_asaas, [])
        self.assertEqual(self.paginas, ["2026-08-15"])

    def test_falha_no_claim_com_cancelamento_ja_no_banco_e_tratada_como_perdida(self):
        # A exceção pode ter estourado DEPOIS do commit. A releitura mostra o
        # cancelamento gravado -> foi corrida perdida (ou foi a própria chamada que
        # commitou e a exceção estourou depois — indistinguível daqui): nada de
        # estornar de novo, mas o admin é SEMPRE avisado pra conferir manualmente
        # (ACHADO 2) — sem isso, o caso "commitou e explodiu depois" (Asaas nunca
        # cancelado, cliente seguindo cobrado) passaria em silêncio total.
        def explode(sid, motivo, acesso_ate):
            raise RuntimeError("connection reset")
        self.db.claim_cancelamento = explode
        self.subscribers.por_id = lambda sid: self._sub(status="CANCELADO",
                                                        cancelado_em="2026-07-24T10:00:00",
                                                        acesso_ate=None)
        self.serve.estornar_arrependimento = lambda sub: self.fail("estado já cancelado: não estorna")
        self._chamar(self._sub(), "mudei de ideia")
        self.assertEqual(self.emails, [])
        self.assertEqual(self.paginas, [None])
        self.assertEqual(len(self.alertas), 1)
        self.assertIn("asaas", self.alertas[0].lower())

    def test_falha_no_claim_com_banco_ok_e_sem_cancelamento_tenta_gravar_de_novo(self):
        # A releitura prova que o UPDATE não passou: o banco responde e o assinante
        # continua ATIVO. Aí é seguro (e obrigatório) tentar gravar de novo — e só assim
        # o cliente dentro dos 7 dias recebe o reembolso a que tem direito.
        tentativas = []

        def as_vezes(sid, motivo, acesso_ate):
            tentativas.append(acesso_ate)
            if len(tentativas) == 1:
                raise RuntimeError("database is locked")
            return True
        self.db.claim_cancelamento = as_vezes
        self.subscribers.por_id = lambda sid: self._sub(status="ATIVO")
        self.serve.estornar_arrependimento = lambda sub: (997.0, "payment")
        self._chamar(self._sub(), "mudei de ideia")
        self.assertEqual(tentativas, ["2026-12-31", "2026-12-31"])
        self.assertEqual(self.encerrados, ["s1"])         # estornou e encerrou o acesso
        self.assertEqual(len(self.emails), 1)

    def test_claim_e_releitura_falhando_segue_o_cancelamento_mas_nao_move_dinheiro(self):
        # Estado desconhecido: nunca estornar (poderia devolver em dobro por cima de um
        # cancelamento que já existe). Mas o cliente NÃO pode ficar preso: o Asaas é
        # cancelado, o e-mail sai e o admin é avisado para conferir na mão.
        def explode(*a, **k):
            raise RuntimeError("database is locked")
        self.db.claim_cancelamento = explode
        self.subscribers.por_id = explode
        self.serve.estornar_arrependimento = lambda sub: self.fail("estado desconhecido: não estorna")
        self._chamar(self._sub(), "mudei de ideia")
        self.assertEqual(self.cancelados_asaas, ["sub_1"])   # assinatura cancelada mesmo assim
        self.assertEqual(len(self.emails), 1)                  # cliente avisado
        self.assertEqual(len(self.alertas), 1)                 # admin avisado
        self.assertIn("estorn", self.alertas[0].lower())

    def test_falha_ao_cancelar_no_asaas_alerta_o_admin(self):
        # Sem alerta, a assinatura seguiria cobrando em silêncio: o claim já foi
        # consumido, então uma nova tentativa do cliente nem chega no Asaas.
        self.asaas.cancelar_assinatura = lambda sid: (_ for _ in ()).throw(RuntimeError("502"))
        self._chamar(self._sub(), "não uso mais")
        self.assertEqual(len(self.alertas), 1)
        self.assertIn("asaas", self.alertas[0].lower())
        self.assertEqual(len(self.emails), 1)          # e o cancelamento segue normal

    def test_cortesia_sem_assinatura_no_asaas_nao_chama_nem_alerta(self):
        self._chamar(self._sub(asaas_subscription_id=None), "não uso mais")
        self.assertEqual(self.cancelados_asaas, [])
        self.assertEqual(self.alertas, [])

    def test_falha_no_email_nao_derruba_a_pagina_de_cancelado(self):
        # O cancelamento já está gravado; um problema no e-mail não pode virar erro 500
        # para quem está na tela.
        self.email_send.enviar = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("smtp down"))
        self._chamar(self._sub(), "não uso mais")
        self.assertEqual(self.paginas, ["2026-12-31"])


if __name__ == "__main__":
    unittest.main()
