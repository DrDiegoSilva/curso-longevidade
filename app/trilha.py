"""Trilha semanal de empreendedorismo médico.

Uma peça por sábado, no horário (slot) que o assinante já escolheu pro estudo.
Drip por assinante: cada um percorre as 12 peças a partir da 1, independente de
quando assinou. Conteúdo é evergreen e mora em `seed/trilha/NN-slug.md`.

Isolado de propósito: NÃO importa nem altera `daily.py`. Se a trilha quebrar,
o estudo diário continua saindo.
"""
import os
import re

import config
import db

_SECOES = {"corpo": "corpo", "micro-resultado": "micro_resultado",
           "mentalidade": "mentalidade", "aviso": "aviso"}


def parse_peca(texto):
    """Converte o arquivo de uma peça em dict.

    Formato: linhas `chave: valor` até a primeira linha em branco, depois blocos
    `## secao`. Seção ausente vira string vazia — peça de mentalidade pura pode
    não ter ferramenta, e isso não é erro.
    """
    linhas = (texto or "").replace("\r\n", "\n").split("\n")
    cab, i = {}, 0
    while i < len(linhas) and linhas[i].strip():
        if ":" in linhas[i]:
            k, v = linhas[i].split(":", 1)
            cab[k.strip().lower()] = v.strip()
        i += 1
    secoes, atual = {}, None
    for linha in linhas[i:]:
        m = re.match(r"^##\s+(.+?)\s*$", linha)
        if m:
            atual = _SECOES.get(m.group(1).strip().lower())
            if atual:
                secoes[atual] = []
            continue
        if atual and atual in secoes:
            secoes[atual].append(linha)
    return {
        "titulo": cab.get("titulo", ""),
        "eixo": cab.get("eixo", ""),
        "ferramenta": cab.get("ferramenta", ""),
        "corpo": "\n".join(secoes.get("corpo", [])).strip(),
        "micro_resultado": "\n".join(secoes.get("micro_resultado", [])).strip(),
        "mentalidade": "\n".join(secoes.get("mentalidade", [])).strip(),
        "aviso": "\n".join(secoes.get("aviso", [])).strip(),
    }


def semear_produto(produto, diretorio=None):
    """Lê `seed/<produto>/NN-*.md` e grava no banco desse produto. Idempotente por
    (produto, numero): editar o texto e redeployar propaga a versão nova.
    Retorna quantas peças gravou."""
    d = diretorio if diretorio is not None else config.TRILHAS[produto]["dir"]
    if not os.path.isdir(d):
        return 0
    n = 0
    for nome in sorted(os.listdir(d)):
        m = re.match(r"^(\d{1,2})[-_]", nome)
        if not m or not nome.endswith(".md"):
            continue
        with open(os.path.join(d, nome), encoding="utf-8") as f:
            p = parse_peca(f.read())
        db.trilha_upsert_peca(produto, int(m.group(1)), p["eixo"], p["titulo"], p["corpo"],
                              p["micro_resultado"], p["mentalidade"], p["aviso"], p["ferramenta"])
        n += 1
    return n


def semear():
    """Semeia TODOS os produtos do catálogo. Produto sem diretório de conteúdo
    ainda (ex.: peptideos antes da redação das peças) conta 0, sem quebrar --
    mesma tolerância que `semear_produto` já tinha pra diretório ausente.

    Produtos com `exige_aviso=True` (a série de peptídeos) têm suas peças
    conferidas: cada uma sem o campo `aviso` preenchido vira uma linha no log de
    deploy -- sinal visível, não bloqueio duro (a peça de abertura pode
    legitimamente não precisar)."""
    contagens = {}
    for produto, info in config.TRILHAS.items():
        contagens[produto] = semear_produto(produto)
        if info.get("exige_aviso"):
            sem_aviso = [p["numero"] for p in db.trilha_listar_pecas(produto)
                        if not (p.get("aviso") or "").strip()]
            if sem_aviso:
                print(f"[trilha] {len(sem_aviso)} peça(s) de \"{produto}\" sem `aviso`: "
                      f"{sem_aviso}", flush=True)
    return contagens


