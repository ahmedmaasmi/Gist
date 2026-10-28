# backend/app/domain/world.py
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field, model_validator

from app.domain.enums import (
    ContradictionType,
    EvidenceCategory,
    ProvenanceClass,
    VerificationStatus,
)


class TimeInterval(BaseModel):
    """
    PRD Section 5.1: Structured time representation in minutes from midnight (0 to 1440)
    or simulation ticks, allowing deterministic overlap and travel-time math.
    Example: 21:30 to 22:30 -> start_min=1290, end_min=1350.
    """
    start_min: int = Field(..., ge=0, description="Start time in minutes from start of day/sim")
    end_min: int = Field(..., ge=0, description="End time in minutes from start of day/sim")

    @model_validator(mode="after")
    def validate_interval_order(self) -> "TimeInterval":
        if self.end_min < self.start_min:
            raise ValueError(
                f"Invalid TimeInterval: end_min ({self.end_min}) cannot be earlier "
                f"than start_min ({self.start_min})."
            )
        return self

    @property
    def duration(self) -> int:
        """Returns the length of the interval in minutes."""
        return self.end_min - self.start_min

    def overlaps(self, other: "TimeInterval") -> bool:
        """Returns True if this time interval overlaps with another interval."""
        return max(self.start_min, other.start_min) <= min(self.end_min, other.end_min)

    def overlap_duration(self, other: "TimeInterval") -> int:
        """
        Computes exact overlapping minutes between two intervals.
        Used directly by `opportunity_overlap` feature in PRD Section 5.3.
        """
        start = max(self.start_min, other.start_min)
        end = min(self.end_min, other.end_min)
        return max(0, end - start)


class Fact(BaseModel):
    """
    PRD Section 5.1: An established statement about the world.
    Example: 'The study door log shows a badge swipe by D. Reed at 21:52'.
    """
    fact_id: str = Field(..., min_length=1)
    case_id: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1, description="Human-readable fact statement")

    # Structured slots for deterministic consistency & feature derivation
    subject_id: Optional[str] = Field(None, description="Character ID involved, if applicable")
    target_id: Optional[str] = Field(None, description="Second Character ID (e.g., argument/debt)")
    location_id: Optional[str] = Field(None, description="Structured location ID")
    time_interval: Optional[TimeInterval] = Field(None, description="Structured time window")

    # Provenance & Feature Categorisation
    category: EvidenceCategory
    provenance: ProvenanceClass
    reliability: float = Field(..., ge=0.0, le=1.0, description="Weight used in feature derivation (0 to 1)")
    status: VerificationStatus = Field(default=VerificationStatus.ESTABLISHED)

    @model_validator(mode="after")
    def forbid_model_inferred_facts(self) -> "Fact":
        """
        PRD Section 5.1 Rule: Model inferences and hypotheses are stored separately
        and can never be promoted to facts by a model.
        """
        if self.provenance == ProvenanceClass.MODEL_INFERRED:
            raise ValueError("MODEL_INFERRED items can never be stored or instantiated as a Fact.")
        return self


class Claim(BaseModel):
    """
    PRD Section 5.1 & MD-04: An assertion made by a character or player.
    A claim is an observation, never automatically a fact.
    """
    claim_id: str = Field(..., min_length=1)
    case_id: str = Field(..., min_length=1)
    speaker_id: str = Field(..., min_length=1, description="Character ID who made the statement")
    turn_index: int = Field(..., ge=0, description="Interrogation turn when recorded")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Structured slots built via the Claim Builder (PRD Section 6.2)
    claimed_location_id: Optional[str] = Field(None, description="Where the speaker claims they or someone else was")
    claimed_time_interval: Optional[TimeInterval] = Field(None, description="When they claim to have been there")
    subject_id: str = Field(..., description="Who the claim is about (usually speaker_id or an observed suspect)")
    observed_character_ids: list[str] = Field(default_factory=list, description="Who they claim to have seen")
    has_corroboration_claim: bool = Field(default=False, description="Whether speaker claims a record/witness backs them")
    free_text: Optional[str] = Field(None, description="Optional player or LLM verbalised text")

    # MD-04 Provenance defaults: Always starts as SELF_REPORT and UNVERIFIED
    provenance: ProvenanceClass = Field(default=ProvenanceClass.SELF_REPORT)
    status: VerificationStatus = Field(default=VerificationStatus.UNVERIFIED)


class ContradictionFlag(BaseModel):
    """
    PRD Section 6.4.B & MD-05: Flagged conflict produced by the consistency engine.
    Links specific claims and facts with a plain-language explanation.
    """
    flag_id: str = Field(..., min_length=1)
    case_id: str = Field(..., min_length=1)
    suspect_id: str = Field(..., min_length=1)
    contradiction_type: ContradictionType
    primary_claim_id: str = Field(..., description="The claim being contradicted")
    conflicting_source_id: str = Field(..., description="The fact_id (CLAIM_FACT) or prior claim_id (CLAIM_CLAIM)")
    explanation: str = Field(..., min_length=1, description="Plain-language explanation of the conflict")
    is_semantic: bool = Field(default=False, description="False if caught by Layer 1 structured rules; True if Layer 2 NLI")