"""Tarefas em segundo plano: fila, trabalhador e o que cada tipo de tarefa faz (docs/04 §3)."""

from orca.tarefas import alternativas, busca, executores  # noqa: F401 — registra os tipos de tarefa
from orca.tarefas.fila import EXECUTORES, PISTA_ASSISTIDA, Contexto, ErroTarefa, Fila, TarefaCancelada, tarefa

__all__ = ["EXECUTORES", "PISTA_ASSISTIDA", "Contexto", "ErroTarefa", "Fila", "TarefaCancelada", "tarefa"]
