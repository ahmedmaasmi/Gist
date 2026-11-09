# CaseMind

CaseMind is a murder-mystery ML platform. A seeded, rule-based social simulation
(characters, relationships, interactions) generates closed-world cases with a hidden
true timeline. In Mode 1 (Machine Detective) a trained suspect ranker, a structured
consistency engine and an entropy-based question policy investigate a human player who
plays a suspect. The project's goal is that every claim about the system's intelligence
is backed by a reproducible measurement. Full spec: `docs/CaseMind PRD v2.0.pdf`
(the file name says v2.0, the content is **v3.0**; treat it as v3.0).

## Session protocol

a. Read `docs/STATUS.md` first (and `docs/DECISIONS.md` when context is needed).
b. Tell the user in plain English where we are and what the next step is, then **wait for their OK**.
c. Work on **one** checklist step at a time. Within a step, work in small sub-steps and explain each one.
d. When a step (or sub-step) is done: run tests, update `docs/STATUS.md`, append decisions to `docs/DECISIONS.md`,
   **append a section to `docs/JOURNAL.md`** explaining in plain language what changed, why, how, the concepts
   behind it and the numbers it produced, then make **one** git commit.

## Hard rules (from the PRD)

- Current scope is **v0.1 only**: no LLM, no Case Lab, no NLI, no cloud deployment.
- **T3 data** (culprit, true timeline, hidden edges, lie annotations, undiscovered evidence)
  never appears in features, API responses, logs or prompts. Canary tests enforce this.
- Splits are **by case and by template**; all evidence states of a case stay in one split.
- Fixed seeds everywhere; **one documented command per experiment**.
- Never cut: baselines, the leakage audit, E1, E3.
- Every report states that scores on synthetic data measure **recovery of the generator's logic**.

## Working style

- The user is an MSc ML student: explain what you do and why, in plain language.
- Never run ahead of the user. No code without an approved plan for the step.
- If the PRD is ambiguous or you disagree with it, say so; do not silently pick.
- Existing code (pre-dating this protocol) is kept but **audited** against the PRD at the start of each step.

## Layout and commands

- Python project: `backend/` (package `app`: `domain/`, `engine/`), managed by **uv** (`backend/uv.lock`, Python 3.12).
  Templates in `data/templates/`.
- `make install` · `make test` · `make lint` · `make fmt` (from the repo root).
- `make audit-generator`: shortcut audit of the case generator → `reports/generator_audit.json`.
- `make audit-contradictions`: precision/recall/false-positive rate of the contradiction layer → `reports/contradiction_audit.json`.
- `make dataset`: builds the versioned dataset → `data/generated/v<version>/` (gitignored; checksums in `manifest.json`).
- `make baselines`: baseline table with 95% CIs → `reports/baselines.{json,md}` (needs `make dataset`).
- `make models`: tune (grouped CV on train), calibrate (val), select the ranker → `reports/models_val.{json,md}`, artefacts in `ml/artifacts/` (gitignored). **Test splits stay sealed until the step 8 leakage audit passes.**
- `make audit-leakage`: PRD 8.8 audit on train/val → `reports/leakage_audit.{json,md}` (must pass before any test evaluation).
- `make e1`: E1 ablation (hypotheses pre-registered in `docs/EXPERIMENTS.md`). `make final-eval`: **one-time** test evaluation, already run for `lightgbm-6d50342630`; do not re-run to tune anything.
- Play-time ranking: `app/ml/ranker.Ranker` (`load()`, `rank(t0, t1, setting)`, `counterfactual(...)`); falls back to the rule if no model loads.
- Art: style reference and portrait prompts in `docs/art/`.
- `make up` / `make down`: Postgres + backend in Docker Compose; API on http://localhost:8000/health.
- Storage is **PostgreSQL in Docker** (user decision D-005, deviates from PRD's JSON/SQLite):
  role `casemind_gameplay` has no access to schema `t3_canonical`; only `casemind_vault` does.
- T3 isolation tests: `tests/test_canary.py`, `tests/test_tier_contracts.py`, `tests/test_lie_annotations.py`.
