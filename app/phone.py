"""Normalização de número de WhatsApp p/ o padrão do Brasil (55 + DDD + número).
O Evolution/WhatsApp exige o código do país. Números com 10-11 dígitos (DDD+número,
sem país) ganham o 55; quem já tem país (12-13 dígitos) fica igual.
"""


def normalizar(w):
    d = "".join(c for c in (w or "") if c.isdigit())
    if len(d) in (10, 11):     # DDD + número, sem código do país
        d = "55" + d
    return d
