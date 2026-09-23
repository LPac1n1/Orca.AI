"""Base das tabelas: identificadores, data/hora em UTC e convenções de nomes."""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import MetaData, String
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

CONVENCAO_NOMES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCAO_NOMES)


def novo_id() -> str:
    """Identificador gerado no programa (UUID), já conhecido antes de gravar."""
    return uuid.uuid4().hex


def agora() -> datetime:
    return datetime.now(UTC)


class DataHora(TypeDecorator):
    """Data e hora sempre com fuso, gravada como texto ISO 8601 em UTC."""

    impl = String(40)
    cache_ok = True

    def process_bind_param(self, valor: datetime | None, dialect) -> str | None:
        if valor is None:
            return None
        if not isinstance(valor, datetime) or valor.tzinfo is None:
            raise ValueError("Data/hora precisa ter fuso horário (use datetime com tzinfo)")
        return valor.astimezone(UTC).isoformat(timespec="microseconds")

    def process_result_value(self, valor: str | None, dialect) -> datetime | None:
        return None if valor is None else datetime.fromisoformat(valor)


class Data(TypeDecorator):
    """Data (sem hora), gravada como texto AAAA-MM-DD."""

    impl = String(10)
    cache_ok = True

    def process_bind_param(self, valor: date | None, dialect) -> str | None:
        if valor is None:
            return None
        if isinstance(valor, datetime) or not isinstance(valor, date):
            raise ValueError("Use um objeto date (sem hora)")
        return valor.isoformat()

    def process_result_value(self, valor: str | None, dialect) -> date | None:
        return None if valor is None else date.fromisoformat(valor)
