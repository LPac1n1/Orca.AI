"""Evidências: armazém de arquivos endereçados pelo conteúdo, com conferência de integridade,
e validade das pesquisas e dos comprovantes."""

from orca.evidencias.armazem import ArmazemArquivos, ArquivoGuardado, ErroIntegridade, impressao
from orca.evidencias.validade import (
    SituacaoValidade,
    Validade,
    comprovante_reaproveitavel,
    dia_em_brasilia,
    hoje_em_brasilia,
    validade,
)

__all__ = [
    "ArmazemArquivos",
    "ArquivoGuardado",
    "ErroIntegridade",
    "SituacaoValidade",
    "Validade",
    "comprovante_reaproveitavel",
    "dia_em_brasilia",
    "hoje_em_brasilia",
    "impressao",
    "validade",
]