_DIAS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]


def e_dia_da_trilha(quando=None):
    """True se `quando` cai no dia da trilha (config.TRILHA_DIA). Aceita date ou datetime."""
    from datetime import datetime
    d = quando or datetime.now()
    return _DIAS[d.weekday()] == config.TRILHA_DIA


def proxima_peca(sub_id):
    """A peça que este assinante deve receber agora (no produto que
    `produto_do_assinante` resolver). None se não há produto pra ele agora, ou se
    ele já concluiu o produto atual (trilha incompleta não vira envio errado).

    Leitura pura: usa `trilha_posicao_leitura` (não cria linha de progresso) --
    só visitar `/trilha` ou ativar um produto sem conteúdo ainda não pode
    matricular o assinante nele pra sempre. A matrícula de verdade só acontece
    em `db.trilha_registrar_envio`, no momento em que uma peça REAL está de
    fato saindo (ver `_enviar_uma_peca`)."""
    produto = produto_do_assinante(sub_id)
    if produto is None:
        return None
    info = config.TRILHAS[produto]
    n = db.trilha_posicao_leitura(sub_id, produto) or 1
    if n > info["total"]:
        return None
    p = db.trilha_peca(produto, n)
    if not p:
        return None
    p["numero"] = n
    return p


def abertura(sub_id, produto, numero):
    """Linha de retomada no topo da peça, olhando a peça anterior DO MESMO
    produto. Vazia na peça 1 (não há anterior)."""
    if numero <= 1:
        return ""
    if db.trilha_fez(sub_id, produto, numero - 1):
        return "Você marcou a tarefa da semana passada como feita. É assim que essa trilha funciona."
    return "A tarefa da semana passada continua em aberto — ela leva menos tempo do que parece."


def _liberar_claim(sub_id, produto, numero):
    """Desfaz o claim de `trilha_registrar_envio` quando o envio falhou."""
    with db._conn() as c:
        c.execute("DELETE FROM trilha_envios WHERE subscriber_id=? AND produto=? AND numero=? "
                  "AND feito_em IS NULL", (sub_id or "", produto, int(numero)))


def _enviar_uma_peca(sub, produto, enviar_fn=None, render_fn=None):
    """Um ciclo claim->render->envia->avança, pra UMA peça de UM produto.
    Extraído pra `enviar_para` poder rodar isto `pecas_por_envio` vezes seguidas
    na mesma visita, sem duplicar a lógica de claim/retomada/falha."""
    import os
    import tempfile
    import deliver
    import phone

    sub_id = sub.get("id")
    info = config.TRILHAS[produto]
    # Leitura pura -- não cria linha de progresso só de calcular qual peça
    # seria a vez. A matrícula de verdade acontece embaixo, em
    # `db.trilha_registrar_envio`, quando a peça JÁ foi confirmada existente
    # e está de fato prestes a ser enviada.
    n = db.trilha_posicao_leitura(sub_id, produto) or 1
    if n > info["total"]:
        return False
    peca = db.trilha_peca(produto, n)
    if not peca:
        return False
    peca["numero"] = n
    if not db.trilha_registrar_envio(sub_id, produto, n):
        # INVARIANTE que sustenta este "retomar" em vez de `return False`: `n`
        # acabou de sair de `db.trilha_posicao_leitura(sub_id, produto)` (ou 1),
        # ou seja, É a posição ATUAL do assinante NESSE produto. Um claim que
        # colide com a posição atual só pode ser órfão (execução anterior
        # morreu entre o INSERT do claim e o envio/avanço). Sem retomar aqui, o
        # assinante trava NESSA peça pra sempre, em silêncio.
        print(f"[trilha] retomando claim órfão da peça {n} ({produto}) p/ {sub_id} "
              f"(execução anterior não completou)", flush=True)

    enviar_fn = enviar_fn or deliver.enviar_pdf
    if render_fn is None:
        import pdf as _pdf
        render_fn = _pdf.gerar_pdf

    try:
        import pdf_trilha
        link = ""
        if peca.get("ferramenta_slug") and caminho_ferramenta(peca["ferramenta_slug"]):
            link = f"{config.ARTIGOS_URL}/ferramentas/{peca['ferramenta_slug']}"
        html_peca = pdf_trilha.montar_html(peca, sub.get("nome", ""),
                                           abertura=abertura(sub_id, produto, n), link_ferramenta=link)
        out = os.path.join(tempfile.gettempdir(), f"trilha-{produto}-{n}-{sub_id}.pdf")
        render_fn(html_peca, out)
        enviar_fn(phone.normalizar(sub.get("whatsapp", "")), out,
                  caption=f"{info['nome']} · Semana {n}: {peca.get('titulo','')}")
    except Exception as e:
        print(f"[trilha] peça {n} ({produto}) p/ {sub_id} falhou: {e}", flush=True)
        _liberar_claim(sub_id, produto, n)
        return False

    try:
        db.trilha_avancar(sub_id, produto, n)
    except Exception as e:
        print(f"[trilha] AVANÇO da peça {n} ({produto}) p/ {sub_id} falhou (mensagem JÁ enviada!): {e}",
              flush=True)
        _liberar_claim(sub_id, produto, n)
        return False

    return True


