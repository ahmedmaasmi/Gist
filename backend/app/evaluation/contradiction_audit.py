# backend/app/evaluation/contradiction_audit.py
"""
Structured contradiction layer evaluation on generated cases (PRD 6.4.B, 10.1, MD-05).

Run:  make audit-contradictions   (or: cd backend && uv run python -m app.evaluation.contradiction_audit)

Ground truth comes from T3 (evaluator-only, PRD 5.2). A claim is INACCURATE if it carries an
intentional-lie annotation or if the speaker visited any location other than the claimed one during
the claimed interval (this includes honest confusion, D-009). Otherwise it is ACCURATE.
A claim is FLAGGED if the structured engine raises any contradiction for it. Separately, a
DISAGREEMENT (D-016) links two speakers' claims that cannot both be true without blaming either;
it is valid if at least one of the two claims is inaccurate, and it can only ever be valid.

Headline safety metric: false-positive rate = flagged accurate claims / accurate claims.
Confidence intervals are 95% Wilson intervals over claims; claims within a case are not independent,
so these intervals are optimistic (bootstrap over cases comes with the evaluation harness, step 6).

NOTE: scores on synthetic data measure recovery of the generator's logic.
"""
import argparse
import json
import math
from collections import Counter
from pathlib import Path

from app.domain.simulation import SimulatedCaseBundle
from app.engine.consistency import StructuredConsistencyEngine
from app.engine.templates import get_template, load_all_templates, sample_case_setup_from_template


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """Proportion with a 95% Wilson score interval: (estimate, low, high)."""
    if n == 0:
        return (float("nan"), float("nan"), float("nan"))
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (round(p, 3), round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3))


def label_claims(bundle: SimulatedCaseBundle) -> dict[str, tuple[bool, str]]:
    """claim_id -> (is_inaccurate, category) using T3 ground truth."""
    t3 = bundle.t3_canonical
    lies = {a.claim_id: a.kind.value for a in t3.lie_annotations}
    labels: dict[str, tuple[bool, str]] = {}
    for claim in bundle.t1_session.recorded_claims:
        window = claim.claimed_time_interval
        visited = {
            e.location_id
            for e in t3.canonical_events
            if e.event_kind == "MOVEMENT" and e.actor_id == claim.speaker_id and window.contains(e.tick_min)
        }
        role = "culprit" if claim.speaker_id == t3.culprit_id else "innocent"
        if claim.claim_id in lies:
            labels[claim.claim_id] = (True, f"{role}: lie {lies[claim.claim_id]}")
        elif visited - {claim.claimed_location_id}:
            labels[claim.claim_id] = (True, f"{role}: honest but inaccurate")
        else:
            labels[claim.claim_id] = (False, f"{role}: accurate")
    return labels


def run(seeds: int = 50) -> dict:
    confusion = Counter()
    by_category = Counter()
    dis = Counter()
    for template_id in sorted(load_all_templates()):
        tpl = get_template(template_id)
        for seed in range(seeds):
            bundle = sample_case_setup_from_template(template=tpl, seed=seed).simulate()
            case_map = bundle.setting  # this case's map, including its travel-time variation
            flagged = {
                f.primary_claim_id
                for f in StructuredConsistencyEngine.evaluate_session(bundle.t1_session, case_map)
            }
            labels = label_claims(bundle)
            disagreements = StructuredConsistencyEngine.find_disagreements(bundle.t1_session, case_map)
            in_disagreement = {cid for d in disagreements for cid in d.claim_ids}
            for d in disagreements:
                dis["disagreements"] += 1
                dis["valid"] += any(labels[cid][0] for cid in d.claim_ids)
            for claim_id, (inaccurate, category) in labels.items():
                by_category[(category, "flag_or_disagreement")] += (
                    claim_id in flagged or claim_id in in_disagreement
                )
                if inaccurate:
                    dis["inaccurate"] += 1
                    dis["inaccurate_caught_by_either"] += claim_id in flagged or claim_id in in_disagreement
                hit = claim_id in flagged
                confusion[("TP" if inaccurate else "FP") if hit else ("FN" if inaccurate else "TN")] += 1
                by_category[(category, "n")] += 1
                by_category[(category, "flagged")] += hit

    tp, fp, fn, tn = (confusion[k] for k in ("TP", "FP", "FN", "TN"))
    categories = sorted({c for c, _ in by_category})
    return {
        "claims": tp + fp + fn + tn,
        "cases": seeds * len(load_all_templates()),
        "false_positive_rate": wilson(fp, fp + tn),
        "recall_inaccurate_claims": wilson(tp, tp + fn),
        "precision": wilson(tp, tp + fp),
        "confusion": {"TP": tp, "FP": fp, "FN": fn, "TN": tn},
        "flag_rate_by_category": {
            c: wilson(by_category[(c, "flagged")], by_category[(c, "n")]) for c in categories
        },
        "disagreements": {
            "count": dis["disagreements"],
            "per_case": round(dis["disagreements"] / (seeds * len(load_all_templates())), 3),
            "valid_share": wilson(dis["valid"], dis["disagreements"]),
            "recall_flag_or_disagreement": wilson(dis["inaccurate_caught_by_either"], dis["inaccurate"]),
            "involvement_rate_by_category": {
                c: wilson(by_category[(c, "flag_or_disagreement")], by_category[(c, "n")]) for c in categories
            },
        },
        "note": (
            "Intervals are (estimate, low, high), 95% Wilson over claims. "
            "Synthetic-data scores measure recovery of the generator's logic."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=50, help="seeds per template")
    parser.add_argument("--out", type=Path, default=None, help="optional JSON output path")
    args = parser.parse_args()
    text = json.dumps(run(seeds=args.seeds), indent=2)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n")


if __name__ == "__main__":
    main()
