# backend/app/features/extract.py
"""
PRD Section 5.3: deterministic, versioned feature functions over T1 facts and claims.

The only inputs are T0 (public case header), T1 (what has been discovered so far) and the setting
template (locations and travel times). There is no parameter through which T2 or T3 could arrive,
so no feature can use the solution, character secrets or undiscovered evidence.
"""
from pydantic import BaseModel, Field

from app.domain.enums import ContradictionType, EvidenceCategory, ProvenanceClass, VerificationStatus
from app.domain.setting import SettingTemplate
from app.domain.tiers import T0Public, T1Session
from app.domain.world import Fact, TimeInterval
from app.engine.consistency import StructuredConsistencyEngine
from app.features.spec import FEATURE_SPEC_VERSION, FEATURES

ESTABLISHED = (VerificationStatus.ESTABLISHED, VerificationStatus.VERIFIED)
RECORD_LIKE = (ProvenanceClass.RECORD, ProvenanceClass.PHYSICAL)
OBSERVED_CLAIM_WEIGHT = 0.5


class SuspectFeatureRow(BaseModel):
    """One suspect in one case at one evidence state (PRD 8.3). IDs are keys, never features."""

    case_id: str
    suspect_id: str
    feature_spec_version: str = FEATURE_SPEC_VERSION
    features: dict[str, float] = Field(default_factory=dict)
    evidence: dict[str, list[str]] = Field(
        default_factory=dict,
        description="MD-08: feature name -> IDs of the T1 facts/claims it was computed from",
    )


def _located(fact: Fact) -> bool:
    return fact.location_id is not None and fact.time_interval is not None


def _supports(fact: Fact, subject_id: str, location_id: str, interval: TimeInterval) -> bool:
    return (
        fact.subject_id == subject_id
        and fact.location_id == location_id
        and fact.time_interval.overlaps(interval)
    )


