# backend/app/domain/tiers.py
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.character import Character, CharacterSecret, RelationshipEdge, RelationshipGraph
from app.domain.world import CanonicalEvent, Claim, ContradictionFlag, Fact, TimeInterval


class T0Public(BaseModel):
    """
    PRD Section 5.2 (T0 Public): Baseline case header and initial crime briefing
    visible to all players and characters at the start of a case.
    """
    case_id: str = Field(..., min_length=1)
    title: str = Field(default="Untitled Case")
    victim_id: str = Field(default="victim")
    crime_location_id: str = Field(default="loc_study")
    crime_window: Optional[TimeInterval] = None
    suspect_ids: list[str] = Field(default_factory=list)


class T1Session(BaseModel):
    """
    PRD Section 5.2 (T1 Session): Player-visible investigation workspace.
    Contains only discovered/established facts, recorded claims, and contradiction flags.
    Strictly isolated from T2 character secrets and T3 canonical ground truth.
    """
    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(default="session_default", min_length=1)
    case_id: str = Field(default="case_default", min_length=1)
    current_turn: int = Field(default=0, ge=0)
    discovered_facts: list[Fact] = Field(default_factory=list)
    recorded_claims: list[Claim] = Field(default_factory=list)
    contradiction_flags: list[ContradictionFlag] = Field(default_factory=list)
    revealed_edges: list[RelationshipEdge] = Field(default_factory=list)

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
    model_config = ConfigDict(populate_by_name=True)

    case_id: str = Field(default="case_default", min_length=1)
    character_id: str = Field(..., min_length=1)
    character: Optional[Character] = None
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
    and unrevealed relationship graph. Inaccessible to gameplay roles.
    """
    case_id: str = Field(..., min_length=1)
    culprit_id: str = Field(..., min_length=1)
    crime_location_id: str = Field(..., min_length=1)
    crime_window: TimeInterval
    ground_truth_facts: list[Fact] = Field(default_factory=list)
    canonical_events: list[CanonicalEvent] = Field(default_factory=list)
    relationship_graph: RelationshipGraph = Field(default_factory=RelationshipGraph)
    canary_token: str = Field(
        default="CANARY_T3_DEFAULT",
        min_length=1,
        description="Unique T3 canary token that must never leak into T0, T1, or T2",
    )


