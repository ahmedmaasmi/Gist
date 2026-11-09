# CaseMind status

- **Current version:** v0.1 (Machine Detective MVP)
- **Current step:** 1. Repo, tooling and core schemas (plan proposed, awaiting approval)
- **Last updated:** 2026-11-09

## v0.1 checklist

The build order follows PRD Sections 14 and 9. "Exists, unaudited" means code from before this protocol that has not yet been checked against the PRD.

- [ ] **1. Repo, tooling and core schemas.** uv, ruff, pytest, Makefile; Fact, Claim, provenance and verification enums, tiers T0–T3, per-field T3 canaries, ModelInference/Hypothesis types, tier contract tests. *(Partly exists, unaudited.)*
- [ ] **2. Simulation engine.** Manor template with 4 characters; ARGUE, CONFIDE and COVER_FOR with reason strings; observation model (T1 facts, T2 knowledge); determinism test (CH-03); solvability check; hand-check 20 seeds; fix the OOD trait range. *(Largely exists, unaudited.)*
- [ ] **3. Structured contradiction checks.** Time overlap, location exclusivity, travel feasibility, record mismatch; CLAIM_FACT and CLAIM_CLAIM flags with linked sources and explanations. *(Exists, unaudited. Moved before features because the conflict features depend on it.)*
- [ ] **4. Feature spec v1.** Written spec (`docs/FEATURES.md`) plus deterministic, versioned functions over T1 only; exclusion list enforced in code.
- [ ] **5. Dataset and splits.** Reveal orderings and evidence states; splits by case and by held-out template; grouped CV folds (group = template); at least 3 hand-authored OOD cases frozen before model work; dataset versioning; report the number of cases and the number of templates. *(Generator exists, unaudited.)*
- [ ] **6. Baselines and evaluation harness.** Random/prior, motive-plus-opportunity rule, symbolic timeline solver; top-1, top-2, MRR, log loss, Brier; 95% bootstrap CIs over cases; one command builds the table. *(Solver exists, unaudited.)*
- [ ] **7. Models.** Logistic Regression and LightGBM, within-case normalisation, calibration on validation, per-suspect explanations linked to evidence IDs (MD-08), heuristic fallback (MD-09), simple abstention rule (MD-06).
- [ ] **8. Leakage audit and E1.** Feature-name audit, shuffled-label control, single-feature models, permutation importance, reveal-artefact check; E1 ablation A/B/C plus leave-one-group-out.
- [ ] **9. Question policy and E3.** Slot-based question bank, scripted player simulator (honest innocent, lying guilty, evasive innocent, mixed), entropy policy vs random, fixed-order and top-two; budgets 3, 5 and 8.
- [ ] **10. API and minimal web UI.** FastAPI endpoints; case page, claim builder, live ranking with explanations, verdict, results; contract and canary tests on every response.
- [ ] **11. Local Docker and README.** Docker Compose with JSON/SQLite storage, health check, `make` targets that reproduce every reported table.
- [ ] **12. Exit-gate check.** A stranger plays one case locally; one command reproduces the baseline table with CIs; the leakage audit passes; tag v0.1.0; README update; two-minute demo clip.

## Done so far

- 2026-11-09: Project memory set up (CLAUDE.md, STATUS, DECISIONS, /status, /wrapup).
- Pre-existing code (unaudited; 45 tests pass):
  - domain models (`backend/app/domain/`);
  - simulator, observation model, solver and validator, consistency engine, reveal sampler, dataset generator (`backend/app/engine/`);
  - 8 setting templates (`data/templates/`).

## Next action

Get the user's approval of the step 1 plan (tooling plus schema gaps) and their answers to open questions A–D, then start sub-step 1a (tooling).

## Open questions / blockers

- **A. Storage for v0.1.** JSON files (recommended) or SQLite? Postgres config exists but is out of v0.1 scope.
- **B. Canary semantics.** Per-field canaries for T3 text fields, plus structural contract tests for ID and number fields (recommended).
- **C. T1 relationships.** Replace raw `RelationshipEdge` in T1 with `RevealedRelationship` (tags plus evidence ID)?
- **D. Lies.** Store INTENTIONAL_LIE as a T3 `LieAnnotation`, never on the T1 Claim?
- **E. Templates.** Manor only for play, all 8 templates for dataset generation? (Decide by step 5.)
- **G. Abstention.** Simple threshold rule in v0.1 (step 7), E4 in v1.0?
- **H. OOD trait range.** Currently 0.1–0.9; the PRD wants the full editor range. (Step 2.)
- **PRD §17 Q4.** Which 3 hand-authored OOD cases are reserved? (Must be frozen before step 5.)
- **Tooling.** uv is not installed; the user needs to run `brew install uv`.
