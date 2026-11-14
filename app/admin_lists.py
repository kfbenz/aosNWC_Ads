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

"""Admin: lookup lists and merging spelling variants (normalization).

- Lookup lists define the allowed values for Sales, Size, Section, and Billed.
- Merging rewrites every ad that uses any of the selected spellings to one value,
  records each change in the audit log, and records the mapping in
  ad_normalization_map so the decision is documented.
"""
from __future__ import annotations

from datetime import datetime, timezone

from flask import abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy import func, select

from app.admin import admin_bp
from app.auth import require_role
from app.extensions import db
from app.lookups import CODE_MAX, LOOKUPS, ad_column, entries, exact, find_code, label_of, usage
from app.target_models import AdNormalizationMap, AdPlacement

PICKER_LIMIT = 300
MERGE_VALUES_LIMIT = 400


def _kind_or_404(kind: str) -> dict:
    if kind not in LOOKUPS:
        abort(404)
    return LOOKUPS[kind]


def _back(kind: str, **args):
    return redirect(url_for("admin.lookup_list", kind=kind, **{k: v for k, v in args.items() if v}))


# ---------------------------------------------------------------- lookup lists
@admin_bp.get("/lookups")
@require_role("Admin")
def lookups():
    summary = []
    for kind, spec in LOOKUPS.items():
        all_entries = entries(kind)
        codes = {e.code for e in all_entries}
        used = usage(kind)
        summary.append({
            "kind": kind,
            "spec": spec,
            "entries": len(all_entries),
            "active": sum(1 for e in all_entries if e.is_active),
            "values_in_use": len(used),
            "ads_off_list": sum(n for v, n in used if v not in codes),
            "values_off_list": sum(1 for v, _n in used if v not in codes),
        })
    return render_template("admin/lookups.html", summary=summary)


@admin_bp.get("/lookups/<kind>")
@require_role("Admin")
def lookup_list(kind: str):
    spec = _kind_or_404(kind)
    q = request.args.get("q", "").strip()

    all_entries = entries(kind)
    used = usage(kind)
    counts = dict(used)
    codes = {e.code for e in all_entries}
    codes_lower = {e.code.lower(): e.code for e in all_entries}

    off_list = []
    for value, n in used:
        if value in codes:
            continue
        if q and q.lower() not in value.lower():
            continue
        off_list.append({
            "value": value,
            "n": n,
            "case_of": codes_lower.get(value.lower()),
            "too_long": len(value) > CODE_MAX,
        })
    shown = off_list[:PICKER_LIMIT]

    return render_template(
        "admin/lookup_list.html",
        kind=kind,
        spec=spec,
        entries=all_entries,
        counts=counts,
        label_of=lambda e: label_of(kind, e),
        off_list=shown,
        off_total=len(off_list),
        q=q,
        code_max=CODE_MAX,
    )


@admin_bp.post("/lookups/<kind>/add")
@require_role("Admin")
def lookup_add(kind: str):
    spec = _kind_or_404(kind)
    code = (request.form.get("code") or "").strip()
    label = (request.form.get("label") or "").strip() or None
    if not code:
        flash("Enter a value to add.", "error")
    elif len(code) > CODE_MAX:
        flash(f"Values can be at most {CODE_MAX} characters.", "error")
    elif find_code(kind, code):
        flash(f"\"{find_code(kind, code).code}\" is already on the list (values must differ by more than capitalization).", "error")
    else:
        entry = spec["model"](code=code, is_active=True)
        setattr(entry, spec["label_attr"], label[:100] if label else None)
        db.session.add(entry)
        db.session.commit()
        flash(f"Added \"{code}\" to {spec['title'].lower()}.", "success")
    return _back(kind)


@admin_bp.post("/lookups/<kind>/add-many")
@require_role("Admin")
def lookup_add_many(kind: str):
    spec = _kind_or_404(kind)
    added, skipped = [], []
    for code in request.form.getlist("codes"):
        if not code or len(code) > CODE_MAX or find_code(kind, code):
            skipped.append(code)
            continue
        db.session.add(spec["model"](code=code, is_active=True))
        db.session.flush()
        added.append(code)
    db.session.commit()
    if added:
        flash(f"Added {len(added)} value{'s' if len(added) != 1 else ''} to {spec['title'].lower()}.", "success")
    if skipped:
        flash(f"Skipped {len(skipped)} already on the list or too long: {', '.join(skipped[:10])}"
              f"{'...' if len(skipped) > 10 else ''}", "error")
    if not added and not skipped:
        flash("Tick the values to add first.", "error")
    return _back(kind, q=request.form.get("q"))


@admin_bp.post("/lookups/<kind>/<int:entry_id>/update")
@require_role("Admin")
def lookup_update(kind: str, entry_id: int):
    spec = _kind_or_404(kind)
    entry = db.get_or_404(spec["model"], entry_id)
    label = (request.form.get("label") or "").strip() or None
    setattr(entry, spec["label_attr"], label[:100] if label else None)
    entry.is_active = request.form.get("is_active") == "1"
    db.session.commit()
    flash(f"Saved \"{entry.code}\".", "success")
    return _back(kind)


