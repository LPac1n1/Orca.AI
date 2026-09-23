"""Fluxo do orçamento: liga as etapas a partir do banco (docs/02 §1).

Lê itens, observações, correspondências, consultas de CNPJ e decisões; roda a
seleção, as vagas, a mão de obra e a otimização; monta o painel e o dossiê.
"""

from orca.fluxo.acoes import (
    ErroAcao,
    corresponder_pendentes,
    devolver_loja,
    marcar_mesma_vaga,
    retirar_loja,
    simular_troca_de_loja,
    substituir_item,
)
from orca.fluxo.dossie import ErroDossie, dossie_do_projeto, evidencia_doc, versao_do_sistema
from orca.fluxo.estado import (
    EstadoCargo,
    EstadoLote,
    EstadoOrcamento,
    EstadoProjeto,
    estado_do_projeto,
    id_da_loja,
    lojas_retiradas,
    meses_ativos,
)
from orca.fluxo.painel import AMARELO, VERDE, VERMELHO, Painel, StatusLinha, painel
from orca.fluxo.teto import ProblemaMontado, execucao_vigente, fechar_teto_do_projeto, montar_problema

__all__ = [
    "AMARELO",
    "VERDE",
    "VERMELHO",
    "ErroAcao",
    "ErroDossie",
    "EstadoCargo",
    "EstadoLote",
    "EstadoOrcamento",
    "EstadoProjeto",
    "Painel",
    "ProblemaMontado",
    "StatusLinha",
    "corresponder_pendentes",
    "devolver_loja",
    "dossie_do_projeto",
    "estado_do_projeto",
    "evidencia_doc",
    "execucao_vigente",
    "fechar_teto_do_projeto",
    "id_da_loja",
    "lojas_retiradas",
    "marcar_mesma_vaga",
    "meses_ativos",
    "montar_problema",
    "painel",
    "retirar_loja",
    "simular_troca_de_loja",
    "substituir_item",
    "versao_do_sistema",
]
