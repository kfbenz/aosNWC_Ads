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

"""Reports that replace the Access Dashboard reports and the one-off saved queries.

See docs/access_application_spec.md section 5 (reports) and section 6 (queries).
All reports are read-only and available to Viewers.
"""
from __future__ import annotations

import re
from collections import OrderedDict
from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import Blueprint, Response, render_template, request
from sqlalchemy import func, select

from app.extensions import db
from app.labels import PER_SHEET, account_label_lines, build_labels_pdf
from app.spreadsheets import DATE, MONEY, PERCENT, csv_response, xlsx_response
from app.target_models import Account, AdPlacement


reports_bp = Blueprint("reports", __name__, url_prefix="/reports")

PREVIEW_LIMIT = 500
ZERO = Decimal("0")


# ---------------------------------------------------------------- helpers
def _date_arg(name: str) -> date | None:
    return _parse_date(request.args.get(name))


def _parse_date(value: str | None) -> date | None:
    value = (value or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def _advertiser(ad: AdPlacement, account: Account | None) -> str:
    if account is not None:
        return account.advertiser or f"(account {account.account_number})"
    return f"(account {ad.legacy_account_number or 'none'} not found)"


def _earned(ad: AdPlacement) -> Decimal:
    return (ad.amount or ZERO) * (ad.commission_percent or ZERO)


def _ads_join():
    return select(AdPlacement, Account).outerjoin(Account, AdPlacement.account_number == Account.account_number)


def _previous_month() -> tuple[date, date]:
    first_this = date.today().replace(day=1)
    last_prev = first_this - timedelta(days=1)
    return last_prev.replace(day=1), last_prev


def _stamp(d: date | None) -> str:
    return d.strftime("%Y%m%d") if d else "all"


def _issue_dates(limit: int = 36) -> list[date]:
    """Recent and upcoming run dates, newest first, for the issue picker."""
    return db.session.scalars(
        select(AdPlacement.date_run)
        .where(AdPlacement.date_run.is_not(None))
        .group_by(AdPlacement.date_run)
        .order_by(AdPlacement.date_run.desc())
        .limit(limit)
    ).all()


# ---------------------------------------------------------------- commission
@reports_bp.get("/commission")
def commission():
    """Commission Report by Sell Date (rpt_ProgressContactsWAds_Comm_01)."""
    start, end = _date_arg("start"), _date_arg("end")
    default_start, default_end = _previous_month()
    form = {"start": start or default_start, "end": end or default_end}
    if not (start and end):
        return render_template("reports/commission.html", form=form, groups=None)
    if start > end:
        start, end = end, start
        form = {"start": start, "end": end}

    rows = db.session.execute(
        _ads_join()
        .where(
            AdPlacement.date_sold >= start,
            AdPlacement.date_sold <= end,
            AdPlacement.commission_percent > 0,
        )
        .order_by(AdPlacement.date_sold, Account.advertiser, AdPlacement.id)
    ).all()

    groups: OrderedDict[date, dict] = OrderedDict()
    for ad, account in rows:
        grp = groups.setdefault(ad.date_sold, {"date": ad.date_sold, "rows": [], "amount": ZERO, "earned": ZERO})
        earned = _earned(ad)
        grp["rows"].append({"ad": ad, "advertiser": _advertiser(ad, account), "earned": earned})
        grp["amount"] += ad.amount or ZERO
        grp["earned"] += earned
    totals = {
        "amount": sum((g["amount"] for g in groups.values()), ZERO),
        "earned": sum((g["earned"] for g in groups.values()), ZERO),
        "count": len(rows),
    }
    actual = (rows[0][0].date_sold, rows[-1][0].date_sold) if rows else (start, end)

    if request.args.get("format") == "csv":
        header = ["Date Sold", "Advertiser", "Description", "Amount", "Comm %", "Run Date", "Comm Earned"]
        out = [
            [r["ad"].date_sold, r["advertiser"], r["ad"].description, r["ad"].amount,
             r["ad"].commission_percent, r["ad"].date_run, r["earned"].quantize(Decimal("0.01"))]
            for g in groups.values() for r in g["rows"]
        ]
        out.append(["", "TOTAL", "", totals["amount"], "", "", totals["earned"].quantize(Decimal("0.01"))])
        return csv_response(f"commission_{_stamp(start)}_{_stamp(end)}.csv", header, out)

    return render_template(
        "reports/commission.html", form=form, groups=list(groups.values()), totals=totals, actual=actual
    )


# ---------------------------------------------------------------- publication
@reports_bp.get("/publication")
def publication():
    """Publication Report by Run Date (rpt_ProgressContactsWAds_Pub_01): one issue's manifest."""
    issue_dates = _issue_dates()
    run_date = _date_arg("date")
    if run_date is None:
        upcoming = [d for d in issue_dates if d >= date.today()]
        default = min(upcoming) if upcoming else (issue_dates[0] if issue_dates else date.today())
        return render_template(
            "reports/publication.html", run_date=None, default=default, issue_dates=issue_dates, rows=None
        )

    rows = db.session.execute(
        _ads_join().where(AdPlacement.date_run == run_date).order_by(Account.advertiser, AdPlacement.id)
    ).all()
    lines = [{"ad": ad, "account": account, "advertiser": _advertiser(ad, account)} for ad, account in rows]
    total = sum((r["ad"].amount or ZERO for r in lines), ZERO)

    if request.args.get("format") == "csv":
        header = ["#", "Acct#", "Advertiser", "Contact", "Description", "Size", "Page", "Notes",
                  "Run #", "Billing", "Amount", "Comm %"]
        out = [
            [i, r["ad"].account_number or r["ad"].legacy_account_number, r["advertiser"],
             r["account"].contact_name if r["account"] else None, r["ad"].description, r["ad"].size_raw,
             r["ad"].ad_page, r["ad"].ad_notes, r["ad"].run_code, r["ad"].bill_number, r["ad"].amount,
             r["ad"].commission_percent]
            for i, r in enumerate(lines, start=1)
        ]
        return csv_response(f"publication_{_stamp(run_date)}.csv", header, out)

    return render_template(
        "reports/publication.html", run_date=run_date, default=run_date, issue_dates=issue_dates,
        rows=lines, total=total,
    )


# ---------------------------------------------------------------- labels
def _start_position() -> int:
    pos = request.args.get("start_at", 1, type=int) or 1
    return max(1, min(pos, PER_SHEET))


def _labels_pdf(accounts: list[Account], filename: str, include_contact: bool) -> Response:
    labels = [account_label_lines(a, include_contact) for a in accounts]
    pdf = build_labels_pdf(labels, start_position=_start_position(), title=filename)
    return Response(
        pdf,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"', "Cache-Control": "no-store"},
    )


@reports_bp.get("/labels")
def labels():
    """Mailing Labels by Directory Year (rpt_LabelsDirectoryXParameter_01)."""
    year = request.args.get("year", "").strip()
    include_contact = request.args.get("contact") == "1"
    accounts = None
    if year:
        accounts = db.session.scalars(
            select(Account)
            .where(Account.directory_years.icontains(year, autoescape=True))
            .order_by(Account.advertiser, Account.account_number)
        ).all()
        if request.args.get("format") == "pdf":
            return _labels_pdf(accounts, f"labels_directory_{re.sub(r'[^0-9A-Za-z-]', '', year)}.pdf", include_contact)

    return render_template(
        "reports/labels.html",
        year=year,
        include_contact=include_contact,
        start_at=_start_position(),
        accounts=accounts,
        per_sheet=PER_SHEET,
    )


# ---------------------------------------------------------------- advertiser lists
LIST_FLAGS = {
    "current": ("Current advertisers", Account.is_current_advertiser),
    "past": ("Past advertisers", Account.is_past_advertiser),
    "email": ("E-mail list", Account.is_email_list),
    "prospect": ("Prospects", Account.is_prospect),
}


def _list_filters() -> dict:
    args = request.args
    issue_tokens = re.split(r"[\s,;]+", args.get("issues", "").strip())
    issues = [d for d in (_parse_date(t) for t in issue_tokens if t) if d]
    return {
        "run_from": _parse_date(args.get("run_from")),
        "run_to": _parse_date(args.get("run_to")),
        "issues": issues,
        "issues_text": args.get("issues", "").strip(),
        "section": args.get("section", "").strip(),
        "rep": args.get("rep", "").strip(),
        "directory_year": args.get("directory_year", "").strip(),
        "category": args.get("category", "").strip(),
        "advertiser": args.get("advertiser", "").strip(),
        "flags": [f for f in LIST_FLAGS if args.get(f"flag_{f}") == "1"],
        "mode": args.get("mode") if args.get("mode") in ("ads", "advertisers") else "advertisers",
        "contact": args.get("contact") == "1",
    }


def _ad_conditions(f: dict) -> list:
    cond = []
    if f["run_from"]:
        cond.append(AdPlacement.date_run >= f["run_from"])
    if f["run_to"]:
        cond.append(AdPlacement.date_run <= f["run_to"])
    if f["issues"]:
        cond.append(AdPlacement.date_run.in_(f["issues"]))
    if f["section"]:
        cond.append(AdPlacement.section_raw.icontains(f["section"], autoescape=True))
    if f["rep"]:
        cond.append(func.upper(AdPlacement.sales_rep_raw) == f["rep"].upper())
    return cond


def _account_conditions(f: dict) -> list:
    cond = []
    if f["directory_year"]:
        cond.append(Account.directory_years.icontains(f["directory_year"], autoescape=True))
    if f["category"]:
        cond.append(Account.category.icontains(f["category"], autoescape=True))
    if f["advertiser"]:
        cond.append(Account.advertiser.icontains(f["advertiser"], autoescape=True))
    for flag in f["flags"]:
        cond.append(LIST_FLAGS[flag][1].is_(True))
    return cond


def _has_any_filter(f: dict) -> bool:
    return bool(_ad_conditions(f) or _account_conditions(f))


ADVERTISER_HEADER = ["Account", "Advertiser", "Contact", "Address", "Address 2", "City", "State", "Zip",
                     "Phone", "E-mail", "Category", "Directory Years", "Current", "Past", "E-mail List", "Prospect"]
AD_HEADER = ["Account", "Advertiser", "Contact", "Address", "Address 2", "City", "State", "Zip", "E-mail",
             "Run Date", "Date Sold", "Description", "Size", "Section", "Page", "Run #", "Bill #", "Amount",
             "Comm %", "Sales"]


def _advertiser_row(a: Account) -> list:
    return [a.account_number, a.advertiser, a.contact_name, a.address1, a.address2, a.city, a.state_code,
            a.postal_code, a.phone, a.email, a.category, a.directory_years,
            "Y" if a.is_current_advertiser else "", "Y" if a.is_past_advertiser else "",
            "Y" if a.is_email_list else "", "Y" if a.is_prospect else ""]


def _ad_row(ad: AdPlacement, a: Account | None) -> list:
    acct = [a.account_number if a else ad.legacy_account_number, _advertiser(ad, a)]
    acct += [a.contact_name, a.address1, a.address2, a.city, a.state_code, a.postal_code, a.email] if a else [None] * 7
    return acct + [ad.date_run, ad.date_sold, ad.description, ad.size_raw, ad.section_raw, ad.ad_page,
                   ad.run_code, ad.bill_number, ad.amount, ad.commission_percent, ad.sales_rep_raw]


@reports_bp.get("/advertiser-lists")
def advertiser_lists():
    """One filtered report replacing the ~60 one-off advertiser queries in Access."""
    f = _list_filters()
    fmt = request.args.get("format", "html")
    submitted = request.args.get("run") == "1"
    context = {"f": f, "flags": LIST_FLAGS, "submitted": submitted, "rows": None}

    if not submitted:
        return render_template("reports/advertiser_lists.html", **context)
    if not _has_any_filter(f):
        context["error"] = "Choose at least one filter, so the list is not every account."
        return render_template("reports/advertiser_lists.html", **context)

    ad_cond = _ad_conditions(f)
    acct_cond = _account_conditions(f)
    stamp = date.today().strftime("%Y%m%d")

    if f["mode"] == "advertisers" or fmt == "labels":
        stmt = select(Account).where(*acct_cond)
        if ad_cond:
            stmt = stmt.where(
                Account.account_number.in_(
                    select(AdPlacement.account_number).where(AdPlacement.account_number.is_not(None), *ad_cond)
                )
            )
        accounts = db.session.scalars(stmt.order_by(Account.advertiser, Account.account_number)).all()

        if fmt == "labels":
            return _labels_pdf(accounts, f"labels_{stamp}.pdf", f["contact"])
        rows = [_advertiser_row(a) for a in accounts]
        if fmt == "csv":
            return csv_response(f"advertisers_{stamp}.csv", ADVERTISER_HEADER, rows)
        if fmt == "xlsx":
            return xlsx_response(f"advertisers_{stamp}.xlsx", [
                {"title": "Advertisers", "header": ADVERTISER_HEADER, "rows": rows}
            ])
        context.update(header=ADVERTISER_HEADER, rows=rows[:PREVIEW_LIMIT], total=len(rows))
        return render_template("reports/advertiser_lists.html", **context)

    stmt = _ads_join().where(*ad_cond, *acct_cond).order_by(Account.advertiser, AdPlacement.date_run, AdPlacement.id)
    results = db.session.execute(stmt).all()
    rows = [_ad_row(ad, a) for ad, a in results]
    if fmt == "csv":
        return csv_response(f"advertiser_ads_{stamp}.csv", AD_HEADER, rows)
    if fmt == "xlsx":
        amount_total = sum((r[17] or ZERO for r in rows), ZERO)
        return xlsx_response(f"advertiser_ads_{stamp}.xlsx", [{
            "title": "Ads", "header": AD_HEADER,
            "rows": rows + [[None, "TOTAL"] + [None] * 15 + [amount_total, None, None]],
            "formats": {9: DATE, 10: DATE, 17: MONEY, 18: PERCENT}, "total_row": True,
        }])
    context.update(
        header=AD_HEADER, rows=rows[:PREVIEW_LIMIT], total=len(rows),
        amount_total=sum((r[17] or ZERO for r in rows), ZERO),
    )
    return render_template("reports/advertiser_lists.html", **context)


# ---------------------------------------------------------------- exports (pivots)
@reports_bp.get("/exports")
def exports():
    """The two Excel exports from the Access Dashboard: amounts and commission earned by run date."""
    start, end = _date_arg("start"), _date_arg("end")
    kind = request.args.get("kind")
    default_start, default_end = _previous_month()
    form = {"start": start or default_start, "end": end or default_end}

    if not (start and end and kind in ("amount", "commission")):
        return render_template("reports/exports.html", form=form)
    if start > end:
        start, end = end, start

    rows = db.session.execute(
        _ads_join()
        .where(AdPlacement.date_run >= start, AdPlacement.date_run <= end)
        .order_by(Account.advertiser, AdPlacement.description, AdPlacement.date_run)
    ).all()
    run_dates = sorted({ad.date_run for ad, _ in rows})

    pivot: OrderedDict[tuple, dict] = OrderedDict()
    for ad, account in rows:
        if kind == "amount":
            key = (_advertiser(ad, account), ad.description)
            value = ad.amount or ZERO
        else:
            key = (_advertiser(ad, account), ad.description, ad.amount, ad.commission_percent)
            value = _earned(ad)
        cells = pivot.setdefault(key, {})
        cells[ad.date_run] = cells.get(ad.date_run, ZERO) + value

    key_header = ["Advertiser", "Description"] + (["Amount", "Comm %"] if kind == "commission" else [])
    date_header = [d.strftime("%Y/%m/%d") for d in run_dates]
    header = key_header + date_header + ["Total"]

    out = []
    column_totals = [ZERO] * len(run_dates)
    for key, cells in pivot.items():
        values = [cells.get(d) for d in run_dates]
        for i, v in enumerate(values):
            if v is not None:
                column_totals[i] += v
        out.append(list(key) + values + [sum((v for v in values if v is not None), ZERO)])
    total_row = ["TOTAL"] + [None] * (len(key_header) - 1) + column_totals + [sum(column_totals, ZERO)]
    out.append(total_row)

    n_keys = len(key_header)
    formats = {i: MONEY for i in range(n_keys, len(header))}
    if kind == "commission":
        formats[2] = MONEY
        formats[3] = PERCENT
    title = "Amounts by run date" if kind == "amount" else "Commission earned by run date"
    filename = f"{'amounts' if kind == 'amount' else 'commission_earned'}_{_stamp(start)}_{_stamp(end)}.xlsx"
    return xlsx_response(filename, [{"title": title, "header": header, "rows": out, "formats": formats,
                                     "total_row": True}])
