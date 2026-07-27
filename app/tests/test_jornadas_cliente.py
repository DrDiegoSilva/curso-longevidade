"""MALHA DE JORNADAS — "pagou X, recebeu Y" para cada tipo de cliente.

Por que este arquivo existe: as quatro rodadas de revisão do branch acharam quase todos os
erros de dinheiro no MESMO ponto cego — testes que montavam o assinante por fixture, num
estado que a produção nunca produz. O caso mais caro: a suíte inteira criava assinante de
cartão parcelado chamando `criar_de_pagamento` na mão, então ninguém percebeu que o webhook
não gravava o grupo de parcelamento — e a parcela 2 de todo anual em 12x dava um ano extra.

A regra deste arquivo, então:

  1. NENHUM assinante é criado por fixture. Todo estado é construído REPLAYANDO os eventos
     do Asaas por `webhook_asaas.processar`, exatamente como em produção.
  2. As expectativas vêm das REGRAS DE NEGÓCIO (o que o cliente pagou x o que tem direito),
     nunca do que o código faz hoje. Um teste que descreve o comportamento atual não
     encontra bug nenhum.
  3. Cada jornada afirma o desfecho em dinheiro e acesso: status, até quando tem acesso,
     que plano ficou gravado e QUANTO a próxima renovação vai cobrar.

Passagem de tempo é simulada movendo `acesso_ate`/`proximo_vencimento` para o passado — é a
única coisa que não dá para obter replayando eventos, já que o código lê o relógio real.
"""
import os
import sys
import importlib
import tempfile
import unittest
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

CPF = "11144477735"
WPP = "5543999990000"
EMAIL = "a@x.com"


