# backend/app/ml/ranker.py
"""
The suspect ranker used at play time (PRD 6.4.A, MD-01, MD-02, MD-06, MD-08, MD-09).

    ranker = Ranker.load()                 # selected model from ml/artifacts, or the rule fallback
    result = ranker.rank(t0, t1, setting)  # T0, T1 and the map only: T2/T3 cannot be passed in
    deltas = ranker.counterfactual(t0, t1, setting, "fact_...")  # "remove this evidence"

Every probability is a MODEL ESTIMATE, not a measure of guilt (PRD 11).
"""
import json
from pathlib import Path

import joblib
import numpy as np
from pydantic import BaseModel, Field

from app.domain.setting import SettingTemplate
from app.domain.tiers import T0Public, T1Session
from app.features import FEATURE_SPEC_VERSION, compute_suspect_features
from app.ml.abstention import TARGET_SELECTIVE_ACCURACY, decide
from app.ml.baselines import FEATURE_NAMES, rule_scores_from_features, softmax
from app.ml.data import MODEL_FEATURE_NAMES, matrix_from_features

ARTIFACTS_DIR = Path(__file__).resolve().parents[3] / "ml" / "artifacts"
ESTIMATE_LABEL = "Model estimate of who did it, given the evidence found so far. Not a measure of guilt."
# Fallback (MD-09): the motive + opportunity rule with the temperature fitted on val in `make baselines`
FALLBACK_TEMPERATURE = 1.5
FALLBACK_NOTICE = "The trained model is unavailable; showing the simple motive + opportunity rule instead."
FALLBACK_ABSTENTION = {"min_top_probability": 0.5, "min_margin": 0.1}


class SuspectExplanation(BaseModel):
    suspect_id: str
    probability: float
    # Contribution of each feature to this suspect's score, in log-odds (positive = more suspicious).
    # Base and within-state relative versions of a feature are summed into one human-readable entry.
    contributions: dict[str, float] = Field(default_factory=dict)
    baseline_score: float = 0.0  # the model's intercept / expected value, so contributions add up
    evidence: dict[str, list[str]] = Field(default_factory=dict)  # feature -> T1 fact/claim IDs


class RankingResult(BaseModel):
    label: str = ESTIMATE_LABEL
    probabilities: dict[str, float]
    explanations: list[SuspectExplanation]
    leading_suspect_id: str | None
    abstain: bool
    abstain_reason: str | None = None
    model_version: str
    feature_spec_version: str = FEATURE_SPEC_VERSION
    fallback_used: bool = False
    notice: str | None = None


def _merge_relative(values: np.ndarray) -> dict[str, float]:
    """Model-feature contributions -> one entry per base feature (base + its `_rel` twin)."""
    by_name = dict(zip(MODEL_FEATURE_NAMES, values.tolist(), strict=True))
    return {n: round(by_name[n] + by_name.get(f"{n}_rel", 0.0), 4) for n in FEATURE_NAMES}


class Ranker:
    def __init__(self, model=None, card: dict | None = None):
        self.model = model
        self.card = card or {}

    @property
    def fallback(self) -> bool:
        return self.model is None

    @classmethod
    def load(cls, artifacts_dir: Path = ARTIFACTS_DIR, version: str | None = None) -> "Ranker":
        """Loads the selected (or a named) model; returns the rule fallback if nothing can be loaded."""
        try:
            version = version or (artifacts_dir / "SELECTED").read_text(encoding="utf-8").strip()
            folder = artifacts_dir / version
            card = json.loads((folder / "model_card.json").read_text(encoding="utf-8"))
            if card.get("feature_spec_version") != FEATURE_SPEC_VERSION:
                return cls()  # a model trained on another feature spec must not be used silently
            return cls(joblib.load(folder / "model.joblib"), card)
        except (OSError, ValueError):
            return cls()

    def _contributions(self, X: np.ndarray) -> tuple[list[dict[str, float]], list[float]]:
        if self.card["family"] == "logistic_regression":
            scaler, lr = self.model[0], self.model[-1]
            z = (X - scaler.mean_) / scaler.scale_
            per_feature = z * lr.coef_[0]
            return [_merge_relative(row) for row in per_feature], [float(lr.intercept_[0])] * len(X)
        # LightGBM: exact per-feature contributions (TreeSHAP), last column = expected value
        contrib = self.model.predict(X, pred_contrib=True)
        return [_merge_relative(row[:-1]) for row in contrib], [float(row[-1]) for row in contrib]

    def rank(self, t0: T0Public, t1: T1Session, setting: SettingTemplate) -> RankingResult:
        rows = compute_suspect_features(t0, t1, setting)
        suspect_ids = [r.suspect_id for r in rows]
        features = {r.suspect_id: r.features for r in rows}
        evidence = {r.suspect_id: r.evidence for r in rows}

        if self.fallback:
            scores = rule_scores_from_features(features)
            probs = softmax(scores, FALLBACK_TEMPERATURE)
            contributions = [{} for _ in suspect_ids]
            baselines = [0.0] * len(suspect_ids)
            thresholds, version = FALLBACK_ABSTENTION, "rule-fallback"
        else:
            X = matrix_from_features(suspect_ids, features)
            p = np.clip(self.model.predict_proba(X)[:, 1], 1e-12, 1.0)
            w = np.exp((np.log(p) - np.log(p).max()) / self.card["temperature"])
            probs = dict(zip(suspect_ids, (w / w.sum()).tolist(), strict=True))
            contributions, baselines = self._contributions(X)
            thresholds, version = self.card["abstention"], self.card["model_version"]

        abstain, reason = decide(probs, thresholds["min_top_probability"], thresholds["min_margin"])
        if abstain and reason:
            reason = f"Not enough evidence to name anyone ({reason}; target accuracy {TARGET_SELECTIVE_ACCURACY:.0%})."
        leader = max(suspect_ids, key=lambda s: (probs[s], s)) if suspect_ids else None
        return RankingResult(
            probabilities={s: round(probs[s], 6) for s in suspect_ids},
            explanations=[
                SuspectExplanation(
                    suspect_id=s,
                    probability=round(probs[s], 6),
                    contributions=contributions[i],
                    baseline_score=round(baselines[i], 4),
                    evidence={k: v for k, v in evidence[s].items() if v},
                )
                for i, s in enumerate(suspect_ids)
            ],
            leading_suspect_id=None if abstain else leader,
            abstain=abstain,
            abstain_reason=reason,
            model_version=version,
            fallback_used=self.fallback,
            notice=FALLBACK_NOTICE if self.fallback else None,
        )

    def counterfactual(
        self, t0: T0Public, t1: T1Session, setting: SettingTemplate, evidence_id: str
    ) -> dict[str, float]:
        """
        MD-08 "remove this evidence": probability change per suspect if one fact or claim (and any
        relationship it revealed) had not been discovered. Positive = more suspicious without it.
        """
        reduced = t1.model_copy(
            update={
                "discovered_facts": [f for f in t1.discovered_facts if f.fact_id != evidence_id],
                "recorded_claims": [c for c in t1.recorded_claims if c.claim_id != evidence_id],
                "revealed_edges": [r for r in t1.revealed_edges if r.evidence_fact_id != evidence_id],
            }
        )
        before = self.rank(t0, t1, setting).probabilities
        after = self.rank(t0, reduced, setting).probabilities
        return {s: round(after[s] - before[s], 6) for s in before}
