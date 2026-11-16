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

from app.extensions import db


class Account(db.Model):
    __tablename__ = "accounts"
    __audited__ = True

    account_number = db.Column(db.String(6), primary_key=True)
    advertiser = db.Column(db.String(255), nullable=True)
    contact_name = db.Column(db.String(255), nullable=True)
    address1 = db.Column(db.String(255), nullable=True)
    address2 = db.Column(db.String(50), nullable=True)
    city = db.Column(db.String(50), nullable=True)
    state_code = db.Column(db.String(8), nullable=True)
    postal_code = db.Column(db.String(12), nullable=True)
    # Where invoices go, when it differs from the contact address above.
    billing_address1 = db.Column(db.String(255), nullable=True)
    billing_address2 = db.Column(db.String(50), nullable=True)
    billing_city = db.Column(db.String(50), nullable=True)
    billing_state_code = db.Column(db.String(8), nullable=True)
    billing_postal_code = db.Column(db.String(12), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    fax = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    website = db.Column(db.String(255), nullable=True)
    category = db.Column(db.String(255), nullable=True)
    ad_ops = db.Column(db.String(255), nullable=True)
    directory_years = db.Column(db.String(255), nullable=True)
    contact_notes = db.Column(db.Text, nullable=True)
    is_prospect = db.Column(db.Boolean, nullable=False, server_default=db.false())
    is_current_advertiser = db.Column(db.Boolean, nullable=False, server_default=db.false())
    is_past_advertiser = db.Column(db.Boolean, nullable=False, server_default=db.false())
    is_email_list = db.Column(db.Boolean, nullable=False, server_default=db.false())
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now(),
    )
    created_by = db.Column(db.String(255), nullable=True)
    updated_by = db.Column(db.String(255), nullable=True)

    ad_placements = db.relationship("AdPlacement", back_populates="account")


class AdPlacement(db.Model):
    __tablename__ = "ad_placements"
    __audited__ = True

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    legacy_account_number = db.Column(db.String(6), nullable=True)
    account_number = db.Column(db.String(6), db.ForeignKey("accounts.account_number"), nullable=True)
    commission_percent = db.Column(db.Numeric(7, 4), nullable=True)
    date_sold = db.Column(db.Date, nullable=True)
    date_run = db.Column(db.Date, nullable=True)
    description = db.Column(db.String(255), nullable=True)
    authorized_by = db.Column(db.String(50), nullable=True)
    sales_rep_raw = db.Column(db.String(50), nullable=True)
    amount = db.Column(db.Numeric(12, 2), nullable=True)
    size_raw = db.Column(db.String(50), nullable=True)
    section_raw = db.Column(db.String(50), nullable=True)
    ad_page = db.Column(db.String(50), nullable=True)
    run_code = db.Column(db.String(255), nullable=True)
    bill_number = db.Column(db.String(50), nullable=True)
    billed_raw = db.Column(db.String(50), nullable=True)
    ad_notes = db.Column(db.Text, nullable=True)
    source_row_hash = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now(),
    )
    created_by = db.Column(db.String(255), nullable=True)
    updated_by = db.Column(db.String(255), nullable=True)

    account = db.relationship("Account", back_populates="ad_placements")


class SalesRep(db.Model):
    __tablename__ = "sales_reps"
    __audited__ = True

    id = db.Column(db.SmallInteger, primary_key=True, autoincrement=True)
    code = db.Column(db.String(50), nullable=False, unique=True)
    display_name = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, server_default=db.true())


class AdSize(db.Model):
    __tablename__ = "ad_sizes"
    __audited__ = True

    id = db.Column(db.SmallInteger, primary_key=True, autoincrement=True)
    code = db.Column(db.String(50), nullable=False, unique=True)
    normalized_label = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, server_default=db.true())


class AdSection(db.Model):
    __tablename__ = "ad_sections"
    __audited__ = True

    id = db.Column(db.SmallInteger, primary_key=True, autoincrement=True)
    code = db.Column(db.String(50), nullable=False, unique=True)
    normalized_label = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, server_default=db.true())


class BillingStatus(db.Model):
    __tablename__ = "billing_statuses"
    __audited__ = True

    id = db.Column(db.SmallInteger, primary_key=True, autoincrement=True)
    code = db.Column(db.String(50), nullable=False, unique=True)
    normalized_label = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, server_default=db.true())


class AdNormalizationMap(db.Model):
    __tablename__ = "ad_normalization_map"
    __audited__ = True

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    domain = db.Column(db.Enum("size", "section", "sales", "billed", name="normalization_domain"), nullable=False)
    raw_value = db.Column(db.String(255), nullable=False)
    normalized_value = db.Column(db.String(255), nullable=False)
    notes = db.Column(db.String(255), nullable=True)
    approved_by = db.Column(db.String(100), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint("domain", "raw_value", name="uq_ad_normalization_map_domain_raw"),
    )
