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

import os
from datetime import timedelta
from urllib.parse import quote_plus

from dotenv import load_dotenv


load_dotenv()

DEFAULT_SECRET_KEY = "dev-secret-key"


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", DEFAULT_SECRET_KEY)

    _database_url = os.getenv("DATABASE_URL")
    if _database_url:
        SQLALCHEMY_DATABASE_URI = _database_url
    else:
        db_user = os.getenv("DB_USER", "root")
        db_password = quote_plus(os.getenv("DB_PASSWORD", ""))
        db_host = os.getenv("DB_HOST", "localhost")
        db_port = os.getenv("DB_PORT", "3306")
        db_name = os.getenv("DB_NAME", "aos_nwc_ads")
        SQLALCHEMY_DATABASE_URI = (
            f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        )

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 3600}

    # Authentication
    # AUTH_MODE=entra : Microsoft Entra ID sign-in (production).
    # AUTH_MODE=dev   : no sign-in; every request runs as a local user with DEV_ROLE.
    #                   Use only on a developer machine or behind an IP allow list.
    AUTH_MODE = os.getenv("AUTH_MODE", "entra").strip().lower()
    DEV_ROLE = os.getenv("DEV_ROLE", "Admin").strip()
    DEV_USER_NAME = os.getenv("DEV_USER_NAME", "Local Developer").strip()

    ENTRA_TENANT_ID = os.getenv("ENTRA_TENANT_ID", "").strip()
    ENTRA_CLIENT_ID = os.getenv("ENTRA_CLIENT_ID", "").strip()
    ENTRA_CLIENT_SECRET = os.getenv("ENTRA_CLIENT_SECRET", "").strip()
    # Optional: set explicitly if the app cannot work out its public URL behind the proxy.
    ENTRA_REDIRECT_URI = os.getenv("ENTRA_REDIRECT_URI", "").strip()

    # Sessions
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", AUTH_MODE != "dev")
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    # Number of reverse proxies in front of the app (Nginx = 1).
    PROXY_COUNT = int(os.getenv("PROXY_COUNT", "1"))
