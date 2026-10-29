# backend/app/domain/character.py
from typing import Optional
from pydantic import BaseModel, Field, model_validator

from app.domain.enums import GoalType, RelationshipTag
from app.domain.world import TimeInterval


class CharacterTraits(BaseModel):
    """
    PRD Section 7A.1 (CH-01, CH-04): Bounded continuous traits [0.0, 1.0] driving
    deterministic simulation rules and Mode 2 dialogue state transitions.
    """
    temper: float = Field(..., ge=0.0, le=1.0)
    greed: float = Field(..., ge=0.0, le=1.0)
    loyalty: float = Field(..., ge=0.0, le=1.0)
    honesty: float = Field(..., ge=0.0, le=1.0)
    composure: float = Field(..., ge=0.0, le=1.0)
    secrecy: float = Field(..., ge=0.0, le=1.0)

    def check_ood(self, min_train: float = 0.1, max_train: float = 0.9) -> list[str]:
        """
        PRD Section 7A.6 (CH-04): Out-of-distribution check warning when any trait
        falls outside the synthetic training distribution [min_train, max_train].
        """
        warnings: list[str] = []
        trait_names = ("temper", "greed", "loyalty", "honesty", "composure", "secrecy")
        for name in trait_names:
            value = getattr(self, name)
            if value < min_train or value > max_train:
                warnings.append(
                    f"CH-04 OOD Warning: trait '{name}'={value:.2f} is outside "
                    f"training range [{min_train:.2f}, {max_train:.2f}]."
                )
        return warnings


class CharacterGoal(BaseModel):
    """
    PRD Section 7A.1: Explicit goal motivating a character's actions.
    """
    goal_type: GoalType
    target_character_id: Optional[str] = None
    description: str


class CharacterSecret(BaseModel):
    """
    PRD Section 7A.1: Hidden truth a character wants to conceal.
    May be linked to the crime or an innocent red herring.
    """
    secret_id: str
    description: str
    severity: float = Field(..., ge=0.0, le=1.0)
    is_crime_linked: bool = Field(
        ...,
        description="True if linked to the murder; False if it is an unrelated red herring (PRD 7A.1)",
    )


class ScheduleSlot(BaseModel):
    """
    PRD Section 7A.1: Planned baseline location during a specific time window.
    """
    time_interval: TimeInterval
    planned_location_id: str


class Character(BaseModel):
    """
    PRD Section 7A.1 (CH-01): Full character definition separating flavour identity
    (never passed to ML ranker) from structured simulation state.
    """
    # Identity (Flavour only, never used as ML features per 7A.1)
    character_id: str
    name: str
    occupation: str
    voice_notes: str = ""

    # Simulation state
    traits: CharacterTraits
    goals: list[CharacterGoal] = Field(default_factory=list)
    secrets: list[CharacterSecret] = Field(default_factory=list)
    schedule: list[ScheduleSlot] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_schedule_no_overlaps(self) -> "Character":
        """Ensures schedule slots for a single character do not overlap in time."""
        n = len(self.schedule)
        for i in range(n):
            for j in range(i + 1, n):
                iv_a = self.schedule[i].time_interval
                iv_b = self.schedule[j].time_interval
                if iv_a.overlap_duration(iv_b) > 0 or (
                    iv_a.start_min == iv_b.start_min and iv_a.end_min == iv_b.end_min
                ):
                    raise ValueError(
                        f"Overlapping schedule slots for character '{self.character_id}': "
                        f"[{iv_a.start_min}, {iv_a.end_min}] overlaps with "
                        f"[{iv_b.start_min}, {iv_b.end_min}]."
                    )
        return self


class RelationshipEdge(BaseModel):
    """
    PRD Section 7A.2 & 7A.6 (CH-06): Directed edge (A -> B) in the relationship graph.
    Supports asymmetric affinity, trust, and obligation between two characters.
    """
    source_id: str
    target_id: str
    affinity: float = Field(..., ge=-1.0, le=1.0)
    trust: float = Field(..., ge=0.0, le=1.0)
    loyalty: float = Field(default=0.0, ge=0.0, le=1.0, description="Optional explicit edge loyalty")
    obligation: float = Field(default=0.0, ge=0.0, le=1.0, description="Debts or favours owed")
    tags: list[RelationshipTag] = Field(default_factory=list)
    is_revealed_to_player: bool = Field(
        default=False,
        description="CH-06: Edges start hidden in T3 and flip to True only when discovered via T1 evidence or interviews",
    )

    @property
    def loyalty_or_trust(self) -> float:
        """PRD 7A.3: Combined loyalty/trust metric used in COVER_FOR precondition."""
        return max(self.loyalty, self.trust)

    @model_validator(mode="after")
    def forbid_self_edge(self) -> "RelationshipEdge":
        if self.source_id == self.target_id:
            raise ValueError(
                f"Self-loop relationship edge is not allowed (source_id == target_id == '{self.source_id}')."
            )
        return self

    def apply_delta(
        self,
        d_affinity: float = 0.0,
        d_trust: float = 0.0,
        d_obligation: float = 0.0,
    ) -> None:
        """
        Applies simulation deltas and clamps affinity to [-1.0, 1.0]
        and trust/obligation to [0.0, 1.0].
        """
        self.affinity = max(-1.0, min(1.0, self.affinity + d_affinity))
        self.trust = max(0.0, min(1.0, self.trust + d_trust))
        self.obligation = max(0.0, min(1.0, self.obligation + d_obligation))


class RelationshipGraph(BaseModel):
    """
    PRD Section 7A.2 & 7A.6 (CH-06): Directed relationship graph over case characters.
    """
    edges: list[RelationshipEdge] = Field(default_factory=list)

    def get_edge(self, source_id: str, target_id: str) -> Optional[RelationshipEdge]:
        """Returns the directed edge source_id -> target_id if present, else None."""
        for edge in self.edges:
            if edge.source_id == source_id and edge.target_id == target_id:
                return edge
        return None

    def get_player_visible_edges(self) -> list[RelationshipEdge]:
        """
        CH-06: Returns only edges discovered by the player (is_revealed_to_player is True),
        preventing T3 ground-truth relationship leakage into the T1 player workspace.
        """
        return [edge for edge in self.edges if edge.is_revealed_to_player]

