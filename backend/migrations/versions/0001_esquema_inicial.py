"""Esquema inicial: secciones, metadatos del cuaderno y ejecuciones.

Revision ID: 0001
Revises:
Create Date: 2026-10-15 23:01:34.612160

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Identificadores de la revisión, usados por Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea las tres tablas."""
    op.create_table(
        "cuaderno",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("intro", sa.Text(), nullable=False),
        sa.Column("preludio", sa.Text(), nullable=False),
        sa.Column("resumen", sa.JSON(), nullable=False),
        sa.Column("nota_final", sa.Text(), nullable=False),
        sa.Column("fuentes", sa.JSON(), nullable=False),
        sa.Column("hash_contenido", sa.String(length=64), nullable=False),
        sa.Column(
            "creada_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "actualizada_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "seccion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(length=300), nullable=False),
        sa.Column("explicacion", sa.Text(), nullable=False),
        sa.Column("referencia", sa.Text(), nullable=False),
        sa.Column("imperativo", sa.Text(), nullable=False),
        sa.Column("declarativo", sa.Text(), nullable=False),
        sa.Column("epilogo", sa.Text(), nullable=False),
        sa.Column("fuente", sa.Text(), nullable=False),
        sa.Column("hash_contenido", sa.String(length=64), nullable=False),
        sa.Column(
            "creada_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "actualizada_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_seccion_numero"), "seccion", ["numero"], unique=True)
    op.create_table(
        "ejecucion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("seccion_id", sa.Integer(), nullable=True),
        sa.Column("salida", sa.Text(), nullable=False),
        sa.Column("codigo_salida", sa.Integer(), nullable=True),
        sa.Column("duracion_ms", sa.Integer(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column(
            "creada_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["seccion_id"], ["seccion.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ejecucion_creada_en"), "ejecucion", ["creada_en"], unique=False)
    op.create_index(op.f("ix_ejecucion_seccion_id"), "ejecucion", ["seccion_id"], unique=False)


def downgrade() -> None:
    """Elimina las tres tablas."""
    op.drop_index(op.f("ix_ejecucion_seccion_id"), table_name="ejecucion")
    op.drop_index(op.f("ix_ejecucion_creada_en"), table_name="ejecucion")
    op.drop_table("ejecucion")
    op.drop_index(op.f("ix_seccion_numero"), table_name="seccion")
    op.drop_table("seccion")
    op.drop_table("cuaderno")
