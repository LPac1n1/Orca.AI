"""Conexão com o banco local (SQLite), migrações, cópia de segurança e sessões com autor."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import orca.auditoria  # noqa: F401 — ativa o registro automático de eventos
from orca.dominio import Autor

PASTA_MIGRACOES = Path(__file__).parent / "migracoes"


def criar_engine(caminho: Path | str) -> Engine:
    """Engine do SQLite com chaves estrangeiras ligadas e modo WAL."""
    engine = create_engine(f"sqlite:///{Path(caminho).as_posix()}")

    @event.listens_for(engine, "connect")
    def _configurar(conexao_dbapi, _registro):
        cursor = conexao_dbapi.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA busy_timeout = 5000")
        cursor.close()

    return engine


def configuracao_alembic() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(PASTA_MIGRACOES))
    return cfg


def revisao_atual(engine: Engine) -> str | None:
    with engine.connect() as conexao:
        return MigrationContext.configure(conexao).get_current_revision()


def revisao_mais_nova() -> str:
    return ScriptDirectory.from_config(configuracao_alembic()).get_current_head()


def copiar_banco(engine: Engine, destino: Path) -> Path:
    """Cópia consistente do banco (API de backup do SQLite, segura com WAL)."""
    destino = Path(destino)
    conexao = engine.raw_connection()
    try:
        with sqlite3.connect(destino) as copia:
            conexao.driver_connection.backup(copia)
    finally:
        conexao.close()
    return destino


def atualizar_banco(engine: Engine, copiar_antes: bool = True) -> str:
    """Aplica as migrações pendentes. Faz cópia de segurança antes, se o banco já existia (docs/04 §4)."""
    atual, nova = revisao_atual(engine), revisao_mais_nova()
    if atual == nova:
        return nova
    if atual is not None and copiar_antes and engine.url.database:
        carimbo = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        copiar_banco(engine, Path(f"{engine.url.database}.copia-{atual}-{carimbo}"))
    cfg = configuracao_alembic()
    with engine.begin() as conexao:
        cfg.attributes["connection"] = conexao
        command.upgrade(cfg, "head")
    return nova


def abrir_banco(caminho: Path | str) -> sessionmaker[Session]:
    """Abre (ou cria) o banco, aplica as migrações e devolve a fábrica de sessões."""
    engine = criar_engine(caminho)
    atualizar_banco(engine)
    return sessionmaker(engine, expire_on_commit=False)


@contextmanager
def sessao_como(fabrica: sessionmaker[Session], autor: str | Autor) -> Iterator[Session]:
    """Sessão que grava em nome de `autor`; confirma no fim ou desfaz em caso de erro."""
    sessao = fabrica()
    sessao.info["autor"] = str(Autor(str(autor)))
    try:
        yield sessao
        sessao.commit()
    except BaseException:
        sessao.rollback()
        raise
    finally:
        sessao.close()
