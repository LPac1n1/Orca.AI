"""Esquema do perfil de regras (docs/05 §1).

Cada chave tem tipo e valores permitidos. Opções que o sistema ainda não
implementa aceitam só o valor padrão. As travas que protegem os princípios
invioláveis (docs/README.md) não podem ser desligadas por nenhuma camada.
"""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from orca.calculo import ComparacaoMedia

NivelAutomacao = Literal["automatico", "com_aprovacao", "manual"]
Percentual = Annotated[int, Field(ge=0, le=100)]
_CEP = re.compile(r"^\d{5}-?\d{3}$")


def _erro(campo: str | None, mensagem: str) -> PydanticCustomError:
    """Erro de regra; `campo` é o caminho completo, ou None para usar a posição do erro."""
    return PydanticCustomError("regra_invalida", mensagem, {"campo": campo} if campo else None)


def _sem_repetidos(lista: list, campo: str) -> None:
    if len(set(lista)) != len(lista):
        raise _erro(campo, "a lista tem valores repetidos")


class _Grupo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Marketplace(_Grupo):
    permitido: bool
    cnpj_considerado: Literal["vendedor"]
    um_vendedor_por_orcamento_comparativo: bool
    descartar_sem_cnpj_vendedor: bool


class FontesAlternativas(_Grupo):
    atas_registro_preco: bool
    painel_de_precos: bool
    caged: bool
    convencao_coletiva: bool


class Fontes(_Grupo):
    fontes_por_cotacao: int = Field(ge=1, le=10)
    lojas_virtuais: Literal["permitidas", "proibidas"]
    validade_dias: int = Field(ge=1)
    aviso_vencimento_dias: int = Field(ge=0)
    cnpjs_distintos_na_cotacao: bool
    marketplace: Marketplace
    fontes_alternativas: FontesAlternativas

    @model_validator(mode="after")
    def checar_aviso_antes_do_vencimento(self):
        if self.aviso_vencimento_dias >= self.validade_dias:
            raise _erro(
                "fontes.aviso_vencimento_dias",
                "o aviso de vencimento precisa ser menor que a validade da pesquisa",
            )
        return self


class PrecoReferencia(_Grupo):
    frete: Literal["excluir", "incluir"]
    desconto_pix: Literal["ignorar", "usar"]
    cupom: Literal["ignorar", "usar"]
    clube_assinatura_ou_login: Literal["ignorar", "usar"]
    promocao_aberta_a_todos: Literal["usar", "ignorar"]
    preco_por_quantidade: Literal["ignorar"]  # D-63: o otimizador exige preço fixo
    cep: str

    @model_validator(mode="after")
    def checar_cep(self):
        if self.cep != "do_projeto" and not _CEP.match(self.cep):
            raise _erro("preco_referencia.cep", 'use "do_projeto" ou um CEP como "03977-015"')
        return self


class Produto(_Grupo):
    equivalencia: Literal["mesma_marca_modelo_apresentacao", "mesmo_ean"]
    exige_ean_igual: bool
    atributos_criticos: str


class Evidencia(_Grupo):
    por_fonte: list[Literal["pdf", "png", "html"]] = Field(min_length=1)
    cabecalho_pdf: list[Literal["url", "data_hora", "cep", "sha256"]]
    pdf_por_cotacao: bool
    comprovante_receita: Literal["obrigatorio", "opcional"]
    reaproveitar_comprovante_dias: int = Field(ge=0)
    cnpj_ativo_obrigatorio: bool

    @model_validator(mode="after")
    def checar_pdf_obrigatorio(self):
        _sem_repetidos(self.por_fonte, "evidencia.por_fonte")
        _sem_repetidos(self.cabecalho_pdf, "evidencia.cabecalho_pdf")
        if "pdf" not in self.por_fonte:
            raise _erro("evidencia.por_fonte", "o PDF da página é obrigatório (D-13)")
        for item in ("url", "data_hora"):
            if item not in self.cabecalho_pdf:
                raise _erro("evidencia.cabecalho_pdf", f"o cabeçalho do PDF precisa ter {item} (D-13)")
        return self


class Cnpj(_Grupo):
    provedores: list[str] = Field(min_length=1)
    aceita_alfanumerico: Literal[True]  # D-19: o formato novo já existe


class Calculo(_Grupo):
    base_preco_final: Literal["A", "B"]
    arredondamento: Literal["comercial"]
    casas_decimais: Literal[2]
    comparar_com: Literal["media_exata", "media_exibida"]
    misturar_lojas_no_final: Literal[False]
    resolucao_item_acima_da_media: list[Literal["trocar_produto", "trocar_loja"]] = Field(min_length=1)
    lotes_dentro_do_orcamento: Literal["permitido", "proibido"]
    comparativos_usam_quantidades_finais: Literal[True]
    orcamento_1: Literal["menor_total"]

    @property
    def comparacao_media(self) -> ComparacaoMedia:
        return ComparacaoMedia(self.comparar_com)

    @model_validator(mode="after")
    def checar_resolucao(self):
        _sem_repetidos(self.resolucao_item_acima_da_media, "calculo.resolucao_item_acima_da_media")
        return self


