from decimal import Decimal
from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

from orca.calculo import centavos_de_decimal, centavos_de_texto, formatar, formatar_exato


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("R$ 1.234,56", 123456),
        ("R$1.234,56", 123456),
        ("1234,56", 123456),
        ("34,5", 3450),
        ("12", 1200),
        ("1.234", 123400),  # formato brasileiro: ponto é separador de milhar
        ("R$ 150.000,00", 15000000),
        ("  R$ 0,99 ", 99),
        ("R$ -3,07", -307),
    ],
)
def test_centavos_de_texto(texto, esperado):
    assert centavos_de_texto(texto) == esperado


@pytest.mark.parametrize("texto", ["34.50", "1,234", "R$ 1,2,3", "abc", "", "12,345"])
def test_centavos_de_texto_recusa_formatos_invalidos(texto):
    with pytest.raises(ValueError):
        centavos_de_texto(texto)


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [("25.29", 2529), ("25.9", 2590), ("26", 2600), (Decimal("34.99"), 3499), ("25.290", 2529), (17, 1700)],
)
def test_centavos_de_decimal(valor, esperado):
    assert centavos_de_decimal(valor) == esperado


def test_centavos_de_decimal_recusa_float_e_mais_de_duas_casas():
    with pytest.raises(TypeError):
        centavos_de_decimal(25.29)
    with pytest.raises(ValueError):
        centavos_de_decimal("25.295")
    with pytest.raises(ValueError):
        centavos_de_decimal("NaN")


@pytest.mark.parametrize(
    ("centavos", "esperado"),
    [(123456, "R$ 1.234,56"), (5, "R$ 0,05"), (15000000, "R$ 150.000,00"), (-307, "-R$ 3,07")],
)
def test_formatar(centavos, esperado):
    assert formatar(centavos) == esperado


@given(st.integers(min_value=-10**12, max_value=10**12))
def test_ida_e_volta(centavos):
    texto = formatar(centavos, simbolo=False)
    assert centavos_de_texto(texto) == centavos


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (Fraction(1500200, 3), "R$ 5.000,6666…"),
        (Fraction(2079795, 10), "R$ 2.079,795"),
        (1500, "R$ 15,00"),
        (1505, "R$ 15,05"),
        (Fraction(2345, 3), "R$ 7,8166…"),
    ],
)
def test_formatar_exato(valor, esperado):
    assert formatar_exato(valor) == esperado