def enviar_para(sub, enviar_fn=None, render_fn=None):
    """Envia a(s) peça(s) da vez a UM assinante -- `pecas_por_envio` do produto em
    que ele está agora (1 pra empreendedorismo, 2 pra peptídeos). Se a trilha
    acabar no meio do lote, manda a que resta e para -- nunca emenda no próximo
    produto no mesmo sábado (isso só é decidido de novo no sábado seguinte, por
    `produto_do_assinante`). True se enviou AO MENOS uma peça."""
    import time

    sub_id = sub.get("id")
    produto = produto_do_assinante(sub_id)
    if produto is None:
        return False
    n_lote = config.TRILHAS[produto].get("pecas_por_envio", 1)
    enviou_alguma = False
    for i in range(n_lote):
        if i > 0:
            # mesmo número de WhatsApp que sustenta o produto pago inteiro -- não
            # dispara 2 mensagens grudadas pra mesma pessoa.
            time.sleep(config.SEND_DELAY_SEC)
        ok = _enviar_uma_peca(sub, produto, enviar_fn=enviar_fn, render_fn=render_fn)
        if not ok:
            return enviou_alguma
        enviou_alguma = True
        if db.trilha_posicao(sub_id, produto) > config.TRILHAS[produto]["total"]:
            break
    return enviou_alguma


def produto_ativo():
    """Qual trilha aceita gente NOVA agora. Vazio = nenhuma -- mesma postura de
    segurança de antes (`ativa()` nascia False): sem escolha explícita, ninguém
    novo entra. Quem já está em progresso em outro produto não é afetado por
    isto (ver `produto_do_assinante`)."""
    v = db.get_config("trilha_produto_ativo", "")
    return v if v in config.TRILHAS else ""


def definir_produto_ativo(produto):
    if produto and produto not in config.TRILHAS:
        raise ValueError(f"produto de trilha desconhecido: {produto}")
    db.set_config("trilha_produto_ativo", produto or "")


def produto_do_assinante(sub_id):
    """Qual produto de trilha este assinante recebe agora.

    1. Se ele tem progresso INCOMPLETO em algum produto do catálogo, é esse --
       não importa qual está ativo agora. É isso que garante "termina antes de
       trocar".
    2. Senão (nunca começou nada, ou concluiu tudo que já tinha começado), cai
       no produto ativo do momento.
    3. Sem produto ativo, `None` -- ninguém novo entra.

    Invariante que sustenta o passo 1: nunca há dois produtos incompletos ao
    mesmo tempo pro mesmo assinante, porque só se entra num produto novo quando
    não sobra nenhum em aberto (não existe caminho pra "meio de A e meio de B"
    simultaneamente)."""
    for produto, info in config.TRILHAS.items():
        pos = db.trilha_posicao_leitura(sub_id, produto)
        if pos is not None and pos <= info["total"]:
            return produto
    return produto_ativo() or None


