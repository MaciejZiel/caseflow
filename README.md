# CaseFlow

CaseFlow is a production-like multi-tenant B2B backend for case and document processing.
The project is being built as a modular monolith with FastAPI, SQLAlchemy and PostgreSQL,
with explicit focus on tenant isolation, RBAC, async document workflows, auditability and
operational readiness.

## Current Scope

The repository currently contains the foundational project structure and developer tooling.
The next implementation slices are:

1. runtime foundation and health endpoints
2. database layer and migrations
3. organization registration with first owner account
4. authentication and tenant-aware case workflows

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
3. Start the API with `make run`.
4. Run tests with `make test`.
