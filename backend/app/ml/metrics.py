# backend/app/ml/metrics.py
"""
PRD 8.6: case-level ranking metrics on within-case distributions, with 95% bootstrap confidence
intervals resampled over CASES, never rows.

The unit of evaluation is an evidence state: one case at one reveal stage and ordering. A predictor
gives a probability for every suspect of that state; exactly one suspect is the culprit.
"""
import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

METRICS = ("top1", "top2", "mrr", "log_loss", "brier")
LOG_LOSS_FLOOR = 1e-15
Distribution = dict[str, float]


@dataclass(frozen=True)
class EvidenceState:
    case_id: str
    template_id: str
    split: str
    order_idx: int
    stage_idx: int
    reveal_fraction: float
    suspect_ids: tuple[str, ...]
    culprit_id: str
    features: dict[str, dict[str, float]]  # suspect_id -> feature name -> value (T1-derived only)
    cv_fold: int | None = None  # grouped-CV fold (group = template) for train states

    @property
    def key(self) -> tuple[str, int, int]:
        return (self.case_id, self.order_idx, self.stage_idx)


def _topk_credit(better: int, tied: int, k: int) -> float:
    """
    Expected credit for "culprit in the top k" under a random tie-break: `better` suspects score
    strictly higher than the culprit, `tied` (including the culprit) score the same.
    """
    if better >= k:
        return 0.0
    return min(1.0, (k - better) / tied)


def state_metrics(probs: Distribution, culprit_id: str) -> dict[str, float]:
    """Metrics for one evidence state. Ties are scored by their expected value under random tie-break."""
    p_c = probs[culprit_id]
    better = sum(1 for p in probs.values() if p > p_c + 1e-12)
    tied = sum(1 for p in probs.values() if abs(p - p_c) <= 1e-12)
    mrr = sum(1.0 / rank for rank in range(better + 1, better + tied + 1)) / tied
    return {
        "top1": _topk_credit(better, tied, 1),
        "top2": _topk_credit(better, tied, 2),
        "mrr": mrr,
        "log_loss": -math.log(max(p_c, LOG_LOSS_FLOOR)),
        "brier": sum((p - (1.0 if sid == culprit_id else 0.0)) ** 2 for sid, p in probs.items()),
    }


def _per_case_sums(
    states: Sequence[EvidenceState], predictions: Sequence[Distribution]
) -> tuple[list[str], np.ndarray, np.ndarray]:
    """Per case: sum of each metric over its states, and the number of states."""
    index: dict[str, int] = {}
    sums: list[np.ndarray] = []
    counts: list[int] = []
    for state, probs in zip(states, predictions, strict=True):
        values = state_metrics(probs, state.culprit_id)
        row = np.array([values[m] for m in METRICS])
        i = index.setdefault(state.case_id, len(index))
        if i == len(sums):
            sums.append(np.zeros(len(METRICS)))
            counts.append(0)
        sums[i] += row
        counts[i] += 1
    return list(index), np.array(sums), np.array(counts, dtype=float)


def _bootstrap(sums: np.ndarray, counts: np.ndarray, n_boot: int, seed: int) -> np.ndarray:
    """(n_boot, n_metrics) state-weighted means over cases resampled with replacement."""
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(counts), size=(n_boot, len(counts)))
    return sums[idx].sum(axis=1) / counts[idx].sum(axis=1)[:, None]


def _summary(point: np.ndarray, boot: np.ndarray) -> dict[str, dict[str, float]]:
    low, high = np.percentile(boot, [2.5, 97.5], axis=0)
    return {
        m: {"mean": round(float(point[j]), 4), "low": round(float(low[j]), 4), "high": round(float(high[j]), 4)}
        for j, m in enumerate(METRICS)
    }


def evaluate(
    states: Sequence[EvidenceState],
    predictions: Sequence[Distribution],
    n_boot: int = 2000,
    seed: int = 0,
) -> dict[str, dict[str, float]]:
    """Mean of every metric over evidence states, with a 95% percentile CI from a case bootstrap."""
    _, sums, counts = _per_case_sums(states, predictions)
    point = sums.sum(axis=0) / counts.sum()
    return _summary(point, _bootstrap(sums, counts, n_boot, seed))


def paired_difference(
    states: Sequence[EvidenceState],
    predictions_a: Sequence[Distribution],
    predictions_b: Sequence[Distribution],
    n_boot: int = 2000,
    seed: int = 0,
) -> dict[str, dict[str, float]]:
    """
    A minus B on the same states, with a paired case bootstrap (the same resampled cases for both).
    If the 95% CI excludes 0, the difference is unlikely to be resampling noise (PRD 15).
    """
    cases_a, sums_a, counts = _per_case_sums(states, predictions_a)
    cases_b, sums_b, _ = _per_case_sums(states, predictions_b)
    assert cases_a == cases_b
    diff = sums_a - sums_b
    point = diff.sum(axis=0) / counts.sum()
    return _summary(point, _bootstrap(diff, counts, n_boot, seed))
