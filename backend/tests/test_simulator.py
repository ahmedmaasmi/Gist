# backend/tests/test_simulator.py
import json
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
    GoalType,
    InteractionType,
    ProvenanceClass,
    RelationshipTag,
    VerificationStatus,
)
from app.domain.setting import Location, SettingTemplate
from app.domain.simulation import (
    CanonicalEvent,
    SimulatedCaseBundle,
    SimulationConfig,
)
from app.domain.world import TimeInterval
from app.engine.consistency import StructuredConsistencyEngine
from app.engine.simulator import SocialSimulator


@pytest.fixture
def manor_setting() -> SettingTemplate:
    """Blackwood Manor spatial setting with restricted study."""
    return SettingTemplate(
        template_id="tpl_manor",
        name="Blackwood Manor",
        locations=[
            Location(location_id="loc_study", name="Lord Blackwood's Study", is_restricted=True),
            Location(location_id="loc_drawing_room", name="Drawing Room", is_restricted=False),
            Location(location_id="loc_conservatory", name="Conservatory", is_restricted=False),
            Location(location_id="loc_cellar", name="Wine Cellar", is_restricted=True),
        ],
        travel_matrix={
            "loc_study": {"loc_drawing_room": 5, "loc_conservatory": 10, "loc_cellar": 15},
            "loc_drawing_room": {"loc_study": 5, "loc_conservatory": 5, "loc_cellar": 10},
            "loc_conservatory": {"loc_study": 10, "loc_drawing_room": 5, "loc_cellar": 15},
            "loc_cellar": {"loc_study": 15, "loc_drawing_room": 10, "loc_conservatory": 15},
        },
    )


@pytest.fixture
def manor_cast() -> tuple[list[Character], RelationshipGraph]:
    """
    Cast of 4 characters (1 victim + 3 suspects) configured so that:
    - suspect_reed has strong motive + opportunity + high temper / low composure -> natural culprit
    - suspect_reed and victim co-locate in loc_drawing_room with suspect_clara as witness -> ARGUE
    - suspect_clara confides her secret to suspect_vance in loc_conservatory -> CONFIDE
    - suspect_vance pledges COVER_FOR for suspect_clara -> COVER_FOR (INTENTIONAL_LIE)
    """
    victim = Character(
        character_id="victim_blackwood",
        name="Lord Blackwood",
        occupation="Aristocrat",
        traits=CharacterTraits(
            temper=0.6,
            greed=0.7,
            loyalty=0.4,
            honesty=0.5,
            composure=0.6,
            secrecy=0.7,
        ),
        schedule=[
            ScheduleSlot(
                time_interval=TimeInterval(start_min=1080, end_min=1260),
                planned_location_id="loc_drawing_room",
            ),
            ScheduleSlot(
                time_interval=TimeInterval(start_min=1260, end_min=1440),
                planned_location_id="loc_study",
            ),
        ],
    )

    suspect_reed = Character(
        character_id="suspect_reed",
        name="Dr. Daniel Reed",
        occupation="Family Physician",
        traits=CharacterTraits(
            temper=0.82,
            greed=0.65,
            loyalty=0.35,
            honesty=0.25,
            composure=0.22,
            secrecy=0.60,
        ),
        goals=[
            CharacterGoal(
                goal_type=GoalType.HIDE_SECRET,
                target_character_id="victim_blackwood",
                description="Stop Blackwood from exposing forged medical records",
            ),
            CharacterGoal(
                goal_type=GoalType.REVENGE,
                target_character_id="victim_blackwood",
                description="Retaliate against Blackwood's blackmail",
            ),
        ],
        secrets=[
            CharacterSecret(
                secret_id="sec_reed_embezzlement",
                description="Embezzled clinic funds discovered by Lord Blackwood",
                severity=0.9,
                is_crime_linked=True,
            )
        ],
        schedule=[
            ScheduleSlot(
                time_interval=TimeInterval(start_min=1080, end_min=1200),
                planned_location_id="loc_drawing_room",
            ),
            ScheduleSlot(
                time_interval=TimeInterval(start_min=1200, end_min=1440),
                planned_location_id="loc_drawing_room",
            ),
        ],
    )

    suspect_clara = Character(
        character_id="suspect_clara",
        name="Clara Thorne",
        occupation="Archivist",
        traits=CharacterTraits(
            temper=0.30,
            greed=0.30,
            loyalty=0.75,
            honesty=0.70,
            composure=0.75,
            secrecy=0.20,
        ),
        secrets=[
            CharacterSecret(
                secret_id="sec_clara_affair",
                description="Secretly selling rare manuscripts to pay off brother's debt",
                severity=0.5,
                is_crime_linked=False,
            )
        ],
        schedule=[
            ScheduleSlot(
                time_interval=TimeInterval(start_min=1080, end_min=1140),
                planned_location_id="loc_drawing_room",
            ),
            ScheduleSlot(
                time_interval=TimeInterval(start_min=1140, end_min=1440),
                planned_location_id="loc_conservatory",
            ),
        ],
    )

    suspect_vance = Character(
        character_id="suspect_vance",
        name="Major Vance",
        occupation="Estate Steward",
        traits=CharacterTraits(
            temper=0.40,
            greed=0.25,
            loyalty=0.85,
            honesty=0.65,
            composure=0.80,
            secrecy=0.40,
        ),
        schedule=[
            ScheduleSlot(
                time_interval=TimeInterval(start_min=1080, end_min=1140),
                planned_location_id="loc_conservatory",
            ),
            ScheduleSlot(
                time_interval=TimeInterval(start_min=1140, end_min=1440),
                planned_location_id="loc_conservatory",
            ),
        ],
    )

    graph = RelationshipGraph(
        edges=[
            RelationshipEdge(
                source_id="suspect_reed",
                target_id="victim_blackwood",
                affinity=-0.75,
                trust=0.15,
                obligation=0.80,
                tags=[RelationshipTag.EMPLOYER_EMPLOYEE, RelationshipTag.RIVAL],
            ),
            RelationshipEdge(
                source_id="suspect_clara",
                target_id="suspect_vance",
                affinity=0.70,
                trust=0.80,
                loyalty=0.80,
                obligation=0.70,
                tags=[RelationshipTag.FAMILY],
            ),
            RelationshipEdge(
                source_id="suspect_vance",
                target_id="suspect_clara",
                affinity=0.75,
                trust=0.85,
                loyalty=0.85,
                obligation=0.65,
                tags=[RelationshipTag.FAMILY],
            ),
        ]
    )

    return [victim, suspect_reed, suspect_clara, suspect_vance], graph


