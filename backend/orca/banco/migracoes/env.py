"""Ambiente do Alembic. Usa a conexão recebida do programa (orca.banco.atualizar_banco)
ou a URL do alembic.ini (desenvolvimento)."""

from alembic import context
from sqlalchemy import engine_from_config, pool

import orca.banco.tabelas  # noqa: F401 — registra as tabelas
from orca.banco.base import Base

config = context.config
alvo = Base.metadata


def _configurar(conexao) -> None:
    context.configure(
        connection=conexao,
        target_metadata=alvo,
        render_as_batch=True,  # SQLite não altera colunas sem recriar a tabela
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


conexao = config.attributes.get("connection")
if conexao is not None:
    _configurar(conexao)
else:
    engine = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as conexao_nova:
        _configurar(conexao_nova)
