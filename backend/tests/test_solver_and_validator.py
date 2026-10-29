# backend/tests/test_solver_and_validator.py
import pytest

from app.domain.character import (
    Character,
    CharacterGoal,
    CharacterSecret,
    CharacterTraits,
    RelationshipEdge,
    RelationshipGraph,
    ScheduleSlot,
)
from app.domain.enums import (
    ContradictionType,
    EvidenceCategory,
    GoalType,
    ProvenanceClass,
    RelationshipTag,
    VerificationStatus,
)
from app.domain.setting import Location, SettingTemplate
from app.domain.simulation import SimulatedCaseBundle
from app.domain.tiers import (
    T0Public,
    T1Session,
    T2CharacterKnowledge,
    T3Canonical,
)
from app.domain.world import (
    CanonicalEvent,
    Claim,
    ContradictionFlag,
    Fact,
    SimulationConfig,
    TimeInterval,
)
from app.engine.simulator import SocialSimulator
from app.engine.solver import (
    CaseSolvabilityValidator,
    CaseValidationReport,
    SymbolicTimelineSolver,
)


@pytest.fixture
def manor_setting() -> SettingTemplate:
    """
    4-room setting template with travel times:
      - loc_study (crime scene)
      - loc_hall (5 min from study)
      - loc_garden (15 min from study)
      - loc_boathouse (25 min from study)
    """
    return SettingTemplate(
        template_id="tpl_manor",
        name="Blackwood Manor",
        locations=[
            Location(location_id="loc_study", name="Study", is_restricted=True),
            Location(location_id="loc_hall", name="Great Hall", is_restricted=False),
            Location(location_id="loc_garden", name="Conservatory Garden", is_restricted=False),
            Location(location_id="loc_boathouse", name="Boathouse", is_restricted=False),
        ],
        travel_matrix={
            "loc_study": {
                "loc_study": 0,
                "loc_hall": 5,
                "loc_garden": 15,
                "loc_boathouse": 25,
            },
            "loc_hall": {
                "loc_study": 5,
                "loc_hall": 0,
                "loc_garden": 10,
                "loc_boathouse": 20,
            },
            "loc_garden": {
                "loc_study": 15,
                "loc_hall": 10,
                "loc_garden": 0,
                "loc_boathouse": 10,
            },
            "loc_boathouse": {
                "loc_study": 25,
                "loc_hall": 20,
                "loc_garden": 10,
                "loc_boathouse": 0,
            },
        },
    )


def _make_base_bundle(
    setting: SettingTemplate,
    culprit_id: str = "suspect_b",
    t1_facts: list[Fact] | None = None,
    t1_claims: list[Claim] | None = None,
    t1_flags: list[ContradictionFlag] | None = None,
) -> SimulatedCaseBundle:
    """Helper to construct a clean 4-suspect SimulatedCaseBundle for validator tests."""
    case_id = "case_val_test"
    murder_window = TimeInterval(start_min=1300, end_min=1320)
    suspect_ids = ["suspect_a", "suspect_b", "suspect_c", "suspect_d"]

    config = SimulationConfig(
        case_id=case_id,
        seed=42,
        start_min=1260,
        end_min=1380,
        tick_size_min=10,
        victim_id="victim_v",
        crime_location_id="loc_study",
        murder_window=murder_window,
        forced_culprit_id=culprit_id,
    )

    t0 = T0Public(
        case_id=case_id,
        title="Murder at Blackwood Manor",
        victim_id="victim_v",
        crime_location_id="loc_study",
        crime_window=murder_window,
        suspect_ids=suspect_ids,
    )

    t1 = T1Session(
        session_id="sess_val_test",
        case_id=case_id,
        current_turn=1,
        discovered_facts=t1_facts or [],
        recorded_claims=t1_claims or [],
        contradiction_flags=t1_flags or [],
    )

    t2: dict[str, T2CharacterKnowledge] = {
        s: T2CharacterKnowledge(case_id=case_id, character_id=s)
        for s in suspect_ids
    }

    t3 = T3Canonical(
        case_id=case_id,
        culprit_id=culprit_id,
        crime_location_id="loc_study",
        crime_window=murder_window,
        ground_truth_facts=[],
        canonical_events=[],
        relationship_graph=RelationshipGraph(),
        canary_token="CANARY_T3_VAL_TEST",
    )

    return SimulatedCaseBundle(
        config=config,
        t0_public=t0,
        t1_session=t1,
        t2_knowledge=t2,
        t3_canonical=t3,
        canonical_events=[],
        log_hash="deadbeef" * 8,
    )


