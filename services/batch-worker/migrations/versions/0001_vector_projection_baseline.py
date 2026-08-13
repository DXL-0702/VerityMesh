"""Create the rebuildable pgvector serving projection baseline."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR

revision: str = "0001_vector_projection"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "projection_builds",
        sa.Column("id", sa.String(length=256), primary_key=True),
        sa.Column("knowledge_release_id", sa.String(length=256), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding_space", sa.String(length=256), nullable=False),
        sa.Column("embedding_model_revision", sa.String(length=256), nullable=False),
        sa.Column("projection_schema_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "knowledge_release_id",
            "manifest_hash",
            name="uq_projection_build_release_manifest",
        ),
    )
    op.create_table(
        "vector_projection_chunks",
        sa.Column("id", sa.String(length=256), primary_key=True),
        sa.Column("projection_build_id", sa.String(length=256), nullable=False),
        sa.Column("project_id", sa.String(length=256), nullable=False),
        sa.Column("knowledge_release_id", sa.String(length=256), nullable=False),
        sa.Column("source_revision_id", sa.String(length=256), nullable=False),
        sa.Column("chunk_id", sa.String(length=256), nullable=False),
        sa.Column("locale", sa.String(length=64), nullable=False),
        sa.Column("access_segment", sa.String(length=64), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("embedding_space", sa.String(length=256), nullable=False),
        sa.Column("embedding_model_revision", sa.String(length=256), nullable=False),
        sa.Column("embedding", VECTOR(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["projection_build_id"],
            ["projection_builds.id"],
            name="fk_vector_chunks_projection_build",
        ),
        sa.UniqueConstraint(
            "knowledge_release_id",
            "chunk_id",
            name="uq_vector_chunks_release_chunk",
        ),
    )
    op.create_index(
        "ix_vector_chunks_filter",
        "vector_projection_chunks",
        ["project_id", "knowledge_release_id", "locale", "access_segment", "revoked_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_vector_chunks_filter", table_name="vector_projection_chunks")
    op.drop_table("vector_projection_chunks")
    op.drop_table("projection_builds")
