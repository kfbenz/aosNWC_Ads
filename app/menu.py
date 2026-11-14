"""Site menu.

Mirrors the Access Dashboard (see docs/access_application_spec.md). Items whose
endpoint is not registered yet are shown disabled as "coming soon", so the menu
can be complete before every page is built.
"""
from __future__ import annotations

from flask import current_app, g, request, url_for


# Each item: label, endpoint, minimum role, extra endpoints that mark it active, children.
MENU = [
    {"label": "Ads", "endpoint": "main.index", "role": "Viewer", "also": ("main.ad_detail",)},
    {"label": "Accounts", "endpoint": "accounts.index", "role": "Viewer", "also_prefix": "accounts."},
    {"label": "Search", "endpoint": "search.index", "role": "Viewer", "also_prefix": "search."},
    {
        "label": "Reports",
        "role": "Viewer",
        "children": [
            {"label": "Commission by sell date", "endpoint": "reports.commission"},
            {"label": "Publication by run date", "endpoint": "reports.publication"},
            {"label": "Mailing labels by directory year", "endpoint": "reports.labels"},
            {"label": "Advertiser lists", "endpoint": "reports.advertiser_lists"},
            {"label": "Exports (amounts and commission)", "endpoint": "reports.exports"},
        ],
    },
    {
        "label": "Admin",
        "role": "Admin",
        "children": [
            {"label": "Lookup lists", "endpoint": "admin.lookups"},
            {"label": "Orphan ads", "endpoint": "admin.orphans"},
            {"label": "Normalization map", "endpoint": "admin.normalization"},
            {"label": "Audit log", "endpoint": "admin.audit"},
        ],
    },
]


def _resolve(item: dict, endpoint: str | None) -> dict:
    target = item.get("endpoint")
    available = target in current_app.view_functions if target else False
    active = bool(endpoint) and (
        endpoint == target
        or endpoint in item.get("also", ())
        or (item.get("also_prefix") and endpoint.startswith(item["also_prefix"]))
    )
    return {
        "label": item["label"],
        "url": url_for(target) if available else None,
        "active": active,
    }


def build_menu() -> list[dict]:
    user = g.get("user")
    if user is None:
        return []

    endpoint = request.endpoint
    menu = []
    for item in MENU:
        if not user.can(item.get("role", "Viewer")):
            continue
        if "children" in item:
            children = [_resolve(child, endpoint) for child in item["children"]]
            menu.append({
                "label": item["label"],
                "children": children,
                "active": any(child["active"] for child in children),
            })
        else:
            menu.append(_resolve(item, endpoint))
    return menu
