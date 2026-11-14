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
