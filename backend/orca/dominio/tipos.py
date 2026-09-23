"""Tipos do domínio: valores fixos e o autor de cada alteração."""

import re
from dataclasses import dataclass
from enum import StrEnum


class TipoOrcamento(StrEnum):
    MATERIAIS = "materiais"
    MAO_DE_OBRA = "mao_de_obra"
    SERVICOS = "servicos"


class Regime(StrEnum):
    MEI = "mei"
    RECIBO = "recibo"
    CLT = "clt"


class AlvoTipo(StrEnum):
    """Do que é uma observação ou cotação."""

    ITEM = "item"
    CARGO = "cargo"


class StatusCorrespondencia(StrEnum):
    VERDE = "verde"  # 🟢 mesmo produto
    AMARELO = "amarelo"  # 🟡 revisão necessária
    VERMELHO = "vermelho"  # 🔴 produto diferente


class OrigemCorrespondencia(StrEnum):
    EAN = "ean"
    ATRIBUTOS = "atributos"
    IA = "ia"
    HUMANO = "humano"


class TipoFonte(StrEnum):
    LOJA = "loja"
    EMPRESA = "empresa"  # empresa que anunciou a vaga
    FORNECEDOR = "fornecedor"  # proposta de serviço
    PUBLICA = "publica"  # ata, Painel de Preços etc. (D-18)


class Severidade(StrEnum):
    INFO = "info"
    ATENCAO = "atencao"
    PROBLEMA = "problema"


_AUTOR = re.compile(r"^(usuario:[^\s:][^:]*|sistema(:[a-z0-9_.-]+)?|ia:[A-Za-z0-9_.\-/]+)$")


@dataclass(frozen=True)
class Autor:
    """Quem fez uma alteração: "usuario:<nome>", "sistema[:<módulo>]" ou "ia:<provedor/modelo>".

    Toda gravação no banco precisa declarar o autor (princípio 2: rastreabilidade).
    """

    valor: str

    def __post_init__(self) -> None:
        if not isinstance(self.valor, str) or not _AUTOR.match(self.valor):
            raise ValueError(
                f"Autor inválido: {self.valor!r}. Use 'usuario:<nome>', 'sistema' ou 'ia:<provedor>'"
            )

    @property
    def tipo(self) -> str:
        return self.valor.split(":", 1)[0]

    def __str__(self) -> str:
        return self.valor
