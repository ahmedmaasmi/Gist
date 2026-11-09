# backend/app/ml/abstention.py
"""
PRD 6.4.E / MD-06: abstain ("not enough evidence to name anyone") when the top suspect's probability
or its margin over the runner-up is too small.

Thresholds are chosen on the VALIDATION split: among all (min_top_probability, min_margin) pairs whose
accuracy on the states the system does answer is >= TARGET_SELECTIVE_ACCURACY, take the one that answers
the most states. The target is a stated product choice (revisited in E4, PRD 8.7).
"""
from collections.abc import Sequence

from app.ml.metrics import Distribution

TARGET_SELECTIVE_ACCURACY = 0.80
TOP_GRID = tuple(round(0.05 * i, 2) for i in range(0, 20))
MARGIN_GRID = tuple(round(0.05 * i, 2) for i in range(0, 15))


def _top_two(dist: Distribution) -> tuple[str, float, float]:
    ranked = sorted(dist.items(), key=lambda kv: (-kv[1], kv[0]))
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    return ranked[0][0], ranked[0][1], ranked[0][1] - second


def decide(dist: Distribution, min_top: float, min_margin: float) -> tuple[bool, str | None]:
    """(abstain?, which condition triggered). Both conditions are reported if both fail."""
    _, top, margin = _top_two(dist)
    reasons = []
    if top < min_top:
        reasons.append(f"top probability {top:.2f} is below {min_top:.2f}")
    if margin < min_margin:
        reasons.append(f"lead over the runner-up {margin:.2f} is below {min_margin:.2f}")
    return (bool(reasons), "; ".join(reasons) or None)


def selective_stats(
    dists: Sequence[Distribution], culprits: Sequence[str], min_top: float, min_margin: float
) -> tuple[float, float]:
    """(coverage, accuracy on answered states)."""
    answered = correct = 0
    for dist, culprit in zip(dists, culprits, strict=True):
        if not decide(dist, min_top, min_margin)[0]:
            answered += 1
            correct += _top_two(dist)[0] == culprit
    coverage = answered / len(dists) if dists else 0.0
    return coverage, (correct / answered if answered else 0.0)


def choose_thresholds(
    dists: Sequence[Distribution], culprits: Sequence[str], target: float = TARGET_SELECTIVE_ACCURACY
) -> dict[str, float]:
    best: dict[str, float] | None = None
    for t in TOP_GRID:
        for m in MARGIN_GRID:
            coverage, accuracy = selective_stats(dists, culprits, t, m)
            if accuracy >= target and (best is None or coverage > best["coverage"]):
                best = {"min_top_probability": t, "min_margin": m, "coverage": coverage, "accuracy": accuracy}
    if best is None:  # target unreachable: answer only the most confident states
        t, m = TOP_GRID[-1], MARGIN_GRID[-1]
        coverage, accuracy = selective_stats(dists, culprits, t, m)
        best = {"min_top_probability": t, "min_margin": m, "coverage": coverage, "accuracy": accuracy}
    best["target_accuracy"] = target
    return {k: round(v, 4) for k, v in best.items()}


def risk_coverage_curve(dists: Sequence[Distribution], culprits: Sequence[str]) -> list[dict[str, float]]:
    """Accuracy on answered states vs coverage, sweeping the top-probability threshold (PRD 8.7)."""
    points = []
    for t in TOP_GRID:
        coverage, accuracy = selective_stats(dists, culprits, t, 0.0)
        points.append({"min_top_probability": t, "coverage": round(coverage, 4), "accuracy": round(accuracy, 4)})
    return points
