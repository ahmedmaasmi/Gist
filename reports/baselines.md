# Baseline results

> Scores on synthetic cases measure how well a method recovers the case generator's logic. They are not evidence of real-world investigative ability. Generalisation claims rest only on the held-out templates and the shifted OOD set (no hand-authored cases, D-020).

Dataset v0.2.0 (features.csv sha256 `1e9d6a320c45…`), feature spec 1.0.0, commit `da4fbd7`. 95% CIs from 2000 bootstrap resamples over cases (seed 0). Calibration fitted on val: rule temperature 1.5, solver epsilon 0.001.

Higher is better for top-1, top-2 and MRR; lower is better for log loss and Brier.

## val: 171 cases, 9 templates, 855 evidence states

| Baseline | top1 | top2 | mrr | log_loss | brier |
|---|---|---|---|---|---|
| uniform | 0.238 [0.228, 0.248] | 0.476 [0.456, 0.495] | 0.499 [0.487, 0.511] | 1.475 [1.435, 1.516] | 0.762 [0.752, 0.772] |
| motive_opportunity_rule | 0.585 [0.525, 0.645] | 0.819 [0.776, 0.857] | 0.755 [0.718, 0.790] | 1.143 [1.032, 1.266] | 0.605 [0.544, 0.670] |
| timeline_solver | 0.246 [0.235, 0.256] | 0.492 [0.471, 0.513] | 0.508 [0.495, 0.520] | 1.445 [1.404, 1.487] | 0.754 [0.744, 0.764] |

Difference vs uniform (paired; CI excluding 0 = real difference):

- motive_opportunity_rule: top-1 0.347 [0.288, 0.406], log loss -0.332 [-0.436, -0.218]
- timeline_solver: top-1 0.008 [0.006, 0.011], log loss -0.030 [-0.039, -0.022]

Top-1 by amount of evidence revealed:

| Baseline | 35% of evidence | 65% of evidence | all evidence |
|---|---|---|---|
| uniform | 0.238 [0.228, 0.248] | 0.238 [0.228, 0.248] | 0.238 [0.228, 0.248] |
| motive_opportunity_rule | 0.531 [0.468, 0.597] | 0.598 [0.528, 0.664] | 0.670 [0.597, 0.737] |
| timeline_solver | 0.239 [0.229, 0.249] | 0.245 [0.235, 0.256] | 0.261 [0.248, 0.273] |

## test_in_dist: 171 cases, 9 templates, 855 evidence states

| Baseline | top1 | top2 | mrr | log_loss | brier |
|---|---|---|---|---|---|
| uniform | 0.233 [0.225, 0.242] | 0.467 [0.449, 0.484] | 0.494 [0.484, 0.505] | 1.487 [1.450, 1.523] | 0.767 [0.758, 0.775] |
| motive_opportunity_rule | 0.583 [0.521, 0.645] | 0.825 [0.778, 0.867] | 0.757 [0.719, 0.794] | 1.110 [1.003, 1.221] | 0.582 [0.525, 0.640] |
| timeline_solver | 0.242 [0.233, 0.252] | 0.484 [0.465, 0.503] | 0.504 [0.494, 0.515] | 1.454 [1.416, 1.490] | 0.758 [0.749, 0.767] |

Difference vs uniform (paired; CI excluding 0 = real difference):

- motive_opportunity_rule: top-1 0.350 [0.289, 0.411], log loss -0.376 [-0.482, -0.265]
- timeline_solver: top-1 0.009 [0.006, 0.011], log loss -0.033 [-0.042, -0.024]

Top-1 by amount of evidence revealed:

| Baseline | 35% of evidence | 65% of evidence | all evidence |
|---|---|---|---|
| uniform | 0.233 [0.225, 0.242] | 0.233 [0.225, 0.242] | 0.233 [0.225, 0.242] |
| motive_opportunity_rule | 0.555 [0.491, 0.616] | 0.595 [0.529, 0.664] | 0.617 [0.547, 0.687] |
| timeline_solver | 0.236 [0.227, 0.245] | 0.241 [0.232, 0.250] | 0.256 [0.245, 0.268] |

## test_held_out_template: 375 cases, 3 templates, 1875 evidence states

| Baseline | top1 | top2 | mrr | log_loss | brier |
|---|---|---|---|---|---|
| uniform | 0.240 [0.234, 0.247] | 0.481 [0.469, 0.493] | 0.503 [0.496, 0.510] | 1.458 [1.433, 1.484] | 0.759 [0.753, 0.766] |
| motive_opportunity_rule | 0.627 [0.588, 0.667] | 0.849 [0.820, 0.877] | 0.783 [0.759, 0.807] | 1.061 [0.986, 1.136] | 0.554 [0.514, 0.593] |
| timeline_solver | 0.250 [0.243, 0.257] | 0.500 [0.486, 0.514] | 0.513 [0.505, 0.521] | 1.426 [1.399, 1.454] | 0.750 [0.743, 0.757] |

Difference vs uniform (paired; CI excluding 0 = real difference):

- motive_opportunity_rule: top-1 0.387 [0.349, 0.426], log loss -0.397 [-0.468, -0.326]
- timeline_solver: top-1 0.010 [0.007, 0.013], log loss -0.032 [-0.041, -0.024]

Top-1 by amount of evidence revealed:

| Baseline | 35% of evidence | 65% of evidence | all evidence |
|---|---|---|---|
| uniform | 0.240 [0.234, 0.247] | 0.240 [0.234, 0.247] | 0.240 [0.234, 0.247] |
| motive_opportunity_rule | 0.596 [0.555, 0.640] | 0.635 [0.592, 0.679] | 0.674 [0.628, 0.720] |
| timeline_solver | 0.244 [0.237, 0.251] | 0.250 [0.243, 0.257] | 0.263 [0.254, 0.271] |

## test_ood_shifted: 150 cases, 3 templates, 750 evidence states

| Baseline | top1 | top2 | mrr | log_loss | brier |
|---|---|---|---|---|---|
| uniform | 0.242 [0.232, 0.253] | 0.484 [0.464, 0.506] | 0.505 [0.493, 0.517] | 1.454 [1.410, 1.494] | 0.758 [0.747, 0.768] |
| motive_opportunity_rule | 0.594 [0.529, 0.659] | 0.812 [0.762, 0.860] | 0.756 [0.713, 0.797] | 1.112 [1.006, 1.223] | 0.582 [0.524, 0.641] |
| timeline_solver | 0.246 [0.236, 0.258] | 0.493 [0.471, 0.515] | 0.509 [0.497, 0.522] | 1.439 [1.395, 1.482] | 0.754 [0.743, 0.764] |

Difference vs uniform (paired; CI excluding 0 = real difference):

- motive_opportunity_rule: top-1 0.352 [0.289, 0.415], log loss -0.342 [-0.440, -0.239]
- timeline_solver: top-1 0.004 [0.002, 0.007], log loss -0.014 [-0.022, -0.008]

Top-1 by amount of evidence revealed:

| Baseline | 35% of evidence | 65% of evidence | all evidence |
|---|---|---|---|
| uniform | 0.242 [0.232, 0.253] | 0.242 [0.232, 0.253] | 0.242 [0.232, 0.253] |
| motive_opportunity_rule | 0.583 [0.517, 0.650] | 0.578 [0.507, 0.648] | 0.650 [0.577, 0.727] |
| timeline_solver | 0.242 [0.232, 0.253] | 0.246 [0.235, 0.257] | 0.256 [0.243, 0.269] |
