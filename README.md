# CaseFlow

CaseFlow is a production-like multi-tenant B2B backend for case and document processing.
The project is being built as a modular monolith with FastAPI, SQLAlchemy and PostgreSQL,
with explicit focus on tenant isolation, RBAC, async document workflows, auditability and
operational readiness.

## Implemented So Far

- project scaffold and developer tooling
- FastAPI app factory with structured logging, request IDs and metrics
- liveness and readiness probes
- SQLAlchemy foundation and Alembic configuration
- core identity schema for organizations, users and memberships
- organization registration with first owner account
- login and current session endpoint

## Planned Stack

- Python 3.13
- FastAPI
- SQLAlchemy 2.x
- Alembic
- PostgreSQL
- Redis
- pytest
- Ruff

## Local Development

1. Create or reuse `.venv`.
2. Install dependencies with `make install`.
3. Apply migrations with `make migrate`.
4. Start the API with `make run`.
5. Run tests with `make test`.

## Next Milestones

- refresh tokens and logout
- invitations and membership management
- RBAC enforcement for organization actions
- case CRUD with tenant isolation
