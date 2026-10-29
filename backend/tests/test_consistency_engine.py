# backend/tests/test_consistency_engine.py
import pytest
from pydantic import ValidationError

from app.domain.enums import (
    ContradictionType,
    EvidenceCategory,
    ProvenanceClass,
    VerificationStatus,
)
from app.domain.setting import Location, SettingTemplate
from app.domain.tiers import T1Session
from app.domain.world import Claim, Fact, TimeInterval
from app.engine.consistency import StructuredConsistencyEngine


@pytest.fixture
def blackwood_setting() -> SettingTemplate:
    """
    Mock Blackwood Manor setting:
    - loc_study <-> loc_library: 2 mins
    - loc_library <-> loc_gatehouse: 15 mins
    - loc_study <-> loc_gatehouse: 17 mins
    """
    return SettingTemplate(
        template_id="tpl_blackwood_manor",
        name="Blackwood Manor",
        locations=[
            Location(location_id="loc_study", name="Lord Blackwood's Study", is_restricted=True),
            Location(location_id="loc_library", name="Main Library", is_restricted=False),
            Location(location_id="loc_gatehouse", name="Outer Gatehouse", is_restricted=False),
        ],
        travel_matrix={
            "loc_study": {"loc_library": 2, "loc_gatehouse": 17},
            "loc_library": {"loc_study": 2, "loc_gatehouse": 15},
            "loc_gatehouse": {"loc_library": 15, "loc_study": 17},
        },
    )


def test_setting_template_travel_time_and_validation(blackwood_setting: SettingTemplate):
    """Verifies travel_matrix lookup, same-location 0 travel time, and invalid key rejection."""
    assert blackwood_setting.get_travel_time("loc_study", "loc_study") == 0
    assert blackwood_setting.get_travel_time("loc_study", "loc_library") == 2
    assert blackwood_setting.get_travel_time("loc_library", "loc_gatehouse") == 15

    with pytest.raises(ValidationError, match="unknown destination location_id"):
        SettingTemplate(
            template_id="tpl_bad",
            name="Invalid Manor",
            locations=[Location(location_id="loc_study", name="Study")],
            travel_matrix={"loc_study": {"loc_nonexistent": 5}},
        )


def test_direct_overlap_claim_fact(blackwood_setting: SettingTemplate):
    """
    1. Direct Overlap (CLAIM_FACT):
    Daniel Reed claims he was in loc_library from 21:30 to 22:30 (1290-1350),
    but an ESTABLISHED door-log Fact places him at loc_study at 21:52 (1312-1312).
    """
    door_log_fact = Fact(
        fact_id="fact_door_log_2152",
        case_id="case_blackwood",
        description="Study door badge swipe by Daniel Reed at 21:52",
        subject_id="suspect_reed",
        location_id="loc_study",
        time_interval=TimeInterval(start_min=1312, end_min=1312),
        category=EvidenceCategory.TIMELINE,
        provenance=ProvenanceClass.RECORD,
        reliability=0.98,
        status=VerificationStatus.ESTABLISHED,
    )
    reed_claim = Claim(
        claim_id="claim_reed_library",
        case_id="case_blackwood",
        speaker_id="suspect_reed",
        subject_id="suspect_reed",
        turn_index=1,
        claimed_location_id="loc_library",
        claimed_time_interval=TimeInterval(start_min=1290, end_min=1350),
    )

    flags = StructuredConsistencyEngine.check_claim_against_facts(
        claim=reed_claim,
        facts=[door_log_fact],
        setting=blackwood_setting,
    )

    assert len(flags) == 1
    flag = flags[0]
    assert flag.contradiction_type == ContradictionType.CLAIM_FACT
    assert flag.suspect_id == "suspect_reed"
    assert flag.primary_claim_id == "claim_reed_library"
    assert flag.conflicting_source_id == "fact_door_log_2152"
    assert flag.is_semantic is False


def test_travel_feasibility_claim_fact(blackwood_setting: SettingTemplate):
    """
    2. Travel Feasibility (CLAIM_FACT):
    Suspect claims they were in loc_library until 21:50 (1310), and a fact places
    them at loc_gatehouse at 21:55 (1315) when travel requires 15 minutes.
    """
    gatehouse_fact = Fact(
        fact_id="fact_gatehouse_cctv",
        case_id="case_blackwood",
        description="Gatehouse camera records Reed at 21:55",
        subject_id="suspect_reed",
        location_id="loc_gatehouse",
        time_interval=TimeInterval(start_min=1315, end_min=1315),
        category=EvidenceCategory.TIMELINE,
        provenance=ProvenanceClass.RECORD,
        reliability=0.95,
        status=VerificationStatus.ESTABLISHED,
    )
    reed_claim = Claim(
        claim_id="claim_reed_lib_2150",
        case_id="case_blackwood",
        speaker_id="suspect_reed",
        subject_id="suspect_reed",
        turn_index=2,
        claimed_location_id="loc_library",
        claimed_time_interval=TimeInterval(start_min=1260, end_min=1310),
    )

    flags = StructuredConsistencyEngine.check_claim_against_facts(
        claim=reed_claim,
        facts=[gatehouse_fact],
        setting=blackwood_setting,
    )

    assert len(flags) == 1
    flag = flags[0]
    assert flag.contradiction_type == ContradictionType.CLAIM_FACT
    assert flag.suspect_id == "suspect_reed"
    assert flag.primary_claim_id == "claim_reed_lib_2150"
    assert flag.conflicting_source_id == "fact_gatehouse_cctv"
    assert "15 minutes" in flag.explanation
    assert "5 minutes" in flag.explanation


