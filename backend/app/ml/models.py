# backend/app/ml/models.py
"""
PRD 6.4.A suspect ranker: a pointwise model scores each suspect (P(culprit | features)), then the scores
are normalised within the evidence state into a distribution over suspects.

Families (PRD 8.5): Logistic Regression (interpretable) and LightGBM (strongest candidate).
Hyperparameters: grouped cross-validation over the train split only, folds grouped by template (PRD 8.4).
Calibration: temperature scaling of the within-state distribution, fitted on val (PRD 8.6).
"""
import itertools
import math
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
from lightgbm import LGBMClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler

from app.ml.data import Table
from app.ml.metrics import Distribution

SEED = 2026
TEMPERATURE_GRID = (0.3, 0.5, 0.7, 0.85, 1.0, 1.2, 1.5, 2.0, 3.0)
LR_GRID = [{"C": c} for c in (0.01, 0.1, 1.0, 10.0)]
LGBM_GRID = [
    {"num_leaves": nl, "learning_rate": lr, "n_estimators": ne, "min_child_samples": mcs}
    for nl, lr, ne, mcs in itertools.product((7, 15, 31), (0.03, 0.1), (100, 300), (20, 50))
]


def make_model(family: str, params: dict):
    if family == "logistic_regression":
        return make_pipeline(StandardScaler(), LogisticRegression(C=params["C"], max_iter=5000))
    if family == "lightgbm":
        return LGBMClassifier(
            **params, random_state=SEED, deterministic=True, force_row_wise=True, n_jobs=1, verbose=-1
        )
    raise ValueError(family)


def positive_scores(model, X: np.ndarray) -> np.ndarray:
    return model.predict_proba(X)[:, 1]


def distributions(table: Table, scores: np.ndarray, temperature: float = 1.0) -> list[Distribution]:
    """
    Within-state normalisation (PRD 6.4.A) with temperature scaling: q_i ∝ p_i^(1/T).
    T > 1 flattens an over-confident model, T < 1 sharpens an under-confident one.
    """
    out: list[Distribution] = []
    log_p = np.log(np.clip(scores, 1e-12, 1.0)) / temperature
    for i, state in enumerate(table.states):
        rows = np.flatnonzero(table.state_idx == i)
        z = log_p[rows] - log_p[rows].max()
        w = np.exp(z)
        out.append(dict(zip(state.suspect_ids, (w / w.sum()).tolist(), strict=True)))
    return out


def mean_log_loss(table: Table, dists: list[Distribution]) -> float:
    return float(np.mean([-math.log(max(d[s.culprit_id], 1e-15)) for s, d in zip(table.states, dists, strict=True)]))


def fit_temperature(val: Table, val_scores: np.ndarray) -> float:
    """Calibration knob chosen on the validation split only."""
    return min(TEMPERATURE_GRID, key=lambda t: mean_log_loss(val, distributions(val, val_scores, t)))


@dataclass
class TuningResult:
    family: str
    best_params: dict
    cv_log_loss: dict[str, float] = field(default_factory=dict)  # str(params) -> mean CV log loss


def grouped_cv_log_loss(train: Table, family: str, params: dict) -> float:
    """Mean over folds of the case log loss on the held-out fold (whole templates held out)."""
    losses = []
    state_folds = np.array([s.cv_fold for s in train.states])
    for fold in sorted(set(state_folds.tolist())):
        fit_part = train.subset(state_folds != fold)
        held = train.subset(state_folds == fold)
        model = make_model(family, params).fit(fit_part.X, fit_part.y)
        losses.append(mean_log_loss(held, distributions(held, positive_scores(model, held.X))))
    return float(np.mean(losses))


def tune(train: Table, family: str, grid: list[dict], progress: Callable[[str], None] = lambda _: None) -> TuningResult:
    if any(s.split != "train" or s.cv_fold is None for s in train.states):
        raise ValueError("Tuning must only see train-split states that carry a CV fold.")
    result = TuningResult(family=family, best_params={})
    for params in grid:
        result.cv_log_loss[str(params)] = round(grouped_cv_log_loss(train, family, params), 6)
        progress(f"{family} {params} -> {result.cv_log_loss[str(params)]}")
    best = min(grid, key=lambda p: (result.cv_log_loss[str(p)], str(p)))
    result.best_params = best
    return result


def lr_coefficients(model: Pipeline, names: list[str]) -> dict[str, float]:
    """Coefficients on standardised inputs: the change in log-odds per one standard deviation."""
    coef = model[-1].coef_[0]
    return {n: round(float(c), 4) for n, c in zip(names, coef, strict=True)}
