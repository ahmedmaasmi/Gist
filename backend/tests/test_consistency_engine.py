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
            locations=[
                Location(location_id="loc_study", name="Study", is_restricted=True),
                Location(location_id="loc_library", name="Library"),
                Location(location_id="loc_gatehouse", name="Gatehouse"),
            ],
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
    Suspect A claims they were at loc_gatehouse 21:50-21:55 and saw suspect_reed there,
    while the study door log proves suspect_reed was in loc_study at 21:52. The study is
    17 minutes from the gatehouse, so Reed cannot have been there at any minute of the claim.
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
        claimed_location_id="loc_gatehouse",
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
    assert flag.linked_source_ids == ["fact_door_log_2152"]
    assert flag.is_semantic is False


def test_seeing_someone_needs_only_one_possible_moment(blackwood_setting: SettingTemplate):
    """
    "I saw Reed in the library 21:50-21:55" is compatible with a study swipe at 21:52: the study is
    2 minutes away, so Reed could have been in the library at 21:50. Flagging it would accuse an
    honest witness (a false positive, the headline safety metric in PRD 10.1).
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
    witness_claim = Claim(
        claim_id="claim_suspect_a_alibi",
        case_id="case_blackwood",
        speaker_id="suspect_a",
        subject_id="suspect_a",
        turn_index=3,
        claimed_location_id="loc_library",
        claimed_time_interval=TimeInterval(start_min=1310, end_min=1315),
        observed_character_ids=["suspect_reed"],
    )
    assert StructuredConsistencyEngine.check_claim_against_facts(
        claim=witness_claim, facts=[door_log_fact], setting=blackwood_setting
    ) == []

    # Two gatehouse swipes that together rule out every minute DO contradict it (both linked)
    early_swipe = door_log_fact.model_copy(
        update={
            "fact_id": "fact_gate_2146",
            "location_id": "loc_gatehouse",
            "time_interval": TimeInterval(start_min=1306, end_min=1306),
        }
    )
    late_swipe = door_log_fact.model_copy(
        update={
            "fact_id": "fact_gate_2158",
            "location_id": "loc_gatehouse",
            "time_interval": TimeInterval(start_min=1318, end_min=1318),
        }
    )
    flags = StructuredConsistencyEngine.check_claim_against_facts(
        claim=witness_claim, facts=[early_swipe, late_swipe], setting=blackwood_setting
    )
    assert len(flags) == 1
    assert set(flags[0].linked_source_ids) == {"fact_gate_2146", "fact_gate_2158"}


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



def test_no_false_positives_on_accurate_generated_claims():
    """
    PRD 10.1 headline safety metric on generated cases: a claim that is exactly true must never be
    flagged. (Before step 3 this was 24%: 'I saw Y' was read as 'Y was there the whole time', and
    10-minute record intervals placed people at the next tick.)
    """
    from app.evaluation.contradiction_audit import run

    result = run(seeds=6)
    assert result["confusion"]["FP"] == 0, result["flag_rate_by_category"]
    assert result["recall_inaccurate_claims"][0] > 0.5


def _session_with(claims):
    from app.domain.tiers import T1Session

    return T1Session(session_id="s", case_id="case_blackwood", recorded_claims=claims)


def test_cross_speaker_disagreement_blames_nobody(blackwood_setting: SettingTemplate):
    """D-016: B says they were with A at the gatehouse; A says the library throughout -> disagreement."""
    b_claim = Claim(
        claim_id="claim_b", case_id="case_blackwood", speaker_id="suspect_b", subject_id="suspect_b",
        turn_index=0, claimed_location_id="loc_gatehouse",
        claimed_time_interval=TimeInterval(start_min=1260, end_min=1280),
        observed_character_ids=["suspect_a"],
    )
    a_claim = Claim(
        claim_id="claim_a", case_id="case_blackwood", speaker_id="suspect_a", subject_id="suspect_a",
        turn_index=0, claimed_location_id="loc_library",
        claimed_time_interval=TimeInterval(start_min=1250, end_min=1290),
    )
    session = _session_with([b_claim, a_claim])
    found = StructuredConsistencyEngine.find_disagreements(session, blackwood_setting)
    assert len(found) == 1
    assert set(found[0].suspect_ids) == {"suspect_a", "suspect_b"}
    assert set(found[0].claim_ids) == {"claim_a", "claim_b"}
    # Not a contradiction of either speaker on its own
    assert StructuredConsistencyEngine.evaluate_session(session, blackwood_setting) == []


def test_no_disagreement_when_both_can_be_true(blackwood_setting: SettingTemplate):
    """A was in the library 21:00-21:05 only; B saw A in the study (2 min away) 21:00-21:20: compatible."""
    b_claim = Claim(
        claim_id="claim_b", case_id="case_blackwood", speaker_id="suspect_b", subject_id="suspect_b",
        turn_index=0, claimed_location_id="loc_study",
        claimed_time_interval=TimeInterval(start_min=1260, end_min=1280),
        observed_character_ids=["suspect_a"],
    )
    a_claim = Claim(
        claim_id="claim_a", case_id="case_blackwood", speaker_id="suspect_a", subject_id="suspect_a",
        turn_index=0, claimed_location_id="loc_library",
        claimed_time_interval=TimeInterval(start_min=1260, end_min=1265),
    )
    assert StructuredConsistencyEngine.find_disagreements(_session_with([b_claim, a_claim]), blackwood_setting) == []


def test_generated_disagreements_always_involve_a_false_claim():
    from app.evaluation.contradiction_audit import run

    result = run(seeds=6)
    assert result["disagreements"]["count"] > 0
    assert result["disagreements"]["valid_share"][0] == 1.0