def _make_config(seed: int = 42, forced_culprit_id: str | None = None) -> SimulationConfig:
    return SimulationConfig(
        case_id="case_blackwood_01",
        seed=seed,
        start_min=1080,
        end_min=1440,
        tick_size_min=10,
        victim_id="victim_blackwood",
        crime_location_id="loc_study",
        murder_window=TimeInterval(start_min=1290, end_min=1350),
        forced_culprit_id=forced_culprit_id,
        witness_noise_rate=0.15,
        record_drop_rate=0.20,
        guilty_lie_rate=0.95,
        innocent_lie_rate=0.25,
    )


def test_ch03_determinism_same_seed_vs_different_seed(
    manor_setting: SettingTemplate,
    manor_cast: tuple[list[Character], RelationshipGraph],
):
    """
    1. CH-03 Determinism Test:
    Running SocialSimulator twice with the exact same SimulationConfig(seed=42) and
    character setup produces the exact same log_hash, culprit, T1 facts, and T2 knowledge packs;
    running with seed=99 produces a different log_hash.
    """
    characters, graph = manor_cast
    config_42_a = _make_config(seed=42)
    config_42_b = _make_config(seed=42)
    config_99 = _make_config(seed=99)

    sim = SocialSimulator()
    bundle_42_a: SimulatedCaseBundle = sim.simulate(
        setting=manor_setting,
        characters=characters,
        relationship_graph=graph,
        config=config_42_a,
    )
    bundle_42_b: SimulatedCaseBundle = sim.simulate(
        setting=manor_setting,
        characters=characters,
        relationship_graph=graph,
        config=config_42_b,
    )
    bundle_99: SimulatedCaseBundle = sim.simulate(
        setting=manor_setting,
        characters=characters,
        relationship_graph=graph,
        config=config_99,
    )

    # Exact match for seed=42 across both runs
    assert bundle_42_a.log_hash == bundle_42_b.log_hash
    assert bundle_42_a.t3_canonical.culprit_id == bundle_42_b.t3_canonical.culprit_id
    assert bundle_42_a.t3_canonical.culprit_id == "suspect_reed"
    assert bundle_42_a.t1_session.model_dump(mode="json") == bundle_42_b.t1_session.model_dump(
        mode="json"
    )
    assert {
        k: v.model_dump(mode="json") for k, v in bundle_42_a.t2_knowledge.items()
    } == {
        k: v.model_dump(mode="json") for k, v in bundle_42_b.t2_knowledge.items()
    }

    # Different seed produces different log_hash
    assert bundle_42_a.log_hash != bundle_99.log_hash


