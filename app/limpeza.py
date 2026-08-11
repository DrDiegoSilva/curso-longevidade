"""Limpeza do estoque já gerado.

Consertar um prompt não conserta o texto que já foi gravado. Quando o `SYS_ESTUDO`
nomeava o leitor ("para o Dr. Diego"), o modelo passou a abrir uma seção com
"*Mensagem prática para Dr. Diego:*" — e isso está DENTRO do resumo salvo dos estudos
que ainda vão sair. Sem esta limpeza, o bug reaparece até o estoque girar.

Cirúrgico de propósito: tira o endereçamento e preserva a conduta clínica. NÃO regenera
com IA — o conteúdo já foi curado, regenerar custaria caro e mudaria texto aprovado.
"""
import re

# "para Dr. Diego:" / "para o Dr. Diego Silva:" / "para a Dra. Fulana:" no fim de um
# CABEÇALHO (antes dos dois-pontos). Prosa no meio do texto não casa: exige o ':' logo
# depois, que é o que caracteriza o rótulo de seção.
_ENDERECAMENTO = re.compile(
    r"\s+para\s+(?:o\s+|a\s+)?Dra?\.?\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ]*(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ]*)*\s*:",
    re.UNICODE)


def sem_endereçamento(texto):
    """Tira o "para Dr. Fulano" dos cabeçalhos, mantendo o resto do texto igual.

    A assinatura da marca ("Dr. Diego Silva · CRM-PR 54310") e o nome em prosa NÃO são
    tocados: só casa o padrão que termina em dois-pontos, que é rótulo de seção.
    """
    return _ENDERECAMENTO.sub(":", texto or "")


def limpar_estoque():
    """Tira o endereçamento dos TRÊS lugares onde o texto já gravado vive. Devolve
    `{reserva, rascunho, portal}` — o que mudou em cada um.

    A primeira versão só varria a reserva, e foi por isso que o nome saiu de novo em
    2026-08-11: o estudo daquele dia **já tinha saído da reserva** e virado o rascunho
    do dia quando o botão foi apertado. A limpeza nunca o viu.

    - `reserva`  → o que ainda vai ser preparado
    - `rascunho` → o estudo do dia, já fora da reserva (o buraco)
    - `portal`   → correção RETROATIVA das páginas publicadas. O PDF que já foi pro
      WhatsApp obviamente não muda; a página do arquivo, sim.

    Idempotente: pode apertar o botão quantas vezes quiser.
    """
    import db
    db.init()
    return {"reserva": _limpar_reserva(db),
            "rascunho": _limpar_rascunhos(db),
            "portal": _limpar_portal(db)}


def _limpar_reserva(db):
    n = 0
    for r in db.listar_reserva():
        atual = r.get("resumo") or ""
        novo = sem_endereçamento(atual)
        if novo != atual:
            db.atualizar_reserva(r["id"], resumo=novo)
            n += 1
    return n


def _limpar_rascunhos(db):
    """Regrava o payload inteiro preservando token e status — o link `/revisar` que o
    Diego tem no WhatsApp precisa continuar valendo."""
    n = 0
    for d in db.listar_drafts():
        atual = d.get("resumo") or ""
        novo = sem_endereçamento(atual)
        if novo != atual:
            d["resumo"] = novo
            db.salvar_draft(d.get("data", ""), d.get("review_token", ""),
                            d.get("status", "DRAFT"), d)
            n += 1
    return n


def _limpar_portal(db):
    n = 0
    for dg in db.listar_digests():
        atual = dg.get("resumo") or ""
        novo = sem_endereçamento(atual)
        if novo != atual:
            db.atualizar_digest_resumo(dg.get("data", ""), dg.get("tema_slug", ""), novo)
            n += 1
    return n
