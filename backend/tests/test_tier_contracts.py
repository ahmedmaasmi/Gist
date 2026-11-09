# backend/tests/test_tier_contracts.py
"""
PRD Section 5.2 & 12: structural tier-isolation contracts.

Canaries can only live in text. ID and numeric T3 data (culprit_id, edge weights, lie flags)
are protected here instead: we walk each lower-tier model's type annotations recursively and
fail if a T3-only type or field name could ever be placed inside it.
"""
import types
import typing

import pytest
from pydantic import BaseModel

from app.domain.character import (
    Character,
    CharacterSecret,
    CharacterTraits,
    RelationshipEdge,
    RelationshipGraph,
)
from app.domain.enums import InformationTier
from app.domain.tiers import T0Public, T1Session, T2CharacterKnowledge, T3Canonical
from app.domain.world import CanonicalEvent, LieAnnotation

T3_ONLY_TYPES = {T3Canonical, CanonicalEvent, LieAnnotation, RelationshipGraph}
T3_ONLY_FIELD_NAMES = {
    "culprit_id",
    "canaries",
    "lie_annotations",
    "canonical_events",
    "relationship_graph",
    "ground_truth_facts",
    "solution_summary",
    "is_crime_linked",  # whether a secret relates to the murder is solution data
}
# T0/T1 additionally must not see characters' hidden simulation state or raw edge values.
HIDDEN_FROM_PLAYER_TYPES = {
    RelationshipEdge,
    Character,
    CharacterTraits,
    CharacterSecret,
    T2CharacterKnowledge,
}


def _reachable(model: type[BaseModel]) -> tuple[set[type], set[str]]:
    """All model types and field names reachable from `model` through its annotations."""
    seen_types: set[type] = set()
    field_names: set[str] = set()

    def visit(tp: typing.Any) -> None:
        origin = typing.get_origin(tp)
        if origin is not None or isinstance(tp, types.UnionType):
            for arg in typing.get_args(tp):
                visit(arg)
            return
        if isinstance(tp, type) and issubclass(tp, BaseModel) and tp not in seen_types:
            seen_types.add(tp)
            for name, field in tp.model_fields.items():
                field_names.add(name)
                visit(field.annotation)

    visit(model)
    return seen_types, field_names


def test_tier_tags():
    assert T0Public.tier == InformationTier.T0
    assert T1Session.tier == InformationTier.T1
    assert T2CharacterKnowledge.tier == InformationTier.T2
    assert T3Canonical.tier == InformationTier.T3


@pytest.mark.parametrize("model", [T0Public, T1Session])
def test_player_tiers_cannot_hold_hidden_data(model):
    reachable_types, names = _reachable(model)
    assert not reachable_types & (T3_ONLY_TYPES | HIDDEN_FROM_PLAYER_TYPES)
    assert not names & T3_ONLY_FIELD_NAMES


def test_t2_cannot_hold_t3_types():
    # T2 may include the character's own Character record (their own truth), but never
    # the case solution, the event log, the relationship graph or lie annotations.
    reachable_types, _ = _reachable(T2CharacterKnowledge)
    assert not reachable_types & T3_ONLY_TYPES


def test_contract_walker_catches_a_violation():
    """Guard against a walker that silently checks nothing."""

    class LeakyResponse(BaseModel):
        hint: list[T3Canonical] | None = None

    reachable_types, names = _reachable(LeakyResponse)
    assert T3Canonical in reachable_types
    assert "culprit_id" in names
