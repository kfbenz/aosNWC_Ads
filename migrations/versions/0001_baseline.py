"""Baseline: core schema from sql/001_target_schema.sql

Uses CREATE TABLE IF NOT EXISTS, so it is a no-op on databases that were
already built with the SQL script and the Access import, and creates the
schema on a fresh database.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-13
"""
from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA_SQL = Path(__file__).resolve().parents[2] / "sql" / "001_target_schema.sql"


def upgrade():
    script = SCHEMA_SQL.read_text(encoding="utf-8")
    for statement in script.split(";"):
        if statement.strip():
            op.execute(sa.text(statement))


def downgrade():
    # Never drop the core business tables from a migration.
    raise RuntimeError("The baseline migration cannot be downgraded.")
