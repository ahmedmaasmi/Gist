# Decisions log

Append-only. Never edit or delete an old entry; if a decision changes, add a new entry that supersedes it.

---

## D-001 (2026-11-09): Keep and audit the existing code

- **Decision:** Keep the ~6,500 lines and 45 tests written before this protocol. Each checklist step starts with an audit of the relevant existing module against the PRD, then closes the gaps.
- **Alternatives considered:** Archive it and start main fresh; keep it but treat every item as not done.
- **Reason:** Much of it already matches the PRD (provenance enums, tier models, simulator with reason strings, determinism). Rewriting it would cost weeks. Auditing finds the real gaps, such as a single constant canary and raw edge values in T1.
- **What I should learn from this:** Code that exists but hasn't been checked against the spec is a liability, not an asset. Passing tests only show that the code does what its author intended, not what the spec requires.

## D-002 (2026-11-09): Treat `docs/CaseMind PRD v2.0.pdf` as the v3.0 spec

- **Decision:** The PDF's file name and page footers say v2.0, but its header and content are v3.0 (sections 7A and 7B, the MVP version ladder). We build against v3.0.
- **Alternatives considered:** Rename the file; ask for a corrected export.
- **Reason:** The content is unambiguous. Renaming now would break nothing but adds noise.
- **What I should learn from this:** Always pin which spec version you build against. When a document's metadata and content disagree, trust the content and write down that you did.

## D-003 (2026-11-09): Project memory structure

- **Decision:**
  - `CLAUDE.md`: short, read automatically every session; protocol and hard rules.
  - `docs/STATUS.md`: checklist and next action.
  - `docs/DECISIONS.md`: this log.
  - `/status` and `/wrapup` slash commands.
- **Alternatives considered:** A single long README; relying on git history only.
- **Reason:** Separating "where are we" (STATUS) from "why did we choose this" (DECISIONS) lets each session start in under a minute. Git history alone doesn't record the alternatives that were rejected.
- **What I should learn from this:** Recording rejected alternatives is what makes a decision log useful. It lets you re-open a decision deliberately instead of re-arguing it by accident.

## D-004 (2026-11-09): Structured contradiction checks move before the feature spec

- **Decision:** In the checklist, structured contradiction checks are step 3, ahead of the feature spec (step 4).
- **Alternatives considered:** The order in the original request, with contradiction checks after E3.
- **Reason:** The features `claim_fact_conflicts` and `claim_claim_conflicts` (PRD 5.3) are computed by the consistency engine, so it has to exist and be audited first.
- **What I should learn from this:** Order build steps by data dependency, not by how important each step feels.

## D-005 (2026-11-09): PostgreSQL in Docker for storage (deviation from the PRD)

- **Decision:** Keep PostgreSQL, run only inside Docker Compose (`make up`). The tier separation is enforced by database roles: `casemind_gameplay` has no access to schema `t3_canonical` (verified); only `casemind_vault` does.
- **Alternatives considered:** JSON files or SQLite, as PRD Section 14 suggests for v0.1.
- **Reason:** User decision. The stack must run from Docker with no local database install. Postgres roles also give a second, database-level wall around T3 on top of the code-level tests.
- **What I should learn from this:** A deviation from the spec is fine when it is recorded with its reason. Defence in depth means T3 is protected by two independent mechanisms (schema contract tests in code, role privileges in the database), so one failing doesn't leak the solution.

## D-006 (2026-11-09): uv + ruff; `backend/` stays the single Python project

- **Decision:** uv manages Python 3.12 and dependencies through `backend/uv.lock`; ruff lints (E, F, I, UP, B; E501 left to the formatter). The package stays `app`, and ML code will live in `backend/app/ml/`. The whole codebase was **not** reformatted (`make fmt` is available) to keep this step's diff reviewable.
- **Alternatives considered:** poetry; plain pip with `requirements.txt`; renaming the package to `casemind` under `src/`.
- **Reason:** A lockfile is what makes "one command reproduces the numbers" true months later. uv is fast and also pins the interpreter. Renaming the package would be churn with no learning value.
- **What I should learn from this:** Reproducibility starts with pinned dependencies, not just fixed seeds: the same seed on a different library version can give different results.

## D-007 (2026-11-09): Canaries for text, structural contract tests for IDs

- **Decision:** `T3Canonical` stamps each free-text field (`solution_summary`, ground-truth fact descriptions, lie notes) with a canary derived from sha256(case_id | seed | field path). ID and number fields are protected by `tests/test_tier_contracts.py`, which walks the T0/T1/T2 model types recursively and fails if any T3-only type or field name is reachable.
- **Alternatives considered:** One constant canary per case (the previous `"CANARY_T3_DEFAULT"`); random canaries; putting canaries into every field.
- **Reason:** A canary can't live inside `culprit_id`, because suspect IDs are legitimately public. Random canaries would break determinism (CH-03). One canary per case can't tell you *which* field leaked.
- **What I should learn from this:** Pick the leak detector to match the data type. Text leaks are caught by searching for a planted marker; structural leaks are caught by checking types before any data exists.

