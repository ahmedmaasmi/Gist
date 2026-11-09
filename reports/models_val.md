# Model results (validation only)

> Scores on synthetic cases measure how well a method recovers the case generator's logic. They are not evidence of real-world investigative ability. Generalisation claims rest only on the held-out templates and the shifted OOD set (no hand-authored cases, D-020). Test splits are not evaluated until the leakage audit (step 8) passes.

Dataset v0.3.0 (`44ceeea3223b…`), feature spec 1.0.0, commit `7b9acdc`. Trained on 783 train cases; evaluated on 171 val cases from 9 templates. 95% CIs: 2000 bootstrap resamples over cases.

| Method | top1 | top2 | mrr | log_loss | brier |
|---|---|---|---|---|---|
| uniform | 0.238 [0.228, 0.248] | 0.476 [0.456, 0.495] | 0.499 [0.487, 0.511] | 1.475 [1.435, 1.516] | 0.762 [0.752, 0.772] |
| motive_opportunity_rule | 0.585 [0.525, 0.645] | 0.819 [0.776, 0.857] | 0.755 [0.718, 0.790] | 1.143 [1.032, 1.266] | 0.605 [0.544, 0.670] |
| logistic_regression | 0.702 [0.660, 0.744] | 0.877 [0.847, 0.905] | 0.825 [0.798, 0.850] | 0.810 [0.719, 0.911] | 0.415 [0.367, 0.465] |
| lightgbm | 0.779 [0.738, 0.818] | 0.889 [0.861, 0.914] | 0.866 [0.841, 0.890] | 0.638 [0.551, 0.731] | 0.321 [0.273, 0.372] |

## Against the motive + opportunity rule (paired, model minus rule)

- **logistic_regression**: top-1 0.117 [0.075, 0.160], log loss -0.333 [-0.418, -0.250]: beats the rule (both CIs exclude 0).
- **lightgbm**: top-1 0.194 [0.148, 0.241], log loss -0.505 [-0.589, -0.422]: beats the rule (both CIs exclude 0).

## Top-1 by amount of evidence

| Method | 35% of evidence | 65% of evidence | all evidence |
|---|---|---|---|
| uniform | 0.238 [0.228, 0.248] | 0.238 [0.228, 0.248] | 0.238 [0.228, 0.248] |
| motive_opportunity_rule | 0.531 [0.468, 0.597] | 0.598 [0.528, 0.664] | 0.670 [0.597, 0.737] |
| logistic_regression | 0.583 [0.525, 0.637] | 0.731 [0.678, 0.784] | 0.883 [0.830, 0.930] |
| lightgbm | 0.656 [0.599, 0.714] | 0.825 [0.778, 0.868] | 0.936 [0.895, 0.971] |

## Tuning (grouped CV on train, folds = groups of templates)

- **logistic_regression**: best {'C': 1.0} (CV log loss 0.9159), val temperature 0.7, version `logistic_regression-de4cc305f0`
- **lightgbm**: best {'num_leaves': 15, 'learning_rate': 0.1, 'n_estimators': 100, 'min_child_samples': 20} (CV log loss 0.704979), val temperature 0.85, version `lightgbm-6d50342630`

**Selected (best val log loss): lightgbm**

## Abstention (MD-06, chosen on val)

The selected model names a suspect only if the top probability is at least 0.35 and its lead over the runner-up is at least 0.0. On val it then answers 96% of evidence states with 80% accuracy (target: at least 80%).

Risk-coverage (selected model; sweep of the top-probability threshold):

| min top probability | coverage | accuracy on answered |
|---|---|---|
| 0.0 | 1.000 | 0.779 |
| 0.1 | 1.000 | 0.779 |
| 0.2 | 1.000 | 0.779 |
| 0.3 | 0.981 | 0.787 |
| 0.4 | 0.933 | 0.817 |
| 0.5 | 0.854 | 0.852 |
| 0.6 | 0.743 | 0.877 |
| 0.7 | 0.639 | 0.907 |
| 0.8 | 0.515 | 0.939 |
| 0.9 | 0.321 | 0.978 |

## Logistic Regression coefficients (log-odds per standard deviation)

- `claim_fact_conflicts_rel`: +1.137
- `scene_presence_in_window_rel`: +1.114
- `unverified_claim_share_rel`: -0.656
- `access_evidence_rel`: -0.653
- `motive_evidence_rel`: +0.615
- `opportunity_overlap_rel`: +0.481
- `disagreement_count_rel`: +0.379
- `scene_presence_in_window`: -0.269
- `claimed_corroboration_share_rel`: +0.164
- `victim_relationship_records_rel`: +0.162
- `claimed_corroboration_share`: -0.155
- `opportunity_overlap`: +0.154
- `disagreement_count`: -0.142
- `alibi_strength_rel`: -0.136
- `evidence_coverage`: -0.133
- `access_evidence`: +0.095
- `motive_evidence`: -0.067
- `claim_fact_conflicts`: -0.063
- `unverified_claim_share`: -0.029
- `alibi_strength`: +0.019
- `victim_relationship_records`: -0.012
- `claim_claim_conflicts`: +0.000
- `claim_claim_conflicts_rel`: +0.000