@admin_bp.post("/lookups/<kind>/<int:entry_id>/delete")
@require_role("Admin")
def lookup_delete(kind: str, entry_id: int):
    spec = _kind_or_404(kind)
    entry = db.get_or_404(spec["model"], entry_id)
    in_use = db.session.scalar(
        select(func.count(AdPlacement.id)).where(exact(ad_column(kind)) == entry.code)
    )
    if in_use:
        flash(f"\"{entry.code}\" is used by {in_use} ads. Deactivate it instead, or merge those ads into another value first.", "error")
    else:
        db.session.delete(entry)
        db.session.commit()
        flash(f"Removed \"{entry.code}\".", "success")
    return _back(kind)


# ---------------------------------------------------------------- merging (normalization)
def _merge_inputs(kind: str):
    values = [v for v in request.form.getlist("values") if v]
    target = (request.form.get("target") or "").strip()
    errors = []
    if not values:
        errors.append("Tick at least one value to merge.")
    if not target:
        errors.append("Enter the value to merge into.")
    elif len(target) > CODE_MAX:
        errors.append(f"The value to merge into can be at most {CODE_MAX} characters.")
    if len(values) > MERGE_VALUES_LIMIT:
        errors.append(f"Merge at most {MERGE_VALUES_LIMIT} values at a time.")
    changing = [v for v in values if v != target]
    return values, target, changing, errors


@admin_bp.get("/normalization")
@require_role("Admin")
def normalization():
    kind = request.args.get("domain", "size")
    spec = _kind_or_404(kind)
    q = request.args.get("q", "").strip()

    used = usage(kind)
    list_codes = {e.code for e in entries(kind)}
    values = [{"value": v, "n": n, "on_list": v in list_codes}
              for v, n in used if not q or q.lower() in v.lower()]

    recent = db.session.scalars(
        select(AdNormalizationMap)
        .where(AdNormalizationMap.domain == kind, AdNormalizationMap.approved_at.is_not(None))
        .order_by(AdNormalizationMap.approved_at.desc(), AdNormalizationMap.id.desc())
        .limit(25)
    ).all()

    return render_template(
        "admin/normalization.html",
        kind=kind,
        spec=spec,
        lookups=LOOKUPS,
        values=values[:PICKER_LIMIT],
        values_total=len(values),
        distinct_total=len(used),
        list_codes=sorted(list_codes, key=str.lower),
        recent=recent,
        q=q,
    )


@admin_bp.post("/normalization/<kind>/preview")
@require_role("Admin")
def normalization_preview(kind: str):
    spec = _kind_or_404(kind)
    values, target, changing, errors = _merge_inputs(kind)
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("admin.normalization", domain=kind, q=request.form.get("q") or None))

    col = exact(ad_column(kind))
    per_value = db.session.execute(
        select(col, func.count(AdPlacement.id)).where(col.in_(changing)).group_by(col)
    ).all() if changing else []
    total = sum(n for _v, n in per_value)
    on_list = find_code(kind, target)

    return render_template(
        "admin/normalization_preview.html",
        kind=kind,
        spec=spec,
        values=values,
        target=target,
        per_value=sorted(per_value, key=lambda r: -r[1]),
        total=total,
        target_on_list=on_list is not None and on_list.code == target,
        case_clash=on_list is not None and on_list.code != target,
        q=request.form.get("q", ""),
    )


@admin_bp.post("/normalization/<kind>/merge")
@require_role("Admin")
def normalization_merge(kind: str):
    spec = _kind_or_404(kind)
    values, target, changing, errors = _merge_inputs(kind)
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("admin.normalization", domain=kind))

    attr = spec["ad_attr"]
    ads = db.session.scalars(select(AdPlacement).where(exact(ad_column(kind)).in_(changing))).all() if changing else []
    for ad in ads:
        setattr(ad, attr, target)

    # Document each decision in the normalization map (one row per original spelling).
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    approver = g.user.username or g.user.name
    for raw in changing:
        row = db.session.scalars(
            select(AdNormalizationMap).where(AdNormalizationMap.domain == kind, AdNormalizationMap.raw_value == raw)
        ).first()
        if row is None:
            row = AdNormalizationMap(domain=kind, raw_value=raw)
            db.session.add(row)
        row.normalized_value = target
        row.notes = "Merged in NWC Ads admin"
        row.approved_by = approver
        row.approved_at = now
        db.session.flush()

    added_to_list = False
    if request.form.get("add_to_list") == "1" and not find_code(kind, target):
        db.session.add(spec["model"](code=target, is_active=True))
        added_to_list = True

    db.session.commit()
    flash(
        f"Merged {len(changing)} spelling{'s' if len(changing) != 1 else ''} into \"{target}\": "
        f"{len(ads)} ad{'s' if len(ads) != 1 else ''} updated"
        f"{', and added to the list' if added_to_list else ''}.",
        "success",
    )
    return redirect(url_for("admin.normalization", domain=kind))
