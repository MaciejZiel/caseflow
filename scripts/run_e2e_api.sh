#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_PATH="/tmp/caseflow-e2e.db"
STORAGE_PATH="/tmp/caseflow-e2e-storage"
EMAIL_PATH="/tmp/caseflow-e2e-emails"

rm -f "${DB_PATH}"
rm -rf "${STORAGE_PATH}" "${EMAIL_PATH}"
mkdir -p "${STORAGE_PATH}" "${EMAIL_PATH}"

export APP_ENV="local"
export DATABASE_URL="sqlite+pysqlite:////tmp/caseflow-e2e.db"
export TEST_DATABASE_URL="sqlite+pysqlite:////tmp/caseflow-e2e.db"
export SECRET_KEY="caseflow-e2e-secret-key-with-32-plus-bytes"
export LOCAL_STORAGE_PATH="${STORAGE_PATH}"
export LOCAL_EMAIL_SINK_PATH="${EMAIL_PATH}"
export CORS_ALLOWED_ORIGINS="http://127.0.0.1:3001"
export TRUSTED_HOST_PATTERNS="127.0.0.1,localhost,testserver"

"${ROOT_DIR}/.venv/bin/python" -m alembic upgrade head

exec "${ROOT_DIR}/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8001
