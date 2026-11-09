# CaseMind status

- **Current version:** v0.1 (Machine Detective MVP)
- **Current step:** 3. Structured contradiction checks audit (not started; waiting for the user's OK)
- **Last updated:** 2026-11-09

## v0.1 checklist

The build order follows PRD Sections 14 and 9. "Exists, unaudited" means code from before this protocol that has not yet been checked against the PRD.

- [x] **1. Repo, tooling and core schemas.** uv, ruff, Makefile, Docker image and Compose stack; tier tags; per-field T3 canaries; ModelInference/Hypothesis; RevealedRelationship; T3 LieAnnotations; tier contract tests. *(Done 2026-11-09.)*
- [x] **2. Simulation engine.** Role-free sampler, noisy culprit choice, no culprit-only clues, coherent timelines, role-neutral wording, determinism (CH-03), reason strings (CH-02), full OOD range, 20 manor seeds hand-checked; `make audit-generator`. *(Done 2026-11-09.)*
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
- 2026-11-09, **step 2 done:** found and fixed a generator in which trivial rules recovered the culprit 100% of the time.
  - **Sampler.** Role-free sampler; culprit chosen by softmax (temperature 0.5) among suspects with a motive and a possible route.
  - **No culprit-only clues.** Records can be missing for anyone, including the culprit; forensic traces exist for any visitor to the scene.
  - **Neutral evidence.** Same motive wording for culprit and innocents; one shared alibi phrase pool.
  - **Bug fixes.** COVER_FOR used the wrong edge direction and was forced; evasive innocents claimed the crime scene; culprits teleported (records are now points in time).
  - **Check 4** labels difficulty instead of filtering.
  - **Audit and tests.** Generator audit script plus report; tests 84 → 99.

## Next action

Audit the structured consistency engine (step 3) against PRD 6.4.B, starting with the interval-semantics items below.

## Generator audit (current numbers, `make audit-generator`, 400 cases)

Scores measure recovery of the generator's logic, not real-world skill.

**Best single trivial rule (top-1):** chance is 0.25.

| Rule | Top-1 |
|---|---|
| Crime-scene presence in the window | 0.64 |
| Motive evidence | 0.42 |
| Has a forensic trace | 0.42 |
| Validator's hand-weighted score | 0.39 |

These were all 1.00 before the step 2 redesign.

**Generator statistics:**
- Culprit lie rate 0.905 (configured 0.90).
- Honest-confusion rate 0.23.
- Checks 1–3 pass in 398 of 400 cases.
- 8.7% of cases have only one eligible culprit (known limitation).

## Step 3 audit items (found during steps 1–2)

- **Touching intervals overlap.** `TimeInterval.overlaps` treats intervals that only touch (e.g. [1250,1260] and [1260,1280]) as overlapping. Check whether the consistency engine and the observation window logic should use a positive overlap instead.
- **Point-in-time records.** Movement records are now `[t, t]` (D-012). Check every consistency rule against zero-length intervals.
- **Corroboration flag.** Lying culprits never claim corroboration, while honest innocents often do. That is plausible behaviour, but note it for the feature spec (step 4) as a likely strong feature.

## Step 5 audit items

- **Artificial hard cases.** `DatasetGenerator._make_under_determined_variant` deletes only the culprit's scene traces to manufacture hard cases. Hard cases now occur naturally (D-010), and the deletion is itself a culprit-specific artefact. Likely remove it.

## Open questions / blockers

- **E. Templates.** Manor only for play, all 8 templates for dataset generation? (Decide by step 5.)
- **G. Abstention.** Simple threshold rule in v0.1 (step 7), E4 in v1.0?
- **PRD §17 Q4.** Which 3 hand-authored OOD cases are reserved? (Must be frozen before step 5.)
- **PRD PDF untracked.** Should `docs/CaseMind PRD v2.0.pdf` be committed so fresh clones have the spec?
