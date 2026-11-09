# Experiments

Hypotheses are written and committed **before** each experiment runs (PRD 9). Results are added afterwards, below the hypotheses, without editing them. Both confirmations and refutations are reported.

> Scores on synthetic cases measure how well a method recovers the case generator's logic. Generalisation claims rest only on the held-out templates and the shifted OOD set (D-020).

---

## E1: feature ablation (PRD 9.1)

**Question.** Do timeline/alibi features (B) and reliability/contradiction features (C) improve over motive and opportunity alone (A), on held-out templates and the OOD set, beyond what the symbolic solver achieves?

### Design (fixed before running)

- **Feature variants** (groups from `docs/FEATURES.md`; `context` is included everywhere):
  - **A:** motive and opportunity: `motive_evidence`, `victim_relationship_records`, `access_evidence`, `opportunity_overlap`
  - **A+B:** adds `scene_presence_in_window`, `alibi_strength`, `claimed_corroboration_share`
  - **A+B+C:** adds `claim_fact_conflicts`, `claim_claim_conflicts`, `disagreement_count`, `unverified_claim_share`
  - **Leave one group out of A+B+C:** without A, without B, without C.
- **Model:** LightGBM (the family selected in step 7). It is **re-tuned for every variant** by the same grouped CV on train, so no variant is handicapped by settings chosen for another. Calibration is on val.
- **Evaluation:**
  - **Splits:** `test_held_out_template` (375 cases, 3 unseen maps) and `test_ood_shifted` (150 cases). Val is shown for reference.
  - **Single run:** each variant is evaluated exactly once.
- **Metrics:** top-1 and log loss, with 95% bootstrap CIs over cases; **paired** differences for every comparison.
- **References:** the motive + opportunity rule and the symbolic timeline solver (`make baselines`).
- **A difference counts as real** only if its paired 95% CI excludes 0.
- **Command:** `make e1` → `reports/e1.{json,md}`.

### Hypotheses (written 2026-11-09, before running)

- **H1.** A+B beats A on held-out templates (top-1). *Reason:* `scene_presence_in_window` (group B) is the strongest single feature in the leakage audit (0.684 alone on val).
- **H2.** A+B+C beats A+B on held-out templates, but by less than H1's gain. *Reason:* refuted statements are strongly culprit-linked, but scene presence already captures much of the same opportunity signal.
- **H3.** Every variant beats the symbolic solver on held-out templates. *Reason:* the solver barely beats chance (0.25), because sightings are single moments.
- **H4.** Variant A alone does *not* beat the motive + opportunity rule. *Reason:* the rule includes scene presence, which A lacks.
- **H5.** Leaving out group B hurts the most among the leave-one-group-out variants.
- **H6.** On the shifted OOD set, the ordering A < A+B < A+B+C holds, but every variant's top-1 is lower than on held-out templates. *Reason:* more missing records and longer windows.

### Results

*(added after running; the hypotheses above are not edited)*

**Run:** `make e1`, 2026-11-09. Full tables are in `reports/e1.md`.

**Held-out templates (375 cases, 3 unseen maps), top-1 with 95% CI:**

| Variant | Top-1 |
|---|---|
| A | 0.644 [0.611, 0.676] |
| A+B | **0.794** [0.766, 0.822] |
| A+B+C | 0.791 [0.764, 0.817] |
| Rule | 0.627 |
| Solver | 0.250 |

**Shifted OOD set (150 cases):**

| Variant | Top-1 |
|---|---|
| A | 0.609 |
| A+B | 0.692 |
| A+B+C | 0.689 |
| Rule | 0.594 |
| Solver | 0.246 |

**Verdicts** (paired top-1 differences; "real" means the 95% CI excludes 0):

| Hypothesis | Verdict | Evidence |
|---|---|---|
| H1: A+B > A | **Confirmed** | +0.150 [0.124, 0.179] (held-out); +0.083 [0.039, 0.129] (OOD) |
| H2: A+B+C > A+B | **Refuted** | −0.003 [−0.013, 0.008] (held-out); −0.003 [−0.021, 0.017] (OOD). Only on val does log loss improve slightly (−0.025). |
| H3: every variant > solver | **Confirmed** | +0.39 to +0.54 (held-out) |
| H4: A does not beat the rule (top-1) | **Confirmed** | +0.016 [−0.023, 0.055]; but A has the better log loss on held-out (−0.115), i.e. it is better calibrated |
| H5: dropping B hurts most | **Mixed** | top-1: dropping A −0.063 vs dropping B −0.057 (CIs overlap: not supported). Log loss: dropping B +0.136 vs dropping A +0.103 (supported). |
| H6: ordering holds on OOD; all lower | **Partly** | all lower than held-out (0.69 vs 0.79), but A+B ≈ A+B+C as in H2 |

**Interpretation.**
- **Why C adds nothing:** in this generator, a statement is refuted mostly *by the very badge record in the murder room* that group B already counts as presence at the scene. So contradiction features are informative on their own (0.50 top-1 in the leakage audit) but redundant once presence is known. *Checked:* on val (all evidence), **90% of the culprits' refuted statements (360/402) are refuted by a crime-scene record**, against 64% for innocents (199/312). The learned model is not "reasoning about lies" beyond what opportunity evidence shows.
- **Two directions this suggests:** contradictions that come from sources *other* than scene records (independent witnesses, cross-checks between suspects), or E3, where the question policy *elicits* new claims that could be refuted in new ways.
- **Generalisation:** the gains carry over to unseen maps. On the shifted set they shrink by about 10 points, but they stay above the rule and the solver.