def test_false_witness_observed_character_claim_fact(blackwood_setting: SettingTemplate):
    """
    3. False Witness / Observed Character (CLAIM_FACT):
    Suspect A claims they were in loc_library at 21:52 and saw suspect_reed there,
    while the study door log proves suspect_reed was in loc_study at 21:52.
    """
    door_log_fact = Fact(
        fact_id="fact_door_log_2152",
        case_id="case_blackwood",
        description="Study door badge swipe by Daniel Reed at 21:52",
        subject_id="suspect_reed",
        location_id="loc_study",
        time_interval=TimeInterval(start_min=1312, end_min=1312),
        category=EvidenceCategory.TIMELINE,
        provenance=ProvenanceClass.RECORD,
        reliability=0.98,
        status=VerificationStatus.ESTABLISHED,
    )
    suspect_a_claim = Claim(
        claim_id="claim_suspect_a_alibi",
        case_id="case_blackwood",
        speaker_id="suspect_a",
        subject_id="suspect_a",
        turn_index=3,
        claimed_location_id="loc_library",
        claimed_time_interval=TimeInterval(start_min=1310, end_min=1315),
        observed_character_ids=["suspect_reed"],
    )

    flags = StructuredConsistencyEngine.check_claim_against_facts(
        claim=suspect_a_claim,
        facts=[door_log_fact],
        setting=blackwood_setting,
    )

    assert len(flags) == 1
    flag = flags[0]
    assert flag.contradiction_type == ContradictionType.CLAIM_FACT
    assert flag.suspect_id == "suspect_a"
    assert flag.primary_claim_id == "claim_suspect_a_alibi"
    assert flag.conflicting_source_id == "fact_door_log_2152"
    assert flag.is_semantic is False


def test_self_contradiction_claim_claim_and_evaluate_session(blackwood_setting: SettingTemplate):
    """
    4. Self-Contradiction (CLAIM_CLAIM):
    On Turn 1, Suspect claims they were in loc_library from 21:00-22:00 (1260-1320).
    On Turn 3, the same Suspect claims they were in loc_gatehouse from 21:30-22:15 (1290-1335).
    """
    claim_turn_1 = Claim(
        claim_id="claim_t1",
        case_id="case_blackwood",
        speaker_id="suspect_reed",
        subject_id="suspect_reed",
        turn_index=1,
        claimed_location_id="loc_library",
        claimed_time_interval=TimeInterval(start_min=1260, end_min=1320),
    )
    claim_turn_3 = Claim(
        claim_id="claim_t3",
        case_id="case_blackwood",
        speaker_id="suspect_reed",
        subject_id="suspect_reed",
        turn_index=3,
        claimed_location_id="loc_gatehouse",
        claimed_time_interval=TimeInterval(start_min=1290, end_min=1335),
    )

    flags = StructuredConsistencyEngine.check_claim_against_claims(
        new_claim=claim_turn_3,
        prior_claims=[claim_turn_1],
        setting=blackwood_setting,
    )
    assert len(flags) == 1
    assert flags[0].contradiction_type == ContradictionType.CLAIM_CLAIM
    assert flags[0].suspect_id == "suspect_reed"
    assert flags[0].primary_claim_id == "claim_t3"
    assert flags[0].conflicting_source_id == "claim_t1"

    # Also verify evaluate_session orders by turn_index and does not double-count
    session = T1Session(
        session_id="sess_01",
        case_id="case_blackwood",
        recorded_claims=[claim_turn_3, claim_turn_1],
        discovered_facts=[],
    )
    session_flags = StructuredConsistencyEngine.evaluate_session(session, blackwood_setting)
    assert len(session_flags) == 1
    assert session_flags[0].contradiction_type == ContradictionType.CLAIM_CLAIM
    assert session_flags[0].primary_claim_id == "claim_t3"
    assert session_flags[0].conflicting_source_id == "claim_t1"


def test_unestablished_or_disputed_fact_ignored(blackwood_setting: SettingTemplate):
    """
    5. Unestablished Fact Ignored:
    Verify that a Fact with status=UNVERIFIED or DISPUTED does NOT trigger a CLAIM_FACT contradiction.
    """
    unverified_fact = Fact(
        fact_id="fact_unverified_rumour",
        case_id="case_blackwood",
        description="Unverified rumour that Reed was in the study at 21:52",
        subject_id="suspect_reed",
        location_id="loc_study",
        time_interval=TimeInterval(start_min=1312, end_min=1312),
        category=EvidenceCategory.TIMELINE,
        provenance=ProvenanceClass.WITNESS,
        reliability=0.4,
        status=VerificationStatus.UNVERIFIED,
    )
    disputed_fact = Fact(
        fact_id="fact_disputed_sighting",
        case_id="case_blackwood",
        description="Disputed sighting of Reed at the gatehouse at 21:55",
        subject_id="suspect_reed",
        location_id="loc_gatehouse",
        time_interval=TimeInterval(start_min=1315, end_min=1315),
        category=EvidenceCategory.TIMELINE,
        provenance=ProvenanceClass.WITNESS,
        reliability=0.5,
        status=VerificationStatus.DISPUTED,
    )
    reed_claim = Claim(
        claim_id="claim_reed_library",
        case_id="case_blackwood",
        speaker_id="suspect_reed",
        subject_id="suspect_reed",
        turn_index=1,
        claimed_location_id="loc_library",
        claimed_time_interval=TimeInterval(start_min=1290, end_min=1350),
    )

    flags = StructuredConsistencyEngine.check_claim_against_facts(
        claim=reed_claim,
        facts=[unverified_fact, disputed_fact],
        setting=blackwood_setting,
    )

    assert flags == []

