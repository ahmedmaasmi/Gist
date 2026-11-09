# CaseMind — one entry point per task. Python tooling runs through uv inside backend/.
.PHONY: install test lint fmt up down logs audit-generator audit-contradictions

install:  ## Install locked dependencies (incl. dev tools) into backend/.venv
	cd backend && uv sync

test:     ## Run the test suite
	cd backend && uv run pytest -q

lint:     ## Lint (ruff)
	cd backend && uv run ruff check .

fmt:      ## Auto-fix lint issues and format code
	cd backend && uv run ruff check --fix . && uv run ruff format .

up:       ## Build and start Postgres + backend in Docker
	docker compose up --build -d

down:     ## Stop the Docker stack (data volume is kept)
	docker compose down

logs:     ## Follow backend logs
	docker compose logs -f backend

audit-generator:  ## Shortcut audit of the case generator (PRD 8.2); writes reports/generator_audit.json
	cd backend && uv run python -m app.evaluation.generator_audit --out ../reports/generator_audit.json

audit-contradictions:  ## Precision / recall / false-positive rate of the structured contradiction layer
	cd backend && uv run python -m app.evaluation.contradiction_audit --out ../reports/contradiction_audit.json
