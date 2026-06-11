.PHONY: install test lint typecheck run-api run-frontend check docker-build docker-run clean

PYTHON = python3

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest tests/test_api.py tests/test_admin.py tests/test_admin_alert.py tests/test_pipeline.py -v

test-all:
	$(PYTHON) -m pytest tests/ -v --tb=short

lint:
	ruff check src/ tests/

typecheck:
	mypy src/

check: lint typecheck test

run-api:
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

run-frontend:
	cd frontend && npm install && npm run dev

frontend-build:
	cd frontend && npm install && npm run build

run-pipeline-worker:
	taskiq worker src.workers.pipeline_worker:broker

docker-build:
	docker compose build

docker-run:
	docker compose up

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .mypy_cache dist build frontend/dist
