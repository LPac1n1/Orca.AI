"""Valores em dinheiro: sempre centavos inteiros, nunca float.

Valores exatos intermediários (ex.: médias) são `Fraction` de centavos.
"""

import re
from decimal import Decimal, InvalidOperation
from fractions import Fraction

# Formato brasileiro: "R$ 1.234,56", "1234,56", "34,5", "12". Recusa "34.50".
_TEXTO_BRL = re.compile(
    r"^\s*(?:R\$\s*)?(-)?(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?\s*$"
)


def centavos_de_texto(texto: str) -> int:
    """Lê um valor escrito no formato brasileiro (como aparece nas páginas)."""
    m = _TEXTO_BRL.match(texto)
    if not m:
        raise ValueError(f"Valor em formato inválido: {texto!r}")
    sinal, inteiro, fracao = m.groups()
    centavos = int(inteiro.replace(".", "")) * 100 + int((fracao or "0").ljust(2, "0"))
    return -centavos if sinal else centavos


def centavos_de_decimal(valor: str | Decimal | int) -> int:
    """Lê um valor com ponto decimal, como nos dados estruturados ("25.29").

    Aceita no máximo 2 casas. Recusa float: ao ler JSON, use
    `json.loads(..., parse_float=Decimal)`.
    """
    if isinstance(valor, bool) or isinstance(valor, float):
        raise TypeError("Use str, Decimal ou int (nunca float)")
    try:
        d = valor if isinstance(valor, Decimal) else Decimal(str(valor).strip())
    except InvalidOperation as e:
        raise ValueError(f"Valor inválido: {valor!r}") from e
    if not d.is_finite():
        raise ValueError(f"Valor inválido: {valor!r}")
    em_centavos = d * 100
    if em_centavos != em_centavos.to_integral_value():
        raise ValueError(f"Mais de 2 casas decimais: {valor!r}")
    return int(em_centavos)


def formatar(centavos: int, simbolo: bool = True) -> str:
    """Formata centavos como 'R$ 1.234,56'."""
    if isinstance(centavos, bool) or not isinstance(centavos, int):
        raise TypeError("Use centavos inteiros")
    sinal = "-" if centavos < 0 else ""
    reais, cent = divmod(abs(centavos), 100)
    texto = f"{reais:,}".replace(",", ".") + f",{cent:02d}"
    return f"{sinal}R$ {texto}" if simbolo else f"{sinal}{texto}"


def formatar_exato(centavos: int | Fraction, casas_max: int = 4) -> str:
    """Formata um valor exato para a memória de cálculo, sem arredondar.

    Mostra até `casas_max` casas decimais (mínimo 2). Se o valor não couber
    nelas, corta e termina com "…": R$ 5.000,6666… ; R$ 2.079,795.
    """
    valor = Fraction(centavos)
    sinal = "-" if valor < 0 else ""
    valor = abs(valor)
    extras = casas_max - 2
    escalado = valor * 10**extras
    inteiro_escalado = escalado.numerator // escalado.denominator
    exato = escalado.denominator == 1
    reais, resto = divmod(inteiro_escalado, 100 * 10**extras)
    decimais = f"{resto:0{casas_max}d}"
    if exato:
        decimais = decimais.rstrip("0").ljust(2, "0")
    texto = f"{reais:,}".replace(",", ".") + "," + decimais + ("" if exato else "…")
    return f"{sinal}R$ {texto}"
