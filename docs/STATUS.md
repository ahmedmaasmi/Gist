# CaseMind status

- **Current version:** v0.1 (Machine Detective MVP)
- **Current step:** 2. Simulation engine audit (not started; waiting for the user's OK)
- **Last updated:** 2026-11-09

## v0.1 checklist

The build order follows PRD Sections 14 and 9. "Exists, unaudited" means code from before this protocol that has not yet been checked against the PRD.

- [x] **1. Repo, tooling and core schemas.** uv, ruff, Makefile, Docker image and Compose stack; tier tags; per-field T3 canaries; ModelInference/Hypothesis; RevealedRelationship; T3 LieAnnotations; tier contract tests. *(Done 2026-11-09.)*
- [ ] **2. Simulation engine.** Manor template with 4 characters; ARGUE, CONFIDE and COVER_FOR with reason strings; observation model (T1 facts, T2 knowledge); determinism test (CH-03); solvability check; hand-check 20 seeds; fix the OOD trait range. *(Largely exists, unaudited. See the step 2 audit items below.)*
- [ ] **3. Structured contradiction checks.** Time overlap, location exclusivity, travel feasibility, record mismatch; CLAIM_FACT and CLAIM_CLAIM flags with linked sources and explanations. *(Exists, unaudited. Moved before features because the conflict features depend on it.)*
- [ ] **4. Feature spec v1.** Written spec (`docs/FEATURES.md`) plus deterministic, versioned functions over T1 only; exclusion list enforced in code.
- [ ] **5. Dataset and splits.** Reveal orderings and evidence states; splits by case and by held-out template; grouped CV folds (group = template); at least 3 hand-authored OOD cases frozen before model work; dataset versioning; report the number of cases and the number of templates. *(Generator exists, unaudited.)*
- [ ] **6. Baselines and evaluation harness.** Random/prior, motive-plus-opportunity rule, symbolic timeline solver; top-1, top-2, MRR, log loss, Brier; 95% bootstrap CIs over cases; one command builds the table. *(Solver exists, unaudited.)*
- [ ] **7. Models.** Logistic Regression and LightGBM, within-case normalisation, calibration on validation, per-suspect explanations linked to evidence IDs (MD-08), heuristic fallback (MD-09), simple abstention rule (MD-06).
- [ ] **8. Leakage audit and E1.** Feature-name audit, shuffled-label control, single-feature models, permutation importance, reveal-artefact check; E1 ablation A/B/C plus leave-one-group-out.
- [ ] **9. Question policy and E3.** Slot-based question bank, scripted player simulator (honest innocent, lying guilty, evasive innocent, mixed), entropy policy vs random, fixed-order and top-two; budgets 3, 5 and 8.
- [ ] **10. API and minimal web UI.** FastAPI endpoints (reading through the `casemind_gameplay` role only); case page, claim builder, live ranking with explanations, verdict, results; contract and canary tests on every response.
- [ ] **11. Docker and README.** Compose stack already runs Postgres and a backend with `/health` (`make up`). Still to do: persistence layer, frontend container, README, `make` targets that reproduce every reported table.
- [ ] **12. Exit-gate check.** A stranger plays one case locally; one command reproduces the baseline table with CIs; the leakage audit passes; tag v0.1.0; README update; two-minute demo clip.

## Done so far

- 2026-11-09: Project memory set up (CLAUDE.md, STATUS, DECISIONS, /status, /wrapup).
- 2026-11-09, **step 1 done:**
  - **Tooling.** uv with a lockfile; ruff (87 findings fixed or removed); Makefile; backend Dockerfile; Compose service next to Postgres; `GET /health`.
  - **Schemas.**
    - `InformationTier` tags on T0–T3.
    - `canary.py`: deterministic, unique canaries for every T3 text field.
    - `T3Canonical` gains `seed`, `solution_summary`, `lie_annotations` and `canaries`.
    - `RevealedRelationship` in T1 (no hidden edge numbers).
    - `ModelInference` and `Hypothesis`.
  - **Leak fixed.** T1 relationship facts and `revealed_edges` exposed T3 affinity and obligation numbers.
  - **Bug fixed.** Culprit lies were never detectable as lies: a culprit who returned to their alibi location counted as truthful.
  - **Tests.** 45 → 83, all passing; Docker stack verified healthy; Postgres role isolation checked.
  - **Housekeeping.** `.env.exemple` renamed to `.env.example`; the `datasets` notes moved to `docs/notes/` (marked out of scope); typo directory removed.

## Next action

Audit the simulation engine (step 2): read `simulator.py` and `observation.py` against PRD 7A, investigate the step 2 audit items below, and hand-check 20 manor seeds.

## Step 2 audit items (found during step 1)

- **Culprit lie rate.** 24 of 24 sampled culprits lie, but `guilty_lie_rate` = 0.85. Is the solvability re-roll in `generate_valid_case` filtering out honest culprits? That would bias the E2 deception experiment.
- **Claim generation uses the last location in the window.** `true_murder_window_loc` drives claims for honest innocents, so an innocent who moved during the window makes an inaccurate claim. Is that an intended "honest confusion" or a bug?
- **Red-herring evasion location.** In manor seed 42, an evasive innocent claims to have been at the crime location (`loc_study`). Is that intended?
- **COVER_FOR is always mutual.** Every case has exactly 2 COVER_FOR lies. Is the rule too easy to trigger?
- **OOD trait range.** `CharacterTraits.check_ood` uses 0.1–0.9; PRD 8.2 wants the full editor range for both training sampling and OOD checks.

## Open questions / blockers

- **E. Templates.** Manor only for play, all 8 templates for dataset generation? (Decide by step 5.)
- **G. Abstention.** Simple threshold rule in v0.1 (step 7), E4 in v1.0?
- **PRD §17 Q4.** Which 3 hand-authored OOD cases are reserved? (Must be frozen before step 5.)
- **PRD PDF untracked.** Should `docs/CaseMind PRD v2.0.pdf` be committed so fresh clones have the spec?
