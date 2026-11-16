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

"""Forms for accounts and ads.

Field order and labels follow the Access forms (docs/access_application_spec.md,
sections 3.1 and 3.2) so staff see familiar screens.
"""
from __future__ import annotations

from datetime import date

from flask_wtf import FlaskForm
from wtforms import BooleanField, DateField, DecimalField, HiddenField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, Regexp, ValidationError


def blank_to_none(value):
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def realistic_date(_form, field):
    """Catch typos such as 0112 or 3006 that exist in the legacy data."""
    if field.data and not (date(1990, 1, 1) <= field.data <= date(2100, 12, 31)):
        raise ValidationError("Enter a date between 1990 and 2100.")


def _text(label, max_len, *extra, **kwargs):
    return StringField(label, filters=[blank_to_none], validators=[Optional(), Length(max=max_len), *extra], **kwargs)


def _area(label):
    return TextAreaField(label, filters=[blank_to_none], validators=[Optional(), Length(max=20000)])


class AccountForm(FlaskForm):
    # Used for optimistic locking: the updated_at value the user started from.
    version = HiddenField()

    account_number = StringField(
        "Account",
        filters=[lambda v: v.strip().upper() if isinstance(v, str) else v],
        validators=[
            DataRequired(),
            Length(max=6),
            Regexp(r"^[A-Z0-9]+$", message="Use letters and digits only, up to 6 characters."),
        ],
    )
    advertiser = StringField(
        "Advertiser", filters=[blank_to_none], validators=[DataRequired(), Length(max=255)]
    )
    contact_name = _text("Contact", 255)
    address1 = _text("Address", 255)
    address2 = _text("Address 2", 50)
    city = _text("City", 50)
    state_code = _text("State", 8)
    postal_code = _text("Zip", 12)
    phone = _text("Phone", 50)
    fax = _text("Fax", 50)
    email = _text("E-mail", 255)
    website = _text("Web site", 255)
    directory_years = _text("Directory Years", 255)

    billing_address1 = _text("Address", 255)
    billing_address2 = _text("Address 2", 50)
    billing_city = _text("City", 50)
    billing_state_code = _text("State", 8)
    billing_postal_code = _text("Zip", 12)

    category = _text("Category", 255)
    ad_ops = _area("Special Advertising Opportunities")
    contact_notes = _area("Notes")
    is_current_advertiser = BooleanField("Current Advertiser")
    is_past_advertiser = BooleanField("Past Advertiser")
    is_email_list = BooleanField("E-mail List")
    is_prospect = BooleanField("Prospect")

    LEFT_FIELDS = (
        "account_number", "advertiser", "contact_name", "address1", "address2", "city",
        "state_code", "postal_code", "phone", "fax", "email", "website", "directory_years",
    )
    BILLING_FIELDS = (
        "billing_address1", "billing_address2", "billing_city", "billing_state_code", "billing_postal_code",
    )
    RIGHT_FIELDS = ("category", "ad_ops", "contact_notes")
    FLAG_FIELDS = ("is_current_advertiser", "is_past_advertiser", "is_email_list", "is_prospect")
    MODEL_FIELDS = LEFT_FIELDS + BILLING_FIELDS + RIGHT_FIELDS + FLAG_FIELDS


class AdForm(FlaskForm):
    version = HiddenField()

    # Entered as a percentage (10 = 10%); stored as a fraction (0.10), as in Access.
    commission_pct = DecimalField(
        "Comm %",
        places=2,
        # "%%" because WTForms applies %-formatting to NumberRange messages.
        validators=[Optional(), NumberRange(min=0, max=100, message="Enter 0 to 100 (for example 10 for 10%%).")],
    )
    date_sold = DateField("Date Sold", validators=[Optional(), realistic_date])
    date_run = DateField("Date Run", validators=[Optional(), realistic_date])
    description = _text("Desc", 255)
    authorized_by = _text("Auth By", 50)
    sales_rep_raw = _text("Sales", 50)
    size_raw = _text("Size", 50)
    section_raw = _text("Section", 50)
    ad_page = _text("Page", 50)
    ad_notes = _area("Notes")
    run_code = _text("Run #", 255)
    bill_number = _text("Bill #", 50)
    amount = DecimalField(
        "Amount",
        places=2,
        validators=[Optional(), NumberRange(min=-1_000_000, max=1_000_000)],
    )

    MODEL_FIELDS = (
        "date_sold", "date_run", "description", "authorized_by", "sales_rep_raw", "size_raw",
        "section_raw", "ad_page", "ad_notes", "run_code", "bill_number", "amount",
    )
