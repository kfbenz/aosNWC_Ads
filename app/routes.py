from datetime import date, datetime

from flask import Blueprint, render_template, request
from sqlalchemy import func, or_, select

from app.extensions import db
from app.target_models import Account, AdPlacement


main_bp = Blueprint("main", __name__)

PER_PAGE = 50


@main_bp.get("/")
def index():
    """Read-only list of imported ad placements with filters.

    Access remains the system of record until cutover, so this view does not edit data.
    """
    q = request.args.get("q", "").strip()
    rep = request.args.get("rep", "").strip()
    date_from = _parse_date(request.args.get("from"))
    date_to = _parse_date(request.args.get("to"))
    page = request.args.get("page", 1, type=int)

    filters = []
    if q:
        filters.append(
            or_(
                Account.advertiser.icontains(q, autoescape=True),
                AdPlacement.description.icontains(q, autoescape=True),
                AdPlacement.legacy_account_number.icontains(q, autoescape=True),
                AdPlacement.bill_number.icontains(q, autoescape=True),
            )
        )
    if rep == "(none)":
        filters.append(AdPlacement.sales_rep_raw.is_(None))
    elif rep:
        # Legacy data mixes case (KH, Kh, kh); match the way Access does.
        filters.append(func.upper(AdPlacement.sales_rep_raw) == rep.upper())
    if date_from:
        filters.append(AdPlacement.date_run >= date_from)
    if date_to:
        filters.append(AdPlacement.date_run <= date_to)

    # MariaDB does not support NULLS LAST; a descending sort already places NULLs last.
    stmt = (
        select(AdPlacement)
        .outerjoin(Account)
        .where(*filters)
        .order_by(AdPlacement.date_run.desc(), AdPlacement.id.desc())
    )
    pagination = db.paginate(stmt, page=page, per_page=PER_PAGE, error_out=False)

    total_count, total_amount = db.session.execute(
        select(func.count(AdPlacement.id), func.sum(AdPlacement.amount))
        .select_from(AdPlacement)
        .outerjoin(Account)
        .where(*filters)
    ).one()

    rep_key = func.upper(AdPlacement.sales_rep_raw)
    reps = db.session.scalars(
        select(rep_key)
        .where(AdPlacement.sales_rep_raw.is_not(None))
        .group_by(rep_key)
        .order_by(rep_key)
    ).all()

    # Current filters without the page number, for building pagination links.
    filter_args = {k: v for k, v in request.args.items() if k != "page" and v}

    return render_template(
        "index.html",
        pagination=pagination,
        total_count=total_count,
        total_amount=total_amount or 0,
        reps=reps,
        filters={
            "q": q,
            "rep": rep,
            "from": date_from.isoformat() if date_from else "",
            "to": date_to.isoformat() if date_to else "",
        },
        filter_args=filter_args,
    )


@main_bp.get("/healthz")
def healthz():
    """Unauthenticated liveness check for curl and monitoring."""
    db.session.execute(select(1))
    return "ok", 200, {"Content-Type": "text/plain"}


@main_bp.get("/ads/<int:ad_id>")
def ad_detail(ad_id: int):
    ad = db.get_or_404(AdPlacement, ad_id)
    return render_template("ad_detail.html", ad=ad)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None