# ==============================================================================
# 1. SymbolicTimelineSolver Elimination & Distribution
# ==============================================================================
def test_symbolic_timeline_solver_eliminates_distant_suspect(
    manor_setting: SettingTemplate,
) -> None:
    """
    Construct a 4-suspect case where Suspect A has an ESTABLISHED RECORD (reliability=0.95)
    in a distant location (loc_boathouse, travel_time=25 min to loc_study) across the
    murder window [1300, 1320].
    Verify Suspect A is eliminated with a clear explanation and gets 0.0 probability,
    while the remaining 3 suspects each get 1/3 (~0.3333).
    """
    murder_window = TimeInterval(start_min=1300, end_min=1320)
    t0 = T0Public(
        case_id="case_001",
        title="Boathouse Alibi Case",
        victim_id="victim_v",
        crime_location_id="loc_study",
        crime_window=murder_window,
        suspect_ids=["suspect_a", "suspect_b", "suspect_c", "suspect_d"],
    )

    # Suspect A is recorded at loc_boathouse during [1295, 1305].
    # With 25 min travel time to loc_study, blocked interval at loc_study is:
    # [1295 - 25 + 1, 1305 + 25 - 1] = [1271, 1329], which completely covers [1300, 1320].
    t1 = T1Session(
        session_id="sess_001",
        case_id="case_001",
        discovered_facts=[
            Fact(
                fact_id="fact_boathouse_swipe_a",
                case_id="case_001",
                description="Boathouse smart-lock log records suspect_a inside from 1295 to 1305.",
                subject_id="suspect_a",
                location_id="loc_boathouse",
                time_interval=TimeInterval(start_min=1295, end_min=1305),
                category=EvidenceCategory.TIMELINE,
                provenance=ProvenanceClass.RECORD,
                reliability=0.95,
                status=VerificationStatus.ESTABLISHED,
            )
        ],
    )

    eliminated = SymbolicTimelineSolver.find_eliminated_suspects(
        t0=t0,
        t1=t1,
        setting=manor_setting,
        crime_location_id="loc_study",
        murder_window=murder_window,
    )

    assert list(eliminated.keys()) == ["suspect_a"]
    assert "suspect_a" in eliminated["suspect_a"]
    assert "loc_boathouse" in eliminated["suspect_a"]
    assert "fact_boathouse_swipe_a" in eliminated["suspect_a"]

    dist = SymbolicTimelineSolver.predict_distribution(
        t0=t0,
        t1=t1,
        setting=manor_setting,
        crime_location_id="loc_study",
        murder_window=murder_window,
    )

    assert dist["suspect_a"] == pytest.approx(0.0)
    assert dist["suspect_b"] == pytest.approx(1.0 / 3.0, abs=1e-4)
    assert dist["suspect_c"] == pytest.approx(1.0 / 3.0, abs=1e-4)
    assert dist["suspect_d"] == pytest.approx(1.0 / 3.0, abs=1e-4)
    assert sum(dist.values()) == pytest.approx(1.0)


