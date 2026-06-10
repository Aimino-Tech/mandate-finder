.PHONY: install test lint typecheck run docker-build docker-run clean

PYTHON = python3

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest tests/ -v

lint:
	ruff check src/ tests/

typecheck:
	mypy src/

check: lint typecheck test

run:
	uvicorn market_intelligence.main:app --reload --host 0.0.0.0 --port 8000

docker-build:
	docker compose build

docker-run:
	docker compose up

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .mypy_cache dist build
