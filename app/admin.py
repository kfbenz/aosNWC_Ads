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
