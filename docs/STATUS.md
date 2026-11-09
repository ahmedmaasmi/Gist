# CaseMind status

- **Current version:** v0.1 (Machine Detective MVP)
- **Current step:** 8. Leakage audit and E1 (8a audit PASSED; next: write the E1 hypotheses, run E1, then the one-time test evaluation)
- **Last updated:** 2026-11-09

## v0.1 checklist

The build order follows PRD Sections 14 and 9. "Exists, unaudited" means code from before this protocol that has not yet been checked against the PRD.

- [x] **1. Repo, tooling and core schemas.** uv, ruff, Makefile, Docker image and Compose stack; tier tags; per-field T3 canaries; ModelInference/Hypothesis; RevealedRelationship; T3 LieAnnotations; tier contract tests. *(Done 2026-11-09.)*
- [x] **2. Simulation engine.** Role-free sampler, noisy culprit choice, no culprit-only clues, coherent timelines, role-neutral wording, determinism (CH-03), reason strings (CH-02), full OOD range, 20 manor seeds hand-checked; `make audit-generator`. *(Done 2026-11-09.)*
- [x] **3. Structured contradiction checks.** Audited against PRD 6.4.B; "seen at some moment" semantics for observed people; `linked_source_ids`; point-in-time traces; travel-feasible schedules; `make audit-contradictions` (false-positive rate 0%, precision 100%, recall 52%). *(Done 2026-11-09.)*
- [x] **4. Feature spec v1.** 12 features in E1 groups A/B/C plus context; `docs/FEATURES.md` kept in sync with `app/features/spec.py`; T1-only signature guarantee; hand-computed test. *(Done 2026-11-09, spec v1.0.0.)*
- [x] **5. Dataset and splits.** 12 floor-plan maps, per-case variables, famous names; `make dataset` → v0.2.0 (1,650 cases; train/val/test_in_dist by case, 3 held-out maps, shifted OOD set, grouped-CV folds; checksums reproduce). *(Done 2026-11-09.)*
- [x] **6. Baselines and evaluation harness.** `app/ml/metrics.py` (case-level metrics, case bootstrap, paired differences); uniform, motive+opportunity rule and timeline solver; `make baselines` → `reports/baselines.{json,md}`, reproducible. *(Done 2026-11-09.)*
- [x] **7. Models.** LR and LightGBM (grouped-CV tuning, val calibration, LightGBM selected, 0.78 val top-1, +0.19 over the rule); the `Ranker` with evidence-linked explanations, a counterfactual, the rule fallback and abstention (96% coverage at 80% accuracy on val). *(Done 2026-11-09; test splits still sealed.)*
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
- 2026-11-09, **step 3 follow-up:** cross-speaker disagreements (D-016); tests 101 → 104. The PRD PDF stays out of git (`docs/*.pdf` ignored).
- 2026-11-09, **step 4 done:** feature spec v1.0.0 (12 features, E1 groups); `docs/FEATURES.md`; T1-only signature guarantee; tests 104 → 110.
- 2026-11-09, **step 5a done:** 12 floor-plan maps; per-case variables; famous character names (D-018 to D-020); argument-witness facts made point-in-time; tests 110 → 147.
- 2026-11-09: **art.** Style reference and the 31-portrait prompt list (`docs/art/`).
- 2026-11-09, **step 5 done:** `make dataset` builds v0.2.0. Splits follow PRD 8.4, with grouped-CV folds, a shifted OOD set, a feature table and a checksummed manifest. Artificial hard cases removed. Tests 148 → 151.
- 2026-11-09, **step 6 done:** evaluation harness and three baselines. The rule reaches about 0.6 top-1 and the solver barely beats chance (D-022). Tests 151 → 161.
- 2026-11-09: **learning journal** `docs/JOURNAL.md` is now a project rule.
- 2026-11-09, **step 7a done:** the first models exposed a scripted tell (culprits never claimed a witness; D-023), so the dataset went to v0.3.0. LR and LightGBM were tuned by grouped CV and calibrated on val; LightGBM is selected at 0.78 val top-1, +0.19 over the rule (D-024). Tests 161 → 166.
- 2026-11-09, **step 7b done:** `Ranker` with evidence-linked explanations (LR coefficients, LightGBM TreeSHAP), a 'remove this evidence' counterfactual, the rule fallback and val-chosen abstention (D-025); import cycle fixed. Tests 166 → 174.
- 2026-11-09, **step 8a done:** leakage audit PASSED, all 7 checks (D-026). The model relies mostly on scene presence (alone 0.684 vs full 0.779). Tests 174 → 176.

## Next action

Write the E1 hypotheses down and commit them *before* running, then run E1 (A / A+B / A+B+C plus leave-one-group-out) and the one-time test evaluation.

