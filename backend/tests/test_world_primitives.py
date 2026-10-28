# backend/tests/test_world_primitives.py
import pytest
from pydantic import ValidationError

from app.domain.enums import EvidenceCategory, ProvenanceClass, VerificationStatus
from app.domain.world import Claim, Fact, TimeInterval


def test_time_interval_overlap_math():
    # Crime window: 21:30 (1290) to 22:30 (1350) -> 60 mins
    crime_window = TimeInterval(start_min=1290, end_min=1350)
    # Suspect in study: 21:45 (1305) to 22:15 (1335) -> 30 mins overlap
    suspect_window = TimeInterval(start_min=1305, end_min=1335)

    assert crime_window.duration == 60
    assert crime_window.overlaps(suspect_window) is True
    assert crime_window.overlap_duration(suspect_window) == 30


def test_invalid_time_interval_rejected():
    with pytest.raises(ValidationError):
        TimeInterval(start_min=1350, end_min=1290)


def test_model_inferred_cannot_become_fact():
    """Enforces PRD Principle 4 & Section 5.1: Models can never create Facts."""
    with pytest.raises(ValidationError, match="MODEL_INFERRED items can never be stored"):
        Fact(
            fact_id="f_bad",
            case_id="case_01",
            description="Model thinks Reed is guilty",
            category=EvidenceCategory.MOTIVE,
            provenance=ProvenanceClass.MODEL_INFERRED,
            reliability=0.9,
        )


def test_claim_defaults_to_unverified_self_report():
    """Enforces PRD Requirement MD-04: Claims start as SELF_REPORT and UNVERIFIED."""
    claim = Claim(
        claim_id="c_01",
        case_id="case_01",
        speaker_id="suspect_reed",
        subject_id="suspect_reed",
        turn_index=1,
        claimed_location_id="loc_library",
        claimed_time_interval=TimeInterval(start_min=1290, end_min=1350),
    )
    assert claim.provenance == ProvenanceClass.SELF_REPORT
    assert claim.status == VerificationStatus.UNVERIFIED