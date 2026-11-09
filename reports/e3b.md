# E3: question policies

> Scores on synthetic cases measure how well a method recovers the case generator's logic. They are not evidence of real-world investigative ability. Generalisation claims rest only on the held-out templates and the shifted OOD set (no hand-authored cases, D-020).

300 fresh cases on test_held_out_template (train, lodge, abbey), start at 15% of the evidence, ranker `lightgbm-0a9d150890`, commit `cdca526`. Top-1 = the leading suspect is the culprit. 95% CIs over cases; differences are paired (same cases).

## honest_innocents

| Policy | start | after 3 | after 5 | after 8 | gain after 8 (paired) | actions to reach & hold |
|---|---|---|---|---|---|---|
| random | 0.510 | 0.563 [0.510, 0.623] | 0.597 [0.543, 0.653] | 0.670 [0.613, 0.727] | 0.160 [0.107, 0.217] | 4.163 [3.680, 4.627] |
| fixed_order | 0.510 | 0.500 [0.443, 0.557] | 0.493 [0.440, 0.550] | 0.483 [0.430, 0.543] | -0.027 [-0.057, 0.000] | 4.883 [4.363, 5.347] |
| top_two | 0.510 | 0.687 [0.633, 0.740] | 0.737 [0.687, 0.787] | 0.750 [0.700, 0.800] | 0.240 [0.187, 0.297] | 3.193 [2.767, 3.610] |
| entropy | 0.510 | 0.750 [0.697, 0.800] | 0.840 [0.797, 0.883] | 0.840 [0.800, 0.880] | 0.330 [0.270, 0.390] | 2.803 [2.427, 3.183] |

Entropy minus other policy (top-1: positive = entropy better; actions: negative = entropy faster):

- vs random: after 3 0.187 [0.130, 0.240], after 5 0.243 [0.183, 0.300], after 8 0.170 [0.113, 0.227]; actions -1.360 [-1.750, -0.970]
- vs fixed_order: after 3 0.250 [0.197, 0.303], after 5 0.347 [0.290, 0.400], after 8 0.357 [0.293, 0.413]; actions -2.080 [-2.470, -1.697]
- vs top_two: after 3 0.063 [0.033, 0.097], after 5 0.103 [0.067, 0.143], after 8 0.090 [0.053, 0.130]; actions -0.390 [-0.590, -0.183]

## evasive_innocents

| Policy | start | after 3 | after 5 | after 8 | gain after 8 (paired) | actions to reach & hold |
|---|---|---|---|---|---|---|
| random | 0.510 | 0.560 [0.507, 0.613] | 0.583 [0.530, 0.640] | 0.657 [0.603, 0.713] | 0.147 [0.090, 0.207] | 4.270 [3.797, 4.727] |
| fixed_order | 0.510 | 0.500 [0.443, 0.557] | 0.477 [0.420, 0.537] | 0.487 [0.433, 0.547] | -0.023 [-0.060, 0.013] | 5.023 [4.516, 5.500] |
| top_two | 0.510 | 0.683 [0.630, 0.737] | 0.743 [0.690, 0.790] | 0.753 [0.700, 0.800] | 0.243 [0.190, 0.300] | 3.167 [2.740, 3.593] |
| entropy | 0.510 | 0.750 [0.697, 0.800] | 0.830 [0.787, 0.873] | 0.853 [0.810, 0.893] | 0.343 [0.283, 0.407] | 2.827 [2.450, 3.223] |

Entropy minus other policy (top-1: positive = entropy better; actions: negative = entropy faster):

- vs random: after 3 0.190 [0.133, 0.243], after 5 0.247 [0.187, 0.303], after 8 0.197 [0.137, 0.253]; actions -1.443 [-1.847, -1.023]
- vs fixed_order: after 3 0.250 [0.193, 0.303], after 5 0.353 [0.297, 0.410], after 8 0.367 [0.307, 0.427]; actions -2.197 [-2.610, -1.790]
- vs top_two: after 3 0.067 [0.037, 0.097], after 5 0.087 [0.047, 0.127], after 8 0.100 [0.060, 0.140]; actions -0.340 [-0.540, -0.130]

## mixed

| Policy | start | after 3 | after 5 | after 8 | gain after 8 (paired) | actions to reach & hold |
|---|---|---|---|---|---|---|
| random | 0.510 | 0.577 [0.523, 0.633] | 0.607 [0.553, 0.663] | 0.683 [0.627, 0.740] | 0.173 [0.120, 0.227] | 4.090 [3.633, 4.553] |
| fixed_order | 0.510 | 0.500 [0.447, 0.560] | 0.500 [0.447, 0.560] | 0.507 [0.450, 0.563] | -0.003 [-0.040, 0.033] | 4.853 [4.343, 5.337] |
| top_two | 0.510 | 0.680 [0.627, 0.733] | 0.740 [0.690, 0.790] | 0.770 [0.720, 0.817] | 0.260 [0.207, 0.317] | 3.160 [2.730, 3.573] |
| entropy | 0.510 | 0.750 [0.697, 0.797] | 0.843 [0.800, 0.887] | 0.847 [0.803, 0.887] | 0.337 [0.277, 0.397] | 2.813 [2.433, 3.207] |

Entropy minus other policy (top-1: positive = entropy better; actions: negative = entropy faster):

- vs random: after 3 0.173 [0.117, 0.230], after 5 0.237 [0.177, 0.290], after 8 0.163 [0.107, 0.220]; actions -1.277 [-1.677, -0.887]
- vs fixed_order: after 3 0.250 [0.193, 0.307], after 5 0.343 [0.283, 0.400], after 8 0.340 [0.277, 0.397]; actions -2.040 [-2.430, -1.657]
- vs top_two: after 3 0.070 [0.040, 0.100], after 5 0.103 [0.063, 0.147], after 8 0.077 [0.037, 0.113]; actions -0.347 [-0.547, -0.143]
