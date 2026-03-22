PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip

.PHONY: install lint format test migrate run seed-demo docker-up docker-down

install:
	$(PIP) install -e ".[dev]"

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

seed-demo:
	$(PYTHON) scripts/seed_demo_data.py

docker-up:
	docker compose up --build

docker-down:
	docker compose down -v
