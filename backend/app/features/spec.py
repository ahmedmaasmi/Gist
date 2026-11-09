# backend/app/features/spec.py
"""
PRD Section 5.3: the feature specification. Human-readable version: docs/FEATURES.md
(tests/test_features.py keeps the two in sync).

Groups follow the E1 ablation (PRD 9.1):
  A        motive and opportunity
  B        timeline compatibility and alibi       (E1 variant B = A + B)
  C        evidence reliability and contradictions (E1 variant C = A + B + C)
  context  case-level context, included in every variant

Bump FEATURE_SPEC_VERSION whenever any definition changes; every dataset and model records it.
"""
from dataclasses import dataclass

FEATURE_SPEC_VERSION = "1.0.0"


@dataclass(frozen=True)
class FeatureDef:
    name: str
    group: str
    description: str


FEATURES: tuple[FeatureDef, ...] = (
    FeatureDef(
        "motive_evidence",
        "A",
        "Reliability-weighted count of established MOTIVE facts linking the suspect and the victim.",
    ),
    FeatureDef(
        "victim_relationship_records",
        "A",
        "Number of discovered relationship records between the suspect and the victim (either direction).",
    ),
    FeatureDef(
        "access_evidence",
        "A",
        "Reliability-weighted count of established RECORD/PHYSICAL facts placing the suspect at the "
        "crime location at any time.",
    ),
    FeatureDef(
        "opportunity_overlap",
        "A",
        "Share of crime-window minutes in which the suspect's established location records and the "
        "travel-time matrix still allow presence at the scene (1 = no record rules any minute out).",
    ),
    FeatureDef(
        "scene_presence_in_window",
        "B",
        "Reliability-weighted count of established facts placing the suspect at the crime location "
        "inside the crime window.",
    ),
    FeatureDef(
        "alibi_strength",
        "B",
        "Independent support for the suspect's own whereabouts claims that overlap the crime window: "
        "established facts at the claimed place and time (weight = reliability) plus other suspects' "
        "claims of seeing them there (weight 0.5 each, self-reports).",
    ),
    FeatureDef(
        "claimed_corroboration_share",
        "B",
        "Fraction of the suspect's claims in which they say a record or witness backs them up.",
    ),
    FeatureDef(
        "claim_fact_conflicts",
        "C",
        "Number of the suspect's claims refuted by established facts (CLAIM_FACT flags).",
    ),
    FeatureDef(
        "claim_claim_conflicts",
        "C",
        "Number of the suspect's claims that contradict their own earlier claims (CLAIM_CLAIM flags).",
    ),
    FeatureDef(
        "disagreement_count",
        "C",
        "Number of cross-speaker disagreements the suspect is part of (D-016; blames nobody).",
    ),
    FeatureDef(
        "unverified_claim_share",
        "C",
        "Fraction of the suspect's claims not supported by any established fact at the claimed place "
        "and time. (Claims are never auto-verified, MD-04, so support is computed, not read from status.)",
    ),
    FeatureDef(
        "evidence_coverage",
        "context",
        "Fraction of the five evidence categories with at least one discovered fact (same for every "
        "suspect in a case state).",
    ),
)

FEATURE_GROUPS: dict[str, list[str]] = {}
for _f in FEATURES:
    FEATURE_GROUPS.setdefault(_f.group, []).append(_f.name)

# PRD 5.3 exclusion list, enforced on feature names (tests/test_features.py) and by the signature of
# compute_suspect_features, which can only receive T0, T1 and the setting.
EXCLUDED_NAME_TOKENS = frozenset(
    {"id", "ids", "name", "names", "culprit", "role", "secret", "lie", "lies", "truth", "canary",
     "guilty", "label", "t2", "t3", "seed"}
)
