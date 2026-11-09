# backend/tests/test_inference.py
"""PRD Principle 4 & 5.1: model inferences and hypotheses are separate types and never become facts."""
import pytest
from pydantic import ValidationError

from app.domain.enums import EvidenceCategory, ProvenanceClass
from app.domain.inference import Hypothesis, ModelInference
from app.domain.world import Fact


def _inference(**overrides):
    data = dict(
        inference_id="inf_1",
        case_id="case_1",
        suspect_id="suspect_a",
        kind="culprit_probability",
        value=0.62,
        evidence_ids=["fact_3", "claim_7"],
        model_version="lr-v1",
        feature_spec_version="fs-v1",
    )
    data.update(overrides)
    return ModelInference(**data)


def test_inference_is_always_model_inferred_and_frozen():
    inf = _inference()
    assert inf.provenance == ProvenanceClass.MODEL_INFERRED
    with pytest.raises(ValidationError):
        _inference(provenance=ProvenanceClass.RECORD)
    with pytest.raises(ValidationError):
        inf.value = 0.99  # logged predictions are immutable


def test_inference_cannot_be_promoted_to_fact():
    inf = _inference()
    with pytest.raises(ValidationError):
        Fact(
            fact_id="promoted",
            case_id=inf.case_id,
            description="Model says suspect_a did it",
            subject_id=inf.suspect_id,
            category=EvidenceCategory.MOTIVE,
            provenance=inf.provenance,
            reliability=inf.value,
        )


def test_hypothesis_links_evidence_but_is_not_evidence():
    hyp = Hypothesis(
        hypothesis_id="hyp_1",
        case_id="case_1",
        suspect_id="suspect_a",
        statement="suspect_a used the study key during the window",
        proposed_by="player",
        supporting_evidence_ids=["fact_3"],
    )
    assert not isinstance(hyp, Fact)
    assert "provenance" not in Hypothesis.model_fields
