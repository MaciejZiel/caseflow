# CaseFlow

CaseFlow is a production-like multi-tenant B2B backend for case and document processing.
It is built as a modular monolith with FastAPI, SQLAlchemy and Alembic, with explicit focus on:

- tenant isolation by `organization_id`
- RBAC for organizations, members, cases, documents and webhooks
- organization-scoped API keys for system-to-system integrations
- session-backed auth with refresh rotation, logout and password reset
- versioned document uploads with processing jobs
- review workflow for documents
- audit logs, webhook delivery history and outbound email outbox
- operational basics: health, readiness, metrics, structured logging, Docker, workers, CI and
  deployment-oriented request hardening

## Implemented Features

- organization registration with first owner account
- JWT login, refresh, logout and password reset
- auth session listing, per-session revocation, device naming and last-seen activity tracking
- invitation flow and membership management
- tenant-scoped case CRUD with archive flow
- case comments
- document uploads, versioning and configurable inline-or-worker job execution
- document approve/reject workflow with case status transitions
- retry worker for failed processing jobs, webhook deliveries and email outbox messages
- audit log for cases and documents
- webhook endpoints, event subscriptions, replay tooling, HMAC-signed deliveries and delivery history
- pluggable email delivery backends with local sink and SMTP adapter
- organization API keys with scoped read-only integration endpoints
- case summary reporting, case search and CSV export surfaces
- security headers, trusted host filtering, opt-in proxy header trust and CORS allowlists
- organization operations summary, failure inspection and scoped retry-due maintenance endpoints
- retention preview/run endpoints for old delivered webhooks and sent outbound emails
- platform admin overview, anomaly detection, risk reporting, tenant activity feed and bulk lifecycle controls
- demo data seeding script for a ready-to-show local environment
- Alembic migrations and integration tests

