"""Conferência de uma grade comparativa pronta (feita fora do sistema).

Recalcula as médias e os totais de cada linha e aponta as divergências, inclusive
o preço do plano acima da média — a mesma conferência que a secretaria faz.
Útil para revisar uma planilha antes de enviar.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from orca.calculo import ComparacaoMedia, Cotacao, formatar, formatar_exato


@dataclass(frozen=True)
class LinhaInformada:
    nome: str
    quantidade: int
    precos: tuple[int, ...]
    media_unitaria: int | None = None
    media_total: int | None = None
    totais: tuple[int, ...] | None = None
    preco_no_plano: int | None = None


@dataclass(frozen=True)
class Divergencia:
    item: str
    tipo: str  # "media_unitaria", "media_total", "total", "acima_da_media"
    informado: int
    correto: int | None
    mensagem: str


def conferir_grade(
    linhas: Sequence[LinhaInformada], comparar_com: ComparacaoMedia = ComparacaoMedia.EXATA
) -> list[Divergencia]:
    divergencias = []
    for linha in linhas:
        cotacao = Cotacao(tuple(linha.precos))
        if linha.media_unitaria is not None and linha.media_unitaria != cotacao.media_exibida:
            divergencias.append(
                Divergencia(
                    linha.nome, "media_unitaria", linha.media_unitaria, cotacao.media_exibida,
                    f"{linha.nome}: média unitária informada {formatar(linha.media_unitaria)}, "
                    f"o correto é {formatar(cotacao.media_exibida)}",
                )
            )
        correta_total = cotacao.media_dos_totais(linha.quantidade)
        if linha.media_total is not None and linha.media_total != correta_total:
            divergencias.append(
                Divergencia(
                    linha.nome, "media_total", linha.media_total, correta_total,
                    f"{linha.nome}: média do total informada {formatar(linha.media_total)}, "
                    f"o correto é {formatar(correta_total)}",
                )
            )
        if linha.totais is not None:
            for informado, correto in zip(linha.totais, cotacao.totais(linha.quantidade), strict=True):
                if informado != correto:
                    divergencias.append(
                        Divergencia(
                            linha.nome, "total", informado, correto,
                            f"{linha.nome}: total informado {formatar(informado)}, o correto é {formatar(correto)}",
                        )
                    )
        if linha.preco_no_plano is not None and not cotacao.dentro_da_media(linha.preco_no_plano, comparar_com):
            divergencias.append(
                Divergencia(
                    linha.nome, "acima_da_media", linha.preco_no_plano, None,
                    f"{linha.nome}: preço no plano {formatar(linha.preco_no_plano)} passa da média "
                    f"{formatar_exato(cotacao.media_exata)}",
                )
            )
    return divergencias
