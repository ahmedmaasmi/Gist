# Leakage and shortcut audit: PASSED

> Scores on synthetic cases measure how well a method recovers the case generator's logic. They are not evidence of real-world investigative ability. Generalisation claims rest only on the held-out templates and the shifted OOD set (no hand-authored cases, D-020).

Dataset v0.4.0, commit `1d207b4-dirty`, model lightgbm {'learning_rate': 0.1, 'min_child_samples': 20, 'n_estimators': 300, 'num_leaves': 15}. Fit on train, measured on val; test splits untouched.

| Check | Result | Key numbers |
|---|---|---|
| 1. Feature names | PASS | excluded names: none; keys used as inputs: none |
| 2. Shuffled labels | PASS | val top-1 with random culprits 0.183; minus uniform -0.055 [-0.079, -0.033] |
| 3. Single-feature models | PASS | full model 0.695; near-shortcuts: none |
| 4. Permutation importance | PASS | dominant features: none (chance 0.2379) |
| 5a. Stage-0 briefing fact | PASS | names culprit 0.358 vs random scene record 0.300 |
| 5b. Features from visible state only | PASS | 0 mismatches in 200 recomputed states |
| 5c. Suspect-order invariance | PASS | 0 of 100 changed |

## Single-feature models (val top-1)

- `scene_presence_in_window`: 0.642 [0.593, 0.686]
- `access_evidence`: 0.504 [0.455, 0.553]
- `claim_fact_conflicts`: 0.442 [0.406, 0.479]
- `motive_evidence`: 0.332 [0.294, 0.369]
- `victim_relationship_records`: 0.276 [0.243, 0.313]
- `disagreement_count`: 0.265 [0.248, 0.282]
- `answers_refuted`: 0.264 [0.249, 0.282]
- `alibi_strength`: 0.260 [0.234, 0.286]
- `opportunity_overlap`: 0.259 [0.237, 0.283]
- `unverified_claim_share`: 0.251 [0.229, 0.276]
- `claim_claim_conflicts`: 0.240 [0.230, 0.251]
- `interview_answers`: 0.240 [0.224, 0.256]
- `evasive_answer_share`: 0.239 [0.225, 0.252]
- `evidence_coverage`: 0.238 [0.228, 0.248]
- `claimed_corroboration_share`: 0.230 [0.198, 0.260]

## Permutation importance (drop in val top-1 when the feature is shuffled)

- `scene_presence_in_window`: +0.387
- `access_evidence`: +0.075
- `claimed_corroboration_share`: +0.010
- `motive_evidence`: +0.009
- `claim_fact_conflicts`: +0.008
- `opportunity_overlap`: +0.006
- `claim_claim_conflicts`: +0.003
- `interview_answers`: +0.003
- `answers_refuted`: +0.002
- `alibi_strength`: +0.001
- `disagreement_count`: -0.001
- `evidence_coverage`: -0.001
- `unverified_claim_share`: -0.002
- `evasive_answer_share`: -0.002
- `victim_relationship_records`: -0.005
