"""Consulta ao histórico de alterações."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from orca.banco.tabelas import Evento


def historico(sessao: Session, entidade: str, entidade_id: str) -> list[Evento]:
    """Todos os eventos de um registro, do mais antigo ao mais novo."""
    consulta = select(Evento).where(Evento.entidade == entidade, Evento.entidade_id == entidade_id)
    return list(sessao.scalars(consulta.order_by(Evento.id)))


def historico_do_projeto(sessao: Session, projeto_id: str) -> list[Evento]:
    """Todos os eventos ligados a um projeto (o projeto, suas rubricas, lotes, itens, cargos…)."""
    consulta = select(Evento).where(Evento.projeto_id == projeto_id)
    return list(sessao.scalars(consulta.order_by(Evento.id)))
