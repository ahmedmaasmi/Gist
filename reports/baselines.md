# Baseline results

> Scores on synthetic cases measure how well a method recovers the case generator's logic. They are not evidence of real-world investigative ability. Generalisation claims rest only on the held-out templates and the shifted OOD set (no hand-authored cases, D-020).

Dataset v0.4.0 (features.csv sha256 `de67dcf8c723…`), feature spec 1.1.0, commit `1d207b4`. 95% CIs from 2000 bootstrap resamples over cases (seed 0). Calibration fitted on val: rule temperature 2.0, solver epsilon 0.001.

Higher is better for top-1, top-2 and MRR; lower is better for log loss and Brier.

## val: 171 cases, 9 templates, 1881 evidence states

| Baseline | top1 | top2 | mrr | log_loss | brier |
|---|---|---|---|---|---|
| uniform | 0.238 [0.228, 0.248] | 0.476 [0.456, 0.495] | 0.499 [0.487, 0.511] | 1.475 [1.435, 1.516] | 0.762 [0.752, 0.772] |
| motive_opportunity_rule | 0.534 [0.476, 0.593] | 0.766 [0.724, 0.809] | 0.716 [0.678, 0.752] | 1.219 [1.136, 1.312] | 0.636 [0.591, 0.683] |
| timeline_solver | 0.245 [0.234, 0.255] | 0.490 [0.469, 0.511] | 0.506 [0.494, 0.518] | 1.450 [1.409, 1.492] | 0.755 [0.745, 0.766] |

Difference vs uniform (paired; CI excluding 0 = real difference):

- motive_opportunity_rule: top-1 0.296 [0.238, 0.353], log loss -0.256 [-0.332, -0.178]
- timeline_solver: top-1 0.007 [0.005, 0.009], log loss -0.025 [-0.033, -0.018]

Top-1 by amount of evidence revealed:

| Baseline | 35% of evidence | 65% of evidence | all evidence | after interview questions |
|---|---|---|---|---|
| uniform | 0.238 [0.228, 0.248] | 0.238 [0.228, 0.248] | 0.238 [0.228, 0.248] | 0.238 [0.228, 0.248] |
| motive_opportunity_rule | 0.531 [0.468, 0.597] | 0.598 [0.528, 0.664] | 0.670 [0.597, 0.737] | 0.491 [0.426, 0.555] |
| timeline_solver | 0.239 [0.229, 0.249] | 0.245 [0.235, 0.256] | 0.261 [0.248, 0.273] | 0.244 [0.233, 0.254] |

## test_in_dist: 171 cases, 9 templates, 1881 evidence states

| Baseline | top1 | top2 | mrr | log_loss | brier |
|---|---|---|---|---|---|
| uniform | 0.233 [0.225, 0.242] | 0.467 [0.449, 0.484] | 0.494 [0.484, 0.505] | 1.487 [1.450, 1.523] | 0.767 [0.758, 0.775] |
| motive_opportunity_rule | 0.558 [0.499, 0.617] | 0.785 [0.740, 0.828] | 0.733 [0.697, 0.770] | 1.208 [1.125, 1.294] | 0.630 [0.585, 0.675] |
| timeline_solver | 0.240 [0.231, 0.250] | 0.481 [0.463, 0.500] | 0.503 [0.492, 0.514] | 1.460 [1.422, 1.496] | 0.759 [0.750, 0.769] |

Difference vs uniform (paired; CI excluding 0 = real difference):

- motive_opportunity_rule: top-1 0.325 [0.269, 0.382], log loss -0.279 [-0.356, -0.199]
- timeline_solver: top-1 0.007 [0.005, 0.010], log loss -0.027 [-0.035, -0.019]

Top-1 by amount of evidence revealed:

| Baseline | 35% of evidence | 65% of evidence | all evidence | after interview questions |
|---|---|---|---|---|
| uniform | 0.233 [0.225, 0.242] | 0.233 [0.225, 0.242] | 0.233 [0.225, 0.242] | 0.233 [0.225, 0.242] |
| motive_opportunity_rule | 0.555 [0.491, 0.616] | 0.595 [0.529, 0.664] | 0.617 [0.547, 0.687] | 0.537 [0.477, 0.596] |
| timeline_solver | 0.236 [0.227, 0.245] | 0.241 [0.232, 0.250] | 0.256 [0.245, 0.268] | 0.239 [0.230, 0.249] |

