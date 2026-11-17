# NWC Ads: Developer Guide

Copyright 2026 Archdiocese of Seattle. Author: Kevin F Benz.

This guide is for a developer who maintains or extends NWC Ads. It covers setting up a workstation, the project's conventions, step-by-step recipes for common changes, and how to release a change. Read [architecture.md](architecture.md) first for the design. [operations.md](operations.md) covers the production server.

## 1. Workstation setup (Windows)

### 1.1 Prerequisites

- **Python 3.11 or later.** Production runs 3.11, so avoid language features newer than 3.11.
- **Git**, with access to the GitHub repository.
- **Visual Studio Code** or another editor.
- **The Access CSV exports** in `exports/access_csv/`. The tests and the local preview load their data from these files. They contain real advertiser data, so they are **not in Git** (`exports/` is in `.gitignore`). Produce them from a copy of the Access database:

  ```powershell
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  ./scripts/export_access_csv.ps1 -DatabasePath "./NWC_ADV_DB_2015.accdb" -OutputDir "./exports/access_csv"
  ```

  After cutover, export test data from MariaDB instead. See the backlog item on test data.
- **Optional: MariaDB 10.11 or later**, if you need to test against the production database engine (see section 6).

### 1.2 Install

```powershell
git clone <repository URL> aosNWCAds
cd aosNWCAds
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` for development:

```ini
AUTH_MODE=dev
DEV_ROLE=Admin          # Try Viewer and Editor too
SECRET_KEY=any-local-value
```

In `dev` mode there is no Microsoft sign-in. Every request acts as `DEV_ROLE`, and a yellow banner shows on every page. **Never** set `AUTH_MODE=dev` on a server that the internet can reach without the IP allow list.

### 1.3 Run the app

**Option A: in-memory preview (no database server needed).** This is the quickest way to try a change:

```powershell
python scripts/serve_preview.py          # http://127.0.0.1:5055
```

It loads the Access exports into an in-memory SQLite database, signs you in as Admin, and discards all changes when it stops. Restart it after any change to Python code or templates; a CSS change needs only a browser refresh.

**Option B: against a local MariaDB.** Use this when you work on SQL, migrations, or anything that depends on collation:

```powershell
# In .env: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD for your local database
flask --app run.py db upgrade        # Creates the tables (see section 5)
flask --app run.py run --debug       # http://127.0.0.1:5000
```

Load data with `sql/002_staging_import.sql`. Read [operations.md](operations.md) section 9 first, because the committed version of that script still lacks three fixes.

**Never point a workstation at the production database.**

## 2. Tests

```powershell
python tests/smoke_test.py
```

The script prints `PASS` or `FAIL` for about 260 checks and ends with `FAILURES: none`, or with a list of failures and exit status 1. It takes a few minutes.

It builds an in-memory SQLite database from the Access exports, then drives the app through Flask's test client in two configurations:

- **Dev mode, as Admin:** every page and report, saving and validation, the audit trail, edit conflicts, search counts, report totals, orphans, lookup lists, merges, and help. Report and search results are checked against totals computed independently from the CSV files.
- **Entra mode, with a fake Microsoft sign-in:** sign-in and sign-out, roles (Viewer, Editor, Admin, none), 403 responses for each role, CSRF rejection, open-redirect protection, and the startup configuration checks.

When you change behavior, add checks to the matching section of `tests/smoke_test.py`. Use the existing `check(label, condition)` helper. A bug fix should come with a check that would have caught the bug.

The script is a plain Python program, not a pytest suite. Converting it is a backlog item.

## 3. Conventions

### 3.1 Code

