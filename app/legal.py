"""Conteúdo dos Termos de Assinatura e da Política de Privacidade.

Só CONTEÚDO — o layout fica no site_web. Cada documento é uma lista de
(título da cláusula, HTML do corpo), pra facilitar renderizar numerado e testar cláusula
a cláusula. Opcionalmente um 3º elemento `True` marca a cláusula como RESTRITIVA (dá
destaque visual obrigatório no render — art. 54 §4 do CDC — sem casar por índice nem
por texto do título: quem decide é o próprio dado, aqui).

VERSAO é a chave do aceite: mudou o texto de forma relevante, sobe a VERSAO e todo mundo
re-aceita no próximo login. Nunca reaproveitar uma versão antiga com texto novo.
"""

VERSAO = "2026-07-24"

CONTROLADOR = {
    "razao_social": "Clínica Diego Silva LTDA",
    "cnpj": "52.891.914/0001-93",
    "endereco": "Av. Adhemar Pereira de Barros, 1500, sala 203 — Londrina/PR, CEP 86047-250",
    "email": "contato@drdiegosilva.com.br",
}

_ASSINATURA = "Atualização Científica"

TERMOS = [
    ("Quem somos e o que é o serviço",
     f"<p>O {_ASSINATURA} é um serviço de assinatura operado por "
     f"<strong>{CONTROLADOR['razao_social']}</strong>, CNPJ {CONTROLADOR['cnpj']}, "
     f"com sede em {CONTROLADOR['endereco']}.</p>"
     f"<p>O serviço consiste no envio de resumos de estudos científicos por WhatsApp em dias "
     f"úteis, com acesso ao portal do assinante e ao arquivo das edições. O conteúdo tem "
     f"finalidade informativa e de educação continuada, <strong>não constitui prescrição, "
     f"diagnóstico ou conduta médica</strong>, e não substitui o julgamento clínico do "
     f"assinante.</p>"),

    ("Preço, cobrança e renovação",
     "<p>O preço vigente é o exibido na página de contratação no momento da compra. A cobrança "
     "é processada pelo Asaas (Asaas Gestão Financeira S.A.), que é quem trata os dados de "
     "pagamento.</p>"
     "<p><strong>A renovação depende da forma de pagamento escolhida:</strong></p>"
     "<ul>"
     "<li><strong>Cartão de crédito à vista:</strong> a assinatura é recorrente e <strong>renova "
     "automaticamente</strong> ao fim de cada ciclo, <strong>pelo mesmo valor contratado</strong>, "
     "até que o assinante cancele a renovação.</li>"
     "<li><strong>Cartão de crédito parcelado:</strong> <strong>não há renovação automática</strong>. "
     "As parcelas correspondem ao período contratado e, ao fim dele, o acesso se encerra, salvo "
     "nova contratação.</li>"
     "<li><strong>Pix:</strong> o pagamento é avulso e <strong>não renova automaticamente</strong>. "
     "Ao fim do período contratado o acesso se encerra, salvo nova contratação.</li>"
     "</ul>"
     # B13 da revisão final #2: dizia "por e-mail", que só acontece para cartão à vista
     # (billing_notices exige asaas_subscription_id) — justamente o método em que nada
     # expira. Quem tem prazo para perder (Pix e parcelado) é avisado pela régua, cujas
     # automações são de WhatsApp. A cláusula agora diz o que o sistema de fato faz.
     "<p>Avisamos antes do fim do período contratado, por e-mail e/ou WhatsApp, nos contatos "
     "informados no cadastro.</p>"),

    ("Cancelamento da renovação",
     "<p>O assinante pode cancelar a renovação a qualquer momento, sem multa, pela área de conta "
     "(<em>Minha conta → Cancelar assinatura</em>). O cancelamento <strong>encerra a renovação "
     "automática</strong>: não haverá cobrança de um novo período, e <strong>a assinatura "
     "permanece ativa até o término do período já contratado</strong> — mensal ou anual, conforme "
     "o plano.</p>"
     "<p>No plano Anual pago de forma parcelada, as parcelas restantes seguem sendo cobradas "
     "normalmente, por corresponderem aos 12 meses já contratados.</p>"),

    ("Reembolso",
     "<p><strong>4.1 — Direito de arrependimento (7 dias).</strong> Por se tratar de contratação "
     "à distância, o assinante pode desistir em até <strong>7 (sete) dias</strong> contados da "
     "confirmação do pagamento, com <strong>devolução integral</strong> do valor pago, nos termos "
     "do art. 49 do Código de Defesa do Consumidor. Basta cancelar pela área de conta dentro do "
     "prazo: o estorno é solicitado automaticamente e aparece em até 10 dias úteis, conforme o "
     "meio de pagamento.</p>"
     "<p><strong>4.2 — Após o prazo de arrependimento.</strong> O cancelamento da renovação "
     "após o prazo de arrependimento <strong>NÃO gera reembolso</strong> dos valores já pagos. "
     "O acesso permanece ativo até o término do período contratado.</p>", True),

    ("Uso do conteúdo",
     "<p>O conteúdo é licenciado para uso pessoal e intransferível do assinante. É vedada a "
     "redistribuição, revenda, publicação ou compartilhamento do material com terceiros, "
     "inclusive o repasse do acesso.</p>"
     "<p>O acesso é individual e vinculado ao número de WhatsApp cadastrado. Indícios de "
     "compartilhamento podem levar à suspensão do acesso.</p>"),

    ("Disponibilidade",
     "<p>Envios ocorrem em dias úteis. Eventuais interrupções por manutenção, falha de "
     "terceiros (WhatsApp, provedores de e-mail, processador de pagamento) ou caso fortuito não "
     "caracterizam descumprimento, e o período afetado é compensado na vigência da assinatura "
     "sempre que aplicável.</p>"),

    ("Dados pessoais",
     "<p>O tratamento de dados pessoais está descrito na "
     "<a href=\"/privacidade\">Política de Privacidade</a>, que integra estes Termos.</p>"),

    ("Alterações destes Termos",
     "<p>Estes Termos podem ser alterados. Alterações relevantes são comunicadas e passam a "
     "exigir novo aceite no acesso à área de conta. O assinante que não concordar pode cancelar "
     "nos termos da cláusula 3.</p>"),

    ("Foro",
     "<p>Fica eleito o foro da Comarca de Londrina/PR para dirimir controvérsias, "
     "<strong>ressalvado ao CONSUMIDOR o direito de ajuizar ação no foro de seu domicílio</strong>, "
     "nos termos do art. 101, I, do Código de Defesa do Consumidor.</p>"),
]

