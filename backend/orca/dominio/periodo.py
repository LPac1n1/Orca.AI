"""Meses ativos de uma linha do orçamento (ex.: do 2º ao 11º mês)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MesesAtivos:
    inicio: int
    fim: int

    def __post_init__(self) -> None:
        for valor, nome in ((self.inicio, "Mês inicial"), (self.fim, "Mês final")):
            if isinstance(valor, bool) or not isinstance(valor, int) or valor < 1:
                raise ValueError(f"{nome} deve ser um inteiro a partir de 1: {valor!r}")
        if self.fim < self.inicio:
            raise ValueError(f"O mês final ({self.fim}) vem antes do inicial ({self.inicio})")

    @property
    def quantidade(self) -> int:
        return self.fim - self.inicio + 1

    def cabe_em(self, duracao_meses: int) -> bool:
        return self.fim <= duracao_meses

    def contem(self, mes: int) -> bool:
        return self.inicio <= mes <= self.fim

    def __str__(self) -> str:
        return f"{self.inicio}º ao {self.fim}º mês" if self.fim != self.inicio else f"{self.inicio}º mês"
