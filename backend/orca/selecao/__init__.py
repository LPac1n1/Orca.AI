"""Seleção: lojas completas, classificação, trio, grade, conferência preço × média,
resolução do item acima da média, escolha das vagas e conferência de grade pronta.

Sem acesso a rede ou banco (docs/04 §3).
"""

from orca.selecao.grade import Divergencia, LinhaInformada, conferir_grade
from orca.selecao.lojas import analisar_lote, classificar, motivos_inelegivel, total_da_loja
from orca.selecao.modelos import (
    AnaliseLote,
    ItemLote,
    LinhaGrade,
    Loja,
    LojaClassificada,
    Oferta,
    ParametrosSelecao,
    SemTrio,
    Violacao,
)
from orca.selecao.resolucao import (
    Alternativa,
    OpcaoTrocaProduto,
    ResultadoTrocaLoja,
    TentativaTrocaLoja,
    trocar_loja,
    trocar_produto,
)
from orca.selecao.vagas import SelecaoVagas, Vaga, selecionar_vagas

__all__ = [
    "Alternativa",
    "AnaliseLote",
    "Divergencia",
    "ItemLote",
    "LinhaGrade",
    "LinhaInformada",
    "Loja",
    "LojaClassificada",
    "Oferta",
    "OpcaoTrocaProduto",
    "ParametrosSelecao",
    "ResultadoTrocaLoja",
    "SelecaoVagas",
    "SemTrio",
    "TentativaTrocaLoja",
    "Vaga",
    "Violacao",
    "analisar_lote",
    "classificar",
    "conferir_grade",
    "motivos_inelegivel",
    "selecionar_vagas",
    "total_da_loja",
    "trocar_loja",
    "trocar_produto",
]
