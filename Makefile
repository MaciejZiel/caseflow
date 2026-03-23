PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip

.PHONY: install install-all frontend-install lint format test migrate run frontend-dev frontend-lint frontend-build seed-demo retry-worker-once retry-worker promote-superuser docker-up docker-down

install:
	$(PIP) install -e ".[dev]"

install-all: install frontend-install

frontend-install:
	npm --prefix frontend install

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m ruff format .

test:
	$(PYTHON) -m pytest

migrate:
	$(PYTHON) -m alembic upgrade head

run:
	$(PYTHON) -m uvicorn app.main:app --reload

frontend-dev:
	npm --prefix frontend run dev

frontend-lint:
	npm --prefix frontend run lint

frontend-build:
	npm --prefix frontend run build

seed-demo:
	$(PYTHON) scripts/seed_demo_data.py

retry-worker-once:
	$(PYTHON) scripts/run_retry_worker.py

retry-worker:
	$(PYTHON) scripts/run_retry_worker.py --loop

promote-superuser:
	$(PYTHON) scripts/set_superuser.py --email "$(EMAIL)"

docker-up:
	docker compose up --build

docker-down:
	docker compose down -v