class LimiteOrcamento(_Grupo):
    min_centavos: Annotated[int, Field(ge=0)] | None = None
    max_centavos: Annotated[int, Field(ge=0)] | None = None
    min_percentual: Percentual | None = None
    max_percentual: Percentual | None = None

    @model_validator(mode="after")
    def checar_limites(self):
        if all(v is None for v in (self.min_centavos, self.max_centavos, self.min_percentual, self.max_percentual)):
            raise _erro(None, "informe ao menos um limite")
        for menor, maior in ((self.min_centavos, self.max_centavos), (self.min_percentual, self.max_percentual)):
            if menor is not None and maior is not None and menor > maior:
                raise _erro(None, "o mínimo não pode ser maior que o máximo")
        return self


class Teto(_Grupo):
    nivel: Literal["projeto"]
    exato: Literal[True]
    limites_por_orcamento: dict[str, LimiteOrcamento]


class Margem(_Grupo):
    min_percentual: int = Field(ge=-100, le=0)
    max_percentual: int = Field(ge=0, le=1000)


class Otimizacao(_Grupo):
    margem_quantidade: Margem
    margem_horas: Margem
    meses: Literal["definidos_pelo_usuario"]
    manter_loja_escolhida_menor_total: bool
    manter_classificacao: bool
    objetivo: list[Literal["menos_linhas_alteradas", "menor_desvio_relativo"]] = Field(min_length=1)

    @model_validator(mode="after")
    def checar_objetivo(self):
        _sem_repetidos(self.objetivo, "otimizacao.objetivo")
        return self


class MaoDeObra(_Grupo):
    fontes_por_cotacao: int = Field(ge=1, le=10)
    valor_referencia: Literal["media"]
    divisor: Literal["jornada_semanal_x5"]
    tabela_jornadas: str
    sequencia_arredondamento: list[Literal["media", "valor_hora", "valor_mensal"]]
    horas_casas_decimais: int = Field(ge=0, le=2)
    encargos: Literal[False]
    regime_padrao: list[Literal["mei_se_permitido", "recibo", "clt"]] = Field(min_length=1)
    formula_por_regime: dict[Literal["mei", "recibo", "clt"], Literal["padrao"]]
    faixa_salarial: Literal["menor_valor"]
    vaga_sem_salario: Literal["descartar"]
    empresa_nao_identificada: Literal["descartar"]
    empresas_distintas_na_cotacao: bool
    mesmo_municipio: bool
    idade_maxima_vaga_dias: Annotated[int, Field(ge=1)] | None
    escolha: Literal["tres_menores_salarios"]
    plataformas: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def checar_mao_de_obra(self):
        if self.sequencia_arredondamento != ["media", "valor_hora", "valor_mensal"]:
            raise _erro(
                "mao_de_obra.sequencia_arredondamento",
                "só a sequência [media, valor_hora, valor_mensal] é suportada (D-43)",
            )
        _sem_repetidos(self.regime_padrao, "mao_de_obra.regime_padrao")
        _sem_repetidos(self.plataformas, "mao_de_obra.plataformas")
        return self


class Desembolso(_Grupo):
    padrao: Literal["parcela_unica_mes_1", "conforme_cronograma"]


class Automacao(_Grupo):
    correspondencia_ean: NivelAutomacao
    correspondencia_atributos: NivelAutomacao
    ia_rebaixa_correspondencia: NivelAutomacao
    promover_amarelo_para_verde: NivelAutomacao
    escolher_lojas: NivelAutomacao
    resolver_item_acima_da_media: NivelAutomacao
    bloquear_cnpj_inativo: NivelAutomacao
    descartar_vaga_duplicada_clara: NivelAutomacao
    descartar_vaga_duplicada_incerta: NivelAutomacao
    sugerir_quantidade_horas_cargo: NivelAutomacao
    refazer_pesquisa_vencida: NivelAutomacao
    otimizar_teto: NivelAutomacao
    perfil_do_edital: NivelAutomacao
    aprovacao_final: NivelAutomacao

    @model_validator(mode="after")
    def checar_travas(self):
        # Travas dos princípios invioláveis: nenhuma camada pode mudar.
        sempre_manual = {
            "promover_amarelo_para_verde": "só uma pessoa promove 🟡 para 🟢 (princípio 4)",
            "perfil_do_edital": "cada regra sugerida a partir do edital é confirmada por uma pessoa",
            "aprovacao_final": "a aprovação final é sempre de uma pessoa",
        }
        for campo, motivo in sempre_manual.items():
            if getattr(self, campo) != "manual":
                raise _erro(f"automacao.{campo}", f"precisa ser manual: {motivo}")
        if self.resolver_item_acima_da_media == "automatico":
            raise _erro(
                "automacao.resolver_item_acima_da_media",
                "não pode ser automático: o usuário escolhe entre trocar produto ou loja (D-23)",
            )
        return self


class PerfilRegras(_Grupo):
    """Perfil completo, depois de somadas todas as camadas."""

    fontes: Fontes
    preco_referencia: PrecoReferencia
    produto: Produto
    evidencia: Evidencia
    cnpj: Cnpj
    calculo: Calculo
    teto: Teto
    otimizacao: Otimizacao
    mao_de_obra: MaoDeObra
    desembolso: Desembolso
    automacao: Automacao
