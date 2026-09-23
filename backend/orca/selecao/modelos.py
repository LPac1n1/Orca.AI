"""Tipos da seleção de lojas e vagas (docs/02 §8–§10; docs/03 §5).

A seleção é pura: recebe as ofertas já coletadas e conferidas e decide, sem
acessar rede nem banco.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from orca.calculo import ComparacaoMedia, Cotacao
from orca.regras import PerfilRegras


@dataclass(frozen=True)
class ParametrosSelecao:
    """O que a seleção precisa das regras. Use `de_regras` para montar a partir do perfil."""

    fontes_por_cotacao: int = 3  # D-10
    base_preco_final: str = "B"  # D-20
    comparar_com: ComparacaoMedia = ComparacaoMedia.EXATA  # P-02
    cnpjs_distintos: bool = True  # P-03
    cnpj_ativo_obrigatorio: bool = True
    exige_cnpj: bool = True  # D-16: descartar sem CNPJ do vendedor
    lotes_permitidos: bool = True  # D-24
    resolucoes: tuple[str, ...] = ("trocar_produto", "trocar_loja")  # D-23

    @classmethod
    def de_regras(cls, regras: PerfilRegras) -> "ParametrosSelecao":
        return cls(
            fontes_por_cotacao=regras.fontes.fontes_por_cotacao,
            base_preco_final=regras.calculo.base_preco_final,
            comparar_com=regras.calculo.comparacao_media,
            cnpjs_distintos=regras.fontes.cnpjs_distintos_na_cotacao,
            cnpj_ativo_obrigatorio=regras.evidencia.cnpj_ativo_obrigatorio,
            exige_cnpj=regras.fontes.marketplace.descartar_sem_cnpj_vendedor,
            lotes_permitidos=regras.calculo.lotes_dentro_do_orcamento == "permitido",
            resolucoes=tuple(regras.calculo.resolucao_item_acima_da_media),
        )


@dataclass(frozen=True)
class ItemLote:
    """Item do lote com a quantidade planejada (por período) e o número de meses."""

    id: str
    nome: str
    quantidade: int
    meses: int = 1

    @property
    def quantidade_total(self) -> int:
        return self.quantidade * self.meses


@dataclass(frozen=True)
class Oferta:
    """Preço de um item numa loja, vindo de uma observação."""

    preco_centavos: int
    verde: bool = True  # correspondência 🟢 (mesmo produto)
    evidencia_valida: bool = True
    observacao_id: str | None = None

    @property
    def utilizavel(self) -> bool:
        return self.verde and self.evidencia_valida


@dataclass(frozen=True)
class Loja:
    id: str
    nome: str
    cnpj: str | None  # do vendedor, normalizado
    ofertas: Mapping[str, Oferta]  # item_id → oferta
    cnpj_ativo: bool = True
    qualidade_evidencia: int = 0  # desempate: maior primeiro


@dataclass(frozen=True)
class LojaClassificada:
    loja: Loja
    total_centavos: int  # com as quantidades planejadas × meses (P-05)


@dataclass(frozen=True)
class Violacao:
    """Item cujo preço na loja escolhida passa da média (Regra B, D-23)."""

    item: ItemLote
    loja: Loja
    preco_centavos: int
    cotacao: Cotacao
    mensagem: str


@dataclass(frozen=True)
class LinhaGrade:
    item: ItemLote
    precos: tuple[int, ...]  # na ordem do trio (Orçamento 1, 2, 3)
    totais: tuple[int, ...]  # preço × quantidade do período
    cotacao: Cotacao
    media_total_centavos: int
    preco_final_centavos: int
    dentro_da_media: bool | None  # None na Regra A


@dataclass(frozen=True)
class AnaliseLote:
    """Trio escolhido, grade comparativa e conferência preço × média."""

    trio: tuple[LojaClassificada, ...]
    linhas: tuple[LinhaGrade, ...]
    violacoes: tuple[Violacao, ...]
    descartadas: tuple[tuple[Loja, str], ...]
    justificativa: str
    parametros: ParametrosSelecao = field(repr=False)
    # Lojas completas que ficaram fora do trio, em ordem (para manter a classificação, C4).
    demais_elegiveis: tuple[LojaClassificada, ...] = ()

    @property
    def escolhida(self) -> Loja:
        """A loja do Orçamento 1: a de menor total (D-26)."""
        return self.trio[0].loja

    def soma_precos_unitarios(self, posicao: int) -> int:
        return sum(linha.precos[posicao] for linha in self.linhas)

    def total_do_periodo(self, posicao: int) -> int:
        return sum(linha.totais[posicao] for linha in self.linhas)


@dataclass(frozen=True)
class SemTrio:
    """Não foi possível formar o trio: diz por quê e o que fazer (docs/02 §8)."""

    necessarias: int
    completas: tuple[Loja, ...]
    bloqueadores: tuple[tuple[ItemLote, int], ...]  # item e em quantas lojas válidas ele existe
    descartadas: tuple[tuple[Loja, str], ...]
    mensagem: str
    sugestoes: tuple[str, ...]