## D-008 (2026-11-09): Lies live in T3 as LieAnnotations; T1 shows relationships without numbers

- **Decision:**
  - Intentional lies are recorded as `T3Canonical.lie_annotations` (claim_id, liar, kind, true location), never on the `Claim`.
  - T1 shows `RevealedRelationship` (tags plus the revealing fact ID) and qualitative relationship facts, not edge numbers.
  - A claim "I was at X throughout the window" counts as a lie if the speaker visited any other location in the window.
- **Alternatives considered:** An `is_lie` flag on Claim; keeping raw `RelationshipEdge` in T1; judging lies by the last location in the window (the old behaviour).
- **Reason:** A flag on the Claim would travel with it to the UI and to features, which is label leakage. Raw edge numbers in T1 were a real leak of T3 data. The "last location" rule missed every culprit who returned to their alibi room after the murder.
- **What I should learn from this:** Label leakage often hides in convenient fields. If an attribute is only knowable from the ground truth, it belongs with the ground truth, not with the observation.

## D-009 (2026-11-09): Inaccurate claims by honest innocents are intended "honest confusion"

- **Decision:** When an innocent, non-lying suspect moves during the murder window and then claims a single location for the whole window, the inaccuracy is intended. It is **not** a `LieAnnotation`. It is an accidental inconsistency, which the consistency engine may still flag.
- **Alternatives considered:** Treat it as a generator bug and make honest claims exactly match the true timeline.
- **Reason:** PRD 6.1 says lying, evasion *and honest confusion* must all be possible, and 6.4.B says a contradiction is evidence of inconsistency, not of guilt. Honest confusion produces innocent contradictions, which stop the ranker from learning "any contradiction means guilty".
- **What I should learn from this:** Noise that looks like signal is what makes a synthetic task non-trivial. If innocents never contradicted themselves, the conflict features would be a near-perfect shortcut to the label, and the leakage audit (step 8) should catch exactly that kind of shortcut.

## D-010 (2026-11-09): Solvability check 4 labels difficulty; it no longer filters generated cases

- **Decision:** For generated data, only checks 1–3 decide whether a case is kept: the culprit is not ruled out by the timeline, at least 2 plausible suspects remain, and a red herring exists. Check 4 ("the culprit has the strictly highest hand-weighted evidence score") only sets EASY/MEDIUM/HARD. This applies in `generate_valid_case` and in the dataset generator. Player-built Case Lab cases (v0.2) can still use it as a gate.
- **Alternatives considered:** Keep filtering on check 4; filter on a softer margin.
- **Reason:** Filtering kept only cases that a hand-written rule solves. That guarantees the rule baseline wins and skews the data: honest culprits passed 11 of 48 times, liars 332 of 352, so the kept data had 97% lying culprits against a configured 90%. The PRD (8.2) explicitly wants genuinely under-determined hard cases.
- **What I should learn from this:** A quality filter on training data is itself a model of the label. If the filter uses the same signals as your baseline, it hands the baseline the answer and biases every other statistic (here the lie rate that E2 varies).

## D-011 (2026-11-09): Role-free case sampler, with the culprit chosen by softmax over the PRD 7A.4 score

- **Decision:**
  - Every suspect is drawn from one distribution: traits uniform on [0, 1], and motive goals, victim-related secrets, private secrets, schedules and relationship edges at documented probabilities (`templates.py`, P_* constants).
  - The culprit is sampled from softmax(score / 0.5), where score = motive + opportunity + low composure (PRD 7A.4), among suspects with a motive and a physically possible route.
  - `is_crime_linked` is set only after the culprit is chosen.
  - Evidence wording is identical for culprit and innocents.
  - The trait OOD range is now the full [0, 1] (CH-04).
