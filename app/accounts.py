"""Accounts (advertisers): list, view/edit with advertising history, add, delete.

Replaces the Access form "View and Edit Advertisers and Ads"
(frm_ProgressContacts_Info_01 with frm_ProgressAds_02_subfrm).
"""
from __future__ import annotations

import re

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy import func, or_, select

from app.auth import require_role
from app.extensions import db
from app.forms import AccountForm
from app.locking import row_version as _version
from app.target_models import Account, AdPlacement


accounts_bp = Blueprint("accounts", __name__, url_prefix="/accounts")

PER_PAGE = 50
FLAG_FILTERS = {
    "current": Account.is_current_advertiser,
    "past": Account.is_past_advertiser,
    "prospect": Account.is_prospect,
    "email": Account.is_email_list,
}
SORTS = {
    "name": (Account.advertiser.asc(), Account.account_number.asc()),
    "number": (Account.account_number.desc(),),
    "recent": None,  # handled in the query (latest run date first)
}


def next_account_number() -> str:
    """Suggest the next numeric account number, zero-padded to 6 digits like the existing ones."""
    numbers = db.session.scalars(select(Account.account_number)).all()
    highest = max((int(n) for n in numbers if n and re.fullmatch(r"\d{6}", n)), default=0)
    return f"{highest + 1:06d}"


@accounts_bp.get("/")
def index():
    q = request.args.get("q", "").strip()
    flag = request.args.get("flag", "").strip()
    sort = request.args.get("sort", "name")
    if sort not in SORTS:
        sort = "name"
    page = request.args.get("page", 1, type=int)

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

    stmt = select(
        Account,
        func.coalesce(ad_stats.c.ad_count, 0).label("ad_count"),
        ad_stats.c.last_run,
    ).outerjoin(ad_stats, ad_stats.c.acct == Account.account_number)

    if q:
        stmt = stmt.where(
            or_(
                Account.account_number.icontains(q, autoescape=True),
                Account.advertiser.icontains(q, autoescape=True),
                Account.contact_name.icontains(q, autoescape=True),
                Account.city.icontains(q, autoescape=True),
                Account.email.icontains(q, autoescape=True),
                Account.phone.icontains(q, autoescape=True),
                Account.category.icontains(q, autoescape=True),
            )
        )
    if flag in FLAG_FILTERS:
        stmt = stmt.where(FLAG_FILTERS[flag].is_(True))

    if sort == "recent":
        # Accounts with the most recent ad first; MariaDB sorts NULLs last in DESC order.
        stmt = stmt.order_by(ad_stats.c.last_run.desc(), Account.advertiser.asc())
    else:
        stmt = stmt.order_by(*SORTS[sort])

    total = db.session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    pages = max(1, -(-total // PER_PAGE))
    page = min(max(page, 1), pages)
    rows = db.session.execute(stmt.limit(PER_PAGE).offset((page - 1) * PER_PAGE)).all()

    filter_args = {k: v for k, v in request.args.items() if k != "page" and v}
    return render_template(
        "accounts/index.html",
        rows=rows,
        total=total,
        page=page,
        pages=pages,
        filters={"q": q, "flag": flag, "sort": sort},
        filter_args=filter_args,
    )


@accounts_bp.route("/new", methods=["GET", "POST"])
@require_role("Editor")
def new():
    form = AccountForm()
    if request.method == "GET":
        form.account_number.data = next_account_number()

    if form.validate_on_submit():
        if db.session.get(Account, form.account_number.data):
            form.account_number.errors.append("This account number is already in use.")
        else:
            account = Account()
            for name in AccountForm.MODEL_FIELDS:
                setattr(account, name, getattr(form, name).data)
            db.session.add(account)
            db.session.commit()
            flash(f"Account {account.account_number} created.", "success")
            return redirect(url_for("accounts.detail", account_number=account.account_number))

    return render_template("accounts/detail.html", form=form, account=None, ads=[], can_edit=True, nav={})


@accounts_bp.route("/<account_number>", methods=["GET", "POST"])
def detail(account_number: str):
    account = db.get_or_404(Account, account_number)
    can_edit = g.user.can("Editor")

    form = AccountForm(obj=account)
    # The account number is the business key used outside this system; it cannot be changed here.
    form.account_number.render_kw = {"readonly": True}

    if request.method == "POST":
        if not can_edit:
            abort(403)
        form.account_number.data = account.account_number
        if form.validate_on_submit():
            if form.version.data != _version(account):
                flash(
                    "Someone else saved this account while you were editing it. "
                    "Their changes are shown below; re-enter yours and save again.",
                    "error",
                )
                return redirect(url_for("accounts.detail", account_number=account.account_number))

            for name in AccountForm.MODEL_FIELDS:
                if name != "account_number":
                    setattr(account, name, getattr(form, name).data)
            db.session.commit()
            flash("Account saved.", "success")
            return redirect(url_for("accounts.detail", account_number=account.account_number))
    else:
        form.version.data = _version(account)

    ads = db.session.scalars(
        select(AdPlacement)
        .where(AdPlacement.account_number == account.account_number)
        .order_by(AdPlacement.date_run.desc(), AdPlacement.id.desc())
    ).all()

    # Previous/next in the Access order (highest account number first).
    nav = {
        "prev": db.session.scalar(
            select(func.min(Account.account_number)).where(Account.account_number > account.account_number)
        ),
        "next": db.session.scalar(
            select(func.max(Account.account_number)).where(Account.account_number < account.account_number)
        ),
    }

    return render_template(
        "accounts/detail.html", form=form, account=account, ads=ads, can_edit=can_edit, nav=nav
    )


@accounts_bp.post("/<account_number>/delete")
@require_role("Admin")
def delete(account_number: str):
    account = db.get_or_404(Account, account_number)
    ad_count = db.session.scalar(
        select(func.count(AdPlacement.id)).where(AdPlacement.account_number == account.account_number)
    )
    if ad_count:
        flash(f"This account has {ad_count} ads and cannot be deleted. Move or delete its ads first.", "error")
        return redirect(url_for("accounts.detail", account_number=account.account_number))

    db.session.delete(account)
    db.session.commit()
    flash(f"Account {account_number} deleted.", "success")
    return redirect(url_for("accounts.index"))
