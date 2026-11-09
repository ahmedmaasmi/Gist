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
        motive_evidence = sum(
            f.reliability
            for f in facts
            if f.category == EvidenceCategory.MOTIVE
            and {f.subject_id, f.target_id} == {sid, victim}
        )
        victim_relationship_records = sum(
            1 for r in t1.revealed_edges if {r.source_id, r.target_id} == {sid, victim}
        )
        access_evidence = sum(
            f.reliability
            for f in located
            if f.subject_id == sid and f.location_id == scene and f.provenance in RECORD_LIKE
        )
        if window is not None:
            sightings = [
                (f.location_id, f.time_interval)
                for f in located
                if f.subject_id == sid and f.provenance in RECORD_LIKE
            ]
            ruled_out = StructuredConsistencyEngine.ruled_out_minutes(scene, window, sightings, setting)
            opportunity_overlap = 1.0 - len(ruled_out) / (window.end_min - window.start_min + 1)
        else:
            opportunity_overlap = 1.0

        # --- B: timeline compatibility and alibi
        scene_presence_in_window = sum(
            f.reliability
            for f in located
            if f.subject_id == sid
            and f.location_id == scene
            and window is not None
            and f.time_interval.overlaps(window)
        )
        alibi_strength = 0.0
        for c in whereabouts:
            if window is not None and not c.claimed_time_interval.overlaps(window):
                continue
            alibi_strength += sum(
                f.reliability
                for f in located
                if _supports(f, sid, c.claimed_location_id, c.claimed_time_interval)
            )
            alibi_strength += OBSERVED_CLAIM_WEIGHT * sum(
                1
                for other in claims
                if other.speaker_id != sid
                and sid in other.observed_character_ids
                and other.claimed_location_id == c.claimed_location_id
                and other.claimed_time_interval is not None
                and other.claimed_time_interval.overlaps(c.claimed_time_interval)
            )
        claimed_corroboration_share = (
            sum(c.has_corroboration_claim for c in own_claims) / len(own_claims) if own_claims else 0.0
        )

        # --- C: evidence reliability and contradictions
        own_flags = [f for f in flags if f.suspect_id == sid]
        claim_fact_conflicts = len(
            {f.primary_claim_id for f in own_flags if f.contradiction_type == ContradictionType.CLAIM_FACT}
        )
        claim_claim_conflicts = len(
            {f.primary_claim_id for f in own_flags if f.contradiction_type == ContradictionType.CLAIM_CLAIM}
        )
        disagreement_count = sum(1 for d in disagreements if sid in d.suspect_ids)
        unsupported = sum(
            1
            for c in whereabouts
            if not any(_supports(f, sid, c.claimed_location_id, c.claimed_time_interval) for f in located)
        )
        unverified_claim_share = unsupported / len(whereabouts) if whereabouts else 0.0

        values = {
            "motive_evidence": motive_evidence,
            "victim_relationship_records": float(victim_relationship_records),
            "access_evidence": access_evidence,
            "opportunity_overlap": opportunity_overlap,
            "scene_presence_in_window": scene_presence_in_window,
            "alibi_strength": alibi_strength,
            "claimed_corroboration_share": claimed_corroboration_share,
            "claim_fact_conflicts": float(claim_fact_conflicts),
            "claim_claim_conflicts": float(claim_claim_conflicts),
            "disagreement_count": float(disagreement_count),
            "unverified_claim_share": unverified_claim_share,
            "evidence_coverage": evidence_coverage,
        }
        rows.append(
            SuspectFeatureRow(
                case_id=t0.case_id,
                suspect_id=sid,
                features={f.name: round(values[f.name], 6) for f in FEATURES},
            )
        )
    return rows
