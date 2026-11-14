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

Status: Superseded by Decision 11 (single cutover, no parallel run).

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

Transition triggers (any one):
- Need public or partner API contracts with OpenAPI-first governance.
- Need generated client SDKs from an API schema.
- Need async-heavy integration patterns where the Flask design becomes limiting.

Guardrails:
- No schema rewrite during the framework transition.
- Keep SQLAlchemy models and migration history unchanged.
- Keep MariaDB table names and keys stable.
- Preserve report outputs and reconciliation checks as release gates.

Phased approach:
1. Extract business logic from Flask routes into service modules.
2. Add API tests against Flask behavior for baseline parity.
3. Stand up a FastAPI app using the same models and service modules.
4. Run FastAPI behind an internal path or subdomain for shadow traffic.
5. Compare responses and performance on real workloads.
6. Cut over by switching the reverse-proxy upstream from Flask to FastAPI.

Rollback: keep the Flask deployment and systemd unit until post-cutover sign-off, and revert the Nginx upstream if parity or stability checks fail.

## Decision 11: Single cutover, no parallel run

Date: 2026-11

Decision:
Build every Access form, report, and export in NWC Ads first, then switch over in one step. Staff do not enter data in both systems.

Rationale:
- Double entry for a publication cycle is error-prone and would be resisted by staff.
- Reconciliation of the imported data against Access (counts and totals) gives the no-loss assurance that the parallel run was meant to provide.

Consequences:
- The final import must be repeatable and verified (backlog C-04, C-05).
- Data cleanup in NWC Ads happens after the final import.

## Decision 12: Microsoft Entra ID sign-in with three app roles

Date: 2026-11

Decision:
Users sign in with their Archdiocese Microsoft accounts. Access is controlled by the Entra app roles `NWCAds.Viewer`, `NWCAds.Editor`, and `NWCAds.Admin`, which IT assigns. NWC Ads stores no passwords and keeps no user table.

Rationale:
- Leavers lose access when IT disables their account, without a separate step in NWC Ads.
- Three nested roles cover the Access usage patterns (read, enter data, administer).

## Decision 13: Audit every data change in the application

Date: 2026-11

Decision:
Record every insert, update, and delete of business data in an `audit_log` table, in the same transaction as the change, through SQLAlchemy session events. All data changes go through the ORM.

Rationale:
- Access had no change history. Pricing, commission, and run-date edits need accountability.
- Application-level auditing records the signed-in person, which database triggers could not.

## Decision 14: Keep free-text vocabularies, and constrain them with lookup lists

Date: 2026-11

Decision:
Keep Sales, Size, Section, and Billed as text on each ad. Admins clean them up with "merge spellings", and lookup lists restrict new entries. Do not convert them to foreign keys now.

Rationale:
- Converting about 830 size spellings to keys would require every mapping decision before go-live.
- Text with lookup lists lets each vocabulary be cleaned up gradually, after cutover, with a full audit trail, and preserves history exactly.

## Decision 15: Detect edits by two people at once with a content hash

Date: 2026-11

Decision:
Edit forms carry a hash of the record's values. A save is refused if the record changed after the form was opened.

Rationale:
- The `updated_at` timestamp has one-second resolution and missed edits made within the same second.

## Decision 16: Host on a single Azure VM with a local MariaDB

Date: 2026-11

Decision:
Run Nginx, Gunicorn, and MariaDB on one Debian VM in Azure, protected by TLS, an Nginx IP allow list, and Entra sign-in.

Rationale:
- The data volume and user count are small. A managed database service would add cost without benefit at this size.
- One server keeps operations simple for one developer.

Consequence:
- Backups are the main protection against VM loss (backlog C-02).

## Decision 17: Apache License 2.0

Date: 2026-11

Decision:
All code is copyright the Archdiocese of Seattle (author Kevin F Benz) and licensed under the Apache License 2.0, with a header in each source file.

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
6. Final import, reconciliation, and single cutover (Decision 11).
7. Retire Access after signed acceptance.

Current open items and business decisions are tracked in [docs/backlog.md](docs/backlog.md).
