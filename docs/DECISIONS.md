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
