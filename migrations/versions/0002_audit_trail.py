"""Audit trail: audit_log table and created_by/updated_by columns

Revision ID: 0002_audit_trail
Revises: 0001_baseline
Create Date: 2026-11-13
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_audit_trail"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

AUDITED_TABLES = ("accounts", "ad_placements")


def upgrade():
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("occurred_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("user_oid", sa.String(length=64), nullable=True),
        sa.Column("user_name", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column("entity", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("changes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_occurred_at", "audit_log", ["occurred_at"])
    op.create_index("ix_audit_log_entity", "audit_log", ["entity", "entity_id"])

    for table in AUDITED_TABLES:
        op.add_column(table, sa.Column("created_by", sa.String(length=255), nullable=True))
        op.add_column(table, sa.Column("updated_by", sa.String(length=255), nullable=True))


def downgrade():
    for table in AUDITED_TABLES:
        op.drop_column(table, "updated_by")
        op.drop_column(table, "created_by")

    op.drop_index("ix_audit_log_entity", table_name="audit_log")
    op.drop_index("ix_audit_log_occurred_at", table_name="audit_log")
    op.drop_table("audit_log")
