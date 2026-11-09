# backend/app/ml/baselines.py
"""
PRD 8.5 baselines, frozen before any result is looked at (PRD principle 7):

  uniform          p = 1 / n. Suspects are exchangeable, so the prior is uniform ("random and prior").
  motive_opportunity  a hand-weighted human heuristic over the T1 features (weights below, fixed a priori),
                      turned into probabilities with a softmax.
  timeline_solver  SymbolicTimelineSolver: uniform over suspects that records do not rule out.

The only fitted number per baseline is a calibration knob chosen on the VAL split by log loss (PRD 8.6):
the softmax temperature of the rule, and the epsilon the solver mixes with uniform so that a ruled-out
culprit never gets probability exactly 0. Ranking metrics do not depend on either.
"""
import csv
import json
import math
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from app.domain.setting import SettingTemplate
from app.domain.tiers import T0Public, T1Session
from app.engine.solver import SymbolicTimelineSolver
from app.features import FEATURES
from app.ml.metrics import Distribution, EvidenceState, state_metrics

FEATURE_NAMES = [f.name for f in FEATURES]

# Motive-plus-opportunity rule: what a reasonable human investigator would weigh. Fixed a priori.
RULE_WEIGHTS: dict[str, float] = {
    "motive_evidence": 1.0,
    "scene_presence_in_window": 1.0,
    "opportunity_overlap": 1.0,
}
RULE_LOG_ACCESS_WEIGHT = 0.5  # access_evidence counts every tick in a restricted room; log1p tames it

TEMPERATURE_GRID = (0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0)
EPSILON_GRID = (0.001, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3)


def load_states(features_csv: Path, splits: Iterable[str]) -> list[EvidenceState]:
    """Groups feature rows into evidence states (one per case, ordering and stage) for the given splits."""
    wanted = set(splits)
    grouped: dict[tuple[str, int, int], dict] = {}
    with Path(features_csv).open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["split"] not in wanted:
                continue
            key = (row["case_id"], int(row["order_idx"]), int(row["stage_idx"]))
            state = grouped.setdefault(
                key,
                {
                    "case_id": row["case_id"],
                    "template_id": row["template_id"],
                    "split": row["split"],
                    "order_idx": key[1],
                    "stage_idx": key[2],
                    "reveal_fraction": float(row["reveal_fraction"]),
                    "cv_fold": int(row["cv_fold"]) if row["cv_fold"] != "" else None,
                    "suspect_ids": [],
                    "culprit_id": None,
                    "features": {},
                },
            )
            sid = row["suspect_id"]
            state["suspect_ids"].append(sid)
            state["features"][sid] = {name: float(row[name]) for name in FEATURE_NAMES}
            if row["label"] == "1":
                state["culprit_id"] = sid
    states = []
    for raw in grouped.values():
        assert raw["culprit_id"] is not None, raw["case_id"]
        raw["suspect_ids"] = tuple(raw["suspect_ids"])
        states.append(EvidenceState(**raw))
    return states


def softmax(scores: dict[str, float], temperature: float) -> Distribution:
    top = max(scores.values())
    weights = {s: math.exp((v - top) / temperature) for s, v in scores.items()}
    total = sum(weights.values())
    return {s: w / total for s, w in weights.items()}


def uniform(state: EvidenceState) -> Distribution:
    return {s: 1.0 / len(state.suspect_ids) for s in state.suspect_ids}


def rule_scores(state: EvidenceState) -> dict[str, float]:
    return rule_scores_from_features(state.features)


def rule_scores_from_features(features: dict[str, dict[str, float]]) -> dict[str, float]:
    """The motive + opportunity rule on per-suspect features (also the ranker's fallback, MD-09)."""
    return {
        sid: sum(w * feats[name] for name, w in RULE_WEIGHTS.items())
        + RULE_LOG_ACCESS_WEIGHT * math.log1p(feats["access_evidence"])
        for sid, feats in features.items()
    }


def mean_log_loss(states: Sequence[EvidenceState], predict: Callable[[EvidenceState], Distribution]) -> float:
    return sum(state_metrics(predict(s), s.culprit_id)["log_loss"] for s in states) / len(states)


def fit_rule_temperature(val_states: Sequence[EvidenceState]) -> float:
    """Softmax temperature for the rule, chosen on validation states only."""
    return min(
        TEMPERATURE_GRID,
        key=lambda t: mean_log_loss(val_states, lambda s: softmax(rule_scores(s), t)),
    )


def rule_predictor(temperature: float) -> Callable[[EvidenceState], Distribution]:
    return lambda state: softmax(rule_scores(state), temperature)


# --- Symbolic timeline solver: needs the full evidence state (T0, T1, map), not just features.

SolverRaw = dict[tuple[str, int, int], Distribution]


def solver_distributions(snapshots_jsonl: Path, splits: Iterable[str]) -> SolverRaw:
    """
    Runs SymbolicTimelineSolver on every evidence state of the given splits. Lines of other splits are
    skipped before parsing, so the (large) snapshot file is read once and cheaply.
    """
    wanted = set(splits)
    out: SolverRaw = {}
    with Path(snapshots_jsonl).open(encoding="utf-8") as f:
        for line in f:
            if not any(f'"split": "{s}"' in line for s in wanted):
                continue
            snap = json.loads(line)
            if snap["split"] not in wanted:
                continue
            t0 = T0Public.model_validate(snap["t0_public"])
            out[(snap["case_id"], snap["order_idx"], snap["stage_idx"])] = (
                SymbolicTimelineSolver.predict_distribution(
                    t0=t0,
                    t1=T1Session.model_validate(snap["t1_partial"]),
                    setting=SettingTemplate.model_validate(snap["setting"]),
                )
            )
    return out


def solver_predictor(raw: SolverRaw, epsilon: float) -> Callable[[EvidenceState], Distribution]:
    """Solver distribution mixed with uniform: (1 - eps) * solver + eps / n."""

    def predict(state: EvidenceState) -> Distribution:
        base = raw[state.key]
        n = len(state.suspect_ids)
        return {s: (1 - epsilon) * base[s] + epsilon / n for s in state.suspect_ids}

    return predict


def fit_solver_epsilon(val_states: Sequence[EvidenceState], raw: SolverRaw) -> float:
    return min(EPSILON_GRID, key=lambda e: mean_log_loss(val_states, solver_predictor(raw, e)))
