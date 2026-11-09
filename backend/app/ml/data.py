# backend/app/ml/data.py
"""
Evidence states -> model matrices.

One row per suspect per evidence state (PRD 8.3). Model inputs are the 12 T1 features plus, for each,
a WITHIN-STATE relative version (value minus the mean over that state's suspects). PRD 5.3 allows relative
features computed from T1; they give a per-suspect (pointwise) model the context "more than the others".
"""
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from app.features import FEATURES
from app.ml.baselines import FEATURE_NAMES
from app.ml.metrics import EvidenceState

# Relative versions only for per-suspect features: case-level context (evidence_coverage) is identical for
# every suspect in a state, so its relative version would be 0 plus floating-point noise.
RELATIVE_FEATURE_NAMES: list[str] = [f.name for f in FEATURES if f.group != "context"]
MODEL_FEATURE_NAMES: list[str] = [*FEATURE_NAMES, *(f"{n}_rel" for n in RELATIVE_FEATURE_NAMES)]


@dataclass
class Table:
    states: list[EvidenceState]
    X: np.ndarray       # (rows, len(MODEL_FEATURE_NAMES))
    y: np.ndarray       # 1 if the row's suspect is the culprit
    state_idx: np.ndarray  # row -> index into `states`
    folds: np.ndarray   # row -> grouped-CV fold, -1 if none

    def subset(self, state_mask: np.ndarray) -> "Table":
        """Keep only the states where `state_mask` is True (and their rows)."""
        keep_states = np.flatnonzero(state_mask)
        remap = {old: new for new, old in enumerate(keep_states)}
        rows = np.isin(self.state_idx, keep_states)
        return Table(
            states=[self.states[i] for i in keep_states],
            X=self.X[rows],
            y=self.y[rows],
            state_idx=np.array([remap[i] for i in self.state_idx[rows]], dtype=int),
            folds=self.folds[rows],
        )


def state_matrix(state: EvidenceState) -> np.ndarray:
    """(suspects, model features) for one evidence state, suspects in `state.suspect_ids` order."""
    base = np.array([[state.features[s][n] for n in FEATURE_NAMES] for s in state.suspect_ids], dtype=float)
    per_suspect = base[:, [FEATURE_NAMES.index(n) for n in RELATIVE_FEATURE_NAMES]]
    # Rounded so that "equal to the average" is exactly 0, not 1e-17 that a scaler would amplify.
    relative = np.round(per_suspect - per_suspect.mean(axis=0, keepdims=True), 9)
    return np.hstack([base, relative])


def build_table(states: Sequence[EvidenceState]) -> Table:
    blocks, ys, idx, folds = [], [], [], []
    for i, state in enumerate(states):
        blocks.append(state_matrix(state))
        ys.extend(1 if s == state.culprit_id else 0 for s in state.suspect_ids)
        idx.extend([i] * len(state.suspect_ids))
        folds.extend([-1 if state.cv_fold is None else state.cv_fold] * len(state.suspect_ids))
    return Table(
        states=list(states),
        X=np.vstack(blocks),
        y=np.array(ys, dtype=int),
        state_idx=np.array(idx, dtype=int),
        folds=np.array(folds, dtype=int),
    )