# ==============================================================================
# 2. Low-Reliability Witness Does Not Hard-Eliminate
# ==============================================================================
def test_low_reliability_witness_does_not_hard_eliminate(
    manor_setting: SettingTemplate,
) -> None:
    """
    Verify that a WITNESS fact with reliability=0.60 (or even high reliability WITNESS,
    or low reliability RECORD) does NOT trigger hard logical elimination in
    SymbolicTimelineSolver (PRD Section 8.2 / 8.5).
    """
    murder_window = TimeInterval(start_min=1300, end_min=1320)
    t0 = T0Public(
        case_id="case_002",
        title="Noisy Witness Case",
        victim_id="victim_v",
        crime_location_id="loc_study",
        crime_window=murder_window,
        suspect_ids=["suspect_a", "suspect_b", "suspect_c", "suspect_d"],
    )

    t1 = T1Session(
        session_id="sess_002",
        case_id="case_002",
        discovered_facts=[
            Fact(
                fact_id="fact_noisy_witness_a",
                case_id="case_002",
                description="Witness thought they saw suspect_a at the Boathouse from 1290 to 1330.",
                subject_id="suspect_a",
                location_id="loc_boathouse",
                time_interval=TimeInterval(start_min=1290, end_min=1330),
                category=EvidenceCategory.TIMELINE,
                provenance=ProvenanceClass.WITNESS,
                reliability=0.60,
                status=VerificationStatus.ESTABLISHED,
            ),
            Fact(
                fact_id="fact_low_rel_record_b",
                case_id="case_002",
                description="Smudged paper sign-in sheet for suspect_b at Boathouse.",
                subject_id="suspect_b",
                location_id="loc_boathouse",
                time_interval=TimeInterval(start_min=1290, end_min=1330),
                category=EvidenceCategory.TIMELINE,
                provenance=ProvenanceClass.RECORD,
                reliability=0.70,  # Below 0.85 threshold
                status=VerificationStatus.ESTABLISHED,
            ),
        ],
    )

    eliminated = SymbolicTimelineSolver.find_eliminated_suspects(
        t0=t0,
        t1=t1,
        setting=manor_setting,
        crime_location_id="loc_study",
        murder_window=murder_window,
    )
    assert eliminated == {}

    dist = SymbolicTimelineSolver.predict_distribution(
        t0=t0,
        t1=t1,
        setting=manor_setting,
        crime_location_id="loc_study",
        murder_window=murder_window,
    )
    for s in t0.suspect_ids:
        assert dist[s] == pytest.approx(0.25)


