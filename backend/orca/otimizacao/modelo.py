"""Tipos do problema de fechar o teto exato (docs/03 §4).

Unidades: dinheiro em centavos; horas em centésimos de hora. Preços e valores-hora
são constantes: o otimizador só mexe em quantidades e horas (D-31).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field


def faixa(planejado: int, min_percentual: int, max_percentual: int, travado: bool = False) -> tuple[int, int]:
    """Limites inteiros a partir da margem (D-32): [⌈planejado·(100+min)/100⌉, ⌊planejado·(100+max)/100⌋]."""
    if planejado < 0:
        raise ValueError("O valor planejado não pode ser negativo")
    if travado:
        return planejado, planejado
    minimo = -((-planejado * (100 + min_percentual)) // 100)
    maximo = (planejado * (100 + max_percentual)) // 100
    return max(0, minimo), max(0, maximo)


@dataclass(frozen=True)
class LinhaMaterial:
    """Linha de material ou serviço: preço final × quantidade por período × meses."""

    id: str
    nome: str
    orcamento: str
    preco_centavos: int
    quantidade_planejada: int
    meses: int
    qtd_min: int
    qtd_max: int
    custo_alteracao: int = 1  # maior = o otimizador evita mexer nesta linha

    def __post_init__(self) -> None:
        if not (0 <= self.qtd_min <= self.qtd_max):
            raise ValueError(f"Limites de quantidade inválidos em {self.nome!r}")
        if self.preco_centavos <= 0 or self.meses < 1 or self.custo_alteracao < 1:
            raise ValueError(f"Preço, meses ou custo inválidos em {self.nome!r}")


@dataclass(frozen=True)
class LinhaMaoDeObra:
    """Linha de mão de obra: valor mensal = R(valor-hora × horas) × meses × postos (D-43)."""

    id: str
    nome: str
    orcamento: str
    valor_hora_centavos: int
    horas_planejadas_centesimos: int
    meses: int
    postos: int
    horas_min_centesimos: int
    horas_max_centesimos: int
    horas_legais_centesimos: int  # jornada legal mensal = 100 × divisor (nunca é relaxada)
    custo_alteracao: int = 1

    def __post_init__(self) -> None:
        if not (0 < self.horas_min_centesimos <= self.horas_max_centesimos <= self.horas_legais_centesimos):
            raise ValueError(f"Limites de horas inválidos em {self.nome!r}")
        if self.valor_hora_centavos <= 0 or self.meses < 1 or self.postos < 1 or self.custo_alteracao < 1:
            raise ValueError(f"Valor-hora, meses, postos ou custo inválidos em {self.nome!r}")


@dataclass(frozen=True)
class RestricaoLote:
    """Regra B: a loja escolhida continua a de menor total (C3) e, opcionalmente,
    o trio continua sendo o das lojas mais baratas (C4). Preços: loja → linha → centavos."""

    lote: str
    escolhida: str
    outras_do_trio: tuple[str, ...]
    fora_do_trio: tuple[str, ...]
    precos: Mapping[str, Mapping[str, int]]
    manter_escolhida: bool = True  # C3
    manter_classificacao: bool = True  # C4


@dataclass(frozen=True)
class LimiteRubrica:
    orcamento: str
    min_centavos: int | None = None
    max_centavos: int | None = None


@dataclass(frozen=True)
class ProblemaTeto:
    teto_centavos: int
    materiais: tuple[LinhaMaterial, ...] = ()
    mao_de_obra: tuple[LinhaMaoDeObra, ...] = ()
    lotes: tuple[RestricaoLote, ...] = ()
    limites: tuple[LimiteRubrica, ...] = ()
    fixos_centavos: int = 0  # valores fora do otimizador

    def __post_init__(self) -> None:
        ids = [l.id for l in self.materiais] + [l.id for l in self.mao_de_obra]
        if not ids:
            raise ValueError("O problema precisa de ao menos uma linha")
        if len(ids) != len(set(ids)):
            raise ValueError("Há linhas com o mesmo identificador")
        if self.teto_centavos <= 0:
            raise ValueError("O teto precisa ser positivo")
        conhecidas = {l.id for l in self.materiais}
        for lote in self.lotes:
            lojas = (lote.escolhida, *lote.outras_do_trio, *lote.fora_do_trio)
            linhas = set(lote.precos[lote.escolhida])
            if not linhas <= conhecidas:
                raise ValueError(f"Lote {lote.lote!r} cita linhas que não estão no problema")
            for loja in lojas:
                if set(lote.precos.get(loja, {})) != linhas:
                    raise ValueError(f"Lote {lote.lote!r}: faltam preços da loja {loja!r}")


@dataclass(frozen=True)
class Alteracao:
    linha: str
    nome: str
    de: int
    para: int
    unidade: str  # "un" ou "h" (centésimos)


@dataclass(frozen=True)
class SolucaoTeto:
    otima: bool  # False = achou solução válida, mas o tempo acabou antes de provar que é a melhor
    quantidades: Mapping[str, int]
    horas_centesimos: Mapping[str, int]
    valores_mensais: Mapping[str, int]  # mão de obra
    totais: Mapping[str, int]  # total de cada linha
    total_centavos: int
    alteracoes: tuple[Alteracao, ...]
    verificacao: tuple[str, ...]  # problemas encontrados pela verificação independente (vazio = ok)
    versao_otimizador: str

    @property
    def verificacao_ok(self) -> bool:
        return not self.verificacao


@dataclass(frozen=True)
class Sugestao:
    tipo: str  # "margem", "limite_rubrica", "classificacao", "trio"
    alvo: str
    mensagem: str
    tamanho: float = 0.0  # para ordenar: menor mudança primeiro


@dataclass(frozen=True)
class SemSolucao:
    motivo: str  # "limites", "divisibilidade", "conflito", "tempo"
    mensagem: str
    conflitos: tuple[str, ...] = ()
    sugestoes: tuple[Sugestao, ...] = field(default=())
