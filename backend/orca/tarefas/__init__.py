"""Tarefas em segundo plano: fila, trabalhador e o que cada tipo de tarefa faz (docs/04 §3)."""

from orca.tarefas import executores  # noqa: F401 — registra os tipos de tarefa
from orca.tarefas.fila import EXECUTORES, Contexto, ErroTarefa, Fila, tarefa

__all__ = ["EXECUTORES", "Contexto", "ErroTarefa", "Fila", "tarefa"]
