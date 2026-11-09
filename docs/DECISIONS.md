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