def test_ch02_reason_strings_and_provenance(
    manor_setting: SettingTemplate,
    manor_cast: tuple[list[Character], RelationshipGraph],
):
    """
    2. CH-02 Reason Strings & Provenance:
    Every CanonicalEvent has a non-empty reason_string containing triggering trait/edge values,
    and every derived Fact and Claim has valid ProvenanceClass and VerificationStatus.
    """
    characters, graph = manor_cast
    bundle = SocialSimulator().simulate(
        setting=manor_setting,
        characters=characters,
        relationship_graph=graph,
        config=_make_config(seed=42),
    )

    assert len(bundle.canonical_events) > 0
    for event in bundle.canonical_events:
        assert isinstance(event, CanonicalEvent)
        assert len(event.reason_string.strip()) > 0
        assert event.event_kind in ("MOVEMENT", "INTERACTION", "MURDER")

        if event.event_kind == "MOVEMENT":
            assert "composure=" in event.reason_string
        elif event.event_kind == "INTERACTION":
            if event.interaction_type == InteractionType.ARGUE:
                assert "temper=" in event.reason_string
                assert "prior_affinity=" in event.reason_string
            elif event.interaction_type == InteractionType.CONFIDE:
                assert "secrecy=" in event.reason_string
                assert "prior_trust=" in event.reason_string
            elif event.interaction_type == InteractionType.COVER_FOR:
                assert "loyalty_or_trust=" in event.reason_string
                assert "INTENTIONAL_LIE" in event.reason_string
        elif event.event_kind == "MURDER":
            assert "motive_score=" in event.reason_string
            assert "opportunity_score=" in event.reason_string
            assert "low_composure_score=" in event.reason_string

    # Verify all T1 facts and claims have valid ProvenanceClass and VerificationStatus
    assert len(bundle.t1_session.discovered_facts) > 0
    for fact in bundle.t1_session.discovered_facts:
        assert isinstance(fact.provenance, ProvenanceClass)
        assert fact.provenance != ProvenanceClass.MODEL_INFERRED
        assert isinstance(fact.status, VerificationStatus)

    assert len(bundle.t1_session.recorded_claims) > 0
    for claim in bundle.t1_session.recorded_claims:
        assert claim.provenance == ProvenanceClass.SELF_REPORT
        assert claim.status == VerificationStatus.UNVERIFIED

    # Verify all T2 private facts and cover story claims have valid provenance and status
    for char_id, t2_pack in bundle.t2_knowledge.items():
        for pfact in t2_pack.private_facts:
            assert isinstance(pfact.provenance, ProvenanceClass)
            assert isinstance(pfact.status, VerificationStatus)
        for cclaim in t2_pack.cover_story:
            assert cclaim.provenance == ProvenanceClass.SELF_REPORT
            assert cclaim.status == VerificationStatus.UNVERIFIED


def test_interaction_effects_argue_confide_cover_for(
    manor_setting: SettingTemplate,
    manor_cast: tuple[list[Character], RelationshipGraph],
):
    """
    3. Interaction Effects:
    Verify ARGUE lowers affinity and records witnesses, CONFIDE transfers secret knowledge to T2,
    and COVER_FOR records an INTENTIONAL_LIE metadata tag in T3.
    """
    characters, graph = manor_cast
    initial_reed_victim_affinity = graph.get_edge(
        "suspect_reed", "victim_blackwood"
    ).affinity
    initial_clara_vance_trust = graph.get_edge(
        "suspect_clara", "suspect_vance"
    ).trust

    bundle = SocialSimulator().simulate(
        setting=manor_setting,
        characters=characters,
        relationship_graph=graph,
        config=_make_config(seed=42),
    )

    # A. ARGUE: lowers affinity by 0.2 and records suspect_clara as witness
    argue_events = [
        e
        for e in bundle.canonical_events
        if e.event_kind == "INTERACTION"
        and e.interaction_type == InteractionType.ARGUE
        and e.actor_id == "suspect_reed"
        and e.target_id == "victim_blackwood"
    ]
    assert len(argue_events) >= 1
    argue_ev = argue_events[0]
    assert "suspect_clara" in argue_ev.witness_ids

    updated_edge = bundle.t3_canonical.relationship_graph.get_edge(
        "suspect_reed", "victim_blackwood"
    )
    assert updated_edge is not None
    assert updated_edge.affinity == pytest.approx(
        max(-1.0, initial_reed_victim_affinity - 0.2)
    )

    # Witness fact emitted in T1 with reliability in [0.55, 0.90]
    witness_facts = [
        f
        for f in bundle.t1_session.discovered_facts
        if f.provenance == ProvenanceClass.WITNESS
        and f.subject_id == "suspect_reed"
        and f.target_id == "victim_blackwood"
    ]
    assert len(witness_facts) >= 1
    assert 0.55 <= witness_facts[0].reliability <= 0.90

    # B. CONFIDE: transfers secret knowledge ('sec_clara_affair') to suspect_vance's T2 pack
    confide_events = [
        e
        for e in bundle.canonical_events
        if e.event_kind == "INTERACTION"
        and e.interaction_type == InteractionType.CONFIDE
        and e.actor_id == "suspect_clara"
        and e.target_id == "suspect_vance"
    ]
    assert len(confide_events) >= 1
    assert confide_events[0].metadata.get("secret_id") == "sec_clara_affair"

    updated_clara_vance = bundle.t3_canonical.relationship_graph.get_edge(
        "suspect_clara", "suspect_vance"
    )
    assert updated_clara_vance is not None
    assert updated_clara_vance.trust == pytest.approx(
        min(1.0, initial_clara_vance_trust + 0.15)
    )

    vance_t2 = bundle.t2_knowledge["suspect_vance"]
    assert "sec_clara_affair" in vance_t2.known_secret_ids
    assert any(s.secret_id == "sec_clara_affair" for s in vance_t2.unrelated_secrets)
    assert any("sec_clara_affair" in f.description for f in vance_t2.private_facts)

    # C. COVER_FOR: records an INTENTIONAL_LIE metadata tag in T3
    cover_events = [
        e
        for e in bundle.canonical_events
        if e.event_kind == "INTERACTION"
        and e.interaction_type == InteractionType.COVER_FOR
    ]
    assert len(cover_events) >= 1
    assert any(
        "INTENTIONAL_LIE" in str(e.metadata.values()) or "INTENTIONAL_LIE" in e.reason_string
        for e in cover_events
    )


