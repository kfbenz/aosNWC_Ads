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

"""Advanced search: replaces the Access form "Search Contacts and Ads" (frm_ProgressSearch_01).

Semantics follow Access (docs/access_application_spec.md section 4): criteria are
evaluated against accounts LEFT JOIN ads, combined with OR or AND, and the result
is the distinct matching accounts. With AND, ad criteria must match the same ad.
Unlike Access, every field works, plain text matches anywhere in the field, and
the status checkboxes always narrow the results.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, Response, render_template, request
from sqlalchemy import and_, func, or_, select

from app.extensions import db
from app.labels import account_label_lines, build_labels_pdf
from app.reports import _parse_date
from app.spreadsheets import csv_response, xlsx_response
from app.target_models import Account, AdPlacement


search_bp = Blueprint("search", __name__, url_prefix="/search")

PER_PAGE = 50
ESCAPE = "/"

# (form name, label, column), in the Access layout order.
CONTACT_FIELDS = [
    ("account_number", "Number", Account.account_number),
    ("advertiser", "Advertiser", Account.advertiser),
    ("contact_name", "Contact", Account.contact_name),
    ("address1", "Address", Account.address1),
    ("address2", "Address 2", Account.address2),
    ("city", "City", Account.city),
    ("state_code", "State", Account.state_code),
    ("postal_code", "Zip", Account.postal_code),
    ("phone", "Phone", Account.phone),
    ("fax", "Fax", Account.fax),
    ("email", "E-mail", Account.email),
    ("website", "Web site", Account.website),
    ("directory_years", "Directory Years", Account.directory_years),
]
CLIENT_FIELDS = [
    ("category", "Category", Account.category),
    ("ad_ops", "Special Advertising Opportunities", Account.ad_ops),
    ("contact_notes", "Notes", Account.contact_notes),
]
AD_FIELDS = [
    ("description", "Description", AdPlacement.description),
    ("authorized_by", "Authorized By", AdPlacement.authorized_by),
    ("sales", "Sales", AdPlacement.sales_rep_raw),
    ("size", "Size", AdPlacement.size_raw),
    ("section", "Section", AdPlacement.section_raw),
    ("ad_page", "Page", AdPlacement.ad_page),
    ("run_code", "Run #", AdPlacement.run_code),
    ("bill_number", "Bill Number", AdPlacement.bill_number),
    ("ad_notes", "Ad Notes", AdPlacement.ad_notes),
]
TEXT_FIELDS = CONTACT_FIELDS + CLIENT_FIELDS + AD_FIELDS
STATUS_FLAGS = [
    ("current", "Current advertisers", Account.is_current_advertiser),
    ("past", "Past advertisers", Account.is_past_advertiser),
    ("prospect", "Prospects", Account.is_prospect),
    ("email_list", "E-mail list", Account.is_email_list),
]

EXPORT_HEADER = ["Account", "Advertiser", "Contact", "Address", "Address 2", "City", "State", "Zip",
                 "Phone", "E-mail", "Category", "Special Advertising Opportunities", "Notes"]


def like_pattern(text: str) -> str:
    """Plain text matches anywhere; * and ? are Access-style wildcards for exact patterns."""
    escaped = text.replace(ESCAPE, ESCAPE * 2).replace("%", ESCAPE + "%").replace("_", ESCAPE + "_")
    if "*" in text or "?" in text:
        return escaped.replace("*", "%").replace("?", "_")
    return f"%{escaped}%"


def _text_condition(column, text: str):
    return func.lower(column).like(like_pattern(text).lower(), escape=ESCAPE)


def _decimal(value: str | None) -> Decimal | None:
    value = (value or "").strip().replace("$", "").replace(",", "").rstrip("%")
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def parse_criteria(args) -> dict:
    """Read the search form from the query string. Returns values, conditions, and errors."""
    values: dict[str, str] = {}
    conditions = []
    errors = []

    for name, label, column in TEXT_FIELDS:
        text = (args.get(name) or "").strip()
        values[name] = text
        if text:
            conditions.append((label, _text_condition(column, text)))

    def date_range(prefix: str, label: str, column):
        raw_from, raw_to = (args.get(f"{prefix}_from") or "").strip(), (args.get(f"{prefix}_to") or "").strip()
        values[f"{prefix}_from"], values[f"{prefix}_to"] = raw_from, raw_to
        d_from, d_to = _parse_date(raw_from), _parse_date(raw_to)
        if raw_from and d_from is None:
            errors.append(f"{label} from: not a date.")
        if raw_to and d_to is None:
            errors.append(f"{label} to: not a date.")
        parts = []
        if d_from:
            parts.append(column >= d_from)
        if d_to:
            parts.append(column <= d_to)
        if parts:
            conditions.append((label, and_(*parts)))

    date_range("date_sold", "Date Sold", AdPlacement.date_sold)
    date_range("date_run", "Date Run", AdPlacement.date_run)

    raw_min, raw_max = (args.get("amount_min") or "").strip(), (args.get("amount_max") or "").strip()
    values["amount_min"], values["amount_max"] = raw_min, raw_max
    a_min, a_max = _decimal(raw_min), _decimal(raw_max)
    if raw_min and a_min is None:
        errors.append("Amount from: not a number.")
    if raw_max and a_max is None:
        errors.append("Amount to: not a number.")
    amount_parts = ([AdPlacement.amount >= a_min] if a_min is not None else []) + (
        [AdPlacement.amount <= a_max] if a_max is not None else []
    )
    if amount_parts:
        conditions.append(("Amount", and_(*amount_parts)))

    raw_pct = (args.get("comm_pct") or "").strip()
    values["comm_pct"] = raw_pct
    pct = _decimal(raw_pct)
    if raw_pct and pct is None:
        errors.append("Comm %: not a number.")
    elif pct is not None:
        fraction = pct / 100
        tolerance = Decimal("0.00005")
        conditions.append(("Comm %", AdPlacement.commission_percent.between(fraction - tolerance, fraction + tolerance)))

    mode = "and" if args.get("mode") == "and" else "or"
    flags = [key for key, _label, _col in STATUS_FLAGS if args.get(f"flag_{key}") == "1"]
    values["mode"] = mode

    return {"values": values, "conditions": conditions, "flags": flags, "mode": mode, "errors": errors}


def matching_accounts_subquery(criteria: dict):
    """Distinct account numbers matching the criteria (accounts LEFT JOIN ads, as in Access)."""
    exprs = [expr for _label, expr in criteria["conditions"]]
    combined = and_(*exprs) if criteria["mode"] == "and" else or_(*exprs)
    flag_conds = [col.is_(True) for key, _label, col in STATUS_FLAGS if key in criteria["flags"]]

    stmt = (
        select(Account.account_number)
        .select_from(Account)
        .outerjoin(AdPlacement, AdPlacement.account_number == Account.account_number)
        .where(*flag_conds)
    )
    if exprs:
        stmt = stmt.where(combined)
    return stmt.distinct()


@search_bp.get("/")
def index():
    criteria = parse_criteria(request.args)
    submitted = request.args.get("run") == "1"
    has_criteria = bool(criteria["conditions"] or criteria["flags"])
    advertisers = db.session.scalars(
        select(Account.advertiser).where(Account.advertiser.is_not(None)).group_by(Account.advertiser).order_by(Account.advertiser)
    ).all()

    context = {
        "v": criteria["values"],
        "flags": criteria["flags"],
        "status_flags": STATUS_FLAGS,
        "contact_fields": CONTACT_FIELDS,
        "client_fields": CLIENT_FIELDS,
        "ad_fields": AD_FIELDS,
        "advertisers": advertisers,
        "errors": criteria["errors"],
        "submitted": submitted,
        "rows": None,
        "used": [label for label, _expr in criteria["conditions"]],
    }

    if not submitted or criteria["errors"]:
        return render_template("search/index.html", **context)
    if not has_criteria:
        context["errors"] = ["Enter at least one search value or tick a status box."]
        return render_template("search/index.html", **context)

    matches = matching_accounts_subquery(criteria)
    fmt = request.args.get("format", "html")
    stamp = date.today().strftime("%Y%m%d")

    if fmt in ("csv", "xlsx", "labels"):
        accounts = db.session.scalars(
            select(Account).where(Account.account_number.in_(matches)).order_by(Account.advertiser, Account.account_number)
        ).all()
        if fmt == "labels":
            start_at = max(1, min(request.args.get("start_at", 1, type=int) or 1, 30))
            pdf = build_labels_pdf([account_label_lines(a) for a in accounts], start_position=start_at,
                                   title="Search results labels")
            return Response(pdf, mimetype="application/pdf", headers={
                "Content-Disposition": f'inline; filename="search_labels_{stamp}.pdf"', "Cache-Control": "no-store"})
        rows = [[a.account_number, a.advertiser, a.contact_name, a.address1, a.address2, a.city, a.state_code,
                 a.postal_code, a.phone, a.email, a.category, a.ad_ops, a.contact_notes] for a in accounts]
        if fmt == "csv":
            return csv_response(f"search_results_{stamp}.csv", EXPORT_HEADER, rows)
        return xlsx_response(f"search_results_{stamp}.xlsx", [
            {"title": "Search results", "header": EXPORT_HEADER, "rows": rows}
        ])

    ad_stats = (
        select(
            AdPlacement.account_number.label("acct"),
            func.count(AdPlacement.id).label("ad_count"),
            func.max(AdPlacement.date_run).label("last_run"),
        )
        .where(AdPlacement.account_number.is_not(None))
        .group_by(AdPlacement.account_number)
        .subquery()
    )
    stmt = (
        select(Account, func.coalesce(ad_stats.c.ad_count, 0), ad_stats.c.last_run)
        .outerjoin(ad_stats, ad_stats.c.acct == Account.account_number)
        .where(Account.account_number.in_(matches))
        .order_by(Account.advertiser, Account.account_number)
    )
    total = db.session.scalar(select(func.count()).select_from(matches.subquery()))
    pages = max(1, -(-total // PER_PAGE))
    page = min(max(request.args.get("page", 1, type=int), 1), pages)
    rows = db.session.execute(stmt.limit(PER_PAGE).offset((page - 1) * PER_PAGE)).all()

    query_args = {k: v for k, v in request.args.items() if k not in ("page", "format") and v}
    context.update(rows=rows, total=total, page=page, pages=pages, query_args=query_args)
    return render_template("search/index.html", **context)
