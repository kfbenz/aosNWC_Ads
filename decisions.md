# NWC Ads Migration Decisions

Date: 2026-08-20
Status: Active

## Decision 1: Replace Access with service-based architecture

Decision:
Adopt a modern replacement for the Access application using:
- Flask for API and business logic (current baseline)
- MariaDB for primary data storage
- Flask-SQLAlchemy and Flask-Migrate
- Small web UI with scope controlled to current operational workflows

Rationale:
- Current database is live and revenue-critical, not archival.
- Data volume is small (~13k rows) and model complexity is low (2 operational tables).
- Core risk is operational fragility and data quality, not scale.

Implementation status:
- Baseline app and deployment scaffolding are in repository.

## Decision 2: Treat migration as live cutover with parallel run

Decision:
Plan a live migration with reconciliation and one publication-cycle parallel operation.

Rationale:
- Data includes forward bookings into 2027.
- Annual revenue tracked in system is material.
- No-loss migration standard is required.

Acceptance criteria:
- Year-by-year ad count and revenue totals match legacy output.
- Reports required by operations are reproducible and accepted.

Implementation status:
- Reconciliation-ready data pipeline files are in place.

## Decision 3: Prioritize data normalization before feature build-out

Decision:
Normalize key free-text domains before final schema lock:
- Size
- Section
- Sales
- Billed

Rationale:
- Normalization and orphan resolution are critical path items.
- Business-owner input is required and cannot be replaced by technical inference.

Implementation status:
- First-pass normalization seed generated in analysis/normalization_seed.csv and sql/003_seed_normalization_map.sql.

## Decision 4: Introduce stable keys for ad records

Decision:
Add a synthetic primary key for ad rows during migration.

Rationale:
- Legacy ads table currently has no primary key.
- API resources and update semantics require stable identifiers.

Constraint:
- Preserve AccountNumber exactly where used externally.

Implementation status:
- ad_placements uses synthetic id and preserves legacy_account_number.

## Decision 5: Preserve operational outputs explicitly

Decision:
Rebuild three capability surfaces that Access currently provides:
- Data entry and editing UI
- Printable reports (labels and publication advertiser views)
- Ad-hoc query access for non-developer users

Rationale:
- Access replacement that omits ad-hoc analysis will likely be bypassed.

## Decision 6: Mitigate immediate corruption risk independent of rewrite

Decision:
Move active Access file out of OneDrive-synced location now.

Rationale:
- Access locking and OneDrive sync behavior are incompatible under write contention.
- Existing compact/repair error evidence indicates prior file distress.

Required controls:
- Host on proper file share with sync exclusion
- Confirm tested backup independent of OneDrive version history

## Decision 7: Scope assumption for estimation

Decision:
Assume small application surface with limited embedded logic:
- 3 forms
- 2 reports
- 1 VBA module

Rationale:
- Scope indicates rewrite effort is dominated by data cleanup and workflow fit.

## Decision 8: Standardize migration pipeline with staging-first import

Decision:
Use a staging-first import approach from Access CSV exports to target tables.

Rationale:
- Enables deterministic transform and replay.
- Makes validation and error handling explicit.
- Supports iterative cleanup without re-reading Access for every test.

Implementation status:
- Export script: scripts/export_access_csv.ps1
- Staging/import SQL: sql/002_staging_import.sql

## Decision 9: Linux runtime is the production deployment standard

Decision:
Deploy production on Linux using Gunicorn, systemd, and Nginx.

Rationale:
- Aligns with runtime requirement.
- Improves operational stability and recoverability.

Implementation status:
- WSGI entrypoint and Linux deployment templates are in repository.

## Decision 10: Defer FastAPI framework transition until after migration cutover

Decision:
Treat FastAPI as optional post-cutover enhancement, not a pre-cutover blocker.

Rationale:
- Data quality and workflow parity are higher-risk items than framework choice.
- Reduces project risk by avoiding platform churn during migration.

## Open decisions requiring stakeholder input

1. Concurrent user count and usage pattern
2. Downstream constraints for report consumers and print process
3. Duplicate advertiser identity resolution rules
4. External dependencies on AccountNumber
5. Primary business pain driving replacement priorities
6. Whether to schedule a Flask-to-FastAPI migration after stabilization

## Execution sequence

1. Stabilize current Access hosting and backup posture.
2. Normalize vocabularies with business owner.
3. Resolve orphan and null-account ad rows.
4. Finalize target schema and migrate data via staging pipeline.
5. Build API, UI, and reports with reconciliation checks.
6. Run in parallel for one publication cycle.
7. Retire Access after signed acceptance.
