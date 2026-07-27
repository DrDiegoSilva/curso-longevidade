"""B4 da revisão final #2: /renovar não pode montar checkout para quem já renova sozinho.

`asaas.montar_checkout` monta TODO checkout de cartão como `chargeTypes: ["RECURRENT"]`.
Quem já tem `asaas_subscription_id` (cartão à vista) já é cobrado automaticamente pelo
Asaas — passar por /renovar criava uma SEGUNDA assinatura recorrente, cobrando duas vezes
para sempre.

É o mesmo estrago que o c6b7466 foi escrito para evitar do lado do webhook (gravar o
subscription_id justamente para a régua NÃO chamar esse assinante para renovar). A rota,
porém, ficou aberta: basta o assinante ter o link, um aviso antigo no WhatsApp ou digitar
/renovar.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class _RotaStub:
    """Stub mínimo pro `self` das rotas — mesmo padrão do _RenovarStub."""

    def __init__(self, sub):
        self._sub = sub
        self.htmls = []

    def _sub_logado(self):
        return self._sub

    def _html(self, s, code=200):
        self.htmls.append((s, code))
        return s

    def _redirect(self, location, token=None, clear=False):
        return f"<redirect {location}>"


class TestRenovarComAssinaturaRecorrente(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # Guarda o ambiente ANTERIOR e restaura no tearDown: dar `pop` cegamente
        # apagava variáveis que outros módulos de teste (ordem alfabética) esperam
        # encontrar — foi assim que o test_preparar_pdf passou a cair em '/data'.
        self._env0 = {k: os.environ.get(k) for k in
                      ("DSCURSO_DATA", "DSCURSO_ARTIGOS_DB", "ASAAS_WEBHOOK_TOKEN")}
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(self.tmp, "artigos.db")
        for m in ("config", "db", "subscribers", "serve", "site_web"):
            sys.modules.pop(m, None)
        import db, config, subscribers, serve, asaas
        db._INITED = False
        db.init()
        self.db, self.config, self.s, self.serve, self.asaas = db, config, subscribers, serve, asaas
        self.s._migrado = False
        self.checkouts = []
        self._orig = asaas.criar_checkout
        asaas.criar_checkout = lambda payload: (self.checkouts.append(payload)
                                                or {"url": "https://checkout.example/x"})

    def tearDown(self):
        self.asaas.criar_checkout = self._orig
        for _k, _v in self._env0.items():
            if _v is None:
                os.environ.pop(_k, None)
            else:
                os.environ[_k] = _v

    def _sub(self, sid=None):
        return {"id": "s1", "nome": "Dr. A", "email": "a@x.com", "cpf": "11144477735",
                "whatsapp": "5543999990000", "plano": "anual", "status": "ATIVO",
                "valor_contratado": 1099.0, "proximo_vencimento": "2027-08-01",
                "acesso_ate": "2027-08-01", "asaas_subscription_id": sid}

    def _g(self, **over):
        base = {"metodo": "CARTAO"}
        base.update(over)
        return lambda k: base.get(k, "")

    def test_post_renovar_recusa_quem_ja_tem_assinatura_recorrente(self):
        stub = _RotaStub(self._sub(sid="sub_asaas_1"))
        out = self.serve.Handler._post_renovar(stub, self._g())
        self.assertEqual(self.checkouts, [])            # nenhum checkout criado no Asaas
        self.assertIn("já renova automaticamente", str(out))

    def test_post_renovar_segue_normal_para_pix(self):
        """A guarda é só para quem JÁ renova sozinho — Pix e parcelado precisam da rota."""
        stub = _RotaStub(self._sub(sid=None))
        out = self.serve.Handler._post_renovar(stub, self._g())
        self.assertEqual(len(self.checkouts), 1)
        self.assertEqual(out, "<redirect https://checkout.example/x>")

    def test_get_renovar_explica_em_vez_de_oferecer_o_botao(self):
        stub = _RotaStub(self._sub(sid="sub_asaas_1"))
        out = self.serve.Handler._get_rota_renovar(stub)
        # não pode oferecer o formulário de pagamento a quem já é cobrado sozinho
        self.assertNotIn('action="/renovar"', str(out))

    def test_get_renovar_mostra_o_form_para_pix(self):
        stub = _RotaStub(self._sub(sid=None))
        out = self.serve.Handler._get_rota_renovar(stub)
        self.assertIn('action="/renovar"', str(out))