| Topic | Convention |
|---|---|
| Structure | One blueprint per functional area. Keep routes short; put reusable logic in a module function (for example `lookups.py` or `labels.py`). |
| Permissions | Put `@require_role("Editor")` or `@require_role("Admin")` on **every** view that changes data or shows Admin information. Hiding a button in the template is for usability only. |
| Forms | Use Flask-WTF forms for records. For small action forms, include `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`. Every POST needs a CSRF token. |
| Saving data | Change data **through ORM objects** (`obj.field = value`, `db.session.add`, `db.session.delete`), never with bulk `update()` or raw SQL. Only ORM changes reach the audit trail. |
| Edit pages | Include the hidden `version` field, and compare it with `row_version(obj)` before saving, as `accounts.detail` and `main.edit_ad` do. |
| Money and percentages | Use `Decimal`, never `float`. Store commission as a fraction; show and accept a percentage. |
| Exact text | When case matters (lookup codes, merges), wrap the column in `lookups.exact()`. |
| Downloads | Build CSV and Excel files with `spreadsheets.csv_response` and `spreadsheets.xlsx_response`. Both protect against formula injection. |
| SQL | Use SQLAlchemy expressions. Escape user text for `LIKE` (`icontains(..., autoescape=True)`, or `search.like_pattern`). Avoid MariaDB-only SQL where possible, because the tests run on SQLite. |
| License | Every new source file starts with the Apache header used in the existing files (copyright Archdiocese of Seattle, author Kevin F Benz). |

### 3.2 Pages and wording

- Pages extend `base.html`. Use the macros in `_form.html` (`field`, `datalist`, `fmt_date`, `money`, `pct`) instead of repeating markup.
- Styles live in `app/static/styles.css` only. Use the color variables at the top of the file (`--accent`, `--brand-cyan`, `--muted`, and so on), not new hard-coded colors.
- Add no JavaScript framework and no build step. Small inline handlers, such as a confirm dialog or a print button, are fine.
- Write all on-screen text and help in **formal English and the active voice, without contractions**. Prefer the staff's own terms from Access ("Advertiser", "Date Run", "Comm %").
- Mark required fields with a red asterisk: `<abbr class="required-mark" title="required">*</abbr>` after the label. The `field` macro in `_form.html` adds it automatically for fields with a `DataRequired` validator.
- Confirm destructive actions with `onsubmit="return confirm('...')"`, and say what cannot be undone.

### 3.3 Git

- Work on `main` for small changes, or on a short-lived branch for larger ones.
- Run the tests before each commit.
- Write the commit message as a summary line in the imperative mood ("Add Billed to the ad form"), followed by details if needed.
- Never commit `.env`, the Access database, or anything under `exports/`.

## 4. Recipes

Each recipe lists every place a change touches. The tests catch many omissions, but not all of them.

### 4.1 Add a page

1. Add the view to the right blueprint module, with `@require_role(...)` if it needs more than Viewer.
2. Add a template under `app/templates/<area>/` that extends `base.html`.
3. If the page belongs in the menu, add it to `MENU` in `app/menu.py`, with its endpoint and minimum role.
4. Map the page to its help section in `SCREEN_HELP` in `app/help.py`, and write that section (recipe 4.7).
5. Add checks to `tests/smoke_test.py`: the page opens (200), a lower role gets 403, and the page shows the expected data.

### 4.2 Add a field to accounts

Example: a `county` field.

1. **Migration**: create `migrations/versions/0003_account_county.py` (recipe 4.8) with `op.add_column("accounts", sa.Column("county", sa.String(50), nullable=True))`, and a matching `downgrade`.
2. **Schema file**: do **not** change `sql/001_target_schema.sql`. It is the frozen baseline that `0001_baseline` runs. On a fresh database, the baseline creates the table and the new migration then adds the column; if the baseline already had the column, the migration would fail with "duplicate column". `0003_account_billing_address.py` is a worked example.
3. **Model**: add `county = db.Column(db.String(50))` to `Account` in `app/target_models.py`.
4. **Form**: add `county = _text("County", 50)` to `AccountForm` in `app/forms.py`, and add `"county"` to `LEFT_FIELDS` or `RIGHT_FIELDS`. The account page renders those lists automatically, and `MODEL_FIELDS` saves them.
5. **Search** (if it should be searchable): add a row to `CONTACT_FIELDS` or `CLIENT_FIELDS` in `app/search.py`.
6. **Exports and labels** (if needed): add the column to `ADVERTISER_HEADER` and its row builder in `app/reports.py`, and to the search exports in `app/search.py`.
7. **Help**: describe the field in `help/topics/accounts.html`.
8. **Tests**: save a value and read it back. The audit trail picks up the new column automatically.

