# backend/app/domain/inference.py
"""
PRD Principle 4 & Section 5.1: Facts, statements, inferences and hypotheses are distinct object
types. Model inferences and hypotheses are stored separately and can never be promoted to facts
by a model. `Fact` itself rejects MODEL_INFERRED provenance; these types are where model output lives.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import ProvenanceClass


class ModelInference(BaseModel):
    """
    A single model output about one suspect (e.g. a ranker probability or a feature contribution),
    with the evidence it was computed from and the versions needed to reproduce it (MD-02, MD-08).
    Frozen: an inference is a logged observation of what the model said, never edited afterwards.
    """
    model_config = ConfigDict(frozen=True)

    inference_id: str = Field(..., min_length=1)
    case_id: str = Field(..., min_length=1)
    suspect_id: str = Field(..., min_length=1)
    kind: str = Field(..., min_length=1, description="e.g. 'culprit_probability', 'feature_contribution'")
    value: float
    evidence_ids: list[str] = Field(default_factory=list, description="T1 fact/claim IDs this was computed from")
    model_version: str = Field(..., min_length=1)
    feature_spec_version: str = Field(..., min_length=1)
    provenance: Literal[ProvenanceClass.MODEL_INFERRED] = ProvenanceClass.MODEL_INFERRED


class Hypothesis(BaseModel):
    """
    A candidate explanation of the case ('X did it because ...'), proposed by the model or the player.
    It links supporting and contradicting evidence but is never itself evidence.
    """
    hypothesis_id: str = Field(..., min_length=1)
    case_id: str = Field(..., min_length=1)
    suspect_id: str = Field(..., min_length=1)
    statement: str = Field(..., min_length=1)
    proposed_by: str = Field(..., min_length=1, description="'player' or a model version, e.g. 'lr-v1'")
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
