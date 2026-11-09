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

## Step 7b: explanations, "what if", fallback and "I'm not sure"

- **What:**
  - `app/ml/ranker.py` (the `Ranker` the game will call) and `app/ml/abstention.py`.
  - Evidence links on every feature row.
  - Abstention thresholds and a risk–coverage table in `make models`.
- **Why:** PRD MD-08 (explain each score, linked to evidence, with a "remove this evidence" counterfactual), MD-09 (fall back to the rule if the model is missing, visibly), MD-06 (abstain when the evidence is too thin, and say why), and MD-01/MD-02 (only T1 data; record model and feature versions).
- **How:**
  1. **Evidence links.** Each feature now *collects* the facts and claims it uses before computing its value, so value and evidence can't drift apart. Values were verified identical on 120 cases.
  2. **Explanations.** A model's score for a suspect is a log-odds number. For logistic regression it splits exactly into intercept + Σ (coefficient × standardised value). For LightGBM, **TreeSHAP** (built in via `pred_contrib=True`) gives an exact split too. A test checks both add up to the model's score.
  3. **Counterfactual.** Re-run the ranker with one fact or claim removed and report how each suspect's probability changes.
  4. **Fallback.** If the model file is missing, or was trained on a different feature spec, use the rule and show a notice.
  5. **Abstention.** Name nobody if the top probability < τ₁ or its lead < τ₂. The thresholds are chosen on val to answer as many states as possible while staying ≥ 80% accurate on those it answers.
- **A real example** (a val case, full evidence):
  - The model gives suspect_02 **70%** (correct).
  - The biggest push is "seen at the scene during the window" (+2.4), citing one badge record, `move_051`, which also refutes their alibi.
  - **Removing that single record** drops them by 48 points, and suspect_05 rises by 34.
- **Numbers (val):** abstention answers **96%** of states at **80%** accuracy. When the model says ≥ 90%, it is right **97.8%** of the time (the risk–coverage curve rises steadily, so the calibration is honest).
- **Also fixed:** an import cycle hidden by the order the tests happened to import things.
- **Concepts:**
  - **Additive explanations (SHAP or linear terms) are exact on the score, not on the final probability.** The probability depends on everyone else in the case. In the UI, say "pushes towards / away from".
  - **Counterfactuals** are the most intuitive explanation for a player ("without this record…"), and they test whether the model really relies on what it claims to.
  - **Selective prediction.** Abstaining trades coverage for accuracy. The risk–coverage curve shows the whole trade-off, and the threshold is a product choice (80%), stated up front rather than tuned after the fact.

## Step 8a: the leakage and shortcut audit

- **What:** `app/evaluation/leakage_audit.py` and `make audit-leakage` → `reports/leakage_audit.md`. Seven checks, all passed.
- **Why:** PRD 8.8 requires the audit *before* any results are reported. It is the last gate before the sealed test sets are opened. Twice already (steps 2 and 7a) the generator handed the model a shortcut, so the audit has to look for that kind of thing systematically.
- **How** (each check has a pass rule fixed in code before running):
  1. **Names.** No input called anything like `id`, `culprit`, `label` or `lie`, and no row key used as an input. A test plants `suspect_id_rel` and `label` to prove the check can fail.
  2. **Shuffled labels.** Give every training case a *random* culprit and retrain. If the pipeline were leaking the answer some other way, it would still score above chance. Result: 0.182, *below* chance (0.238): no leak.
  3. **One feature at a time.** Train on each feature alone. If one feature nearly matches the full model, it's a shortcut.
  4. **Permutation importance.** Scramble one feature across suspects and see how much accuracy drops.
  5. **Reveal and order artefacts:**
     - does the guaranteed first clue give the culprit away?
     - recomputing features from only what is visible gives exactly the stored values;
     - listing the suspects in reverse order changes nothing.
- **Numbers (val):**

  | Model | Top-1 |
  |---|---|
  | Full model | 0.779 |
  | Shuffled labels | 0.182 |
  | Best single feature (scene presence) | 0.684 |
  | Corroboration alone (the old tell) | 0.235 |

  Permuting scene presence costs 43 points, and the model still beats chance without it (0.35 vs 0.29). The briefing fact is slightly biased (0.36 vs 0.30, within tolerance).
- **Concepts:**
  - **Why "below chance" is fine.** A model fitted to noise learns "typical = positive", and real culprits are atypical. The PRD question is "does it find signal that isn't there?", so only *above-chance* results would be alarming. That makes the test one-sided.
  - **Dominance is not leakage, but it is a limitation.** The model's skill comes mostly from one plausible clue (opportunity: a door log in the murder room). That's honest detective evidence, but the report must say so, and E1 will show how much the other groups add.
  - **Audits must be able to fail.** A check that can never fail tells you nothing, which is why the planted-name test exists.

## Step 8b: E1, the feature ablation (pre-registered)

