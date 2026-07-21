"""Validação de CPF — formato (11 dígitos) + dígitos verificadores. Puro/testável."""
import re


def so_digitos(cpf):
    return re.sub(r"\D", "", cpf or "")


def valida(cpf):
    """True se o CPF é válido: 11 dígitos, não todos iguais, e os 2 dígitos
    verificadores conferem pelo algoritmo oficial."""
    n = so_digitos(cpf)
    if len(n) != 11 or n == n[0] * 11:
        return False
    for i in (9, 10):                       # calcula o 1º e o 2º dígito verificador
        soma = sum(int(n[j]) * ((i + 1) - j) for j in range(i))
        dv = (soma * 10) % 11
        dv = 0 if dv == 10 else dv
        if dv != int(n[i]):
            return False
    return True


def formata(cpf):
    """000.000.000-00 (ou o valor original se não tiver 11 dígitos)."""
    n = so_digitos(cpf)
    return f"{n[:3]}.{n[3:6]}.{n[6:9]}-{n[9:]}" if len(n) == 11 else (cpf or "")
