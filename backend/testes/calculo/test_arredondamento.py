"""T-01 — Arredondamento comercial (D-21)."""

from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

from orca.calculo import arredondar_centavos


@pytest.mark.parametrize(
    ("centavos_exatos", "esperado"),
    [
        (Fraction(15556, 10), 1556),  # R$ 15,556 → R$ 15,56
        (Fraction(15554, 10), 1555),  # R$ 15,554 → R$ 15,55
        (Fraction(15555, 10), 1556),  # R$ 15,555 → R$ 15,56 (5 sobe)
        (Fraction(207979_5, 10), 207980),  # R$ 2.079,795 → R$ 2.079,80
        (Fraction(2345, 3), 782),  # média 7,8166… → 7,82
        (Fraction(1500200, 3), 500067),  # média 5.000,6666… → 5.000,67
        (Fraction(2758, 3), 919),  # média 9,1933… → 9,19
        (1234, 1234),  # já inteiro
        (0, 0),
    ],
)
def test_exemplos(centavos_exatos, esperado):
    assert arredondar_centavos(centavos_exatos) == esperado


def test_negativo_simetrico():
    assert arredondar_centavos(Fraction(-15555, 10)) == -1556
    assert arredondar_centavos(Fraction(-15554, 10)) == -1555


@pytest.mark.parametrize("invalido", [1.5, "1,5", None, True])
def test_recusa_float_e_outros_tipos(invalido):
    with pytest.raises(TypeError):
        arredondar_centavos(invalido)


fracoes = st.fractions(min_value=-10**9, max_value=10**9, max_denominator=10**6)


@given(st.integers(min_value=-10**12, max_value=10**12))
def test_inteiro_nao_muda(n):
    assert arredondar_centavos(n) == n


@given(fracoes)
def test_erro_no_maximo_meio_centavo(x):
    assert abs(arredondar_centavos(x) - x) <= Fraction(1, 2)


@given(fracoes, fracoes)
def test_monotonico(x, y):
    if x <= y:
        assert arredondar_centavos(x) <= arredondar_centavos(y)


@given(fracoes)
def test_simetrico(x):
    assert arredondar_centavos(-x) == -arredondar_centavos(x)


@given(st.lists(st.integers(min_value=1, max_value=10**9), min_size=3, max_size=3))
def test_media_de_tres_nunca_empata(precos):
    """A média de 3 valores em centavos termina em 0, 1/3 ou 2/3: nunca exatamente meio (docs/03 §1)."""
    media = Fraction(sum(precos), 3)
    assert media - (media.numerator // media.denominator) != Fraction(1, 2)
