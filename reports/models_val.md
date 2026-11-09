# Model results (validation only)

> Scores on synthetic cases measure how well a method recovers the case generator's logic. They are not evidence of real-world investigative ability. Generalisation claims rest only on the held-out templates and the shifted OOD set (no hand-authored cases, D-020). Test splits are not evaluated until the leakage audit (step 8) passes.

Dataset v0.4.0 (`de67dcf8c723…`), feature spec 1.1.0, commit `1d207b4-dirty`. Trained on 783 train cases; evaluated on 171 val cases from 9 templates. 95% CIs: 2000 bootstrap resamples over cases.

| Method | top1 | top2 | mrr | log_loss | brier |
|---|---|---|---|---|---|
| uniform | 0.238 [0.228, 0.248] | 0.476 [0.456, 0.495] | 0.499 [0.487, 0.511] | 1.475 [1.435, 1.516] | 0.762 [0.752, 0.772] |
| motive_opportunity_rule | 0.534 [0.476, 0.593] | 0.766 [0.724, 0.809] | 0.716 [0.678, 0.752] | 1.219 [1.136, 1.312] | 0.636 [0.591, 0.683] |
| logistic_regression | 0.624 [0.574, 0.671] | 0.816 [0.781, 0.850] | 0.771 [0.740, 0.801] | 0.995 [0.902, 1.092] | 0.508 [0.462, 0.555] |
| lightgbm | 0.695 [0.650, 0.738] | 0.827 [0.794, 0.857] | 0.809 [0.780, 0.837] | 0.822 [0.725, 0.919] | 0.411 [0.363, 0.462] |

## Against the motive + opportunity rule (paired, model minus rule)

- **logistic_regression**: top-1 0.090 [0.054, 0.126], log loss -0.224 [-0.287, -0.150]: beats the rule (both CIs exclude 0).
- **lightgbm**: top-1 0.161 [0.118, 0.202], log loss -0.397 [-0.464, -0.330]: beats the rule (both CIs exclude 0).

## Top-1 by amount of evidence

| Method | 35% of evidence | 65% of evidence | all evidence | after interview questions |
|---|---|---|---|---|
| uniform | 0.238 [0.228, 0.248] | 0.238 [0.228, 0.248] | 0.238 [0.228, 0.248] | 0.238 [0.228, 0.248] |
| motive_opportunity_rule | 0.531 [0.468, 0.597] | 0.598 [0.528, 0.664] | 0.670 [0.597, 0.737] | 0.491 [0.426, 0.555] |
| logistic_regression | 0.597 [0.538, 0.652] | 0.737 [0.681, 0.792] | 0.825 [0.766, 0.877] | 0.562 [0.502, 0.618] |
| lightgbm | 0.645 [0.586, 0.702] | 0.807 [0.757, 0.854] | 0.930 [0.889, 0.965] | 0.635 [0.578, 0.691] |

## Tuning (grouped CV on train, folds = groups of templates)

- **logistic_regression**: best {'C': 10.0} (CV log loss 1.089465), val temperature 0.5, version `logistic_regression-d23da4c960`
- **lightgbm**: best {'num_leaves': 15, 'learning_rate': 0.1, 'n_estimators': 300, 'min_child_samples': 20} (CV log loss 0.884699), val temperature 0.7, version `lightgbm-0a9d150890`

**Selected (best val log loss): lightgbm**

## Abstention (MD-06, chosen on val)

The selected model names a suspect only if the top probability is at least 0.35 and its lead over the runner-up is at least 0.1. On val it then answers 77% of evidence states with 81% accuracy (target: at least 80%).

Risk-coverage (selected model; sweep of the top-probability threshold):

| min top probability | coverage | accuracy on answered |
|---|---|---|
| 0.0 | 1.000 | 0.693 |
| 0.1 | 1.000 | 0.693 |
| 0.2 | 0.992 | 0.697 |
| 0.3 | 0.932 | 0.733 |
| 0.4 | 0.826 | 0.786 |
| 0.5 | 0.689 | 0.844 |
| 0.6 | 0.559 | 0.875 |
| 0.7 | 0.443 | 0.920 |
| 0.8 | 0.334 | 0.957 |
| 0.9 | 0.209 | 0.977 |

## Logistic Regression coefficients (log-odds per standard deviation)

- `scene_presence_in_window_rel`: +1.251
- `claim_fact_conflicts_rel`: +0.877
- `access_evidence_rel`: -0.713
- `motive_evidence_rel`: +0.476
- `answers_refuted_rel`: -0.334
- `opportunity_overlap_rel`: +0.318
- `unverified_claim_share_rel`: -0.294
- `disagreement_count_rel`: +0.287
- `claim_fact_conflicts`: -0.195
- `victim_relationship_records_rel`: +0.178
- `access_evidence`: +0.148
- `alibi_strength`: -0.143
- `unverified_claim_share`: -0.134
- `alibi_strength_rel`: -0.126
- `answers_refuted`: +0.118
- `scene_presence_in_window`: -0.100
- `claim_claim_conflicts_rel`: +0.097
- `opportunity_overlap`: +0.095
- `interview_answers`: +0.093
- `disagreement_count`: -0.080
- `motive_evidence`: -0.077
- `interview_answers_rel`: +0.076
- `victim_relationship_records`: -0.065
- `evasive_answer_share_rel`: -0.063
- `claimed_corroboration_share_rel`: +0.053
- `evidence_coverage`: -0.019
- `evasive_answer_share`: -0.016
- `claim_claim_conflicts`: +0.009
- `claimed_corroboration_share`: +0.008
