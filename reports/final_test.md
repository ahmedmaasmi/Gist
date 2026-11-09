# Final test evaluation (run once)

> Scores on synthetic cases measure how well a method recovers the case generator's logic. They are not evidence of real-world investigative ability. Generalisation claims rest only on the held-out templates and the shifted OOD set (no hand-authored cases, D-020).

Model `lightgbm-6d50342630` (selected on val in step 7), dataset v0.3.0, commit `ceef8b3`. Leakage audit passed beforehand. 95% CIs over cases (2000 resamples); abstention proportions with Wilson intervals.

## test_in_dist: 171 cases, 9 templates

| Method | top1 | top2 | mrr | log_loss | brier |
|---|---|---|---|---|---|
| model | 0.796 [0.757, 0.832] | 0.887 [0.858, 0.913] | 0.874 [0.849, 0.896] | 0.632 [0.542, 0.732] | 0.305 [0.258, 0.354] |
| motive_opportunity_rule | 0.583 [0.521, 0.645] | 0.825 [0.778, 0.867] | 0.757 [0.719, 0.794] | 1.110 [1.003, 1.221] | 0.582 [0.525, 0.640] |
| timeline_solver | 0.242 [0.233, 0.252] | 0.484 [0.465, 0.503] | 0.504 [0.494, 0.515] | 1.454 [1.416, 1.490] | 0.758 [0.749, 0.767] |
| uniform | 0.233 [0.225, 0.242] | 0.467 [0.449, 0.484] | 0.494 [0.484, 0.505] | 1.487 [1.450, 1.523] | 0.767 [0.758, 0.775] |

Model minus reference (paired):

- vs motive_opportunity_rule: top-1 0.213 [0.163, 0.264], log loss -0.478 [-0.565, -0.394]: beats it (both CIs exclude 0)
- vs timeline_solver: top-1 0.554 [0.516, 0.590], log loss -0.822 [-0.916, -0.718]: beats it (both CIs exclude 0)
- vs uniform: top-1 0.563 [0.524, 0.599], log loss -0.855 [-0.950, -0.750]: beats it (both CIs exclude 0)

Abstention: names a suspect in 95.9% [94.4%, 97.0%] of evidence states, correct 82.6% [79.8%, 85.0%] of the time when it does (target set on val: 80%).

Model top-1 by evidence revealed: 35% of evidence 0.655 [0.598, 0.709], 65% of evidence 0.867 [0.820, 0.908], all evidence 0.936 [0.895, 0.971]

## test_held_out_template: 375 cases, 3 templates

| Method | top1 | top2 | mrr | log_loss | brier |
|---|---|---|---|---|---|
| model | 0.791 [0.764, 0.817] | 0.896 [0.877, 0.915] | 0.874 [0.857, 0.891] | 0.607 [0.542, 0.676] | 0.298 [0.265, 0.331] |
| motive_opportunity_rule | 0.627 [0.588, 0.667] | 0.849 [0.820, 0.877] | 0.783 [0.759, 0.807] | 1.061 [0.986, 1.136] | 0.554 [0.514, 0.593] |
| timeline_solver | 0.250 [0.243, 0.257] | 0.500 [0.486, 0.514] | 0.513 [0.505, 0.521] | 1.426 [1.399, 1.454] | 0.750 [0.743, 0.757] |
| uniform | 0.240 [0.234, 0.247] | 0.481 [0.469, 0.493] | 0.503 [0.496, 0.510] | 1.458 [1.433, 1.484] | 0.759 [0.753, 0.766] |

Model minus reference (paired):

- vs motive_opportunity_rule: top-1 0.164 [0.131, 0.194], log loss -0.454 [-0.511, -0.399]: beats it (both CIs exclude 0)
- vs timeline_solver: top-1 0.541 [0.514, 0.567], log loss -0.820 [-0.883, -0.752]: beats it (both CIs exclude 0)
- vs uniform: top-1 0.550 [0.523, 0.577], log loss -0.851 [-0.915, -0.783]: beats it (both CIs exclude 0)

Abstention: names a suspect in 95.8% [94.8%, 96.7%] of evidence states, correct 81.5% [79.6%, 83.2%] of the time when it does (target set on val: 80%).

Model top-1 by evidence revealed: 35% of evidence 0.687 [0.650, 0.723], 65% of evidence 0.831 [0.799, 0.863], all evidence 0.917 [0.888, 0.944]

## test_ood_shifted: 150 cases, 3 templates

| Method | top1 | top2 | mrr | log_loss | brier |
|---|---|---|---|---|---|
| model | 0.689 [0.631, 0.748] | 0.825 [0.778, 0.871] | 0.807 [0.768, 0.845] | 0.854 [0.711, 1.000] | 0.427 [0.356, 0.498] |
| motive_opportunity_rule | 0.594 [0.529, 0.659] | 0.812 [0.762, 0.860] | 0.756 [0.713, 0.797] | 1.112 [1.006, 1.223] | 0.582 [0.524, 0.641] |
| timeline_solver | 0.246 [0.236, 0.258] | 0.493 [0.471, 0.515] | 0.509 [0.497, 0.522] | 1.439 [1.395, 1.482] | 0.754 [0.743, 0.764] |
| uniform | 0.242 [0.232, 0.253] | 0.484 [0.464, 0.506] | 0.505 [0.493, 0.517] | 1.454 [1.410, 1.494] | 0.758 [0.747, 0.768] |

Model minus reference (paired):

- vs motive_opportunity_rule: top-1 0.095 [0.052, 0.140], log loss -0.257 [-0.349, -0.167]: beats it (both CIs exclude 0)
- vs timeline_solver: top-1 0.443 [0.386, 0.501], log loss -0.585 [-0.722, -0.447]: beats it (both CIs exclude 0)
- vs uniform: top-1 0.447 [0.390, 0.506], log loss -0.599 [-0.735, -0.461]: beats it (both CIs exclude 0)

Abstention: names a suspect in 92.1% [90.0%, 93.9%] of evidence states, correct 71.9% [68.5%, 75.1%] of the time when it does (target set on val: 80%).

Model top-1 by evidence revealed: 35% of evidence 0.627 [0.558, 0.693], 65% of evidence 0.697 [0.633, 0.763], all evidence 0.800 [0.733, 0.867]