PRIVACIDADE = [
    ("Controlador",
     f"<p>O controlador dos dados é <strong>{CONTROLADOR['razao_social']}</strong>, "
     f"CNPJ {CONTROLADOR['cnpj']}, {CONTROLADOR['endereco']}.</p>"
     f"<p>Canal do titular e do encarregado: "
     f"<a href=\"mailto:{CONTROLADOR['email']}\">{CONTROLADOR['email']}</a>.</p>"),

    ("Dados que coletamos",
     "<ul>"
     "<li><strong>Cadastro:</strong> nome, e-mail, CPF e número de WhatsApp.</li>"
     "<li><strong>Pagamento:</strong> processado pelo Asaas. Dados de cartão são coletados e "
     "armazenados pelo Asaas — <strong>não temos acesso a eles</strong>. Recebemos apenas "
     "identificadores da cobrança, valor e status.</li>"
     "<li><strong>Uso:</strong> registros de acesso, preferências de horário de envio e histórico "
     "de envios.</li>"
     "</ul>"),

    ("Finalidade e base legal",
     "<ul>"
     "<li><strong>Executar o contrato</strong> (art. 7º, V da LGPD): entregar os resumos, dar "
     "acesso ao portal, processar cobranças e enviar avisos de renovação e cancelamento.</li>"
     "<li><strong>Cumprir obrigação legal</strong> (art. 7º, II): emissão fiscal e guarda de "
     "registros.</li>"
     "<li><strong>Legítimo interesse</strong> (art. 7º, IX): prevenção a fraude e a "
     "compartilhamento indevido de acesso.</li>"
     "</ul>"
     "<p>O CPF é coletado por exigência do processador de pagamento para emissão da cobrança.</p>"),

    ("Com quem compartilhamos",
     "<p>Compartilhamos o mínimo necessário com operadores que viabilizam o serviço:</p>"
     "<ul>"
     "<li><strong>Asaas</strong> — processamento de pagamentos e emissão de cobranças.</li>"
     "<li><strong>Provedor de mensagens WhatsApp</strong> — entrega dos resumos.</li>"
     "<li><strong>Provedor de e-mail</strong> — avisos transacionais.</li>"
     "<li><strong>Infraestrutura de hospedagem e banco de dados.</strong></li>"
     "</ul>"
     "<p>Não vendemos dados pessoais e não os cedemos para publicidade de terceiros.</p>"),

    ("Por quanto tempo guardamos",
     "<p>Dados de cadastro e de assinatura são mantidos enquanto durar a relação e, após o "
     "encerramento, pelo prazo necessário ao cumprimento de obrigações legais e à defesa em "
     "eventual processo. Depois disso são eliminados ou anonimizados.</p>"),

    ("Direitos do titular",
     "<p>O titular pode solicitar confirmação de tratamento, acesso, correção, anonimização, "
     "portabilidade, informação sobre compartilhamento e eliminação de dados tratados com base "
     "no consentimento, nos termos do art. 18 da LGPD.</p>"
     f"<p>Os pedidos devem ser feitos por "
     f"<a href=\"mailto:{CONTROLADOR['email']}\">{CONTROLADOR['email']}</a> e são respondidos "
     f"nos prazos legais. Parte dos dados pode ser mantida quando houver obrigação legal ou "
     f"necessidade de defesa em processo.</p>"),

    ("Segurança",
     "<p>Adotamos medidas técnicas e administrativas para proteger os dados, incluindo controle "
     "de acesso, autenticação do assinante por código enviado ao WhatsApp cadastrado, e tráfego "
     "criptografado. Nenhum sistema é infalível — incidentes relevantes são comunicados aos "
     "titulares e à ANPD conforme a LGPD.</p>"),

    ("Cookies",
     "<p>Usamos apenas cookie de sessão para manter o assinante autenticado. Não usamos cookies "
     "de publicidade nem rastreamento de terceiros.</p>"),

    ("Alterações desta Política",
     "<p>Esta Política pode ser atualizada. Alterações relevantes são comunicadas e passam a "
     "exigir novo aceite no acesso à área de conta.</p>"),
]
