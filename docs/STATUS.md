# CaseMind status

- **Current version:** v0.1 (Machine Detective MVP)
- **Current step:** 4. Feature spec v1 (not started; waiting for the user's OK)
- **Last updated:** 2026-11-09

## v0.1 checklist

The build order follows PRD Sections 14 and 9. "Exists, unaudited" means code from before this protocol that has not yet been checked against the PRD.

- [x] **1. Repo, tooling and core schemas.** uv, ruff, Makefile, Docker image and Compose stack; tier tags; per-field T3 canaries; ModelInference/Hypothesis; RevealedRelationship; T3 LieAnnotations; tier contract tests. *(Done 2026-11-09.)*
- [x] **2. Simulation engine.** Role-free sampler, noisy culprit choice, no culprit-only clues, coherent timelines, role-neutral wording, determinism (CH-03), reason strings (CH-02), full OOD range, 20 manor seeds hand-checked; `make audit-generator`. *(Done 2026-11-09.)*
- [x] **3. Structured contradiction checks.** Audited against PRD 6.4.B; "seen at some moment" semantics for observed people; `linked_source_ids`; point-in-time traces; travel-feasible schedules; `make audit-contradictions` (false-positive rate 0%, precision 100%, recall 52%). *(Done 2026-11-09.)*
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
- 2026-11-09, **step 3 done:** contradiction checker audited.
  - **Fewer false accusations.** Truthful innocents flagged 24% → 0%. The cause was the "I saw Y" rule reading "Y was there the whole time".
  - **Linked sources.** Flags now list every record the conflict rests on.
  - **Coherent world.** Forensic traces are point-in-time and schedules respect travel time, so the generator no longer makes impossible worlds.
  - **New evaluation.** `make audit-contradictions` reports precision, recall and false-positive rate with CIs.
  - **Tests.** 99 → 101.

## Next action

Write feature spec v1 (step 4): the written spec in `docs/FEATURES.md` plus deterministic, versioned feature functions over T1 only, with the exclusion list enforced in code.

## Generator audit (current numbers, `make audit-generator`, 400 cases)

Scores measure recovery of the generator's logic, not real-world skill.

**Best single trivial rule (top-1):** chance is 0.25.

| Rule | Top-1 |
|---|---|
| Crime-scene presence in the window | 0.63 |
| Motive evidence | 0.43 |
| Has a forensic trace | 0.43 |
| Validator's hand-weighted score | 0.36 |

These were all 1.00 before the step 2 redesign.

**Generator statistics:**
- Culprit lie rate 0.87 (configured 0.90).
- Honest-confusion rate 0.18.
- Checks 1–3 pass in 400 of 400 cases.
- 3.7% of cases have only one eligible culprit (known limitation).

## Contradiction layer (current numbers, `make audit-contradictions`, 400 cases, 1,600 claims)

- **False-positive rate: 0.0%** (95% Wilson CI 0–0.9%). **Precision: 100%. Recall: 52%.**
- **Flag rate by claim type:**

| Claim type | Flagged |
|---|---|
| Lying culprits | 95% |
| Honestly confused innocents | 52% |
| Red-herring evasions | 42% |
| COVER_FOR lies | 28% |
| Accurate claims | 0% |

## Step 4 notes (feature spec)

- **Corroboration flag.** Lying culprits never claim corroboration, while honest innocents often do. That is plausible behaviour, but it is a likely strong feature; watch for it in the leakage audit (step 8).
- **Weighting flags by reliability.** Contradiction features can weight each flag by the reliability of its linked records (`linked_source_ids`).

## Step 5 audit items

- **Artificial hard cases.** `DatasetGenerator._make_under_determined_variant` deletes only the culprit's scene traces to manufacture hard cases. Hard cases now occur naturally (D-010), and the deletion is itself a culprit-specific artefact. Likely remove it.

## Open questions / blockers

- **Cross-speaker contradictions?** The engine only compares a speaker with their *own* earlier claims (PRD 5.3 defines `claim_claim_conflicts` as self-contradiction). Comparing B's "I was with A at X" against A's "I was at Y" would catch many of the 72% of COVER_FOR lies that are missed now. It is a design choice; decide before step 4.

- **E. Templates.** Manor only for play, all 8 templates for dataset generation? (Decide by step 5.)
- **G. Abstention.** Simple threshold rule in v0.1 (step 7), E4 in v1.0?
- **PRD §17 Q4.** Which 3 hand-authored OOD cases are reserved? (Must be frozen before step 5.)
- **PRD PDF untracked.** Should `docs/CaseMind PRD v2.0.pdf` be committed so fresh clones have the spec?
