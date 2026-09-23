"""Catálogos e pares da OSC (etapa 9.4; D-64 a D-66).

Revisão: 0004
Anterior: 0003
Criada em: 2026-09-24

Lembrete: operações em modo batch recriam a tabela e perdem os gatilhos.
Depois delas, chame orca.banco.gatilhos.criar_gatilhos(op.execute, tabela, imutavel).
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

from orca.banco.gatilhos import criar_gatilhos


revision: str = '0004'
down_revision: str | Sequence[str] | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('catalogo_camada',
    sa.Column('organizacao_id', sa.String(length=32), nullable=False),
    sa.Column('tipo', sa.String(length=20), nullable=False),
    sa.Column('versao', sa.Integer(), nullable=False),
    sa.Column('conteudo', sa.JSON(), nullable=False),
    sa.Column('impressao', sa.String(length=64), nullable=False),
    sa.Column('resumo', sa.Text(), nullable=True),
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('criado_em', sa.String(length=40), nullable=False),
    sa.Column('autor', sa.String(length=120), nullable=False),
    sa.CheckConstraint("tipo IN ('atributos', 'lojas')", name=op.f('ck_catalogo_camada_tipo')),
    sa.CheckConstraint('versao >= 1', name=op.f('ck_catalogo_camada_versao')),
    sa.ForeignKeyConstraint(['organizacao_id'], ['organizacao.id'], name=op.f('fk_catalogo_camada_organizacao_id_organizacao')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_catalogo_camada')),
    sa.UniqueConstraint('organizacao_id', 'tipo', 'versao', name=op.f('uq_catalogo_camada_organizacao_id_tipo_versao'))
    )
    with op.batch_alter_table('catalogo_camada', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_catalogo_camada_organizacao_id'), ['organizacao_id'], unique=False)

    op.create_table('par_referencia',
    sa.Column('organizacao_id', sa.String(length=32), nullable=False),
    sa.Column('categoria', sa.String(length=50), nullable=True),
    sa.Column('titulo_a', sa.Text(), nullable=False),
    sa.Column('marca_a', sa.String(length=120), nullable=True),
    sa.Column('ean_a', sa.String(length=14), nullable=True),
    sa.Column('titulo_b', sa.Text(), nullable=False),
    sa.Column('marca_b', sa.String(length=120), nullable=True),
    sa.Column('ean_b', sa.String(length=14), nullable=True),
    sa.Column('rotulo', sa.String(length=10), nullable=False),
    sa.Column('motivo', sa.Text(), nullable=True),
    sa.Column('origem', sa.String(length=10), nullable=False),
    sa.Column('chave', sa.String(length=80), nullable=True),
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('criado_em', sa.String(length=40), nullable=False),
    sa.Column('excluido_em', sa.String(length=40), nullable=True),
    sa.CheckConstraint("origem IN ('decisao', 'ean', 'usuario')", name=op.f('ck_par_referencia_origem')),
    sa.CheckConstraint("rotulo IN ('mesmo', 'diferente')", name=op.f('ck_par_referencia_rotulo')),
    sa.ForeignKeyConstraint(['organizacao_id'], ['organizacao.id'], name=op.f('fk_par_referencia_organizacao_id_organizacao')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_par_referencia')),
    sa.UniqueConstraint('chave', name=op.f('uq_par_referencia_chave'))
    )
    with op.batch_alter_table('par_referencia', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_par_referencia_organizacao_id'), ['organizacao_id'], unique=False)

    criar_gatilhos(op.execute, "catalogo_camada", imutavel=True)
    criar_gatilhos(op.execute, "par_referencia", imutavel=False)


def downgrade() -> None:
    raise NotImplementedError("O Orça.AI não desfaz migrações; restaure a cópia de segurança.")