# ==============================================================================
# 3. Valid Case Passes (CH-05 & CL-02)
# ==============================================================================
def test_valid_case_passes_validator(manor_setting: SettingTemplate) -> None:
    """
    Verify a well-formed case bundle (where the culprit is plausible, at least 2 suspects
    survive timeline elimination, at least 1 innocent red herring exists, and the culprit
    has top discoverable evidence support) passes with is_valid=True and a valid
    difficulty_estimate.
    """
    murder_window = TimeInterval(start_min=1300, end_min=1320)
    facts = [
        # Suspect A (innocent) is eliminated by hard alibi at Boathouse
        Fact(
            fact_id="fact_a_alibi",
            case_id="case_val_test",
            description="Boathouse badge swipe for suspect_a.",
            subject_id="suspect_a",
            location_id="loc_boathouse",
            time_interval=TimeInterval(start_min=1295, end_min=1315),
            category=EvidenceCategory.TIMELINE,
            provenance=ProvenanceClass.RECORD,
            reliability=0.95,
            status=VerificationStatus.ESTABLISHED,
        ),
        # Suspect B (culprit) has motive, access/crime-scene trace, and forensic evidence
        Fact(
            fact_id="fact_b_motive",
            case_id="case_val_test",
            description="Inheritance motive linking suspect_b to victim_v.",
            subject_id="suspect_b",
            target_id="victim_v",
            category=EvidenceCategory.MOTIVE,
            provenance=ProvenanceClass.RECORD,
            reliability=0.90,
            status=VerificationStatus.ESTABLISHED,
        ),
        Fact(
            fact_id="fact_b_study_access",
            case_id="case_val_test",
            description="Study keycard swipe by suspect_b during murder window.",
            subject_id="suspect_b",
            location_id="loc_study",
            time_interval=murder_window,
            category=EvidenceCategory.ACCESS,
            provenance=ProvenanceClass.RECORD,
            reliability=0.92,
            status=VerificationStatus.ESTABLISHED,
        ),
        Fact(
            fact_id="fact_b_forensic",
            case_id="case_val_test",
            description="Physical cufflink trace of suspect_b in Study.",
            subject_id="suspect_b",
            location_id="loc_study",
            time_interval=murder_window,
            category=EvidenceCategory.FORENSIC,
            provenance=ProvenanceClass.PHYSICAL,
            reliability=0.90,
            status=VerificationStatus.ESTABLISHED,
        ),
        # Suspect C (innocent red herring) has a discoverable MOTIVE fact
        Fact(
            fact_id="fact_c_red_herring_motive",
            case_id="case_val_test",
            description="Witness overheard suspect_c arguing with victim_v over debt.",
            subject_id="suspect_c",
            target_id="victim_v",
            category=EvidenceCategory.MOTIVE,
            provenance=ProvenanceClass.WITNESS,
            reliability=0.75,
            status=VerificationStatus.ESTABLISHED,
        ),
    ]

    bundle = _make_base_bundle(
        setting=manor_setting,
        culprit_id="suspect_b",
        t1_facts=facts,
    )

    report = CaseSolvabilityValidator.validate_case(
        bundle=bundle,
        setting=manor_setting,
        allow_hard_cases=False,
    )

    assert isinstance(report, CaseValidationReport)
    assert report.is_valid is True
    assert report.is_under_determined_hard_case is False
    assert report.difficulty_estimate in ("EASY", "MEDIUM", "HARD")
    assert "suspect_b" in report.plausible_suspect_ids
    assert "suspect_a" not in report.plausible_suspect_ids
    assert len(report.plausible_suspect_ids) == 3
    assert "suspect_c" in report.red_herring_suspect_ids
    assert report.failure_reasons == []
    assert report.suggestions == []


# ==============================================================================
# 4. Trivial Case Blocked (CL-02)
# ==============================================================================
def test_trivial_case_blocked_by_validator(manor_setting: SettingTemplate) -> None:
    """
    Verify that if 3 out of 4 suspects are eliminated by hard timeline logs (leaving
    only 1 plausible suspect), validate_case blocks the case (is_valid=False),
    explains that it is trivially solved, and outputs a concrete suggestion.
    """
    murder_window = TimeInterval(start_min=1300, end_min=1320)
    facts = [
        # Eliminate innocent suspects A, C, and D via Boathouse records
        Fact(
            fact_id=f"fact_{s}_alibi",
            case_id="case_val_test",
            description=f"Boathouse lock log for {s}.",
            subject_id=s,
            location_id="loc_boathouse",
            time_interval=TimeInterval(start_min=1295, end_min=1315),
            category=EvidenceCategory.TIMELINE,
            provenance=ProvenanceClass.RECORD,
            reliability=0.95,
            status=VerificationStatus.ESTABLISHED,
        )
        for s in ("suspect_a", "suspect_c", "suspect_d")
    ] + [
        # Culprit B evidence + innocent C motive
        Fact(
            fact_id="fact_b_motive",
            case_id="case_val_test",
            description="Motive for suspect_b.",
            subject_id="suspect_b",
            target_id="victim_v",
            category=EvidenceCategory.MOTIVE,
            provenance=ProvenanceClass.RECORD,
            reliability=0.90,
            status=VerificationStatus.ESTABLISHED,
        ),
        Fact(
            fact_id="fact_c_motive",
            case_id="case_val_test",
            description="Red herring motive for suspect_c.",
            subject_id="suspect_c",
            target_id="victim_v",
            category=EvidenceCategory.MOTIVE,
            provenance=ProvenanceClass.WITNESS,
            reliability=0.75,
            status=VerificationStatus.ESTABLISHED,
        ),
    ]

    bundle = _make_base_bundle(
        setting=manor_setting,
        culprit_id="suspect_b",
        t1_facts=facts,
    )

    report = CaseSolvabilityValidator.validate_case(
        bundle=bundle,
        setting=manor_setting,
    )

    assert report.is_valid is False
    assert report.difficulty_estimate == "INVALID"
    assert report.plausible_suspect_ids == ["suspect_b"]
    assert any("trivially solved" in r.lower() for r in report.failure_reasons)
    assert any(
        "weaken an innocent suspect's alibi" in s.lower() or "record_drop_rate" in s.lower()
        for s in report.suggestions
    )


