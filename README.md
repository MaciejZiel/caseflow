# CaseFlow

CaseFlow is a production-like multi-tenant B2B backend for case and document processing.
It is built as a modular monolith with FastAPI, SQLAlchemy and Alembic, with explicit focus on:

- tenant isolation by `organization_id`
- RBAC for organizations, members, cases, documents and webhooks
- versioned document uploads with processing jobs
- review workflow for documents
- audit logs and webhook delivery history
- operational basics: health, readiness, metrics, structured logging and Docker

## Implemented Features

- organization registration with first owner account
- JWT login and current session endpoint
- invitation flow and membership management
- tenant-scoped case CRUD with archive flow
- document uploads, versioning and in-process job execution
- document approve/reject workflow with case status transitions
- audit log for cases and documents
- webhook endpoints, HMAC-signed deliveries and delivery history
- Alembic migrations and integration tests

## API Highlights

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/me`
- `POST /api/v1/organizations/current/invitations`
- `GET /api/v1/organizations/current/members`
- `POST /api/v1/cases`
- `GET /api/v1/cases/{case_id}/audit-log`
- `POST /api/v1/cases/{case_id}/documents`
- `POST /api/v1/documents/{document_id}/versions`
- `POST /api/v1/documents/{document_id}/approve`
- `POST /api/v1/documents/{document_id}/reject`
- `GET /api/v1/documents/{document_id}/audit-log`
- `POST /api/v1/webhooks/endpoints`
- `GET /api/v1/webhooks/deliveries`
- `GET /health`
- `GET /ready`
- `GET /metrics`

## Local Development

1. Create or reuse `.venv`.
2. Install dependencies with `make install`.
3. Copy `.env.example` to `.env` and adjust values if needed.
4. Apply migrations with `make migrate`.
5. Start the API with `make run`.
6. Run checks with `make lint` and `make test`.

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

Integration tests cover:

- auth and invitations
- tenant isolation for cases and documents
- document processing and review workflow
- audit log generation
- webhook delivery success and failure handling

## Current Architecture Notes

- The project uses shared-schema multi-tenancy with explicit query scoping.
- Document processing is currently implemented as an in-process worker flow to keep the system self-contained.
- Webhook deliveries are persisted and dispatched synchronously after event publication.
- Storage uses a local filesystem adapter behind a storage abstraction.

## Next High-Value Steps

- case comments
- retry scheduler / dedicated worker process for failed jobs and failed webhook deliveries
- refresh tokens, logout and password reset
- seed/demo data scripts
- CI pipeline and deployment-oriented docs
