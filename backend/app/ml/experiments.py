# backend/app/ml/experiments.py
"""Shared helpers for the leakage audit (PRD 8.8) and experiments (PRD 9): train on a column subset."""
from collections.abc import Sequence

import numpy as np

from app.ml.data import MODEL_FEATURE_NAMES, Table
from app.ml.metrics import Distribution
from app.ml.models import distributions, fit_temperature, make_model, positive_scores


def columns_for(base_features: Sequence[str]) -> list[int]:
    """Model-input columns for a set of base features: each feature plus its within-state relative twin."""
    wanted = set(base_features) | {f"{n}_rel" for n in base_features}
    return [i for i, name in enumerate(MODEL_FEATURE_NAMES) if name in wanted]


def fit_predict(
    train: Table,
    val: Table,
    evaluate_on: Sequence[Table],
    family: str,
    params: dict,
    columns: Sequence[int],
    y_train: np.ndarray | None = None,
) -> list[list[Distribution]]:
    """
    Train on `train` (optionally with replacement labels, for the shuffled-label control), calibrate the
    temperature on `val`, and return calibrated distributions for each table in `evaluate_on`.
    """
    cols = list(columns)
    model = make_model(family, params).fit(train.X[:, cols], train.y if y_train is None else y_train)
    temperature = fit_temperature(val, positive_scores(model, val.X[:, cols]))
    return [distributions(t, positive_scores(model, t.X[:, cols]), temperature) for t in evaluate_on]
