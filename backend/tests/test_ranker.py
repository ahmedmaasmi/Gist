# backend/tests/test_ranker.py
"""Step 7b: Ranker (MD-01/02/06/08/09) — explanations add up, cite real evidence, fallback and abstention."""
import inspect
import json
import math

import numpy as np
import pytest

from app.domain.setting import SettingTemplate
from app.domain.tiers import T0Public, T1Session
from app.engine.dataset_generator import DatasetGenerator
from app.evaluation import model_report
from app.features import compute_suspect_features
from app.ml.abstention import choose_thresholds, decide
from app.ml.data import matrix_from_features
from app.ml.ranker import ESTIMATE_LABEL, Ranker


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    data = tmp_path_factory.mktemp("dataset")
    snapshots, manifest = DatasetGenerator.generate_dataset(total_cases=72, master_seed=5, ood_shifted_cases=3)
    DatasetGenerator.save_dataset(snapshots, manifest, data)
    artifacts = tmp_path_factory.mktemp("artifacts")
    mp = pytest.MonkeyPatch()
    mp.setattr(model_report, "FAMILIES", {
        "logistic_regression": [{"C": 1.0}],
        "lightgbm": [{"num_leaves": 7, "learning_rate": 0.1, "n_estimators": 50, "min_child_samples": 20}],
    })
    report = model_report.train_and_report(data, artifacts_dir=artifacts, n_boot=50)
    mp.undo()
    val = [s for s in snapshots if s.split == "val" and s.reveal_fraction == 1.0]
    return report, artifacts, val


def _inputs(snap):
    return snap.t0_public, snap.t1_partial, snap.setting


def test_rank_only_accepts_public_and_session_data():
    params = list(inspect.signature(Ranker.rank).parameters.values())[1:]
    assert [p.annotation for p in params] == [T0Public, T1Session, SettingTemplate]


@pytest.mark.parametrize("family", ["logistic_regression", "lightgbm"])
def test_contributions_add_up_to_the_model_score(trained, family):
    report, artifacts, val = trained
    ranker = Ranker.load(artifacts, version=report["families"][family]["version"])
    snap = val[0]
    result = ranker.rank(*_inputs(snap))
    rows = compute_suspect_features(*_inputs(snap))
    X = matrix_from_features([r.suspect_id for r in rows], {r.suspect_id: r.features for r in rows})
    p = ranker.model.predict_proba(X)[:, 1]
    for i, expl in enumerate(result.explanations):
        logit = math.log(p[i] / (1 - p[i]))
        assert expl.baseline_score + sum(expl.contributions.values()) == pytest.approx(logit, abs=1e-2)
    assert sum(result.probabilities.values()) == pytest.approx(1.0, abs=1e-5)
    assert result.label == ESTIMATE_LABEL and result.model_version == report["families"][family]["version"]


def test_explanations_cite_only_evidence_that_was_discovered(trained):
    _, artifacts, val = trained
    ranker = Ranker.load(artifacts)
    for snap in val[:5]:
        known = {f.fact_id for f in snap.t1_partial.discovered_facts} | {
            c.claim_id for c in snap.t1_partial.recorded_claims
        }
        for expl in ranker.rank(*_inputs(snap)).explanations:
            for ids in expl.evidence.values():
                assert set(ids) <= known


def test_counterfactual(trained):
    _, artifacts, val = trained
    ranker = Ranker.load(artifacts)
    snap = val[0]
    assert set(ranker.counterfactual(*_inputs(snap), "not_an_evidence_id").values()) == {0.0}
    fact_id = snap.t1_partial.discovered_facts[0].fact_id
    deltas = ranker.counterfactual(*_inputs(snap), fact_id)
    assert sum(deltas.values()) == pytest.approx(0.0, abs=1e-5)  # probability moves between suspects


def test_fallback_when_no_model_is_available(trained, tmp_path):
    _, _, val = trained
    result = Ranker.load(tmp_path / "empty").rank(*_inputs(val[0]))
    assert result.fallback_used and result.notice and result.model_version == "rule-fallback"
    assert sum(result.probabilities.values()) == pytest.approx(1.0, abs=1e-5)


def test_model_from_another_feature_spec_is_not_used(trained, tmp_path):
    report, artifacts, _ = trained
    version = report["families"][report["selected"]]["version"]
    (tmp_path / version).mkdir()
    card = json.loads((artifacts / version / "model_card.json").read_text())
    card["feature_spec_version"] = "0.0.0"
    (tmp_path / version / "model_card.json").write_text(json.dumps(card))
    (tmp_path / version / "model.joblib").write_bytes((artifacts / version / "model.joblib").read_bytes())
    (tmp_path / "SELECTED").write_text(version)
    assert Ranker.load(tmp_path).fallback


def test_abstention_thresholds_meet_the_target_and_explain_themselves():
    rng = np.random.default_rng(0)
    dists, culprits = [], []
    for _ in range(400):
        p = rng.dirichlet(np.ones(4) * 0.7)
        names = ["a", "b", "c", "d"]
        dists.append(dict(zip(names, p.tolist(), strict=True)))
        culprits.append(names[int(rng.choice(4, p=p))])  # a calibrated "model"
    chosen = choose_thresholds(dists, culprits, target=0.8)
    assert chosen["accuracy"] >= 0.8 and 0 < chosen["coverage"] <= 1
    abstain, reason = decide({"a": 0.3, "b": 0.28, "c": 0.22, "d": 0.2}, 0.5, 0.1)
    assert abstain and "top probability" in reason and "runner-up" in reason
    assert decide({"a": 0.9, "b": 0.05, "c": 0.03, "d": 0.02}, 0.5, 0.1) == (False, None)
