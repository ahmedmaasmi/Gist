# backend/tests/test_baselines.py
"""PRD 8.5 baselines and the one-command baseline report."""
import json

import pytest

from app.engine.dataset_generator import DatasetGenerator
from app.evaluation.baseline_report import EVAL_SPLITS, build_report
from app.ml.baselines import fit_rule_temperature, load_states, uniform
from app.ml.metrics import METRICS, evaluate


@pytest.fixture(scope="module")
def tiny_dataset(tmp_path_factory):
    out = tmp_path_factory.mktemp("dataset")
    snapshots, manifest = DatasetGenerator.generate_dataset(total_cases=60, master_seed=7, ood_shifted_cases=6)
    DatasetGenerator.save_dataset(snapshots, manifest, out)
    return out


def test_uniform_top1_is_exactly_mean_chance(tiny_dataset):
    states = load_states(tiny_dataset / "features.csv", ["train"])
    result = evaluate(states, [uniform(s) for s in states], n_boot=100)
    chance = sum(1 / len(s.suspect_ids) for s in states) / len(states)
    assert result["top1"]["mean"] == pytest.approx(chance, abs=1e-4)


def test_every_state_has_exactly_one_culprit(tiny_dataset):
    for state in load_states(tiny_dataset / "features.csv", EVAL_SPLITS):
        assert state.culprit_id in state.suspect_ids


def test_temperature_is_fitted_on_val_only(tiny_dataset):
    """The report loads all splits, but its fitted temperature must equal a fit on val alone."""
    val = load_states(tiny_dataset / "features.csv", ["val"])
    report = build_report(tiny_dataset, n_boot=50)
    assert report["fitted_on_val"]["rule_softmax_temperature"] == fit_rule_temperature(val)


def test_report_is_complete_and_reproducible(tiny_dataset):
    a = build_report(tiny_dataset, n_boot=100, seed=3)
    b = build_report(tiny_dataset, n_boot=100, seed=3)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert "generator's logic" in a["note"]
    for split in EVAL_SPLITS:
        block = a["results"][split]
        assert block["cases"] > 0 and block["templates"]
        for baseline in ("uniform", "motive_opportunity_rule", "timeline_solver"):
            for metric in METRICS:
                cell = block["overall"][baseline][metric]
                assert cell["low"] <= cell["mean"] <= cell["high"]
