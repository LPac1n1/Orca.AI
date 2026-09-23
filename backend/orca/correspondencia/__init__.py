"""Correspondência: o produto da página é exatamente o item pedido? (docs/02 §7; D-17, D-52)

Sem IA e sem acesso a rede ou disco: código de barras, marca, atributos críticos da
categoria (medidas e vocabulário) e palavras que sobram. Na dúvida, 🟡.
"""

from orca.correspondencia.avaliacao import Avaliacao, Par, avaliar, pares_do_sistema
from orca.correspondencia.comparar import (
    Anuncio,
    ComparacaoAtributo,
    Especificacao,
    ResultadoCorrespondencia,
    Situacao,
    comparar,
)
from orca.correspondencia.medidas import LEITORES, Quantidade
from orca.correspondencia.texto import normalizar
from orca.correspondencia.vocabulario import Grupo, Vocabulario, valores_no_texto

__all__ = [
    "LEITORES",
    "Anuncio",
    "Avaliacao",
    "ComparacaoAtributo",
    "Especificacao",
    "Grupo",
    "Par",
    "Quantidade",
    "ResultadoCorrespondencia",
    "Situacao",
    "Vocabulario",
    "avaliar",
    "comparar",
    "normalizar",
    "pares_do_sistema",
    "valores_no_texto",
]
