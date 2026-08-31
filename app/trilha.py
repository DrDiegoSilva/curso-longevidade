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
    ele já concluiu o produto atual (trilha incompleta não vira envio errado)."""
    produto = produto_do_assinante(sub_id)
    if produto is None:
        return None
    info = config.TRILHAS[produto]
    n = db.trilha_posicao(sub_id, produto)
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


def enviar_para(sub, enviar_fn=None, render_fn=None):
    """Envia a peça da vez a UM assinante. True se enviou.

    Ordem que importa: claim -> render -> envia -> avança. A posição só anda depois
    do envio dar certo; se falhar, o claim é liberado e ele recebe a MESMA peça no
    sábado seguinte. Nunca pula conteúdo."""
    import os
    import tempfile
    import deliver
    import phone

    sub_id = sub.get("id")
    peca = proxima_peca(sub_id)
    if peca is None:
        return False
    numero = peca["numero"]
    if not db.trilha_registrar_envio(sub_id, numero):
        # INVARIANTE que sustenta este "retomar" em vez de `return False`: `numero`
        # acabou de sair de `proxima_peca(sub_id)`, ou seja, É a posição ATUAL do
        # assinante. Se esta peça já tivesse sido enviada com sucesso, `trilha_avancar`
        # já teria movido a posição pra frente e `proxima_peca` teria devolvido outro
        # número -- não este. Logo, um claim que colide com a posição atual só pode
        # ser órfão: uma execução anterior morreu entre o INSERT do claim e o
        # envio/avanço (deploy, OOM, restart do container) e nunca chegou nos
        # try/except abaixo, que liberariam o claim via `_liberar_claim`. Sem retomar
        # aqui, o assinante trava NESSA peça pra sempre, em silêncio -- provado em
        # produção: 3 sábados seguidos com {'enviados': 0, 'falhas': 1}, posição
        # sempre 1, zero mensagens de verdade. O que evita reenvio duplicado DENTRO
        # do mesmo sábado não é este claim por peça -- é o claim por (sábado,
        # assinante) que `enviar_slot` faz ANTES de chamar esta função (chave
        # `trilha:{data}` em `registrar_envio_assinante`).
        print(f"[trilha] retomando claim órfão da peça {numero} p/ {sub_id} "
              f"(execução anterior não completou)", flush=True)

    enviar_fn = enviar_fn or deliver.enviar_pdf
    if render_fn is None:
        import pdf as _pdf
        render_fn = _pdf.gerar_pdf

    try:
        import pdf_trilha
        link = ""
        # só afirma o link se o ARQUIVO existir -- a peça pode declarar `ferramenta:`
        # no cabeçalho antes do arquivo ser subido em seed/trilha/ferramentas/, e um
        # link morto na peça 1 é o pior lugar pra isso acontecer (todo assinante
        # pagante recebe a peça 1 primeiro).
        if peca.get("ferramenta_slug") and caminho_ferramenta(peca["ferramenta_slug"]):
            # ARTIGOS_URL, não PUBLIC_URL: este app serve DOIS hosts. `curso.`
            # (PUBLIC_URL) é o ebook e faz fallback pra ele em rota desconhecida —
            # um link de ferramenta ali devolveria o ebook, com HTTP 200, sem erro
            # nenhum aparecendo. `/ferramentas/` só existe no portal do assinante.
            link = f"{config.ARTIGOS_URL}/ferramentas/{peca['ferramenta_slug']}"
        html_peca = pdf_trilha.montar_html(peca, sub.get("nome", ""),
                                           abertura=abertura(sub_id, numero), link_ferramenta=link)
        out = os.path.join(tempfile.gettempdir(), f"trilha-{numero}-{sub_id}.pdf")
        render_fn(html_peca, out)
        # nota: deliver.enviar_pdf(whatsapp, pdf_path, caption="") não tem parâmetro
        # `nome_arquivo` (o nome do arquivo no WhatsApp sai do próprio `caption`,
        # ver deliver._evolution_media_payload) — não passar aqui derrubaria todo
        # envio real com TypeError, capturado abaixo e mascarado como "zap caiu".
        enviar_fn(phone.normalizar(sub.get("whatsapp", "")), out,
                  caption=f"{config.TRILHA_NOME} · Semana {numero}: {peca.get('titulo','')}")
    except Exception as e:
        print(f"[trilha] peça {numero} p/ {sub_id} falhou: {e}", flush=True)
        _liberar_claim(sub_id, numero)
        return False

    try:
        db.trilha_avancar(sub_id, numero)
    except Exception as e:
        # a mensagem JÁ SAIU no WhatsApp aqui — não dá pra desfazer o envio. Se a
        # posição não avançar e o claim continuar de pé, o assinante trava nessa
        # peça pra sempre, em silêncio (proxima_peca some, mas trilha_registrar_envio
        # devolve False pro resto da vida). Preferimos o oposto: libera o claim e
        # ele recebe a MESMA peça de novo no sábado seguinte — duplicata é visível
        # e recuperável; travamento silencioso não é.
        print(f"[trilha] AVANÇO da peça {numero} p/ {sub_id} falhou (mensagem JÁ enviada!): {e}",
              flush=True)
        _liberar_claim(sub_id, numero)
        return False

    return True


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
    """Envia a peça da semana aos assinantes ativos de `slot`. Só roda no dia da
    trilha, e só com o interruptor `ativa()` ligado. Idempotente por (data, slot)
    usando `envios_slot` com chave namespaced — mesmo truque da varredura semanal,
    sem tabela nova.

    Dois claims empilhados, cada um matando um bug diferente:
    - por (data, slot), acima: o TICK inteiro não roda duas vezes (restart do cron).
    - por (data, assinante), no loop: o ASSINANTE não leva DUAS peças no mesmo
      sábado por causa de troca de horário no meio do dia — mesma defesa que
      `daily.enviar_slot` usa pro estudo diário (ver `db.registrar_envio_assinante`),
      aqui reaproveitada com chave namespaced (`trilha:{data}`) pra não brigar com
      o claim do estudo diário na mesma tabela `envios_dia`."""
    from datetime import datetime
    import time
    import subscribers

    d = quando or datetime.now()
    if not ativa():
        # ANTES de qualquer claim: desligar a trilha não pode queimar o envio do
        # sábado. Se o claim fosse consumido aqui, ligar o interruptor no mesmo dia
        # deixaria a base sem receber e ninguém entenderia por quê.
        return {"enviados": 0, "falhas": 0, "desligada": True}
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
        if not db.registrar_envio_assinante(f"trilha:{data}", s.get("id")):
            continue   # já recebeu a peça da semana hoje (troca de horário no mesmo sábado)
        # pacing: é o MESMO número de WhatsApp que sustenta o produto pago inteiro —
        # sem o delay, o 1º sábado dispara a base inteira de um slot em rajada. Não
        # dorme antes do 1º envio (sem atraso inútil no início do lote).
        if not primeiro:
            time.sleep(config.SEND_DELAY_SEC)
        primeiro = False
        try:
            ok = enviar_para(s, enviar_fn=enviar_fn, render_fn=render_fn)
        except Exception as e:
            # cinto e suspensório: enviar_para já cobre claim/render/envio/avanço
            # com try/except próprios, mas uma falha em UM assinante (ex.: erro no
            # próprio `proxima_peca`, antes do try interno) não pode abortar o
            # `for` e deixar o resto do slot sem receber nada.
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
    """Caminho absoluto do arquivo da ferramenta, ou None.

    O slug vem da URL, então é entrada não confiável: só minúscula/dígito/hífen
    passa, o que já elimina `..`, `/` e `\\`. A checagem de prefixo depois é cinto
    e suspensório — se o regex mudar um dia, o arquivo servido continua preso ao
    diretório de ferramentas."""
    if not slug or not _SLUG_OK.match(slug):
        return None
    base = os.path.realpath(os.path.join(config.TRILHA_DIR, "ferramentas"))
    for nome in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        raiz, _ext = os.path.splitext(nome)
        if raiz != slug:
            continue
        caminho = os.path.realpath(os.path.join(base, nome))
        if caminho.startswith(base + os.sep) and os.path.isfile(caminho):
            return caminho
    return None
