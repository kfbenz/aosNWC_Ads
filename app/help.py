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

"""In-app help.

Each topic is a template under templates/help/topics/<slug>.html. To add or edit
help, change that template; to add a topic, also add it to TOPICS. SCREEN_HELP
maps each screen (Flask endpoint) to the topic and section that explain it, so
the "Help" link in the header opens the right place.
"""
from __future__ import annotations

import html
import re

from flask import Blueprint, abort, g, render_template, request, url_for


help_bp = Blueprint("help", __name__, url_prefix="/help")


# slug, title, minimum role, group, one-line summary. Order is the order shown.
TOPICS = [
    ("getting-started", "Getting started", "Viewer", "Using NWC Ads",
     "Signing in, roles, the menu, and saving your work."),
    ("ads", "Ads", "Viewer", "Using NWC Ads",
     "Finding ads, and adding, editing, and deleting them."),
    ("accounts", "Accounts", "Viewer", "Using NWC Ads",
     "Finding advertisers, creating accounts, and editing contact details."),
    ("search", "Search", "Viewer", "Using NWC Ads",
     "Advanced search across advertisers and ads, with exports and labels."),
    ("reports", "Reports", "Viewer", "Using NWC Ads",
     "Commission, publication, mailing labels, advertiser lists, and exports."),
    ("glossary", "Terms and questions", "Viewer", "Using NWC Ads",
     "What the fields and terms mean, and answers to common questions."),
    ("admin-lookups", "Lookup lists", "Admin", "Administration",
     "The allowed values for Sales, Size, Section, and Billed."),
    ("admin-merge", "Merge spellings", "Admin", "Administration",
     "Combining values that mean the same thing."),
    ("admin-orphans", "Orphan ads", "Admin", "Administration",
     "Ads whose account number is not in Accounts."),
    ("admin-audit", "Audit log", "Admin", "Administration",
     "Who changed what, and when."),
]

# Screen (endpoint) -> (topic slug, section anchor or None).
SCREEN_HELP = {
    "main.index": ("ads", "list"),
    "main.ad_detail": ("ads", "view"),
    "main.new_ad": ("ads", "add"),
    "main.edit_ad": ("ads", "edit"),
    "accounts.index": ("accounts", "list"),
    "accounts.new": ("accounts", "new"),
    "accounts.detail": ("accounts", "detail"),
    "search.index": ("search", None),
    "reports.commission": ("reports", "commission"),
    "reports.publication": ("reports", "publication"),
    "reports.labels": ("reports", "labels"),
    "reports.advertiser_lists": ("reports", "advertiser-lists"),
    "reports.exports": ("reports", "exports"),
    "admin.lookups": ("admin-lookups", None),
    "admin.lookup_list": ("admin-lookups", "list"),
    "admin.normalization": ("admin-merge", None),
    "admin.normalization_preview": ("admin-merge", "preview"),
    "admin.orphans": ("admin-orphans", None),
    "admin.audit": ("admin-audit", None),
}

SNIPPET_RADIUS = 80
MAX_SNIPPETS = 3


def _topic(slug: str) -> dict | None:
    for t_slug, title, role, group, summary in TOPICS:
        if t_slug == slug:
            return {"slug": t_slug, "title": title, "role": role, "group": group, "summary": summary}
    return None


def visible_topics() -> list[dict]:
    """Topics the signed-in user's role can use."""
    user = g.get("user")
    topics = [_topic(slug) for slug, *_ in TOPICS]
    return [t for t in topics if user is not None and user.can(t["role"])]


def help_url_for_page() -> str:
    """Link for the header's Help button: the section for the current screen when there is one."""
    slug, anchor = SCREEN_HELP.get(request.endpoint or "", (None, None))
    topic = _topic(slug) if slug else None
    user = g.get("user")
    if topic is None or user is None or not user.can(topic["role"]):
        return url_for("help.index")
    return url_for("help.topic", slug=slug, _anchor=anchor)


def _render_body(slug: str) -> str:
    return render_template(f"help/topics/{slug}.html")


def _plain_text(markup: str) -> str:
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", markup, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _snippets(text: str, words: list[str]) -> list[str]:
    """Short excerpts around the first matches of the search words."""
    lowered = text.lower()
    spans: list[tuple[int, int]] = []
    for word in words:
        start = 0
        while len(spans) < MAX_SNIPPETS:
            pos = lowered.find(word, start)
            if pos < 0:
                break
            spans.append((max(0, pos - SNIPPET_RADIUS), min(len(text), pos + len(word) + SNIPPET_RADIUS)))
            start = pos + len(word)
    spans.sort()
    merged: list[list[int]] = []
    for lo, hi in spans:
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    out = []
    for lo, hi in merged[:MAX_SNIPPETS]:
        out.append(("…" if lo else "") + text[lo:hi].strip() + ("…" if hi < len(text) else ""))
    return out


@help_bp.get("/")
def index():
    q = request.args.get("q", "").strip()
    topics = visible_topics()
    results = None

    if q:
        words = [w for w in q.lower().split() if w][:8]
        results = []
        for t in topics:
            text = _plain_text(_render_body(t["slug"]))
            haystack = (t["title"] + " " + text).lower()
            if all(w in haystack for w in words):
                score = sum(haystack.count(w) for w in words) + (10 if all(w in t["title"].lower() for w in words) else 0)
                results.append({**t, "snippets": _snippets(text, words), "score": score})
        results.sort(key=lambda r: -r["score"])

    groups: dict[str, list[dict]] = {}
    for t in topics:
        groups.setdefault(t["group"], []).append(t)

    return render_template("help/index.html", groups=groups, topics=topics, q=q, results=results)


@help_bp.get("/<slug>")
def topic(slug: str):
    t = _topic(slug)
    if t is None:
        abort(404)
    if not g.user.can(t["role"]):
        abort(403)

    topics = visible_topics()
    position = next(i for i, x in enumerate(topics) if x["slug"] == slug)
    return render_template(
        "help/topic.html",
        topic=t,
        topics=topics,
        body=_render_body(slug),
        prev_topic=topics[position - 1] if position > 0 else None,
        next_topic=topics[position + 1] if position + 1 < len(topics) else None,
    )
