# CaseMind learning journal

This is a running, plain-language explanation of every change: **what** changed, **why**, **how**, the **concepts** behind it, and the **numbers** it produced. It is written for me (an MSc ML student) to be able to explain any part of the project to an examiner or interviewer.

- `docs/DECISIONS.md` is the short, formal log of each decision.
- `docs/STATUS.md` says where we are.
- This file tells the story.

---

## How the pieces fit (big picture)

```
case generator (simulation)  ->  hidden truth (T3) + evidence the player can find (T1)
        |                                         |
   audits: are there shortcuts?            features (12 numbers per suspect, T1 only)
                                                  |
                                    baselines and models -> probability per suspect
                                                  |
                         metrics with confidence intervals (bootstrap over cases)
```

1. **Generator.** A seeded simulation invents an evening: characters with traits, relationships and schedules move around a map, argue, confide, cover for each other; one of them commits the murder.
2. **Observation model.** It turns that hidden truth into *evidence*: badge-swipe records, forensic traces, witness reports and the suspects' own (possibly lying) statements. Some records go missing; some witnesses are unreliable.
3. **Information tiers.** T0 = public, T1 = what the player has found, T2 = a character's private knowledge, T3 = the solution. Models may only ever see T0 and T1.
4. **Features, models, metrics.** We turn T1 into numbers, learn to rank suspects, and measure honestly.

**The golden rule:** on synthetic data, a high score only shows that a method recovers *the generator's own logic*. Every report says so.

---

## Setup: project memory

- **What:**
  - `CLAUDE.md` (rules read every session);
  - `docs/STATUS.md` (checklist and next action);
  - `docs/DECISIONS.md` (decision log);
  - the `/status` and `/wrapup` commands.
- **Why:** so any future session can resume exactly where we stopped, and so decisions keep their reasons and the alternatives that were rejected.
- **How:** plain Markdown files kept in git; one commit per finished step.
- **Concept:** a decision log that records *rejected alternatives* lets you revisit a choice deliberately instead of re-arguing it by accident.

## Step 1: tooling and the core schemas

- **What:**
  - **Tooling:** `uv` (package manager with a lockfile), `ruff` (linter), a `Makefile`, and Docker for Postgres and the backend.
  - **Schemas:** information tiers, canary tokens, `ModelInference` and `Hypothesis` types, `RevealedRelationship`, and `LieAnnotation`.
- **Why:** the PRD requires that hidden data (T3) never leaks to the player or the model, and that results be reproducible.
- **How:**
  - **Canaries.** Every T3 text field gets a unique, deterministic marker string (a hash of case, seed and field). Tests search every public payload for any marker.
  - **Structural tests.** Fields like `culprit_id` can't hold a marker, so a test walks the public data models and fails if a hidden type could be placed inside them.
  - **Lies live with the truth.** Lies are stored in T3 as annotations, never on the statement itself.
- **Bugs found:**
  - **Leaked scores.** Relationship evidence shown to the player contained the hidden relationship scores.
  - **Culprit lies never detected.** A culprit who walked back to their alibi room looked truthful.
- **Concepts:**
  - **Leakage prevention by construction.** Make it *impossible* to pass hidden data, rather than promising not to use it.
  - **Lockfiles.** Fixed seeds are not enough for reproducibility; library versions must be pinned too.

## Step 2: the generator, and the shortcut we found

- **What:** an audit of the case generator, followed by a redesign.
- **Why:** an audit showed that a single rule, "whoever the evidence calls crime-linked", found the culprit in **400/400** cases. The generator always built one scripted "primary" suspect as the murderer. Any model would have scored 100% while learning nothing. This was the PRD's number-one risk.
- **How:**
  - **Role-free cast.** Every suspect is drawn from the same distribution (traits uniform on 0–1, random motives, secrets, schedules and relationships).
  - **Noisy culprit choice.** The culprit is sampled with **softmax(score / temperature)**, where score = motive + opportunity + low composure. The most suspicious suspect is *usually* guilty, but not always.
  - **No culprit-only clues.** Any record can go missing, and anyone at the scene can leave a trace.
  - **Role-neutral wording.** Statements no longer reveal who is lying ("I remained at X per my schedule" was a giveaway).
  - **Coherent movement.** A culprit must be able to physically walk to the scene. Records became single moments, which stopped the "teleporting".
  - **Solvability check 4** became a difficulty *label* instead of a *filter*. As a filter it kept only cases a simple rule could solve.