- **What:** `app/evaluation/e1_ablation.py` and `make e1` → `reports/e1.md`. Hypotheses and results are in `docs/EXPERIMENTS.md`.
- **Why:** PRD 9.1. Which kinds of evidence actually help? And does the model beat pure logic (the solver) on maps it never saw?
- **How:**
  1. **Pre-register.** Hypotheses H1–H6 were written and *committed* before running. The commit timestamp proves the predictions came first.
  2. **Variants.** Train the model on feature group A only, A+B, A+B+C, and A+B+C minus each group. Each variant is **re-tuned** by grouped CV, so none is disadvantaged.
  3. **Evaluate once** on held-out maps and the shifted set, with **paired** bootstrap differences. The same cases are resampled for both variants, which removes case-to-case noise from the comparison.
- **Numbers (held-out maps, top-1):** A 0.644 → A+B **0.794** → A+B+C 0.791. Rule 0.627, solver 0.250.
- **What we learned:**
  - **H1 confirmed.** Timeline and alibi evidence (B) is worth +15 points.
  - **H2 refuted.** Contradictions (C) add nothing once B is known, because 90% of culprits' refuted statements are refuted by the *same* murder-room records B already counts.
  - **Everything beats pure logic** (the solver) by 40–54 points.
- **Concepts:**
  - **Ablation.** Remove one ingredient and measure the drop, to find out what a model really relies on.
  - **Redundancy vs. usefulness.** A feature can be informative alone (contradictions: 0.50) yet add nothing next to a correlated one. Single-feature scores can't show this; ablations can.
  - **Pre-registration** protects against the forking-paths problem: trying many analyses and reporting the one that looks good.

## Step 8c: the one-time final test evaluation

- **What:** `app/evaluation/final_eval.py` and `make final-eval` → `reports/final_test.md`. Run once, after the audit passed.
- **Why:** PRD 8.4 and 15. Test sets are touched once, for the final model, so the reported number is an honest estimate rather than a tuned one.
- **How:**
  - It goes through the *deployed* path: `Ranker.load()` on the saved model, then `rank(t0, t1, map)` on every test evidence state.
  - It compares against the rule, the solver and uniform with paired CIs.
  - It reports abstention coverage and accuracy with Wilson intervals.
- **Numbers (top-1):**

  | Split | Model | vs rule |
  |---|---|---|
  | Same maps | 0.796 | +0.21 |
  | Unseen maps | 0.791 | +0.16 |
  | Shifted conditions | 0.689 | +0.10 |

  All CIs exclude 0. The held-out result matches E1 exactly (0.791) through an independent code path.
  - **Abstention:** 80% accuracy when answering, met on familiar and unseen maps, but only **72%** under shifted conditions.
- **Concepts:**
  - **Why "once".** Every look at test data that influences a decision leaks information into the model choice. That's why E1's lesson (use A+B, which is simpler) waits for the next version, decided on val.
  - **Distribution shift breaks calibration before it breaks ranking.** Under shift the model still beats the baselines, but its confidence is too high. This motivates OOD warnings (PRD CL-05) and E4.

## Step 9: the Machine Detective asks questions (E3)

- **What:**
  - `app/modes/mode1_detective/` (question bank, simulated players, four policies, episode loop);
  - `app/evaluation/e3_policies.py` and `make e3` → `reports/e3.md`;
  - E3 hypotheses in `docs/EXPERIMENTS.md`.