- **Alternatives considered:** Keep scripted roles and add noise to the evidence; pure argmax culprit choice (the PRD's literal wording); a fully random culprit.
- **Reason:** With scripted roles, the "primary" suspect was the culprit in 400 of 400 cases, and one fact containing the words "crime-linked" named them every time (PRD 8.2 violation). Pure argmax makes the label a deterministic function of latent variables; a fully random culprit makes the evidence meaningless. Softmax keeps motive, opportunity and temperament *informative but not decisive*. Results (`make audit-generator`, 400 cases): the best single rule is 64% top-1 against 25% chance, down from 100%; the culprit lie rate is 90.5% against 90% configured.
- **What I should learn from this:** A synthetic task is only a test of learning if the label is a *noisy* function of what the model can observe. The temperature is the knob between "trivial" (argmax) and "impossible" (uniform), and it must be chosen and documented before seeing model results, not tuned to make the model look good.

## D-012 (2026-11-09): Movement records are points in time; a culprit must be able to reach the scene

- **Decision:** Access and movement facts get `TimeInterval(tick, tick)` instead of `[tick, tick + 10]`. A suspect can only be the culprit if the scene is within one tick's travel of where they are one tick before and one tick after the murder.
- **Alternatives considered:** Change the solver's interval arithmetic instead (step 3); keep teleporting and rely on the validator to reject those cases.
- **Reason:** The hand-check found 4 of 20 manor culprits "teleporting" to the scene: the 10-minute interval said they were still elsewhere at the murder minute, so the solver eliminated them. Rejecting such cases would make the data quietly depend on the bug. Validity rose from 369/400 to 398/400.
- **What I should learn from this:** Keep the time model consistent end to end. If the simulator thinks in instants (ticks), records must be instants too; mixing instants and intervals creates contradictions nobody intended.

## D-013 (2026-11-09): Alibi free text is drawn from one role-neutral phrase pool

- **Decision:** Every alibi's `free_text` is a random phrase from a shared pool, filled only with the claim's own place, time and companions.
- **Alternatives considered:** Keep role-specific phrasings; drop free text entirely.
- **Reason:** Lying culprits always said "I remained at X … per my schedule", which is a perfect text shortcut for any NLP feature and an easy tell for a player.
- **What I should learn from this:** Leakage isn't only in numeric columns. Generated *text* carries the generator's branch structure unless you deliberately decouple wording from the hidden state.

## D-014 (2026-11-09): "I saw Y there" means Y was there at some moment, not throughout

- **Decision:** For people a speaker claims to have seen, the consistency engine flags a contradiction only if Y's records, combined with travel times, make **every** minute of the claimed interval impossible (the same logic as the timeline solver). The speaker's **own** whereabouts are still checked as "throughout the interval". Flags gained `linked_source_ids`, because a conclusion can rest on several records together (MD-05).
- **Alternatives considered:** Keep the per-record "Y was there the whole time" check; drop observed-person checks.
- **Reason:** 24% of exactly-true innocent claims were flagged. The usual pattern: an honest witness truthfully saw the culprit, who then left to commit the murder. False positives are the PRD's headline safety metric (10.1). After the fix: false-positive rate 0% (95% CI 0–0.9%), precision 100%, recall 52% (`make audit-contradictions`). One existing test asserted a false positive (the library is 2 minutes from the study) and was corrected.
- **What I should learn from this:** Translating natural language into logic is where false positives come from. "I saw X" is existential (some moment), while "I was at X" is universal (all moments). Choosing the wrong quantifier makes a precise-looking rule systematically wrong.

## D-015 (2026-11-09): Forensic traces are point-in-time; sampled schedules respect travel time

- **Decision:** Forensic traces are dated to a single tick, like movement records (D-012). Each sampled schedule slot must be reachable from the previous slot within one tick.
- **Alternatives considered:** Add a time tolerance to the consistency engine; let the simulator delay arrivals.
- **Reason:** The last 2% of false positives came from 10-minute trace intervals reaching into the next tick. There were also 28 record pairs in which innocents "teleported" between schedule slots. Both are now 0. A tolerance would have hidden the problem and weakened true detections.
- **What I should learn from this:** Fix inconsistencies where they are created (the generator) rather than where they are noticed (the checker). Otherwise the checker learns to excuse a broken world.

## D-016 (2026-11-09): Cross-speaker "disagreements" that blame nobody

- **Decision:** New `Disagreement` type from `StructuredConsistencyEngine.find_disagreements`. When B says they saw A at X and A's own claim rules out A being at X at every minute of B's interval, the two claims are linked as a disagreement involving both speakers. It is separate from `ContradictionFlag`, which blames one speaker. The PRD's `claim_claim_conflicts` stays self-contradiction only.
- **Alternatives considered:** Treat it as CLAIM_CLAIM blamed on the later speaker; flag both speakers as contradicted; leave it out.
- **Reason:** 72% of COVER_FOR lies went undetected, because the engine never compared two people's statements. Blaming either side would wrongly accuse the honest party. Results (`make audit-contradictions`): 1.25 disagreements per case, 100% involve at least one false claim, and the share of false claims caught by a flag *or* a disagreement rose from 52% to 81% (COVER_FOR from 28% to 77%). The cost is that 37% of accurate innocents are involved in some disagreement, which is why it stays a separate, unblamed signal.
- **What I should learn from this:** Some evidence is symmetric. It tells you *that* something is wrong, not *who* is wrong. Modelling it as symmetric, and letting the learner weigh it, is more honest than forcing an attribution that a rule cannot justify.
