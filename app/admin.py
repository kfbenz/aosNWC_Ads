"""Admin pages (Admin role only)."""
from flask import Blueprint, render_template, request
from sqlalchemy import select

from app.audit import AuditLog
from app.auth import require_role
from app.extensions import db


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

AUDIT_PER_PAGE = 100


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
        entities=["accounts", "ad_placements"],
    )
