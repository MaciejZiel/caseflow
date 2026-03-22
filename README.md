# CaseFlow

CaseFlow is a production-like multi-tenant B2B backend for case and document processing.
It is built as a modular monolith with FastAPI, SQLAlchemy and Alembic, with explicit focus on:

- tenant isolation by `organization_id`
- RBAC for organizations, members, cases, documents and webhooks
- session-backed auth with refresh rotation, logout and password reset
- versioned document uploads with processing jobs
- review workflow for documents
- audit logs, webhook delivery history and outbound email outbox
- operational basics: health, readiness, metrics, structured logging, Docker, workers and CI

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
- webhook endpoints, HMAC-signed deliveries and delivery history
- pluggable email delivery backends with local sink and SMTP adapter
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
- `POST /api/v1/organizations/current/invitations`
- `GET /api/v1/organizations/current/members`
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
- `GET /api/v1/webhooks/deliveries`
- `POST /api/v1/webhooks/deliveries/{delivery_id}/retry`
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
10. Run checks with `make lint` and `make test`.

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
- Document processing, webhook delivery and outbound emails can run inline for local simplicity or via
  persisted worker queues for asynchronous execution.
- Webhook deliveries and emails use persisted outbox records with retry scheduling.
- Storage uses a local filesystem adapter behind a storage abstraction.

## Next High-Value Steps

- deployment-oriented docs and environment hardening
- API keys and system-to-system integrations
