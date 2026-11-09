# CaseMind — one entry point per task. Python tooling runs through uv inside backend/.
.PHONY: install test lint fmt up down logs audit-generator audit-contradictions dataset baselines models audit-leakage e1 final-eval

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

dataset:  ## Build the versioned dataset (1,500 cases + 150 shifted OOD) into data/generated/v<version>/
	cd backend && uv run python -m app.engine.dataset_generator --out ../data/generated

baselines:  ## Baseline table with 95% bootstrap CIs (needs `make dataset` first) -> reports/baselines.{json,md}
	cd backend && uv run python -m app.evaluation.baseline_report

models:  ## Tune (grouped CV on train), calibrate (val) and select the ranker -> reports/models_val.{json,md}
	cd backend && uv run python -m app.evaluation.model_report

audit-leakage:  ## Leakage and shortcut audit (PRD 8.8) on train/val -> reports/leakage_audit.{json,md}
	cd backend && uv run python -m app.evaluation.leakage_audit

e1:  ## E1 feature ablation (PRD 9.1; pre-registered in docs/EXPERIMENTS.md) -> reports/e1.{json,md}
	cd backend && uv run python -m app.evaluation.e1_ablation

final-eval:  ## ONE-TIME test evaluation of the selected model (needs a passed leakage audit) -> reports/final_test.{json,md}
	cd backend && uv run python -m app.evaluation.final_eval