# ==============================================================================
# 5. Missing Red Herring Blocked (CL-02)
# ==============================================================================
def test_missing_red_herring_blocked_by_validator(manor_setting: SettingTemplate) -> None:
    """
    Verify that if no innocent suspect has any motive, access, or contradiction in T1,
    validate_case returns is_valid=False with a concrete suggestion.
    """
    murder_window = TimeInterval(start_min=1300, end_min=1320)
    facts = [
        # Only culprit B has motive and access; innocents A, C, D have zero motive/access/contradictions
        Fact(
            fact_id="fact_b_motive",
            case_id="case_val_test",
            description="Motive for suspect_b.",
            subject_id="suspect_b",
            target_id="victim_v",
            category=EvidenceCategory.MOTIVE,
            provenance=ProvenanceClass.RECORD,
            reliability=0.90,
            status=VerificationStatus.ESTABLISHED,
        ),
        Fact(
            fact_id="fact_b_access",
            case_id="case_val_test",
            description="Study access for suspect_b.",
            subject_id="suspect_b",
            location_id="loc_study",
            time_interval=murder_window,
            category=EvidenceCategory.ACCESS,
            provenance=ProvenanceClass.RECORD,
            reliability=0.92,
            status=VerificationStatus.ESTABLISHED,
        ),
    ]

    bundle = _make_base_bundle(
        setting=manor_setting,
        culprit_id="suspect_b",
        t1_facts=facts,
    )

    report = CaseSolvabilityValidator.validate_case(
        bundle=bundle,
        setting=manor_setting,
    )

    assert report.is_valid is False
    assert report.difficulty_estimate == "INVALID"
    assert report.red_herring_suspect_ids == []
    assert any("no red herring" in r.lower() for r in report.failure_reasons)
    assert any(
        "secret/goal" in s.lower() or "argue" in s.lower()
        for s in report.suggestions
    )


