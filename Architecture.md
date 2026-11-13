# Northwest Catholic Ads - Target Architecture

Date: 2026-08-20
Author: Migration Working Draft
Status: Updated to match current repository baseline

## 1. Context

The current Access database functions as the operational system of record for ad sales and billing. Although nominally historical by filename, the data is live with forward-booked ads and active revenue tracking.

Observed shape:
- Operational data mostly concentrated in two tables:
  - tbl_ProgressContacts_01 (advertisers/contacts)
  - tbl_ProgressAds_01 (placements)
- Remaining tables are mostly scaffolding, caches, or error artifacts.
- Embedded application logic surface is small (3 forms, 2 reports, 1 VBA module).

## 2. Architecture goals

1. Preserve business continuity with no data loss.
2. Replace single-file Access fragility with server-backed storage.
3. Provide equivalent or better data-entry UX and reporting.
4. Preserve ad-hoc query capability for non-developers.
5. Improve data quality and enforce constraints.

## 3. Current baseline stack (implemented)

- API and domain logic: Flask
- Database: MariaDB
- ORM/migrations: Flask-SQLAlchemy + Flask-Migrate
- Production runtime: Linux + Gunicorn + systemd + Nginx
- Data migration tooling: PowerShell extraction/profiling + SQL staging import scripts

Repository artifacts in place:
- Core schema: sql/001_target_schema.sql
- Staging import: sql/002_staging_import.sql
- Normalization seed SQL: sql/003_seed_normalization_map.sql
- Access profiling script: scripts/profile_access.ps1
- Access CSV export script: scripts/export_access_csv.ps1
- Normalization seed builder: scripts/build_normalization_seed.ps1

Rationale for MariaDB baseline:
- Aligns with requested target runtime.
- Operationally straightforward for Linux hosting.
- Supports multi-user access, backups, and safer writes versus Access file locking.

## 4. Planned evolution options

Option A (recommended near-term):
- Continue with Flask service and expand domain modules.

Option B (deferred):
- Move API layer to FastAPI later if async endpoints or OpenAPI-first workflows become a priority.

Decision gate:
- Keep migration focused on data quality and operational parity first.
- Re-evaluate framework shift only after successful parallel run.

## 5. Logical domain model

Core entities:
- Account (preserve AccountNumber as business identifier)
- AdPlacement (synthetic primary key)
- Lookup tables:
  - AdSize
  - AdSection
  - SalesRep
  - BillingStatus
  - AdNormalizationMap

Key rules:
- AdPlacement may retain legacy_account_number while account_number is null for orphan handling.
- Dates validated to realistic ranges.
- Enumerated domains no longer free text.
- Soft-delete or audit log for critical edits/deletes.

## 6. Data quality workstream (critical path)

Data cleanup drives timeline more than coding.

Priority issues:
- Missing PK on ads table
- Free-text normalization (Size, Section, Sales, Billed)
- Orphan ads and null account references
- Invalid and missing date values
- Duplicate-contact ambiguity

Required operating model:
- Business owner adjudicates normalization mappings and ambiguity.
- Technical team implements deterministic transforms with full audit trail.

## 7. Migration strategy

Phase 1: Stabilize source
- Move Access file off OneDrive-synced location.
- Verify tested backups.
- Freeze structural changes unless approved.

Phase 2: Profile and map
- Finalize canonical vocabulary maps.
- Define reconciliation queries and acceptance metrics.
- Generate first-pass map from distinct value exports, then business-review to final.

Phase 3: Build and migrate
- Apply schema (sql/001_target_schema.sql).
- Load CSV into staging and upsert/import (sql/002_staging_import.sql).
- Apply normalization map seed and approved revisions (sql/003_seed_normalization_map.sql).

Phase 4: Validate
- Reconcile yearly counts and yearly revenue totals against legacy.
- Validate report output parity for operational stakeholders.

Phase 5: Parallel run and cutover
- Run both systems for one publication cycle.
- Sign off on reconciliation and operational workflows.
- Retire Access with rollback window and archive snapshot.

## 8. Non-functional requirements

- Daily automated backups with restore test cadence
- Change auditability for pricing, billing, and run-date edits
- Role-based permissions and session security
- Basic observability (request logs, error tracking)
- CSV export capability for ad-hoc analysis
- Linux service hardening (systemd restart policy, Nginx reverse proxy, TLS)

## 9. Delivery slices

Slice A (foundation)
- Auth, account CRUD, lookup tables

Slice B (ad operations)
- Ad placement CRUD with normalized fields and validation

Slice C (reporting)
- Mailing labels and publication advertiser reports as PDFs

Slice D (self-service analysis)
- Filter builder, saved views, export

## 10. Risks and mitigations

Risk: Source data corruption during transition
Mitigation: Immediate hosting change and backup verification

Risk: Business rule ambiguity in free-text mappings
Mitigation: Owner-approved mapping tables and staged review

Risk: User rejection due to reduced flexibility
Mitigation: Include ad-hoc filtering/saved views in MVP

Risk: Hidden dependencies on AccountNumber
Mitigation: Preserve as immutable business key and inventory integrations early

Risk: Framework churn before cutover
Mitigation: Keep Flask baseline through migration; postpone framework migration decision

## 11. Open questions

1. Number of concurrent users and peak editing windows
2. Downstream consumers of reports and their format constraints
3. Duplicate advertiser resolution policy
4. External systems dependent on AccountNumber
5. Primary replacement driver (fragility, multi-user access, integration, reporting)
6. Is FastAPI still a mandatory target, or acceptable as post-cutover enhancement?

## 12. Success criteria

- No-loss migration validated by reconciliation
- Operational reporting accepted by users
- Stable multi-user operation without file-lock failures
- Access retirement completed after parallel-run signoff
- Production Linux service deployed with repeatable runbook
