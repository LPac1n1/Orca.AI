"""${message}

Revisão: ${up_revision}
Anterior: ${down_revision | comma,n}
Criada em: ${create_date}

Lembrete: operações em modo batch recriam a tabela e perdem os gatilhos.
Depois delas, chame orca.banco.gatilhos.criar_gatilhos(op.execute, tabela, imutavel).
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | Sequence[str] | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    raise NotImplementedError("O Orça.AI não desfaz migrações; restaure a cópia de segurança.")