- **Numbers:** best trivial rule **100% → about 63%** (chance 24–25%). The culprit lie rate now matches its setting.
- **Concepts:**
  - **A synthetic task only tests learning if the label is a *noisy* function of what the model can see.** The softmax temperature is the dial between "trivial" (always the top scorer) and "impossible" (random).
  - **A data filter is itself a model of the label.** If it uses the same signals as a baseline, it hands that baseline the answer.

## Step 3: the contradiction checker

- **What:**
  - **Audit.** The rule-based consistency engine was checked against PRD 6.4.B.
  - **New disagreement type.** Two people's statements that can't both be true are linked, without blaming either.
- **Why:** 24% of completely true statements by innocents were flagged as contradictions. The PRD calls false positives the headline safety metric, because they are false accusations.
- **How:**
  - **"I saw Y there"** means Y was there at *some moment*. It's flagged only if Y's records rule out *every* minute.
  - **"I was there"** still means the whole interval.
  - **Records and traces** became single moments; schedules respect walking times.
- **Numbers:**
  - **False-positive rate:** 24% → **0%**.
  - **Lies caught:** 52% by flags; **81–85%** with disagreements.
- **Concepts:**
  - **Getting "some" and "all" right matters.** "Seen at some moment" and "present the whole time" are different claims, and confusing them creates systematic false positives.
  - **Symmetric evidence.** "These two can't both be right" says *something* is wrong, not *who*.

## Step 4: the features

- **What:** 12 numbers per suspect, in groups A (motive and opportunity), B (timeline and alibi), C (reliability and contradictions) and context. They are written up in `docs/FEATURES.md`.
- **Why:** PRD 5.3. Features must be computed by code from T1 only, never typed in. The groups match experiment E1.
- **How:**
  - `compute_suspect_features(t0, t1, setting)` cannot receive T2 or T3, and a test checks the signature.
  - A test keeps the spec document and the code in sync.
  - Another test checks every value on a small case worked out by hand.
- **Concept:** a feature that is constant by design (e.g. "unverified" read from a status that never changes) is a bug in the spec. Catch it before training.

## Step 5: maps, variety, names and the dataset

- **What:**
  - **Maps:** 12 maps drawn as floor plans.
  - **Variety:** many per-case variables.
  - **Names:** famous character names.
  - **Dataset:** a versioned dataset built by one command.
- **Why:** the user wanted as much variety and as many good maps as possible, no hand-written cases, and famous names. The PRD wants splits by case *and* by template.
- **How:**
  - **Floor plans.** Each map is rooms with positions plus corridors. A shortest-path algorithm (Floyd–Warshall) computes the walking times, so every map is automatically consistent.
  - **Per-case variables:**
    - number of suspects (3–6);
    - murder window start (20:00–23:00) and length (20–40 min);
    - walking times ±20%;
    - noise, record-loss, trace and lie rates.
  - **Names.** 31 names: historical cases over 100 years old, and public-domain fiction. They are assigned at random, and a test checks no name predicts guilt.
  - **Dataset** (`make dataset`):
    - train / val / test cases come from 9 maps, split *by case*;
    - 3 maps are held out entirely;
    - a "shifted" set uses settings outside the training ranges;
    - 3 cross-validation folds are grouped by map;
    - checksums prove that a rebuild is identical.
- **Bug found (third time):** 10-minute evidence intervals created false accusations. Now a test forbids them for *all* player-visible facts.
- **Concepts:**
  - **Two kinds of generalisation.** Splitting *by case* tests familiar maps; *held-out maps* test something closer to generalisation.
  - **Same generator, same blind spots.** Without independent hand-written data, every test shares the generator's assumptions.

## Step 6: baselines and the evaluation harness

