# E3: question policies

> Scores on synthetic cases measure how well a method recovers the case generator's logic. They are not evidence of real-world investigative ability. Generalisation claims rest only on the held-out templates and the shifted OOD set (no hand-authored cases, D-020).

300 fresh cases on test_held_out_template (train, lodge, abbey), start at 35% of the evidence, ranker `lightgbm-6d50342630`, commit `0f9309a`. Top-1 = the leading suspect is the culprit. 95% CIs over cases; differences are paired (same cases).

## honest_innocents

| Policy | start | after 3 | after 5 | after 8 | actions to reach & hold |
|---|---|---|---|---|---|
| random | 0.630 | 0.653 [0.593, 0.707] | 0.687 [0.633, 0.740] | 0.747 [0.697, 0.797] | 3.090 [2.643, 3.563] |
| fixed_order | 0.630 | 0.640 [0.587, 0.693] | 0.637 [0.583, 0.690] | 0.627 [0.573, 0.680] | 3.390 [2.907, 3.870] |
| top_two | 0.630 | 0.767 [0.720, 0.817] | 0.787 [0.740, 0.833] | 0.790 [0.743, 0.837] | 2.283 [1.890, 2.687] |
| entropy | 0.630 | 0.750 [0.700, 0.797] | 0.803 [0.757, 0.847] | 0.853 [0.813, 0.893] | 2.160 [1.793, 2.550] |

Entropy minus other policy (top-1: positive = entropy better; actions: negative = entropy faster):

- vs random: after 3 0.097 [0.057, 0.140], after 5 0.117 [0.070, 0.163], after 8 0.107 [0.060, 0.153]; actions -0.930 [-1.250, -0.613]
- vs fixed_order: after 3 0.110 [0.073, 0.147], after 5 0.167 [0.127, 0.210], after 8 0.227 [0.180, 0.277]; actions -1.230 [-1.523, -0.947]
- vs top_two: after 3 -0.017 [-0.047, 0.013], after 5 0.017 [-0.007, 0.040], after 8 0.063 [0.037, 0.093]; actions -0.123 [-0.270, 0.017]

## evasive_innocents

| Policy | start | after 3 | after 5 | after 8 | actions to reach & hold |
|---|---|---|---|---|---|
| random | 0.630 | 0.657 [0.600, 0.710] | 0.687 [0.633, 0.740] | 0.740 [0.690, 0.790] | 3.123 [2.683, 3.603] |
| fixed_order | 0.630 | 0.637 [0.583, 0.690] | 0.637 [0.583, 0.690] | 0.633 [0.580, 0.687] | 3.347 [2.863, 3.833] |
| top_two | 0.630 | 0.763 [0.713, 0.813] | 0.783 [0.737, 0.830] | 0.787 [0.743, 0.833] | 2.303 [1.903, 2.717] |
| entropy | 0.630 | 0.750 [0.700, 0.797] | 0.803 [0.757, 0.847] | 0.860 [0.820, 0.900] | 2.140 [1.767, 2.513] |

Entropy minus other policy (top-1: positive = entropy better; actions: negative = entropy faster):

- vs random: after 3 0.093 [0.053, 0.137], after 5 0.117 [0.073, 0.167], after 8 0.120 [0.073, 0.170]; actions -0.983 [-1.323, -0.667]
- vs fixed_order: after 3 0.113 [0.077, 0.150], after 5 0.167 [0.127, 0.210], after 8 0.227 [0.180, 0.277]; actions -1.207 [-1.497, -0.923]
- vs top_two: after 3 -0.013 [-0.043, 0.017], after 5 0.020 [0.000, 0.043], after 8 0.073 [0.047, 0.103]; actions -0.163 [-0.317, -0.023]

## mixed

| Policy | start | after 3 | after 5 | after 8 | actions to reach & hold |
|---|---|---|---|---|---|
| random | 0.630 | 0.657 [0.600, 0.710] | 0.683 [0.630, 0.737] | 0.747 [0.697, 0.797] | 3.093 [2.647, 3.563] |
| fixed_order | 0.630 | 0.637 [0.583, 0.690] | 0.637 [0.583, 0.690] | 0.637 [0.583, 0.690] | 3.343 [2.860, 3.827] |
| top_two | 0.630 | 0.767 [0.720, 0.817] | 0.787 [0.740, 0.833] | 0.787 [0.740, 0.833] | 2.320 [1.923, 2.737] |
| entropy | 0.630 | 0.750 [0.700, 0.797] | 0.807 [0.760, 0.850] | 0.860 [0.820, 0.900] | 2.157 [1.793, 2.537] |

Entropy minus other policy (top-1: positive = entropy better; actions: negative = entropy faster):

- vs random: after 3 0.093 [0.053, 0.137], after 5 0.123 [0.077, 0.173], after 8 0.113 [0.067, 0.160]; actions -0.937 [-1.257, -0.627]
- vs fixed_order: after 3 0.113 [0.077, 0.150], after 5 0.170 [0.127, 0.213], after 8 0.223 [0.177, 0.270]; actions -1.187 [-1.480, -0.910]
- vs top_two: after 3 -0.017 [-0.047, 0.013], after 5 0.020 [-0.003, 0.043], after 8 0.073 [0.043, 0.107]; actions -0.163 [-0.313, -0.017]
