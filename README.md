# AOS NWC Ads (Flask + MariaDB)

This is a starter web app to replace an Access-based workflow.

Development OS: Windows
Runtime OS: Linux

## What is included

- Flask application factory structure
- MariaDB connection using SQLAlchemy + PyMySQL
- Migration support via Flask-Migrate
- Starter Ad model and browser CRUD pages
- Linux production runtime via Gunicorn

## Windows development setup

### 1) Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2) Install dependencies

```powershell
pip install -r requirements.txt
```

### 3) Configure environment

Copy .env.example to .env and set values.

```powershell
Copy-Item .env.example .env
```

### 4) Create MariaDB database

```sql
CREATE DATABASE aos_nwc_ads;
```

### 5) Initialize migrations and create tables

```powershell
flask --app run.py db init
flask --app run.py db migrate -m "Initial schema"
flask --app run.py db upgrade
```

### 6) Run the app

```powershell
flask --app run.py run --debug
```

Open http://127.0.0.1:5000

## Linux runtime (production)

### 1) Install system packages

Debian/Ubuntu example:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip mariadb-client
```

### 2) Create app directory and virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3) Set environment variables

```bash
cp .env.example .env
```

Then edit .env with your Linux runtime DB host, user, and password.

### 4) Run migrations

```bash
flask --app run.py db upgrade
```

### 5) Run app with Gunicorn

```bash
gunicorn --bind 0.0.0.0:8000 --workers 3 wsgi:app
```

### 6) Reverse proxy

Put Nginx (or Apache) in front of Gunicorn for TLS termination and request buffering.

## Linux service management (systemd)

Template file:
- deploy/systemd/aosnwcads.service

Install on Linux host:

```bash
sudo cp deploy/systemd/aosnwcads.service /etc/systemd/system/aosnwcads.service
sudo systemctl daemon-reload
sudo systemctl enable aosnwcads
sudo systemctl start aosnwcads
sudo systemctl status aosnwcads
```

Before enabling:
- Confirm WorkingDirectory points to your deployed path.
- Confirm User and Group are correct for your server.
- Confirm EnvironmentFile points to your production .env.

## Linux reverse proxy (Nginx)

Template file:
- deploy/nginx/aosnwcads.conf

Install on Linux host (Debian/Ubuntu):

```bash
sudo cp deploy/nginx/aosnwcads.conf /etc/nginx/sites-available/aosnwcads
sudo ln -s /etc/nginx/sites-available/aosnwcads /etc/nginx/sites-enabled/aosnwcads
sudo nginx -t
sudo systemctl reload nginx
```

Before reloading:
- Replace server_name example.com with your real domain.
- Configure TLS using certbot or your existing certificate process.

## Sign-in (Microsoft Entra ID) and roles

Set `AUTH_MODE` in `.env`:

- `entra`: production. Staff sign in with Microsoft 365. Requires `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET`, and a non-default `SECRET_KEY`; the app refuses to start without them.
- `dev`: no sign-in; every request runs as `DEV_ROLE` (default Admin). Use only on a developer machine or behind the Nginx IP allow list. A yellow banner is shown on every page.

Roles come from the Entra app roles `NWCAds.Viewer`, `NWCAds.Editor`, and `NWCAds.Admin`. Every page requires at least Viewer; protect editing views with `@require_role("Editor")` from `app/auth.py`.

Entra app registration settings:
- Redirect URI: `https://<host>/auth/callback`
- Front-channel logout URL: `https://<host>/auth/frontchannel-logout`

Unauthenticated health check: `GET /healthz` returns `ok`.

## Audit trail

Models with `__audited__ = True` (currently `Account` and `AdPlacement`) write one `audit_log` row per insert, update, or delete, in the same transaction, and stamp `created_by` / `updated_by`. Admins can browse it at Admin > Audit log.

## Database migrations

Schema changes go through Flask-Migrate (`migrations/`). On the server:

