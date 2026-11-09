# Final test evaluation (run once)

> Scores on synthetic cases measure how well a method recovers the case generator's logic. They are not evidence of real-world investigative ability. Generalisation claims rest only on the held-out templates and the shifted OOD set (no hand-authored cases, D-020).

Model `lightgbm-0a9d150890` (selected on val in step 7), dataset v0.4.0, commit `cdca526`. Leakage audit passed beforehand. 95% CIs over cases (2000 resamples); abstention proportions with Wilson intervals.

## test_in_dist: 171 cases, 9 templates

| Method | top1 | top2 | mrr | log_loss | brier |
|---|---|---|---|---|---|
| model | 0.720 [0.676, 0.763] | 0.842 [0.807, 0.873] | 0.826 [0.797, 0.853] | 0.814 [0.717, 0.918] | 0.399 [0.351, 0.448] |
| motive_opportunity_rule | 0.558 [0.499, 0.617] | 0.785 [0.740, 0.828] | 0.733 [0.697, 0.770] | 1.208 [1.125, 1.294] | 0.630 [0.585, 0.675] |
| timeline_solver | 0.240 [0.231, 0.250] | 0.481 [0.463, 0.500] | 0.503 [0.492, 0.514] | 1.460 [1.422, 1.496] | 0.759 [0.750, 0.769] |
| uniform | 0.233 [0.225, 0.242] | 0.467 [0.449, 0.484] | 0.494 [0.484, 0.505] | 1.487 [1.450, 1.523] | 0.767 [0.758, 0.775] |

Model minus reference (paired):

- vs motive_opportunity_rule: top-1 0.162 [0.119, 0.208], log loss -0.394 [-0.467, -0.319]: beats it (both CIs exclude 0)
- vs timeline_solver: top-1 0.480 [0.436, 0.523], log loss -0.646 [-0.745, -0.540]: beats it (both CIs exclude 0)
- vs uniform: top-1 0.487 [0.443, 0.530], log loss -0.673 [-0.771, -0.565]: beats it (both CIs exclude 0)

Abstention: names a suspect in 78.0% [76.1%, 79.8%] of evidence states, correct 81.7% [79.7%, 83.6%] of the time when it does (target set on val: 80%).

Model top-1 by evidence revealed: 35% of evidence 0.652 [0.594, 0.708], 65% of evidence 0.854 [0.807, 0.898], all evidence 0.901 [0.854, 0.942], after interview questions 0.668 [0.613, 0.723]

## test_held_out_template: 375 cases, 3 templates

| Method | top1 | top2 | mrr | log_loss | brier |
|---|---|---|---|---|---|
| model | 0.728 [0.698, 0.756] | 0.837 [0.813, 0.860] | 0.828 [0.809, 0.847] | 0.778 [0.711, 0.848] | 0.382 [0.349, 0.417] |
| motive_opportunity_rule | 0.603 [0.565, 0.641] | 0.806 [0.777, 0.835] | 0.760 [0.736, 0.785] | 1.145 [1.089, 1.202] | 0.595 [0.565, 0.626] |
| timeline_solver | 0.248 [0.241, 0.255] | 0.497 [0.483, 0.510] | 0.511 [0.503, 0.519] | 1.433 [1.406, 1.459] | 0.752 [0.745, 0.758] |
| uniform | 0.240 [0.234, 0.247] | 0.481 [0.469, 0.493] | 0.503 [0.496, 0.510] | 1.458 [1.433, 1.484] | 0.759 [0.753, 0.766] |

Model minus reference (paired):

- vs motive_opportunity_rule: top-1 0.125 [0.098, 0.150], log loss -0.367 [-0.416, -0.323]: beats it (both CIs exclude 0)
- vs timeline_solver: top-1 0.479 [0.450, 0.508], log loss -0.654 [-0.716, -0.589]: beats it (both CIs exclude 0)
- vs uniform: top-1 0.487 [0.457, 0.515], log loss -0.680 [-0.743, -0.615]: beats it (both CIs exclude 0)

Abstention: names a suspect in 79.1% [77.8%, 80.3%] of evidence states, correct 82.8% [81.5%, 84.1%] of the time when it does (target set on val: 80%).

Model top-1 by evidence revealed: 35% of evidence 0.684 [0.647, 0.721], 65% of evidence 0.822 [0.791, 0.854], all evidence 0.915 [0.883, 0.941], after interview questions 0.679 [0.642, 0.716]

## test_ood_shifted: 150 cases, 3 templates

| Method | top1 | top2 | mrr | log_loss | brier |
|---|---|---|---|---|---|
| model | 0.646 [0.590, 0.703] | 0.797 [0.750, 0.842] | 0.777 [0.740, 0.815] | 0.917 [0.789, 1.048] | 0.457 [0.393, 0.519] |
| motive_opportunity_rule | 0.589 [0.529, 0.651] | 0.786 [0.734, 0.836] | 0.748 [0.708, 0.788] | 1.166 [1.085, 1.246] | 0.607 [0.565, 0.649] |
| timeline_solver | 0.246 [0.235, 0.257] | 0.492 [0.470, 0.514] | 0.508 [0.496, 0.521] | 1.442 [1.398, 1.484] | 0.754 [0.743, 0.765] |
| uniform | 0.242 [0.232, 0.253] | 0.484 [0.464, 0.506] | 0.505 [0.493, 0.517] | 1.454 [1.410, 1.494] | 0.758 [0.747, 0.768] |

Model minus reference (paired):

- vs motive_opportunity_rule: top-1 0.058 [0.021, 0.096], log loss -0.249 [-0.340, -0.162]: beats it (both CIs exclude 0)
- vs timeline_solver: top-1 0.401 [0.345, 0.456], log loss -0.525 [-0.648, -0.402]: beats it (both CIs exclude 0)
- vs uniform: top-1 0.404 [0.349, 0.459], log loss -0.536 [-0.658, -0.414]: beats it (both CIs exclude 0)

Abstention: names a suspect in 71.8% [69.5%, 73.9%] of evidence states, correct 77.3% [74.8%, 79.6%] of the time when it does (target set on val: 80%).

Model top-1 by evidence revealed: 35% of evidence 0.630 [0.563, 0.695], 65% of evidence 0.677 [0.617, 0.740], all evidence 0.787 [0.720, 0.853], after interview questions 0.618 [0.553, 0.682]
