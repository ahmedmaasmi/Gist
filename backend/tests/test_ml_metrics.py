# backend/tests/test_ml_metrics.py
"""PRD 8.6: case-level metrics and case-bootstrap confidence intervals."""
import math

import pytest

from app.ml.metrics import EvidenceState, evaluate, paired_difference, state_metrics


def _state(case_id: str, culprit: str = "a", suspects=("a", "b", "c", "d"), stage=0) -> EvidenceState:
    return EvidenceState(
        case_id=case_id, template_id="t", split="val", order_idx=0, stage_idx=stage,
        reveal_fraction=1.0, suspect_ids=tuple(suspects), culprit_id=culprit, features={},
    )


def test_hand_computed_metrics():
    probs = {"a": 0.2, "b": 0.5, "c": 0.2, "d": 0.1}  # culprit a: one better (b), tied with c
    m = state_metrics(probs, "a")
    assert m["top1"] == 0.0
    assert m["top2"] == pytest.approx(0.5)            # one slot left, two candidates
    assert m["mrr"] == pytest.approx((1 / 2 + 1 / 3) / 2)
    assert m["log_loss"] == pytest.approx(-math.log(0.2))
    assert m["brier"] == pytest.approx(0.8**2 + 0.5**2 + 0.2**2 + 0.1**2)


def test_uniform_gets_chance_credit_not_luck():
    m = state_metrics({s: 0.25 for s in "abcd"}, "a")
    assert m["top1"] == pytest.approx(0.25) and m["top2"] == pytest.approx(0.5)
    assert m["mrr"] == pytest.approx((1 + 1 / 2 + 1 / 3 + 1 / 4) / 4)


def test_log_loss_floor_keeps_it_finite():
    assert math.isfinite(state_metrics({"a": 0.0, "b": 1.0}, "a")["log_loss"])


def test_bootstrap_is_deterministic_and_brackets_the_mean():
    states = [_state(f"c{i}", culprit="a" if i % 3 else "b") for i in range(30)]
    preds = [{"a": 0.7, "b": 0.1, "c": 0.1, "d": 0.1}] * 30
    r1, r2 = evaluate(states, preds, n_boot=500, seed=1), evaluate(states, preds, n_boot=500, seed=1)
    assert r1 == r2
    for cell in r1.values():
        assert cell["low"] <= cell["mean"] <= cell["high"]


def test_bootstrap_resamples_cases_not_rows():
    """Copying every evidence state 10 times must not narrow the CI: the unit is the case."""
    base = [_state(f"c{i}", culprit="a" if i % 2 else "b") for i in range(40)]
    pred = {"a": 0.6, "b": 0.2, "c": 0.1, "d": 0.1}
    once = evaluate(base, [pred] * 40, n_boot=1000, seed=0)["top1"]
    tenfold = evaluate([s for s in base for _ in range(10)], [pred] * 400, n_boot=1000, seed=0)["top1"]
    assert tenfold["mean"] == once["mean"]
    assert tenfold["high"] - tenfold["low"] == pytest.approx(once["high"] - once["low"], abs=1e-9)


def test_paired_difference_of_a_predictor_with_itself_is_zero():
    states = [_state(f"c{i}") for i in range(10)]
    preds = [{"a": 0.4, "b": 0.3, "c": 0.2, "d": 0.1}] * 10
    diff = paired_difference(states, preds, preds, n_boot=200)
    assert all(cell == {"mean": 0.0, "low": 0.0, "high": 0.0} for cell in diff.values())