- **Why:** PRD 6.3, 6.4.D and 9.3. The detective should choose good questions, and we must measure whether a smart policy beats simple ones, using simulated players at scale (human play is only a demo).
- **How:**
  1. **Question bank.** Per suspect: "where were you at" the start, middle or end of the window, and "request their records". It is built from public information only.
  2. **Simulated players** answer from the hidden truth, as a human playing that character would:
     - **honest:** says where they really were;
     - **lying culprit:** repeats their cover story during the window;
     - **evasive:** sometimes "I don't remember".
  3. **Entropy policy.**
     - **Entropy** measures how spread out the probabilities are (high = unsure).
     - For each possible question, it estimates the probability of each answer type if this suspect is guilty vs innocent. Those numbers are learned from simulations on *training* maps.
     - It computes the expected entropy after the answer (Bayes' rule) and picks the question with the largest expected drop.
     - It logs the alternatives and their expected gains (MD-03).
  4. **The loop.** Policy picks → player answers or records are revealed → the contradiction checker runs → the real ranker re-ranks. Eight actions per case.
  5. **Pre-registered**, then run once on 300 fresh cases from unseen maps.
- **Numbers (top-1 after 8 actions, start 0.47):**

  | Policy | Top-1 | Actions to reach and hold the right answer |
  |---|---|---|
  | Entropy | **0.85** | 2.8 |
  | Top-two | 0.71 | 3.2 |
  | Random | 0.65 | 4.2 |
  | Fixed script | 0.48 | 4.8 |

- **The big lesson:**
  - **Interviews don't help the current model.** The fixed script asks only "where were you" questions and gains nothing. Even the entropy policy wins by choosing *which records* to request.
  - **Evasive players change nothing,** because answers barely matter.
  - **Two causes:**
    - a lie is caught only by a record the model already counts (E1);
    - the ranker never saw multi-statement interviews in training.
  - **Why it matters:** Mode 1's core idea is that *your* answers matter, so this is a design problem to fix, not just a number.
- **Concepts:**
  - **Expected information gain** = current entropy − expected entropy after the answer. The answer is unknown, so you average over possible answers, weighted by how likely each is.
  - **Surrogate model for decisions.** A cheap Bayesian update is good enough for *choosing*; the real model does the *updating*.
  - **Train–use mismatch.** The ranker was trained on single-statement states, so states with many answers are out of its experience, and it ignores what it never learned to use.

## Step 9b: trying to make interview answers matter (and what it revealed)

- **What:**
  - **Dataset 0.4.0** with simulated interviews.
  - **Feature spec 1.1.0** with three interview features.
  - **Per-state balanced training** for every model.
  - **A stronger leakage control.**
  - **E3b** (pre-registered), and a one-time test evaluation of the new model.
- **Why:** E3 showed the Machine Detective ignores interview answers, while the game's premise is that *your* answers matter.
- **How:**
  1. **Simulated interviews.** Random questions and record requests in every case, answered by players who lie consistently or dodge 20% of the time. *Everyone* dodges at that rate, culprit included, so dodging isn't a giveaway (the lesson from step 7a). A dodge is recorded as "I don't remember", so the model can see it.
  2. **New features:** answers given, share dodged, answers refuted by records.
  3. **A bug caught on the way:** answers were timestamped with the computer's clock, so the dataset wasn't reproducible. The checksum test caught it.
- **What the audit found:** this is the most important lesson of the step.
  - **The first audit failed narrowly.** With the new data, the shuffled-label control was just over its limit (+0.006, upper bound 0.032).
  - **Pooling exposed a real bias.** I didn't loosen the limit. I pooled 5 independent shuffles to get more evidence, and the result jumped to **+0.106**: models trained on *random* answers were finding the culprit.
  - **The cause:** each case has one culprit among n suspects, so the base rate is 1/n. Small casts give each suspect more evidence, and so do culprits. A per-suspect model learned "lots of evidence = small case = more likely positive", and that happens to point at culprits.
  - **The fix:** weight each case so its one positive balances its negatives. The shuffled control then drops to chance (−0.005).
  - **The old model had the same issue** (+0.084 pooled), so its earlier test result is superseded. Measured like-for-like, the inflation was small (0.687 → 0.684 at 35% of the evidence on unseen maps).
- **E3b result:**
  - **No change from interview training.** Questions alone still gain nothing (−0.027).
  - **The reason:** an answer can only be checked against a record, and the model already uses that record. You can't learn information that isn't there.
  - **The next fix** has to add a new source of truth: questions about *other* suspects, so honest witnesses can contradict the culprit.
- **New model, tested once (top-1):** held-out maps 0.728 (+0.13 vs rule), in-dist 0.720 (+0.16), shifted 0.646 (+0.06).
- **Concepts:**
  - **Base-rate confounding.** When the label rate differs between groups (here, case sizes) and features can tell the groups apart, a model learns the group, not the target. Per-group balancing removes it.
  - **Statistical power of controls.** One random shuffle is one noisy draw. Replicating it is how a hidden 8–10 point bias became visible.
  - **Information vs representation.** Better features or more training data can't extract information the signal doesn't contain. When an experiment says "no effect", ask whether the *data source* can carry the effect at all.

## Step 10a: the game server (API)

- **What:**
  - `backend/app/api/`: `game.py` (game logic), `views.py` (the only place server data becomes client data), `schemas.py` (typed responses), `routes.py` (endpoints).
  - Docker now runs the full game with the trained model.
- **Why:** PRD 6.3, 11, 12 and 13. The web UI needs a server that plays Mode 1 and never lets the solution reach the browser before the verdict.
- **How:**
  - **Start a game:** choose a case and a role (culprit or innocent). You get the public case plus your own character's knowledge.
  - **The detective moves one step at a time.** It asks you, asks a scripted suspect, or requests records, always the best expected question (entropy policy), and logs the alternatives.
  - **You answer with the claim builder:** room, time, who you saw, optional text. It's stored as an unverified self-report; the model re-ranks and logs its prediction with versions.
  - **The verdict** gives the top suspect with supporting evidence and contradictions, or "not enough evidence". **Results** unlock only after the verdict.
  - **Retries are safe:** `Idempotency-Key` stops a retried request from acting twice.
- **Numbers:** a test game played as the culprit (Count Dracula): the detective named Dracula at 97% after 8 actions. Tests 188 → 198.
- **Concepts:**
  - **A single secrecy boundary.** Only `views.py` turns server state into client data, and contract tests check the response *types*. If someone adds an endpoint that could leak the solution, the test fails before any data exists.
  - **Idempotency.** Networks retry requests. An idempotency key turns "do it again" into "give me the same answer again".