def compute_suspect_features(
    t0: T0Public,
    t1: T1Session,
    setting: SettingTemplate,
) -> list[SuspectFeatureRow]:
    """Feature rows for every suspect in `t0.suspect_ids`, in that order."""
    facts = [f for f in t1.discovered_facts if f.status in ESTABLISHED]
    located = [f for f in facts if _located(f)]
    claims = t1.recorded_claims
    victim = t0.victim_id
    scene = t0.crime_location_id
    window = t0.crime_window

    flags = StructuredConsistencyEngine.evaluate_session(t1, setting)
    disagreements = StructuredConsistencyEngine.find_disagreements(t1, setting)
    categories_seen = {f.category for f in facts}
    evidence_coverage = len(categories_seen) / len(EvidenceCategory)

    rows: list[SuspectFeatureRow] = []
    for sid in t0.suspect_ids:
        own_claims = [c for c in claims if c.speaker_id == sid]
        whereabouts = [
            c
            for c in own_claims
            if c.subject_id == sid and c.claimed_location_id is not None and c.claimed_time_interval is not None
        ]

        # --- A: motive and opportunity
        motive_facts = [
            f for f in facts if f.category == EvidenceCategory.MOTIVE and {f.subject_id, f.target_id} == {sid, victim}
        ]
        victim_relationships = [r for r in t1.revealed_edges if {r.source_id, r.target_id} == {sid, victim}]
        access_facts = [
            f for f in located if f.subject_id == sid and f.location_id == scene and f.provenance in RECORD_LIKE
        ]
        ruling_out_facts: list[Fact] = []
        if window is not None:
            own_records = [f for f in located if f.subject_id == sid and f.provenance in RECORD_LIKE]
            ruled_out = StructuredConsistencyEngine.ruled_out_minutes(
                scene, window, [(f.location_id, f.time_interval) for f in own_records], setting
            )
            opportunity_overlap = 1.0 - len(ruled_out) / (window.end_min - window.start_min + 1)
            ruling_out_facts = [
                f
                for f in own_records
                if StructuredConsistencyEngine.ruled_out_minutes(
                    scene, window, [(f.location_id, f.time_interval)], setting
                )
            ]
        else:
            opportunity_overlap = 1.0

        # --- B: timeline compatibility and alibi
        scene_facts = [
            f
            for f in located
            if f.subject_id == sid and f.location_id == scene and window is not None and f.time_interval.overlaps(window)
        ]
        alibi_strength = 0.0
        alibi_sources: list[str] = []
        for c in whereabouts:
            if window is not None and not c.claimed_time_interval.overlaps(window):
                continue
            supporting = [f for f in located if _supports(f, sid, c.claimed_location_id, c.claimed_time_interval)]
            witnesses = [
                other
                for other in claims
                if other.speaker_id != sid
                and sid in other.observed_character_ids
                and other.claimed_location_id == c.claimed_location_id
                and other.claimed_time_interval is not None
                and other.claimed_time_interval.overlaps(c.claimed_time_interval)
            ]
            alibi_strength += sum(f.reliability for f in supporting) + OBSERVED_CLAIM_WEIGHT * len(witnesses)
            alibi_sources += [c.claim_id, *(f.fact_id for f in supporting), *(w.claim_id for w in witnesses)]
        corroborated_claims = [c for c in own_claims if c.has_corroboration_claim]
        claimed_corroboration_share = len(corroborated_claims) / len(own_claims) if own_claims else 0.0

        # --- C: evidence reliability and contradictions
        own_flags = [f for f in flags if f.suspect_id == sid]
        fact_flags = [f for f in own_flags if f.contradiction_type == ContradictionType.CLAIM_FACT]
        claim_flags = [f for f in own_flags if f.contradiction_type == ContradictionType.CLAIM_CLAIM]
        own_disagreements = [d for d in disagreements if sid in d.suspect_ids]
        unsupported_claims = [
            c
            for c in whereabouts
            if not any(_supports(f, sid, c.claimed_location_id, c.claimed_time_interval) for f in located)
        ]
        unverified_claim_share = len(unsupported_claims) / len(whereabouts) if whereabouts else 0.0

        # --- D: interview answers (claims made in reply to questions, turn >= 1)
        answers = [c for c in own_claims if c.turn_index >= 1]
        dodged = [c for c in answers if c.claimed_location_id is None]
        answer_ids = {c.claim_id for c in answers}
        refuted_answers = sorted({f.primary_claim_id for f in fact_flags if f.primary_claim_id in answer_ids})

        values = {
            "motive_evidence": sum(f.reliability for f in motive_facts),
            "victim_relationship_records": float(len(victim_relationships)),
            "access_evidence": sum(f.reliability for f in access_facts),
            "opportunity_overlap": opportunity_overlap,
            "scene_presence_in_window": sum(f.reliability for f in scene_facts),
            "alibi_strength": alibi_strength,
            "claimed_corroboration_share": claimed_corroboration_share,
            "claim_fact_conflicts": float(len({f.primary_claim_id for f in fact_flags})),
            "claim_claim_conflicts": float(len({f.primary_claim_id for f in claim_flags})),
            "disagreement_count": float(len(own_disagreements)),
            "unverified_claim_share": unverified_claim_share,
            "interview_answers": float(len(answers)),
            "evasive_answer_share": len(dodged) / len(answers) if answers else 0.0,
            "answers_refuted": float(len(refuted_answers)),
            "evidence_coverage": evidence_coverage,
        }
        # MD-08: the T1 facts and claims each feature was computed from, so explanations can cite them.
        evidence = {
            "motive_evidence": [f.fact_id for f in motive_facts],
            "victim_relationship_records": [r.evidence_fact_id for r in victim_relationships],
            "access_evidence": [f.fact_id for f in access_facts],
            "opportunity_overlap": [f.fact_id for f in ruling_out_facts],
            "scene_presence_in_window": [f.fact_id for f in scene_facts],
            "alibi_strength": alibi_sources,
            "claimed_corroboration_share": [c.claim_id for c in corroborated_claims],
            "claim_fact_conflicts": [i for f in fact_flags for i in (f.primary_claim_id, *f.linked_source_ids)],
            "claim_claim_conflicts": [i for f in claim_flags for i in (f.primary_claim_id, *f.linked_source_ids)],
            "disagreement_count": [i for d in own_disagreements for i in d.claim_ids],
            "unverified_claim_share": [c.claim_id for c in unsupported_claims],
            "interview_answers": [c.claim_id for c in answers],
            "evasive_answer_share": [c.claim_id for c in dodged],
            "answers_refuted": [
                i for f in fact_flags if f.primary_claim_id in answer_ids for i in (f.primary_claim_id, *f.linked_source_ids)
            ],
            "evidence_coverage": [],
        }
        rows.append(
            SuspectFeatureRow(
                case_id=t0.case_id,
                suspect_id=sid,
                features={f.name: round(values[f.name], 6) for f in FEATURES},
                evidence={f.name: list(dict.fromkeys(evidence[f.name])) for f in FEATURES},
            )
        )
    return rows
