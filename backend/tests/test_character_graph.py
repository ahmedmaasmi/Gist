# backend/tests/test_character_graph.py
import pytest
from pydantic import ValidationError

from app.domain.character import (
    Character,
    CharacterGoal,
    CharacterSecret,
    CharacterTraits,
    RelationshipEdge,
    RelationshipGraph,
    ScheduleSlot,
)
from app.domain.enums import GoalType, RelationshipTag
from app.domain.world import TimeInterval


def _make_default_traits(**overrides: float) -> CharacterTraits:
    base = {
        "temper": 0.5,
        "greed": 0.4,
        "loyalty": 0.6,
        "honesty": 0.7,
        "composure": 0.5,
        "secrecy": 0.3,
    }
    base.update(overrides)
    return CharacterTraits(**base)


def test_asymmetric_directed_relationships():
    """PRD 7A.2: A -> B and B -> A can hold completely asymmetric trust and affinity."""
    edge_a_to_b = RelationshipEdge(
        source_id="char_a",
        target_id="char_b",
        affinity=0.8,
        trust=0.9,
        obligation=0.1,
        tags=[RelationshipTag.BUSINESS_PARTNER],
    )
    edge_b_to_a = RelationshipEdge(
        source_id="char_b",
        target_id="char_a",
        affinity=-0.7,
        trust=0.1,
        obligation=0.8,
        tags=[RelationshipTag.BUSINESS_PARTNER, RelationshipTag.RIVAL],
    )

    graph = RelationshipGraph(edges=[edge_a_to_b, edge_b_to_a])

    ab = graph.get_edge("char_a", "char_b")
    ba = graph.get_edge("char_b", "char_a")
    assert ab is not None and ba is not None
    assert ab.trust == 0.9 and ab.affinity == 0.8
    assert ba.trust == 0.1 and ba.affinity == -0.7
    assert graph.get_edge("char_a", "char_unknown") is None


def test_relationship_edge_apply_delta_clamping():
    """PRD 7A.2: Simulation ticks must clamp affinity to [-1, 1] and trust/obligation to [0, 1]."""
    edge = RelationshipEdge(
        source_id="char_a",
        target_id="char_b",
        affinity=0.5,
        trust=0.5,
        obligation=0.5,
    )

    # Push above upper bounds
    edge.apply_delta(d_affinity=0.9, d_trust=0.8, d_obligation=0.95)
    assert edge.affinity == 1.0
    assert edge.trust == 1.0
    assert edge.obligation == 1.0

    # Push below lower bounds
    edge.apply_delta(d_affinity=-2.5, d_trust=-1.5, d_obligation=-3.0)
    assert edge.affinity == -1.0
    assert edge.trust == 0.0
    assert edge.obligation == 0.0


def test_ch04_ood_trait_warning_detection():
    """PRD 7A.6 (CH-04): Traits outside [0.1, 0.9] emit OOD warnings; in-distribution traits do not."""
    in_dist_traits = _make_default_traits(temper=0.50)
    assert in_dist_traits.check_ood() == []

    ood_traits = _make_default_traits(temper=0.98, honesty=0.05)
    warnings = ood_traits.check_ood()
    assert len(warnings) == 2
    assert any("temper" in w and "0.98" in w for w in warnings)
    assert any("honesty" in w and "0.05" in w for w in warnings)


def test_ch06_player_visible_edges_filtering():
    """PRD 7A.6 (CH-06): Unrevealed T3 edges stay hidden; only revealed edges appear in T1."""
    hidden_affair = RelationshipEdge(
        source_id="suspect_1",
        target_id="victim",
        affinity=0.7,
        trust=0.8,
        tags=[RelationshipTag.SECRET_AFFAIR],
        is_revealed_to_player=False,
    )
    known_employer = RelationshipEdge(
        source_id="suspect_2",
        target_id="victim",
        affinity=-0.2,
        trust=0.4,
        tags=[RelationshipTag.EMPLOYER_EMPLOYEE],
        is_revealed_to_player=True,
    )

    graph = RelationshipGraph(edges=[hidden_affair, known_employer])
    visible = graph.get_player_visible_edges()

    assert len(visible) == 1
    assert visible[0].source_id == "suspect_2"
    assert visible[0].tags == [RelationshipTag.EMPLOYER_EMPLOYEE]


def test_overlapping_schedule_slots_rejected():
    """PRD 7A.1: A single character cannot be scheduled in two overlapping time intervals."""
    with pytest.raises(ValidationError, match="Overlapping schedule slots"):
        Character(
            character_id="char_reed",
            name="Dr. Reed",
            occupation="Physician",
            traits=_make_default_traits(),
            goals=[
                CharacterGoal(
                    goal_type=GoalType.HIDE_SECRET,
                    target_character_id="victim",
                    description="Conceal malpractice record",
                )
            ],
            secrets=[
                CharacterSecret(
                    secret_id="sec_01",
                    description="Forged prescription logs",
                    severity=0.8,
                    is_crime_linked=True,
                )
            ],
            schedule=[
                ScheduleSlot(
                    time_interval=TimeInterval(start_min=1260, end_min=1320),
                    planned_location_id="loc_study",
                ),
                ScheduleSlot(
                    time_interval=TimeInterval(start_min=1300, end_min=1350),
                    planned_location_id="loc_dining_hall",
                ),
            ],
        )


def test_self_loop_relationship_edge_rejected():
    """PRD 7A.2: A character cannot have a relationship edge pointing to themselves."""
    with pytest.raises(ValidationError, match="Self-loop relationship edge"):
        RelationshipEdge(
            source_id="char_reed",
            target_id="char_reed",
            affinity=1.0,
            trust=1.0,
        )

