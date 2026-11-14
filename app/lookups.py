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

"""Lookup lists (sales reps, sizes, sections, billing statuses) and exact-text helpers.

Each list's `code` is the exact text stored on the ad (for example size_raw = "1/4 pg").
When a list has active entries, the ad form offers it as a dropdown; values on
older ads that are not on the list are kept and shown as "(legacy)".
"""
from __future__ import annotations

from sqlalchemy import func, select

from app.extensions import db
from app.target_models import AdPlacement, AdSection, AdSize, BillingStatus, SalesRep


LOOKUPS = {
    "sales": {
        "title": "Sales reps", "singular": "sales rep", "model": SalesRep, "label_attr": "display_name",
        "label_title": "Full name", "ad_attr": "sales_rep_raw", "field_label": "Sales",
    },
    "size": {
        "title": "Sizes", "singular": "size", "model": AdSize, "label_attr": "normalized_label",
        "label_title": "Description", "ad_attr": "size_raw", "field_label": "Size",
    },
    "section": {
        "title": "Sections", "singular": "section", "model": AdSection, "label_attr": "normalized_label",
        "label_title": "Description", "ad_attr": "section_raw", "field_label": "Section",
    },
    "billed": {
        "title": "Billing statuses", "singular": "billing status", "model": BillingStatus,
        "label_attr": "normalized_label", "label_title": "Description", "ad_attr": "billed_raw",
        "field_label": "Billed",
    },
}

# Ad form fields that switch to a dropdown when their list has active entries.
FORM_FIELD_KIND = {"sales_rep_raw": "sales", "size_raw": "size", "section_raw": "section"}
CODE_MAX = 50


def ad_column(kind: str):
    return getattr(AdPlacement, LOOKUPS[kind]["ad_attr"])


def exact(column):
    """Compare text exactly. MariaDB's default collation ignores case ("KH" = "kh"),
    which would hide spelling variants; SQLite compares exactly already."""
    if db.engine.dialect.name in ("mysql", "mariadb"):
        return column.collate("utf8mb4_bin")
    return column


def entries(kind: str, active_only: bool = False) -> list:
    model = LOOKUPS[kind]["model"]
    stmt = select(model).order_by(func.lower(model.code))
    if active_only:
        stmt = stmt.where(model.is_active.is_(True))
    return db.session.scalars(stmt).all()


def label_of(kind: str, entry) -> str | None:
    return getattr(entry, LOOKUPS[kind]["label_attr"])


def find_code(kind: str, code: str):
    """Existing entry with this code, ignoring case (codes must be unique regardless of case)."""
    model = LOOKUPS[kind]["model"]
    return db.session.scalars(select(model).where(func.lower(model.code) == code.lower())).first()


def usage(kind: str) -> list[tuple[str, int]]:
    """(exact value, number of ads) for every value in use, most used first."""
    col = exact(ad_column(kind))
    return db.session.execute(
        select(col.label("value"), func.count(AdPlacement.id).label("n"))
        .where(ad_column(kind).is_not(None))
        .group_by(col)
        .order_by(func.count(AdPlacement.id).desc(), col)
    ).all()


def dropdown_choices(kind: str, current: str | None = None) -> list[tuple[str, str]] | None:
    """(value, text) options for the ad form, or None when the list is still empty."""
    active = entries(kind, active_only=True)
    if not active:
        return None
    options = [("", "")]
    codes = set()
    for e in active:
        label = label_of(kind, e)
        options.append((e.code, f"{e.code} - {label}" if label and label != e.code else e.code))
        codes.add(e.code)
    if current and current not in codes:
        options.insert(1, (current, f"{current} (legacy, not on the list)"))
    return options
