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

from datetime import date

from flask import Flask, render_template
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from app.extensions import db, migrate


csrf = CSRFProtect()


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    # Trust X-Forwarded-* from Nginx so redirects and the Entra callback URL use https.
    proxies = app.config.get("PROXY_COUNT", 1)
    if proxies:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxies, x_proto=proxies, x_host=proxies)

    from app.auth import auth_bp, validate_config

    validate_config(app)

    db.init_app(app)
    migrate.init_app(app, db, compare_type=True)
    csrf.init_app(app)

    # Import models so they are registered with SQLAlchemy and Flask-Migrate.
    from app import target_models  # noqa: F401
    from app.audit import AuditLog, init_audit  # noqa: F401

    init_audit()

    from app.accounts import accounts_bp
    from app.admin import admin_bp
    from app.menu import build_menu
    from app.reports import reports_bp
    from app.routes import main_bp
    from app.search import search_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(admin_bp)

    @app.context_processor
    def inject_layout():
        return {
            "menu": build_menu(),
            "auth_mode": app.config["AUTH_MODE"],
            "today": date.today(),
        }

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    return app
