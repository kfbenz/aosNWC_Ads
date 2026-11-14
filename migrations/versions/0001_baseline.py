# Copyright 2026 Archdiocese of Seattle
# Author: Kevin F Benz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
    # Drop "--" comment lines first: the license header contains a semicolon,
    # and a comment-only fragment would be rejected by MariaDB as an empty query.
    script = "\n".join(
        line for line in SCHEMA_SQL.read_text(encoding="utf-8-sig").splitlines()
        if not line.lstrip().startswith("--")
    )
    for statement in script.split(";"):
        if statement.strip():
            op.execute(sa.text(statement))


def downgrade():
    # Never drop the core business tables from a migration.
    raise RuntimeError("The baseline migration cannot be downgraded.")
