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
    """Reescreve os resumos da reserva que tenham endereçamento. Devolve quantos mudaram.

    Idempotente — pode apertar o botão duas vezes sem efeito colateral.
    """
    import db
    db.init()
    n = 0
    for r in db.listar_reserva():
        atual = r.get("resumo") or ""
        novo = sem_endereçamento(atual)
        if novo != atual:
            db.atualizar_reserva(r["id"], resumo=novo)
            n += 1
    return n