def enviar_slot(slot, quando=None, enviar_fn=None, render_fn=None):
    """Envia a peça (ou peças, se `pecas_por_envio>1`) da semana aos assinantes
    ativos de `slot`. Só roda no dia da trilha. Quem não tem produto pra receber
    agora (`produto_do_assinante` devolve None) simplesmente não conta nem como
    enviado nem como falha -- não existe mais um "desligada" global: cada
    assinante é resolvido individualmente, então quem está no meio de uma trilha
    continua recebendo mesmo sem nenhum produto NOVO ativo.

    Dois claims empilhados, cada um matando um bug diferente:
    - por (data, slot): o TICK inteiro não roda duas vezes (restart do cron).
    - por (data, assinante): o ASSINANTE não leva DUAS peças no mesmo sábado por
      troca de horário no meio do dia -- reaproveitado com chave namespaced
      (`trilha:{data}`) pra não brigar com o claim do estudo diário."""
    from datetime import datetime
    import time
    import subscribers

    d = quando or datetime.now()
    if not e_dia_da_trilha(d):
        return {"enviados": 0, "falhas": 0}
    data = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)
    if not db.registrar_envio_slot(f"trilha:{data}", slot):   # slot já rodou hoje
        return {"enviados": 0, "falhas": 0}

    enviados = falhas = 0
    primeiro = True
    for s in subscribers.ativos():
        if subscribers.slot_de(s) != slot:
            continue
        try:
            tem_produto = produto_do_assinante(s.get("id")) is not None
        except Exception as e:
            print(f"[trilha] envio a {s.get('id')} explodiu fora do enviar_para: {e}", flush=True)
            falhas += 1
            continue
        if not tem_produto:
            # ninguém ativo e este assinante nunca começou nenhuma trilha --
            # não é falha, é "nada pra fazer aqui" (ver docstring). Continuar
            # ANTES do claim/pacing: não queima o claim do dia à toa nem
            # espera o delay de um envio que não vai acontecer.
            continue
        if not db.registrar_envio_assinante(f"trilha:{data}", s.get("id")):
            continue   # já recebeu a(s) peça(s) da semana hoje
        if not primeiro:
            time.sleep(config.SEND_DELAY_SEC)
        primeiro = False
        try:
            ok = enviar_para(s, enviar_fn=enviar_fn, render_fn=render_fn)
        except Exception as e:
            print(f"[trilha] envio a {s.get('id')} explodiu fora do enviar_para: {e}", flush=True)
            ok = False
        if ok:
            enviados += 1
        else:
            falhas += 1
    if enviados or falhas:
        try:
            import deliver
            deliver.enviar_curador(f"📘 Trilha (slot {slot}): {enviados} enviada(s)"
                                   + (f" · {falhas} sem envio" if falhas else ""))
        except Exception as e:
            print(f"[trilha] aviso ao curador falhou: {e}", flush=True)
    return {"enviados": enviados, "falhas": falhas}


_SLUG_OK = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")


def caminho_ferramenta(slug):
    """Caminho absoluto do arquivo da ferramenta, ou None. Busca em TODOS os
    diretórios do catálogo (a rota /ferramentas/<slug> não sabe de qual produto é
    o slug) -- primeiro achado vence, mesma tolerância de sempre.

    O slug vem da URL, então é entrada não confiável: só minúscula/dígito/hífen
    passa, o que já elimina `..`, `/` e `\\`. A checagem de prefixo depois é cinto
    e suspensório -- se o regex mudar um dia, o arquivo servido continua preso ao
    diretório de ferramentas daquele produto."""
    if not slug or not _SLUG_OK.match(slug):
        return None
    for info in config.TRILHAS.values():
        base = os.path.realpath(os.path.join(info["dir"], "ferramentas"))
        if not os.path.isdir(base):
            continue
        for nome in sorted(os.listdir(base)):
            raiz, _ext = os.path.splitext(nome)
            if raiz != slug:
                continue
            caminho = os.path.realpath(os.path.join(base, nome))
            if caminho.startswith(base + os.sep) and os.path.isfile(caminho):
                return caminho
    return None
