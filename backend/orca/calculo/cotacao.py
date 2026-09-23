"""Cotação de um item: preços nas fontes, médias e conferência (docs/03 §2)."""

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction

from orca.calculo.arredondamento import arredondar_centavos


class ComparacaoMedia(StrEnum):
    """Com qual média o preço da loja escolhida é comparado na Regra B."""

    EXATA = "media_exata"  # P-02 (padrão): mais rigorosa
    EXIBIDA = "media_exibida"  # a média arredondada que aparece na grade


def _validar_inteiro(valor: int, nome: str, minimo: int) -> None:
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise TypeError(f"{nome} deve ser int (centavos ou unidades), não {type(valor).__name__}")
    if valor < minimo:
        raise ValueError(f"{nome} deve ser ≥ {minimo}: {valor}")


@dataclass(frozen=True)
class Cotacao:
    """Preços de um item, em centavos, nas fontes da cotação (3 por padrão, D-10)."""

    precos: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.precos, tuple) or not self.precos:
            raise ValueError("A cotação precisa de uma tupla com ao menos um preço")
        for preco in self.precos:
            _validar_inteiro(preco, "Preço", 1)

    @property
    def n(self) -> int:
        return len(self.precos)

    @property
    def soma(self) -> int:
        return sum(self.precos)

    @property
    def media_exata(self) -> Fraction:
        """Média sem arredondar, em centavos."""
        return Fraction(self.soma, self.n)

    @property
    def media_exibida(self) -> int:
        """Média arredondada (D-21): o valor que aparece na grade."""
        return arredondar_centavos(self.media_exata)

    def preco_regra_a(self) -> int:
        """Preço final pela Regra A: a média arredondada (D-20)."""
        return self.media_exibida

    def dentro_da_media(
        self, preco: int, comparar_com: ComparacaoMedia = ComparacaoMedia.EXATA
    ) -> bool:
        """Regra B: o preço da loja escolhida não pode passar da média (D-23, P-02).

        Com a média exata, a conta é feita só com inteiros: preço × n ≤ soma.
        """
        _validar_inteiro(preco, "Preço", 1)
        if comparar_com is ComparacaoMedia.EXATA:
            return preco * self.n <= self.soma
        return preco <= self.media_exibida

    def totais(self, quantidade: int) -> tuple[int, ...]:
        """Total de cada fonte para a quantidade da linha."""
        _validar_inteiro(quantidade, "Quantidade", 0)
        return tuple(p * quantidade for p in self.precos)

    def media_dos_totais(self, quantidade: int) -> int:
        """Média dos totais, arredondada, como na coluna "média do total" da grade.

        Pode diferir em centavos de quantidade × média unitária (docs/03 §2).
        """
        return arredondar_centavos(Fraction(sum(self.totais(quantidade)), self.n))
