"""Fila de tarefas (etapa 9.2).

Revisão: 0003
Anterior: 0002
Criada em: 2026-09-24

Lembrete: operações em modo batch recriam a tabela e perdem os gatilhos.
Depois delas, chame orca.banco.gatilhos.criar_gatilhos(op.execute, tabela, imutavel).
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

from orca.banco.gatilhos import criar_gatilhos


revision: str = '0003'
down_revision: str | Sequence[str] | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('tarefa',
    sa.Column('projeto_id', sa.String(length=32), nullable=True),
    sa.Column('tipo', sa.String(length=40), nullable=False),
    sa.Column('estado', sa.String(length=20), nullable=False),
    sa.Column('progresso', sa.Integer(), nullable=False),
    sa.Column('mensagem', sa.Text(), nullable=True),
    sa.Column('parametros', sa.JSON(), nullable=False),
    sa.Column('resultado', sa.JSON(), nullable=True),
    sa.Column('iniciada_em', sa.String(length=40), nullable=True),
    sa.Column('concluida_em', sa.String(length=40), nullable=True),
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('criado_em', sa.String(length=40), nullable=False),
    sa.Column('autor', sa.String(length=120), nullable=False),
    sa.CheckConstraint("estado IN ('pendente', 'rodando', 'esperando_usuario', 'concluida', 'falhou', 'cancelada')",
                       name=op.f('ck_tarefa_estado')),
    sa.CheckConstraint('progresso BETWEEN 0 AND 100', name=op.f('ck_tarefa_progresso')),
    sa.ForeignKeyConstraint(['projeto_id'], ['projeto.id'], name=op.f('fk_tarefa_projeto_id_projeto')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_tarefa'))
    )
    with op.batch_alter_table('tarefa', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tarefa_projeto_id'), ['projeto_id'], unique=False)

    # Tabela viva (o andamento muda), mas nunca apagada (princípio 6).
    criar_gatilhos(op.execute, "tarefa", imutavel=False)


def downgrade() -> None:
    raise NotImplementedError("O Orça.AI não desfaz migrações; restaure a cópia de segurança.")
