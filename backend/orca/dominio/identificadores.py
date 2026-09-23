"""CNPJ (numérico e alfanumérico, D-19) e código de barras GTIN/EAN.

Funções puras: validam o dígito verificador e devolvem a forma normalizada.
"""

import re

# --- CNPJ --------------------------------------------------------------------
# Desde julho/2026 as 12 primeiras posições podem ter letras (A–Z). No cálculo do
# dígito verificador, cada caractere vale (código ASCII − 48): '0'–'9' → 0–9,
# 'A' → 17, 'B' → 18… Os 2 dígitos verificadores continuam numéricos.

_CNPJ_NORMALIZADO = re.compile(r"^[0-9A-Z]{12}[0-9]{2}$")
_PESOS_DV1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_PESOS_DV2 = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)


def _dv_cnpj(base: str, pesos: tuple[int, ...]) -> int:
    resto = sum((ord(c) - 48) * p for c, p in zip(base, pesos)) % 11
    return 0 if resto < 2 else 11 - resto


def normalizar_cnpj(texto: str) -> str:
    """Valida o CNPJ e devolve os 14 caracteres sem pontuação, em maiúsculas.

    Aceita "12.ABC.345/01DE-35", "12abc34501de35", "43.283.811/0001-50" etc.
    """
    if not isinstance(texto, str):
        raise TypeError("O CNPJ deve ser texto")
    limpo = re.sub(r"[.\-/\s]", "", texto).upper()
    if not _CNPJ_NORMALIZADO.match(limpo):
        raise ValueError(f"CNPJ em formato inválido: {texto!r}")
    if len(set(limpo)) == 1:
        raise ValueError(f"CNPJ inválido: {texto!r}")
    dv1 = _dv_cnpj(limpo[:12], _PESOS_DV1)
    dv2 = _dv_cnpj(limpo[:12] + str(dv1), _PESOS_DV2)
    if limpo[12:] != f"{dv1}{dv2}":
        raise ValueError(f"CNPJ com dígito verificador errado: {texto!r}")
    return limpo


def formatar_cnpj(cnpj: str) -> str:
    """'12ABC34501DE35' → '12.ABC.345/01DE-35'."""
    c = normalizar_cnpj(cnpj)
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


def cnpj_raiz(cnpj: str) -> str:
    """Os 8 primeiros caracteres: iguais para matriz e filiais (P-03)."""
    return normalizar_cnpj(cnpj)[:8]


# --- Código de barras (GTIN-8, 12, 13 e 14; EAN-13 é o GTIN-13) ----------------

_GTIN = re.compile(r"^(\d{8}|\d{12}|\d{13}|\d{14})$")


def normalizar_gtin(texto: str) -> str:
    """Valida o código de barras e devolve só os dígitos."""
    if not isinstance(texto, str):
        raise TypeError("O código de barras deve ser texto")
    limpo = re.sub(r"[\s-]", "", texto)
    if not _GTIN.match(limpo):
        raise ValueError(f"Código de barras em formato inválido: {texto!r}")
    corpo, dv = limpo[:-1], int(limpo[-1])
    soma = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(corpo)))
    if (10 - soma % 10) % 10 != dv:
        raise ValueError(f"Código de barras com dígito verificador errado: {texto!r}")
    return limpo