class JornadaBase(unittest.TestCase):
    """Ferramental. Cada teste monta a história do cliente com os `passo_*` e depois afirma."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._env0 = {k: os.environ.get(k) for k in
                      ("DSCURSO_DATA", "DSCURSO_ARTIGOS_DB", "ASAAS_WEBHOOK_TOKEN")}
        os.environ["DSCURSO_DATA"] = self.tmp
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["ASAAS_WEBHOOK_TOKEN"] = "segredo"
        for m in ("config", "db", "subscribers", "webhook_asaas", "renovacao", "refunds",
                  "pricing", "regua"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import config, db, subscribers, webhook_asaas, renovacao, pricing, regua
        for mod in (config, db, subscribers, webhook_asaas, renovacao, pricing, regua):
            importlib.reload(mod)
        self.cfg, self.db, self.s = config, db, subscribers
        self.w, self.renovacao, self.pricing, self.regua = webhook_asaas, renovacao, pricing, regua
        self.s._migrado = False
        db.init()
        self.wa = []            # WhatsApp de boas-vindas
        self.emails = []        # e-mails disparados
        import deliver, email_send
        self._orig = (deliver.enviar_texto, email_send.enviar, deliver.enviar_admin)
        deliver.enviar_texto = lambda w, m: self.wa.append((w, m))
        deliver.enviar_admin = lambda m: None
        email_send.enviar = lambda to, a, h: self.emails.append((to, a))
        self.deliver, self.email_send = deliver, email_send
        self._n = 0

    def tearDown(self):
        self.deliver.enviar_texto, self.email_send.enviar, self.deliver.enviar_admin = self._orig
        for k, v in self._env0.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

    # ── passos: cada um é um evento real do Asaas ──
    def _pid(self, prefixo="pay"):
        self._n += 1
        return f"{prefixo}_{self._n}"

    def _checkout(self, plano="anual", metodo="PIX", parcelas=1, cupom=""):
        """Cria o pending como o checkout do site cria, com o preço da tabela vigente."""
        p = self.cfg.plano_por_slug(plano)
        base_vig = self.pricing.preco_vigente(p, len(self.s.ativos()))
        base_final = self.pricing.base_cobrada(p, metodo, base_vig, 0.0)
        return self.db.criar_pending({"nome": "Dr. A", "whatsapp": WPP, "email": EMAIL,
                                      "cpf": CPF, "plano": plano, "metodo": metodo,
                                      "parcelas": parcelas, "valor": base_final,
                                      "valor_base": base_vig,
                                      "afiliado_codigo": cupom}), base_final, base_vig

    def paga(self, plano="anual", metodo="PIX", parcelas=1, evento="PAYMENT_CONFIRMED",
             sub_id=None, grupo=None, n_parcela=None, pid=None, tok=None, valor=None,
             venc="2026-07-19", cupom=""):
        """Um pagamento confirmado pelo Asaas. Devolve (status, msg)."""
        if tok is None:
            tok, base_final, _ = self._checkout(plano, metodo, parcelas, cupom)
            valor = base_final if valor is None else valor
            if parcelas > 1:
                valor = round(base_final / parcelas, 2)
        pay = {"id": pid or self._pid(), "externalReference": tok, "customer": "cus_1",
               "subscription": sub_id, "dueDate": venc, "value": valor, "cpfCnpj": CPF}
        if grupo:
            pay["installment"] = grupo
            pay["installmentNumber"] = n_parcela or 1
        return self.w.processar({"event": evento, "payment": pay}, "segredo",
                                enviar_fn=lambda w, m: self.wa.append((w, m))), tok

    def evento(self, tipo, pid, sub_id=None, valor=1099.0):
        pay = {"id": pid, "customer": "cus_1", "subscription": sub_id,
               "dueDate": "2026-07-19", "value": valor, "cpfCnpj": CPF}
        return self.w.processar({"event": tipo, "payment": pay}, "segredo",
                                enviar_fn=lambda w, m: self.wa.append((w, m)))

    def passa_o_tempo(self, dias):
        """Simula o relógio andando: joga o fim do acesso `dias` para trás."""
        sub = self.s.por_cpf(CPF)
        novo = (date.today() - timedelta(days=dias)).isoformat()
        self.s.marcar_status(sub["id"], sub["status"], acesso_ate=novo,
                             proximo_vencimento=novo)

    # ── leitura do desfecho ──
    def estado(self):
        sub = self.s.por_cpf(CPF) or self.s.por_whatsapp(WPP)
        if not sub:
            return None
        plano = self.cfg.plano_por_slug(sub.get("plano") or "") or {}
        return {
            "status": sub["status"],
            "tem_acesso": self.s.tem_acesso(sub),
            "acesso_ate": sub.get("acesso_ate"),
            "plano": sub.get("plano"),
            "cancelado": bool(sub.get("cancelado_em")),
            "grupo_parcelas": sub.get("asaas_installment_id"),
            "assinatura_asaas": sub.get("asaas_subscription_id"),
            "renovacao_cobraria": (self.renovacao.preco_renovacao(sub, plano) if plano else None),
            "na_regua": self.regua.na_regua(sub, plano),
        }

    def dias_de_acesso(self, a_partir_de="2026-07-19"):
        """Quantos dias de acesso o cliente ficou tendo, contados do vencimento da cobrança."""
        sub = self.s.por_cpf(CPF)
        if not sub or not sub.get("acesso_ate"):
            return None
        fim = datetime.fromisoformat(sub["acesso_ate"]).date()
        return (fim - date.fromisoformat(a_partir_de)).days

    def assert_recebeu_um_ano(self, msg=""):
        d = self.dias_de_acesso()
        self.assertIsNotNone(d, f"{msg}: sem acesso gravado")
        self.assertGreaterEqual(d, 365, f"{msg}: recebeu só {d} dias por um ANO pago")

    def boas_vindas_enviadas(self):
        return len([m for _w, m in self.wa if "senha" in m.lower() or "bem-vindo" in m.lower()])


class TestCompraNova(JornadaBase):
    """Cliente que nunca comprou. Pagou um período — tem que receber esse período."""

    def test_pix_anual(self):
        self.paga(plano="anual", metodo="PIX")
        e = self.estado()
        self.assert_recebeu_um_ano("Pix anual")
        self.assertEqual(e["plano"], "anual")
        self.assertTrue(e["tem_acesso"])
        self.assertEqual(e["renovacao_cobraria"], 1099.0)   # a BASE, não o valor com desconto
        self.assertEqual(self.boas_vindas_enviadas(), 1)

    def test_cartao_a_vista_anual(self):
        self.paga(plano="anual", metodo="CARTAO", sub_id="sub_1")
        e = self.estado()
        self.assertTrue(e["tem_acesso"])
        self.assertEqual(e["assinatura_asaas"], "sub_1")
        self.assertFalse(e["na_regua"])          # renova sozinho: régua não pode chamar
        self.assertEqual(e["renovacao_cobraria"], 1099.0)

    def test_cartao_12x_anual(self):
        self.paga(plano="anual", metodo="CARTAO", parcelas=12, grupo="g1", n_parcela=1)
        e = self.estado()
        self.assert_recebeu_um_ano("anual 12x")
        self.assertEqual(e["renovacao_cobraria"], 1099.0)   # não R$ 91,58
        self.assertTrue(e["na_regua"])           # parcelado NÃO renova sozinho
        self.assertEqual(self.boas_vindas_enviadas(), 1)

    def test_mensal_cartao(self):
        self.paga(plano="mensal", metodo="CARTAO", sub_id="sub_m")
        e = self.estado()
        self.assertEqual(e["plano"], "mensal")
        self.assertEqual(e["renovacao_cobraria"], 99.0)


class TestEventosRepetidos(JornadaBase):
    """O Asaas manda CONFIRMED e RECEIVED do mesmo pagamento, e re-tenta em falha.
    Nada disso pode virar período extra."""

    def test_confirmed_e_received_do_mesmo_pagamento(self):
        (_, _), tok = self.paga(plano="anual", metodo="PIX", pid="p1")
        antes = self.estado()
        self.paga(plano="anual", metodo="PIX", evento="PAYMENT_RECEIVED", pid="p1", tok=tok,
                  valor=1044.05)
        self.assertEqual(self.estado()["acesso_ate"], antes["acesso_ate"])
        self.assertEqual(self.boas_vindas_enviadas(), 1)      # não repete boas-vindas

    def test_doze_parcelas_dao_um_ano_e_nao_doze(self):
        _, tok = self.paga(plano="anual", metodo="CARTAO", parcelas=12, grupo="g1", n_parcela=1)
        depois_da_1 = self.estado()["acesso_ate"]
        for n in range(2, 13):
            self.paga(plano="anual", metodo="CARTAO", parcelas=12, grupo="g1", n_parcela=n,
                      tok=tok, valor=91.58)
        self.assertEqual(self.estado()["acesso_ate"], depois_da_1)
        self.assertEqual(self.boas_vindas_enviadas(), 1)

    def test_parcelas_sem_o_numero_da_parcela_no_payload(self):
        """O `installmentNumber` é o discriminador forte, mas não podemos depender de o Asaas
        sempre mandá-lo. Sem ele, o que separa "parcela do contrato em arquivo" de "primeira
        cobrança de um contrato novo" é o GRUPO gravado quando o assinante foi criado."""
        _, tok = self.paga(plano="anual", metodo="CARTAO", parcelas=12, grupo="g1")
        depois_da_1 = self.estado()["acesso_ate"]
        for _ in range(2, 6):
            self.paga(plano="anual", metodo="CARTAO", parcelas=12, grupo="g1",
                      tok=tok, valor=91.58)
        self.assertEqual(self.estado()["acesso_ate"], depois_da_1,
                         "sem installmentNumber, cada parcela comprou um período novo")

    def test_parcela_repetida_pelo_asaas(self):
        _, tok = self.paga(plano="anual", metodo="CARTAO", parcelas=12, grupo="g1",
                           n_parcela=1, pid="pp1")
        antes = self.estado()["acesso_ate"]
        self.paga(plano="anual", metodo="CARTAO", parcelas=12, grupo="g1", n_parcela=1,
                  pid="pp1", evento="PAYMENT_RECEIVED", tok=tok, valor=91.58)
        self.assertEqual(self.estado()["acesso_ate"], antes)


