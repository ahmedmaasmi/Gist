# Leakage and shortcut audit: PASSED

> Scores on synthetic cases measure how well a method recovers the case generator's logic. They are not evidence of real-world investigative ability. Generalisation claims rest only on the held-out templates and the shifted OOD set (no hand-authored cases, D-020).

Dataset v0.3.0, commit `92564b7`, model lightgbm {'learning_rate': 0.1, 'min_child_samples': 20, 'n_estimators': 100, 'num_leaves': 15}. Fit on train, measured on val; test splits untouched.

| Check | Result | Key numbers |
|---|---|---|
| 1. Feature names | PASS | excluded names: none; keys used as inputs: none |
| 2. Shuffled labels | PASS | val top-1 with random culprits 0.182; minus uniform -0.056 [-0.089, -0.024] |
| 3. Single-feature models | PASS | full model 0.779; near-shortcuts: none |
| 4. Permutation importance | PASS | dominant features: none (chance 0.2379) |
| 5a. Stage-0 briefing fact | PASS | names culprit 0.358 vs random scene record 0.300 |
| 5b. Features from visible state only | PASS | 0 mismatches in 200 recomputed states |
| 5c. Suspect-order invariance | PASS | 0 of 100 changed |

## Single-feature models (val top-1)

- `scene_presence_in_window`: 0.684 [0.642, 0.727]
- `access_evidence`: 0.537 [0.492, 0.587]
- `claim_fact_conflicts`: 0.504 [0.463, 0.541]
- `motive_evidence`: 0.383 [0.341, 0.424]
- `alibi_strength`: 0.289 [0.258, 0.321]
- `disagreement_count`: 0.289 [0.264, 0.315]
- `victim_relationship_records`: 0.276 [0.244, 0.312]
- `unverified_claim_share`: 0.245 [0.223, 0.269]
- `opportunity_overlap`: 0.243 [0.220, 0.267]
- `claim_claim_conflicts`: 0.238 [0.228, 0.248]
- `evidence_coverage`: 0.238 [0.228, 0.248]
- `claimed_corroboration_share`: 0.235 [0.202, 0.266]

## Permutation importance (drop in val top-1 when the feature is shuffled)

- `scene_presence_in_window`: +0.426
- `access_evidence`: +0.075
- `motive_evidence`: +0.036
- `disagreement_count`: +0.013
- `claimed_corroboration_share`: +0.013
- `claim_fact_conflicts`: +0.010
- `opportunity_overlap`: +0.008
- `alibi_strength`: +0.008
- `claim_claim_conflicts`: +0.000
- `unverified_claim_share`: +0.000
- `evidence_coverage`: +0.000
- `victim_relationship_records`: -0.003
