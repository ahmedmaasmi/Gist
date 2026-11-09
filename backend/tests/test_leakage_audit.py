# backend/tests/test_leakage_audit.py
"""PRD 8.8: the leakage audit runs end to end, and its checks can actually fail."""
import json

import pytest

from app.engine.dataset_generator import DatasetGenerator
from app.evaluation import leakage_audit, model_report


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    data = tmp_path_factory.mktemp("dataset")
    snapshots, manifest = DatasetGenerator.generate_dataset(total_cases=72, master_seed=9, ood_shifted_cases=3)
    DatasetGenerator.save_dataset(snapshots, manifest, data)
    mp = pytest.MonkeyPatch()
    mp.setattr(model_report, "FAMILIES", {
        "logistic_regression": [{"C": 1.0}],
        "lightgbm": [{"num_leaves": 7, "learning_rate": 0.1, "n_estimators": 50, "min_child_samples": 20}],
    })
    report = model_report.train_and_report(data, artifacts_dir=tmp_path_factory.mktemp("art"), n_boot=50)
    mp.undo()
    report_path = data / "models_val.json"
    report_path.write_text(json.dumps(report))
    return data, report_path


def test_audit_runs_and_reports_every_check(trained):
    data, report_path = trained
    result = leakage_audit.run_audit(data, report_path, n_boot=100)
    assert set(result["checks"]) == {
        "names", "shuffled_labels", "single_features", "permutation_importance",
        "briefing_fact", "features_from_visible_state_only", "suspect_order_invariance",
    }
    assert result["checks"]["features_from_visible_state_only"]["mismatches"] == 0
    assert result["checks"]["suspect_order_invariance"]["changed"] == 0
    assert "Leakage and shortcut audit" in leakage_audit.to_markdown(result)


def test_name_check_catches_planted_identifiers_and_labels():
    clean = list(leakage_audit.MODEL_FEATURE_NAMES)
    assert leakage_audit.name_violations(clean) == ([], [])
    bad, keys = leakage_audit.name_violations([*clean, "suspect_id_rel", "label"])
    assert bad == ["suspect_id_rel", "label"] and keys == ["label"]
