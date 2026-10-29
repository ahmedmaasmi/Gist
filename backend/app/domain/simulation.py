# backend/app/domain/simulation.py
from pydantic import BaseModel, Field

from app.domain.tiers import (
    T0Public,
    T1Session,
    T2CharacterKnowledge,
    T3Canonical,
)
from app.domain.world import CanonicalEvent, SimulationConfig


class SimulatedCaseBundle(BaseModel):
    """
    PRD Section 7A.4: Complete output bundle produced by a deterministic
    SocialSimulator run and its ObservationModel derivation.
    """
    config: SimulationConfig
    t0_public: T0Public
    t1_session: T1Session
    t2_knowledge: dict[str, T2CharacterKnowledge]
    t3_canonical: T3Canonical
    canonical_events: list[CanonicalEvent]
    log_hash: str = Field(
        ...,
        min_length=1,
        description="PRD 7A.4: Deterministic SHA-256 hash of canonical_events",
    )


__all__ = [
    "SimulationConfig",
    "CanonicalEvent",
    "SimulatedCaseBundle",
]

