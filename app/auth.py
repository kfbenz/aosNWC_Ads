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

"""Microsoft Entra ID sign-in and role-based access control.

Every page requires a signed-in user with at least the Viewer role, except the
endpoints listed in PUBLIC_ENDPOINTS. Use @require_role("Editor") or
@require_role("Admin") on views that need more.

Roles come from the Entra app roles NWCAds.Viewer, NWCAds.Editor, and NWCAds.Admin
in the ID token's "roles" claim. A user with several roles gets the highest one.
"""
from __future__ import annotations

import functools
from dataclasses import asdict, dataclass
from urllib.parse import quote

import msal
from flask import (
    Blueprint,
    abort,
    current_app,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

ROLE_PREFIX = "NWCAds."
ROLE_LEVELS = {"Viewer": 1, "Editor": 2, "Admin": 3}
SCOPES = ["User.Read"]

PUBLIC_ENDPOINTS = {
    "auth.login",
    "auth.callback",
    "auth.logout",
    "auth.frontchannel_logout",
    "auth.signed_out",
    "main.healthz",
    "static",
}


@dataclass(frozen=True)
class CurrentUser:
    oid: str
    name: str
    username: str
    role: str | None

    def can(self, role: str) -> bool:
        return self.role is not None and ROLE_LEVELS[self.role] >= ROLE_LEVELS[role]


def highest_role(role_claims) -> str | None:
    best = None
    for claim in role_claims or []:
        if not isinstance(claim, str) or not claim.startswith(ROLE_PREFIX):
            continue
        name = claim[len(ROLE_PREFIX):]
        if name in ROLE_LEVELS and (best is None or ROLE_LEVELS[name] > ROLE_LEVELS[best]):
            best = name
    return best


def require_role(role: str):
    """Restrict a view to users with at least the given role."""
    if role not in ROLE_LEVELS:
        raise ValueError(f"Unknown role: {role}")

    def decorator(view):
        @functools.wraps(view)
        def wrapper(*args, **kwargs):
            if g.get("user") is None or not g.user.can(role):
                abort(403)
            return view(*args, **kwargs)

        return wrapper

    return decorator


def validate_config(app) -> None:
    """Fail fast at startup on unsafe or incomplete auth settings."""
    mode = app.config["AUTH_MODE"]
    if mode not in ("entra", "dev"):
        raise RuntimeError(f"AUTH_MODE must be 'entra' or 'dev', not {mode!r}.")

    if mode == "dev":
        if app.config["DEV_ROLE"] not in ROLE_LEVELS:
            raise RuntimeError(f"DEV_ROLE must be one of {', '.join(ROLE_LEVELS)}.")
        app.logger.warning("AUTH_MODE=dev: sign-in is disabled. Do not expose this app to the internet.")
        return

    missing = [
        key
        for key in ("ENTRA_TENANT_ID", "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET")
        if not app.config.get(key)
    ]
    if missing:
        raise RuntimeError(
            "AUTH_MODE=entra requires " + ", ".join(missing)
            + " in .env. Until IT provides them, set AUTH_MODE=dev (only behind the Nginx IP allow list)."
        )

    from config import DEFAULT_SECRET_KEY

    if app.config["SECRET_KEY"] in ("", DEFAULT_SECRET_KEY, "replace-me"):
        raise RuntimeError("Set SECRET_KEY in .env to a long random value before enabling Entra sign-in.")


def _authority() -> str:
    return f"https://login.microsoftonline.com/{current_app.config['ENTRA_TENANT_ID']}"


def _msal_app() -> msal.ConfidentialClientApplication:
    client = current_app.extensions.get("msal_client")
    if client is None:
        client = msal.ConfidentialClientApplication(
            current_app.config["ENTRA_CLIENT_ID"],
            authority=_authority(),
            client_credential=current_app.config["ENTRA_CLIENT_SECRET"],
        )
        current_app.extensions["msal_client"] = client
    return client


def _redirect_uri() -> str:
    return current_app.config["ENTRA_REDIRECT_URI"] or url_for("auth.callback", _external=True)


def _safe_next(target: str | None) -> str | None:
    """Allow only same-site relative paths, to prevent open redirects."""
    if not target or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return None
    return target


@auth_bp.before_app_request
def load_user():
    g.user = None

    if current_app.config["AUTH_MODE"] == "dev":
        g.user = CurrentUser(
            oid="dev",
            name=current_app.config["DEV_USER_NAME"],
            username="dev@localhost",
            role=current_app.config["DEV_ROLE"],
        )
        return None

    data = session.get("user")
    if data:
        g.user = CurrentUser(**data)

    # Unknown URLs (endpoint None) fall through to the normal 404 handling.
    if request.endpoint is None or request.endpoint in PUBLIC_ENDPOINTS:
        return None

    if g.user is None:
        next_path = request.full_path.rstrip("?") if request.method == "GET" else None
        return redirect(url_for("auth.login", next=next_path))

    if g.user.role is None:
        return render_template("auth/not_assigned.html"), 403

    return None


@auth_bp.get("/login")
def login():
    if current_app.config["AUTH_MODE"] != "entra":
        return redirect(url_for("main.index"))

    flow = _msal_app().initiate_auth_code_flow(SCOPES, redirect_uri=_redirect_uri())
    session["auth_flow"] = flow
    session["auth_next"] = _safe_next(request.args.get("next"))
    return redirect(flow["auth_uri"])


@auth_bp.get("/callback")
def callback():
    if current_app.config["AUTH_MODE"] != "entra":
        return redirect(url_for("main.index"))

    flow = session.pop("auth_flow", None)
    next_url = session.pop("auth_next", None)
    if not flow:
        return redirect(url_for("auth.login"))

    try:
        result = _msal_app().acquire_token_by_auth_code_flow(flow, request.args.to_dict())
    except ValueError:
        # State mismatch: the response does not belong to the sign-in this browser started.
        current_app.logger.warning("Entra sign-in rejected: state mismatch")
        abort(400)

    if "error" in result:
        current_app.logger.warning(
            "Entra sign-in failed: %s %s", result.get("error"), result.get("error_description")
        )
        return render_template("auth/error.html", error=result.get("error")), 401

    claims = result.get("id_token_claims") or {}
    user = CurrentUser(
        oid=claims.get("oid", ""),
        name=claims.get("name") or claims.get("preferred_username", ""),
        username=claims.get("preferred_username", ""),
        role=highest_role(claims.get("roles")),
    )

    # Start a fresh session on sign-in to prevent session fixation.
    session.clear()
    session["user"] = asdict(user)
    session.permanent = True
    current_app.logger.info("Signed in: %s (%s)", user.username, user.role or "no role")

    return redirect(next_url or url_for("main.index"))


@auth_bp.get("/logout")
def logout():
    session.clear()
    if current_app.config["AUTH_MODE"] != "entra":
        return redirect(url_for("main.index"))

    after = quote(url_for("auth.signed_out", _external=True), safe="")
    return redirect(f"{_authority()}/oauth2/v2.0/logout?post_logout_redirect_uri={after}")


@auth_bp.get("/signed-out")
def signed_out():
    return render_template("auth/signed_out.html")


@auth_bp.get("/frontchannel-logout")
def frontchannel_logout():
    """Called by Entra in a hidden frame when the user signs out elsewhere."""
    session.clear()
    return "", 200
