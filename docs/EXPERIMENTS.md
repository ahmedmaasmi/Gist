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

---

## E3: question policies (PRD 9.3)

**Question.** Does choosing questions by expected entropy reduction find the culprit faster than random, fixed-order and top-two policies, across honest, evasive and mixed simulated players?

### Design (fixed before running)

- **Cases.** Fresh cases, generated for E3 only:
  - **300** on the **held-out templates** (train, lodge, abbey; 100 each), seeds 6,000,000+.
  - The answer-outcome model is estimated on **300 separate cases from dev templates**, seeds 5,000,000+, with the *mixed* population. The policy does not know which population it faces.
- **Start.** Each episode starts from the case's **15%** evidence state (about 11 facts), first ordering. Starting accuracy there is about 0.52 on dev maps, measured before any policy was run. Starting at 35% leaves less room: about 0.65 on dev maps, 0.69 at the 35% stage of the final test. It is reported as a secondary analysis. *Limitation:* the ranker was trained on states with 35% or more of the evidence.
- **Question bank** (12–24 questions): per suspect, "where were you at" the start, middle and end of the window, plus "request records". Each question at most once.
- **Players** (`app/modes/mode1_detective/players.py`):
  - **honest_innocents:** a lying culprit and honest innocents.
  - **evasive_innocents:** a lying culprit and innocents who are evasive 50% of the time.
  - **mixed:** behaviour as generated, with innocents evasive 25% of the time.
- **Policies:** random, fixed_order, top_two, entropy. The ranker is fixed (`lightgbm-6d50342630`) and updates after every action.
- **Metrics** (paired over the same cases; 95% case-bootstrap CIs):
  - top-1 accuracy of the leading suspect after **3, 5 and 8** actions;
  - **actions to reach and hold** the correct leader (9 if never within 8).
- **Command:** `make e3` → `reports/e3.{json,md}`.

### Hypotheses (written 2026-11-09, before running)

- **H1.** Entropy beats random on top-1 after 5 actions, for every population.
- **H2.** Entropy beats fixed_order on top-1 after 3 and after 5 actions.
- **H3.** Entropy is not worse than top_two at any budget (paired CI not entirely below 0). The two may tie, since both focus on likely suspects.
- **H4.** Every policy improves on the starting accuracy (0 actions) by 8 actions.
- **H5.** For every policy, accuracy after 5 actions is lower with evasive innocents than with honest innocents.
- **H6.** Entropy needs fewer actions to reach and hold the correct leader than random.

### Results

*(added after running; the hypotheses above are not edited)*

**Run:** `make e3`, 2026-11-09, on 300 fresh held-out-map cases, starting from 15% of the evidence (start top-1 0.467). Full tables are in `reports/e3.md`; the secondary 35% start is in `reports/e3_start35.md`.

**Top-1 after 8 actions (honest / evasive / mixed innocents):**

| Policy | Top-1 | Actions to reach and hold (honest) |
|---|---|---|
| Random | 0.65 / 0.65 / 0.65 | 4.2 |
| Fixed order | 0.48 / 0.49 / 0.50 | 4.8 |
| Top-two | 0.71 / 0.71 / 0.71 | 3.2 |
| **Entropy** | **0.85 / 0.84 / 0.85** | **2.8** |

**Verdicts** (paired 95% CIs over the same cases):

| Hypothesis | Verdict | Evidence |
|---|---|---|
| H1: entropy > random after 5, every population | **Confirmed** | +0.18 to +0.19 (all CIs exclude 0) |
| H2: entropy > fixed_order after 3 and 5 | **Confirmed** | +0.20 to +0.21 after 3; +0.27 after 5 |
| H3: entropy not worse than top_two | **Confirmed** | tie after 3 (+0.013 [−0.013, 0.040]); better after 5 (+0.05 to +0.06) and after 8 (+0.13 to +0.14) |
| H4: every policy improves on the start by 8 actions | **Refuted for fixed_order** | 0.467 → 0.480 [0.420, 0.540]; random, top_two and entropy improve clearly |
| H5: evasive innocents lower accuracy | **Refuted** | differences ≤ 0.01 for every policy |
| H6: entropy needs fewer actions than random | **Confirmed** | −1.4 [−1.8, −1.0] |

The secondary 35% start shows the same pattern: entropy 0.853 vs random 0.747 after 8; fixed_order flat (0.630 → 0.627).

**Interpretation: the answers carry almost no information.**
- **Fixed_order shows it most clearly.** It only asks "where were you" (480 questions, no record checks) and gains nothing. The entropy policy wins mainly by **requesting records** (185 of 480 actions), and by asking the right suspect at the right time.
- **The cause is the same as E1's refuted H2.** A lie is only caught when a record contradicts it, and the ranker already counts that record as presence at the scene. Also, the ranker was trained on states with a single statement per suspect.
- **That's why evasiveness doesn't matter (H5):** if answers barely move the model, refusing to answer barely matters either.
- **Product consequence for Mode 1:** the player is the suspect being questioned, so at present their answers barely influence the Machine Detective. Possible fixes are listed in `docs/STATUS.md` (open questions).

---

## E3b: do interview answers matter after interview training? (re-run of E3)

**Why.** E3 found that answers barely moved the ranker: a questions-only script gained nothing. In response, D-029 added interview evidence states to the training data (dataset 0.4.0), added interview features (group D, spec 1.1.0), and fixed a case-size confound found by the leakage audit (per-state balanced training). The ranker is now `lightgbm-0a9d150890`.

**Design.** Identical to E3: same 300 fresh held-out-map cases (seeds 6,000,000+), same outcome-model cases, 15% start, same populations and policies, paired CIs. One added metric: each policy's paired gain after 8 actions over its own start. Command: `make e3b` → `reports/e3b.{json,md}`.

### Hypotheses (written 2026-11-09, before running)

- **H1.** The questions-only fixed_order script now improves top-1 over its start by 8 actions (paired gain CI excludes 0), for honest innocents. This is the point of D-029.
- **H2.** Entropy still beats random after 5 actions, for every population.
- **H3.** With fixed_order, evasive innocents now give lower top-1 after 8 actions than honest innocents (answers matter, so dodging matters).
- **H4.** Entropy's top-1 after 8 actions is at least as high as in E3 (0.85) for honest innocents.

### Results

*(added after running; the hypotheses above are not edited)*
