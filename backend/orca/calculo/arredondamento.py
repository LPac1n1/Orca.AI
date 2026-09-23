"""Arredondamento comercial (D-21).

Pela terceira casa decimal do valor em reais: 5 ou mais sobe, menos de 5 desce
(R$ 15,556 → R$ 15,56; R$ 15,554 → R$ 15,55; R$ 2.079,795 → R$ 2.079,80).

Como o sistema trabalha em centavos, isso equivale a levar um valor exato em
centavos ao centavo inteiro mais próximo, com o meio centavo indo para longe do
zero — o mesmo comportamento da função ARRED do Excel.
"""

from fractions import Fraction
from math import floor

_MEIO = Fraction(1, 2)


def arredondar_centavos(valor: int | Fraction) -> int:
    """Arredonda um valor exato, em centavos, para centavos inteiros."""
    if isinstance(valor, bool) or not isinstance(valor, (int, Fraction)):
        raise TypeError(
            f"Use int ou Fraction (nunca float): recebido {type(valor).__name__}"
        )
    if valor >= 0:
        return floor(valor + _MEIO)
    return -floor(-valor + _MEIO)
