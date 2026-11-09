# backend/tests/test_canary.py
"""
PRD Section 5.2: every T3 text field carries a unique canary token, and no canary may
appear in T0, T1 or T2 (nor, later, in API responses, prompts or logs).
"""
import json

import pytest

from app.domain.canary import CANARY_PREFIX, assert_no_canary, find_canaries, make_canary
from app.domain.tiers import T3Canonical
from app.engine.reveal_sampler import sample_reveal_snapshots
from app.engine.templates import generate_valid_case, get_template, load_all_templates


def test_canary_is_deterministic_and_unique():
    assert make_canary("case_1", 42, "solution_summary") == make_canary("case_1", 42, "solution_summary")
    tokens = {
        make_canary("case_1", 42, "solution_summary"),
        make_canary("case_1", 42, "ground_truth_facts[0].description"),
        make_canary("case_2", 42, "solution_summary"),
        make_canary("case_1", 43, "solution_summary"),
    }
    assert len(tokens) == 4, "Each (case, seed, field) must get its own canary"
    assert all(t.startswith(CANARY_PREFIX) for t in tokens)


def test_find_canaries_detects_known_and_foreign_tokens():
    mine = make_canary("case_1", 1, "solution_summary")
    foreign = make_canary("case_9", 9, "solution_summary")
    assert find_canaries({"text": f"oops {mine}"}, [mine]) == [mine]
    # A canary from another case is still caught via the generic prefix
    assert find_canaries(f"oops {foreign}", [mine]) == [CANARY_PREFIX]
    assert find_canaries("clean payload", [mine]) == []
    with pytest.raises(AssertionError):
        assert_no_canary({"x": mine}, [mine], where="test payload")


@pytest.fixture(scope="module")
def manor_bundle():
    _, bundle, _ = generate_valid_case(get_template("manor"), base_seed=42)
    return bundle


def test_every_t3_text_field_is_stamped(manor_bundle):
    t3 = manor_bundle.t3_canonical
    assert t3.canaries["solution_summary"] in t3.solution_summary
    for i, fact in enumerate(t3.ground_truth_facts):
        assert t3.canaries[f"ground_truth_facts[{i}].description"] in fact.description
    for i, lie in enumerate(t3.lie_annotations):
        assert t3.canaries[f"lie_annotations[{i}].note"] in lie.note
    assert len(t3.canary_set()) == len(t3.canaries), "Canaries must be unique within a case"


def test_restamping_is_idempotent(manor_bundle):
    """Re-validating a T3 record (e.g. loading it back from storage) must not double-stamp."""
    t3 = manor_bundle.t3_canonical
    reloaded = T3Canonical.model_validate(json.loads(t3.model_dump_json()))
    assert reloaded.canaries == t3.canaries
    assert reloaded.solution_summary == t3.solution_summary


@pytest.mark.parametrize("template_id", sorted(load_all_templates()))
@pytest.mark.parametrize("seed", [7, 42, 1234])
def test_no_canary_in_t0_t1_t2_or_snapshots(template_id, seed):
    _, bundle, _ = generate_valid_case(get_template(template_id), base_seed=seed)
    canaries = bundle.t3_canonical.canary_set()
    assert canaries

    assert_no_canary(bundle.t0_public, canaries, where="T0")
    assert_no_canary(bundle.t1_session, canaries, where="T1")
    for cid, pack in bundle.t2_knowledge.items():
        assert_no_canary(pack, canaries, where=f"T2[{cid}]")
    tpl = get_template(template_id)
    for snap in sample_reveal_snapshots(bundle, template=tpl, split="train"):
        assert_no_canary(snap.t1_partial, canaries, where=f"snapshot {snap.snapshot_id}")
