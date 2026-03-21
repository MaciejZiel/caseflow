PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip

.PHONY: install lint format test run

install:
	$(PIP) install -e ".[dev]"

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m ruff format .

test:
	$(PYTHON) -m pytest

run:
	$(PYTHON) -m uvicorn app.main:app --reload
