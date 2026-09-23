"""Documentos: planilhas Excel com fórmulas, PDFs e o pacote ZIP com manifesto (docs/02 §18).

Tudo sai do dossiê (`Dossie`), montado a partir da seleção, do cálculo e da otimização.
"""

from orca.documentos.conformidade import ATENCAO, OK, PROBLEMA, Conferencia, conferir, resumo_da_conformidade
from orca.documentos.modelo import (
    AlteracaoDoc,
    ArquivoRef,
    CargoDoc,
    Dossie,
    Empresa,
    EventoDoc,
    EvidenciaDoc,
    FonteItem,
    LinhaCotacao,
    LojaDoLote,
    LoteDoc,
    OrcamentoDoc,
    OtimizacaoDoc,
    ProjetoDoc,
    VagaDoc,
)
from orca.documentos.montagem import cargo_doc, lote_doc, otimizacao_doc
from orca.documentos.pacote import gerar_pacote, manifesto, montar_arquivos, nome_de_arquivo, salvar_pacote
from orca.documentos.pdf import Renderizador, juntar_pdfs
from orca.documentos.planilhas import grade_comparativa, plano_de_aplicacao

__all__ = [
    "ATENCAO",
    "OK",
    "PROBLEMA",
    "AlteracaoDoc",
    "ArquivoRef",
    "CargoDoc",
    "Conferencia",
    "Dossie",
    "Empresa",
    "EventoDoc",
    "EvidenciaDoc",
    "FonteItem",
    "LinhaCotacao",
    "LojaDoLote",
    "LoteDoc",
    "OrcamentoDoc",
    "OtimizacaoDoc",
    "ProjetoDoc",
    "Renderizador",
    "VagaDoc",
    "cargo_doc",
    "conferir",
    "gerar_pacote",
    "grade_comparativa",
    "juntar_pdfs",
    "lote_doc",
    "manifesto",
    "montar_arquivos",
    "nome_de_arquivo",
    "otimizacao_doc",
    "plano_de_aplicacao",
    "resumo_da_conformidade",
    "salvar_pacote",
]