- **What:** `app/ml/metrics.py` (scores and confidence intervals) and three baselines: uniform, a motive+opportunity rule, and the timeline solver. `make baselines` writes `reports/baselines.md`.
- **Why:** PRD 8.5. You must know what simple methods achieve before claiming a model is good.
- **How:**
  - **The five PRD scores.** Top-1, top-2, MRR, log loss and Brier per evidence state.
  - **Fair ties.** Tied probabilities get the *expected* credit of a random tie-break.
  - **Confidence intervals.** 95% intervals come from resampling **whole cases** 2,000 times, plus paired differences between methods.
- **Numbers (top-1):**
  - **Uniform:** about 0.24.
  - **Rule:** about **0.58–0.63** on every test split.
  - **Solver:** about 0.25. It never rules out the culprit, but sightings are single moments, so logic alone rarely closes a 20–40 minute window.
- **Concepts:**
  - **Bootstrap over cases, not rows.** The 5 evidence states of one case are not independent, and resampling rows would make the intervals falsely narrow.
  - **The bar.** The ML model must beat the *rule*, with a paired confidence interval that excludes zero, or we report that it doesn't.

## Step 7a: the first models, and the shortcut they exposed

- **What:**
  - `app/ml/data.py`: evidence states become a matrix, one row per suspect.
  - `app/ml/models.py`: logistic regression, LightGBM and grouped-CV tuning.
  - `app/evaluation/model_report.py` and `make models`: the command that trains, tunes, selects and reports.
  - A generator fix: culprits may now name false witnesses. Dataset v0.3.0.
- **Why:** PRD 6.4.A and 8.5. We need a learned ranker that beats the baselines, chosen and calibrated without touching the test sets (PRD 8.4 and 8.8: the leakage audit comes first).
- **How:**
  1. **Pointwise model, then normalise.** Each suspect row gets a score P(culprit | features). Within an evidence state the scores are rescaled to sum to 1, giving a probability distribution over the suspects.
  2. **Relative features.** Each per-suspect feature also gets a "minus the average of this state" version, so the model can see "more motive *than the others*".
  3. **Grouped cross-validation on train only.** The 3 folds are groups of 3 maps. Each candidate setting is trained on 2 groups and scored on the 3rd, so the tuning score always comes from *unseen maps*. A test makes tuning refuse any non-train data.
  4. **Calibration on val.** One temperature, q ∝ p^(1/T), makes the probabilities honest. It doesn't change the ranking.
  5. **Selection on val.** The best val log loss wins (LightGBM). Test sets: not touched.
- **What went wrong, and why it matters:**
  - **Too good to be true.** The first run gave **0.86** val top-1 and **0.99** with all evidence.
  - **The coefficients gave it away.** Logistic regression's biggest weight was "claims a witness" (−5.5). The generator *never* let a culprit claim a witness: 0 of 855 claims, against about half of innocents.
  - **A hand rule did nearly as well.** Three terms ("no witness + statement refuted + seen at the scene") reached 0.92.
  - **So the model had learned the generator's script, not investigation.**
  - **Fix:** a lying culprit now names a false witness 70% of the time, chosen so culprits and innocents claim witnesses equally often (0.69 vs 0.69). False witnesses can be caught when the named person's records or statement disagree. A test keeps the rates matched.
- **Numbers (val, top-1, after the fix):**

  | Method | Top-1 | vs rule (paired, 95% CI) |
  |---|---|---|
  | Uniform | 0.24 | |
  | Rule | 0.585 | |
  | Logistic regression | 0.702 | +0.12 [0.08, 0.16] |
  | LightGBM | 0.779 | +0.19 [0.15, 0.24] |

  LightGBM improves as evidence arrives: 0.67 → 0.82 → 0.95. The strongest signals are now "a record refutes their statement", "seen at the scene during the window" and "motive", which is what a detective would use. The corroboration weight is about 0.
- **Concepts:**
  - **Why a pointwise model needs relative features.** It scores one suspect at a time. Without "compared to the others", it cannot know that 2 motive records is a lot in one case and little in another.
  - **Three layers of data use.** CV folds choose hyperparameters, val chooses the family and the calibration, and the test sets are touched once at the end. Using the test set earlier would make the final number optimistic.
  - **Interpretable models are a debugging tool.** The logistic regression coefficients exposed a shortcut that the more accurate LightGBM was silently exploiting just as much.
  - **Temperature scaling.** One parameter that makes "70% sure" mean right about 70% of the time, without changing which suspect ranks first.
