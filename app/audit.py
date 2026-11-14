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

"""Audit trail for data changes.

Any model class with ``__audited__ = True`` gets:
- created_by / updated_by stamped with the signed-in user (if the columns exist), and
- one audit_log row per insert, update, or delete, with the changed values.

The audit rows are written in the same transaction as the change, so a change
cannot be saved without its audit record.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from flask import g, has_request_context
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.orm.base import NO_VALUE

from app.extensions import db


SKIP_FIELDS = {"created_at", "updated_at", "created_by", "updated_by"}


class AuditLog(db.Model):
    __tablename__ = "audit_log"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    occurred_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now(), index=True)
    user_oid = db.Column(db.String(64), nullable=True)
    user_name = db.Column(db.String(255), nullable=True)
    action = db.Column(db.String(10), nullable=False)
    entity = db.Column(db.String(64), nullable=False)
    entity_id = db.Column(db.String(64), nullable=False)
    changes = db.Column(db.Text, nullable=True)

    __table_args__ = (db.Index("ix_audit_log_entity", "entity", "entity_id"),)

    @property
    def changes_dict(self) -> dict:
        try:
            return json.loads(self.changes) if self.changes else {}
        except ValueError:
            return {}


def _current_actor() -> tuple[str | None, str]:
    if has_request_context() and g.get("user") is not None:
        return g.user.oid, g.user.username or g.user.name
    return None, "system"


def _jsonable(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _column_keys(obj):
    return [attr.key for attr in inspect(obj).mapper.column_attrs if attr.key not in SKIP_FIELDS]


def _entity_id(obj) -> str:
    pk = inspect(obj).mapper.primary_key_from_instance(obj)
    return "/".join("" if v is None else str(v) for v in pk)


def _is_audited(obj) -> bool:
    return getattr(type(obj), "__audited__", False)


def _before_flush(session: Session, flush_context, instances) -> None:
    _, actor = _current_actor()
    for obj in session.new:
        if _is_audited(obj):
            if hasattr(obj, "created_by") and not obj.created_by:
                obj.created_by = actor
            if hasattr(obj, "updated_by"):
                obj.updated_by = actor
    for obj in session.dirty:
        if _is_audited(obj) and session.is_modified(obj, include_collections=False):
            if hasattr(obj, "updated_by"):
                obj.updated_by = actor


def _after_flush(session: Session, flush_context) -> None:
    oid, actor = _current_actor()
    rows = []

    for obj in session.new:
        if not _is_audited(obj):
            continue
        state = inspect(obj)
        values = {k: _jsonable(state.attrs[k].value) for k in _column_keys(obj)}
        rows.append(("insert", obj, {k: v for k, v in values.items() if v is not None}))

    for obj in session.dirty:
        if not _is_audited(obj):
            continue
        state = inspect(obj)
        changed = {}
        for key in _column_keys(obj):
            hist = state.attrs[key].history
            if hist.has_changes():
                old = hist.deleted[0] if hist.deleted else None
                new = hist.added[0] if hist.added else None
                if old != new:
                    changed[key] = [_jsonable(old), _jsonable(new)]
        if changed:
            rows.append(("update", obj, changed))

    for obj in session.deleted:
        if not _is_audited(obj):
            continue
        state = inspect(obj)
        snapshot = {}
        for key in _column_keys(obj):
            value = state.attrs[key].loaded_value
            if value is not NO_VALUE and value is not None:
                snapshot[key] = _jsonable(value)
        rows.append(("delete", obj, snapshot))

    if not rows:
        return

    session.connection().execute(
        AuditLog.__table__.insert(),
        [
            {
                "user_oid": oid,
                "user_name": actor,
                "action": action,
                "entity": type(obj).__tablename__,
                "entity_id": _entity_id(obj),
                "changes": json.dumps(changes, default=str, sort_keys=True),
            }
            for action, obj, changes in rows
        ],
    )


def init_audit() -> None:
    """Register the session listeners once per process."""
    if not event.contains(Session, "before_flush", _before_flush):
        event.listen(Session, "before_flush", _before_flush)
    if not event.contains(Session, "after_flush", _after_flush):
        event.listen(Session, "after_flush", _after_flush)
