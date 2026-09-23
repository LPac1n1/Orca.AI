"""O dossiê: tudo o que os documentos mostram, num só lugar (docs/02 §18).

Os documentos (planilhas, PDFs, pacote) só leem o dossiê; nenhum número é
calculado de novo por eles, a não ser as fórmulas das planilhas, que o teste
confere contra os valores daqui.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from fractions import Fraction

from orca.calculo import Cotacao, arredondar_centavos


@dataclass(frozen=True)
class ArquivoRef:
    """Arquivo guardado no armazém de evidências."""

    caminho: str  # relativo à pasta de dados (ArmazemArquivos)
    sha256: str
    tipo: str  # "pdf" | "png" | "mhtml"


@dataclass(frozen=True)
class EvidenciaDoc:
    url: str
    coletado_em: datetime
    metodo: str = "C1"
    arquivos: tuple[ArquivoRef, ...] = ()

    def arquivo(self, tipo: str) -> ArquivoRef | None:
        return next((a for a in self.arquivos if a.tipo == tipo), None)


@dataclass(frozen=True)
class Empresa:
    nome: str
    cnpj: str | None
    situacao: str | None = None  # "ATIVA", "BAIXADA"… (None = não consultado)
    consultado_em: datetime | None = None
    comprovante: ArquivoRef | None = None  # comprovante da Receita (D-13)


@dataclass(frozen=True)
class FonteItem:
    """O preço de um item numa loja, com a página de onde veio."""

    loja: str  # id da loja no lote
    preco_centavos: int
    evidencia: EvidenciaDoc | None = None
    titulo_na_pagina: str | None = None


@dataclass(frozen=True)
class LinhaCotacao:
    id: str
    nome: str
    unidade: str
    quantidade: int  # por período (mês), depois da otimização (D-25)
    quantidade_planejada: int
    meses: int
    mes_inicio: int
    fontes: tuple[FonteItem, ...]  # na ordem dos orçamentos (1, 2, 3…)
    preco_final_centavos: int
    base_preco_final: str  # "A" | "B" (D-20)
    comparar_com: str = "media_exata"  # P-02

    @property
    def cotacao(self) -> Cotacao:
        return Cotacao(tuple(f.preco_centavos for f in self.fontes))

    @property
    def precos(self) -> tuple[int, ...]:
        return tuple(f.preco_centavos for f in self.fontes)

    @property
    def totais(self) -> tuple[int, ...]:
        return tuple(p * self.quantidade for p in self.precos)

    @property
    def media_exata(self) -> Fraction:
        return self.cotacao.media_exata

    @property
    def media_exibida(self) -> int:
        return self.cotacao.media_exibida

    @property
    def media_dos_totais(self) -> int:
        return arredondar_centavos(Fraction(sum(self.totais), len(self.fontes)))

    @property
    def total_final(self) -> int:
        """Preço final × quantidade do período (a grade)."""
        return self.preco_final_centavos * self.quantidade

    @property
    def total_no_projeto(self) -> int:
        """Preço final × quantidade × meses (o plano de aplicação)."""
        return self.preco_final_centavos * self.quantidade * self.meses

    @property
    def dentro_da_media(self) -> bool | None:
        if self.base_preco_final != "B":
            return None
        if self.comparar_com == "media_exata":
            return self.preco_final_centavos * len(self.fontes) <= sum(self.precos)
        return self.preco_final_centavos <= self.media_exibida


@dataclass(frozen=True)
class LojaDoLote:
    id: str
    empresa: Empresa
    total_centavos: int  # soma dos totais do período, com as quantidades finais


@dataclass(frozen=True)
class LoteDoc:
    nome: str
    lojas: tuple[LojaDoLote, ...]  # na ordem dos orçamentos: 1 = menor total (D-26)
    linhas: tuple[LinhaCotacao, ...]
    base_preco_final: str
    justificativa: str = ""
    demais_elegiveis: tuple[LojaDoLote, ...] = ()
    descartadas: tuple[tuple[str, str], ...] = ()  # (loja, motivo)

    @property
    def total_final(self) -> int:
        return sum(l.total_final for l in self.linhas)

    @property
    def total_no_projeto(self) -> int:
        return sum(l.total_no_projeto for l in self.linhas)


@dataclass(frozen=True)
class VagaDoc:
    empresa: Empresa
    salario_centavos: int  # faixa → menor valor (D-46)
    descricao: str = ""  # como a vaga aparece (título, faixa)
    plataforma: str | None = None
    evidencia: EvidenciaDoc | None = None


@dataclass(frozen=True)
class CargoDoc:
    id: str
    nome: str
    regime: str
    jornada_semanal_horas: int
    divisor: int
    vagas: tuple[VagaDoc, ...]
    media_centavos: int
    valor_hora_centavos: int
    horas_mes_centesimos: int  # depois da otimização
    horas_planejadas_centesimos: int
    valor_mensal_centavos: int
    meses: int
    postos: int
    mes_inicio: int
    memoria: tuple[str, ...]
    descartadas: tuple[tuple[str, str], ...] = ()  # (vaga, motivo)

    @property
    def total_no_projeto(self) -> int:
        return self.valor_mensal_centavos * self.meses * self.postos


@dataclass(frozen=True)
class OrcamentoDoc:
    """Uma rubrica do projeto."""

    nome: str
    tipo: str  # "materiais" | "mao_de_obra" | "servicos"
    lotes: tuple[LoteDoc, ...] = ()
    cargos: tuple[CargoDoc, ...] = ()

    @property
    def total_no_projeto(self) -> int:
        return sum(l.total_no_projeto for l in self.lotes) + sum(c.total_no_projeto for c in self.cargos)


@dataclass(frozen=True)
class AlteracaoDoc:
    nome: str
    de: str
    para: str


@dataclass(frozen=True)
class OtimizacaoDoc:
    status: str  # "otima" | "viavel" | "sem_otimizacao"
    total_centavos: int
    alteracoes: tuple[AlteracaoDoc, ...] = ()
    verificacao: tuple[str, ...] = ()  # problemas da verificação independente (vazio = ok)
    versao: str = ""


@dataclass(frozen=True)
class ProjetoDoc:
    nome: str
    organizacao: Empresa
    teto_centavos: int
    duracao_meses: int
    orgao: str | None = None
    instrumento: str | None = None
    processo: str | None = None
    cep: str | None = None
    data_entrega: date | None = None
    contrapartida_centavos: int = 0
    desembolso: str = "parcela_unica_mes_1"  # P-06 | "conforme_cronograma"
    fontes_por_cotacao: int = 3  # D-10
    validade_dias: int = 180  # D-12
    aviso_vencimento_dias: int = 30
    impressao_regras: str = ""
    versao_sistema: str = ""
    gerado_em: datetime | None = None


@dataclass(frozen=True)
class EventoDoc:
    criado_em: datetime
    entidade: str
    entidade_id: str
    acao: str
    autor: str
    antes: dict | None = None
    depois: dict | None = None


@dataclass(frozen=True)
class Dossie:
    projeto: ProjetoDoc
    orcamentos: tuple[OrcamentoDoc, ...]
    otimizacao: OtimizacaoDoc
    empresas: dict[str, Empresa] = field(default_factory=dict)  # CNPJ → dados e comprovante
    eventos: tuple[EventoDoc, ...] = ()

    @property
    def total_centavos(self) -> int:
        return sum(o.total_no_projeto for o in self.orcamentos)

    def empresa(self, cnpj: str | None) -> Empresa | None:
        return self.empresas.get(cnpj) if cnpj else None
