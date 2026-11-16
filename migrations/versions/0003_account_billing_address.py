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

"""Accounts: separate billing address

Revision ID: 0003_account_billing_address
Revises: 0002_audit_trail
Create Date: 2026-11-16
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_account_billing_address"
down_revision = "0002_audit_trail"
branch_labels = None
depends_on = None

# Same sizes as the contact address columns.
COLUMNS = (
    ("billing_address1", 255),
    ("billing_address2", 50),
    ("billing_city", 50),
    ("billing_state_code", 8),
    ("billing_postal_code", 12),
)


def upgrade():
    for name, length in COLUMNS:
        op.add_column("accounts", sa.Column(name, sa.String(length=length), nullable=True))


def downgrade():
    for name, _length in reversed(COLUMNS):
        op.drop_column("accounts", name)