Adding a field to ads follows the same steps, with `AdPlacement`, `AdForm` (`MODEL_FIELDS`), `ads/form.html` (which lists its fields explicitly), `ad_detail.html`, and `AD_FIELDS` in `search.py`.

### 4.3 Add a report

1. Write the view in `app/reports.py`. Parse its parameters with the existing helpers (`_parse_date`), and return `render_template(...)` for the screen or `csv_response(...)` / `xlsx_response(...)` / a labels PDF for downloads.
2. Add the template under `app/templates/reports/`. Put the parameter form and action buttons inside `<div class="no-print">`, so that printing shows only the report. For landscape, add `{% block head %}<style>@page { size: letter landscape; }</style>{% endblock %}`, as `publication.html` does.
3. Add the report to the Reports children in `app/menu.py`, to `SCREEN_HELP`, and to `help/topics/reports.html`.
4. Test the totals against an independent calculation from the CSV data, as the existing report checks do.

### 4.4 Put Billed on the ad form (or add another lookup-driven field)

`billed_raw` already exists in the database, and the Billed lookup list exists in Admin. To put it on the ad form:

1. Add `billed_raw = _text("Billed", 50)` to `AdForm`, and add `"billed_raw"` to `AdForm.MODEL_FIELDS`.
2. Add `"billed_raw": "billed"` to `FORM_FIELD_KIND` in `app/lookups.py`. The form now shows a dropdown whenever the Billed list has active entries, and the server validates the value.
3. In `app/templates/ads/form.html`, add `{{ pick(form.billed_raw, choices.billed_raw, 'dl-billed') }}` and a matching `{{ f.datalist('dl-billed', suggestions.billed) }}`. Add `"billed"` to `_suggestions()` in `app/routes.py`.
4. Show Billed on `ad_detail.html` and in the account's Advertising History, and add it to search and exports if needed.
5. Update the Ads help topic and the lookup-list help, and remove the "Billed is not on the ad form yet" note from `admin/lookups.html`.

For an entirely new lookup list, first add a table (recipe 4.5), then add an entry to `LOOKUPS` in `app/lookups.py`, and add its domain to the `ad_normalization_map.domain` enum. The Admin list and merge pages pick it up from `LOOKUPS`.

### 4.5 Add a table

1. Add the model to `app/target_models.py`. Set `__audited__ = True` if its changes should be audited, which is the default expectation for business data.
2. Write a migration that creates it (recipe 4.8). Leave `sql/001_target_schema.sql` unchanged; it is the frozen baseline.
3. If Admins should see it in the audit log filter, add its table name to `AUDITED_ENTITIES` in `app/admin.py`.
4. In the test script, any `BigInteger` or `SmallInteger` primary key must be switched to `Integer` for SQLite, as the script already does for the existing tables (see section 6).

### 4.6 Change who can do what

- To let a different role use a view, change its `@require_role(...)`, the matching `g.user.can(...)` checks in templates, and the `role` in `app/menu.py`. Update the roles table in `help/topics/getting-started.html` and the tests.
- To add a new role, add it to `ROLE_LEVELS` in `app/auth.py`. IT must also add the app role `NWCAds.<Name>` to the Entra app registration. Roles are levels, so a new role must fit between, above, or below the existing ones. Separate, non-nested permissions would need a different design.

### 4.7 Edit or add help

- Help text is plain HTML in `app/templates/help/topics/<slug>.html`. Edit it like any template. Use `<h3 id="...">` for sections, so that screens and other topics can link to them.
- To add a topic, create the file and add a line to `TOPICS` in `app/help.py` (slug, title, minimum role, group, summary).
- To link a screen to a section, add `"blueprint.endpoint": ("slug", "section-id")` to `SCREEN_HELP`.
- The tests check that every topic renders, and that every `SCREEN_HELP` entry and every cross-link points to a section that exists.

