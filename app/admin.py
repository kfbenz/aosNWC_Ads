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

"""Admin pages (Admin role only): audit log and orphan-ad cleanup.

Lookup lists and value merging are in app/admin_lists.py, on the same blueprint.
"""
import re

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import func, select

from app.audit import AuditLog
from app.auth import require_role
from app.extensions import db
from app.target_models import Account, AdPlacement


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

AUDIT_PER_PAGE = 100
ORPHAN_GROUPS_PER_PAGE = 40
ACCOUNT_NUMBER_RE = re.compile(r"^[A-Z0-9]{1,6}$")
AUDITED_ENTITIES = ["accounts", "ad_placements", "sales_reps", "ad_sizes", "ad_sections",
                    "billing_statuses", "ad_normalization_map"]


@admin_bp.get("/audit")
@require_role("Admin")
def audit():
    entity = request.args.get("entity", "").strip()
    entity_id = request.args.get("id", "").strip()
    user = request.args.get("user", "").strip()
    page = request.args.get("page", 1, type=int)

    stmt = select(AuditLog)
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if user:
        stmt = stmt.where(AuditLog.user_name.icontains(user, autoescape=True))
    stmt = stmt.order_by(AuditLog.id.desc())

    pagination = db.paginate(stmt, page=page, per_page=AUDIT_PER_PAGE, error_out=False)
    filter_args = {k: v for k, v in request.args.items() if k != "page" and v}

    return render_template(
        "admin/audit.html",
        pagination=pagination,
        filters={"entity": entity, "id": entity_id, "user": user},
        filter_args=filter_args,
        entities=AUDITED_ENTITIES,
    )


# ---------------------------------------------------------------- orphan ads
def _orphan_filter(legacy: str):
    """Ads with no linked account whose legacy number is `legacy` ('' = blank)."""
    cond = [AdPlacement.account_number.is_(None)]
    if legacy:
        cond.append(AdPlacement.legacy_account_number == legacy)
    else:
        cond.append(AdPlacement.legacy_account_number.is_(None))
    return cond


def _suggest_account(legacy: str, known: set[str]) -> str | None:
    """Existing account that the legacy number probably meant (missing zeros or wrong case)."""
    if not legacy:
        return None
    candidates = [legacy.upper()]
    if legacy.isdigit() and len(legacy) < 6:
        candidates.append(legacy.zfill(6))
    for c in candidates:
        if c in known and c != legacy:
            return c
    return None


@admin_bp.get("/orphans")
@require_role("Admin")
def orphans():
    q = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)

    legacy_key = func.coalesce(AdPlacement.legacy_account_number, "")
    groups_stmt = (
        select(
            legacy_key.label("legacy"),
            func.count(AdPlacement.id).label("ad_count"),
            func.sum(AdPlacement.amount).label("total"),
            func.min(AdPlacement.date_run).label("first_run"),
            func.max(AdPlacement.date_run).label("last_run"),
        )
        .where(AdPlacement.account_number.is_(None))
        .group_by(legacy_key)
    )
    if q:
        matching = select(func.coalesce(AdPlacement.legacy_account_number, "")).where(
            AdPlacement.account_number.is_(None),
            (AdPlacement.legacy_account_number.icontains(q, autoescape=True))
            | (AdPlacement.description.icontains(q, autoescape=True))
            | (AdPlacement.ad_notes.icontains(q, autoescape=True)),
        )
        groups_stmt = groups_stmt.where(legacy_key.in_(matching))
    groups_stmt = groups_stmt.order_by(func.max(AdPlacement.date_run).desc(), legacy_key)

    total_groups = db.session.scalar(select(func.count()).select_from(groups_stmt.order_by(None).subquery()))
    total_ads = db.session.scalar(select(func.count(AdPlacement.id)).where(AdPlacement.account_number.is_(None)))
    pages = max(1, -(-total_groups // ORPHAN_GROUPS_PER_PAGE))
    page = min(max(page, 1), pages)
    groups = db.session.execute(
        groups_stmt.limit(ORPHAN_GROUPS_PER_PAGE).offset((page - 1) * ORPHAN_GROUPS_PER_PAGE)
    ).all()

    known = set(db.session.scalars(select(Account.account_number)).all())
    details = {}
    for g in groups:
        ads = db.session.scalars(
            select(AdPlacement)
            .where(*_orphan_filter(g.legacy))
            .order_by(AdPlacement.date_run.desc(), AdPlacement.id.desc())
            .limit(5)
        ).all()
        details[g.legacy] = {
            "ads": ads,
            "suggestion": _suggest_account(g.legacy, known),
            "can_create": bool(ACCOUNT_NUMBER_RE.match(g.legacy.upper())) and g.legacy.upper() not in known,
        }

    accounts = db.session.execute(
        select(Account.account_number, Account.advertiser).order_by(Account.advertiser)
    ).all()

    return render_template(
        "admin/orphans.html",
        groups=groups,
        details=details,
        accounts=accounts,
        suggestion_names=dict(accounts),
        total_groups=total_groups,
        total_ads=total_ads,
        page=page,
        pages=pages,
        q=q,
    )


@admin_bp.post("/orphans/resolve")
@require_role("Admin")
def resolve_orphans():
    legacy = request.form.get("legacy", "")
    action = request.form.get("action")
    back = redirect(url_for("admin.orphans", q=request.form.get("q") or None, page=request.form.get("page") or None))

    ads = db.session.scalars(select(AdPlacement).where(*_orphan_filter(legacy))).all()
    if not ads:
        flash("Those ads are no longer orphans (someone may have resolved them already).", "error")
        return back

    if action == "attach":
        target = (request.form.get("account_number") or "").strip().upper()
        account = db.session.get(Account, target) if target else None
        if account is None:
            flash(f"Account {target or '(blank)'} does not exist. Pick an existing account number.", "error")
            return back
    elif action == "create":
        target = legacy.upper()
        advertiser = (request.form.get("advertiser") or "").strip()
        if not ACCOUNT_NUMBER_RE.match(target):
            flash(f"{legacy or '(blank)'} cannot be used as an account number. Attach these ads instead.", "error")
            return back
        if db.session.get(Account, target) is not None:
            flash(f"Account {target} already exists. Use Attach instead.", "error")
            return back
        if not advertiser:
            flash("Enter the advertiser name for the new account.", "error")
            return back
        account = Account(account_number=target, advertiser=advertiser[:255])
        db.session.add(account)
        db.session.flush()
    else:
        flash("Unknown action.", "error")
        return back

    for ad in ads:
        # legacy_account_number is kept unchanged as the record of what Access had.
        ad.account_number = account.account_number
    db.session.commit()

    verb = "Created account" if action == "create" else "Attached to account"
    flash(
        f"{verb} {account.account_number} ({account.advertiser or 'no name'}): "
        f"{len(ads)} ad{'s' if len(ads) != 1 else ''} from old number {legacy or '(blank)'}.",
        "success",
    )
    return back


# Register the lookup-list and merge pages on this blueprint.
from app import admin_lists  # noqa: E402,F401
