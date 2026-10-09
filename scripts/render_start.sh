#!/usr/bin/env sh
# Start command for the Render web service (see render.yaml).
#
# Render's free instances have no pre-deploy hook and an ephemeral filesystem,
# so migrations run here and, when SEED_DEMO_DATA=true, the demo workspace is
# recreated on every boot. That keeps the seeded documents in local storage and
# their database rows in sync after a restart or spin-down.
set -eu

python -m alembic upgrade head

if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
    python scripts/seed_demo_data.py --replace-existing > /dev/null
    echo "Demo workspace 'demo-claims' recreated."
fi

exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