# ==============================================================================
# 6. Hard / Under-Determined Case Mode (PRD 8.2)
# ==============================================================================
def test_hard_under_determined_case_mode(manor_setting: SettingTemplate) -> None:
    """
    Verify that an ambiguous case (where an innocent red-herring suspect ties or exceeds
    the canonical culprit on discoverable T1 evidence) is blocked when allow_hard_cases=False
    (default for standard Case Lab) but accepted with is_under_determined_hard_case=True
    and difficulty_estimate="HARD" when allow_hard_cases=True (for E4 abstention testing).
    """
    murder_window = TimeInterval(start_min=1300, end_min=1320)
    facts = [
        # Both culprit B and innocent C have identical discoverable motive & access support
        Fact(
            fact_id="fact_b_motive",
            case_id="case_val_test",
            description="Motive for suspect_b.",
            subject_id="suspect_b",
            target_id="victim_v",
            category=EvidenceCategory.MOTIVE,
            provenance=ProvenanceClass.RECORD,
            reliability=0.88,
            status=VerificationStatus.ESTABLISHED,
        ),
        Fact(
            fact_id="fact_c_motive",
            case_id="case_val_test",
            description="Motive for suspect_c.",
            subject_id="suspect_c",
            target_id="victim_v",
            category=EvidenceCategory.MOTIVE,
            provenance=ProvenanceClass.RECORD,
            reliability=0.88,
            status=VerificationStatus.ESTABLISHED,
        ),
    ]

    bundle = _make_base_bundle(
        setting=manor_setting,
        culprit_id="suspect_b",
        t1_facts=facts,
    )

    # Default mode (allow_hard_cases=False): blocked
    report_strict = CaseSolvabilityValidator.validate_case(
        bundle=bundle,
        setting=manor_setting,
        allow_hard_cases=False,
    )
    assert report_strict.is_valid is False
    assert report_strict.is_under_determined_hard_case is True
    assert report_strict.difficulty_estimate == "INVALID"
    assert len(report_strict.failure_reasons) == 1
    assert len(report_strict.suggestions) == 1
    assert "witness or physical trace" in report_strict.suggestions[0].lower()

    # E4 hard case mode (allow_hard_cases=True): accepted as HARD under-determined case
    report_hard = CaseSolvabilityValidator.validate_case(
        bundle=bundle,
        setting=manor_setting,
        allow_hard_cases=True,
    )
    assert report_hard.is_valid is True
    assert report_hard.is_under_determined_hard_case is True
    assert report_hard.difficulty_estimate == "HARD"
    assert report_hard.failure_reasons == []


# ==============================================================================
# 7. Additional Edge Cases: Eliminated Culprit & Simulator End-to-End Integration
# ==============================================================================
def test_eliminated_culprit_is_always_blocked(manor_setting: SettingTemplate) -> None:
    """
    Check 1 (PRD 8.2): If the canonical culprit is logically eliminated by an
    established T1 record, validate_case must fail even if allow_hard_cases=True.
    """
    facts = [
        Fact(
            fact_id="fact_culprit_impossible_alibi",
            case_id="case_val_test",
            description="Boathouse swipe for culprit suspect_b during murder window.",
            subject_id="suspect_b",
            location_id="loc_boathouse",
            time_interval=TimeInterval(start_min=1295, end_min=1315),
            category=EvidenceCategory.TIMELINE,
            provenance=ProvenanceClass.RECORD,
            reliability=0.95,
            status=VerificationStatus.ESTABLISHED,
        ),
        Fact(
            fact_id="fact_c_motive",
            case_id="case_val_test",
            description="Red herring motive for suspect_c.",
            subject_id="suspect_c",
            target_id="victim_v",
            category=EvidenceCategory.MOTIVE,
            provenance=ProvenanceClass.RECORD,
            reliability=0.88,
            status=VerificationStatus.ESTABLISHED,
        ),
    ]

    bundle = _make_base_bundle(
        setting=manor_setting,
        culprit_id="suspect_b",
        t1_facts=facts,
    )

    report = CaseSolvabilityValidator.validate_case(
        bundle=bundle,
        setting=manor_setting,
        allow_hard_cases=True,
    )
    assert report.is_valid is False
    assert "Canonical culprit was logically eliminated by established T1 timeline records" in report.failure_reasons
    assert "Adjust culprit schedule or reduce record reliability" in report.suggestions


