"""Cálculo de mão de obra (docs/03 §3; D-41 a D-44).

Sequência, com arredondamento comercial em cada etapa (D-43):
    média das vagas → valor-hora = média ÷ divisor → valor mensal = valor-hora × horas
    → total = valor mensal × meses × postos
Divisor mensal = jornada semanal máxima legal × 5 (D-42).
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from orca.calculo.arredondamento import arredondar_centavos
from orca.calculo.dinheiro import formatar, formatar_exato

FATOR_DIVISOR_PADRAO = 5  # D-42

_HORAS = re.compile(r"^\s*(\d+)(?:[,.](\d{1,2}))?\s*$")


def centesimos_de_horas(texto: str) -> int:
    """Lê horas com até 2 decimais ("91,5" → 9150 centésimos de hora)."""
    m = _HORAS.match(texto)
    if not m:
        raise ValueError(f"Horas em formato inválido: {texto!r}")
    inteiro, fracao = m.groups()
    return int(inteiro) * 100 + int((fracao or "0").ljust(2, "0"))


def formatar_horas(centesimos: int) -> str:
    horas, resto = divmod(centesimos, 100)
    return f"{horas},{resto:02d} h"


def divisor_mensal(jornada_semanal_horas: int, fator: int = FATOR_DIVISOR_PADRAO) -> int:
    """Horas mensais que dividem o salário: jornada semanal × fator (44 h → 220)."""
    for valor, nome in ((jornada_semanal_horas, "Jornada semanal"), (fator, "Fator")):
        if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
            raise ValueError(f"{nome} deve ser um inteiro positivo: {valor!r}")
    return jornada_semanal_horas * fator


@dataclass(frozen=True)
class CalculoMaoDeObra:
    """Resultado com todos os valores intermediários (memória de cálculo)."""

    salarios: tuple[int, ...]
    media_exata: Fraction
    media: int
    jornada_semanal_horas: int
    divisor: int
    valor_hora_exato: Fraction
    valor_hora: int
    horas_mes_centesimos: int
    valor_mensal_exato: Fraction
    valor_mensal: int
    meses: int
    postos: int
    total: int

    def memoria(self) -> list[str]:
        """Linhas da memória de cálculo, com fórmula e valores antes e depois do arredondamento."""
        soma = " + ".join(formatar(s) for s in self.salarios)
        return [
            f"Média: ({soma}) ÷ {len(self.salarios)} = "
            f"{formatar_exato(self.media_exata)} → {formatar(self.media)}",
            f"Divisor: {self.jornada_semanal_horas} h semanais × "
            f"{self.divisor // self.jornada_semanal_horas} = {self.divisor} h",
            f"Valor-hora: {formatar(self.media)} ÷ {self.divisor} = "
            f"{formatar_exato(self.valor_hora_exato)} → {formatar(self.valor_hora)}",
            f"Valor mensal: {formatar(self.valor_hora)} × {formatar_horas(self.horas_mes_centesimos)} = "
            f"{formatar_exato(self.valor_mensal_exato)} → {formatar(self.valor_mensal)}",
            f"Total: {formatar(self.valor_mensal)} × {self.meses} "
            f"{'mês' if self.meses == 1 else 'meses'} × {self.postos} "
            f"{'posto' if self.postos == 1 else 'postos'} = {formatar(self.total)}",
        ]


def calcular_mao_de_obra(
    salarios: Sequence[int],
    jornada_semanal_horas: int,
    horas_mes_centesimos: int,
    meses: int,
    postos: int = 1,
    fator_divisor: int = FATOR_DIVISOR_PADRAO,
) -> CalculoMaoDeObra:
    """Calcula o valor de um cargo a partir dos salários da cotação (em centavos)."""
    salarios = tuple(salarios)
    if not salarios:
        raise ValueError("Informe ao menos um salário")
    for s in salarios:
        if isinstance(s, bool) or not isinstance(s, int) or s <= 0:
            raise ValueError(f"Salário deve ser centavos inteiros positivos: {s!r}")
    for valor, nome in ((horas_mes_centesimos, "Horas por mês"), (meses, "Meses"), (postos, "Postos")):
        if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
            raise ValueError(f"{nome} deve ser um inteiro positivo: {valor!r}")

    divisor = divisor_mensal(jornada_semanal_horas, fator_divisor)
    if horas_mes_centesimos > divisor * 100:  # D-32: sem passar da jornada legal
        raise ValueError(
            f"{formatar_horas(horas_mes_centesimos)} por mês passa da jornada legal "
            f"de {divisor} h"
        )

    media_exata = Fraction(sum(salarios), len(salarios))
    media = arredondar_centavos(media_exata)
    valor_hora_exato = Fraction(media, divisor)
    valor_hora = arredondar_centavos(valor_hora_exato)
    valor_mensal_exato = Fraction(valor_hora * horas_mes_centesimos, 100)
    valor_mensal = arredondar_centavos(valor_mensal_exato)

    return CalculoMaoDeObra(
        salarios=salarios,
        media_exata=media_exata,
        media=media,
        jornada_semanal_horas=jornada_semanal_horas,
        divisor=divisor,
        valor_hora_exato=valor_hora_exato,
        valor_hora=valor_hora,
        horas_mes_centesimos=horas_mes_centesimos,
        valor_mensal_exato=valor_mensal_exato,
        valor_mensal=valor_mensal,
        meses=meses,
        postos=postos,
        total=valor_mensal * meses * postos,
    )
