# backend/tests/test_ml_models.py
"""Step 7a: model inputs, grouped-CV tuning on train only, within-state normalisation, reproducibility."""
import json

import numpy as np
import pytest

from app.engine.dataset_generator import DatasetGenerator
from app.evaluation import model_report
from app.ml.baselines import load_states
from app.ml.data import MODEL_FEATURE_NAMES, RELATIVE_FEATURE_NAMES, build_table
from app.ml.models import distributions, fit_temperature, make_model, positive_scores, tune


@pytest.fixture(scope="module")
def tiny_dataset(tmp_path_factory):
    out = tmp_path_factory.mktemp("dataset")
    snapshots, manifest = DatasetGenerator.generate_dataset(total_cases=72, master_seed=11, ood_shifted_cases=3)
    DatasetGenerator.save_dataset(snapshots, manifest, out)
    return out


def test_relative_features_are_within_state_and_exclude_context(tiny_dataset):
    table = build_table(load_states(tiny_dataset / "features.csv", ["train"]))
    rel_cols = [MODEL_FEATURE_NAMES.index(f"{n}_rel") for n in RELATIVE_FEATURE_NAMES]
    assert "evidence_coverage" not in RELATIVE_FEATURE_NAMES
    for i in range(len(table.states)):
        rows = table.state_idx == i
        assert np.allclose(table.X[rows][:, rel_cols].sum(axis=0), 0.0, atol=1e-6)


def test_tuning_refuses_anything_but_train_states(tiny_dataset):
    val = build_table(load_states(tiny_dataset / "features.csv", ["val"]))
    with pytest.raises(ValueError, match="train-split"):
        tune(val, "logistic_regression", [{"C": 1.0}])


def test_within_state_distributions_sum_to_one_and_temperature_comes_from_val(tiny_dataset):
    states = load_states(tiny_dataset / "features.csv", ["train", "val"])
    train = build_table([s for s in states if s.split == "train"])
    val = build_table([s for s in states if s.split == "val"])
    model = make_model("logistic_regression", {"C": 1.0}).fit(train.X, train.y)
    scores = positive_scores(model, val.X)
    for dist in distributions(val, scores, temperature=1.7):
        assert sum(dist.values()) == pytest.approx(1.0)
    t = fit_temperature(val, scores)
    assert t == fit_temperature(val, scores)  # deterministic grid search on val inputs only


def test_training_and_report_are_reproducible(tiny_dataset, tmp_path, monkeypatch):
    monkeypatch.setattr(
        model_report,
        "FAMILIES",
        {
            "logistic_regression": [{"C": 0.1}, {"C": 1.0}],
            "lightgbm": [{"num_leaves": 7, "learning_rate": 0.1, "n_estimators": 50, "min_child_samples": 20}],
        },
    )
    a = model_report.train_and_report(tiny_dataset, artifacts_dir=tmp_path / "a", n_boot=100)
    b = model_report.train_and_report(tiny_dataset, artifacts_dir=tmp_path / "b", n_boot=100)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["split_evaluated"] == "val" and "leakage audit" in a["note"]
    selected = a["families"][a["selected"]]["version"]
    assert (tmp_path / "a" / "SELECTED").read_text().strip() == selected
    card = json.loads((tmp_path / "a" / selected / "model_card.json").read_text())
    assert card["feature_names"] == MODEL_FEATURE_NAMES and card["calibrated_on"] == "val split"
