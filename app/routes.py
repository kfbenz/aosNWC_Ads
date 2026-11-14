from datetime import date, datetime
from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import func, or_, select

from app.auth import require_role
from app.extensions import db
from app.forms import AdForm
from app.locking import row_version as _version
from app.target_models import Account, AdPlacement


main_bp = Blueprint("main", __name__)

PER_PAGE = 50
SUGGESTION_LIMIT = 150


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


@main_bp.route("/accounts/<account_number>/ads/new", methods=["GET", "POST"])
@require_role("Editor")
def new_ad(account_number: str):
    account = db.get_or_404(Account, account_number)
    form = AdForm()

    if request.method == "GET":
        # Start from the account's most recent ad, as staff usually repeat its terms.
        last = db.session.scalars(
            select(AdPlacement)
            .where(AdPlacement.account_number == account.account_number)
            .order_by(AdPlacement.date_run.desc(), AdPlacement.id.desc())
            .limit(1)
        ).first()
        if last is not None:
            form.commission_pct.data = _fraction_to_pct(last.commission_percent)
            form.sales_rep_raw.data = last.sales_rep_raw
            form.authorized_by.data = last.authorized_by
        form.date_sold.data = date.today()

    if form.validate_on_submit():
        ad = AdPlacement(account_number=account.account_number, legacy_account_number=account.account_number)
        _apply_ad_form(form, ad)
        db.session.add(ad)
        db.session.commit()
        flash("Ad added.", "success")
        return redirect(url_for("accounts.detail", account_number=account.account_number))

    return render_template("ads/form.html", form=form, ad=None, account=account, suggestions=_suggestions())


@main_bp.route("/ads/<int:ad_id>/edit", methods=["GET", "POST"])
@require_role("Editor")
def edit_ad(ad_id: int):
    ad = db.get_or_404(AdPlacement, ad_id)
    form = AdForm(obj=ad)

    if request.method == "GET":
        form.commission_pct.data = _fraction_to_pct(ad.commission_percent)
        form.version.data = _version(ad)

    if form.validate_on_submit():
        if form.version.data != _version(ad):
            flash(
                "Someone else saved this ad while you were editing it. "
                "Their changes are shown below; re-enter yours and save again.",
                "error",
            )
            return redirect(url_for("main.edit_ad", ad_id=ad.id))

        _apply_ad_form(form, ad)
        db.session.commit()
        flash("Ad saved.", "success")
        if ad.account_number:
            return redirect(url_for("accounts.detail", account_number=ad.account_number))
        return redirect(url_for("main.ad_detail", ad_id=ad.id))

    return render_template("ads/form.html", form=form, ad=ad, account=ad.account, suggestions=_suggestions())


@main_bp.post("/ads/<int:ad_id>/delete")
@require_role("Admin")
def delete_ad(ad_id: int):
    ad = db.get_or_404(AdPlacement, ad_id)
    account_number = ad.account_number
    db.session.delete(ad)
    db.session.commit()
    flash(f"Ad #{ad_id} deleted.", "success")
    if account_number:
        return redirect(url_for("accounts.detail", account_number=account_number))
    return redirect(url_for("main.index"))


def _fraction_to_pct(value):
    return None if value is None else (Decimal(value) * 100).quantize(Decimal("0.01"))


def _apply_ad_form(form: AdForm, ad: AdPlacement) -> None:
    for name in AdForm.MODEL_FIELDS:
        setattr(ad, name, getattr(form, name).data)
    pct = form.commission_pct.data
    ad.commission_percent = None if pct is None else (Decimal(pct) / 100).quantize(Decimal("0.0001"))


def _suggestions() -> dict:
    """Values already in use, most common first, offered as type-ahead suggestions."""

    def common(column):
        return db.session.scalars(
            select(column)
            .where(column.is_not(None))
            .group_by(column)
            .order_by(func.count().desc(), column)
            .limit(SUGGESTION_LIMIT)
        ).all()

    return {
        "sales": common(func.upper(AdPlacement.sales_rep_raw)),
        "size": common(AdPlacement.size_raw),
        "section": common(AdPlacement.section_raw),
    }


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None
