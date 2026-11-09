# CaseMind feature specification

Version: 1.1.0 (`FEATURE_SPEC_VERSION` in `backend/app/features/spec.py`). 1.1.0 adds group D, the interview features (D-029).

> Scores on synthetic cases measure how well a model recovers the generator's logic.
> They are not evidence of real-world investigative ability (PRD 1).

## Scope

- **One row** = one suspect in one case at one evidence state (PRD 8.3).
- **Inputs:** T0 (public case header), T1 (facts discovered and claims recorded *so far*) and the setting template (locations, travel times).
- **Signature as a guarantee:** `compute_suspect_features(t0, t1, setting)` has no parameter through which T2 or T3 data could arrive. A test asserts the signature.
- **Deterministic:** the same inputs always give the same row. Values are rounded to 6 decimals.
- **Versioned:** any change to a definition bumps the version, and every dataset and model records it.
- **Not features:** `case_id` and `suspect_id` are row keys only.

## Exclusion list (PRD 5.3)

Never used as features:
- case ID, suspect ID, names, occupations, voice notes
- canonical role, culprit, lie annotations, `is_crime_linked`, any T2 or T3 field
- anything computed from evidence not yet discovered in that state

Feature names may not contain the tokens `id, name, culprit, role, secret, lie, truth, canary, guilty, label, t2, t3, seed` (enforced by a test).

Relative features (rank or z-score within a case) are allowed if computed from T1 only. None are defined in v1.0.0.

## Features

Groups follow the E1 ablation (PRD 9.1):
- **A:** motive and opportunity
- **A + B:** adds timeline compatibility and alibi
- **A + B + C:** adds evidence reliability and contradictions
- **D:** interview answers (added in 1.1.0 after E3; not part of the E1 variants)
- **context:** included in every variant

"Established" means status ESTABLISHED or VERIFIED.

| Feature | Group | Definition |
|---|---|---|
| `motive_evidence` | A | Sum of reliabilities of established MOTIVE facts whose subject and target are the suspect and the victim (either way round). |
| `victim_relationship_records` | A | Number of revealed relationships between the suspect and the victim (either direction). |
| `access_evidence` | A | Sum of reliabilities of established RECORD/PHYSICAL facts placing the suspect at the crime location, at any time. |
| `opportunity_overlap` | A | 1 − (crime-window minutes ruled out ÷ window minutes). A record of the suspect elsewhere at minute *t* rules out [*t* − travel + 1, *t* + travel − 1], the same rule as the timeline solver. |
| `scene_presence_in_window` | B | Sum of reliabilities of established facts placing the suspect at the crime location inside the crime window. |
| `alibi_strength` | B | For each of the suspect's own whereabouts claims that overlaps the window: reliabilities of established facts at the claimed place and time, plus 0.5 for each other suspect's claim of seeing them there. |
| `claimed_corroboration_share` | B | Fraction of the suspect's claims in which they say a record or witness backs them up. |
| `claim_fact_conflicts` | C | Number of the suspect's claims with at least one CLAIM_FACT flag. |
| `claim_claim_conflicts` | C | Number of the suspect's claims with at least one CLAIM_CLAIM (self-contradiction) flag. |
| `disagreement_count` | C | Number of cross-speaker disagreements the suspect is part of (D-016). Disagreements blame nobody. |
| `unverified_claim_share` | C | Fraction of the suspect's whereabouts claims with no established fact at the claimed place and time. Support is computed, because claims are never auto-verified (MD-04). |
| `interview_answers` | D | Number of answers the suspect gave to the detective's questions (turn ≥ 1), "I don't remember" included. |
| `evasive_answer_share` | D | Fraction of those answers that were "I don't remember" (no location). |
| `answers_refuted` | D | Number of those answers refuted by an established fact (CLAIM_FACT). |
| `evidence_coverage` | context | Fraction of the 5 evidence categories with at least one discovered fact. Same value for every suspect in a case state. |

## Known properties to watch (leakage audit, step 8)

- `claimed_corroboration_share`: lying culprits never claim corroboration in the generator. This is plausible behaviour, but possibly a near-shortcut.
- `claim_claim_conflicts` is always 0 in generated cases, because each suspect makes one initial claim. It only varies during play.
- `access_evidence` counts every tick spent in a restricted crime room, so its scale is large. Models must scale features (step 7).

## Model inputs (step 7)

The models do not see a different spec. They see the 12 features above **plus 11 within-state relative versions** (`<name>_rel`). Each relative version is the feature minus its mean over the suspects of the same evidence state.

- **Why:** a per-suspect (pointwise) model otherwise only knows "how much motive", not "more motive than the others".
- **Scope:** relative features use only the same state's T1 values, which PRD 5.3 allows.
- **Not for context features:** `evidence_coverage` gets no relative version, because it is identical for everyone in a state.
- **Where:** they are built in `backend/app/ml/data.py` and do not change `FEATURE_SPEC_VERSION`.

## Evidence links (MD-08, step 7b)

Every feature row also carries `evidence`: for each feature, the IDs of the T1 facts and claims it was computed from. For example, `scene_presence_in_window → [fact_…_move_051]`, or `claim_fact_conflicts → [the refuted claim, the record that refutes it]`. The feature *values* are unchanged; this was verified as identical on 120 cases before and after. The ranker uses these links to cite evidence in explanations, and to run the "remove this evidence" counterfactual.
