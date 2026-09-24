"""Entradas da API, validadas. Dinheiro em centavos, horas em centésimos (como no resto do sistema)."""

import re
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

Centavos = Annotated[int, Field(ge=0)]
Mes = Annotated[int, Field(ge=1, le=120)]
Margem = Annotated[int, Field(ge=-100, le=1000)]


def _cep(valor: str | None) -> str | None:
    """"03977-015" ou "03977015" → "03977015"; vazio → sem CEP."""
    if valor is None or not valor.strip():
        return None
    digitos = re.sub(r"\D", "", valor)
    if len(digitos) != 8:
        raise ValueError("o CEP deve ter 8 números, por exemplo 03977-015")
    return digitos


Cep = Annotated[str | None, AfterValidator(_cep)]


class _Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NovaOrganizacao(_Entrada):
    nome: str = Field(min_length=1, max_length=200)
    cnpj: str | None = None


class NovoProjeto(_Entrada):
    organizacao_id: str
    nome: str = Field(min_length=1, max_length=300)
    teto_centavos: Annotated[int, Field(gt=0)]
    duracao_meses: Annotated[int, Field(ge=1, le=120)]
    orgao: str | None = None
    instrumento: str | None = None
    processo: str | None = None
    cep: Cep = None
    data_entrega: date | None = None


class MudancaProjeto(_Entrada):
    nome: str | None = Field(default=None, min_length=1, max_length=300)
    teto_centavos: Annotated[int, Field(gt=0)] | None = None
    duracao_meses: Annotated[int, Field(ge=1, le=120)] | None = None
    orgao: str | None = None
    instrumento: str | None = None
    processo: str | None = None
    cep: Cep = None
    data_entrega: date | None = None


class NovoOrcamento(_Entrada):
    nome: str = Field(min_length=1, max_length=200)
    tipo: Literal["materiais", "mao_de_obra", "servicos"]
    descricao: str | None = None


class MudancaOrcamento(_Entrada):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    descricao: str | None = None


class NovoLote(_Entrada):
    nome: str = Field(min_length=1, max_length=200)


class DadosItem(_Entrada):
    descricao: str | None = Field(default=None, min_length=1, max_length=300)
    categoria: str | None = None
    marca: str | None = None
    modelo: str | None = None
    apresentacao: str | None = None
    atributos: dict[str, Any] | None = None
    ean: str | None = None
    unidade: str | None = None
    qtd_planejada: Annotated[int, Field(ge=0)] | None = None
    mes_inicio: Mes | None = None
    mes_fim: Mes | None = None
    margem_min_percentual: Margem | None = None
    margem_max_percentual: Margem | None = None
    travado: bool | None = None


class NovoItem(DadosItem):
    descricao: str = Field(min_length=1, max_length=300)
    qtd_planejada: Annotated[int, Field(ge=0)]
    mes_inicio: Mes = 1
    mes_fim: Mes


class TrocaDeProduto(DadosItem):
    justificativa: str = Field(min_length=1)


class DadosCargo(_Entrada):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    cbo: str | None = None
    postos: Annotated[int, Field(ge=1)] | None = None
    regime: Literal["mei", "recibo", "clt"] | None = None
    jornada_id: str | None = None
    horas_planejadas_centesimos: Annotated[int, Field(gt=0)] | None = None
    mes_inicio: Mes | None = None
    mes_fim: Mes | None = None
    margem_min_percentual: Margem | None = None
    margem_max_percentual: Margem | None = None
    travado: bool | None = None


class NovoCargo(DadosCargo):
    nome: str = Field(min_length=1, max_length=200)
    regime: Literal["mei", "recibo", "clt"]
    horas_planejadas_centesimos: Annotated[int, Field(gt=0)]
    mes_inicio: Mes = 1
    mes_fim: Mes


class ColetaDeItem(_Entrada):
    url: str = Field(pattern=r"^https?://")
    cnpj_vendedor: str | None = None
    preco_centavos: Annotated[int, Field(gt=0)] | None = None  # captura assistida: preço que a pessoa vê


class ColetaDeCargo(_Entrada):
    url: str = Field(pattern=r"^https?://")
    cnpj_empresa: str | None = None
    salario_min_centavos: Annotated[int, Field(gt=0)] | None = None
    salario_max_centavos: Annotated[int, Field(gt=0)] | None = None


class DecisaoDeCorrespondencia(_Entrada):
    item_id: str
    observacao_id: str
    status: Literal["verde", "amarelo", "vermelho"]
    justificativa: str = Field(min_length=1)


class CorrecaoDePreco(_Entrada):
    preco_centavos: Annotated[int, Field(gt=0)]
    justificativa: str = Field(min_length=1)


class PedidoDeBusca(_Entrada):
    lojas: list[str] = Field(min_length=1)


class DecisaoDeLoja(_Entrada):
    loja: str
    justificativa: str = Field(min_length=1)


class MesmaVaga(_Entrada):
    a: str
    b: str
    justificativa: str = Field(min_length=1)


class Justificativa(_Entrada):
    justificativa: str = Field(min_length=1)


class CapturaAssistida(_Entrada):
    url: str = Field(pattern=r"^https?://")
    cnpj_vendedor: str | None = None
    preco_centavos: Annotated[int, Field(gt=0)] | None = None


class CapturaAssistidaDeCargo(_Entrada):
    url: str = Field(pattern=r"^https?://")
    cnpj_empresa: str | None = None
    salario_min_centavos: Annotated[int, Field(gt=0)] | None = None
    salario_max_centavos: Annotated[int, Field(gt=0)] | None = None


class PedidoDeComprovante(_Entrada):
    cnpj: str = Field(min_length=14, max_length=18)
    projeto_id: str | None = None


class CatalogoEditado(_Entrada):
    """O catálogo como a OSC quer que fique; o sistema grava só a diferença para o do sistema."""

    conteudo: dict[str, Any]
    resumo: str | None = Field(default=None, max_length=500)


class NovoPar(_Entrada):
    titulo_a: str = Field(min_length=1, max_length=500)
    titulo_b: str = Field(min_length=1, max_length=500)
    rotulo: Literal["mesmo", "diferente"]
    categoria: str | None = None
    marca_a: str | None = None
    marca_b: str | None = None
    motivo: str | None = None


class RegrasProprias(_Entrada):
    """Só o que muda em relação às camadas de cima (vazio = nenhuma regra própria)."""

    conteudo: dict[str, Any]
