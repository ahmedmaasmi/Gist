# backend/tests/test_lie_annotations.py
"""
PRD 7.2 / 7A.3: intentional lies are recorded in T3 as LieAnnotations, never on the Claim itself.
"""
from app.domain.enums import LieKind
from app.engine.templates import generate_valid_case, get_template


def test_culprit_who_left_and_returned_is_annotated_as_lying():
    """
    Regression: the culprit's claimed location can equal their *last* location in the window
    (library -> study -> library). The claim "I stayed in the library" must still be a lie.
    """
    _, bundle, _ = generate_valid_case(get_template("manor"), base_seed=42)
    t3 = bundle.t3_canonical
    culprit_lies = [a for a in t3.lie_annotations if a.liar_id == t3.culprit_id]
    assert [a.kind for a in culprit_lies] == [LieKind.CULPRIT_COVER_STORY]
    assert culprit_lies[0].true_location_id == t3.crime_location_id


def test_lie_annotations_point_at_recorded_claims_and_stay_out_of_t1():
    _, bundle, _ = generate_valid_case(get_template("manor"), base_seed=42)
    claim_ids = {c.claim_id for c in bundle.t1_session.recorded_claims}
    for lie in bundle.t3_canonical.lie_annotations:
        assert lie.claim_id in claim_ids
    t1_json = bundle.t1_session.model_dump_json()
    assert "INTENTIONAL_LIE" not in t1_json
    assert "lie_annotations" not in t1_json
