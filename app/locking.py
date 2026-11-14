"""Optimistic locking for edit forms.

The form carries a fingerprint of the record as it was when the page loaded.
On save, a different fingerprint means someone else changed the record in the
meantime, so the save is refused instead of silently overwriting their work.
A content hash is used rather than updated_at, because timestamps only have
one-second resolution.
"""
import hashlib
import json

from sqlalchemy import inspect


def row_version(obj) -> str:
    if obj is None:
        return ""
    mapper = inspect(obj).mapper
    values = {attr.key: getattr(obj, attr.key) for attr in mapper.column_attrs}
    payload = json.dumps(values, default=str, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
