# backend/app/domain/tiers.py
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.canary import make_canary, stamp
from app.domain.character import Character, CharacterSecret, RelationshipGraph, RevealedRelationship
from app.domain.enums import InformationTier
from app.domain.world import CanonicalEvent, Claim, ContradictionFlag, Fact, LieAnnotation, TimeInterval


class T0Public(BaseModel):
    """
    PRD Section 5.2 (T0 Public): Baseline case header and initial crime briefing
    visible to all players and characters at the start of a case.
    """
    tier: ClassVar[InformationTier] = InformationTier.T0

    case_id: str = Field(..., min_length=1)
    title: str = Field(default="Untitled Case")
    victim_id: str = Field(default="victim")
    crime_location_id: str = Field(default="loc_study")
    crime_window: TimeInterval | None = None
    suspect_ids: list[str] = Field(default_factory=list)


class T1Session(BaseModel):
    """
    PRD Section 5.2 (T1 Session): Player-visible investigation workspace.
    Contains only discovered/established facts, recorded claims, and contradiction flags.
    Strictly isolated from T2 character secrets and T3 canonical ground truth.
    """
    tier: ClassVar[InformationTier] = InformationTier.T1
    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(default="session_default", min_length=1)
    case_id: str = Field(default="case_default", min_length=1)
    current_turn: int = Field(default=0, ge=0)
    discovered_facts: list[Fact] = Field(default_factory=list)
    recorded_claims: list[Claim] = Field(default_factory=list)
    contradiction_flags: list[ContradictionFlag] = Field(default_factory=list)
    revealed_edges: list[RevealedRelationship] = Field(
        default_factory=list,
        description="CH-06: relationships the player has discovered (tags + evidence only, no T3 edge values)",
    )

    @model_validator(mode="before")
    @classmethod
    def _support_facts_alias(cls, data: Any) -> Any:
        if isinstance(data, dict) and "facts" in data and "discovered_facts" not in data:
            data = dict(data)
            data["discovered_facts"] = data.pop("facts")
        return data

    @property
    def facts(self) -> list[Fact]:
        """Convenience alias for discovered_facts."""
        return self.discovered_facts


class T2CharacterKnowledge(BaseModel):
    """
    PRD Section 5.2 (T2 Character): Private knowledge, cover story, and personal
    observations held by an individual character during Mode 2 interrogation.
    """
    tier: ClassVar[InformationTier] = InformationTier.T2
    model_config = ConfigDict(populate_by_name=True)

    case_id: str = Field(default="case_default", min_length=1)
    character_id: str = Field(..., min_length=1)
    character: Character | None = None
    private_facts: list[Fact] = Field(default_factory=list)
    unrelated_secrets: list[CharacterSecret] = Field(default_factory=list)
    known_secret_ids: list[str] = Field(
        default_factory=list,
        description="Secret IDs known to this character (own secrets + secrets learned via CONFIDE)",
    )
    cover_story: list[Claim] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _support_legacy_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = dict(data)
            if "personal_facts" in data and "private_facts" not in data:
                data["private_facts"] = data.pop("personal_facts")
            if "cover_story_claims" in data and "cover_story" not in data:
                data["cover_story"] = data.pop("cover_story_claims")
        return data

    @property
    def personal_facts(self) -> list[Fact]:
        """Backwards-compatible alias for private_facts."""
        return self.private_facts

    @property
    def cover_story_claims(self) -> list[Claim]:
        """Backwards-compatible alias for cover_story."""
        return self.cover_story


# Backwards compatibility alias
T2Character = T2CharacterKnowledge


class T3Canonical(BaseModel):
    """
    PRD Section 5.2 (T3 Canonical Vault): Ground-truth culprit, full event timeline,
    unrevealed relationship graph and lie annotations. Inaccessible to gameplay roles.

    Every free-text field is stamped with its own canary token on validation (see canary.py).
    ID and numeric fields cannot carry a canary (e.g. culprit_id also appears in T0's suspect
    list); their isolation is enforced structurally by tests/test_tier_contracts.py.
    """
    tier: ClassVar[InformationTier] = InformationTier.T3

    case_id: str = Field(..., min_length=1)
    seed: int = Field(..., description="Simulation seed; with case_id it determines the canaries")
    culprit_id: str = Field(..., min_length=1)
    crime_location_id: str = Field(..., min_length=1)
    crime_window: TimeInterval
    solution_summary: str = Field(default="", description="Plain-language canonical solution")
    ground_truth_facts: list[Fact] = Field(default_factory=list)
    canonical_events: list[CanonicalEvent] = Field(default_factory=list)
    relationship_graph: RelationshipGraph = Field(default_factory=RelationshipGraph)
    lie_annotations: list[LieAnnotation] = Field(default_factory=list)
    canaries: dict[str, str] = Field(
        default_factory=dict,
        description="field path -> canary token; filled by the validator, never set by hand",
    )

    @model_validator(mode="after")
    def _stamp_canaries(self) -> "T3Canonical":
        canaries: dict[str, str] = {}

        def stamped(path: str, text: str) -> str:
            canaries[path] = make_canary(self.case_id, self.seed, path)
            return stamp(text, canaries[path])

        self.solution_summary = stamped("solution_summary", self.solution_summary)
        self.ground_truth_facts = [
            f.model_copy(update={"description": stamped(f"ground_truth_facts[{i}].description", f.description)})
            for i, f in enumerate(self.ground_truth_facts)
        ]
        self.lie_annotations = [
            a.model_copy(update={"note": stamped(f"lie_annotations[{i}].note", a.note)})
            for i, a in enumerate(self.lie_annotations)
        ]
        self.canaries = canaries
        return self

    def canary_set(self) -> set[str]:
        """All canary tokens of this case, for leakage assertions."""
        return set(self.canaries.values())