class TestClienteQueVolta(JornadaBase):
    """Venceu e voltou. É contrato novo: período novo, e o preço do plano que ele ESCOLHEU."""

    def _venceu(self, plano="anual", metodo="PIX", **kw):
        self.paga(plano=plano, metodo=metodo, **kw)
        self.passa_o_tempo(10)

    def test_volta_no_mesmo_plano_por_pix(self):
        self._venceu()
        self.paga(plano="anual", metodo="PIX")
        e = self.estado()
        self.assertTrue(e["tem_acesso"])
        self.assertFalse(e["cancelado"])
        self.assertEqual(e["renovacao_cobraria"], 1099.0)

    def test_volta_no_12x_recebe_o_ano(self):
        self._venceu()
        self.paga(plano="anual", metodo="CARTAO", parcelas=12, grupo="g2", n_parcela=1)
        e = self.estado()
        self.assertTrue(e["tem_acesso"], "voltou no 12x e ficou sem acesso")
        self.assertEqual(e["renovacao_cobraria"], 1099.0)

    def test_ex_mensal_que_compra_o_anual_recebe_o_anual(self):
        self._venceu(plano="mensal", metodo="CARTAO", sub_id="sub_m")
        self.paga(plano="anual", metodo="PIX")
        e = self.estado()
        self.assertEqual(e["plano"], "anual")
        self.assertEqual(e["renovacao_cobraria"], 1099.0)

    def test_ex_anual_que_compra_o_mensal_recebe_o_mensal(self):
        self._venceu(plano="anual", metodo="PIX")
        self.paga(plano="mensal", metodo="CARTAO", sub_id="sub_m")
        e = self.estado()
        self.assertEqual(e["plano"], "mensal")
        self.assertEqual(e["renovacao_cobraria"], 99.0)

    def test_checkout_abandonado_nao_muda_o_plano_do_que_ele_pagou(self):
        self._venceu(plano="anual", metodo="PIX")
        self.db.criar_pending({"nome": "Dr. A", "whatsapp": WPP, "email": EMAIL, "cpf": CPF,
                               "plano": "teste", "metodo": "PIX", "parcelas": 1,
                               "valor": 5.0, "valor_base": 5.0})
        self.paga(plano="anual", metodo="PIX", tok="", valor=1044.05)
        e = self.estado()
        self.assertEqual(e["plano"], "anual")
        self.assertNotEqual(e["renovacao_cobraria"], 5.0)