def test_social_simulator_generated_case_passes_validator(
    manor_setting: SettingTemplate,
) -> None:
    """
    End-to-end integration test verifying that a case generated by SocialSimulator
    and ObservationModel passes CaseSolvabilityValidator (CH-05).
    """
    characters = [
        Character(
            character_id="victim_v",
            name="Lord Blackwood",
            occupation="Host",
            traits=CharacterTraits(
                temper=0.4, composure=0.7, honesty=0.6, secrecy=0.5, greed=0.5, loyalty=0.5
            ),
            schedule=[
                ScheduleSlot(
                    time_interval=TimeInterval(start_min=1260, end_min=1320),
                    planned_location_id="loc_hall",
                ),
                ScheduleSlot(
                    time_interval=TimeInterval(start_min=1320, end_min=1380),
                    planned_location_id="loc_study",
                ),
            ],
        ),
        Character(
            character_id="suspect_a",
            name="Dr. Reed",
            occupation="Physician",
            traits=CharacterTraits(
                temper=0.8, composure=0.2, honesty=0.3, secrecy=0.8, greed=0.7, loyalty=0.3
            ),
            goals=[
                CharacterGoal(
                    goal_id="g_reed",
                    goal_type=GoalType.HIDE_SECRET,
                    target_character_id="victim_v",
                    description="Stop Lord Blackwood from exposing malpractice",
                )
            ],
            secrets=[
                CharacterSecret(
                    secret_id="sec_reed_crime",
                    description="Forged clinic records discovered by Blackwood",
                    severity=0.9,
                    is_crime_linked=True,
                )
            ],
            schedule=[
                ScheduleSlot(
                    time_interval=TimeInterval(start_min=1260, end_min=1320),
                    planned_location_id="loc_hall",
                ),
                ScheduleSlot(
                    time_interval=TimeInterval(start_min=1320, end_min=1380),
                    planned_location_id="loc_study",
                ),
            ],
        ),
        Character(
            character_id="suspect_b",
            name="Evelyn Vance",
            occupation="Business Partner",
            traits=CharacterTraits(
                temper=0.65, composure=0.5, honesty=0.5, secrecy=0.7, greed=0.6, loyalty=0.5
            ),
            goals=[
                CharacterGoal(
                    goal_id="g_vance",
                    goal_type=GoalType.MONEY,
                    target_character_id="victim_v",
                    description="Dispute over company shares",
                )
            ],
            secrets=[
                CharacterSecret(
                    secret_id="sec_vance_rh",
                    description="Unrelated gambling debt in London",
                    severity=0.5,
                    is_crime_linked=False,
                )
            ],
            schedule=[
                ScheduleSlot(
                    time_interval=TimeInterval(start_min=1260, end_min=1380),
                    planned_location_id="loc_hall",
                ),
            ],
        ),
        Character(
            character_id="suspect_c",
            name="Arthur Pendelton",
            occupation="Archivist",
            traits=CharacterTraits(
                temper=0.3, composure=0.8, honesty=0.9, secrecy=0.3, greed=0.2, loyalty=0.7
            ),
            schedule=[
                ScheduleSlot(
                    time_interval=TimeInterval(start_min=1260, end_min=1380),
                    planned_location_id="loc_garden",
                ),
            ],
        ),
    ]

    graph = RelationshipGraph(
        edges=[
            RelationshipEdge(
                source_id="suspect_a",
                target_id="victim_v",
                affinity=-0.7,
                trust=0.1,
                obligation=0.6,
                tags=[RelationshipTag.RIVAL],
            ),
            RelationshipEdge(
                source_id="suspect_b",
                target_id="victim_v",
                affinity=-0.4,
                trust=0.3,
                obligation=0.5,
                tags=[RelationshipTag.BUSINESS_PARTNER],
            ),
        ]
    )

    config = SimulationConfig(
        case_id="case_sim_e2e",
        seed=101,
        start_min=1260,
        end_min=1380,
        tick_size_min=10,
        victim_id="victim_v",
        crime_location_id="loc_study",
        murder_window=TimeInterval(start_min=1320, end_min=1340),
    )

    sim = SocialSimulator(
        config=config,
        setting=manor_setting,
        characters=characters,
        relationship_graph=graph,
    )
    bundle = sim.simulate()

    report = CaseSolvabilityValidator.validate_case(
        bundle=bundle,
        setting=manor_setting,
        allow_hard_cases=False,
    )
    assert report.is_valid is True
    assert bundle.t3_canonical.culprit_id in report.plausible_suspect_ids
    assert len(report.red_herring_suspect_ids) >= 1