### 4.8 Change the database schema (migrations)

Every schema change goes through an Alembic revision in `migrations/versions/`. The deployment runs `flask db upgrade`, which applies the new revisions in order.

1. Name the file `NNNN_short_description.py`, continuing the numbering (`0003_...`). Set `revision = "0003_short_description"` and `down_revision` to the previous revision ID.
2. Write `upgrade()` and `downgrade()` by hand with `op.add_column`, `op.create_table`, `op.create_index`, and so on. Copy the style of `0002_audit_trail.py`.
3. Alternatively, run `flask --app run.py db migrate -m "..."` against a local MariaDB with the current schema, and **review the generated file carefully**. `migrations/env.py` ignores tables that the app does not model (the import staging tables and the old `ads` table), so autogenerate does not propose dropping them.
4. Test the revision against a **copy of the production database**: `flask db upgrade`, then `flask db downgrade`, then `flask db upgrade` again.
5. For a data change, such as filling a new column, update rows through the ORM in a script, or write the `audit_log` rows explicitly. Otherwise the change leaves no audit trail.

Never edit a revision that production has already applied. Write a new one instead.

## 5. Database setup notes

- On a fresh database, `flask db upgrade` creates everything. `0001_baseline` runs `sql/001_target_schema.sql`, and `0002_audit_trail` adds the audit log.
- The production database was built from the SQL files before migrations existed. `0001_baseline` uses `CREATE TABLE IF NOT EXISTS`, so `flask db upgrade` on that database adds only what is missing (the audit trail from `0002`).
- To see which revision a database is at, run `flask --app run.py db current`. To see the revision history, run `flask --app run.py db history`.
- The baseline migration strips `--` comment lines before splitting the SQL file on `;`. Do not put a semicolon inside a string literal in `sql/001_target_schema.sql`.

## 6. SQLite and MariaDB

The tests and the preview use SQLite, and production uses MariaDB. These differences have caused bugs before:

| Topic | MariaDB | SQLite | What to do |
|---|---|---|---|
| Text comparison | Case-insensitive (`utf8mb4_unicode_ci`): `'KH' = 'kh'` is true | Case-sensitive | Use `lookups.exact()` when case matters. Remember that unique keys on MariaDB are case-insensitive too. |
| `NULLS LAST` | Not supported (error 1064) | Supported | Do not use `.nullslast()`. A descending sort already puts NULLs last on MariaDB. |
| `BIGINT` / `SMALLINT` primary keys | Auto-increment | Do **not** auto-increment | The test script switches them to `Integer`. Do the same for new tables. |
| Booleans, dates | Native types | Stored loosely | Validate in forms; do not rely on the database to reject bad values in tests. |

When a change involves collation, sorting, or SQL functions, also try it against a local MariaDB (option B in section 1.3), or render the SQL with the MariaDB dialect:

```python
from sqlalchemy.dialects import mysql
print(stmt.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}))
```

## 7. Releasing a change

1. Run `python tests/smoke_test.py`, and confirm `FAILURES: none`.
2. Try the change in the preview, as each role it affects (`DEV_ROLE`).
3. Update the in-app help, and these documents if the design or operations changed. Update [backlog.md](backlog.md).
4. Commit and push to `main`.
5. Deploy as described in [operations.md](operations.md) section 3. Run `flask db upgrade` if the change includes a migration. **Back up the database first** if it does.
6. Check the changed pages on the live site.

## 8. Where to look first

| Question | Start in |
|---|---|
| "Why can user X not do Y?" | `auth.py` (`ROLE_LEVELS`, `require_role`), the view's decorator, and the user's Entra role assignment |
| "Who changed this record?" | Admin › Audit log, or the `audit_log` table |
| "Why does this report show a different total than Access?" | The report's view in `reports.py`, and the matching Access query in [access_application_spec.md](access_application_spec.md) |
| "Where does this menu item go?" | `app/menu.py` |
| "Where does this text on the page come from?" | `grep` the templates for the text |
| "The site is down" | [operations.md](operations.md) section 8 |