class TestCancelamento(JornadaBase):
    """Cancelar = cancelar a RENOVAÇÃO. O período pago continua valendo."""

    def _cancela(self):
        sub = self.s.por_cpf(CPF)
        self.db.claim_cancelamento(sub["id"], "achei caro", sub.get("acesso_ate"))
        return self.s.por_cpf(CPF)

    def test_parcela_apos_cancelar_nao_compra_periodo_novo(self):
        _, tok = self.paga(plano="anual", metodo="CARTAO", parcelas=12, grupo="g1", n_parcela=1)
        self._cancela()
        fim = self.estado()["acesso_ate"]
        self.paga(plano="anual", metodo="CARTAO", parcelas=12, grupo="g1", n_parcela=2,
                  tok=tok, valor=91.58)
        e = self.estado()
        self.assertEqual(e["acesso_ate"], fim)
        self.assertTrue(e["cancelado"], "a parcela apagou a marca do cancelamento")

    def test_quem_cancelou_e_paga_de_novo_volta_a_ter_acesso(self):
        """Cancelou por Pix (o acesso segue até o fim do período) e resolveu voltar ANTES de
        vencer. É o ramo de recompra: sem reativar de verdade, ele pagava e continuava
        marcado como cancelado — fora da régua e impedido de cancelar outra vez."""
        self.paga(plano="anual", metodo="PIX")
        self._cancela()
        self.assertTrue(self.estado()["tem_acesso"])     # pré-condição: ainda no período pago
        self.paga(plano="anual", metodo="PIX")
        e = self.estado()
        self.assertEqual(e["status"], "ATIVO")
        self.assertFalse(e["cancelado"], "pagou de novo e continuou marcado como cancelado")
        self.assertTrue(e["tem_acesso"])
        self.assertTrue(e["na_regua"], "ficou fora da régua para sempre")

    def test_quem_cancelou_no_cartao_e_recontrata_volta_a_ter_acesso(self):
        self.paga(plano="anual", metodo="CARTAO", sub_id="sub_1")
        self._cancela()
        self.paga(plano="anual", metodo="CARTAO", sub_id="sub_2")
        e = self.estado()
        self.assertEqual(e["status"], "ATIVO")
        self.assertFalse(e["cancelado"])
        self.assertTrue(e["tem_acesso"], "pagou de novo e continuou sem acesso")


