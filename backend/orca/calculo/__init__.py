"""Núcleo de cálculo: dinheiro em centavos, arredondamento, cotações e mão de obra.

Sem acesso a rede ou disco (docs/04 §3).
"""

from orca.calculo.arredondamento import arredondar_centavos
from orca.calculo.cotacao import ComparacaoMedia, Cotacao
from orca.calculo.dinheiro import (
    centavos_de_decimal,
    centavos_de_texto,
    formatar,
    formatar_exato,
)
from orca.calculo.mao_de_obra import (
    CalculoMaoDeObra,
    calcular_mao_de_obra,
    centesimos_de_horas,
    divisor_mensal,
    formatar_horas,
)

__all__ = [
    "CalculoMaoDeObra",
    "ComparacaoMedia",
    "Cotacao",
    "arredondar_centavos",
    "calcular_mao_de_obra",
    "centavos_de_decimal",
    "centavos_de_texto",
    "centesimos_de_horas",
    "divisor_mensal",
    "formatar",
    "formatar_exato",
    "formatar_horas",
]
