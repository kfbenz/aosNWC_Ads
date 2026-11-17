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

"""Accounts: billing contact name

Revision ID: 0004_account_billing_name
Revises: 0003_account_billing_address
Create Date: 2026-11-16
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_account_billing_name"
down_revision = "0003_account_billing_address"
branch_labels = None
depends_on = None


def upgrade():
    # Same size as contact_name.
    op.add_column("accounts", sa.Column("billing_name", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("accounts", "billing_name")
