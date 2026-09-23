"""Otimização: fechar o teto do projeto exato ao centavo, mexendo só em quantidades e horas
(docs/03 §4). Sem acesso a rede ou banco."""

from orca.otimizacao.diagnostico import diagnosticar
from orca.otimizacao.modelo import (
    Alteracao,
    LimiteRubrica,
    LinhaMaoDeObra,
    LinhaMaterial,
    ProblemaTeto,
    RestricaoLote,
    SemSolucao,
    SolucaoTeto,
    Sugestao,
    faixa,
)
from orca.otimizacao.montagem import limites_das_regras, linha_de_cargo, linhas_do_lote
from orca.otimizacao.otimizar import VERSAO_OTIMIZADOR, fechar_teto
from orca.otimizacao.verificacao import verificar

__all__ = [
    "VERSAO_OTIMIZADOR",
    "Alteracao",
    "LimiteRubrica",
    "LinhaMaoDeObra",
    "LinhaMaterial",
    "ProblemaTeto",
    "RestricaoLote",
    "SemSolucao",
    "SolucaoTeto",
    "Sugestao",
    "diagnosticar",
    "faixa",
    "fechar_teto",
    "limites_das_regras",
    "linha_de_cargo",
    "linhas_do_lote",
    "verificar",
]
