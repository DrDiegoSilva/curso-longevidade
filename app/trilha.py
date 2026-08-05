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
           "mentalidade": "mentalidade"}


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
    }


def semear(diretorio=None):
    """Lê `seed/trilha/NN-*.md` e grava no banco. Idempotente por número: editar o
    texto e redeployar propaga a versão nova (o upsert atualiza a linha).
    Retorna quantas peças gravou."""
    d = diretorio or config.TRILHA_DIR
    if not os.path.isdir(d):
        return 0
    n = 0
    for nome in sorted(os.listdir(d)):
        m = re.match(r"^(\d{1,2})[-_]", nome)
        if not m or not nome.endswith(".md"):
            continue
        with open(os.path.join(d, nome), encoding="utf-8") as f:
            p = parse_peca(f.read())
        db.trilha_upsert_peca(int(m.group(1)), p["eixo"], p["titulo"], p["corpo"],
                              p["micro_resultado"], p["mentalidade"], p["ferramenta"])
        n += 1
    return n


_DIAS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]


def e_dia_da_trilha(quando=None):
    """True se `quando` cai no dia da trilha (config.TRILHA_DIA). Aceita date ou datetime."""
    from datetime import datetime
    d = quando or datetime.now()
    return _DIAS[d.weekday()] == config.TRILHA_DIA


def proxima_peca(sub_id):
    """A peça que este assinante deve receber agora. None se já concluiu a trilha
    (ou se a peça não existe no banco — trilha incompleta não vira envio errado)."""
    n = db.trilha_posicao(sub_id)
    if n > config.TRILHA_TOTAL:
        return None
    p = db.trilha_peca(n)
    if not p:
        return None
    p["numero"] = n
    return p


def abertura(sub_id, numero):
    """Linha de retomada no topo da peça, olhando a peça anterior.

    É a cobrança da trilha: sem grupo, sem live, sem canal de entrada no WhatsApp —
    a peça seguinte é que reconhece ou retoma. Vazia na peça 1 (não há anterior)."""
    if numero <= 1:
        return ""
    if db.trilha_fez(sub_id, numero - 1):
        return "Você marcou a tarefa da semana passada como feita. É assim que essa trilha funciona."
    return "A tarefa da semana passada continua em aberto — ela leva menos tempo do que parece."


def _liberar_claim(sub_id, numero):
    """Desfaz o claim de `trilha_registrar_envio` quando o envio falhou. Sem isso o
    assinante ficaria travado: a posição não avançou (certo) mas o claim impediria
    a retentativa no sábado seguinte (errado) — ele nunca mais receberia a peça."""
    with db._conn() as c:
        c.execute("DELETE FROM trilha_envios WHERE subscriber_id=? AND numero=? "
                  "AND feito_em IS NULL", (sub_id or "", int(numero)))


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
    if not db.trilha_registrar_envio(sub_id, numero):    # já reivindicada
        return False

    enviar_fn = enviar_fn or deliver.enviar_pdf
    if render_fn is None:
        import pdf as _pdf
        render_fn = _pdf.gerar_pdf

    try:
        import pdf_trilha
        link = ""
        if peca.get("ferramenta_slug"):
            link = f"{config.PUBLIC_URL}/ferramentas/{peca['ferramenta_slug']}"
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

    db.trilha_avancar(sub_id, numero)
    return True


def enviar_slot(slot, quando=None, enviar_fn=None, render_fn=None):
    """Envia a peça da semana aos assinantes ativos de `slot`. Só roda no dia da
    trilha. Idempotente por (data, slot) usando `envios_slot` com chave namespaced —
    mesmo truque da varredura semanal, sem tabela nova."""
    from datetime import datetime
    import subscribers

    d = quando or datetime.now()
    if not e_dia_da_trilha(d):
        return {"enviados": 0, "falhas": 0}
    data = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)
    if not db.registrar_envio_slot(f"trilha:{data}", slot):   # slot já rodou hoje
        return {"enviados": 0, "falhas": 0}

    enviados = falhas = 0
    for s in subscribers.ativos():
        if subscribers.slot_de(s) != slot:
            continue
        if enviar_para(s, enviar_fn=enviar_fn, render_fn=render_fn):
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
