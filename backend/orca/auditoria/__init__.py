"""Auditoria: histórico automático de toda gravação e consultas ao histórico.

Importar este pacote ativa o registro automático de eventos.
"""

from orca.auditoria.eventos import ErroAuditoria
from orca.auditoria.historico import historico, historico_do_projeto

__all__ = ["ErroAuditoria", "historico", "historico_do_projeto"]