def test_zero_canary_leakage_in_derived_t0_t1_t2(
    manor_setting: SettingTemplate,
    manor_cast: tuple[list[Character], RelationshipGraph],
):
    """
    4. Zero Canary Leakage in Derived T1/T2:
    Serialize t0_public, t1_session, and t2_knowledge to JSON and assert
    t3_canonical.canary_token (and "CANARY_T3_") does not appear anywhere in T0, T1, or T2.
    """
    characters, graph = manor_cast
    bundle = SocialSimulator().simulate(
        setting=manor_setting,
        characters=characters,
        relationship_graph=graph,
        config=_make_config(seed=42),
    )

    canary = bundle.t3_canonical.canary_token
    assert canary.startswith("CANARY_T3_")

    t0_json = json.dumps(bundle.t0_public.model_dump(mode="json"))
    t1_json = json.dumps(bundle.t1_session.model_dump(mode="json"))
    t2_json = json.dumps(
        {k: v.model_dump(mode="json") for k, v in bundle.t2_knowledge.items()}
    )

    for payload_name, payload in (("T0", t0_json), ("T1", t1_json), ("T2", t2_json)):
        assert canary not in payload, f"Canary token leaked into {payload_name}!"
        assert "CANARY_T3_" not in payload, f"CANARY_T3_ prefix leaked into {payload_name}!"


def test_culprit_false_alibi_detected_by_consistency_engine(
    manor_setting: SettingTemplate,
    manor_cast: tuple[list[Character], RelationshipGraph],
):
    """
    Verifies that when guilty_lie_rate=1.0, the culprit claims their planned schedule
    location during murder_window while T1 crime-scene traces place them at crime_location_id,
    allowing StructuredConsistencyEngine to flag a CLAIM_FACT contradiction.
    """
    characters, graph = manor_cast
    cfg = _make_config(seed=42)
    cfg.guilty_lie_rate = 1.0

    bundle = SocialSimulator().simulate(
        setting=manor_setting,
        characters=characters,
        relationship_graph=graph,
        config=cfg,
    )

    flags = StructuredConsistencyEngine.evaluate_session(
        session=bundle.t1_session,
        setting=manor_setting,
    )
    culprit_flags = [
        f for f in flags if f.suspect_id == bundle.t3_canonical.culprit_id
    ]
    assert len(culprit_flags) >= 1


def test_forced_culprit_override_and_red_herring_injection(
    manor_setting: SettingTemplate,
    manor_cast: tuple[list[Character], RelationshipGraph],
):
    """
    Verifies forced_culprit_id override (PRD 7A.4) and red-herring secret guarantee
    for innocent suspects (PRD 8.2).
    """
    from app.domain.world import SimulatedCaseBundle as WorldBundleAlias

    characters, graph = manor_cast
    # Strip existing unrelated secrets to verify simulator injects a red herring for an innocent
    for c in characters:
        c.secrets = [s for s in c.secrets if s.is_crime_linked]

    cfg = _make_config(seed=7, forced_culprit_id="suspect_vance")
    bundle = SocialSimulator().simulate(
        setting=manor_setting,
        characters=characters,
        relationship_graph=graph,
        config=cfg,
    )

    assert isinstance(bundle, WorldBundleAlias)
    assert bundle.t3_canonical.culprit_id == "suspect_vance"

    innocent_ids = [
        cid
        for cid in bundle.t0_public.suspect_ids
        if cid != bundle.t3_canonical.culprit_id
    ]
    assert any(
        len(bundle.t2_knowledge[cid].unrelated_secrets) > 0 for cid in innocent_ids
    )