## API Highlights

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/logout-all`
- `GET /api/v1/auth/sessions`
- `PATCH /api/v1/auth/sessions/{session_id}`
- `DELETE /api/v1/auth/sessions/{session_id}`
- `POST /api/v1/auth/password-reset/request`
- `POST /api/v1/auth/password-reset/confirm`
- `GET /api/v1/me`
- `POST /api/v1/api-keys`
- `GET /api/v1/api-keys`
- `POST /api/v1/api-keys/{api_key_id}/revoke`
- `GET /api/v1/admin/organizations`
- `GET /api/v1/admin/organizations/{organization_id}`
- `GET /api/v1/admin/organizations/{organization_id}/activity`
- `POST /api/v1/admin/organizations/bulk-status`
- `GET /api/v1/admin/overview`
- `GET /api/v1/admin/anomalies`
- `GET /api/v1/admin/risk-report`
- `GET /api/v1/admin/exports/organizations.csv`
- `GET /api/v1/admin/failures`
- `POST /api/v1/admin/organizations/{organization_id}/suspend`
- `POST /api/v1/admin/organizations/{organization_id}/reactivate`
- `POST /api/v1/admin/retry-due`
- `GET /api/v1/reports/cases/summary`
- `GET /api/v1/search/cases`
- `GET /api/v1/operations/summary`
- `GET /api/v1/operations/failures`
- `POST /api/v1/operations/retry-due`
- `GET /api/v1/operations/retention-preview`
- `POST /api/v1/operations/retention-run`
- `POST /api/v1/organizations/current/invitations`
- `GET /api/v1/organizations/current/members`
- `GET /api/v1/integrations/cases`
- `GET /api/v1/integrations/cases/{case_id}`
- `GET /api/v1/integrations/cases/{case_id}/documents`
- `GET /api/v1/integrations/exports/cases.csv`
- `GET /api/v1/integrations/documents/{document_id}`
- `POST /api/v1/cases`
- `POST /api/v1/cases/{case_id}/comments`
- `GET /api/v1/cases/{case_id}/audit-log`
- `POST /api/v1/cases/{case_id}/documents`
- `POST /api/v1/documents/{document_id}/versions`
- `POST /api/v1/documents/{document_id}/approve`
- `POST /api/v1/documents/{document_id}/reject`
- `POST /api/v1/documents/{document_id}/jobs/{job_id}/retry`
- `GET /api/v1/documents/{document_id}/audit-log`
- `POST /api/v1/webhooks/endpoints`
- `PATCH /api/v1/webhooks/endpoints/{endpoint_id}`
- `GET /api/v1/webhooks/deliveries`
- `POST /api/v1/webhooks/deliveries/{delivery_id}/retry`
- `POST /api/v1/webhooks/deliveries/{delivery_id}/replay`
- `GET /health`
- `GET /ready`
- `GET /metrics`

## Local Development

1. Create or reuse `.venv`.
2. Install dependencies with `make install`.
3. Copy `.env.example` to `.env` and adjust values if needed.
4. Apply migrations with `make migrate`.
5. Start the API with `make run`.
6. Optionally preload a ready-to-demo workspace with `make seed-demo`.
7. Run the retry worker with `make retry-worker` or a single cycle with `make retry-worker-once`.
8. Pick delivery modes in `.env` if you want workers or SMTP instead of local inline flows.
9. Tune `AUTH_SESSION_ACTIVITY_UPDATE_INTERVAL_SECONDS` if you want less or more frequent
   session activity writes.
10. Set `CORS_ALLOWED_ORIGINS` and `TRUSTED_HOST_PATTERNS` as JSON arrays before putting the API
    behind a real frontend or public ingress.
11. Enable `TRUST_PROXY_HEADERS` only when the app runs behind a trusted reverse proxy.
12. Promote a platform admin with `make promote-superuser EMAIL=owner@example.com` if you need
    access to `/api/v1/admin/*`.
13. Tune `ADMIN_FAILURE_ANOMALY_THRESHOLD` and `ADMIN_QUEUE_STALE_HOURS` if you want stricter or
    looser platform anomaly detection.
14. Run checks with `make lint` and `make test`.

## Demo Dataset

Run `make seed-demo` after migrations to create:

- one demo organization: `demo-claims`
- owner, admin, reviewer and member accounts with preset passwords
- approved, rejected, failed-processing and archived cases
- multi-version document history, comments and an inactive webhook endpoint

The script prints a JSON summary with seeded credentials, case references and storage location.
It refuses to overwrite an existing demo dataset unless you pass `--replace-existing` directly to
`scripts/seed_demo_data.py`.

## Local Email Sink

Invitation and password reset emails go through the persisted outbox and can be delivered with:

- `EMAIL_DELIVERY_BACKEND=local` writing JSON payloads to `LOCAL_EMAIL_SINK_PATH`
- `EMAIL_DELIVERY_BACKEND=smtp` using `SMTP_*` settings for real delivery

`EMAIL_DELIVERY_MODE=sync` sends immediately during the request path.
`EMAIL_DELIVERY_MODE=worker` leaves messages pending for the retry worker.

## Worker Modes

CaseFlow can run synchronously for a simple local setup or defer side effects to the worker:

- `DOCUMENT_PROCESSING_MODE=inline|worker`
- `WEBHOOK_DELIVERY_MODE=sync|worker`
- `EMAIL_DELIVERY_MODE=sync|worker`

When a `worker` mode is enabled, records are persisted first and processed by
`scripts/run_retry_worker.py` / `make retry-worker`.

## Docker

1. Copy `.env.example` if you want a local reference for settings.
2. Start the stack with `make docker-up`.
3. API will be available on `http://127.0.0.1:8000`.
4. Stop and remove data volumes with `make docker-down`.

The Docker stack currently includes:

- `api` running FastAPI with migrations on startup
- `db` running PostgreSQL 17
- persistent storage volume for uploaded documents

## Testing

Current verification baseline:

- `make lint`
- `make test`
- `alembic upgrade head` on a clean SQLite database
- retry worker cycle through `scripts/run_retry_worker.py`
- GitHub Actions workflow in `.github/workflows/ci.yml` running lint, tests and PostgreSQL migration verification

Integration tests cover:

- auth session lifecycle, device metadata and password reset
- API key management and tenant-scoped integration access
- case reporting, search and CSV export
- operational summary, failures and maintenance retry endpoints
- platform admin overview, anomaly detection, risk reporting, activity feed and bulk lifecycle controls
- retention preview and cleanup controls
- email outbox and local sink delivery
- demo data seeding
- auth and invitations
- tenant isolation for cases and documents
- document processing and review workflow
- audit log generation
- webhook delivery success and failure handling
- worker-driven retries for due failures

## Current Architecture Notes

- The project uses shared-schema multi-tenancy with explicit query scoping.
- Access tokens are short-lived JWTs bound to persisted auth sessions for immediate logout support.
- Auth sessions keep stable client metadata, rolling `last_seen_*` activity snapshots and optional
  user-defined device names.
- API keys are hashed at rest, scoped per organization and exposed through dedicated integration
  endpoints instead of broad write access to the main app API.
- Reporting and search stay tenant-scoped and reuse the same domain model instead of creating a
  second analytics datastore too early.
- Webhook endpoints can subscribe to selected event types, while replay creates a fresh delivery
  record instead of mutating historical delivery state.
- Maintenance endpoints stay organization-scoped and reuse the same retry machinery as the worker
  instead of introducing a second execution path.
- Platform admin endpoints stay explicitly superuser-only and can suspend tenants without leaving
  their existing auth sessions reusable after reactivation.
- Platform-wide retry uses the same persisted queues as organization-scoped maintenance and the
  background worker, so operational behavior does not fork between code paths.
- Platform anomaly detection is query-driven over real tenant state, so it can flag ownerless
  organizations, stale worker backlogs and inconsistent inactive tenants without a separate rules
  engine.
- Platform risk reporting reuses anomaly scoring plus tenant health counters, so operators can sort
  tenants by urgency and export the same snapshot as CSV without duplicating logic elsewhere.
- Superuser access is managed explicitly through a dedicated service and script instead of being
  hardcoded into registration or environment-only bootstrap logic.
- Retention cleanup is explicit and previewable, so old operational records can be pruned without
  blind deletes.
- Proxy-derived client metadata is opt-in, while CORS and host filtering stay configuration-driven
  for deployment safety.
- Document processing, webhook delivery and outbound emails can run inline for local simplicity or via
  persisted worker queues for asynchronous execution.
- Webhook deliveries and emails use persisted outbox records with retry scheduling.
- Storage uses a local filesystem adapter behind a storage abstraction.

## Next High-Value Steps

- internal admin UI for platform operators
- deeper tenant analytics and anomaly detection