## test_held_out_template: 375 cases, 3 templates, 4125 evidence states

| Baseline | top1 | top2 | mrr | log_loss | brier |
|---|---|---|---|---|---|
| uniform | 0.240 [0.234, 0.247] | 0.481 [0.469, 0.493] | 0.503 [0.496, 0.510] | 1.458 [1.433, 1.484] | 0.759 [0.753, 0.766] |
| motive_opportunity_rule | 0.603 [0.565, 0.641] | 0.806 [0.777, 0.835] | 0.760 [0.736, 0.785] | 1.145 [1.089, 1.202] | 0.595 [0.565, 0.626] |
| timeline_solver | 0.248 [0.241, 0.255] | 0.497 [0.483, 0.510] | 0.511 [0.503, 0.519] | 1.433 [1.406, 1.459] | 0.752 [0.745, 0.758] |

Difference vs uniform (paired; CI excluding 0 = real difference):

- motive_opportunity_rule: top-1 0.362 [0.325, 0.400], log loss -0.313 [-0.364, -0.261]
- timeline_solver: top-1 0.008 [0.005, 0.010], log loss -0.026 [-0.033, -0.019]

Top-1 by amount of evidence revealed:

| Baseline | 35% of evidence | 65% of evidence | all evidence | after interview questions |
|---|---|---|---|---|
| uniform | 0.240 [0.234, 0.247] | 0.240 [0.234, 0.247] | 0.240 [0.234, 0.247] | 0.240 [0.234, 0.247] |
| motive_opportunity_rule | 0.596 [0.555, 0.640] | 0.635 [0.592, 0.679] | 0.674 [0.628, 0.720] | 0.582 [0.541, 0.625] |
| timeline_solver | 0.244 [0.237, 0.251] | 0.250 [0.243, 0.257] | 0.263 [0.254, 0.271] | 0.247 [0.240, 0.254] |

## test_ood_shifted: 150 cases, 3 templates, 1650 evidence states

| Baseline | top1 | top2 | mrr | log_loss | brier |
|---|---|---|---|---|---|
| uniform | 0.242 [0.232, 0.253] | 0.484 [0.464, 0.506] | 0.505 [0.493, 0.517] | 1.454 [1.410, 1.494] | 0.758 [0.747, 0.768] |
| motive_opportunity_rule | 0.589 [0.529, 0.651] | 0.786 [0.734, 0.836] | 0.748 [0.708, 0.788] | 1.166 [1.085, 1.246] | 0.607 [0.565, 0.649] |
| timeline_solver | 0.246 [0.235, 0.257] | 0.492 [0.470, 0.514] | 0.508 [0.496, 0.521] | 1.442 [1.398, 1.484] | 0.754 [0.743, 0.765] |

Difference vs uniform (paired; CI excluding 0 = real difference):

- motive_opportunity_rule: top-1 0.347 [0.289, 0.405], log loss -0.288 [-0.356, -0.218]
- timeline_solver: top-1 0.004 [0.002, 0.006], log loss -0.011 [-0.018, -0.006]

Top-1 by amount of evidence revealed:

| Baseline | 35% of evidence | 65% of evidence | all evidence | after interview questions |
|---|---|---|---|---|
| uniform | 0.242 [0.232, 0.253] | 0.242 [0.232, 0.253] | 0.242 [0.232, 0.253] | 0.242 [0.232, 0.253] |
| motive_opportunity_rule | 0.583 [0.517, 0.650] | 0.578 [0.507, 0.648] | 0.650 [0.577, 0.727] | 0.584 [0.519, 0.649] |
| timeline_solver | 0.242 [0.232, 0.253] | 0.246 [0.235, 0.257] | 0.256 [0.243, 0.269] | 0.245 [0.234, 0.257] |