```bash
.venv/bin/flask --app run.py db upgrade
```

The baseline migration (`0001_baseline`) runs `sql/001_target_schema.sql` with `CREATE TABLE IF NOT EXISTS`, so it is safe on a database that was already built and imported. For new changes, write a new revision in `migrations/versions/`.

## Moving from Access

1. List your Access tables, fields, and relationships.
2. Add matching SQLAlchemy models in `app/models.py`.
3. Create migration scripts and apply with `db upgrade`.
4. Build pages/API routes for the Access forms/reports you use most.
5. Import legacy data into MariaDB (CSV export from Access works well).

## Access export (core tables)

Export script:
- scripts/export_access_csv.ps1

Example run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
./scripts/export_access_csv.ps1 -DatabasePath "./NWC_ADV_DB_2015.accdb" -OutputDir "./exports/access_csv"
```

Default tables exported:
- tbl_ProgressContacts_01
- tbl_ProgressAds_01

## MariaDB target schema and models

Target SQL schema:
- sql/001_target_schema.sql

Target SQLAlchemy models:
- app/target_models.py

Apply schema on MariaDB:

```bash
mariadb -u <user> -p <database_name> < sql/001_target_schema.sql
```

Current model strategy:
- app/models.py keeps the starter UI example model.
- app/target_models.py contains migration-target tables derived from Access profiling.

## Staging import into MariaDB

Import SQL template:
- sql/002_staging_import.sql

Run order:
1. Apply sql/001_target_schema.sql.
2. Edit two file path placeholders in sql/002_staging_import.sql.
3. Run sql/002_staging_import.sql.

Example:

```bash
mariadb --local-infile=1 -u <user> -p <database_name> < sql/001_target_schema.sql
mariadb --local-infile=1 -u <user> -p <database_name> < sql/002_staging_import.sql
```

## First-pass normalization seed

Seed generator script:
- scripts/build_normalization_seed.ps1

Generated outputs:
- analysis/normalization_seed.csv
- sql/003_seed_normalization_map.sql

Generate seed files:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
./scripts/build_normalization_seed.ps1 -AnalysisDir "./analysis" -OutputCsv "./analysis/normalization_seed.csv" -OutputSql "./sql/003_seed_normalization_map.sql"
```

Apply to MariaDB:

```bash
mariadb -u <user> -p <database_name> < sql/003_seed_normalization_map.sql
```

## Future Flask-to-FastAPI transition plan

Keep Flask through migration and parallel-run acceptance. Move to FastAPI only after cutover criteria are met.

Transition triggers:
- Need public/partner API contracts with OpenAPI-first governance.
- Need generated client SDKs from API schema.
- Need async-heavy integration patterns where Flask design becomes limiting.

Guardrails:
- No schema rewrite during framework transition.
- Keep SQLAlchemy models and migration history unchanged.
- Keep MariaDB table names and keys stable.
- Preserve report outputs and reconciliation checks as release gates.

Phased approach:
1. Extract business logic from Flask routes into service modules.
2. Add API tests against Flask behavior for baseline parity.
3. Stand up FastAPI app using same models and service modules.
4. Run FastAPI behind internal path or subdomain for shadow traffic.
5. Compare responses and performance on real workloads.
6. Cut over by switching reverse-proxy upstream from Flask to FastAPI.

Rollback plan:
- Keep Flask deployment artifact and systemd unit available until post-cutover signoff.
- Revert Nginx upstream to Flask if parity or stability checks fail.

Definition of done for transition:
- Zero data model drift.
- All API parity tests pass.
- Reporting and reconciliation outputs remain unchanged.
- One full publication cycle in production without framework-related incidents.

## Next recommended steps

- Add authentication and role-based access.
- Add search/filtering for ads.
- Add audit history for edits/deletes.
- Add data import scripts for Access exports.

## License

Copyright 2026 Archdiocese of Seattle. Author: Kevin F Benz.

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). Each source file carries the standard Apache header; add it to new files as well.