class TestDinheiroDeVolta(JornadaBase):
    """Estorno e chargeback cortam o acesso — em TODOS os meios de pagamento."""

    def test_estorno_de_pix_corta(self):
        self.paga(plano="anual", metodo="PIX", pid="pg1")
        self.evento("PAYMENT_REFUNDED", "pg1")
        self.assertFalse(self.estado()["tem_acesso"])

    def test_estorno_de_cartao_a_vista_corta(self):
        self.paga(plano="anual", metodo="CARTAO", sub_id="sub_1", pid="pg1")
        self.evento("PAYMENT_REFUNDED", "pg1", sub_id="sub_1")
        self.assertFalse(self.estado()["tem_acesso"])

    def test_chargeback_de_parcelado_corta(self):
        self.paga(plano="anual", metodo="CARTAO", parcelas=12, grupo="g1", n_parcela=1, pid="pg1")
        self.evento("PAYMENT_CHARGEBACK_REQUESTED", "pg1")
        self.assertFalse(self.estado()["tem_acesso"])

    def test_apagar_cobranca_nao_paga_nao_corta(self):
        self.paga(plano="anual", metodo="PIX", pid="pg1")
        self.evento("PAYMENT_DELETED", "pg_abandonada")
        self.assertTrue(self.estado()["tem_acesso"], "cobrança não paga apagada cortou o acesso")

    def test_overdue_de_pix_nao_encurta_acesso_pago(self):
        self.paga(plano="anual", metodo="PIX", pid="pg1")
        self.evento("PAYMENT_OVERDUE", "pg_nova")
        self.assertTrue(self.estado()["tem_acesso"])


class TestReguaNaoChamaQuemNaoDeve(JornadaBase):
    """A régua existe para quem NÃO renova sozinho. Chamar os outros é cobrança em dobro."""

    def test_cartao_a_vista_fica_fora(self):
        self.paga(plano="anual", metodo="CARTAO", sub_id="sub_1")
        self.assertFalse(self.estado()["na_regua"])

    def test_pix_e_parcelado_ficam_dentro(self):
        self.paga(plano="anual", metodo="PIX")
        self.assertTrue(self.estado()["na_regua"])

    def test_quem_cancelou_fica_fora(self):
        self.paga(plano="anual", metodo="PIX")
        sub = self.s.por_cpf(CPF)
        self.db.claim_cancelamento(sub["id"], "x", sub.get("acesso_ate"))
        self.assertFalse(self.estado()["na_regua"])
