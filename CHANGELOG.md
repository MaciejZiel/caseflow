# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-10

First tagged release.

### Added

- Multi-tenant FastAPI backend on a shared PostgreSQL schema: organization
  registration, invitations, membership management and role-based access
  control enforced in the service layer.
- Authentication with short-lived JWTs bound to persisted sessions: refresh
  token rotation, logout and logout-all, per-session revocation, device names,
  last-seen tracking and password reset.
- Scoped organization API keys for read-only integrations.
- Cases with comments, archiving and audit logs; versioned document uploads
  with inline or worker processing and an approve / reject review flow.
- Persisted work records for document jobs, HMAC-signed webhook deliveries and
  outbound email (local sink or SMTP), with a retry worker, manual retries and
  webhook replay.
- Reporting, search and CSV exports; organization operations summary, failure
  inspection and previewable retention cleanup.
- Platform administration: overview, anomaly and activity feeds, risk reports,
  tenant suspension and bulk lifecycle actions, a review queue with assignees,
  due dates, auto-opening, auto-assignment and overdue escalation, and operator
  notifications with scheduled digests.
- Deterministic case assistant that ranks the case's documents and comments
  and answers with stored citations, in four prompt modes.
- Next.js 16 workspace: sign-in and registration, operations dashboard, case
  workbench with document uploads and the assistant thread.
- Demo data seeding (`make seed-demo`, `make docker-seed-demo`) and a superuser
  promotion script.
- Docker Compose setup for the API, frontend and PostgreSQL, and a Render
  Blueprint for free-tier deployment.
- Operational hardening: security headers, trusted hosts, CORS allowlist,
  opt-in proxy header trust, structured JSON logs, Prometheus metrics, health
  and readiness probes.
- 148 pytest tests with full line coverage of `app/`, plus Playwright
  end-to-end scenarios for the frontend.
- CodeQL code scanning for Python and TypeScript, and Dependabot updates for
  pip, npm, Docker and GitHub Actions.

### Changed

- The codebase is formatted with `ruff format`, and CI fails on unformatted
  files.
- The landing page no longer shows invented case and document counts.

[1.0.0]: https://github.com/MaciejZiel/caseflow/releases/tag/v1.0.0
