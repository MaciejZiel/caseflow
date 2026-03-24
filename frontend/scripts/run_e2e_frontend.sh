#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${ROOT_DIR}"
export NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8001"

exec npm run dev -- --hostname 127.0.0.1 --port 3001