## Generator audit (current numbers, `make audit-generator`, 600 cases, 12 maps)

Scores measure recovery of the generator's logic, not real-world skill.

**Best single trivial rule (top-1):** chance is 0.24 (the suspect count varies).

| Rule | Top-1 |
|---|---|
| Crime-scene presence in the window | 0.63 |
| Has a forensic trace | 0.45 |
| Motive evidence | 0.41 |
| Validator's hand-weighted score | 0.37 |

**Per map:** the best rule scores 0.53–0.71 on every map, so no single map has a shortcut.

**Generator statistics:**
- Checks 1–3 pass in 598 of 600 cases.
- 5.3% of cases have only one eligible culprit.

## Contradiction layer (current numbers, `make audit-contradictions`, 600 cases)

- **False-positive rate: 0.0%** (95% Wilson CI 0–0.5%). **Precision: 100%. Recall: 48%.**
- **Flag rate by claim type:**

| Claim type | Flagged |
|---|---|
| Lying culprits | 95% |
| Honestly confused innocents | 52% |
| Red-herring evasions | 42% |
| COVER_FOR lies | 28% |
| Accurate claims | 0% |

**Disagreements (D-016):** 1.25 per case; 100% involve a false claim. False claims caught by a flag *or* a disagreement: **85%**. 37% of accurate innocents are involved in a disagreement (the honest counterpart), so it is never treated as blame.

## Models (`make models`, val only; top-1 with 95% CI)

| Method | Top-1 | Paired difference vs rule |
|---|---|---|
| Rule | 0.585 | — |
| Logistic regression | 0.702 | +0.12 [0.08, 0.16] |
| **LightGBM (selected)** | **0.779** | **+0.19 [0.15, 0.24]** |

**LightGBM top-1 by stage:** 0.67 at 35% of evidence, 0.82 at 65%, 0.95 with all evidence. The tests stay sealed until step 8.

**Abstention (val):** names someone when top ≥ 0.35. It answers 96% of states at 80% accuracy; at ≥ 0.9 confidence it is right 97.8% of the time.

## Baselines (`make baselines`; top-1 with 95% CI over cases)

| Split | Uniform | Motive + opportunity rule | Timeline solver |
|---|---|---|---|
| val | 0.24 | 0.60 | 0.25 |
| test_in_dist | 0.23 | 0.58 [0.52, 0.65] | 0.24 |
| held-out maps | 0.24 | 0.63 [0.59, 0.67] | 0.25 |
| shifted OOD | 0.24 | 0.59 [0.53, 0.66] | 0.25 |

**The bar for step 7:** beat the rule, with a paired CI that excludes 0.

## Dataset v0.3.0 (`make dataset`, about 15 s; 0.3.0 adds false witnesses, D-023)

- **Cases:** 1,650 on 12 maps.

| Split | Cases | Feature rows |
|---|---|---|
| Train | 783 | 17,520 |
| Val | 171 | 3,880 |
| Test (in distribution) | 171 | 3,895 |
| Test (held-out maps: train, lodge, abbey) | 375 | 8,320 |
| Test (shifted OOD) | 150 | 3,320 |

- **CV folds (train):** {clinic, hotel, theatre}, {college, manor, warehouse}, {gallery, office, yacht}.
- **Reproducibility:** two builds give identical checksums.

## Step 8 watch-list (leakage audit)

- **Briefing fact at stage 0.** `EvidenceRevealSampler` always reveals one "briefing" fact first: the earliest record at the crime scene. Check whether it favours the culprit (a reveal artefact, PRD 8.8).
- **Corroboration share.** Was a real shortcut (culprits never claimed a witness); fixed in D-023. Re-check that it is now uninformative.
- **Strong legitimate signals.** The strongest model signals are now refuted statements and presence at the scene in the window. The audit must confirm they aren't artefacts. For example, does the culprit's scene record survive more often than others'?
- **Constant feature.** `claim_claim_conflicts` is always 0 in generated data.
- **Lie rate.** The culprit lie rate is 0.820 observed against 0.806 sampled (z = 1.75, not significant); re-check.

## Open questions / blockers

- **Step 10 (UI):** render statements with room names, character names and clock times. Generated free text uses raw IDs and minutes.
- **Art:** portraits to be generated by the user from `docs/art/portraits.csv` into `frontend/public/portraits/`.

- **E. Templates.** Manor only for play, all 8 templates for dataset generation? (Decide by step 5.)
- **G. Abstention.** Simple threshold rule in v0.1 (step 7), E4 in v1.0?
- **PRD §17 Q4.** Which 3 hand-authored OOD cases are reserved? (Must be frozen before step 5.)
- **PRD PDF untracked.** Should `docs/CaseMind PRD v2.0.pdf` be committed so fresh clones have the spec?
