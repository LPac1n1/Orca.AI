"""Domínio: tipos, identificadores e regras puras (sem acesso a rede ou disco)."""

from orca.dominio.identificadores import cnpj_raiz, formatar_cnpj, normalizar_cnpj, normalizar_gtin
from orca.dominio.periodo import MesesAtivos
from orca.dominio.tipos import (
    AlvoTipo,
    Autor,
    OrigemCorrespondencia,
    Regime,
    Severidade,
    StatusCorrespondencia,
    TipoFonte,
    TipoOrcamento,
)

__all__ = [
    "AlvoTipo",
    "Autor",
    "MesesAtivos",
    "OrigemCorrespondencia",
    "Regime",
    "Severidade",
    "StatusCorrespondencia",
    "TipoFonte",
    "TipoOrcamento",
    "cnpj_raiz",
    "formatar_cnpj",
    "normalizar_cnpj",
    "normalizar_gtin",
]
